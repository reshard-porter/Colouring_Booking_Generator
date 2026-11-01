"""Seeded, editable sample project: 'Cute Island Adventures' with 40 DEMONSTRATION illustrations."""
from __future__ import annotations

from .democraft import design_description, draw_scene
from .imaging import to_png_bytes

DEMO_DECL = {
    "source_type": "demo_sample",
    "creator": "Coloring Book Studio sample generator (procedural drawing code, not AI)",
    "license": "Sample placeholder bundled with Coloring Book Studio. Not commercially reviewed. Replace or confirm before publishing.",
    "rights_declaration": "unknown",
    "ai_involvement": "none",
    "is_demo": True,
}


def seed_sample(studio, progress=None) -> str:
    existing = studio.db.q1("SELECT id FROM projects WHERE is_sample=1")
    if existing:
        return existing["id"]
    pid = studio.create_project("Cute Island Adventures (sample)", is_sample=True)
    pages = [p for p in studio.pages(pid) if p["kind"] == "illustration"]
    first_version = None
    for i, page in enumerate(pages):
        desc = design_description(i)
        scene = studio.save_scene(pid, desc)
        im = draw_scene(i)
        data = to_png_bytes(im, dpi=300)
        asset = studio.import_asset(pid, f"demo-{i + 1:02d}-{desc['demo_design_key']}.png", data, DEMO_DECL)
        vid = asset["current_version_id"]
        first_version = first_version or vid
        studio.update_page_meta(page["id"], {"scene_id": scene["id"], "label": f"{i + 1}. {desc['subject'][2:]} {desc['action']}"})
        studio.place_asset(page["id"], vid, fit="safe")
        if progress:
            progress((i + 1) / len(pages))
    cover_art = studio.derive_cover_art(first_version)
    thumbs = [studio.pages(pid)]  # noqa: F841 - kept simple below
    illus = [p for p in studio.pages(pid) if p["kind"] == "illustration"]
    thumb_ids = [illus[k]["elements"][0]["asset_version_id"] for k in (9, 18, 27) if k < len(illus)]
    studio.update_cover(pid, {"front_art_version_id": cover_art["current_version_id"], "back_thumbnail_version_ids": thumb_ids})
    return pid
