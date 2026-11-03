"""Draft listing text from what is already in the book, and check listing fields against KDP's limits.

The draft is built only from the book's own facts (title, ages, page count, characters, story parts, intro pages, size). It
makes no sales claims, rankings or search-volume statements, and keyword *ideas* are word combinations from the book, not
search data. Everything is a starting point for the owner to edit.

Limits (KDP help pages, checked 2026-11-01): title + subtitle together 200 characters or fewer; description at most 4000
characters, HTML tags included. Keyword boxes: 7, each commonly limited to 50 characters (KDP's form enforces it)."""
from __future__ import annotations

import re

TITLE_SUBTITLE_MAX = 200
DESCRIPTION_MAX = 4000
KEYWORD_BOXES = 7
KEYWORD_MAX = 50
BACK_COPY_TARGET = 450  # what fits comfortably above the barcode box at the default size
GENERIC_KEYWORD_WORDS = {"book", "books", "kindle", "ebook", "notebook", "journal", "gift", "gifts"}


def _ages(spec: dict) -> tuple[int | None, int | None]:
    return spec.get("age_min"), spec.get("age_max")


def _species(c: dict) -> str:
    """'Red Panda. Brass fire-helmet…' -> 'red panda' (only when the first sentence is a short noun phrase)."""
    first = re.split(r"[.;(]", (c.get("appearance") or "").strip(), maxsplit=1)[0].strip()
    return first.lower() if first and len(first.split()) <= 3 else ""


def _strip_act(a: str) -> str:
    return re.sub(r"^\s*(act|chapter|part)\s+[\w]+\s*[:.\-–—]\s*", "", a, flags=re.I).strip()


def _story_name(spec: dict) -> str:
    sub = (spec.get("subtitle") or "").strip()
    return sub.split(":")[0].strip() if sub else ""


def _acts_from_theme(theme: str) -> list[str]:
    m = re.search(r"The story is told in parts:\s*(.+?)\.?$", theme or "", re.S)
    return [a.strip() for a in m.group(1).split(";")] if m else []


def _join(items: list[str]) -> str:
    items = [i for i in items if i]
    if len(items) <= 2:
        return " and ".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def draft_listing(studio, pid: str) -> dict:
    sp, sg, asm = studio.spec(pid), studio.style_guide(pid), studio.assembly(pid)
    title = (sp.get("title") or "").strip()
    lo, hi = _ages(sp)
    kids = bool(lo and hi and hi <= 10)
    adult = (sp.get("audience") or "").lower().startswith("adult")
    n = asm["illustration_count"]
    chars = [c for c in sg.get("characters", []) if c.get("name")]
    acts = [_strip_act(a) for a in _acts_from_theme(sp.get("theme") or "")]
    intro = [r["label"] for r in studio.intro_descriptions(pid)]
    story = _story_name(sp)
    who = f"kids ages {lo}–{hi}" if kids else ("adults" if adult else (sp.get("audience") or "colorists").lower())
    trim = sp.get("trim", "8.5x11").replace("x", " × ") + " in"

    # ---- description
    names = _join([c["name"] for c in chars[:6]])
    team = (sg.get("team") or {}).get("name")
    if chars and story:
        hook = f"Join {names}{' of ' + team if team else ''} in {story} – {n} original coloring pages for {who}."
    elif chars:
        hook = f"Join {names}{' of ' + team if team else ''} in {n} original coloring pages for {who}."
    else:
        hook = f"{title}: {n} original coloring pages for {who}."
    paras = [hook]
    if acts:
        paras.append(f"The pictures follow one story from page to page, in {len(acts)} parts: {_join(acts)}.")
    if chars:
        lines = []
        for c in chars[:8]:
            bits = [b for b in (_species(c), (c.get("role") or "").lower()) if b]
            lines.append(f"• {c['name']}" + (f" – {', '.join(bits)}" if bits else ""))
        paras.append("Meet the characters:\n" + "\n".join(lines))
    if sp.get("facing_text"):
        inside = [f"• {n} illustrations, each on a right-hand page, with a story page facing every picture that describes what's happening"]
    else:
        inside = [f"• {n} illustrations, each on its own page" + (" with a blank back, so markers are less likely to bleed onto the next picture"
                                                                 if sp.get("blank_backs", True) else "")]
    if kids and sg.get("cleanup_mode", "bold") == "bold":
        inside.append("• Bold outlines and big, closed shapes that are easy to color with crayons, markers or colored pencils")
    if intro:
        inside.append(f"• Extra pages at the front: {_join([i.lower() if i[:1].isupper() and i[1:].islower() else i for i in intro])}")
    inside.append(f"• Large {trim} pages")
    paras.append("Inside this book:\n" + "\n".join(inside))
    paras.append("A screen-free activity for quiet time, car rides and rainy days." if kids else "A relaxing, screen-free coloring project.")
    description = "\n\n".join(paras)[:DESCRIPTION_MAX]

    # ---- back cover blurb (short; the cover designer prints it above the barcode box)
    if chars:
        back = f"Join {names}{' of ' + team if team else ''}" + (f" in {story}!" if story else " on a big adventure!")
    else:
        back = f"{n} original pictures to color!"
    back += (f" {n} pictures to color, each with a story to read on the facing page." if sp.get("facing_text") else
             f" {n} pictures to color" + (", each printed on its own page" if sp.get("blank_backs", True) else "") + ".")
    if kids:
        back += f" Big, bold shapes made for crayons. For ages {lo}–{hi}."
    back_copy = back.strip()

    # ---- keyword ideas (combinations of the book's own words; not search data)
    ideas: list[str] = []
    age_tag = f"ages {lo}-{hi}" if kids else ""
    base = "coloring book for kids" if kids else "coloring book for adults" if adult else "coloring book"
    ideas.append(f"{base} {age_tag}".strip())
    for c in [c for c in chars if _species(c)][:3]:
        s = _species(c)
        if s:
            ideas.append(f"{s} coloring pages for kids" if kids else f"{s} coloring pages")
    preset = sg.get("preset") or ""
    theme_words = {"vehicles_machines": "trucks and rescue vehicles coloring book", "storybook_adventure": "adventure story coloring book",
                   "cute_animal_friends": "cute animal coloring book", "fairytale_magic": "fairy tale coloring book",
                   "hidden_object_fun": "find and color activity book", "big_bold_first": "my first coloring book toddler",
                   "sticker_bubble": "simple cute coloring pages", "crayon_doodle": "silly doodle coloring book",
                   "chibi_cute": "kawaii coloring book", "adult_pen_ink": "intricate pen and ink coloring book"}
    if preset in theme_words:
        ideas.append(theme_words[preset])
    if team or len(chars) > 2:
        ideas.append("rescue team adventure coloring book" if re.search(r"rescue", (sp.get("theme") or "") + (sp.get("subtitle") or ""), re.I)
                     else "team of friends coloring book")
    if kids:
        ideas += ["preschool activity book", "screen free activities for kids"]
    out, seen = [], set()
    from .ip_guard import find
    for k in ideas:
        k = re.sub(r"\s+", " ", k).strip().lower()[:KEYWORD_MAX]
        if k and k not in seen and not find(k):
            seen.add(k)
            out.append(k)
    keywords = out[:KEYWORD_BOXES]
    notes = ["Built from your book's own details – edit freely. Nothing here is search-volume or sales data.",
             "Keyword ideas are word combinations, not research: check them with your own searches on Amazon before using them."]
    return {"description": description, "back_copy": back_copy, "keywords": keywords, "notes": notes,
            "checks": listing_checks({"title": title, "subtitle": sp.get("subtitle", ""), "description": description, "keywords": keywords})}


def listing_checks(listing: dict) -> list[dict]:
    """KDP field limits and common keyword mistakes. severity: error (KDP will refuse) | warning (worth fixing) | tip."""
    out = []
    t, s = (listing.get("title") or "").strip(), (listing.get("subtitle") or "").strip()
    ts = len(t) + len(s)
    if ts > TITLE_SUBTITLE_MAX:
        out.append({"severity": "error", "code": "title_too_long", "field": "title",
                    "message": f"Title + subtitle are {ts} characters; KDP allows 200 or fewer together."})
    desc = listing.get("description") or ""
    if len(desc) > DESCRIPTION_MAX:
        out.append({"severity": "error", "code": "description_too_long", "field": "description",
                    "message": f"Description is {len(desc)} characters; KDP allows 4000 (HTML tags count too)."})
    elif desc.strip() and len(desc.strip()) < 200:
        out.append({"severity": "tip", "code": "description_short", "field": "description",
                    "message": "The description is very short. Say who the book is for, what's inside and what makes it fun."})
    kws = [k.strip() for k in (listing.get("keywords") or []) if k and k.strip()]
    if len(kws) > KEYWORD_BOXES:
        out.append({"severity": "warning", "code": "too_many_keywords", "field": "keywords",
                    "message": f"{len(kws)} keyword lines; KDP has {KEYWORD_BOXES} boxes, so pick your best {KEYWORD_BOXES}."})
    title_words = set(re.findall(r"[a-z]+", (t + " " + s).lower())) - {"a", "an", "and", "the", "for", "of", "to", "in", "with"}
    for k in kws:
        if len(k) > KEYWORD_MAX:
            out.append({"severity": "error", "code": "keyword_too_long", "field": "keywords",
                        "message": f"“{k[:40]}…” is {len(k)} characters; each keyword box holds {KEYWORD_MAX}."})
        words = set(re.findall(r"[a-z]+", k.lower()))
        if words and words <= title_words:
            out.append({"severity": "tip", "code": "keyword_repeats_title", "field": "keywords",
                        "message": f"“{k}” only repeats words already in your title or subtitle, which Amazon indexes anyway."})
        if words & GENERIC_KEYWORD_WORDS and len(words) <= 2:
            out.append({"severity": "tip", "code": "keyword_generic", "field": "keywords",
                        "message": f"“{k}” is mostly a generic word (book, gift, notebook…); longer phrases usually work better."})
        if re.search(r"[\"“”]", k):
            out.append({"severity": "tip", "code": "keyword_quotes", "field": "keywords",
                        "message": f"“{k}” contains quotation marks; leave them out."})
    return out
