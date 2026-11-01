"""Export pipeline: immutable snapshot → interior/cover/contact sheet → verification → ZIP."""
from __future__ import annotations

import json
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from . import preflight as pf
from .db import jdump, jload, new_id, now_iso
from .docs_gen import checklist_md, listing_md
from .geometry import PrintConfig, page_geometry, Rect
from .jobs import JobCancelled, handler
from .pricing import calculate
from .provenance import disclosure, provenance_records
from .render import Cancelled, render_contact_sheet, render_cover, render_interior
from .snapshot import build_snapshot, load_snapshot, public_project_json, store_snapshot
from .units import in_to_pt
from .verify import verify_cover, verify_interior


class ExportBlocked(Exception):
    pass


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "book"


def request_export(studio, runner, pid: str, mode: str, include_sources: bool = False, acknowledged_review: bool = False) -> dict:
    if mode not in ("draft", "release"):
        raise ValueError("mode must be draft or release")
    snap = build_snapshot(studio, pid)
    sid, sha = store_snapshot(studio, pid, snap)
    return runner.enqueue("export_package", pid, {"snapshot_id": sid, "mode": mode, "include_sources": include_sources,
                                                  "acknowledged_review": acknowledged_review}, dedupe_key=f"export:{pid}")


@handler("export_package")
def export_job(studio, ctx, params: dict) -> dict:
    sid, mode = params["snapshot_id"], params["mode"]
    snap = load_snapshot(studio, sid)
    pid = snap["project"]["id"]
    ctx.progress(0.02, "Running preflight on snapshot")
    rep = pf.run(studio, snap)
    if mode == "release":
        if rep["counts"]["error"]:
            raise ExportBlocked(f"Print-release package blocked by {rep['counts']['error']} unresolved technical error(s). "
                                "Fix them in Preflight, or export a draft.")
        if rep["counts"]["review"] and not params.get("acknowledged_review"):
            raise ExportBlocked("Human review items remain. Review them and confirm before creating a release package.")
    eid = new_id("exp")
    out_dir = studio.settings.exports_dir / eid
    work = out_dir / "package"
    (work / "preview").mkdir(parents=True, exist_ok=True)
    studio.db.x("INSERT INTO exports(id, project_id, snapshot_id, job_id, mode, status, created_at) VALUES (?,?,?,?,?,?,?)",
                (eid, pid, sid, ctx.job["id"], mode, "running", now_iso()))
    read = studio.storage.read
    try:
        cfg = PrintConfig(**snap["config"])
        asm = snap["assembly"]
        manifest = render_interior(snap, read, work / "interior.pdf",
                                   progress=lambda f, l: ctx.progress(0.05 + 0.55 * f, l), cancelled=ctx.cancelled)
        ctx.check()
        ctx.progress(0.62, "Verifying interior PDF")
        media = []
        for e in asm["pages"]:
            geo = page_geometry(cfg, e["number"], max(asm["page_count"], 24))
            media.append((in_to_pt(geo.media_w), in_to_pt(geo.media_h)))
        blank_pages = [e["number"] for e in asm["pages"] if e["kind"] == "blank"]
        v_int = verify_interior(work / "interior.pdf", asm["page_count"], media, blank_pages,
                                (in_to_pt(cfg.trim_w), in_to_pt(cfg.trim_h)))
        ctx.progress(0.7, "Rendering cover")
        cover_layout = render_cover(snap, read, work / "cover.pdf")
        g = snap["cover"]["geometry"]
        bc = Rect(**g["barcode"])
        H = g["full_height_in"]
        v_cov = verify_cover(work / "cover.pdf", g["full_width_pt"], g["full_height_pt"],
                             (in_to_pt(bc.x), in_to_pt(H - bc.y - bc.h), in_to_pt(bc.w), in_to_pt(bc.h)))
        ctx.check()
        ctx.progress(0.78, "Rendering contact sheet")
        status_line = (f"{'PRINT-RELEASE CANDIDATE' if mode == 'release' else 'DRAFT'} · Preflight: {rep['status_label']} · "
                       f"snapshot {snap_sha_short(studio, sid)} · {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")
        render_contact_sheet(snap, work / "interior.pdf", work / "cover.pdf", work / "preview" / "contact-sheet.pdf", status_line,
                             progress=lambda f, l: ctx.progress(0.78 + 0.1 * f, l), cancelled=ctx.cancelled)
        verification = {"interior": v_int, "cover": v_cov}
        if not (v_int["ok"] and v_cov["ok"]):
            raise RuntimeError("Exported files failed verification: " + "; ".join(v_int["errors"] + v_cov["errors"]))
        ctx.progress(0.9, "Writing documents")
        listing = snap["listing"]
        pricing = calculate(snap["pricing_profile"], asm["page_count"], cfg.large_trim, listing.get("list_price") or "9.99")
        snap_m = dict(snap, _manifest_pages=manifest)
        disc = disclosure(snap_m)
        (work / "listing.md").write_text(listing_md(snap, pricing, disc))
        (work / "preflight.json").write_text(json.dumps(rep, indent=2))
        (work / "preflight.md").write_text(pf.to_markdown(rep, snap["spec"]["title"]))
        (work / "provenance.json").write_text(json.dumps({"assets": provenance_records(snap), "ai_disclosure_proposal": disc}, indent=2))
        (work / "project.json").write_text(json.dumps(public_project_json(snap), indent=2))
        (work / "pricing.json").write_text(json.dumps(pricing, indent=2))
        (work / "publishing-checklist.md").write_text(checklist_md(snap, rep, pricing, mode))
        export_manifest = {
            "export_id": eid, "mode": mode, "snapshot_id": sid, "created_at": now_iso(),
            "files": {"interior.pdf": {"pages": manifest}, "cover.pdf": {"layout_in": cover_layout, "geometry": g}},
            "verification": verification,
        }
        (work / "manifest.json").write_text(json.dumps(export_manifest, indent=2))
        if params.get("include_sources"):
            src = work / "sources"
            src.mkdir()
            for vid, v in snap["versions"].items():
                a = snap["assets"][v["asset_id"]]
                ext = v["storage_key"].rsplit(".", 1)[-1]
                name = f"{slugify(a['display_name'].rsplit('.', 1)[0])}-v{v['version_no']}-{vid[-6:]}.{ext}"
                (src / name).write_bytes(read(v["storage_key"]))
        ctx.check()
        zip_name = f"{slugify(snap['spec']['title'])}-{mode}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.zip"
        with zipfile.ZipFile(out_dir / zip_name, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(work.rglob("*")):
                if f.is_file():
                    z.write(f, f.relative_to(work).as_posix())
        files = {f.relative_to(work).as_posix(): f.stat().st_size for f in sorted(work.rglob("*")) if f.is_file()}
        files["__zip__"] = zip_name
        studio.db.x("UPDATE exports SET status='succeeded', files=?, manifest=?, verification=? WHERE id=?",
                    (jdump(files), jdump({"pages": len(manifest)}), jdump(verification), eid))
        if mode == "release":
            studio.set_release_approval(pid, snap_sha_full(studio, sid), [f["code"] for f in rep["findings"] if f["severity"] == "review"])
        ctx.progress(1.0, "Done")
        return {"export_id": eid, "zip": zip_name, "mode": mode, "preflight_status": rep["status"],
                "page_count": asm["page_count"], "verification_ok": True}
    except (Cancelled, JobCancelled):
        studio.db.x("UPDATE exports SET status='canceled' WHERE id=?", (eid,))
        shutil.rmtree(work, ignore_errors=True)
        raise JobCancelled()
    except Exception:
        studio.db.x("UPDATE exports SET status='failed' WHERE id=?", (eid,))
        raise


def snap_sha_full(studio, sid):
    return studio.db.q1("SELECT sha256 FROM export_snapshots WHERE id=?", (sid,))["sha256"]


def snap_sha_short(studio, sid):
    return snap_sha_full(studio, sid)[:10]


def list_exports(studio, pid: str) -> list[dict]:
    out = []
    for r in studio.db.q("SELECT * FROM exports WHERE project_id=? ORDER BY created_at DESC, rowid DESC", (pid,)):
        d = dict(r)
        d["files"] = jload(d["files"])
        d["verification"] = jload(d["verification"])
        d["manifest"] = jload(d["manifest"])
        out.append(d)
    return out


def export_file_path(studio, eid: str, rel: str) -> Path:
    base = (studio.settings.exports_dir / eid).resolve()
    r = studio.db.q1("SELECT files FROM exports WHERE id=?", (eid,))
    if not r:
        raise KeyError(eid)
    files = jload(r["files"]) or {}
    if rel == "zip":
        p = base / files["__zip__"]
    else:
        if rel not in files:
            raise KeyError(rel)
        p = base / "package" / rel
    p = p.resolve()
    if base not in p.parents:
        raise KeyError(rel)
    return p
