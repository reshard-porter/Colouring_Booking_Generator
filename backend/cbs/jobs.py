"""Durable background jobs backed by SQLite.

- Status: queued → running → succeeded | failed | canceled | needs_attention
- Duplicate active jobs are prevented by a partial unique index on dedupe_key.
- On restart, interrupted idempotent jobs are re-queued (bounded by max_attempts);
  billable jobs are NEVER blindly retried: they move to needs_attention.
"""
from __future__ import annotations

import sqlite3
import threading
import time
import traceback
from typing import Callable

from .db import jdump, jload, new_id, now_iso

HANDLERS: dict[str, Callable] = {}
BILLABLE = {"generate_images", "write_stories"}


class JobCancelled(Exception):
    pass


class JobContext:
    def __init__(self, runner: "JobRunner", job: dict):
        self.runner, self.job = runner, job

    def progress(self, fraction: float | None, label: str = ""):
        self.runner.studio.db.x("UPDATE jobs SET progress=?, progress_label=?, updated_at=? WHERE id=?",
                                (None if fraction is None else max(0.0, min(1.0, fraction)), label[:200], now_iso(), self.job["id"]))

    def cancelled(self) -> bool:
        r = self.runner.studio.db.q1("SELECT cancel_requested FROM jobs WHERE id=?", (self.job["id"],))
        return bool(r and r["cancel_requested"])

    def check(self):
        if self.cancelled():
            raise JobCancelled()


def handler(name: str):
    def deco(fn):
        HANDLERS[name] = fn
        return fn
    return deco


class DuplicateJob(Exception):
    def __init__(self, job_id):
        super().__init__(job_id)
        self.job_id = job_id


class JobRunner:
    def __init__(self, studio):
        self.studio = studio
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    # --- API -----------------------------------------------------------------------------
    def enqueue(self, type_: str, project_id: str | None, params: dict, dedupe_key: str | None = None, max_attempts: int = 2) -> dict:
        if type_ not in HANDLERS:
            raise ValueError(f"Unknown job type {type_}")
        if type_ in BILLABLE:
            max_attempts = 1
        jid = new_id("job")
        ts = now_iso()
        try:
            self.studio.db.x("""INSERT INTO jobs(id, project_id, type, status, dedupe_key, params, attempts, max_attempts, created_at, updated_at)
                               VALUES (?,?,?,?,?,?,0,?,?,?)""", (jid, project_id, type_, "queued", dedupe_key, jdump(params), max_attempts, ts, ts))
        except sqlite3.IntegrityError:
            r = self.studio.db.q1("SELECT id FROM jobs WHERE dedupe_key=? AND status IN ('queued','running')", (dedupe_key,))
            raise DuplicateJob(r["id"] if r else None)
        self._wake.set()
        return self.get(jid)

    def get(self, jid: str) -> dict:
        r = self.studio.db.q1("SELECT * FROM jobs WHERE id=?", (jid,))
        if not r:
            raise KeyError(jid)
        d = dict(r)
        d["params"] = jload(d["params"])
        d["result"] = jload(d["result"])
        d["cancel_requested"] = bool(d["cancel_requested"])
        return d

    def list(self, project_id: str | None = None, limit: int = 50) -> list[dict]:
        if project_id:
            rows = self.studio.db.q("SELECT id FROM jobs WHERE project_id=? ORDER BY created_at DESC, rowid DESC LIMIT ?", (project_id, limit))
        else:
            rows = self.studio.db.q("SELECT id FROM jobs ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,))
        return [self.get(r["id"]) for r in rows]

    def cancel(self, jid: str) -> dict:
        j = self.get(jid)
        if j["status"] == "queued":
            self.studio.db.x("UPDATE jobs SET status='canceled', cancel_requested=1, finished_at=?, updated_at=? WHERE id=?", (now_iso(), now_iso(), jid))
        elif j["status"] == "running":
            self.studio.db.x("UPDATE jobs SET cancel_requested=1, updated_at=? WHERE id=?", (now_iso(), jid))
        return self.get(jid)

    def retry(self, jid: str) -> dict:
        j = self.get(jid)
        if j["status"] not in ("failed", "canceled"):
            raise ValueError("Only failed or canceled jobs can be retried")
        if j["type"] in BILLABLE:
            raise ValueError("Billable generation jobs are not retried automatically; start a new generation explicitly.")
        return self.enqueue(j["type"], j["project_id"], j["params"], j["dedupe_key"], j["max_attempts"])

    # --- lifecycle ---------------------------------------------------------------------------
    def recover(self) -> list[str]:
        """Called at startup: handle jobs that were running when the process stopped."""
        recovered = []
        for r in self.studio.db.q("SELECT * FROM jobs WHERE status='running'"):
            if r["type"] in BILLABLE:
                self.studio.db.x("UPDATE jobs SET status='needs_attention', error=?, finished_at=?, updated_at=? WHERE id=?",
                                 ("Interrupted while a paid generation request may have been in flight. Outcome unknown – not retried "
                                  "automatically to avoid duplicate charges. Check your provider dashboard.", now_iso(), now_iso(), r["id"]))
                self.studio.db.x("UPDATE generation_requests SET state='unknown_outcome', updated_at=? WHERE job_id=? AND state='submitting'",
                                 (now_iso(), r["id"]))
            elif r["attempts"] < r["max_attempts"]:
                self.studio.db.x("UPDATE jobs SET status='queued', error=?, progress=NULL, progress_label='Recovered after restart', updated_at=? WHERE id=?",
                                 ("Interrupted by application restart; re-queued.", now_iso(), r["id"]))
            else:
                self.studio.db.x("UPDATE jobs SET status='failed', error=?, finished_at=?, updated_at=? WHERE id=?",
                                 ("Interrupted by restart and out of retry attempts.", now_iso(), now_iso(), r["id"]))
            recovered.append(r["id"])
        return recovered

    def start(self):
        self.recover()
        self._thread = threading.Thread(target=self._loop, name="cbs-worker", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=10)

    def _claim(self) -> dict | None:
        db = self.studio.db
        with db.tx():
            r = db.q1("SELECT id FROM jobs WHERE status='queued' ORDER BY created_at, rowid LIMIT 1")
            if not r:
                return None
            db.x("UPDATE jobs SET status='running', attempts=attempts+1, started_at=?, updated_at=?, error=NULL WHERE id=?",
                 (now_iso(), now_iso(), r["id"]))
        return self.get(r["id"])

    def run_one(self) -> bool:
        job = self._claim()
        if not job:
            return False
        ctx = JobContext(self, job)
        try:
            result = HANDLERS[job["type"]](self.studio, ctx, job["params"])
            self.studio.db.x("UPDATE jobs SET status='succeeded', progress=1, result=?, finished_at=?, updated_at=? WHERE id=?",
                             (jdump(result), now_iso(), now_iso(), job["id"]))
        except JobCancelled:
            self.studio.db.x("UPDATE jobs SET status='canceled', finished_at=?, updated_at=? WHERE id=?", (now_iso(), now_iso(), job["id"]))
        except Exception as e:  # noqa: BLE001
            msg = f"{type(e).__name__}: {e}"
            status = "failed"
            if job["type"] in BILLABLE and getattr(e, "outcome_unknown", False):
                status = "needs_attention"
            self.studio.db.x("UPDATE jobs SET status=?, error=?, result=?, finished_at=?, updated_at=? WHERE id=?",
                             (status, msg[:2000], jdump({"trace": traceback.format_exc()[-3000:]}), now_iso(), now_iso(), job["id"]))
            # bounded automatic retry for idempotent jobs
            j = self.get(job["id"])
            if status == "failed" and job["type"] not in BILLABLE and j["attempts"] < j["max_attempts"] and getattr(e, "retryable", False):
                self.studio.db.x("UPDATE jobs SET status='queued', updated_at=? WHERE id=?", (now_iso(), job["id"]))
        return True

    def _loop(self):
        while not self._stop.is_set():
            try:
                did = self.run_one()
            except Exception:  # noqa: BLE001
                traceback.print_exc()
                did = False
            if not did:
                self._wake.wait(1.0)
                self._wake.clear()

    def wait(self, jid: str, timeout: float = 600) -> dict:
        t0 = time.time()
        while time.time() - t0 < timeout:
            j = self.get(jid)
            if j["status"] not in ("queued", "running"):
                return j
            time.sleep(0.2)
        raise TimeoutError(jid)
