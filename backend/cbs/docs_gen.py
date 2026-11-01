"""Markdown documents included in the publishing package."""
from __future__ import annotations

from .provenance import DISCLOSURE_SOURCE

LOW_CONTENT_URL = "https://kdp.amazon.com/en_US/help/topic/GGE5T76TWKA85DJM"
ISBN_URL = "https://kdp.amazon.com/en_US/help/topic/GTJ8LBXL6Z4WV5QX"


def listing_md(snap: dict, pricing: dict, disclosure: dict) -> str:
    L, s, a = snap["listing"], snap["spec"], snap["assembly"]
    kw = L.get("keywords") or []
    return "\n".join([
        f"# Listing draft – {L.get('title')}", "",
        "_Draft for you to copy into KDP. Nothing here has been submitted to Amazon._", "",
        "| Field | Value |", "|---|---|",
        f"| Title | {L.get('title', '')} |",
        f"| Subtitle | {L.get('subtitle', '')} |",
        f"| Author | {L.get('author', '')} |",
        f"| Language | {L.get('language', '')} |",
        f"| Audience | {L.get('audience', '')} (ages {L.get('age_range', '')}) |",
        f"| Format | Paperback, {s['trim'].replace('x', ' × ')} in, black ink on {'white' if s['paper'] == 'bw_white' else 'cream'} paper, "
        f"{'with' if s.get('interior_bleed') else 'no'} interior bleed, {s.get('cover_finish', 'matte')} cover |",
        f"| Interior | {a['page_count']} pages: {a['illustration_count']} illustrations, {a['intro_count']} intro pages, {a['blank_count']} blank pages |",
        f"| Difficulty | {s.get('difficulty', '')} |",
        f"| List price ({pricing['marketplace']}) | {pricing['currency']} {pricing['list_price']} |",
        "", "## Description", "", L.get("description") or "_(empty – write an accurate description)_", "",
        "## Keyword ideas (up to 7 KDP keyword boxes)", "",
        *(f"{i + 1}. {k}" for i, k in enumerate(kw[:7])),
        *([] if kw else ["_(none yet)_"]),
        "", "These are suggestions to research, not rankings or search-volume data.", "",
        "## Category research notes", "", L.get("category_notes") or "", "",
        "## Competitor notes (entered by you)", "", L.get("competitor_notes") or "_(none)_", "",
        "## ISBN", "", f"Choice: **{L.get('isbn_choice', 'undecided')}**. {L.get('isbn_notes', '')}",
        f"KDP offers a free KDP ISBN for paperbacks, or you can use one you own. See {ISBN_URL}.", "",
        "## Low-content classification", "",
        "Coloring books with varied, original illustrations are generally not treated as low-content books under current "
        "KDP guidance (low-content books are things like blank journals and planners with repetitive interiors). "
        f"Low-content books are not eligible for a free ISBN. Confirm how your book is classified: {LOW_CONTENT_URL}", "",
        "## AI-content disclosure (proposed)", "",
        f"- Interior images: {disclosure['images']['interior']['proposed_answer']}",
        f"- Cover images: {disclosure['images']['cover']['proposed_answer']}",
        f"- Text: {disclosure['text']['declared']}",
        f"- Translations: {disclosure['translations']['declared']}",
        f"- Guideline: {DISCLOSURE_SOURCE}", "",
    ])


def checklist_md(snap: dict, preflight: dict, pricing: dict, mode: str) -> str:
    s, a, g = snap["spec"], snap["assembly"], snap["cover"]["geometry"]
    status = preflight["status_label"]
    return "\n".join([
        f"# Manual KDP publishing checklist – {s['title']}", "",
        f"Package type: **{'PRINT-RELEASE CANDIDATE' if mode == 'release' else 'DRAFT'}** · Preflight: **{status}**", "",
        "This app prepares files. You review them and upload them yourself at kdp.amazon.com. Passing preflight is not Amazon approval.", "",
        "## 1. Account", "- [ ] Sign in at kdp.amazon.com and complete tax and payment information.", "",
        "## 2. Create the paperback", "- [ ] Bookshelf → + Create → Paperback.", "",
        "## 3. Details (copy from listing.md)",
        "- [ ] Language, title, subtitle and author exactly match the cover.",
        "- [ ] Description, keywords and categories (your own research).",
        "- [ ] Audience: confirm the age range; do not mark as low-content unless it truly is.",
        "- [ ] Rights: confirm you hold the necessary rights to all artwork (see provenance.json).", "",
        "## 4. AI-content questions",
        "- [ ] Answer KDP's AI questions yourself using the PROPOSED summary in provenance.json/listing.md.",
        "- [ ] Remember: AI-created artwork is AI-generated even after manual editing.", "",
        "## 5. ISBN", "- [ ] Choose a free KDP ISBN or enter your own.", "",
        "## 6. Print options (must match these files)",
        f"- [ ] Ink and paper: black & white interior, {'white' if s['paper'] == 'bw_white' else 'cream'} paper.",
        f"- [ ] Trim size: {s['trim'].replace('x', ' × ')} in.",
        f"- [ ] Bleed: {'Bleed (PDF only)' if s.get('interior_bleed') else 'No bleed'}.",
        f"- [ ] Cover finish: {s.get('cover_finish', 'matte')}.", "",
        "## 7. Upload",
        f"- [ ] Manuscript: interior.pdf ({a['page_count']} pages).",
        f"- [ ] Cover: 'Upload a cover you already have' → cover.pdf ({g['full_width_in']} × {g['full_height_in']} in, spine {g['spine_width_in']} in).",
        "- [ ] If KDP's cover calculator shows different dimensions for your configuration, trust KDP and re-export.",
        "- [ ] Barcode: leave the white box on the back cover empty; KDP adds the barcode.", "",
        "## 8. Previewer",
        "- [ ] Open the KDP Print Previewer and check every page, blank backs, margins and the cover wrap.", "",
        "## 9. Proof",
        "- [ ] Order a printed proof copy (proof copies cost printing + shipping) and check line quality and spine.", "",
        "## 10. Pricing",
        f"- [ ] Reference estimate: list {pricing['currency']} {pricing['list_price']} → printing {pricing['printing_cost']}, "
        f"royalty ≈ {pricing['royalty_per_copy']} per copy on {pricing['marketplace']} (profile checked {pricing['checked_on']}).",
        "- [ ] Confirm in KDP's own pricing panel. Expanded Distribution: decide only if your book qualifies.", "",
        "## 11. Submit",
        "- [ ] Click Publish when satisfied. KDP review can take several days and may request changes.", "",
    ])
