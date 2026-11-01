"""Book brief: one Markdown file that describes a whole coloring book.

parse_brief(text)        -> {"data": {...}, "warnings": [...], "summary": {...}}
apply_brief(studio, pid, data) -> summary of what changed
export_brief(studio, pid) -> Markdown text (round-trips through parse_brief)

The format is forgiving: headings are matched case-insensitively with common aliases, settings are
"Key: value" lines (with or without a leading "-"), and unknown sections are reported, not fatal."""
from __future__ import annotations

import re

MAX_BRIEF_BYTES = 2 * 1024 * 1024

SECTION_ALIASES = {
    "settings": ["settings", "book settings", "setup", "book setup", "details", "book details"],
    "book_description": ["book description", "description of the book", "about the book", "theme", "book theme", "overview", "story"],
    "master_style": ["master style", "style", "art style", "master style suffix"],
    "avoid": ["avoid", "things to avoid", "do not include", "don't include"],
    "characters": ["characters", "heroes", "cast", "main characters"],
    "team": ["team", "hero team"],
    "front_cover": ["front cover", "front cover art", "cover", "cover art"],
    "back_cover": ["back cover", "back cover art", "back cover illustration"],
    "back_cover_text": ["back cover text", "back cover blurb", "blurb", "back cover copy"],
    "intro": ["intro pages", "introductory pages", "intro", "front matter", "introduction pages"],
    "pages": ["pages", "illustrations", "page descriptions", "illustration pages", "coloring pages"],
    "listing": ["listing", "amazon listing", "kdp listing", "kdp"],
}
SETTING_KEYS = {
    "title": ["title", "book title", "working title"], "subtitle": ["subtitle"], "author": ["author", "pen name", "author name"],
    "audience": ["audience", "for", "target audience", "reader", "readers"], "ages": ["ages", "age range", "age"], "trim": ["trim", "trim size", "size", "page size"],
    "paper": ["paper", "paper color", "paper colour"], "bleed": ["bleed", "interior bleed"], "blank_backs": ["blank backs", "blank back", "single sided", "single-sided"],
    "language": ["language"], "style_preset": ["style preset", "preset"], "cleanup": ["cleanup", "line art cleanup", "line-art cleanup", "detail", "drawing difficulty", "difficulty", "detail level", "line weight"],
    "intro_pages": ["intro pages", "intro page count", "number of intro pages", "introductory pages"], "format": ["format", "book format"],
    "illustrations": ["illustrations", "illustration count", "number of illustrations", "pages"],
    "cover_finish": ["cover finish", "finish"], "list_price": ["list price", "price"],
}
CHAR_KEYS = {"role": ["role"], "powers": ["powers", "power", "abilities"], "costume": ["costume", "outfit", "clothes"],
             "emblem": ["emblem", "symbol", "logo"], "appearance": ["appearance", "looks", "look", "description"],
             "proportions": ["proportions", "body"]}
TEAM_KEYS = {"name": ["name", "team name"], "motto": ["motto"], "headquarters": ["headquarters", "hq", "base"], "emblem": ["emblem", "symbol"]}
LISTING_KEYS = {"keywords": ["keywords", "keyword ideas"], "category_notes": ["categories", "category notes", "category"],
                "isbn": ["isbn", "isbn choice"], "description": ["description"], "list_price": ["list price", "price"],
                "text_ai": ["text ai", "text ai involvement"]}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower()).strip()


def _match(name: str, table: dict) -> str | None:
    n = _norm(name)
    n = re.sub(r"\s+", " ", n)
    for key, aliases in table.items():
        if n in [_norm(a) for a in aliases]:
            return key
    return None


KV = re.compile(r"^\s*(?:[-*+]\s+)?(?:\*\*|__)?([A-Za-z][A-Za-z /&'()-]{0,40}?)\s*(?:\*\*|__)?\s*:\s*(?:\*\*|__)?\s*(.*)$")


def _kv_lines(lines: list[str], table: dict) -> tuple[dict, list[str]]:
    """Pull 'Key: value' lines that match `table`; return (values, remaining free-text lines)."""
    vals, rest = {}, []
    for ln in lines:
        m = KV.match(ln)
        key = _match(m.group(1), table) if m else None
        if key and key not in vals:
            vals[key] = m.group(2).strip()
        else:
            rest.append(ln)
    return vals, rest


def _text(lines: list[str]) -> str:
    t = "\n".join(lines).strip()
    return re.sub(r"\n{3,}", "\n\n", t)


def _split_h3(lines: list[str]) -> tuple[list[str], list[tuple[str, list[str]]]]:
    pre, items, cur = [], [], None
    for ln in lines:
        m = re.match(r"^###\s+(.*?)\s*#*\s*$", ln)
        if m:
            cur = (m.group(1).strip(), [])
            items.append(cur)
        elif cur is None:
            pre.append(ln)
        else:
            cur[1].append(ln)
    return pre, items


def _bullets(lines: list[str]) -> list[str]:
    out = []
    for ln in lines:
        s = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", ln).strip()
        if s:
            out.extend([x.strip() for x in s.split(",")] if "," in s and not ln.strip().startswith(("-", "*", "+")) else [s])
    return [x for x in out if x]


def _yes(v: str) -> bool | None:
    v = _norm(v)
    if v in ("yes", "y", "true", "on", "1"):
        return True
    if v in ("no", "n", "false", "off", "0", "none"):
        return False
    return None


# A line that starts a page or intro item: "Page 3: …", "- Page 40 (Cliffhanger): …", "**Intro 1 (Badge):** …", "Illustration 2) …"
ITEM_RE = re.compile(
    r"^\s*(?:[-*+]\s+|\d+[.)]\s+)?(?:\*\*|__)?\s*(page|pg\.?|illustration|scene|intro(?:ductory)?(?:\s+page)?)\s*#?\s*(\d+)\s*"
    r"(?:\(([^)]{0,80})\))?\s*(?:\*\*|__)?\s*(?:[:.)\-–—]|\*\*|__)+\s*(.*)$", re.I)
NUM_RE = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")
BULLET_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
CHAR_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\*\*|__)?([^:()*_\n]{1,50}?)(?:\*\*|__)?\s*(?:\(([^)]{1,80})\))?\s*(?:\*\*|__)?"
                     r"\s*(?::|\s[-–—]\s)\s*(?:\*\*|__)?\s*(.+)$")
ITEM_SECTIONS = ("characters", "intro", "pages", "listing")
ROMAN = r"(?:[ivxlc]+|\d+|one|two|three|four|five|six|seven|eight|nine|ten)"


def _strip_md(s: str) -> str:
    return re.sub(r"^(?:\*\*|__)|(?:\*\*|__)$", "", (s or "").strip()).strip()


def _classify(name: str) -> str | None:
    """Guess which part of the brief a heading starts, from the words in it (forgiving on purpose)."""
    raw = _strip_md(name)
    if ITEM_RE.match(raw):
        return None
    n = re.sub(r"\s+", " ", _norm(re.sub(r"\([^)]*\)", " ", raw)))
    if not n:
        return None
    exact = _match(n, SECTION_ALIASES)
    if exact:
        return exact
    if re.match(rf"^(act|chapter|part)\s+{ROMAN}\b", n):
        return "act"
    if "back cover" in n:
        return "back_cover_text" if re.search(r"\b(text|blurb|copy|words|wording)\b", n) else "back_cover"
    if "front cover" in n or re.fullmatch(r"(book )?cover( art| design| illustration| prompt| image)?", n):
        return "front_cover"
    if "blurb" in n:
        return "back_cover_text"
    if re.search(r"\bintro|introductory|front matter", n):
        return "intro"
    if re.search(r"\b(listing|keywords?|amazon|kdp|marketing)\b", n):
        return "listing"
    if re.search(r"\b(avoid|do not|don t|negative|never draw)\b", n):
        return "avoid"
    if re.search(r"\b(characters?|cast|reference sheet|heroes|vehicles?|crew)\b", n):
        return "characters"
    if re.search(r"^(hero )?team\b|\bteam$", n):
        return "team"
    if re.search(r"\b(style|visual|art direction|look and feel)\b", n):
        return "master_style"
    if re.search(r"\b(pages?|illustrations?|prompts|scenes|storyboard)\b", n):
        return "pages"
    if re.search(r"\b(settings?|metadata|details|setup|info|specs?|specifications?|format)\b", n):
        return "settings"
    if re.search(r"\b(description|story|overview|about|synopsis|theme|plot|summary|premise)\b", n):
        return "book_description"
    return None


def _heading(ln: str, cur: str | None):
    """-> ("section", key|None, name) | ("title", name) | None (an ordinary line)."""
    m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", ln)
    if m:
        level, name = len(m.group(1)), _strip_md(m.group(2))
        if level >= 3 and cur in ITEM_SECTIONS:
            k = _match(name, SECTION_ALIASES)
            return ("section", k, name) if k and k != cur and not ITEM_RE.match(name) else None
        if ITEM_RE.match(name) and cur in ("pages", "intro", None):
            return None  # "## Page 3: …" is a page, not a section
        k = _classify(name)
        if level == 1 and k is None:
            return ("title", name)
        if k:
            return ("section", k, name)
        return ("section", None, name) if level <= 2 else None
    m = re.match(r"^\s*\[(.+?)\]\s*$", ln)  # [Introductory Pages], [Act I: The Alarm]
    if m:
        k = _classify(m.group(1))
        if k:
            return ("section", k, m.group(1).strip())
        return ("section", "act", m.group(1).strip()) if cur in ("pages", "intro") else None
    m = re.match(r"^\s*(?:\*\*|__)([^*_]{2,90}?)(?::)?(?:\*\*|__)\s*:?\s*$", ln) or \
        re.match(r"^\s*([A-Za-z][^:\n*#\[\]]{1,90}?)\s*:\s*$", ln)  # **Front cover**  /  Book Metadata:
    if m and not BULLET_RE.match(ln):
        k = _classify(m.group(1))
        if k:
            return ("section", k, m.group(1).strip())
    return None


SMALL_WORDS = {"a", "an", "and", "at", "by", "for", "in", "of", "on", "or", "the", "to", "with"}


def _title_label(line: str) -> tuple[str, str] | None:
    """'Tug-of-War Day: All five heroes…' -> ('Tug-of-War Day', 'All five heroes…'). Only Title-Case labels count, so a
    sentence such as 'A sign reads: welcome' is left alone."""
    m = re.match(r"^\s*(?:\*\*|__)([^*_]{2,60}?)(?::)?(?:\*\*|__)\s*:?\s+(.{3,})$", line)  # **Label:** text
    if m:
        return _strip_md(m.group(1)), m.group(2)
    m = re.match(r"^\s*([^:]{2,50}?)\s*:\s+(.{3,})$", line)
    if not m or _match(m.group(1), {"x": ["placement", "position", "text", "page text"]}):
        return None
    words = m.group(1).split()
    if len(words) <= 6 and all(w[0].isupper() or w[0].isdigit() or w.lower() in SMALL_WORDS for w in words) and words[0][0].isupper():
        return m.group(1).strip(), m.group(2)
    return None


def _line_items(lines: list[str], default_kind: str) -> list[dict]:
    """Split lines into items: 'Page N: …' lines, numbered lines, bullets, or blank-line paragraphs.
    A line directly under an item (not a new bullet) continues that item."""
    items: list[dict] = []
    cur = None
    for ln in lines:
        if not ln.strip():
            cur = None
            continue
        m = ITEM_RE.match(ln)
        if m:
            kind = "intro" if m.group(1).lower().startswith("intro") else "page"
            cur = {"kind": kind, "number": int(m.group(2)), "label": (m.group(3) or "").strip(), "lines": [m.group(4)], "explicit": True}
            items.append(cur)
            continue
        n, b = NUM_RE.match(ln), BULLET_RE.match(ln)
        if cur is not None and not (n or b):
            cur["lines"].append(ln)
            continue
        if cur is not None and b and KV.match(ln) and _match(KV.match(ln).group(1), {"x": ["placement", "position", "text", "page text"]}):
            cur["lines"].append(b.group(1))  # "- Placement: …" belongs to the item above
            continue
        cur = {"kind": default_kind, "number": int(n.group(1)) if n else None, "label": "",
               "lines": [n.group(2) if n else b.group(1) if b else ln], "explicit": False}
        items.append(cur)
    for it in items:
        if not it["label"] and it["lines"] and it["lines"][0].strip():
            tl = _title_label(it["lines"][0])
            if tl:
                it["label"], it["lines"][0] = tl
    return items


def _intro_from(label: str, lines: list[str], number: int | None) -> dict:
    vals, rest = _kv_lines(lines, {"placement": ["placement", "position"], "text": ["text", "page text"]})
    pl = _norm(vals.get("placement", ""))
    placement = ("full_page" if re.search(r"full page picture|full picture|whole page|full page art|full page illustration", pl)
                 else "behind_text" if ("behind" in pl or "frame" in pl or "full" in pl) else "free_space" if pl else None)
    return {"label": label, "description": _text(rest), "placement": placement, "text": vals.get("text"), "number": number}


def _character_lines(lines: list[str]) -> list[dict]:
    chars, cur = [], None
    for ln in lines:
        m = CHAR_RE.match(ln)
        if m and not _match(m.group(1), CHAR_KEYS) and len(m.group(1).split()) <= 6:
            name, species, rest = _strip_md(m.group(1)), (m.group(2) or "").strip(), m.group(3).strip()
            role = ""
            first = re.match(r"^([^.]{1,40})\.\s+(.*)$", rest)
            if first and len(first.group(1).split()) <= 5:
                role, rest = first.group(1).strip(), first.group(2).strip()
            cur = {"name": name, "role": role, "appearance": ((species + ". ") if species else "") + rest}
            chars.append(cur)
        elif cur is not None and ln.strip():
            kv = KV.match(ln)
            k = _match(kv.group(1), CHAR_KEYS) if kv else None
            if k:
                cur[k] = kv.group(2).strip()
            else:
                cur["appearance"] = (cur["appearance"] + " " + ln.strip()).strip()
        elif not ln.strip():
            cur = None
    return chars


def _parse_markdown(text: str, warnings: list[str]) -> dict:
    data: dict = {}
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)  # template instructions
    sections: list[list] = []
    cur: list | None = None
    preamble: list[str] = []
    for ln in text.split("\n"):
        h = _heading(ln, cur[0] if cur else None)
        if h and h[0] == "title":
            t = re.sub(r"^(book|title)\s*:\s*", "", h[1], flags=re.I)
            if t and "title" not in data:
                data["title"] = t
            continue
        if h:
            key, name = h[1], h[2]
            if key == "act":  # an act/chapter heading groups the pages that follow
                cur = ["pages", name, [], name]
            else:
                cur = [key, name, [], None]
            sections.append(cur)
            continue
        (cur[2] if cur else preamble).append(ln)
    acts: list[str] = []
    for key, name, body, act in sections:
        if act and act not in acts:
            acts.append(act)
        if key is None:
            if _text(body):
                warnings.append(f"Unknown section “{name}” was ignored.")
            continue
        if key == "settings":
            vals, rest = _kv_lines(body, SETTING_KEYS)
            data.setdefault("settings", {}).update({k: v for k, v in vals.items() if k not in data.get("settings", {})})
            for ln in rest:
                if KV.match(ln) and KV.match(ln).group(2).strip():
                    warnings.append(f"Unknown setting ignored: “{ln.strip().lstrip('-*+ ')}”.")
        elif key in ("book_description", "master_style", "front_cover", "back_cover", "back_cover_text"):
            t = _text(body)
            if t:
                data[key] = (data[key] + "\n\n" + t) if data.get(key) else t
        elif key == "avoid":
            data.setdefault("avoid", []).extend(_bullets(body))
        elif key == "team":
            vals, _ = _kv_lines(body, TEAM_KEYS)
            data.setdefault("team", {}).update(vals)
        elif key == "characters":
            pre, items = _split_h3(body)
            chars = _character_lines(pre)
            for title, blines in items:
                vals, rest = _kv_lines(blines, CHAR_KEYS)
                c = {"name": _strip_md(title), **vals}
                extra = _text(rest)
                if extra:
                    c["appearance"] = (c.get("appearance", "") + (" " if c.get("appearance") else "") + extra).strip()
                chars.append(c)
            if not chars and _text(body):
                warnings.append(f"“{name}”: no characters could be read. List them as “1. Name (animal): description” or “### Name”.")
            data.setdefault("characters", []).extend(chars)
        elif key in ("intro", "pages"):
            pre, items = _split_h3(body)
            found = []
            if items:
                for title, blines in items:
                    m = ITEM_RE.match(title) or ITEM_RE.match(title + ":")
                    if m:
                        kind = "intro" if m.group(1).lower().startswith("intro") else "page"
                        label = (m.group(3) or m.group(4) or "").strip()
                        found.append({"kind": kind, "number": int(m.group(2)), "label": label, "lines": blines, "heading": True})
                    else:
                        found.append({"kind": "intro" if key == "intro" else "page", "number": None, "label": title, "lines": blines,
                                      "heading": True})
                if _text(pre):  # only clear "Page N:" / "Intro N:" lines above the first ### heading count
                    found = [x for x in _line_items(pre, "intro" if key == "intro" else "page") if x["explicit"]] + found
            else:
                found = _line_items(body, "intro" if key == "intro" else "page")
            for it in found:
                if it["kind"] == "intro":
                    data.setdefault("intro", []).append(_intro_from(it["label"] or (f"Intro {it['number']}" if it["number"] else "Intro page"),
                                                                    it["lines"], it["number"]))
                else:
                    desc = _text(it["lines"])
                    if desc or it["label"] or it.get("heading"):
                        data.setdefault("pages", []).append({"label": it["label"], "description": desc, "number": it["number"], "act": act})
        elif key == "listing":
            pre, items = _split_h3(body)
            vals, rest = _kv_lines(pre, LISTING_KEYS)
            lst = data.setdefault("listing", {})
            lst.update(vals)
            for title, blines in items:
                k = _match(title, LISTING_KEYS)
                if k == "keywords":
                    lst["keywords"] = _bullets(blines)
                elif k:
                    lst[k] = _text(blines)
    if _text(preamble) and "book_description" not in data:
        data["book_description"] = _text(preamble)
    if acts:
        data["acts"] = acts
    return data


# ------------------------------------------------------------------------------------------------ JSON briefs

JSON_TOP = {**SECTION_ALIASES, "title": ["title", "book title", "working title"], "acts": ["acts", "chapters"]}


def _as_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return "\n\n".join(_as_text(x) for x in v if x is not None)
    if isinstance(v, dict):
        return "\n".join(f"{k}: {_as_text(x)}" for k, x in v.items())
    return str(v).strip()


def _parse_json(obj, warnings: list[str]) -> dict:
    if not isinstance(obj, dict):
        raise ValueError("A JSON brief must be one object { … } at the top level.")
    data: dict = {}
    settings: dict = {}
    for raw_key, v in obj.items():
        key = _match(raw_key.replace("_", " "), JSON_TOP)
        skey = _match(raw_key.replace("_", " "), SETTING_KEYS) if key is None else None
        if key is None and skey:
            settings[skey] = _as_text(v)
            continue
        if key is None:
            warnings.append(f"Unknown field “{raw_key}” was ignored.")
            continue
        if key == "title":
            data["title"] = _as_text(v)
        elif key == "settings":
            if not isinstance(v, dict):
                warnings.append("“settings” should be an object; ignored.")
                continue
            for k2, v2 in v.items():
                sk = _match(k2.replace("_", " "), SETTING_KEYS)
                if sk:
                    settings[sk] = _as_text(v2)
                else:
                    warnings.append(f"Unknown setting ignored: “{k2}”.")
        elif key in ("book_description", "master_style", "front_cover", "back_cover", "back_cover_text"):
            data[key] = _as_text(v)
        elif key == "avoid":
            data["avoid"] = [x.strip() for x in (v if isinstance(v, list) else re.split(r"[,\n]", str(v))) if str(x).strip()]
        elif key == "team":
            data["team"] = {tk: _as_text(v.get(raw)) for raw in (v if isinstance(v, dict) else {})
                            for tk in [_match(raw, TEAM_KEYS)] if tk}
        elif key == "characters":
            items = v.items() if isinstance(v, dict) else enumerate(v if isinstance(v, list) else [])
            chars = []
            for nm, c in items:
                if isinstance(c, str):
                    chars.append({"name": str(nm), "appearance": c})
                elif isinstance(c, dict):
                    ch = {"name": _as_text(c.get("name") or nm)}
                    for k2, v2 in c.items():
                        ck = _match(k2, CHAR_KEYS)
                        if ck:
                            ch[ck] = _as_text(v2)
                        elif k2.lower() in ("species", "animal", "vehicle", "vehicles", "gear", "notes"):
                            ch["appearance"] = (ch.get("appearance", "") + " " + f"{k2.title()}: {_as_text(v2)}.").strip()
                    chars.append(ch)
            data["characters"] = chars
        elif key in ("intro", "pages"):
            out = []
            for i, it in enumerate(v if isinstance(v, list) else []):
                if isinstance(it, str):
                    it = {"description": it}
                if not isinstance(it, dict):
                    continue
                num = it.get("number") or it.get("page") or it.get("intro")
                num = int(num) if str(num or "").strip().isdigit() else None
                label = _as_text(it.get("label") or it.get("title") or it.get("name"))
                desc = _as_text(it.get("description") or it.get("prompt") or it.get("scene") or it.get("illustration"))
                if key == "intro":
                    item = _intro_from(label or f"Intro {num or i + 1}", [f"Placement: {it['placement']}"] if it.get("placement") else [], num)
                    item["description"], item["text"] = desc, _as_text(it.get("text")) or None
                    out.append(item)
                else:
                    out.append({"label": label, "description": desc, "number": num, "act": _as_text(it.get("act")) or None})
            data[key] = out
        elif key == "listing":
            lst = {}
            for k2, v2 in (v.items() if isinstance(v, dict) else []):
                lk = _match(k2.replace("_", " "), LISTING_KEYS)
                if lk == "keywords":
                    lst["keywords"] = [str(x).strip() for x in v2] if isinstance(v2, list) else _as_text(v2)
                elif lk:
                    lst[lk] = _as_text(v2)
            data["listing"] = lst
        elif key == "acts":
            data["acts"] = [_as_text(a) for a in (v if isinstance(v, list) else [v])]
    if settings:
        data["settings"] = settings
    return data


# ------------------------------------------------------------------------------------------------ shared clean-up

STYLE_REF_PAREN = re.compile(r"\s*\([^()]*\b(?:inspired by|in the style of|style of|similar to|reminiscent of|like|think|a la|à la)\b[^()]*\)", re.I)
STYLE_REF_CLAUSE = re.compile(r",?\s*\b(?:inspired by|in the style of|similar to|reminiscent of|in the vein of|styled after)\s+[^.;:\n()]*", re.I)


def _strip_brand_refs(text: str) -> tuple[str, list[str]]:
    """Remove 'inspired by <protected show>' style references. The style words around them stay."""
    from .ip_guard import find
    removed = []

    def sub(m):
        if find(m.group(0)):
            removed.append(m.group(0).strip(" ,"))
            return ""
        return m.group(0)
    out = STYLE_REF_PAREN.sub(sub, text)
    out = STYLE_REF_CLAUSE.sub(sub, out)
    if removed:
        out = re.sub(r"[ \t]{2,}", " ", out)
        out = re.sub(r"\s+([.,;:])", r"\1", out)
    return out, removed


FIELD_NAMES = {"master_style": "the master style", "book_description": "the book description", "front_cover": "the front cover",
               "back_cover": "the back cover", "back_cover_text": "the back-cover text"}


def _clean_brand_refs(data: dict, warnings: list[str]) -> None:
    def fix(holder, key, where):
        if isinstance(holder.get(key), str):
            holder[key], gone = _strip_brand_refs(holder[key])
            for g in gone:
                warnings.append(f"Removed “{g}” from {where}: image prompts can't name other companies' shows or characters "
                                f"(and KDP can block books that trade on them). The rest of your wording is kept.")
    for k, where in FIELD_NAMES.items():
        fix(data, k, where)
    for p in data.get("pages", []):
        fix(p, "description", f"page {p.get('number') or p.get('label') or ''}".strip())
    for it in data.get("intro", []):
        fix(it, "description", f"intro page “{it['label']}”")
    for c in data.get("characters", []):
        for k in ("appearance", "costume", "role", "powers"):
            fix(c, k, f"character “{c.get('name', '')}”")


def _all_strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from _all_strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from _all_strings(v)


def parse_brief(text: str) -> dict:
    """Read a Markdown (any reasonable layout) or JSON brief."""
    if len(text.encode("utf-8")) > MAX_BRIEF_BYTES:
        raise ValueError("The brief is larger than 2 MB.")
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")
    warnings: list[str] = []
    stripped = text.strip()
    fmt = "markdown"
    if stripped.startswith("```json"):
        stripped = re.sub(r"^```json\s*|\s*```\s*$", "", stripped)
    if stripped.startswith("{"):
        import json
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError as e:
            raise ValueError(f"This looks like JSON but it can't be read: {e.msg} at line {e.lineno}, column {e.colno}. "
                             "A missing comma or quote is the usual cause.") from None
        data = _parse_json(obj, warnings)
        fmt = "json"
    else:
        data = _parse_markdown(text, warnings)
    s = data.setdefault("settings", {})
    if not s:
        data.pop("settings")
        s = {}
    if s.get("title"):
        data["title"] = s["title"]
    if data.get("title"):
        data["title"] = re.sub(r"^\s*(system prompt|prompt|brief|book brief)\s*:\s*", "", data["title"], flags=re.I).strip()
    _format_setting(s)
    # pages: put numbered pages in order, report gaps and repeats
    pages = data.get("pages", [])
    last = 0
    for p in pages:
        if p.get("number") is None:
            p["number"] = last + 1
        last = p["number"]
    nums = [p["number"] for p in pages]
    if nums and nums != sorted(nums):
        pages.sort(key=lambda p: p["number"])
        warnings.append("Pages were listed out of order; they were put in page-number order.")
    dup = sorted({n for n in nums if nums.count(n) > 1})
    if dup:
        warnings.append("Page number(s) " + ", ".join(map(str, dup)) + " appear more than once; each copy became its own page.")
    gaps = sorted(set(range(1, max(nums) + 1)) - set(nums)) if nums else []
    if gaps:
        warnings.append("No description for page(s) " + ", ".join(map(str, gaps[:20])) + ("…" if len(gaps) > 20 else "")
                        + "; the pages that follow move up to fill the gap.")
    intro = data.get("intro", [])
    if intro and any(i.get("number") for i in intro):
        intro.sort(key=lambda i: i.get("number") or 999)
        data["intro_exact"] = True
    if s.get("intro_pages") and str(s["intro_pages"]).strip().isdigit():
        data["intro_exact"] = bool(intro)
        if intro and int(s["intro_pages"]) != len(intro):
            warnings.append(f"Settings say {s['intro_pages']} intro pages but {len(intro)} are described; the book gets the {len(intro)} described.")
    for it in intro:
        if it.get("placement") is None:
            it["placement"] = "full_page" if data.get("intro_exact") and not it.get("text") else "free_space"
    # validation / warnings
    for p in pages:
        if len(p["description"]) > 4000:
            warnings.append(f"Page {p['number']} description is over 4000 characters and will be shortened.")
            p["description"] = p["description"][:4000]
    if len(data.get("master_style", "")) > 3000:
        warnings.append("Master style is over 3000 characters and will be shortened.")
        data["master_style"] = data["master_style"][:3000]
    if len((data.get("book_description") or "").split()) > 10000:
        raise ValueError("The book description is over 10,000 words.")
    if not data.get("book_description") and (s.get("subtitle") or data.get("acts")):
        bits = [x for x in (data.get("title"), s.get("subtitle")) if x]
        desc = " — ".join(bits) + "." if bits else ""
        if data.get("acts"):
            desc += " The story is told in parts: " + "; ".join(data["acts"]) + "."
        data["book_description"] = desc.strip()
        warnings.append("No book description was found, so a short one was made from the title, subtitle and act headings. "
                        "Your page descriptions carry the detail.")
    _clean_brand_refs(data, warnings)
    kws = data.get("listing", {}).get("keywords") or []
    if isinstance(kws, str):
        kws = data["listing"]["keywords"] = [k.strip() for k in re.split(r"[,;]", kws) if k.strip()]
    if len(kws) > 7:
        warnings.append(f"{len(kws)} keywords given; KDP has 7 keyword boxes – all are kept in the listing draft for you to choose.")
    from .ip_guard import find
    seen = set()
    for t in _all_strings(data):
        for h in find(t):
            if h["matched"].lower() not in seen:
                seen.add(h["matched"].lower())
                warnings.append(f"“{h['matched']}” looks like a protected name ({h['owner']}). Pages or covers that use it won't be generated.")
    n_pages = len(pages)
    ill = s.get("illustrations")
    if ill and n_pages and str(ill).strip().isdigit() and int(ill) != n_pages:
        warnings.append(f"Settings say {ill} illustrations but {n_pages} pages are described; the book will have {max(int(ill), n_pages)} illustration pages.")
    summary = {
        "format": fmt,
        "title": data.get("title"), "author": s.get("author"), "audience": s.get("audience"),
        "illustration_pages": max(n_pages, int(ill) if ill and str(ill).isdigit() else 0) or None,
        "described_pages": n_pages, "intro_pages": len(intro), "characters": len(data.get("characters", [])),
        "has_book_description": bool(data.get("book_description")), "has_master_style": bool(data.get("master_style")),
        "has_front_cover": bool(data.get("front_cover")), "has_back_cover": bool(data.get("back_cover")),
        "has_back_cover_text": bool(data.get("back_cover_text")), "has_listing": bool(data.get("listing")),
        "book_description_words": len((data.get("book_description") or "").split()),
        "acts": data.get("acts", []), "intro_exact": bool(data.get("intro_exact")),
        "intro_labels": [i["label"] for i in intro], "character_names": [c.get("name", "") for c in data.get("characters", [])],
        "first_pages": [f"{p['number']}. " + (p["label"] + " – " if p["label"] else "") + p["description"][:110] for p in pages[:3]],
        "last_page": (f"{pages[-1]['number']}. " + (pages[-1]["label"] + " – " if pages[-1]["label"] else "") + pages[-1]["description"][:110])
                     if len(pages) > 3 else None,
    }
    if not (data.get("title") or n_pages or data.get("book_description")):
        warnings.append("Nothing recognisable was found. Start from the template (Download template).")
    return {"data": data, "warnings": warnings, "summary": summary}


def _format_setting(s: dict) -> None:
    """'Format: 4 Intro Pages, 40 Illustrations, 8.5 x 11 in' and 'Target audience: Children ages 3–7' fill the matching settings."""
    f = s.get("format", "")
    if f:
        m = re.search(r"(\d+)\s*(?:intro|introductory)", f, re.I)
        if m and not s.get("intro_pages"):
            s["intro_pages"] = m.group(1)
        m = re.search(r"(\d+)\s*(?:illustrations?|coloring pages|colouring pages|story pages|pictures)", f, re.I)
        if m and not s.get("illustrations"):
            s["illustrations"] = m.group(1)
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:in(?:ch(?:es)?)?|\")?\s*[x×]\s*(\d+(?:\.\d+)?)", f, re.I)
        if m and not s.get("trim"):
            s["trim"] = f"{m.group(1)}x{m.group(2)}"
    a = s.get("audience", "")
    if a and re.search(r"\d", a) and not s.get("ages"):
        s["ages"] = a
        s["audience"] = re.sub(r"\(.*?\)|\b(?:ages?|aged)\b.*$|\d.*$", "", a, flags=re.I).strip(" ,-–") or "Children"


# ------------------------------------------------------------------------------------------------ apply

TRIMS = {"8.5x11": "8.5x11", "85x11": "8.5x11", "8x10": "8x10", "8.5x8.5": "8.5x8.5", "85x85": "8.5x8.5"}


def spec_from_settings(data: dict) -> tuple[dict, list[str]]:
    s, spec, warn = data.get("settings", {}), {}, []
    for k in ("title", "subtitle", "author", "audience", "language"):
        if s.get(k):
            spec[k] = s[k]
    if data.get("title"):
        spec["title"] = data["title"]
    if s.get("ages"):
        nums = [int(x) for x in re.findall(r"\d+", s["ages"])]
        if len(nums) >= 2:
            spec["age_min"], spec["age_max"] = nums[0], nums[1]
        elif len(nums) == 1:
            spec["age_min"], spec["age_max"] = nums[0], nums[0]
        elif "adult" in s["ages"].lower():
            spec["age_min"], spec["age_max"] = None, None
            spec.setdefault("audience", "Adults")
    if s.get("trim"):
        t = TRIMS.get(re.sub(r"[^0-9.x]", "", s["trim"].lower().replace("×", "x").replace(" ", "")))
        if t:
            spec["trim"] = t
        else:
            warn.append(f"Trim “{s['trim']}” isn't a supported preset (8.5x11, 8x10, 8.5x8.5); kept the current trim.")
    if s.get("paper"):
        spec["paper"] = "bw_cream" if "cream" in s["paper"].lower() else "bw_white"
    for k, sk in (("bleed", "interior_bleed"), ("blank_backs", "blank_backs")):
        if s.get(k):
            y = _yes(s[k])
            if y is not None:
                spec[sk] = y
    if s.get("cover_finish"):
        spec["cover_finish"] = "glossy" if "gloss" in s["cover_finish"].lower() else "matte"
    if data.get("book_description"):
        spec["theme"] = data["book_description"]
    n = len(data.get("pages", []))
    ill = s.get("illustrations")
    count = max(n, int(ill) if ill and str(ill).strip().isdigit() else 0)
    if count:
        spec["illustration_count"] = count
    return spec, warn


def _match_preset(name: str) -> str | None:
    from .planning import load_presets
    presets = load_presets()["presets"]
    n = _norm(name)
    for k, p in presets.items():
        if n in (_norm(k), _norm(k.replace("_", " ")), _norm(p["label"])) or _norm(p["label"]).startswith(n):
            return k
    return None


def _match_intro(label: str, rows: list[dict]) -> dict | None:
    n = _norm(label)
    keys = [("title", "title"), ("belong", "belongs"), ("color test", "color test"), ("colour test", "color test"),
            ("test", "color test"), ("copyright", "copyright"), ("tips", "copyright")]
    for r in rows:
        if _norm(r["label"]) == n:
            return r
    for frag, target in keys:
        if frag in n:
            for r in rows:
                if target in _norm(r["label"]):
                    return r
    return None


def _short_label(desc: str) -> str:
    words = re.sub(r"\s+", " ", desc).strip().split(" ")
    if not words or not words[0]:
        return ""
    out = " ".join(words[:7]).rstrip(".,;:!")
    return out + ("…" if len(words) > 7 else "")


def _set_intro_text(studio, page_id: str, text: str) -> None:
    els = studio.page(page_id)["elements"]
    tx = [e for e in els if e["kind"] == "text"]
    if tx:
        tx[0]["text"] = text
        studio.save_elements(page_id, els, reason="brief: intro text")


def _new_intro_page(studio, pid: str, it: dict) -> dict:
    p = studio.add_page(pid, "intro")
    studio.update_page_meta(p["id"], {"label": it["label"][:120]})
    if it.get("text"):
        _set_intro_text(studio, p["id"], it["text"])
    else:  # a picture-only page: drop the empty placeholder text box
        studio.save_elements(p["id"], [e for e in studio.page(p["id"])["elements"] if e["kind"] != "text" or (e.get("text") or "").strip()],
                             reason="brief: picture page")
    return next(x for x in studio.intro_descriptions(pid) if x["page_id"] == p["id"])


def _apply_intro_exact(studio, pid: str, intro: list[dict], warnings: list[str]) -> list[str]:
    """The brief numbers its intro pages, so the book's intro pages become exactly those, in that order.
    Pages with the same label are reused (re-importing is safe); old intro pages with artwork are kept."""
    existing = studio.intro_descriptions(pid)
    used, order, added = set(), [], []
    for it in intro:
        r = next((x for x in existing if x["page_id"] not in used and _norm(x["label"]) == _norm(it["label"])), None)
        if r is None:
            r = _new_intro_page(studio, pid, it)
            added.append(it["label"])
        elif it.get("text"):
            _set_intro_text(studio, r["page_id"], it["text"])
        used.add(r["page_id"])
        order.append(r["page_id"])
        studio.set_intro_description(r["page_id"], it.get("description") or "", it.get("placement"))
    removed, kept = [], []
    for x in existing:
        if x["page_id"] in used:
            continue
        if x["version_id"]:
            kept.append(x["label"])
            order.append(x["page_id"])
        else:
            studio.delete_page(x["page_id"])
            removed.append(x["label"])
    pages = studio.pages(pid)
    studio.reorder_pages(pid, order + [p["id"] for p in pages if p["id"] not in order])
    out = [f"Intro pages set to your {len(intro)}: " + ", ".join(i["label"] for i in intro)]
    if removed:
        out.append("Removed default intro pages: " + ", ".join(removed))
        if any("copyright" in _norm(r) for r in removed):
            warnings.append("The default copyright page was removed because your brief lists its own intro pages. KDP doesn't "
                            "require one, but you can add an intro page with “Text: Copyright © …” if you want it.")
    if kept:
        warnings.append("These intro pages already have artwork and were kept after yours: " + ", ".join(kept) + ".")
    return out


def apply_brief(studio, pid: str, data: dict) -> dict:
    from .generation import plan_from_description  # noqa: F401  (imports module with handlers)
    changes: list[str] = []
    warnings: list[str] = []
    old = studio.spec(pid)
    spec, w = spec_from_settings(data)
    warnings += w
    if spec:
        studio.update_spec(pid, spec)
        changes.append("Book setup updated")
    new = studio.spec(pid)
    # keep the default intro text in step with the new title/subtitle/author
    for p in [p for p in studio.pages(pid) if p["kind"] == "intro"]:
        els, touched = [], False
        for e in p["elements"]:
            if e["kind"] == "text" and e.get("text"):
                t = e["text"]
                for k in ("title", "subtitle", "author"):
                    if old.get(k) and new.get(k) and old[k] != new[k] and old[k] in t:
                        t = t.replace(old[k], new[k])
                if t != e["text"]:
                    e = {**e, "text": t}
                    touched = True
            els.append(e)
        if touched:
            studio.save_elements(p["id"], els, reason="brief: update intro text")
    # style
    st = data.get("settings", {})
    if st.get("style_preset"):
        key = _match_preset(st["style_preset"])
        if key:
            studio.apply_style_preset(pid, key)
            changes.append(f"Style preset: {key}")
        else:
            warnings.append(f"Style preset “{st['style_preset']}” not found; kept the current style.")
    sg_patch = {}
    if "master_style" in data:
        sg_patch["master_style"] = data["master_style"]
    if st.get("cleanup"):
        sg_patch["cleanup_mode"] = "fine" if any(x in st["cleanup"].lower() for x in ("fine", "adult", "intricate", "detail")) else "bold"
    elif data.get("master_style") and re.search(r"stippl|hatch|fine|micron|intricate", data["master_style"], re.I):
        sg_patch["cleanup_mode"] = "fine"
        changes.append("Line-art cleanup set to Fine detail (your master style asks for fine detail)")
    if data.get("characters"):
        sg_patch["characters"] = [{"name": c.get("name", ""), "role": c.get("role", ""), "powers": c.get("powers", ""),
                                   "costume": c.get("costume", ""), "emblem": c.get("emblem", ""), "appearance": c.get("appearance", ""),
                                   "proportions": c.get("proportions", ""), "reference_asset_ids": []} for c in data["characters"]]
    if data.get("team"):
        sg_patch["team"] = data["team"]
    if data.get("avoid"):
        sg_patch["avoid"] = data["avoid"]
    if sg_patch:
        studio.update_style_guide(pid, sg_patch)
        changes.append("Style guide updated" + (" (master style)" if "master_style" in sg_patch else ""))
    # illustration pages: make the count match, then plan and fill descriptions
    count = new["illustration_count"]
    illus = [p for p in studio.pages(pid) if p["kind"] == "illustration"]
    if len(illus) < count:
        for _ in range(count - len(illus)):
            studio.add_page(pid, "illustration")
    elif len(illus) > count:
        removable = [p for p in reversed(illus) if not p["approved"] and not p["elements"]]
        for p in removable[: len(illus) - count]:
            studio.delete_page(p["id"])
        left = len([p for p in studio.pages(pid) if p["kind"] == "illustration"])
        if left > count:
            warnings.append(f"{left - count} extra illustration page(s) already have artwork or approval and were kept.")
            studio.update_spec(pid, {"illustration_count": left})
            count = left
    studio.draft_plan(pid, count, replace=True)
    rows = studio.page_descriptions(pid)
    for row, pg in zip(rows, data.get("pages", [])):
        studio.set_page_description(row["page_id"], pg["description"])
        label = pg.get("label") or _short_label(pg.get("description", ""))
        if label:
            studio.update_page_meta(row["page_id"], {"label": f"{row['illustration_number']}. {label}"[:120]})
    if data.get("pages"):
        changes.append(f"{min(len(rows), len(data['pages']))} page descriptions set")
    # intro pages
    if data.get("intro_exact"):
        changes += _apply_intro_exact(studio, pid, data["intro"], warnings)
    else:
        for it in data.get("intro", []):
            rows_i = studio.intro_descriptions(pid)
            r = _match_intro(it["label"], rows_i)
            if r is None:
                r = _new_intro_page(studio, pid, it)
                changes.append(f"Intro page added: {it['label']}")
            elif it.get("text"):
                _set_intro_text(studio, r["page_id"], it["text"])
            if it.get("description"):
                studio.set_intro_description(r["page_id"], it["description"], it.get("placement"))
        if data.get("intro"):
            changes.append(f"{len(data['intro'])} intro page(s) described")
    n_intro = len([p for p in studio.pages(pid) if p["kind"] == "intro"])
    if int(studio.spec(pid).get("intro_pages", n_intro)) != n_intro:
        studio.update_spec(pid, {"intro_pages": n_intro})
    # cover
    cov = {}
    if data.get("front_cover"):
        cov["front_description"] = data["front_cover"][:4000]
    if data.get("back_cover"):
        cov["back_description"] = data["back_cover"][:4000]
    if data.get("back_cover_text"):
        cov["back_copy"] = data["back_cover_text"]
    if not data.get("back_cover_text"):
        cur_back = (studio.cover(pid)["data"].get("back_copy") or "").strip()
        from .studio import DEFAULT_COVER
        if not cur_back or cur_back == DEFAULT_COVER["back_copy"].strip():
            from .listing_draft import draft_listing
            cov["back_copy"] = draft_listing(studio, pid)["back_copy"]
            changes.append("Back-cover text drafted from your book (edit it on the Cover page)")
    if cov:
        studio.update_cover(pid, cov)
        changes.append("Cover descriptions/text set")
    studio.recalc_cover(pid)
    # listing
    lp = {"title": new["title"], "subtitle": new.get("subtitle", ""), "author": new.get("author", ""), "language": new.get("language", "English")}
    if new.get("age_min") and new.get("age_max"):
        lp["age_range"] = f"{new['age_min']}–{new['age_max']}"
    elif (new.get("audience") or "").lower().startswith("adult"):
        lp["age_range"] = "Adults"
    L = data.get("listing", {})
    if L.get("description"):
        lp["description"] = L["description"]
    if L.get("keywords"):
        lp["keywords"] = L["keywords"]
    if L.get("category_notes"):
        lp["category_notes"] = L["category_notes"]
    price = L.get("list_price") or st.get("list_price")
    if price:
        m = re.search(r"\d+(?:\.\d{1,2})?", price)
        if m:
            lp["list_price"] = m.group(0)
    if L.get("isbn"):
        lp["isbn_choice"] = "free_kdp" if "free" in L["isbn"].lower() or "kdp" in L["isbn"].lower() else "own" if "own" in L["isbn"].lower() else "undecided"
    studio.update_listing(pid, lp)
    changes.append("Listing draft updated")
    asm = studio.assembly(pid)
    if asm["page_count"] < 24:
        need = (24 - asm["intro_count"] + 1) // (2 if new.get("blank_backs", True) else 1)
        warnings.append(f"The book has {asm['page_count']} pages; KDP paperbacks need at least 24. Describe at least {need} pages "
                        f"(or set “Illustrations: {need}” and let the app plan the rest).")
    return {"changes": changes, "warnings": warnings, "assembly": asm}


# ------------------------------------------------------------------------------------------------ export

def export_brief(studio, pid: str) -> str:
    sp, sg, ls, cv = studio.spec(pid), studio.style_guide(pid), studio.listing(pid), studio.cover(pid)["data"]
    ages = f"{sp['age_min']}-{sp['age_max']}" if sp.get("age_min") and sp.get("age_max") else ("Adults" if (sp.get("audience") or "").lower().startswith("adult") else "")
    out = [f"# {sp['title']}", "", "## Settings",
           f"- Subtitle: {sp.get('subtitle', '')}", f"- Author: {sp.get('author', '')}", f"- Audience: {sp.get('audience', '')}",
           f"- Ages: {ages}", f"- Trim: {sp['trim']}", f"- Paper: {'cream' if sp['paper'] == 'bw_cream' else 'white'}",
           f"- Bleed: {'yes' if sp.get('interior_bleed') else 'no'}", f"- Blank backs: {'yes' if sp.get('blank_backs', True) else 'no'}",
           f"- Style preset: {sg.get('preset', '')}", f"- Cleanup: {sg.get('cleanup_mode', 'bold')}",
           f"- Illustrations: {len(studio.page_descriptions(pid))}", f"- List price: {ls.get('list_price', '')}", "",
           "## Book description", "", sp.get("theme") or "", "", "## Master style", "", sg.get("master_style") or "", ""]
    if sg.get("avoid"):
        out += ["## Avoid", ""] + [f"- {a}" for a in sg["avoid"] if a] + [""]
    if sg.get("characters"):
        out += ["## Characters", ""]
        for c in sg["characters"]:
            if c.get("name"):
                out += [f"### {c['name']}"] + [f"- {k.title()}: {c[k]}" for k in ("role", "powers", "costume", "emblem", "appearance", "proportions") if c.get(k)] + [""]
    if (sg.get("team") or {}).get("name"):
        t = sg["team"]
        out += ["## Team", ""] + [f"- {k.title()}: {t[k]}" for k in ("name", "motto", "headquarters", "emblem") if t.get(k)] + [""]
    out += ["## Front cover", "", cv.get("front_description") or "", "", "## Back cover", "", cv.get("back_description") or "", "",
            "## Back cover text", "", cv.get("back_copy") or "", "", "## Intro pages", ""]
    PL = {"behind_text": "behind text", "full_page": "full page picture", "free_space": "free space"}
    for i, r in enumerate(studio.intro_descriptions(pid), 1):
        out += [f"### Intro {i} ({r['label']})", f"- Placement: {PL.get(r['placement'], 'free space')}"]
        out += ["", r["description"] or "", ""]
    out += ["## Pages", ""]
    for r in studio.page_descriptions(pid):
        label = re.sub(r"^\d+\.\s*", "", r["label"] or "")
        out += [f"### Page {r['illustration_number']}" + (f": {label}" if label and not label.lower().startswith("illustration") else ""), "",
                r["description"] or "", ""]
    out += ["## Listing", "", f"- Keywords: {', '.join(k for k in (ls.get('keywords') or []) if k)}",
            f"- ISBN: {ls.get('isbn_choice', 'undecided')}", "", "### Description", "", ls.get("description") or "", ""]
    return "\n".join(out).rstrip() + "\n"


# ------------------------------------------------------------------------------------------------ JSON form

def brief_to_json(data: dict) -> dict:
    """The parsed brief as a clean JSON object (the same shape a .json brief is read in)."""
    out: dict = {"title": data.get("title", "")}
    if data.get("settings"):
        out["settings"] = {k: v for k, v in data["settings"].items() if k != "format"}
    for k in ("book_description", "master_style"):
        if data.get(k):
            out[k] = data[k]
    if data.get("avoid"):
        out["avoid"] = data["avoid"]
    if data.get("characters"):
        out["characters"] = [{k: v for k, v in c.items() if v} for c in data["characters"]]
    if data.get("team"):
        out["team"] = data["team"]
    for k in ("front_cover", "back_cover", "back_cover_text"):
        if data.get(k):
            out[k] = data[k]
    if data.get("intro"):
        out["intro_pages"] = [{k: v for k, v in (("number", i.get("number")), ("label", i["label"]), ("placement", i.get("placement")),
                                                 ("text", i.get("text")), ("description", i.get("description"))) if v}
                              for i in data["intro"]]
    if data.get("pages"):
        out["pages"] = [{k: v for k, v in (("page", p.get("number")), ("label", p.get("label")), ("act", p.get("act")),
                                           ("description", p.get("description"))) if v} for p in data["pages"]]
    if data.get("listing"):
        out["listing"] = data["listing"]
    return out


def export_brief_json(studio, pid: str) -> str:
    import json
    return json.dumps(brief_to_json(parse_brief(export_brief(studio, pid))["data"]), indent=2, ensure_ascii=False) + "\n"


def template_json() -> str:
    import json
    from .config import PROFILE_DIR
    return json.dumps(brief_to_json(parse_brief((PROFILE_DIR / "book-brief-template.md").read_text())["data"]), indent=2, ensure_ascii=False) + "\n"
