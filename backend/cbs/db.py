"""SQLite access + forward-only SQL migrations."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class Database:
    """Thread-safe-enough wrapper: one connection per thread, WAL mode."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._local = threading.local()
        self.write_lock = threading.RLock()

    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30, isolation_level=None, check_same_thread=False)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys=ON")
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA busy_timeout=30000")
            self._local.conn = c
        return c

    def close(self) -> None:
        c = getattr(self._local, "conn", None)
        if c is not None:
            c.close()
            self._local.conn = None

    # --- helpers -------------------------------------------------------------
    def q(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        return list(self.conn().execute(sql, tuple(params)))

    def q1(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        return self.conn().execute(sql, tuple(params)).fetchone()

    def x(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self.write_lock:
            return self.conn().execute(sql, tuple(params))

    def tx(self):
        return _Tx(self)

    # --- migrations ----------------------------------------------------------
    def migrate(self) -> list[str]:
        applied: list[str] = []
        with self.write_lock:
            c = self.conn()
            c.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
            done = {r[0] for r in c.execute("SELECT name FROM schema_migrations")}
            for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
                if f.name in done:
                    continue
                c.execute("BEGIN")
                try:
                    for stmt in _split_sql(f.read_text()):
                        c.execute(stmt)
                    c.execute("INSERT INTO schema_migrations(name, applied_at) VALUES (?,?)", (f.name, now_iso()))
                    c.execute("COMMIT")
                except Exception:
                    c.execute("ROLLBACK")
                    raise
                applied.append(f.name)
        return applied


def _split_sql(text: str) -> list[str]:
    stmts, buf = [], []
    for line in text.splitlines():
        if line.strip().startswith("--"):
            continue
        buf.append(line)
        if line.rstrip().endswith(";"):
            s = "\n".join(buf).strip()
            if s:
                stmts.append(s)
            buf = []
    tail = "\n".join(buf).strip()
    if tail:
        stmts.append(tail)
    return stmts


class _Tx:
    def __init__(self, db: Database):
        self.db = db

    def __enter__(self):
        self.db.write_lock.acquire()
        self.db.conn().execute("BEGIN IMMEDIATE")
        return self.db

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.db.conn().execute("COMMIT")
            else:
                self.db.conn().execute("ROLLBACK")
        finally:
            self.db.write_lock.release()
        return False


def jload(s: str | None, default: Any = None) -> Any:
    if s is None or s == "":
        return default
    return json.loads(s)


def jdump(v: Any) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"))
