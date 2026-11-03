"""Story pages: text on the left-hand page that describes the illustration facing it (spec["facing_text"]).

The text belongs to the illustration page (table page_stories), so re-planning scenes, reordering pages or replacing art
never loses it. It can be typed, pasted for many pages at once, loaded from a book brief, or written by an OpenAI text
model (optional, billed to the owner's OpenAI account, inside the same spending limit as images).

AI-written text is recorded as AI-generated (meta.ai) and stays that way after editing, and the listing's text-AI
answer is raised to "AI-generated" because KDP asks about AI-generated text."""
from __future__ import annotations

import re
from decimal import Decimal

from .db import jdump, jload, new_id, now_iso
from .jobs import handler
from .layout import assemble

MAX_STORY_CHARS = 9000
MAX_TITLE_CHARS = 80


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9’']+", text or ""))


# ------------------------------------------------------------------------------------------------ storage

def _rows(studio, pid: str) -> dict[str, dict]:
    return {r["page_id"]: {"title": r["title"] or "", "text": r["text"] or "", "meta": jload(r["meta"]) or {}, "updated_at": r["updated_at"]}
            for r in studio.db.q("SELECT * FROM page_stories WHERE project_id=?", (pid,))}


def story_map(studio, pid: str) -> dict[str, dict]:
    return _rows(studio, pid)


def list_stories(studio, pid: str) -> list[dict]:
    spec = studio.spec(pid)
    pages = studio.pages(pid)
    asm = assemble(pages, spec)
    story_nums = {e["story_for"]: e["number"] for e in asm["pages"] if e["kind"] == "story"}
    pic_nums = {e["page_id"]: e["number"] for e in asm["pages"] if e["page_id"]}
    scenes = {sc["id"]: sc for sc in studio.scenes(pid)}
    rows = _rows(studio, pid)
    out = []
    target = int(spec.get("story_words") or 400)
    for i, p in enumerate([p for p in pages if p["kind"] == "illustration"]):
        st = rows.get(p["id"], {"title": "", "text": "", "meta": {}})
        img = next((e for e in p["elements"] if e["kind"] == "image"), None)
        fit = story_fit(studio, pid, st["text"], st["title"]) if st["text"].strip() else None
        out.append({"page_id": p["id"], "illustration_number": i + 1, "label": p["label"],
                    "story_page_number": story_nums.get(p["id"]), "picture_page_number": pic_nums.get(p["id"]),
                    "description": (scenes.get(p["scene_id"]) or {}).get("description", ""),
                    "title": st["title"], "text": st["text"], "words": word_count(st["text"]), "target_words": target,
                    "ai": bool(st["meta"].get("ai")), "ai_model": (st["meta"].get("ai") or {}).get("model"),
                    "edited_after_ai": bool(st["meta"].get("edited_after_ai")),
                    "fits": fit["fits"] if fit else None, "font_pt": fit["body_pt"] if fit else None,
                    "version_id": img["asset_version_id"] if img else None})
    return out


def set_story(studio, page_id: str, text: str, title: str | None = None, ai_meta: dict | None = None) -> dict:
    p = studio.page(page_id)
    if p["kind"] != "illustration":
        raise ValueError("Story text belongs to an illustration page.")
    text = re.sub(r"\r\n?", "\n", text or "").strip()
    title = (title or "").strip()
    if len(text) > MAX_STORY_CHARS:
        raise ValueError(f"A story page can hold at most {MAX_STORY_CHARS} characters (about 1,400 words).")
    if len(title) > MAX_TITLE_CHARS:
        raise ValueError(f"A story title can be at most {MAX_TITLE_CHARS} characters.")
    from .ip_guard import find
    old = _rows(studio, p["project_id"]).get(page_id)
    meta = dict(old["meta"]) if old else {}
    if ai_meta:
        meta = {"ai": ai_meta}
    elif meta.get("ai") and old and old["text"] != text:
        meta["edited_after_ai"] = True  # still AI-generated under KDP's definition
    studio.db.x("""INSERT INTO page_stories(page_id, project_id, title, text, meta, updated_at) VALUES (?,?,?,?,?,?)
                   ON CONFLICT(page_id) DO UPDATE SET title=excluded.title, text=excluded.text, meta=excluded.meta, updated_at=excluded.updated_at""",
                (page_id, p["project_id"], title, text, jdump(meta), now_iso()))
    studio.touch(p["project_id"])
    row = next(r for r in list_stories(studio, p["project_id"]) if r["page_id"] == page_id)
    row["protected_names"] = [h["matched"] for h in find(title + "\n" + text)]
    return row


SPLIT_RE = re.compile(r"^\s*(?:#{1,6}\s*)?(?:\*\*)?(?:page|story|picture|illustration)\s*#?\s*(\d+)\b\s*(?:\*\*)?\s*[:.)\-–—]?\s*(.*)$", re.I)


def split_pasted(text: str) -> list[tuple[int | None, str, str]]:
    """'Page 1: Title' / '### Story 2' headings start a new story; '---' lines also separate stories.
    Returns (number, title, text) tuples."""
    out: list[list] = []
    cur = None
    for ln in (text or "").replace("\r\n", "\n").split("\n"):
        m = SPLIT_RE.match(ln)
        if m:
            cur = [int(m.group(1)), m.group(2).strip().strip("*").strip(), []]
            out.append(cur)
        elif re.match(r"^\s*-{3,}\s*$", ln):
            cur = None
        else:
            if cur is None:
                if not ln.strip():
                    continue
                cur = [None, "", []]
                out.append(cur)
            cur[2].append(ln)
    res = []
    for n, title, lines in out:
        body = "\n".join(lines).strip()
        body = re.sub(r"\n{3,}", "\n\n", body)
        if body or title:
            # a heading line that is really the story's first sentence is not a title
            if title and len(title.split()) > 10:
                body, title = (title + ("\n\n" + body if body else "")).strip(), ""
            res.append((n, title, body))
    return res


def bulk_set(studio, pid: str, text: str) -> dict:
    parts = split_pasted(text)
    if not parts:
        raise ValueError("No stories found. Start each one with a line like “Page 1” (or put a line with --- between them).")
    rows = list_stories(studio, pid)
    nxt, filled, ignored = 0, 0, 0
    for n, title, body in parts:
        idx = (n - 1) if n else nxt
        if not 0 <= idx < len(rows):
            ignored += 1
            continue
        set_story(studio, rows[idx]["page_id"], body, title)
        filled += 1
        nxt = idx + 1
    return {"filled": filled, "ignored": ignored, "rows": list_stories(studio, pid)}


# ------------------------------------------------------------------------------------------------ fit on the page

def story_fit(studio, pid: str, text: str, title: str = "") -> dict:
    from .geometry import page_geometry, resolve_config
    from .render import layout_story
    spec = studio.spec(pid)
    cfg = resolve_config(spec)
    asm = assemble(studio.pages(pid), spec)
    num = next((e["number"] for e in asm["pages"] if e["kind"] == "story"), 2)
    geo = page_geometry(cfg, num, max(asm["page_count"], 24))
    from .units import in_to_pt
    lay = layout_story(text, title, in_to_pt(geo.safe.w), in_to_pt(geo.safe.h))
    return {"fits": lay is not None, "body_pt": lay["body_pt"] if lay else None}


# ------------------------------------------------------------------------------------------------ AI writing

_text_override = None


def set_test_text_provider(p):
    global _text_override
    _text_override = p


def text_provider(studio):
    if _text_override is not None:
        return _text_override
    from .generation import SecretStore
    from .providers.openai_text import DEFAULT_TEXT_MODEL, OpenAITextProvider
    cfg = studio.get_setting("ai_provider", {}) or {}
    return OpenAITextProvider(SecretStore(studio.settings.secrets_path).get("OPENAI_API_KEY"), model=cfg.get("text_model") or DEFAULT_TEXT_MODEL)


def _strip_act(a: str) -> str:
    return re.sub(r"^\s*(act|chapter|part)\s+\w+\s*[:.\-–—]\s*", "", a or "", flags=re.I).strip()


def build_story_request(spec: dict, style: dict, row: dict, prev_text: str = "", next_desc: str = "") -> tuple[str, str]:
    lo, hi = spec.get("age_min"), spec.get("age_max")
    target = int(spec.get("story_words") or 400)
    kids = bool(lo and hi and hi <= 10)
    reader = f"children ages {lo}–{hi}, read aloud by a grown-up" if kids else (spec.get("audience") or "readers")
    chars = []
    for c in style.get("characters", []):
        if c.get("name"):
            bits = [b for b in (c.get("role"), c.get("appearance")) if b]
            chars.append(f"- {c['name']}: {'; '.join(bits)}")
    instructions = (
        f"You write the story text for a coloring book. Each picture sits on a right-hand page; your text is printed on the "
        f"left-hand page facing it, for {reader}.\n"
        f"Write {target}–{target + 120} words of plain prose (no headings, no bullet points, no markdown) in 4–7 short paragraphs "
        "separated by blank lines.\n"
        "Describe what is happening in the picture so a child can find each thing in it, tell this moment of the story with "
        "warmth and gentle humor, and keep it continuous with the previous page. "
        + ("Use short sentences and simple, everyday words; nothing scary or violent. " if kids else "")
        + "End with one friendly question or coloring idea about the picture (for example which color the child might choose). "
        "Use only the characters and places given; never mention or imitate characters, shows, films, games, brands or "
        "authors that belong to anyone else. Write only the story text."
    )
    parts = [f"Book: {spec.get('title', '')}" + (f" – {spec['subtitle']}" if spec.get("subtitle") else "")]
    theme = (spec.get("theme") or "").strip()
    if theme:
        parts.append("About the book:\n" + theme[:3000])
    if chars:
        parts.append("Characters:\n" + "\n".join(chars))
    parts.append(f"This is picture {row['illustration_number']}.")
    if row.get("description"):
        parts.append("The picture on the right shows:\n" + row["description"])
    elif row.get("label"):
        parts.append("The picture on the right shows:\n" + re.sub(r"^\d+\.\s*", "", row["label"]))
    if prev_text:
        parts.append("The previous page's story ended like this:\n" + prev_text[-700:])
    if next_desc:
        parts.append("The next picture will show (don't describe it yet, but you may lead toward it):\n" + next_desc)
    return instructions, "\n\n".join(parts)


def estimate_stories(studio, pid: str, page_ids: list[str]) -> dict:
    from .generation import budget
    from .ip_guard import find
    prov = text_provider(studio)
    st = prov.status()
    cfg = studio.get_setting("ai_provider", {}) or {}
    per = cfg.get("per_story_estimate")
    b = budget(studio, pid)
    n = len(page_ids)
    problems = []
    if not st["configured"]:
        problems.append("No OpenAI API key is saved (Settings or ✨ Create with AI).")
    if n == 0:
        problems.append("No pages selected – every story already has text, or the book has no illustration pages.")
    if n > 1 and not per:
        problems.append("Cost per story is unknown. Enter your own estimate (from OpenAI's price page) before writing many stories.")
    if n > 1 and b["spending_limit"] is None:
        problems.append("Set a spending limit before writing many stories.")
    if per and b["spending_limit"] is not None and Decimal(b["estimated_spent"]) + Decimal(per) * n > Decimal(b["spending_limit"]):
        problems.append(f"This would exceed your spending limit ({b['spending_limit']}).")
    spec, style = studio.spec(pid), studio.style_guide(pid)
    rows = {r["page_id"]: r for r in list_stories(studio, pid)}
    for pid_ in page_ids[:200]:
        if pid_ in rows:
            ins, prompt = build_story_request(spec, style, rows[pid_])
            for h in find(prompt):
                problems.append(f"Picture {rows[pid_]['illustration_number']} mentions “{h['matched']}” ({h['owner']}); story text "
                                "for protected characters can't be written.")
                break
    return {"count": n, "model": st.get("model"), "per_story_estimate": per, "estimated_cost": str(Decimal(per) * n) if per else "unknown",
            "budget": b, "allowed": not problems, "problems": problems,
            "note": "Text is written by OpenAI and billed to your OpenAI account. Read and edit every page before publishing."}


def start_writing(studio, runner, pid: str, page_ids: list[str] | None, confirm: bool, overwrite: bool = False) -> dict:
    if not confirm:
        raise ValueError("Writing stories with AI needs your confirmation.")
    rows = list_stories(studio, pid)
    ids = page_ids or [r["page_id"] for r in rows if overwrite or not r["text"].strip()]
    est = estimate_stories(studio, pid, ids)
    if not est["allowed"]:
        raise ValueError(" ".join(est["problems"]))
    return runner.enqueue("write_stories", pid, {"page_ids": ids, "per_story_estimate": est["per_story_estimate"]},
                          dedupe_key=f"stories:{pid}")


@handler("write_stories")
def write_stories_job(studio, ctx, params) -> dict:
    from .generation import budget
    from .ip_guard import find
    from .providers.base import ProviderOutcomeUnknown, ProviderRequestFailed
    pid = ctx.job["project_id"]
    prov = text_provider(studio)
    model = prov.status().get("model")
    live = prov.status().get("live", False)
    per = params.get("per_story_estimate")
    ids = params["page_ids"]
    spec, style = studio.spec(pid), studio.style_guide(pid)
    written, failed, unknown, stopped = [], [], [], False
    for i, page_id in enumerate(ids):
        ctx.check()
        rows = list_stories(studio, pid)
        by_id = {r["page_id"]: r for r in rows}
        row = by_id.get(page_id)
        if not row:
            continue
        k = row["illustration_number"] - 1
        prev_text = rows[k - 1]["text"] if k > 0 else ""
        next_desc = rows[k + 1]["description"] if k + 1 < len(rows) else ""
        ins, prompt = build_story_request(spec, style, row, prev_text, next_desc)
        b = budget(studio, pid)
        if per and b["spending_limit"] is not None and Decimal(b["estimated_spent"]) + Decimal(per) > Decimal(b["spending_limit"]):
            stopped = True
            break
        gid = new_id("gen")
        studio.db.x("""INSERT INTO generation_requests(id, project_id, job_id, scene_id, provider, model, prompt, params, state,
                       estimated_cost, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (gid, pid, ctx.job["id"], None, prov.name, model, prompt, jdump({"kind": "story", "page_id": page_id}),
                     "submitting", per, now_iso(), now_iso()))
        try:
            res = prov.write(ins, prompt)
        except ProviderOutcomeUnknown as e:
            studio.db.x("UPDATE generation_requests SET state='unknown_outcome', error=?, updated_at=? WHERE id=?", (str(e), now_iso(), gid))
            unknown.append({"page": row["illustration_number"], "error": str(e)})
            continue
        except ProviderRequestFailed as e:
            studio.db.x("UPDATE generation_requests SET state='failed', error=?, updated_at=? WHERE id=?", (str(e), now_iso(), gid))
            failed.append({"page": row["illustration_number"], "error": str(e)})
            if "401" in str(e) or "quota" in str(e).lower() or "credit" in str(e).lower():
                break  # every following request would fail the same way
            continue
        text = re.sub(r"^\s*#+\s.*\n", "", res["text"]).strip()
        hits = find(text)
        studio.db.x("UPDATE generation_requests SET state='succeeded', reported_usage=?, updated_at=? WHERE id=?",
                    (jdump(res.get("usage")), now_iso(), gid))
        if hits:
            failed.append({"page": row["illustration_number"], "error": f"The text mentioned “{hits[0]['matched']}”, so it was not used."})
            continue
        set_story(studio, page_id, text, row["title"], ai_meta={"provider": prov.name, "model": res.get("model") or model,
                                                                  "live": live, "generated_at": now_iso(), "request_id": res.get("request_id"),
                                                                  "generation_request_id": gid})
        written.append(row["illustration_number"])
        ctx.progress((i + 1) / len(ids), f"Story {i + 1} of {len(ids)}")
    if written:
        ls = studio.listing(pid)
        if ls.get("text_ai_involvement") in (None, "none", "ai_assisted"):
            studio.update_listing(pid, {"text_ai_involvement": "ai_generated"})
    return {"written": written, "failed": failed, "unknown_outcome": unknown, "stopped_at_limit": stopped}
