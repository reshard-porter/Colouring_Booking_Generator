"""Kids' style presets (ages 3–7) and how a preset meets an existing master style: keep, replace, combine, restore."""
import re

import pytest

from cbs import generation
from cbs.planning import load_presets

KIDS = ["big_bold_first", "cute_animal_friends", "classic_cartoon", "storybook_adventure", "vehicles_machines",
        "sticker_bubble", "crayon_doodle", "hidden_object_fun", "fairytale_magic", "chibi_cute"]
MASTER = 'Thick bold outlines for crayons. Include one hidden "Golden Gear" per story page.'


def test_every_preset_is_complete_and_kids_ones_are_crayon_friendly():
    from cbs.ip_guard import find
    presets = load_presets()["presets"]
    assert set(KIDS) <= set(presets) and len(presets) == 13
    for key, p in presets.items():
        for f in ("label", "ages", "description", "best_for", "prompt_style", "outline_weight", "detail_level", "coloring_spaces",
                  "background_density", "master_style"):
            assert p.get(f), (key, f)
        assert len(p["master_style"]) <= 3000 and not find(p["master_style"] + p["prompt_style"] + p["description"]), key
        if key in KIDS:
            n = [int(x) for x in re.findall(r"\d+", p["ages"])]
            assert n[0] <= 5 and n[1] <= 7, key
            ms = p["master_style"].lower()
            assert "no gray" in ms and "closed" in ms and "no shading" in ms, key
            assert p.get("cleanup_mode", "bold") == "bold", key


@pytest.mark.parametrize("key", KIDS)
def test_kids_preset_drives_prompt_without_master_style(studio, key):
    pid = studio.create_project("Kids", {"age_min": 4, "age_max": 7})
    sg = studio.apply_style_preset(pid, key)
    assert sg["preset"] == key and sg["master_style"] == "" and sg["cleanup_mode"] == "bold"
    scene = {"description": "A friendly crab building a sandcastle."}
    prompt = generation.build_prompt(studio.spec(pid), sg, scene)
    assert load_presets()["presets"][key]["prompt_style"] in prompt and "(ages 4–7)" in prompt
    studio.draft_plan(pid, 10, replace=True)  # the preset's subjects/activities plan cleanly
    assert len(studio.scenes(pid)) >= 10


def test_keep_replace_combine_and_restore(studio):
    pid = studio.create_project("Crew")
    studio.update_style_guide(pid, {"master_style": MASTER})
    kept = studio.apply_style_preset(pid, "storybook_adventure")  # default = keep
    assert kept["master_style"] == MASTER and kept["preset"] == "storybook_adventure"
    p = load_presets()["presets"]
    rep = studio.apply_style_preset(pid, "vehicles_machines", "replace")
    assert rep["master_style"] == p["vehicles_machines"]["master_style"] and rep["previous_master_style"] == MASTER
    # combining after a replace finds nothing of the owner's in the current text, so it is just the preset text
    comb = studio.apply_style_preset(pid, "storybook_adventure", "combine")
    assert comb["master_style"] == p["storybook_adventure"]["master_style"]
    studio.update_style_guide(pid, {"master_style": MASTER})
    comb = studio.apply_style_preset(pid, "vehicles_machines", "combine")
    assert comb["master_style"].startswith(p["vehicles_machines"]["master_style"]) and comb["master_style"].endswith("Also for this book: " + MASTER)
    # switching to another style keeps the owner's part only once
    comb2 = studio.apply_style_preset(pid, "big_bold_first", "combine")
    assert comb2["master_style"] == p["big_bold_first"]["master_style"] + "\n\nAlso for this book: " + MASTER
    # the page prompt ends with the combined text; the owner's hidden-object rule survives
    sc = {"description": "Barnaby drives the Ladder-Buggy."}
    assert generation.build_prompt(studio.spec(pid), comb2, sc).rstrip().endswith('one hidden "Golden Gear" per story page.')
    # restore (what the Restore button sends)
    back = studio.update_style_guide(pid, {"master_style": comb2["previous_master_style"], "previous_master_style": comb2["master_style"]})
    assert back["master_style"] == comb["master_style"]
    with pytest.raises(ValueError):
        studio.apply_style_preset(pid, "storybook_adventure", "merge")
    studio.update_style_guide(pid, {"master_style": "x" * 2900})
    with pytest.raises(ValueError, match="over 3000"):
        studio.apply_style_preset(pid, "storybook_adventure", "combine")


def test_adult_master_replaced_by_kids_style_switches_cleanup(studio):
    pid = studio.create_project("Switch")
    studio.apply_style_preset(pid, "adult_pen_ink")
    studio.update_style_guide(pid, {"master_style": "Intricate stippling.", "cleanup_mode": "fine"})
    sg = studio.apply_style_preset(pid, "cute_animal_friends", "replace")
    assert sg["cleanup_mode"] == "bold" and "fingertip" in sg["master_style"]
    sg = studio.apply_style_preset(pid, "adult_pen_ink", "keep")
    assert sg["cleanup_mode"] == "bold" and "fingertip" in sg["master_style"]  # keep leaves the owner's choices alone


def test_api_preset_master_choice(settings, monkeypatch):
    monkeypatch.setenv("CBS_SEED_SAMPLE", "0")
    from fastapi.testclient import TestClient
    from cbs.api import create_app
    H = {"x-cbs-client": "1"}
    app = create_app(settings)
    with TestClient(app) as c:
        pid = app.state.studio.create_project("Kids")
        c.put(f"/api/projects/{pid}/style", json={"master_style": MASTER}, headers=H)
        r = c.post(f"/api/projects/{pid}/style/preset", json={"key": "hidden_object_fun", "master": "combine"}, headers=H)
        assert r.status_code == 200 and "five to eight easy-to-spot objects" in r.json()["master_style"] and MASTER in r.json()["master_style"]
        bad = c.post(f"/api/projects/{pid}/style/preset", json={"key": "hidden_object_fun", "master": "nope"}, headers=H)
        assert bad.status_code == 400
        assert c.get("/api/style-presets").json()["presets"]["big_bold_first"]["ages"] == "3–5"
