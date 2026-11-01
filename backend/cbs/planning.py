"""Offline book planning helpers (no AI). Drafts are deterministic suggestions the owner edits."""
from __future__ import annotations

import re
from collections import Counter

DEFAULT_SUBJECTS = ["turtle", "crab", "parrot", "monkey", "frog", "piglet", "bunny", "kitten", "toucan", "sea otter"]
ACTIVITIES = [
    ("building a sandcastle", "the sandy shore with a bucket and spade"),
    ("riding a surfboard", "a big rolling wave under the sun"),
    ("sailing a little boat", "calm sea with fluffy clouds"),
    ("enjoying an ice cream", "under a striped beach umbrella"),
    ("collecting seashells", "the beach at low tide"),
    ("flying a kite", "a breezy hilltop above the bay"),
    ("snorkeling with fish", "a shallow lagoon with big bubbles"),
    ("having a picnic", "a blanket under a palm tree"),
    ("playing with a beach ball", "the soft sand by the water"),
    ("napping in a hammock", "between two palm trees"),
    ("painting a sunset", "a wooden dock at evening"),
    ("splashing in a tide pool", "rocks with a friendly starfish"),
]
COMPOSITIONS = [
    "character large and centered, simple background",
    "character on the left, activity object on the right",
    "close-up of character with a few big props",
    "wide scene with horizon line and one large character",
    "two friends side by side",
]
COMPLEXITY = {
    "easy": "large enclosed shapes, bold outlines, minimal background",
    "medium": "medium shapes, a few background details",
}


def load_presets() -> dict:
    import json
    from .config import PROFILE_DIR
    return json.loads((PROFILE_DIR / "style_presets.json").read_text())


def _subjects(spec: dict, style: dict, preset: dict | None) -> list[str]:
    named = []
    for c in style.get("characters", []):
        if c.get("name"):
            role = f", the team's {c['role']}" if c.get("role") else ""
            named.append(f"{c['name']}{role}")
    named += [c for c in spec.get("characters", []) if isinstance(c, str) and c]
    if preset and preset.get("subjects"):
        return named + list(preset["subjects"]) if not named else named
    return named + [f"a friendly cartoon {a}" for a in DEFAULT_SUBJECTS]


def draft_scenes(spec: dict, style: dict, n: int) -> list[dict]:
    preset = load_presets()["presets"].get(style.get("preset") or "")
    subjects = _subjects(spec, style, preset)
    activities = [tuple(a) for a in (preset or {}).get("activities") or []] or ACTIVITIES
    compositions = (preset or {}).get("compositions") or COMPOSITIONS
    complexity = COMPLEXITY["easy"] if "large" in (spec.get("difficulty") or "").lower() else COMPLEXITY["medium"]
    if preset and preset.get("detail_level"):
        complexity = f"{preset['detail_level']}; {preset['coloring_spaces']}"
    team = style.get("team") or {}
    out = []
    used = set()
    i = 0
    # interleave so neighbouring pages differ in both subject and activity
    while len(out) < n:
        s_idx = i % len(subjects)
        a_idx = (i * 5 + i // len(subjects)) % len(activities)
        key = (s_idx, a_idx)
        i += 1
        if key in used and i < 10 * n:
            continue
        used.add(key)
        action, setting = activities[a_idx]
        if team.get("headquarters"):
            if "headquarters" in setting:
                setting = setting.replace("the team headquarters", team["headquarters"]).replace("team headquarters", team["headquarters"])
            elif "headquarters" in action:
                setting = team["headquarters"]
        out.append({
            "subject": subjects[s_idx][0].upper() + subjects[s_idx][1:],
            "action": action,
            "setting": setting,
            "composition": compositions[len(out) % len(compositions)],
            "complexity": complexity,
            "notes": "",
        })
    return out


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (s or "").lower()).strip()


def scene_warnings(scenes: list[dict]) -> list[dict]:
    warnings = []
    seen = Counter((_norm(s.get("subject")), _norm(s.get("action")), _norm(s.get("setting"))) for s in scenes)
    for key, count in seen.items():
        if count > 1 and any(key):
            ids = [s["id"] for s in scenes if (_norm(s.get("subject")), _norm(s.get("action")), _norm(s.get("setting"))) == key]
            warnings.append({"code": "repeated_scene", "scene_ids": ids,
                             "message": f"{count} scenes share the same subject, action and setting: “{key[1]}”. "
                                        "Recurring characters are fine; repeated scenes may disappoint buyers."})
    for a, b in zip(scenes, scenes[1:]):
        if _norm(a.get("action")) == _norm(b.get("action")) and _norm(a.get("action")):
            warnings.append({"code": "adjacent_same_activity", "scene_ids": [a["id"], b["id"]],
                             "message": f"Two neighbouring scenes use the same activity (“{a.get('action')}”). Consider varying them."})
    actions = Counter(_norm(s.get("action")) for s in scenes if s.get("action"))
    if scenes and actions and actions.most_common(1)[0][1] > max(3, len(scenes) // 4):
        act, c = actions.most_common(1)[0]
        warnings.append({"code": "low_variety", "scene_ids": [], "message": f"“{act}” is used in {c} of {len(scenes)} scenes."})
    return warnings
