"""Provenance summaries and a PROPOSED KDP AI-content disclosure for the owner to verify.
Nothing here is ever submitted to Amazon."""
from __future__ import annotations

from collections import Counter

DISCLOSURE_SOURCE = "https://kdp.amazon.com/en_US/help/topic/G200672390"


def _bucket(asset: dict) -> str:
    ai = asset.get("ai_involvement", "unknown")
    if ai in ("ai_generated", "ai_assisted", "none"):
        return ai
    return "unknown"


def disclosure(snapshot: dict) -> dict:
    assets = snapshot["assets"]
    used_interior = {pl["asset_id"] for p in snapshot.get("_manifest_pages", []) for pl in p.get("placements", []) if pl.get("asset_id")}
    if not used_interior:
        for p in snapshot["assembly"]["pages"]:
            for el in p.get("elements", []):
                if el["kind"] == "image":
                    used_interior.add(snapshot["versions"][el["asset_version_id"]]["asset_id"])
    cd = snapshot["cover"]["data"]
    used_cover = set()
    for vid in [cd.get("front_art_version_id"), cd.get("back_art_version_id")] + list(cd.get("back_thumbnail_version_ids") or []):
        if vid and vid in snapshot["versions"]:
            used_cover.add(snapshot["versions"][vid]["asset_id"])

    def summarize(ids):
        c = Counter(_bucket(assets[a]) for a in ids)
        return {"total": len(ids), "ai_generated": c["ai_generated"], "ai_assisted": c["ai_assisted"],
                "no_ai": c["none"], "unknown": c["unknown"]}

    interior, cover = summarize(used_interior), summarize(used_cover)
    listing = snapshot["listing"]

    def answer(s):
        if s["unknown"]:
            return "UNDETERMINED – some images have unknown AI involvement; resolve before answering KDP's questions."
        if s["ai_generated"]:
            return "AI-generated images: YES (some or all)"
        if s["ai_assisted"]:
            return "AI-assisted only (not AI-generated)"
        return "No AI-generated images recorded"

    return {
        "status": "PROPOSED – verify before answering KDP's AI-content questions yourself. This app never submits disclosures.",
        "source": DISCLOSURE_SOURCE,
        "definitions": {
            "ai_generated": "Content (text, images or translations) created by an AI tool counts as AI-generated, even if you substantially edited it afterwards.",
            "ai_assisted": "You created the content yourself and used AI tools to edit, refine, error-check or brainstorm; KDP does not require disclosing AI-assisted content (check the current guideline).",
            "brainstorming_note": "Using AI only for ideas, then drawing every illustration yourself, is a different case from AI-created artwork.",
        },
        "images": {"interior": interior | {"proposed_answer": answer(interior)},
                   "cover": cover | {"proposed_answer": answer(cover)}},
        "text": {"declared": listing.get("text_ai_involvement", "unknown")},
        "translations": {"declared": listing.get("translation_ai_involvement", "not_applicable")},
    }


def provenance_records(snapshot: dict) -> list[dict]:
    out = []
    for aid, a in snapshot["assets"].items():
        versions = [{"version_id": vid, "sha256": v["sha256"], "parent_version_id": v.get("parent_version_id"),
                     "operation": v.get("operation"), "width_px": v["width_px"], "height_px": v["height_px"],
                     "original_width_px": v.get("original_width_px"), "upscaled": v.get("upscaled", False)}
                    for vid, v in snapshot["versions"].items() if v["asset_id"] == aid]
        out.append({"asset_id": aid, "name": a["display_name"], "kind": a["kind"], "source_type": a["source_type"],
                    "creator": a.get("creator"), "license": a.get("license"), "license_evidence": a.get("license_evidence"),
                    "rights_declaration": a["rights_declaration"], "ai_involvement": a["ai_involvement"],
                    "generation": a.get("generation"), "review_status": a["review_status"], "review_notes": a.get("review_notes"),
                    "is_demo": a.get("is_demo", False), "versions_used": versions})
    return out
