"""Start the next book in a series: a new project that reuses the first book's look and cast, but not its story or art."""
from __future__ import annotations

import copy
import re


def next_title(title: str) -> tuple[str, str, int]:
    """'Sprocket Squad: Book 1' -> ('Sprocket Squad: Book 2', 'Sprocket Squad', 2); 'Moon Friends' -> ('Moon Friends: Book 2', 'Moon Friends', 2)."""
    m = re.match(r"^(.*?)[\s:,–—-]*\b(book|volume|vol\.?|part)\s*#?\s*(\d+)\s*$", title.strip(), re.I)
    if m:
        series, word, n = m.group(1).strip(" :,–—-"), m.group(2), int(m.group(3)) + 1
        return f"{series}: {word.title() if word.islower() else word} {n}", series, n
    return f"{title.strip()}: Book 2", title.strip(), 2


def start_next_book(studio, pid: str, title: str | None = None) -> dict:
    src_spec, src_style, src_listing = studio.spec(pid), studio.style_guide(pid), studio.listing(pid)
    src_cover = studio.cover(pid)["data"]
    auto_title, series_name, number = next_title(src_spec["title"])
    series_name = (src_listing.get("series_name") or "").strip() or series_name
    if src_listing.get("series_number") and str(src_listing["series_number"]).isdigit() and not title:
        number = int(src_listing["series_number"]) + 1
        auto_title = f"{series_name}: Book {number}"
    new_title = (title or auto_title).strip()[:150]
    spec = {k: v for k, v in src_spec.items() if k not in ("title", "subtitle", "theme")}
    spec.update({"title": new_title, "subtitle": "", "theme": ""})
    new = studio.create_project(new_title, spec)
    # intro pages: same set and descriptions (crew sheets, maps and badges usually carry over); no art
    src_intro = [p for p in studio.pages(pid) if p["kind"] == "intro"]
    src_desc = {r["page_id"]: r for r in studio.intro_descriptions(pid)}
    for p in [p for p in studio.pages(new) if p["kind"] == "intro"]:
        studio.delete_page(p["id"])
    for p in src_intro:
        np_ = studio.add_page(new, "intro")
        studio.update_page_meta(np_["id"], {"label": p["label"]})
        els = []
        for e in p["elements"]:
            if e["kind"] == "image":
                continue
            e = {k: v for k, v in e.items() if k != "id"}
            if e["kind"] == "text" and e.get("text") and src_spec.get("title"):
                e["text"] = e["text"].replace(src_spec["title"], new_title)
                if src_spec.get("subtitle"):
                    e["text"] = e["text"].replace(src_spec["subtitle"], "")
            els.append(e)
        studio.save_elements(np_["id"], els, reason="series: copy intro page")
        d = src_desc.get(p["id"])
        if d and d["description"]:
            studio.set_intro_description(np_["id"], d["description"], d["placement"])
    # pages in the right order (intro first), page count note in spec
    ids = [p["id"] for p in studio.pages(new)]
    intro_ids = [p["id"] for p in studio.pages(new) if p["kind"] == "intro"]
    studio.reorder_pages(new, intro_ids + [i for i in ids if i not in intro_ids])
    studio.update_spec(new, {"intro_pages": len(intro_ids)})
    # style: same look and cast; references to the first book's images don't carry over
    style = copy.deepcopy(src_style)
    style["reference_images"] = []
    for c in style.get("characters", []):
        c["reference_asset_ids"] = []
    style["previous_master_style"] = ""
    studio.update_style_guide(new, {k: v for k, v in style.items()})
    # listing: same author/age/series; story-specific text starts empty
    studio.update_listing(new, {"author": src_listing.get("author", ""), "language": src_listing.get("language", "English"),
                                "age_range": src_listing.get("age_range", ""), "audience": src_listing.get("audience", ""),
                                "keywords": list(src_listing.get("keywords") or []), "list_price": src_listing.get("list_price", ""),
                                "isbn_choice": "undecided", "series_name": series_name, "series_number": str(number),
                                "text_ai_involvement": src_listing.get("text_ai_involvement", "none")})
    if not (src_listing.get("series_name") or "").strip():
        studio.update_listing(pid, {"series_name": series_name, "series_number": str(number - 1)})
    # cover: same colors and type sizes; art, descriptions and back text are per book
    keep = {k: src_cover[k] for k in ("background", "accent", "title_color", "text_color", "title_pt", "subtitle_pt", "author_pt",
                                       "back_copy_pt", "spine_text_pt") if k in src_cover}
    studio.update_cover(new, keep)
    return {"project_id": new, "title": new_title, "series_name": series_name, "series_number": number,
            "copied": ["book setup (size, paper, ages, page count)", "style, master style and cleanup", "characters and team",
                       f"{len(src_intro)} intro pages with their descriptions (no art)", "cover colors", "author, ages and keyword ideas"],
            "not_copied": ["the story (book description) and subtitle", "page descriptions", "all artwork", "back-cover text and listing description"]}
