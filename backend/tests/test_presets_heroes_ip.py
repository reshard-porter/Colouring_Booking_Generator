"""Style presets, original hero-team builder and the protected-name check."""
import pytest

from cbs import exporter, generation, preflight
from cbs.heroes import suggest_hero, suggest_team
from cbs.ip_guard import find
from cbs.providers.mock import MockProvider
from cbs.snapshot import build_snapshot

from conftest import make_small_book


@pytest.mark.parametrize("text,term", [
    ("Justice League Coloring Book", "justice league"), ("BATMAN", "batman"), ("spider-man", "spider man"),
    ("Spiderman", "spider man"), ("Iron  Man", "iron man"), ("the Flash", "the flash"), ("Pokémon", "pokémon"),
    ("Naruto fans", "naruto"), ("Demon-Slayer", "demon slayer"), ("X-Men", "x men"), ("Hello Kitty", "hello kitty"),
])
def test_protected_names_detected(text, term):
    assert term in [h["term"] for h in find(text)]


@pytest.mark.parametrize("text", ["flash cards for kids", "marvelous animals", "a one-piece swimsuit", "Captain Thunderpaw",
                                  "superb heroes", "ironing day", "The Sunny Patrol"])
def test_everyday_words_not_flagged(text):
    assert find(text) == []


def test_suggested_heroes_and_teams_are_clean():
    for seed in range(300):
        h, t = suggest_hero(seed), suggest_team(seed)
        assert not find(h["name"]) and not find(t["name"])
        assert h["powers"] and h["costume"] and h["emblem"]


def test_preset_and_hero_team_drive_the_plan(studio):
    pid = make_small_book(studio)
    sg = studio.apply_style_preset(pid, "superhero_comic")
    assert sg["preset"] == "superhero_comic" and "bold inking" in sg["prompt_style"]
    assert any("existing superhero costumes" in a for a in sg["avoid"])
    with pytest.raises(ValueError):
        studio.apply_style_preset(pid, "nope")
    studio.update_style_guide(pid, {
        "team": {"name": "The Sunny Patrol", "headquarters": "a treehouse fortress", "motto": "Together we shine!"},
        "characters": [{"name": "Captain Thunderpaw", "role": "leader", "powers": "talks to animals", "costume": "hooded cape", "emblem": "a smiling sun"},
                       {"name": "Doctor Gumdrop", "role": "inventor", "powers": "builds gadgets", "costume": "tool vest", "emblem": "a gear"}]})
    scenes = studio.draft_plan(pid, 8, replace=True)
    assert {s["subject"].split(",")[0] for s in scenes} == {"Captain Thunderpaw", "Doctor Gumdrop"}
    presets_actions = {"flying over the city", "lifting a giant boulder", "rescuing a kitten from a tree", "training at the team headquarters",
                       "stopping a runaway train", "helping clean up the park", "unveiling a new gadget", "posing for a team photo"}
    assert {s["action"] for s in scenes} <= presets_actions
    assert any("treehouse fortress" in s["setting"] for s in scenes if s["action"] == "training at the team headquarters") or \
        all(s["action"] != "training at the team headquarters" for s in scenes)
    prompt = generation.build_prompt(studio.spec(pid), studio.style_guide(pid), scenes[0])
    assert "Captain Thunderpaw" in prompt and "The Sunny Patrol" in prompt and "bold inking" in prompt
    assert "do not depict any existing copyrighted character" in prompt
    # anime preset gives anime subjects when no characters exist
    pid2 = make_small_book(studio)
    studio.update_style_guide(pid2, {"characters": []})
    studio.apply_style_preset(pid2, "anime_inspired")
    sc = studio.draft_plan(pid2, 5, replace=True)
    assert all("original" in s["subject"].lower() for s in sc)
    assert not any(find(s["subject"] + " " + s["action"]) for s in sc)


def test_protected_names_block_release_and_licensed_terms_downgrade(studio, runner):
    pid = make_small_book(studio)
    studio.update_listing(pid, {"keywords": ["justice league coloring book", "kids"]})
    studio.update_cover(pid, {"title": "Batman Adventures"})
    rep = preflight.run(studio, build_snapshot(studio, pid))
    pn = [f for f in rep["findings"] if f["code"] == "protected_name"]
    assert {f["detail"]["term"] for f in pn} >= {"justice league", "batman"}
    assert all(f["severity"] == "error" for f in pn) and rep["status"] == "blocked"
    j = exporter.request_export(studio, runner, pid, "release", acknowledged_review=True)
    runner.run_one()
    assert runner.get(j["id"])["status"] == "failed"
    # scenes/characters are warnings, not errors
    studio.update_listing(pid, {"keywords": ["kids"]})
    studio.update_cover(pid, {"title": None})
    studio.save_scene(pid, {"subject": "Goku", "action": "flying", "setting": "sky"})
    rep = preflight.run(studio, build_snapshot(studio, pid))
    pn = [f for f in rep["findings"] if f["code"] == "protected_name"]
    assert pn and all(f["severity"] == "warning" for f in pn)
    # a declared license with evidence turns a match into a human-review item
    studio.update_listing(pid, {"keywords": ["batman"], "licensed_terms": [{"term": "batman", "evidence": "License #42"}]})
    rep = preflight.run(studio, build_snapshot(studio, pid))
    assert any(f["code"] == "licensed_name" and f["severity"] == "review" for f in rep["findings"])
    assert not any(f["code"] == "protected_name" and f["detail"]["term"] == "batman" for f in rep["findings"])
    # license without evidence is not honoured
    studio.update_listing(pid, {"licensed_terms": [{"term": "batman", "evidence": ""}]})
    rep = preflight.run(studio, build_snapshot(studio, pid))
    assert any(f["code"] == "protected_name" and f["detail"]["term"] == "batman" and f["severity"] == "error" for f in rep["findings"])


def test_generation_refuses_protected_prompts(studio, runner):
    pid = make_small_book(studio)
    s = studio.save_scene(pid, {"subject": "Pikachu", "action": "waving", "setting": "a meadow"})
    mock = MockProvider()
    generation.set_test_provider(mock)
    try:
        est = generation.estimate(studio, pid, 1, {}, [s["id"]])
        assert not est["allowed"] and any("Pikachu" in p for p in est["problems"])
        with pytest.raises(ValueError, match="protected"):
            generation.start_generation(studio, runner, pid, [s["id"]], {}, confirm=True)
        assert mock.calls == 0
    finally:
        generation.set_test_provider(None)


def test_api_endpoints(settings, monkeypatch):
    monkeypatch.setenv("CBS_SEED_SAMPLE", "0")
    from fastapi.testclient import TestClient
    from cbs.api import create_app
    with TestClient(create_app(settings)) as c:
        H = {"x-cbs-client": "1"}
        assert set(c.get("/api/style-presets").json()["presets"]) >= {"anime_inspired", "superhero_comic", "chibi_cute", "classic_cartoon"}
        pid = c.post("/api/projects", json={"name": "t", "spec": {"illustration_count": 2}}, headers=H).json()["project"]["id"]
        assert c.post(f"/api/projects/{pid}/style/preset", json={"key": "anime_inspired"}, headers=H).json()["preset"] == "anime_inspired"
        first = c.post(f"/api/projects/{pid}/heroes/suggest", json={"kind": "hero", "seed": 1}, headers=H).json()["name"]
        again = c.post(f"/api/projects/{pid}/heroes/suggest", json={"kind": "hero", "seed": 1, "taken": [first]}, headers=H).json()["name"]
        assert first and again != first
        assert c.post(f"/api/projects/{pid}/heroes/suggest", json={"kind": "team", "seed": 1}, headers=H).json()["name"].startswith("The ")
        r = c.post("/api/ip-check", json={"text": "Wonder Woman and Sailor Moon"}, headers=H).json()
        assert {h["term"] for h in r["hits"]} == {"wonder woman", "sailor moon"}
        assert c.get(f"/api/projects/{pid}/ip-check").json()["hits"] == []
