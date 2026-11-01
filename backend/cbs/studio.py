"""Application service layer: all persistent operations go through `Studio`."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

from .config import Settings, PROFILE_DIR
from .db import Database, jdump, jload, new_id, now_iso
from .geometry import (Rect, UnsupportedConfiguration, cover_geometry, fit_element, page_geometry,
                       resolve_config)
from .imaging import (UploadRejected, apply_operation, open_flat, safe_display_name, to_png_bytes,
                      validate_image_bytes)
from .layout import assemble
from .storage import LocalFileStorage, sha256_bytes


MAX_PAGE_DESCRIPTION = 4000


class NotFound(KeyError):
    pass


class Conflict(ValueError):
    pass


SOURCE_TYPES = {"user_created", "licensed", "public_domain", "ai_generated", "ai_assisted", "demo_sample", "unknown"}
AI_INVOLVEMENT = {"none", "ai_generated", "ai_assisted", "unknown"}
RIGHTS = {"owner_declared", "licensed_with_evidence", "public_domain_declared", "unknown"}
REVIEW = {"unreviewed", "approved", "needs_changes", "rejected"}

DEFAULT_SPEC = {
    "title": "Cute Island Adventures",
    "subtitle": "A Coloring Book for Kids Ages 4–7",
    "author": "Your Name",
    "audience": "Children ages 4–7",
    "age_min": 4,
    "age_max": 7,
    "theme": "Original cartoon animals enjoying island activities",
    "difficulty": "Large enclosed shapes and bold outlines",
    "language": "English",
    "reading_direction": "ltr",
    "binding": "paperback",
    "trim": "8.5x11",
    "paper": "bw_white",
    "interior_bleed": False,
    "illustration_count": 40,
    "intro_pages": 4,
    "blank_backs": True,
    "cover_type": "color",
    "cover_finish": "matte",
    "marketplace": "Amazon.com",
    "currency": "USD",
    "safe_margin_in": 0.5,
    "characters": [],
}

DEFAULT_STYLE = {
    "preset": "classic_cartoon",
    "master_style": "",
    "previous_master_style": "",
    "cleanup_mode": "bold",
    "prompt_style": "classic friendly cartoon style, rounded shapes, thick clean outlines",
    "team": {},
    "characters": [
        {"name": "Tilly the Turtle", "appearance": "round dome shell with a big pentagon plate, wide smile",
         "proportions": "head about 1/3 of shell width", "reference_asset_ids": []},
    ],
    "outline_weight": "Bold, uniform outlines (about 1–1.5 mm printed)",
    "background_density": "Sparse – a few large background objects",
    "detail_level": "Low – suitable for ages 4–7",
    "coloring_spaces": "Mostly large spaces; avoid regions smaller than a fingertip",
    "avoid": ["gray shading", "solid black backgrounds", "tiny repeating patterns", "text inside illustrations",
              "photorealism", "copyrighted characters or brand logos"],
    "reference_images": [],
    "consistency_note": "Image generators cannot guarantee perfect character consistency or correct anatomy. "
                        "Review every image; recurring characters will vary between pages.",
}

DEFAULT_LISTING = {
    "title": "Cute Island Adventures",
    "subtitle": "A Coloring Book for Kids Ages 4–7",
    "author": "Your Name",
    "language": "English",
    "audience": "Children",
    "age_range": "4–7",
    "description": "Forty original cartoon animal scenes set on a sunny island: sandcastles, surfing, sailing and "
                   "beach picnics. Every illustration is printed on its own page with a blank back to reduce "
                   "marker bleed-through. Large shapes and bold outlines suit young colorists.",
    "keywords": ["coloring book for kids", "animal coloring book", "beach coloring pages", "toddler coloring",
                 "island animals", "preschool activity book", "summer coloring book"],
    "category_notes": "Research categories yourself in KDP's category picker. This app does not provide "
                      "category IDs or rankings.",
    "isbn_choice": "undecided",
    "isbn_notes": "",
    "text_ai_involvement": "none",
    "translation_ai_involvement": "not_applicable",
    "list_price": "9.99",
    "competitor_notes": "",
    "licensed_terms": [],
    "series_name": "",
    "series_number": "",
}

DEFAULT_COVER = {
    "background": "#8fd3f4",
    "accent": "#ffd166",
    "title_color": "#1d3557",
    "text_color": "#1d3557",
    "title": None, "subtitle": None, "author": None,
    "title_pt": 54, "subtitle_pt": 22, "author_pt": 20,
    "back_copy": "Grab your crayons and visit a sunny island full of friendly animals! Inside you will find "
                 "40 original illustrations with big, bold shapes made for little hands.\n\n"
                 "• 40 single-sided designs\n• Blank back on every page\n• 8.5 × 11 in pages",
    "back_copy_pt": 15,
    "front_art_version_id": None,
    "back_art_version_id": None,
    "front_description": "",
    "back_description": "",
    "art_scale": 1.0, "art_offset_x": 0.0, "art_offset_y": 0.0,
    "back_thumbnail_version_ids": [],
    "spine_text_enabled": False,
    "spine_text": None,
    "spine_text_pt": 10,
    "template_overlay_version_id": None,
    "template_opacity": 0.5,
}


PLACEMENTS = ("free_space", "behind_text", "full_page")


def _intro_elements(spec: dict, n: int, is_sample: bool) -> tuple[str, list[dict]]:
    T = lambda x, y, w, h, text, pt, bold=True, align="center": {
        "kind": "text", "x": x, "y": y, "w": w, "h": h, "text": text, "size_pt": pt, "bold": bold, "align": align}
    S = lambda shape, x, y, w, h, stroke=2.5: {"kind": "shape", "shape": shape, "x": x, "y": y, "w": w, "h": h, "stroke_pt": stroke}
    W = 8.5
    if n == 0:
        return "Title page", [T(0.75, 2.6, W - 1.5, 2.2, spec["title"], 44),
                              T(0.75, 5.0, W - 1.5, 1.0, spec.get("subtitle", ""), 20, False),
                              T(0.75, 9.2, W - 1.5, 0.6, spec.get("author", ""), 16, False)]
    if n == 1:
        return "This book belongs to", [T(0.75, 3.4, W - 1.5, 1.0, "This book belongs to:", 30),
                                        S("line", 1.5, 5.6, W - 3.0, 0, 3)]
    if n == 2:
        els = [T(0.75, 0.9, W - 1.5, 0.8, "Test your colors!", 28)]
        for r in range(5):
            for c in range(4):
                els.append(S("rect", 0.95 + c * 1.7, 2.1 + r * 1.65, 1.4, 1.3))
        return "Color test page", els
    if n == 3:
        lines = [f"Copyright © 2026 {spec.get('author', '')}. All rights reserved.", "",
                 "Coloring tips:",
                 "• Slip a sheet of paper behind the page you are coloring.",
                 "• Each picture is printed on one side only.",
                 "• There is no wrong way to color!"]
        if is_sample:
            lines += ["", "Sample project note: the illustrations in this demonstration project were drawn "
                          "procedurally by Coloring Book Studio as placeholders. Replace them with your own or "
                          "properly licensed artwork before publishing."]
        return "Copyright & tips", [T(0.9, 2.0, W - 1.8, 6.5, "\n".join(lines), 13, False, "left")]
    return f"Intro page {n + 1}", [T(0.75, 4.5, W - 1.5, 1.0, "", 20)]


class Studio:
    def __init__(self, settings: Settings):
        self.settings = settings
        settings.ensure_dirs()
        self.db = Database(settings.db_path)
        self.db.migrate()
        self.storage = LocalFileStorage(settings.files_dir)
        self._seed_pricing_profiles()
        self._analysis_cache: dict[str, dict] = {}

    # ------------------------------------------------------------------ pricing seed
    def _seed_pricing_profiles(self):
        data = json.loads((PROFILE_DIR / "pricing_amazon_com.json").read_text())
        if not self.db.q1("SELECT id FROM pricing_profiles WHERE id=?", (data["id"],)):
            self.db.x("INSERT INTO pricing_profiles(id, marketplace, version, checked_on, data, active) VALUES (?,?,?,?,?,1)",
                      (data["id"], data["marketplace"], data["version"], data["checked_on"], jdump(data)))

    def pricing_profiles(self) -> list[dict]:
        return [jload(r["data"]) | {"active": bool(r["active"])} for r in self.db.q("SELECT * FROM pricing_profiles ORDER BY checked_on DESC")]

    def active_pricing_profile(self, marketplace: str = "Amazon.com") -> dict:
        r = self.db.q1("SELECT data FROM pricing_profiles WHERE marketplace=? AND active=1 ORDER BY checked_on DESC", (marketplace,))
        if not r:
            raise NotFound(f"No pricing profile for {marketplace}")
        return jload(r["data"])

    def save_pricing_profile(self, data: dict) -> dict:
        required = {"id", "marketplace", "currency", "version", "checked_on", "printing_cost_bands", "royalty_tiers", "sources"}
        missing = required - set(data)
        if missing:
            raise ValueError(f"Pricing profile missing fields: {sorted(missing)}")
        with self.db.tx():
            self.db.x("UPDATE pricing_profiles SET active=0 WHERE marketplace=?", (data["marketplace"],))
            self.db.x("INSERT OR REPLACE INTO pricing_profiles(id, marketplace, version, checked_on, data, active) VALUES (?,?,?,?,?,1)",
                      (data["id"], data["marketplace"], data["version"], data["checked_on"], jdump(data)))
        return data

    # ------------------------------------------------------------------ projects
    def create_project(self, name: str | None = None, spec: dict | None = None, *, is_sample: bool = False,
                       create_pages: bool = True) -> str:
        sp = copy.deepcopy(DEFAULT_SPEC)
        sp.update(spec or {})
        resolve_config(sp)  # validate
        pid = new_id("prj")
        ts = now_iso()
        listing = copy.deepcopy(DEFAULT_LISTING)
        listing.update({"title": sp["title"], "subtitle": sp.get("subtitle", ""), "author": sp.get("author", ""),
                        "language": sp.get("language", "English"), "age_range": f"{sp.get('age_min', 4)}–{sp.get('age_max', 7)}"})
        if not is_sample:
            listing["description"] = ""
            listing["keywords"] = []
        with self.db.tx():
            self.db.x("INSERT INTO projects(id, name, created_at, updated_at, is_sample) VALUES (?,?,?,?,?)",
                      (pid, name or sp["title"], ts, ts, int(is_sample)))
            self.db.x("INSERT INTO book_specs VALUES (?,?,?)", (pid, jdump(sp), ts))
            style = copy.deepcopy(DEFAULT_STYLE)
            if not is_sample:
                style["characters"] = []
            self.db.x("INSERT INTO style_guides VALUES (?,?,?)", (pid, jdump(style), ts))
            self.db.x("INSERT INTO listings VALUES (?,?,?)", (pid, jdump(listing), ts))
            if create_pages:
                pos = 0
                for i in range(int(sp["intro_pages"])):
                    label, els = _intro_elements(sp, i, is_sample)
                    self._insert_page(pid, pos, "intro", label, els)
                    pos += 1
                for i in range(int(sp["illustration_count"])):
                    self._insert_page(pid, pos, "illustration", f"Illustration {i + 1}", [])
                    pos += 1
        cover = copy.deepcopy(DEFAULT_COVER)
        if not is_sample:
            cover["back_copy"] = ""  # the default text describes the sample book; new books start empty
        self.recalc_cover(pid, data=cover)
        return pid

    def _insert_page(self, pid, pos, kind, label, elements, scene_id=None) -> str:
        page_id = new_id("pg")
        self.db.x("INSERT INTO pages(id, project_id, position, kind, label, scene_id, updated_at) VALUES (?,?,?,?,?,?,?)",
                  (page_id, pid, pos, kind, label, scene_id, now_iso()))
        for z, el in enumerate(elements):
            self._insert_element(page_id, z, el)
        return page_id

    def _insert_element(self, page_id, z, el) -> str:
        eid = el.get("id") or new_id("el")
        data = {k: v for k, v in el.items() if k not in ("id", "kind", "z")}
        self.db.x("INSERT INTO page_elements(id, page_id, z, kind, data) VALUES (?,?,?,?,?)", (eid, page_id, z, el["kind"], jdump(data)))
        return eid

    def list_projects(self) -> list[dict]:
        out = []
        for r in self.db.q("SELECT * FROM projects ORDER BY updated_at DESC"):
            spec = self.spec(r["id"])
            pages = self.pages(r["id"])
            asm = assemble(pages, spec)
            out.append({"id": r["id"], "name": r["name"], "updated_at": r["updated_at"], "is_sample": bool(r["is_sample"]),
                        "title": spec["title"], "page_count": asm["page_count"], "illustrations": asm["illustration_count"],
                        "approved": sum(1 for p in pages if p["kind"] == "illustration" and p["approved"])})
        return out

    def project_row(self, pid) -> dict:
        r = self.db.q1("SELECT * FROM projects WHERE id=?", (pid,))
        if not r:
            raise NotFound(pid)
        return dict(r)

    def touch(self, pid, *, layout_changed: bool = False):
        if layout_changed:
            self.db.x("UPDATE projects SET updated_at=?, layout_revision=layout_revision+1 WHERE id=?", (now_iso(), pid))
        else:
            self.db.x("UPDATE projects SET updated_at=? WHERE id=?", (now_iso(), pid))

    def delete_project(self, pid):
        self.project_row(pid)
        self.db.x("DELETE FROM projects WHERE id=?", (pid,))

    def rename_project(self, pid, name: str):
        self.db.x("UPDATE projects SET name=?, updated_at=? WHERE id=?", (name.strip()[:200] or "Untitled", now_iso(), pid))

    # ------------------------------------------------------------------ spec / style / listing
    def spec(self, pid) -> dict:
        r = self.db.q1("SELECT data FROM book_specs WHERE project_id=?", (pid,))
        if not r:
            raise NotFound(pid)
        return jload(r["data"])

    def update_spec(self, pid, patch: dict) -> dict:
        sp = self.spec(pid)
        old = dict(sp)
        allowed = set(DEFAULT_SPEC)
        for k, v in patch.items():
            if k in allowed:
                sp[k] = v
        theme = str(sp.get("theme") or "")
        if len(theme.split()) > 10000 or len(theme) > 90000:
            raise ValueError("The book description can be at most 10,000 words.")
        try:
            resolve_config(sp)
        except UnsupportedConfiguration as e:
            raise ValueError(str(e))
        geometry_keys = {"trim", "paper", "interior_bleed", "safe_margin_in", "blank_backs", "binding"}
        changed = any(old.get(k) != sp.get(k) for k in geometry_keys)
        self.db.x("UPDATE book_specs SET data=?, updated_at=? WHERE project_id=?", (jdump(sp), now_iso(), pid))
        self.touch(pid, layout_changed=changed)
        return sp

    def ensure_illustration_slots(self, pid) -> int:
        """Add empty illustration pages until the plan's illustration_count is reached."""
        sp = self.spec(pid)
        pages = self.pages(pid)
        have = sum(1 for p in pages if p["kind"] == "illustration")
        add = int(sp["illustration_count"]) - have
        if add > 0:
            pos = max([p["position"] for p in pages], default=-1) + 1
            with self.db.tx():
                for i in range(add):
                    self._insert_page(pid, pos + i, "illustration", f"Illustration {have + i + 1}", [])
            self.touch(pid, layout_changed=True)
        return max(add, 0)

    def style_guide(self, pid) -> dict:
        return jload(self.db.q1("SELECT data FROM style_guides WHERE project_id=?", (pid,))["data"])

    def update_style_guide(self, pid, data: dict) -> dict:
        if len(str(data.get("master_style") or "")) > 3000:
            raise ValueError("The master style can be at most 3000 characters.")
        if data.get("cleanup_mode") not in (None, "bold", "fine"):
            raise ValueError("cleanup_mode must be 'bold' or 'fine'")
        sg = self.style_guide(pid)
        sg.update({k: v for k, v in data.items() if k in DEFAULT_STYLE})
        self.db.x("UPDATE style_guides SET data=?, updated_at=? WHERE project_id=?", (jdump(sg), now_iso(), pid))
        self.touch(pid)
        return sg

    COMBINE_MARK = "\n\nAlso for this book: "

    def apply_style_preset(self, pid, key: str, master: str | None = None) -> dict:
        """Apply a style preset. When the book has a master style (which decides the look), `master` says what to do with it:
        'keep' (default – the preset only changes planning and the built-in style fields), 'replace' (use the preset's style
        text) or 'combine' (the preset's style text first, then the owner's own text). The old text is kept for Restore."""
        from .planning import load_presets
        presets = load_presets()["presets"]
        if key not in presets:
            raise ValueError(f"Unknown style preset '{key}'")
        if master not in (None, "keep", "replace", "combine"):
            raise ValueError("master must be keep, replace or combine")
        p = presets[key]
        sg = self.style_guide(pid)
        base_avoid = [a for a in DEFAULT_STYLE["avoid"]]
        avoid = p["avoid"] if "avoid" in p else base_avoid + [a for a in p.get("avoid_extra", []) if a not in base_avoid]
        current = (sg.get("master_style") or "").strip()
        sg.update({"preset": key, "prompt_style": p["prompt_style"], "outline_weight": p["outline_weight"],
                   "background_density": p["background_density"], "detail_level": p["detail_level"],
                   "coloring_spaces": p["coloring_spaces"], "avoid": avoid})
        if master in ("replace", "combine") and p.get("master_style"):
            own = current.split(self.COMBINE_MARK, 1)[1] if self.COMBINE_MARK in current else current
            if any(own.strip() == (x.get("master_style") or "").strip() for x in presets.values()):
                own = ""  # the current text is just another preset's text – nothing of the owner's to keep
            text = p["master_style"] + (self.COMBINE_MARK + own if master == "combine" and own else "")
            if len(text) > 3000:
                raise ValueError("The preset's style text plus your own master style would be over 3000 characters. "
                                 "Shorten your master style or choose Replace.")
            if current and current != text:
                sg["previous_master_style"] = current
            sg["master_style"] = text
            sg["cleanup_mode"] = p.get("cleanup_mode", "bold")
        else:
            # a master style decides the look, so keep the owner's cleanup choice when one is set
            sg["cleanup_mode"] = sg.get("cleanup_mode", "bold") if current else p.get("cleanup_mode", "bold")
        self.db.x("UPDATE style_guides SET data=?, updated_at=? WHERE project_id=?", (jdump(sg), now_iso(), pid))
        self.touch(pid)
        return sg

    def ip_check(self, pid) -> list[dict]:
        from .ip_guard import scan_project
        from .snapshot import build_snapshot
        return scan_project(build_snapshot(self, pid))

    def listing(self, pid) -> dict:
        return jload(self.db.q1("SELECT data FROM listings WHERE project_id=?", (pid,))["data"])

    def update_listing(self, pid, data: dict) -> dict:
        ls = self.listing(pid)
        ls.update({k: v for k, v in data.items() if k in DEFAULT_LISTING})
        self.db.x("UPDATE listings SET data=?, updated_at=? WHERE project_id=?", (jdump(ls), now_iso(), pid))
        self.touch(pid)
        return ls

    # ------------------------------------------------------------------ scenes
    def scenes(self, pid) -> list[dict]:
        return [{"id": r["id"], "position": r["position"], **jload(r["data"])}
                for r in self.db.q("SELECT * FROM scenes WHERE project_id=? ORDER BY position", (pid,))]

    def save_scene(self, pid, data: dict, scene_id: str | None = None) -> dict:
        fields = {k: str(data.get(k, ""))[:2000] for k in ("subject", "action", "setting", "composition", "complexity", "notes", "characters", "demo_design_key")}
        desc = str(data.get("description") or "")
        if len(desc) > MAX_PAGE_DESCRIPTION:
            raise ValueError(f"A page description can be at most {MAX_PAGE_DESCRIPTION} characters.")
        fields["description"] = desc
        if data.get("placement") in PLACEMENTS:
            fields["placement"] = data["placement"]
        ts = now_iso()
        if scene_id:
            self.db.x("UPDATE scenes SET data=?, updated_at=? WHERE id=? AND project_id=?", (jdump(fields), ts, scene_id, pid))
        else:
            scene_id = new_id("scn")
            pos = (self.db.q1("SELECT COALESCE(MAX(position),-1)+1 AS p FROM scenes WHERE project_id=?", (pid,))["p"])
            self.db.x("INSERT INTO scenes VALUES (?,?,?,?,?,?)", (scene_id, pid, pos, jdump(fields), ts, ts))
        self.touch(pid)
        return {"id": scene_id, **fields}

    def delete_scene(self, pid, scene_id):
        self.db.x("DELETE FROM scenes WHERE id=? AND project_id=?", (scene_id, pid))
        self.touch(pid)

    def draft_plan(self, pid, count: int | None = None, replace: bool = False) -> list[dict]:
        """Offline, rule-based plan draft (no AI). Varies subject, activity, setting and composition."""
        from .planning import draft_scenes
        sp = self.spec(pid)
        sg = self.style_guide(pid)
        n = int(count or sp["illustration_count"])
        kept: dict[str, str] = {}
        if replace:
            # page descriptions written by the owner survive re-planning
            by_scene = {sc["id"]: sc for sc in self.scenes(pid)}
            kept = {p["id"]: (p["kind"], by_scene[p["scene_id"]].get("description", ""), by_scene[p["scene_id"]].get("placement"))
                    for p in self.pages(pid) if p["scene_id"] in by_scene and by_scene[p["scene_id"]].get("description")}
            self.db.x("UPDATE pages SET scene_id=NULL WHERE project_id=?", (pid,))
            self.db.x("DELETE FROM scenes WHERE project_id=?", (pid,))
        drafts = draft_scenes(sp, sg, n)
        out = [self.save_scene(pid, d) for d in drafts]
        self.link_scenes_to_pages(pid)
        for page_id, (kind, d, placement) in kept.items():
            try:
                if kind == "intro":
                    self.set_intro_description(page_id, d, placement)
                else:
                    self.set_page_description(page_id, d)
            except NotFound:
                pass
        return out

    # ------------------------------------------------------------------ per-page descriptions
    def page_descriptions(self, pid) -> list[dict]:
        asm = assemble(self.pages(pid), self.spec(pid))
        nums = {e["page_id"]: e["number"] for e in asm["pages"] if e["page_id"]}
        scenes = {sc["id"]: sc for sc in self.scenes(pid)}
        out = []
        for i, p in enumerate([p for p in self.pages(pid) if p["kind"] == "illustration"]):
            sc = scenes.get(p["scene_id"]) or {}
            img = next((e for e in p["elements"] if e["kind"] == "image"), None)
            draft = ", ".join(x for x in (sc.get("subject"), sc.get("action"), sc.get("setting")) if x)
            out.append({"page_id": p["id"], "kind": "illustration", "illustration_number": i + 1, "page_number": nums.get(p["id"]), "label": p["label"],
                        "scene_id": p["scene_id"], "description": sc.get("description", ""), "draft_summary": draft,
                        "version_id": img["asset_version_id"] if img else None, "approved": p["approved"]})
        return out

    def intro_descriptions(self, pid) -> list[dict]:
        asm = assemble(self.pages(pid), self.spec(pid))
        nums = {e["page_id"]: e["number"] for e in asm["pages"] if e["page_id"]}
        scenes = {sc["id"]: sc for sc in self.scenes(pid)}
        out = []
        for p in [p for p in self.pages(pid) if p["kind"] == "intro"]:
            sc = scenes.get(p["scene_id"]) or {}
            img = next((e for e in p["elements"] if e["kind"] == "image"), None)
            texts = [e.get("text", "") for e in p["elements"] if e["kind"] == "text" and e.get("text")]
            out.append({"page_id": p["id"], "kind": "intro", "page_number": nums.get(p["id"]), "label": p["label"],
                        "scene_id": p["scene_id"], "description": sc.get("description", ""), "placement": sc.get("placement") or "free_space",
                        "page_text": " / ".join(t.split("\n")[0] for t in texts)[:160],
                        "version_id": img["asset_version_id"] if img else None})
        return out

    def set_intro_description(self, page_id, text: str, placement: str | None = None) -> dict:
        p = self.page(page_id)
        if p["kind"] != "intro":
            raise ValueError("Not an introductory page.")
        if placement is not None and placement not in PLACEMENTS:
            raise ValueError("placement must be free_space, behind_text or full_page")
        text = (text or "").strip()
        if len(text) > MAX_PAGE_DESCRIPTION:
            raise ValueError(f"A page description can be at most {MAX_PAGE_DESCRIPTION} characters.")
        sc = next((x for x in self.scenes(p["project_id"]) if x["id"] == p["scene_id"]), None) if p["scene_id"] else None
        data = {k: v for k, v in (sc or {}).items() if k not in ("id", "position")}
        data["description"] = text
        if placement:
            data["placement"] = placement
        if sc:
            self.save_scene(p["project_id"], data, sc["id"])
        else:
            new = self.save_scene(p["project_id"], data)
            self.db.x("UPDATE pages SET scene_id=? WHERE id=?", (new["id"], page_id))
        return next(r for r in self.intro_descriptions(p["project_id"]) if r["page_id"] == page_id)

    def place_intro_art(self, page_id, version_id, placement: str = "free_space") -> dict:
        """Put generated art on an intro page WITHOUT touching its text: either in the largest free horizontal band of
        the safe area, or across the whole safe area behind the text."""
        p = self.page(page_id)
        v = self.version(version_id)
        geo = self.page_geometry_for(p["project_id"], page_id)
        safe = Rect(**geo["safe"])
        keep = [e for e in p["elements"] if e["kind"] != "image"]
        target = safe
        if placement not in ("behind_text", "full_page"):
            occupied = []
            for e in keep:
                if e["kind"] == "text" and not (e.get("text") or "").strip():
                    continue  # an empty text box takes no room
                y0, h = float(e["y"]), float(e.get("h") or 0)
                if e["kind"] == "text":
                    from .render import wrap_text
                    from .units import in_to_pt
                    lines = wrap_text(e.get("text", ""), e.get("bold", False), float(e.get("size_pt", 12)), in_to_pt(float(e["w"])))
                    h = min(h, len(lines) * float(e.get("size_pt", 12)) * 1.25 / 72) if lines else 0
                occupied.append((y0 - 0.15, y0 + max(h, 0.05) + 0.15))
            occupied.sort()
            bands, cur = [], safe.y
            for a, b in occupied:
                if a > cur:
                    bands.append((cur, min(a, safe.y2)))
                cur = max(cur, b)
            if cur < safe.y2:
                bands.append((cur, safe.y2))
            bands = [(a, b) for a, b in bands if b - a > 0.6]
            if bands:
                a, b = max(bands, key=lambda t: t[1] - t[0])
                target = Rect(safe.x, a, safe.w, b - a)
        el = fit_element({"kind": "image", "asset_version_id": version_id, "x": 0, "y": 0, "w": 1, "rotation": 0,
                          "crop": {"l": 0, "t": 0, "r": 0, "b": 0}}, v, target)
        return self.save_elements(page_id, [el] + keep, reason="place intro art")

    def set_page_description(self, page_id, text: str) -> dict:
        p = self.page(page_id)
        if p["kind"] != "illustration":
            raise ValueError("Descriptions are for illustration pages.")
        text = (text or "").strip()
        if len(text) > MAX_PAGE_DESCRIPTION:
            raise ValueError(f"A page description can be at most {MAX_PAGE_DESCRIPTION} characters.")
        if p["scene_id"]:
            sc = next((x for x in self.scenes(p["project_id"]) if x["id"] == p["scene_id"]), None)
            data = {k: v for k, v in (sc or {}).items() if k not in ("id", "position")}
            data["description"] = text
            self.save_scene(p["project_id"], data, p["scene_id"])
        else:
            sc = self.save_scene(p["project_id"], {"description": text})
            self.db.x("UPDATE pages SET scene_id=? WHERE id=?", (sc["id"], page_id))
        return next(r for r in self.page_descriptions(p["project_id"]) if r["page_id"] == page_id)

    def bulk_page_descriptions(self, pid, text: str, add_pages: bool = True) -> dict:
        """Split pasted text into one description per page (blank line between pages; 'Page 3:' prefixes are removed)."""
        import re
        chunks = [c.strip() for c in re.split(r"\n\s*\n", (text or "").replace("\r\n", "\n")) if c.strip()]
        chunks = [re.sub(r"^(page|illustration|pg\.?)\s*#?\d+\s*[:.)\-–]\s*", "", c, flags=re.I) for c in chunks]
        if not chunks:
            raise ValueError("No descriptions found. Put a blank line between pages.")
        if len(chunks) > 200:
            raise ValueError("At most 200 page descriptions at once.")
        rows = self.page_descriptions(pid)
        added = 0
        if add_pages and len(chunks) > len(rows):
            for _ in range(len(chunks) - len(rows)):
                self.add_page(pid, "illustration")
                added += 1
            sp = self.spec(pid)
            if sp["illustration_count"] < len(chunks):
                self.update_spec(pid, {"illustration_count": len(chunks)})
            rows = self.page_descriptions(pid)
        for row, chunk in zip(rows, chunks):
            self.set_page_description(row["page_id"], chunk)
        return {"filled": min(len(chunks), len(rows)), "pages_added": added, "ignored": max(0, len(chunks) - len(rows)),
                "rows": self.page_descriptions(pid)}

    def link_scenes_to_pages(self, pid):
        pages = self.pages(pid)
        used = {p["scene_id"] for p in pages if p["scene_id"]}
        free = iter([sc for sc in self.scenes(pid) if sc["id"] not in used])
        for p in [p for p in pages if p["kind"] == "illustration" and not p["scene_id"]]:
            sc = next(free, None)
            if sc is None:
                break
            self.db.x("UPDATE pages SET scene_id=? WHERE id=?", (sc["id"], p["id"]))

    def plan_warnings(self, pid) -> list[dict]:
        from .planning import scene_warnings
        return scene_warnings(self.scenes(pid))

    # ------------------------------------------------------------------ assets
    def import_asset(self, pid, filename: str, data: bytes, decl: dict | None = None, *, kind: str = "artwork") -> dict:
        self.project_row(pid)
        v = validate_image_bytes(data, max_bytes=self.settings.max_upload_bytes,
                                 max_pixels=self.settings.max_image_pixels, max_side=self.settings.max_image_side)
        decl = decl or {}
        source_type = decl.get("source_type", "unknown")
        ai = decl.get("ai_involvement", "unknown")
        rights = decl.get("rights_declaration", "unknown")
        if source_type not in SOURCE_TYPES or ai not in AI_INVOLVEMENT or rights not in RIGHTS:
            raise ValueError("Invalid provenance values")
        if source_type in ("ai_generated", "ai_assisted") and ai == "unknown":
            ai = source_type
        key, digest = self.storage.put(data, v.ext)
        aid, vid = new_id("ast"), new_id("ver")
        ts = now_iso()
        with self.db.tx():
            self.db.x("""INSERT INTO assets(id, project_id, kind, display_name, created_at, source_type, creator, license,
                        license_evidence, rights_declaration, ai_involvement, generation, review_status, is_demo, current_version_id)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (aid, pid, kind, safe_display_name(filename), ts, source_type, decl.get("creator"), decl.get("license"),
                       decl.get("license_evidence"), rights, ai, jdump(decl["generation"]) if decl.get("generation") else None,
                       "unreviewed", int(bool(decl.get("is_demo"))), vid))
            self.db.x("""INSERT INTO asset_versions(id, asset_id, parent_version_id, version_no, sha256, storage_key, mime, width_px,
                        height_px, dpi_meta_x, dpi_meta_y, operation, original_width_px, original_height_px, created_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (vid, aid, None, 1, digest, key, v.mime, v.width, v.height, v.dpi[0] if v.dpi else None,
                       v.dpi[1] if v.dpi else None, jdump({"type": "original_import"}), v.width, v.height, ts))
        self.touch(pid)
        return self.asset(aid)

    def asset(self, aid) -> dict:
        r = self.db.q1("SELECT * FROM assets WHERE id=?", (aid,))
        if not r:
            raise NotFound(aid)
        a = dict(r)
        a["generation"] = jload(a["generation"])
        a["is_demo"] = bool(a["is_demo"])
        a["versions"] = [self._version_dict(v) for v in self.db.q("SELECT * FROM asset_versions WHERE asset_id=? ORDER BY version_no", (aid,))]
        return a

    def _version_dict(self, r) -> dict:
        v = dict(r)
        v["operation"] = jload(v["operation"])
        v["upscaled"] = v["width_px"] > v["original_width_px"]
        return v

    def version(self, vid) -> dict:
        r = self.db.q1("SELECT v.*, a.project_id, a.ai_involvement, a.source_type, a.rights_declaration, a.review_status, "
                       "a.is_demo, a.display_name FROM asset_versions v JOIN assets a ON a.id=v.asset_id WHERE v.id=?", (vid,))
        if not r:
            raise NotFound(vid)
        return self._version_dict(r)

    def assets(self, pid, kind: str | None = None) -> list[dict]:
        rows = self.db.q("SELECT id FROM assets WHERE project_id=? " + ("AND kind=? " if kind else "") + "ORDER BY created_at",
                         (pid, kind) if kind else (pid,))
        return [self.asset(r["id"]) for r in rows]

    def update_asset_provenance(self, aid, data: dict) -> dict:
        a = self.asset(aid)
        fields = {}
        for k in ("source_type", "creator", "license", "license_evidence", "rights_declaration", "ai_involvement",
                  "review_status", "review_notes", "display_name"):
            if k in data:
                fields[k] = data[k]
        if "source_type" in fields and fields["source_type"] not in SOURCE_TYPES:
            raise ValueError("bad source_type")
        if "ai_involvement" in fields and fields["ai_involvement"] not in AI_INVOLVEMENT:
            raise ValueError("bad ai_involvement")
        if "rights_declaration" in fields and fields["rights_declaration"] not in RIGHTS:
            raise ValueError("bad rights_declaration")
        if "review_status" in fields and fields["review_status"] not in REVIEW:
            raise ValueError("bad review_status")
        # AI-created artwork stays AI-generated even after manual edits: never allow downgrading
        # a recorded generation to "none" while generation metadata exists.
        if a["generation"] and a["generation"].get("provider") and fields.get("ai_involvement") in ("none",):
            raise Conflict("This asset was recorded as generated by an AI provider; it remains AI-generated after editing.")
        if fields:
            sets = ", ".join(f"{k}=?" for k in fields)
            self.db.x(f"UPDATE assets SET {sets} WHERE id=?", (*fields.values(), aid))
            self.touch(a["project_id"])
        return self.asset(aid)

    def version_bytes(self, vid) -> bytes:
        return self.storage.read(self.version(vid)["storage_key"])

    def derive_version(self, vid, operation: dict) -> dict:
        """Apply a non-destructive edit to `vid`, producing a NEW immutable version of the same asset.
        Provenance lives on the asset, so it is inherited by every version automatically."""
        base = self.version(vid)
        im = open_flat(self.storage.read(base["storage_key"]))
        out = apply_operation(im, operation)
        data = to_png_bytes(out)
        key, digest = self.storage.put(data, "png")
        nv = new_id("ver")
        no = self.db.q1("SELECT MAX(version_no)+1 AS n FROM asset_versions WHERE asset_id=?", (base["asset_id"],))["n"]
        self.db.x("""INSERT INTO asset_versions(id, asset_id, parent_version_id, version_no, sha256, storage_key, mime, width_px,
                    height_px, dpi_meta_x, dpi_meta_y, operation, original_width_px, original_height_px, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (nv, base["asset_id"], vid, no, digest, key, "image/png", out.width, out.height, None, None,
                   jdump(operation), base["original_width_px"], base["original_height_px"], now_iso()))
        self.db.x("UPDATE assets SET current_version_id=? WHERE id=?", (nv, base["asset_id"]))
        self.touch(base["project_id"])
        return self.version(nv)

    def derive_cover_art(self, vid) -> dict:
        """Create a colored version of interior art as a separate cover-art asset that inherits provenance."""
        base = self.version(vid)
        src = self.asset(base["asset_id"])
        im = open_flat(self.storage.read(base["storage_key"]))
        colored = apply_operation(im, {"type": "colorize"})
        data = to_png_bytes(colored)
        a = self.import_asset(src["project_id"], f"cover-{src['display_name'].rsplit('.', 1)[0]}.png", data, {
            "source_type": src["source_type"], "creator": src["creator"], "license": src["license"],
            "license_evidence": src["license_evidence"], "rights_declaration": src["rights_declaration"],
            "ai_involvement": src["ai_involvement"], "is_demo": src["is_demo"],
            "generation": (src["generation"] or {}) | {"derived_from_asset": src["id"], "derived_from_version": vid,
                                                        "derivation": "automatic region color fill (colorize)"},
        }, kind="cover_art")
        return a

    def asset_analysis(self, vid) -> dict:
        from .imaging import analyze
        v = self.version(vid)
        if v["sha256"] not in self._analysis_cache:
            self._analysis_cache[v["sha256"]] = analyze(open_flat(self.storage.read(v["storage_key"])))
        return self._analysis_cache[v["sha256"]]

    # ------------------------------------------------------------------ pages
    def pages(self, pid) -> list[dict]:
        rows = self.db.q("SELECT * FROM pages WHERE project_id=? ORDER BY CASE kind WHEN 'intro' THEN 0 ELSE 1 END, position", (pid,))
        out = []
        for r in rows:
            p = dict(r)
            p["approved"] = bool(p["approved"])
            p["elements"] = self.elements(p["id"])
            out.append(p)
        return out

    def page(self, page_id) -> dict:
        r = self.db.q1("SELECT * FROM pages WHERE id=?", (page_id,))
        if not r:
            raise NotFound(page_id)
        p = dict(r)
        p["approved"] = bool(p["approved"])
        p["elements"] = self.elements(page_id)
        return p

    def elements(self, page_id) -> list[dict]:
        return [{"id": r["id"], "kind": r["kind"], "z": r["z"], **jload(r["data"])}
                for r in self.db.q("SELECT * FROM page_elements WHERE page_id=? ORDER BY z", (page_id,))]

    def _snapshot_page(self, page_id, reason):
        p = self.page(page_id)
        self.db.x("INSERT INTO page_history(id, page_id, created_at, reason, snapshot) VALUES (?,?,?,?,?)",
                  (new_id("ph"), page_id, now_iso(), reason, jdump(p["elements"])))
        # keep history bounded
        self.db.x("""DELETE FROM page_history WHERE page_id=? AND id NOT IN
                    (SELECT id FROM page_history WHERE page_id=? ORDER BY created_at DESC, rowid DESC LIMIT 100)""", (page_id, page_id))

    def _validate_elements(self, pid, elements: list[dict]):
        for el in elements:
            k = el.get("kind")
            if k not in ("image", "text", "shape"):
                raise ValueError(f"Unknown element kind {k}")
            for f in ("x", "y", "w"):
                float(el[f])
            if float(el["w"]) <= 0:
                raise ValueError("Element width must be positive")
            if k == "image":
                v = self.version(el["asset_version_id"])
                if v["project_id"] != pid:
                    raise ValueError("Asset belongs to another project")
                from .geometry import crop_px
                crop_px(v["width_px"], v["height_px"], el.get("crop"))
            if k == "text":
                if float(el.get("h", 0)) <= 0:
                    raise ValueError("Text box height must be positive")
                if not 4 <= float(el.get("size_pt", 12)) <= 200:
                    raise ValueError("Font size must be 4–200 pt")

    def save_elements(self, page_id, elements: list[dict], reason: str = "edit") -> dict:
        p = self.page(page_id)
        self._validate_elements(p["project_id"], elements)
        with self.db.tx():
            self._snapshot_page(page_id, reason)
            self.db.x("DELETE FROM page_elements WHERE page_id=?", (page_id,))
            for z, el in enumerate(elements):
                self._insert_element(page_id, z, el)
            # content changed -> approval must be renewed
            self.db.x("UPDATE pages SET updated_at=?, approved=0, approved_at=NULL WHERE id=?", (now_iso(), page_id))
        self.touch(p["project_id"])
        return self.page(page_id)

    def page_history(self, page_id) -> list[dict]:
        return [{"id": r["id"], "created_at": r["created_at"], "reason": r["reason"], "element_count": len(jload(r["snapshot"]))}
                for r in self.db.q("SELECT * FROM page_history WHERE page_id=? ORDER BY created_at DESC, rowid DESC", (page_id,))]

    def restore_page_history(self, page_id, history_id) -> dict:
        r = self.db.q1("SELECT snapshot FROM page_history WHERE id=? AND page_id=?", (history_id, page_id))
        if not r:
            raise NotFound(history_id)
        els = jload(r["snapshot"])
        return self.save_elements(page_id, els, reason="restore")

    def place_asset(self, page_id, version_id, fit: str = "safe") -> dict:
        p = self.page(page_id)
        v = self.version(version_id)
        cfg = resolve_config(self.spec(p["project_id"]))
        asm = assemble(self.pages(p["project_id"]), self.spec(p["project_id"]))
        num = next((x["number"] for x in asm["pages"] if x["page_id"] == page_id), 1)
        geo = page_geometry(cfg, num, max(asm["page_count"], 24))
        target = geo.safe if fit == "safe" else geo.trim
        el = fit_element({"kind": "image", "asset_version_id": version_id, "x": 0, "y": 0, "w": 1, "rotation": 0,
                          "crop": {"l": 0, "t": 0, "r": 0, "b": 0}}, v, target)
        others = [e for e in p["elements"] if e["kind"] != "image"]
        return self.save_elements(page_id, [el] + others, reason="place artwork")

    def add_page(self, pid, kind: str, after_page_id: str | None = None) -> dict:
        if kind not in ("intro", "illustration"):
            raise ValueError("kind must be intro or illustration")
        pages = [p for p in self.pages(pid) if p["kind"] == kind]
        n = len(pages)
        label, els = (_intro_elements(self.spec(pid), 99, False) if kind == "intro" else (f"Illustration {n + 1}", []))
        with self.db.tx():
            pos = max([p["position"] for p in pages], default=-1) + 1
            if after_page_id:
                after = self.page(after_page_id)
                pos = after["position"] + 1
                self.db.x("UPDATE pages SET position=position+1 WHERE project_id=? AND kind=? AND position>=?", (pid, kind, pos))
            new = self._insert_page(pid, pos, kind, label if kind == "intro" else f"Illustration {n + 1}", els)
        self.touch(pid, layout_changed=True)
        return self.page(new)

    def reorder_pages(self, pid, ordered_ids: list[str]):
        pages = self.pages(pid)
        ids = {p["id"] for p in pages}
        if set(ordered_ids) != ids or len(ordered_ids) != len(ids):
            raise ValueError("Reorder must include every content page exactly once")
        kinds = {p["id"]: p["kind"] for p in pages}
        with self.db.tx():
            for i, page_id in enumerate(ordered_ids):
                self.db.x("UPDATE pages SET position=? WHERE id=?", (i, page_id))
        self.touch(pid, layout_changed=True)
        # Intro pages always precede illustrations; report normalisation if the request mixed them
        mixed = any(kinds[a] == "illustration" and kinds[b] == "intro" for a, b in zip(ordered_ids, ordered_ids[1:]))
        return {"normalized": mixed}

    def duplicate_page(self, page_id) -> dict:
        p = self.page(page_id)
        with self.db.tx():
            self.db.x("UPDATE pages SET position=position+1 WHERE project_id=? AND kind=? AND position>?",
                      (p["project_id"], p["kind"], p["position"]))
            els = [{k: v for k, v in e.items() if k != "id"} for e in p["elements"]]
            new = self._insert_page(p["project_id"], p["position"] + 1, p["kind"], f"{p['label']} (copy)", els, p["scene_id"])
        self.touch(p["project_id"], layout_changed=True)
        return self.page(new)

    def delete_page(self, page_id):
        p = self.page(page_id)
        self.db.x("DELETE FROM pages WHERE id=?", (page_id,))
        self.touch(p["project_id"], layout_changed=True)

    def set_page_approval(self, page_id, approved: bool, note: str | None = None) -> dict:
        p = self.page(page_id)
        self.db.x("UPDATE pages SET approved=?, approved_at=?, approval_note=? WHERE id=?",
                  (int(approved), now_iso() if approved else None, note, page_id))
        self.touch(p["project_id"])
        return self.page(page_id)

    def update_page_meta(self, page_id, data: dict) -> dict:
        p = self.page(page_id)
        if "label" in data:
            self.db.x("UPDATE pages SET label=? WHERE id=?", (str(data["label"])[:120], page_id))
        if "scene_id" in data:
            self.db.x("UPDATE pages SET scene_id=? WHERE id=?", (data["scene_id"], page_id))
        self.touch(p["project_id"])
        return self.page(page_id)

    def assembly(self, pid) -> dict:
        sp = self.spec(pid)
        asm = assemble(self.pages(pid), sp)
        cfg = resolve_config(sp)
        asm["geometry"] = {}
        if asm["page_count"] >= 24:
            for kind_side in (1, 2):
                if kind_side <= asm["page_count"]:
                    asm["geometry"]["recto" if kind_side == 1 else "verso"] = page_geometry(cfg, kind_side, asm["page_count"]).d()
        else:
            asm["geometry"] = {"recto": page_geometry(cfg, 1, 24).d(), "verso": page_geometry(cfg, 2, 24).d(),
                               "note": "Fewer than 24 pages: margins shown for the 24-page minimum."}
        return asm

    def page_geometry_for(self, pid, page_id) -> dict:
        asm = assemble(self.pages(pid), self.spec(pid))
        num = next((x["number"] for x in asm["pages"] if x["page_id"] == page_id), None)
        if num is None:
            raise NotFound(page_id)
        cfg = resolve_config(self.spec(pid))
        return page_geometry(cfg, num, max(asm["page_count"], 24)).d()

    # ------------------------------------------------------------------ cover
    def cover(self, pid) -> dict:
        r = self.db.q1("SELECT * FROM cover_layouts WHERE project_id=?", (pid,))
        if not r:
            raise NotFound(pid)
        sp = self.spec(pid)
        asm = assemble(self.pages(pid), sp)
        cfg = resolve_config(sp)
        geo_stored = jload(r["geometry"])
        stale_reasons = []
        if r["basis_page_count"] != asm["page_count"]:
            stale_reasons.append(f"Interior page count changed from {r['basis_page_count']} to {asm['page_count']}.")
        if geo_stored.get("paper") != cfg.paper_key or abs(geo_stored.get("full_height_in", 0) - (cfg.trim_h + 0.25)) > 1e-6:
            stale_reasons.append("Trim size or paper changed since the cover was calculated.")
        return {"data": jload(r["data"]), "geometry": geo_stored, "basis_page_count": r["basis_page_count"],
                "stale": bool(stale_reasons), "stale_reasons": stale_reasons, "current_page_count": asm["page_count"],
                "updated_at": r["updated_at"]}

    def recalc_cover(self, pid, data: dict | None = None) -> dict:
        sp = self.spec(pid)
        asm = assemble(self.pages(pid), sp)
        cfg = resolve_config(sp)
        existing = self.db.q1("SELECT data FROM cover_layouts WHERE project_id=?", (pid,))
        cur = jload(existing["data"]) if existing else copy.deepcopy(DEFAULT_COVER)
        if data:
            cur.update({k: v for k, v in data.items() if k in DEFAULT_COVER})
        geo = cover_geometry(cfg, max(asm["page_count"], 24), float(cur.get("spine_text_pt") or 10))
        if cur.get("spine_text_enabled") and not geo["spine_text"]["eligible"]:
            cur["spine_text_enabled"] = False
        prow = self.project_row(pid)
        self.db.x("""INSERT INTO cover_layouts(project_id, data, geometry, basis_layout_revision, basis_page_count, updated_at)
                    VALUES (?,?,?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET data=excluded.data, geometry=excluded.geometry,
                    basis_layout_revision=excluded.basis_layout_revision, basis_page_count=excluded.basis_page_count,
                    updated_at=excluded.updated_at""",
                  (pid, jdump(cur), jdump(geo), prow["layout_revision"], asm["page_count"], now_iso()))
        self.touch(pid)
        return self.cover(pid)

    def update_cover(self, pid, data: dict) -> dict:
        if data.get("spine_text_enabled"):
            c = self.cover(pid)
            if not c["geometry"]["spine_text"]["eligible"]:
                raise Conflict("Spine text is not available: " + " ".join(c["geometry"]["spine_text"]["reasons"]))
        for key in ("front_description", "back_description"):
            if len(str(data.get(key) or "")) > MAX_PAGE_DESCRIPTION:
                raise ValueError(f"A cover description can be at most {MAX_PAGE_DESCRIPTION} characters.")
        for key in ("front_art_version_id", "back_art_version_id", "template_overlay_version_id"):
            if data.get(key):
                if self.version(data[key])["project_id"] != pid:
                    raise ValueError("Asset belongs to another project")
        return self.recalc_cover(pid, data)

    # ------------------------------------------------------------------ approval / release
    def set_release_approval(self, pid, snapshot_sha: str | None, acknowledged_items: list[str]):
        self.db.x("UPDATE projects SET release_approval=? WHERE id=?",
                  (jdump({"snapshot_sha": snapshot_sha, "acknowledged": acknowledged_items, "at": now_iso()}) if snapshot_sha else None, pid))

    # ------------------------------------------------------------------ settings (non-secret)
    def get_setting(self, key, default=None):
        r = self.db.q1("SELECT value FROM settings WHERE key=?", (key,))
        return jload(r["value"]) if r else default

    def set_setting(self, key, value):
        self.db.x("INSERT INTO settings(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, jdump(value)))

    # ------------------------------------------------------------------ backup / portable project
    PORTABLE_TABLES = ["projects", "book_specs", "style_guides", "listings", "scenes", "assets", "asset_versions",
                       "pages", "page_elements", "cover_layouts"]

    def export_project_archive(self, pid) -> bytes:
        self.project_row(pid)
        rows: dict[str, list[dict]] = {}
        rows["projects"] = [dict(r) for r in self.db.q("SELECT * FROM projects WHERE id=?", (pid,))]
        for t in ("book_specs", "style_guides", "listings", "scenes", "assets", "pages", "cover_layouts"):
            rows[t] = [dict(r) for r in self.db.q(f"SELECT * FROM {t} WHERE project_id=?", (pid,))]
        rows["asset_versions"] = [dict(r) for r in self.db.q(
            "SELECT v.* FROM asset_versions v JOIN assets a ON a.id=v.asset_id WHERE a.project_id=? ORDER BY v.version_no", (pid,))]
        rows["page_elements"] = [dict(r) for r in self.db.q(
            "SELECT e.* FROM page_elements e JOIN pages p ON p.id=e.page_id WHERE p.project_id=?", (pid,))]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("cbs-project.json", json.dumps({"format": "coloring-book-studio-project", "format_version": 1,
                                                        "exported_at": now_iso(), "tables": rows}, indent=1))
            written = set()
            for v in rows["asset_versions"]:
                if v["storage_key"] in written:  # identical files are stored once
                    continue
                written.add(v["storage_key"])
                z.writestr(f"files/{v['storage_key']}", self.storage.read(v["storage_key"]))
        return buf.getvalue()

    def import_project_archive(self, data: bytes) -> str:
        """Import a portable project as a NEW project (new IDs), verifying every file hash."""
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            raise ValueError("Not a valid project archive")
        total = sum(i.file_size for i in z.infolist())
        if total > 4 * 1024 ** 3:
            raise ValueError("Archive too large")
        meta = json.loads(z.read("cbs-project.json"))
        if meta.get("format") != "coloring-book-studio-project":
            raise ValueError("Unrecognized archive format")
        t = meta["tables"]
        idmap: dict[str, str] = {}

        def m(old):
            if old is None:
                return None
            if old not in idmap:
                idmap[old] = new_id(old.split("_")[0])
            return idmap[old]

        for v in t["asset_versions"]:
            blob = z.read(f"files/{v['storage_key']}")
            if sha256_bytes(blob) != v["sha256"]:
                raise ValueError(f"File hash mismatch for asset version {v['id']}; archive is damaged")
            key, digest = self.storage.put(blob, v["storage_key"].rsplit(".", 1)[-1])
            v["storage_key"] = key
        with self.db.tx():
            for table in self.PORTABLE_TABLES:
                for row in t.get(table, []):
                    row = dict(row)
                    for col in ("id", "project_id", "asset_id", "parent_version_id", "page_id", "scene_id", "current_version_id"):
                        if col in row and row[col] is not None:
                            row[col] = m(row[col])
                    if table == "projects":
                        row["name"] = row["name"] + " (imported)"
                        row["release_approval"] = None
                        row["is_sample"] = 0
                    if table in ("page_elements", "cover_layouts"):
                        d = jload(row["data"])
                        for k in ("asset_version_id", "front_art_version_id", "back_art_version_id", "template_overlay_version_id"):
                            if d.get(k):
                                d[k] = m(d[k])
                        if "back_thumbnail_version_ids" in d:
                            d["back_thumbnail_version_ids"] = [m(x) for x in d["back_thumbnail_version_ids"]]
                        row["data"] = jdump(d)
                    cols = ",".join(row)
                    self.db.x(f"INSERT INTO {table}({cols}) VALUES ({','.join('?' * len(row))})", tuple(row.values()))
        return idmap[t["projects"][0]["id"]]

    def backup_now(self, pid) -> Path:
        data = self.export_project_archive(pid)
        name = f"{pid}-{now_iso().replace(':', '').replace('+0000', 'Z')}.cbsproj"
        p = self.settings.backups_dir / name
        p.write_bytes(data)
        backups = sorted(self.settings.backups_dir.glob(f"{pid}-*.cbsproj"))
        for old in backups[:-10]:
            old.unlink(missing_ok=True)
        return p
