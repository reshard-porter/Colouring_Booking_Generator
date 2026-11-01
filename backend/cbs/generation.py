"""Controlled, budgeted AI generation workflow (optional)."""
from __future__ import annotations

import json
import os
import stat
from decimal import Decimal

from .db import jdump, jload, new_id, now_iso
from .jobs import handler
from .providers.base import ProviderOutcomeUnknown, ProviderRequestFailed
from .providers.openai_images import OpenAIImagesProvider


class SecretStore:
    """API keys live only on the server: env var, or a 0600 secrets file in the data dir.
    They are never returned by the API, written to exports, or logged."""

    def __init__(self, path):
        self.path = path

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except FileNotFoundError:
            return {}

    def get(self, name: str) -> str | None:
        env = os.environ.get(name)
        if env:
            return env
        return self._load().get(name)

    def source(self, name: str) -> str | None:
        if os.environ.get(name):
            return "environment"
        return "local secrets file" if self._load().get(name) else None

    def set(self, name: str, value: str | None):
        d = self._load()
        if value:
            d[name] = value.strip()
        else:
            d.pop(name, None)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d))
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(tmp, self.path)


_override_provider = None  # tests may inject a provider


def set_test_provider(p):
    global _override_provider
    _override_provider = p


def get_provider(studio):
    if _override_provider is not None:
        return _override_provider
    if os.environ.get("CBS_ENABLE_MOCK_PROVIDER") == "1":
        from .providers.mock import MockProvider
        return MockProvider()
    cfg = studio.get_setting("ai_provider", {}) or {}
    secrets = SecretStore(studio.settings.secrets_path)
    from .providers.openai_images import DEFAULT_MODEL
    return OpenAIImagesProvider(secrets.get("OPENAI_API_KEY"), model=cfg.get("model") or DEFAULT_MODEL)


def budget(studio, pid: str) -> dict:
    cfg = studio.get_setting("ai_provider", {}) or {}
    rows = studio.db.q("SELECT state, estimated_cost, reported_cost FROM generation_requests WHERE project_id=?", (pid,))
    est_spent = sum((Decimal(r["estimated_cost"]) for r in rows if r["estimated_cost"] and r["state"] in ("succeeded", "unknown_outcome", "submitting")), Decimal(0))
    reported = sum((Decimal(r["reported_cost"]) for r in rows if r["reported_cost"]), Decimal(0))
    return {
        "per_image_estimate": cfg.get("per_image_estimate"),  # entered by the owner; None = unknown
        "spending_limit": cfg.get("spending_limit"),
        "estimated_spent": str(est_spent),
        "provider_reported_cost": str(reported) if reported else None,
        "unknown_outcomes": sum(1 for r in rows if r["state"] == "unknown_outcome"),
        "note": "Estimates come from the per-image figure you entered. Provider-reported charges are shown separately "
                "when available; check your provider dashboard for actual billing.",
    }


def _ip_problems(studio, pid: str, scene_ids: list[str] | None) -> list[str]:
    from .ip_guard import find
    spec, style = studio.spec(pid), studio.style_guide(pid)
    scenes = {s["id"]: s for s in studio.scenes(pid)}
    probs = []
    for sid in scene_ids or []:
        if sid in scenes:
            for h in find(build_prompt(spec, style, scenes[sid])):
                probs.append(f"The prompt for “{scenes[sid].get('subject')}” mentions “{h['matched']}” ({h['owner']}). "
                             "Generation of protected characters or brands is not allowed – use your original characters.")
    return probs


def estimate(studio, pid: str, count: int, settings: dict, scene_ids: list[str] | None = None) -> dict:
    prov = get_provider(studio)
    st = prov.status()
    b = budget(studio, pid)
    per = b["per_image_estimate"]
    total = str(Decimal(per) * count) if per else "unknown"
    has_candidate = bool(studio.db.q1("""SELECT 1 FROM generation_requests g JOIN assets a ON a.id=g.asset_id
                                          WHERE g.project_id=? AND g.state='succeeded' AND a.review_status='approved'""", (pid,)))
    problems = _ip_problems(studio, pid, scene_ids)
    if not st["configured"]:
        problems.append("No image provider is configured.")
    if count > 1 and not has_candidate:
        problems.append("Generate ONE candidate and approve it in the artwork library before running a batch.")
    if count > 1 and not per:
        problems.append("Cost per image is unknown. Enter your own per-image estimate in Settings before batch generation.")
    if b["spending_limit"] is None and count > 1:
        problems.append("Set a spending limit in Settings before batch generation.")
    if per and b["spending_limit"] is not None:
        if Decimal(b["estimated_spent"]) + Decimal(per) * count > Decimal(b["spending_limit"]):
            problems.append(f"This batch would exceed your spending limit ({b['spending_limit']}).")
    return {"provider": st, "count": count, "settings": settings, "estimated_cost": total, "budget": b,
            "allowed": not problems, "problems": problems,
            "warning": "Image generation cannot guarantee character consistency or correct anatomy. Review every image."}


def _age_detail(spec: dict) -> str:
    age = int(spec.get("age_max") or 7)
    if age <= 6:
        return "Very simple: a few BIG shapes, thick outlines, almost no small details, wide-open coloring areas."
    if age <= 10:
        return "Simple to medium detail: large main shapes with some fun details, no tiny fiddly areas."
    return "Medium detail with clear separate shapes; still no tiny texture patterns."


def _character_text(style: dict) -> str:
    chars = []
    for c in style.get("characters", []):
        if not c.get("name"):
            continue
        bits = [c.get("appearance"), f"costume: {c['costume']}" if c.get("costume") else None,
                f"chest emblem: {c['emblem']}" if c.get("emblem") else None, f"power: {c['powers']}" if c.get("powers") else None,
                f"proportions: {c['proportions']}" if c.get("proportions") else None]
        chars.append(f"{c['name']} ({'; '.join(b for b in bits if b)})")
    team = style.get("team") or {}
    out = ("Recurring original characters – keep their look consistent: " + "; ".join(chars) + ". ") if chars else ""
    if team.get("name"):
        out += f"They belong to an original hero team called {team['name']}" + (f" whose emblem is {team['emblem']}" if team.get("emblem") else "") + ". "
    return out


def build_prompt(spec: dict, style: dict, scene: dict, with_reference: bool = False) -> str:
    base = _build_prompt_base(spec, style, scene, with_reference)
    if not spec.get("theme"):
        return base.replace("{THEME}", "")
    budget = OPENAI_PROMPT_LIMIT - PROMPT_SAFETY_MARGIN - len(base)
    scene_words = " ".join(str(scene.get(k) or "") for k in ("subject", "action", "setting", "description")).lower()
    focus = [scene.get("subject"), scene.get("action"), scene.get("setting"), scene.get("description")] + \
        [c.get("name") for c in style.get("characters", []) if c.get("name") and c["name"].split()[0].lower() in scene_words]
    text, excerpt = description_for_prompt(spec["theme"], budget, focus)
    label = "BOOK DESCRIPTION (excerpt relevant to this page)" if excerpt else "BOOK DESCRIPTION"
    return base.replace("{THEME}", f"{label}:\n{text}\n")


def _scene_text(scene: dict, master: bool) -> str:
    desc = (scene.get("description") or "").strip()
    if desc:
        # the owner's own words for this page lead; auto-drafted fields are not mixed in
        return f"THIS PAGE MUST SHOW: {desc}\n"
    tail = "" if master else " The main character is large, shown in full, and clearly the focus."
    return (f"SCENE: {scene.get('subject')}, {scene.get('action')}. Setting: {scene.get('setting')}. "
            f"Composition: {scene.get('composition')}.{tail}\n")


def _build_prompt_base(spec: dict, style: dict, scene: dict, with_reference: bool = False) -> str:
    avoid = ", ".join(a for a in style.get("avoid", []) if a)
    lo, hi = spec.get("age_min"), spec.get("age_max")
    master = (style.get("master_style") or "").strip()
    ref = ("Image 1 is a STYLE REFERENCE from the same coloring book: match its line thickness, level of detail and the way "
           "characters are drawn. Do NOT copy its scene, pose or composition – draw the new scene described below.\n") if with_reference else ""
    essentials = ("no color, no text, letters, numbers, signatures or watermarks. Original characters only – do not depict any "
                  "existing copyrighted character, costume, logo or brand.")
    if master:
        # The owner's master style decides the look; only content essentials are added by the app, and the master style
        # is placed verbatim at the very END of the prompt.
        return (
            f"{ref}Create ONE printable coloring book page for {spec.get('audience', 'readers')}"
            f"{f' (ages {lo}–{hi})' if lo and hi else ''}.\n"
            f"{{THEME}}"
            f"{_scene_text(scene, master=True)}"
            f"{_character_text(style)}"
            f"RULES: {essentials}\n"
            f"{('ALSO AVOID: ' + avoid + '.' + chr(10)) if avoid else ''}"
            f"{master}")
    return (
        f"{ref}Create ONE printable coloring book page for {spec.get('audience', 'children')}"
        f"{f' (ages {lo}–{hi})' if lo and hi else ''}.\n"
        f"STYLE: {style.get('prompt_style') or 'friendly cartoon style'}. Clean, crisp line art: pure black lines on a pure "
        f"white background. {style.get('outline_weight', 'Bold, uniform outlines')}. Lines are smooth and of even thickness; "
        f"every shape is fully closed so it can be colored in.\n"
        f"DETAIL: {_age_detail(spec)} {style.get('coloring_spaces', '')}. Background: {style.get('background_density', 'simple')}.\n"
        f"{{THEME}}"
        f"{_scene_text(scene, master=False)}"
        f"{_character_text(style)}"
        f"STRICT RULES: no gray tones, no shading, no gradients, no hatching or stippling, no solid black filled areas, "
        f"no border or frame. Keep a clean white margin – nothing touches the edges. {essentials}\n"
        f"{('ALSO AVOID: ' + avoid + '.') if avoid else ''}")


def build_cover_prompt(spec: dict, style: dict, cover_data: dict | None = None, which: str = "front") -> str:
    cd = cover_data or {}
    desc = (cd.get(f"{which}_description") or "").strip()
    must = f"THE {which.upper()} COVER MUST SHOW: {desc} " if desc else ""
    if which == "back":
        role = ("Full-color illustration for the BACK cover of a coloring book. It sits below the back-cover text, so keep it "
                "simple, wide and uncluttered (landscape composition). ")
    else:
        role = "Full-color front cover illustration for a coloring book. The main characters are large and happy in the middle. "
    return (
        f"{role}Audience: {spec.get('audience', 'children')}. {must}"
        f"{('Theme: ' + description_for_prompt(spec['theme'], 20000, [desc])[0] + ' ') if spec.get('theme') else ''}"
        f"{style.get('prompt_style') or 'friendly cartoon style'}, bright cheerful colors, clean bold outlines, simple background. "
        f"{_character_text(style)}"
        "Absolutely no text, letters, title, numbers or logos anywhere – the title and text are added separately. "
        "Original characters only – no existing copyrighted characters, costumes or brands.")


def build_intro_prompt(spec: dict, style: dict, page: dict) -> str:
    """Line-art decoration for an introductory page (title page, 'this book belongs to', etc.). The app keeps the page text."""
    placement = page.get("placement") or "free_space"
    scene = {"description": page.get("description") or f"a decorative illustration suitable for the {page.get('label', 'introductory')} page"}
    base = build_prompt(spec, style, scene)
    if placement == "full_page":
        ctx = (f"This is the “{page.get('label', 'introductory page')}” page at the front of the book. Make it ONE full-page, "
               "portrait-shaped coloring illustration that fills the page. Draw words or numbers ONLY where the description "
               "puts them in quotes, spelled exactly as written; any name lines, boxes or banners for the child to fill in "
               "stay blank.\n")
        return ctx + base.replace("no color, no text, letters, numbers,", "no color, no words other than ones quoted in the description,", 1)
    where = ("Draw it as a decorative FRAME around the edges and leave a large plain white area in the middle, because the "
             "page's text will be printed there."
             if placement == "behind_text" else
             "Make it a wide, landscape-shaped illustration: it is placed in an empty band of the page, next to the page's text.")
    ctx = (f"This is the “{page.get('label', 'introductory page')}” page at the front of the book. The app adds the page's own "
           f"text{(' (' + page['page_text'] + ')') if page.get('page_text') else ''} separately, so DO NOT draw any words, letters "
           f"or numbers. {where}\n")
    return ctx + base


def intro_size(prov, placement: str) -> str:
    flex = "2400x3200" in (prov.capabilities().get("sizes") or [])
    if placement in ("behind_text", "full_page"):
        return "2400x3200" if flex else "1024x1536"
    return "2400x1600" if flex else "1536x1024"


def back_cover_size(prov) -> str:
    return "2400x1344" if "2400x3200" in (prov.capabilities().get("sizes") or []) else "1536x1024"


def default_settings(prov) -> dict:
    caps = prov.capabilities()
    sizes = caps.get("sizes") or ["1024x1536"]
    return {"size": sizes[0], "quality": "high", "auto_cleanup": True, "match_sample": True}


def start_generation(studio, runner, pid: str, scene_ids: list[str], settings: dict, confirm: bool,
                     replace_page_ids: list[str] | None = None, auto_cover: bool = False, cover: bool = False,
                     back_cover: bool = False) -> dict:
    if not confirm:
        raise ValueError("Generation requires an explicit Generate confirmation.")
    count = len(scene_ids) + (1 if cover else 0) + (1 if back_cover else 0)
    est = estimate(studio, pid, count, settings, scene_ids)
    if (cover or back_cover) and count == 1:
        est["problems"] = [p for p in est["problems"] if "ONE candidate" not in p]
        est["allowed"] = not est["problems"]
    if not est["allowed"]:
        raise ValueError(" ".join(est["problems"]))
    prov = get_provider(studio)
    merged = {**default_settings(prov), **{k: v for k, v in (settings or {}).items() if v not in (None, "")}}
    return runner.enqueue("generate_images", pid, {"scene_ids": scene_ids, "settings": merged,
                                                   "per_image_estimate": est["budget"]["per_image_estimate"],
                                                   "replace_page_ids": replace_page_ids or [], "auto_cover": auto_cover,
                                                   "cover": cover, "back_cover": back_cover,
                                                   "auto_cleanup": merged.get("auto_cleanup", True)},
                          dedupe_key=f"generate:{pid}")


def _png_reference(studio, version_id: str, max_side: int = 1024) -> bytes:
    from PIL import Image
    from .imaging import open_flat, to_png_bytes
    im = open_flat(studio.version_bytes(version_id)).convert("L")
    im.thumbnail((max_side, max_side), Image.LANCZOS)
    return to_png_bytes(im)


def _style_reference(studio, pid: str) -> str | None:
    """The approved generated sample (its current version) – used to keep the whole book in one style."""
    r = studio.db.q1("""SELECT a.current_version_id FROM generation_requests g JOIN assets a ON a.id=g.asset_id
                         WHERE g.project_id=? AND g.state='succeeded' AND a.review_status='approved' AND a.kind='artwork'
                         ORDER BY g.created_at LIMIT 1""", (pid,))
    return r["current_version_id"] if r else None


def _save_raw(studio, gid: str, data: bytes):
    """Every paid image is written to disk before anything else can go wrong."""
    d = studio.settings.data_dir / "generated-originals"
    d.mkdir(parents=True, exist_ok=True)
    ext = "png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "jpg" if data[:3] == b"\xff\xd8\xff" else "bin"
    p = d / f"{gid}.{ext}"
    p.write_bytes(data)
    return p


def recover_unimported(studio, pid: str) -> list[str]:
    """Import paid images that were saved but never added (e.g. after an earlier bug)."""
    out = []
    rows = studio.db.q("SELECT * FROM generation_requests WHERE project_id=? AND state='received_not_imported'", (pid,))
    for r in rows:
        files = list((studio.settings.data_dir / "generated-originals").glob(f"{r['id']}.*"))
        if not files:
            continue
        gen = {"provider": r["provider"], "model": r["model"], "prompt": r["prompt"], "generation_request_id": r["id"],
               "recovered": True, "live": True}
        a = studio.import_asset(pid, f"recovered-{r['id'][-6:]}.png", files[0].read_bytes(), {
            "source_type": "ai_generated", "ai_involvement": "ai_generated", "creator": f"{r['provider']} {r['model']}",
            "rights_declaration": "unknown", "generation": gen})
        vid = make_print_ready(studio, a["current_version_id"], fine=studio.style_guide(pid).get("cleanup_mode") == "fine")
        studio.db.x("UPDATE generation_requests SET state='succeeded', asset_id=?, error=NULL, updated_at=? WHERE id=?", (a["id"], now_iso(), r["id"]))
        for p in studio.pages(pid):
            if p["scene_id"] == r["scene_id"] and p["kind"] == "illustration" and not p["approved"] and not any(e["kind"] == "image" for e in p["elements"]):
                studio.place_asset(p["id"], vid)
                break
        out.append(a["id"])
    return out


def make_print_ready(studio, version_id: str, fine: bool = False) -> str:
    """Threshold + despeckle + crop; smooth-enlarge only if the art is too small for a full page (recorded as enlarged).
    fine=True keeps stippling dots and tiny enclosed areas (for intricate adult styles)."""
    v = studio.derive_version(version_id, {"type": "print_ready", "fine": fine})
    if v["width_px"] < 2000:
        factor = round(min(4.0, max(1.05, 2250 / v["width_px"])), 3)
        v = studio.derive_version(v["id"], {"type": "upscale", "factor": factor})
        v = studio.derive_version(v["id"], {"type": "threshold", "level": 128})
    return v["id"]


@handler("generate_images")
def generate_job(studio, ctx, params) -> dict:
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from .ip_guard import find
    pid = ctx.job["project_id"]
    prov = get_provider(studio)
    spec, style = studio.spec(pid), studio.style_guide(pid)
    scenes = {s["id"]: s for s in studio.scenes(pid)}
    st = params["settings"]
    size = st.get("size") or default_settings(prov)["size"]
    quality = st.get("quality") or "high"
    per = params.get("per_image_estimate")
    live = prov.status().get("live", False)
    model = prov.status().get("model")
    created, failed, unknown = [], [], []
    lock = threading.Lock()
    stop = threading.Event()
    replace = set(params.get("replace_page_ids") or [])
    char_ref_ids = [r for c in style.get("characters", []) for r in c.get("reference_asset_ids", [])]
    refs_base: list[bytes] = []
    if prov.capabilities().get("reference_images"):
        for aid in char_ref_ids[:3]:
            a = studio.asset(aid)
            if a["rights_declaration"] != "unknown":
                refs_base.append(_png_reference(studio, a["current_version_id"]))
    sample_vid = _style_reference(studio, pid) if st.get("match_sample", True) and prov.capabilities().get("reference_images") else None
    sample_bytes = _png_reference(studio, sample_vid) if sample_vid else None

    def reserve(sid, prompt, nrefs, kind):
        """Atomically check the budget and record the request as 'submitting' before any billable call."""
        with lock:
            b = budget(studio, pid)
            if per and b["spending_limit"] is not None and Decimal(b["estimated_spent"]) + Decimal(per) > Decimal(b["spending_limit"]):
                stop.set()
                return None
            gid = new_id("gen")
            studio.db.x("""INSERT INTO generation_requests(id, project_id, job_id, scene_id, provider, model, prompt, params, state,
                           estimated_cost, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (gid, pid, ctx.job["id"], sid, prov.name, model, prompt,
                         jdump({"size": size, "quality": quality, "reference_count": nrefs, "kind": kind}), "submitting", per, now_iso(), now_iso()))
            return gid

    def record(gid, prompt, res, refs_used, name, kind):
        gen_meta = {"provider": prov.name, "model": model, "prompt": prompt, "revised_prompt": res.revised_prompt,
                    "reference_version_ids": refs_used, "seed": None, "generated_at": now_iso(), "size": size, "quality": quality,
                    "reported_usage": res.usage, "provider_request_id": res.provider_request_id, "live": live, "generation_request_id": gid}
        a = studio.import_asset(pid, f"{'MOCK-' if not live else ''}{name}.png", res.data, {
            "source_type": "ai_generated", "ai_involvement": "ai_generated", "creator": f"{prov.name} {model}",
            "rights_declaration": "unknown", "generation": gen_meta}, kind=kind)
        studio.db.x("UPDATE generation_requests SET state='succeeded', asset_id=?, reported_usage=?, updated_at=? WHERE id=?",
                    (a["id"], jdump(res.usage), now_iso(), gid))
        return a

    intro_by_scene = {r["scene_id"]: r for r in studio.intro_descriptions(pid) if r["scene_id"]}

    def one(sid):
        if stop.is_set() or ctx.cancelled():
            return
        scene = scenes.get(sid)
        if not scene:
            failed.append({"scene_id": sid, "error": "scene not found"})
            return
        intro = intro_by_scene.get(sid)
        refs = ([sample_bytes] if sample_bytes else []) + refs_base
        if intro:
            prompt = build_intro_prompt(spec, style, intro)
            page_size = intro_size(prov, intro.get("placement"))
        else:
            prompt = build_prompt(spec, style, scene, with_reference=bool(sample_bytes))
            page_size = size
        if find(prompt):
            failed.append({"scene_id": sid, "error": "Prompt mentions a protected character or brand; not sent to the provider."})
            return
        gid = reserve(sid, prompt, len(refs), "page")
        if not gid:
            return
        try:
            res = prov.generate(prompt, size=page_size, quality=quality, references=(refs or None) if not intro else (refs_base or None))
        except ProviderRequestFailed as e:
            studio.db.x("UPDATE generation_requests SET state='failed', error=?, estimated_cost=NULL, updated_at=? WHERE id=?", (str(e), now_iso(), gid))
            failed.append({"scene_id": sid, "error": str(e)})
            if "API key" in str(e) or "verified" in str(e) or "quota" in str(e) or "credit" in str(e):
                stop.set()  # the same account problem would fail every remaining page
            return
        except ProviderOutcomeUnknown as e:
            studio.db.x("UPDATE generation_requests SET state='unknown_outcome', error=?, updated_at=? WHERE id=?", (str(e), now_iso(), gid))
            unknown.append(str(e))
            stop.set()
            return
        raw = _save_raw(studio, gid, res.data)
        try:
            a = record(gid, prompt, res, [sample_vid] if sample_bytes and not intro else [],
                       f"{'intro-' + intro['label'][:30] if intro else 'page-' + (scene.get('subject') or 'scene')[:40]}", "artwork")
            version_id = (make_print_ready(studio, a["current_version_id"], fine=style.get("cleanup_mode") == "fine")
                          if params.get("auto_cleanup", True) else a["current_version_id"])
        except Exception as e:  # noqa: BLE001 – the image was paid for: keep it and report clearly
            studio.db.x("UPDATE generation_requests SET state='received_not_imported', error=?, updated_at=? WHERE id=?",
                        (f"{type(e).__name__}: {e} – original saved at {raw}", now_iso(), gid))
            failed.append({"scene_id": sid, "error": f"Image received but could not be added ({e}). It was saved at {raw}."})
            return
        with lock:
            created.append(a["id"])
            if intro:
                studio.place_intro_art(intro["page_id"], version_id, intro.get("placement") or "free_space")
                done = len(created) + len(failed)
                ctx.progress(done / max(1, len(ids)), f"{done} of {len(ids)} pages done")
                return
            for p in studio.pages(pid):
                if p["scene_id"] == sid and p["kind"] == "illustration" and not p["approved"] and \
                        (p["id"] in replace or not any(e["kind"] == "image" for e in p["elements"])):
                    studio.place_asset(p["id"], version_id)
                    break
            done = len(created) + len(failed)
            ctx.progress(done / max(1, len(ids)), f"{done} of {len(ids)} pages done")

    ids = list(params["scene_ids"])
    if ids:
        ctx.progress(0.0, f"Generating {len(ids)} page{'s' if len(ids) > 1 else ''} (up to 3 at a time)")
        with ThreadPoolExecutor(max_workers=min(3, len(ids))) as pool:
            list(pool.map(one, ids))
    cover_asset = None
    if params.get("cover") and not stop.is_set() and not ctx.cancelled():
        cover_size = "2400x2400" if size not in ("1024x1536", "1024x1024", "1536x1024") else "1024x1024"
        prompt = build_cover_prompt(spec, style, studio.cover(pid)["data"], "front")
        if not find(prompt):
            gid = reserve(None, prompt, 0, "cover")
            if gid:
                ctx.progress(0.95, "Generating cover art")
                try:
                    res = prov.generate(prompt, size=cover_size, quality=quality, references=None)
                    _save_raw(studio, gid, res.data)
                    cover_asset = record(gid, prompt, res, [], "cover-art", "cover_art")
                    studio.update_cover(pid, {"front_art_version_id": cover_asset["current_version_id"]})
                except ProviderRequestFailed as e:
                    studio.db.x("UPDATE generation_requests SET state='failed', error=?, estimated_cost=NULL, updated_at=? WHERE id=?", (str(e), now_iso(), gid))
                    failed.append({"scene_id": None, "error": f"cover: {e}"})
                except ProviderOutcomeUnknown as e:
                    studio.db.x("UPDATE generation_requests SET state='unknown_outcome', error=?, updated_at=? WHERE id=?", (str(e), now_iso(), gid))
                    unknown.append(str(e))
    if params.get("back_cover") and not stop.is_set() and not ctx.cancelled():
        prompt = build_cover_prompt(spec, style, studio.cover(pid)["data"], "back")
        if find(prompt):
            failed.append({"scene_id": None, "error": "back cover: the description mentions a protected character or brand"})
        else:
            gid = reserve(None, prompt, 0, "back_cover")
            if gid:
                ctx.progress(0.97, "Generating back-cover art")
                try:
                    res = prov.generate(prompt, size=back_cover_size(prov), quality=quality, references=None)
                    _save_raw(studio, gid, res.data)
                    back_asset = record(gid, prompt, res, [], "back-cover-art", "cover_art")
                    studio.update_cover(pid, {"back_art_version_id": back_asset["current_version_id"]})
                    created.append(back_asset["id"])
                except ProviderRequestFailed as e:
                    studio.db.x("UPDATE generation_requests SET state='failed', error=?, estimated_cost=NULL, updated_at=? WHERE id=?", (str(e), now_iso(), gid))
                    failed.append({"scene_id": None, "error": f"back cover: {e}"})
                except ProviderOutcomeUnknown as e:
                    studio.db.x("UPDATE generation_requests SET state='unknown_outcome', error=?, updated_at=? WHERE id=?", (str(e), now_iso(), gid))
                    unknown.append(str(e))
    if created and params.get("auto_cover"):
        cov = studio.cover(pid)
        if not cov["data"].get("front_art_version_id"):
            art = studio.derive_cover_art(studio.asset(created[0])["current_version_id"])
            studio.update_cover(pid, {"front_art_version_id": art["current_version_id"]})
    if unknown:
        e = ProviderOutcomeUnknown(unknown[0] + f" ({len(created)} page(s) were finished and saved.)")
        raise e
    if ctx.cancelled():
        from .jobs import JobCancelled
        raise JobCancelled()
    result = {"created_asset_ids": created, "failed": failed, "cover_asset_id": cover_asset["id"] if cover_asset else None}
    if stop.is_set() and not unknown and len(created) + len(failed) < len(ids):
        result["stopped"] = "Stopped early: spending limit reached or an account problem would affect every page."
    if failed and not created and not cover_asset:
        raise RuntimeError(failed[0]["error"])
    return result


def generation_requests(studio, pid: str) -> list[dict]:
    out = []
    for r in studio.db.q("SELECT * FROM generation_requests WHERE project_id=? ORDER BY created_at DESC", (pid,)):
        d = dict(r)
        d["params"] = jload(d["params"])
        d["reported_usage"] = jload(d["reported_usage"])
        out.append(d)
    return out


MAX_DESCRIPTION_WORDS = 10000
MAX_DESCRIPTION_CHARS = 90000
OPENAI_PROMPT_LIMIT = 32000      # OpenAI's documented maximum prompt length (characters)
PROMPT_SAFETY_MARGIN = 800


def word_count(text: str) -> int:
    return len((text or "").split())


def description_for_prompt(theme: str, budget: int, focus_terms: list[str]) -> tuple[str, bool]:
    """Return (text, excerpted). If the whole description fits, use it. Otherwise keep the opening overview
    and add the paragraphs most relevant to this page (mentioning its characters/subject/setting), in original order."""
    theme = (theme or "").strip()
    if len(theme) <= budget:
        return theme, False
    import re
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n", theme) if p.strip()]
    terms = {t.lower() for ft in focus_terms for t in re.findall(r"[A-Za-z][A-Za-z'-]{2,}", ft or "")}
    terms -= {"the", "and", "with", "for", "original", "friendly", "cartoon", "a", "an", "team's"}
    chosen, used = set(), 0
    overview_budget = budget // 4
    for i, p in enumerate(paras):  # opening overview
        if used + len(p) + 2 > overview_budget and chosen:
            break
        chosen.add(i)
        used += min(len(p), overview_budget) + 2
    scored = sorted(((sum(1 for t in terms if t in p.lower()), -i, i) for i, p in enumerate(paras) if i not in chosen), reverse=True)
    for score, _, i in scored:
        if score == 0:
            break
        if used + len(paras[i]) + 2 <= budget:
            chosen.add(i)
            used += len(paras[i]) + 2
    text = "\n".join(paras[i] for i in sorted(chosen))
    return text[:budget], True


def plan_from_description(studio, pid: str, description: str, count: int, preset: str | None = None) -> dict:
    """One step: store the description as the book theme, size the book, apply a style and draft scenes."""
    from .ip_guard import find
    description = (description or "").strip()
    if len(description) < 10:
        raise ValueError("Describe your book in at least a sentence (theme, audience, kind of characters).")
    hits = find(description)
    if hits:
        raise ValueError(f"“{hits[0]['matched']}” belongs to {hits[0]['owner']}. Describe original characters instead – "
                         "for example with the hero-team builder.")
    if not 1 <= int(count) <= 200:
        raise ValueError("Choose between 1 and 200 illustrations.")
    if word_count(description) > MAX_DESCRIPTION_WORDS or len(description) > MAX_DESCRIPTION_CHARS:
        raise ValueError(f"The description is {word_count(description):,} words; the limit is {MAX_DESCRIPTION_WORDS:,} words.")
    spec = studio.update_spec(pid, {"theme": description, "illustration_count": int(count)})
    illus = [p for p in studio.pages(pid) if p["kind"] == "illustration"]
    # remove surplus EMPTY, unapproved illustration pages so the book matches the requested count
    surplus = len(illus) - int(count)
    described = {r["page_id"] for r in studio.page_descriptions(pid) if r["description"]}
    for p in reversed(illus):
        if surplus <= 0:
            break
        if not p["approved"] and not p["elements"] and p["id"] not in described:
            studio.delete_page(p["id"])
            surplus -= 1
    studio.ensure_illustration_slots(pid)
    if preset:
        studio.apply_style_preset(pid, preset)
    scenes = studio.draft_plan(pid, int(count), replace=True)
    return {"spec": spec, "scenes": scenes, "assembly": studio.assembly(pid)}


def autobook_status(studio, pid: str) -> dict:
    fine_mode = studio.style_guide(pid).get("cleanup_mode") == "fine"
    pages = [p for p in studio.pages(pid) if p["kind"] == "illustration"]
    gen_assets = {a["id"]: a for a in studio.assets(pid) if (a.get("generation") or {}).get("provider")}
    approved_sample = any(a["review_status"] == "approved" for a in gen_assets.values())
    empty = [p for p in pages if not any(e["kind"] == "image" for e in p["elements"])]
    rows = []
    for p in pages:
        img = next((e for e in p["elements"] if e["kind"] == "image"), None)
        flags = []
        if img:
            try:
                an = studio.asset_analysis(img["asset_version_id"])
                if an["black_coverage"] > (0.45 if fine_mode else 0.30):
                    flags.append("heavy black areas")
                if an["tiny_regions"] > 60 and not fine_mode:
                    flags.append("many tiny spaces")
                if an["gray_fill_fraction"] > 0.03:
                    flags.append("gray shading")
            except Exception:  # noqa: BLE001
                flags.append("could not analyse")
        rows.append({"page_id": p["id"], "label": p["label"], "scene_id": p["scene_id"], "approved": p["approved"],
                     "version_id": img["asset_version_id"] if img else None, "check": flags})
    unimported = studio.db.q1("SELECT COUNT(*) AS n FROM generation_requests WHERE project_id=? AND state='received_not_imported'", (pid,))["n"]
    return {"pages": rows, "empty_scene_ids": [p["scene_id"] for p in empty if p["scene_id"]], "unimported": unimported,
            "generated_count": len(gen_assets), "approved_sample": approved_sample}
