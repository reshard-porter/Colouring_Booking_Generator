"""Approve a whole book in one step: declare rights for the artwork it uses and approve its illustration pages.

This only records what the owner declares – the app can't verify rights. It never changes a recorded AI status
(AI-generated stays AI-generated), never declares rights for the app's demonstration art, and leaves artwork the owner
marked "needs changes" or "rejected" alone. Pages without artwork can't be approved."""
from __future__ import annotations

from .snapshot import build_snapshot
from .db import now_iso

AI_CHOICES = ("leave", "none", "ai_assisted", "ai_generated")


def _book_assets(studio, pid: str) -> dict[str, dict]:
    snap = build_snapshot(studio, pid)
    return {aid: studio.asset(aid) for aid in snap["assets"]}


def plan(studio, pid: str) -> dict:
    """What 'Approve everything' would do, without changing anything."""
    assets = _book_assets(studio, pid)
    pages = [p for p in studio.pages(pid) if p["kind"] == "illustration"]
    with_art = [p for p in pages if any(e["kind"] == "image" for e in p["elements"])]
    ok = [a for a in assets.values() if not a["is_demo"] and a["review_status"] not in ("needs_changes", "rejected")]
    out = {
        "pages_to_approve": sum(1 for p in with_art if not p["approved"]),
        "pages_already_approved": sum(1 for p in with_art if p["approved"]),
        "pages_without_art": [p["label"] for p in pages if p not in with_art],
        "rights_to_declare": sum(1 for a in ok if a["rights_declaration"] == "unknown"),
        "artwork_to_approve": sum(1 for a in ok if a["review_status"] == "unreviewed"),
        "ai_unknown": sum(1 for a in ok if a["ai_involvement"] == "unknown"),
        "ai_generated": sum(1 for a in assets.values() if a["ai_involvement"] == "ai_generated"),
        "demo_art": [a["display_name"] for a in assets.values() if a["is_demo"]],
        "flagged": [a["display_name"] for a in assets.values() if a["review_status"] in ("needs_changes", "rejected")],
        "artwork_total": len(assets),
    }
    return out


def approve_everything(studio, pid: str, *, confirm: bool, creator: str | None = None, ai_for_unknown: str = "leave") -> dict:
    if not confirm:
        raise ValueError("Approving everything needs your confirmation that you checked the pages and may sell the artwork.")
    if ai_for_unknown not in AI_CHOICES:
        raise ValueError("ai_for_unknown must be leave, none, ai_assisted or ai_generated")
    assets = _book_assets(studio, pid)
    stamp = now_iso()[:10]
    author = (creator or studio.spec(pid).get("author") or "").strip()
    declared = approved_art = ai_set = 0
    for aid, a in assets.items():
        if a["is_demo"] or a["review_status"] in ("needs_changes", "rejected"):
            continue
        patch: dict = {}
        if a["rights_declaration"] == "unknown":
            patch["rights_declaration"] = "owner_declared"
            if not a.get("creator") and author:
                patch["creator"] = author
            declared += 1
        if a["ai_involvement"] == "unknown" and ai_for_unknown != "leave":
            patch["ai_involvement"] = ai_for_unknown
            if a["source_type"] == "unknown":
                patch["source_type"] = {"none": "user_created", "ai_assisted": "ai_assisted", "ai_generated": "ai_generated"}[ai_for_unknown]
            ai_set += 1
        if a["review_status"] == "unreviewed":
            patch["review_status"] = "approved"
            approved_art += 1
        if patch:
            note = (a.get("review_notes") or "").strip()
            patch["review_notes"] = (note + "\n" if note else "") + f"Rights declared and approved by the owner with “Approve everything” on {stamp}."
            studio.update_asset_provenance(aid, patch)
    approved_pages = 0
    for p in studio.pages(pid):
        if p["kind"] == "illustration" and not p["approved"] and any(e["kind"] == "image" for e in p["elements"]):
            studio.set_page_approval(p["id"], True, f"Approved with “Approve everything” on {stamp}")
            approved_pages += 1
    left = plan(studio, pid)
    return {"pages_approved": approved_pages, "rights_declared": declared, "artwork_approved": approved_art, "ai_status_set": ai_set,
            "still_open": {k: left[k] for k in ("pages_without_art", "ai_unknown", "demo_art", "flagged")}}


def unapprove_pages(studio, pid: str) -> dict:
    """Take back page approvals (rights declarations stay as declared)."""
    n = 0
    for p in studio.pages(pid):
        if p["kind"] == "illustration" and p["approved"]:
            studio.set_page_approval(p["id"], False)
            n += 1
    return {"pages_unapproved": n}
