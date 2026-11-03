"""Immutable project snapshots. Exports render ONLY from a stored snapshot."""
from __future__ import annotations

import hashlib
import json

from .db import jdump, jload, new_id, now_iso
from .geometry import resolve_config
from .layout import assemble


def build_snapshot(studio, pid: str) -> dict:
    prow = studio.project_row(pid)
    spec = studio.spec(pid)
    cfg = resolve_config(spec)
    pages = studio.pages(pid)
    asm = assemble(pages, spec)
    by_id = {p["id"]: p for p in pages}
    for entry in asm["pages"]:
        if entry["page_id"]:
            p = by_id[entry["page_id"]]
            entry["elements"] = p["elements"]
            entry["label"] = p["label"]
            entry["approved"] = p["approved"]
            entry["scene_id"] = p["scene_id"]
    if any(e["kind"] == "story" for e in asm["pages"]):
        from .stories import story_map
        stories = story_map(studio, pid)
        for entry in asm["pages"]:
            if entry["kind"] == "story":
                st = stories.get(entry["story_for"]) or {}
                entry["story"] = {"title": st.get("title", ""), "text": st.get("text", ""), "ai": bool((st.get("meta") or {}).get("ai"))}
    cover = studio.cover(pid)
    version_ids = set()
    for e in asm["pages"]:
        for el in e.get("elements", []):
            if el["kind"] == "image":
                version_ids.add(el["asset_version_id"])
    cd = cover["data"]
    for vid in [cd.get("front_art_version_id"), cd.get("back_art_version_id")] + list(cd.get("back_thumbnail_version_ids") or []):
        if vid:
            version_ids.add(vid)
    versions, assets = {}, {}
    for vid in sorted(version_ids):
        v = studio.version(vid)
        versions[vid] = {k: v[k] for k in ("asset_id", "sha256", "storage_key", "mime", "width_px", "height_px",
                                            "dpi_meta_x", "dpi_meta_y", "original_width_px", "original_height_px",
                                            "parent_version_id", "operation", "upscaled", "version_no")}
        if v["asset_id"] not in assets:
            a = studio.asset(v["asset_id"])
            assets[v["asset_id"]] = {k: a[k] for k in ("display_name", "kind", "source_type", "creator", "license",
                                                       "license_evidence", "rights_declaration", "ai_involvement",
                                                       "generation", "review_status", "review_notes", "is_demo")}
    snap = {
        "format": "coloring-book-studio-snapshot", "format_version": 1,
        "project": {"id": pid, "name": prow["name"], "is_sample": bool(prow["is_sample"])},
        "layout_revision": prow["layout_revision"],
        "spec": spec, "config": cfg.as_dict(), "assembly": asm,
        "cover": {"data": cd, "geometry": cover["geometry"], "stale": cover["stale"], "stale_reasons": cover["stale_reasons"]},
        "versions": versions, "assets": assets,
        "listing": studio.listing(pid), "style_guide": studio.style_guide(pid), "scenes": studio.scenes(pid),
        "pricing_profile": studio.active_pricing_profile(spec.get("marketplace", "Amazon.com")),
    }
    return snap


def snapshot_sha(snap: dict) -> str:
    return hashlib.sha256(json.dumps(snap, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def store_snapshot(studio, pid: str, snap: dict) -> tuple[str, str]:
    sha = snapshot_sha(snap)
    existing = studio.db.q1("SELECT id FROM export_snapshots WHERE project_id=? AND sha256=?", (pid, sha))
    if existing:
        return existing["id"], sha
    sid = new_id("snap")
    studio.db.x("INSERT INTO export_snapshots(id, project_id, created_at, sha256, layout_revision, data) VALUES (?,?,?,?,?,?)",
                (sid, pid, now_iso(), sha, snap["layout_revision"], jdump(snap)))
    return sid, sha


def load_snapshot(studio, sid: str) -> dict:
    r = studio.db.q1("SELECT data FROM export_snapshots WHERE id=?", (sid,))
    return jload(r["data"])


def public_project_json(snap: dict) -> dict:
    """Project data for the export package: no storage paths, secrets or local environment data."""
    s = json.loads(json.dumps(snap))
    for v in s["versions"].values():
        v.pop("storage_key", None)
    s.pop("_manifest_pages", None)
    return s
