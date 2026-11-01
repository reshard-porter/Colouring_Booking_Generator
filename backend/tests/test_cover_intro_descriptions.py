"""Front/back cover descriptions + back-cover art, and introductory-page descriptions + intro art placement."""
import io

import pytest

from cbs import generation, preflight
from cbs.geometry import Rect, element_rect
from cbs.providers.mock import MockProvider
from cbs.render import cover_layout, render_cover
from cbs.snapshot import build_snapshot
from cbs.units import in_to_pt
from cbs.verify import verify_cover


@pytest.fixture
def mock():
    m = MockProvider()
    generation.set_test_provider(m)
    yield m
    generation.set_test_provider(None)


def test_cover_descriptions_drive_prompts_and_back_art_is_laid_out_safely(studio, runner, mock, tmp_path):
    pid = studio.create_project("Covers", {"title": "Sea Pals", "author": "R. Porter"})
    studio.update_cover(pid, {"front_description": "A smiling octopus juggling seashells on a sunny beach.",
                              "back_description": "A row of crabs waving goodbye at sunset."})
    d = studio.cover(pid)["data"]
    front = generation.build_cover_prompt(studio.spec(pid), studio.style_guide(pid), d, "front")
    back = generation.build_cover_prompt(studio.spec(pid), studio.style_guide(pid), d, "back")
    assert "THE FRONT COVER MUST SHOW: A smiling octopus" in front and "crabs" not in front
    assert "THE BACK COVER MUST SHOW: A row of crabs" in back and "BACK cover" in back and "no text" in back
    # generate the back cover art (single image: no sample needed)
    generation.start_generation(studio, runner, pid, [], {}, True, back_cover=True)
    runner.run_one()
    assert mock.last["size"] == "1536x1024" and "crabs waving" in mock.last["prompt"]
    d = studio.cover(pid)["data"]
    assert d["back_art_version_id"]
    a = studio.asset(studio.version(d["back_art_version_id"])["asset_id"])
    assert a["kind"] == "cover_art" and a["ai_involvement"] == "ai_generated"
    snap = build_snapshot(studio, pid)
    L = cover_layout(snap)
    g = snap["cover"]["geometry"]
    assert L["back_art"] and not L["back_art"].intersects(L["barcode"]) and Rect(**g["back_safe"]).contains(L["back_art"])
    assert L["back_art"].y > L["back_copy_box"].y and L["thumbs"] == []
    rep = preflight.run(studio, snap)
    assert not any(f["code"] in ("barcode_overlap", "back_art_outside_safe") for f in rep["findings"])
    # the rendered PDF keeps the barcode box white
    out = tmp_path / "cover.pdf"
    render_cover(snap, studio.storage.read, out)
    bc = L["barcode"]
    v = verify_cover(out, g["full_width_pt"], g["full_height_pt"],
                     (in_to_pt(bc.x), in_to_pt(g["full_height_in"] - bc.y - bc.h), in_to_pt(bc.w), in_to_pt(bc.h)))
    assert v["ok"], v["errors"]
    # disclosure counts the back art as cover art
    from cbs.provenance import disclosure
    assert disclosure(snap)["images"]["cover"]["ai_generated"] >= 1
    with pytest.raises(ValueError):
        studio.update_cover(pid, {"back_description": "x" * 4001})


def test_intro_descriptions_generate_art_without_touching_text(studio, runner, mock):
    pid = studio.create_project("Intro", {"title": "Sea Pals", "illustration_count": 10})
    intros = studio.intro_descriptions(pid)
    assert [r["label"] for r in intros] == ["Title page", "This book belongs to", "Color test page", "Copyright & tips"]
    assert "This book belongs to" in intros[1]["page_text"]
    title_page = intros[0]
    before_text = [e for e in studio.page(title_page["page_id"])["elements"] if e["kind"] != "image"]
    r = studio.set_intro_description(title_page["page_id"], "A garland of seashells and a happy octopus.")
    assert r["scene_id"] and r["placement"] == "free_space"
    generation.start_generation(studio, runner, pid, [r["scene_id"]], {}, True, replace_page_ids=[title_page["page_id"]])
    runner.run_one()
    p = mock.last["prompt"]
    assert "Title page" in p and "DO NOT draw any words" in p and "garland of seashells" in p and mock.last["size"] == "1536x1024"
    page = studio.page(title_page["page_id"])
    texts = [e for e in page["elements"] if e["kind"] != "image"]
    assert [(e["kind"], e.get("text")) for e in texts] == [(e["kind"], e.get("text")) for e in before_text]  # text untouched
    img = [e for e in page["elements"] if e["kind"] == "image"]
    assert len(img) == 1
    v = studio.version(img[0]["asset_version_id"])
    art = element_rect(img[0], v)
    geo = studio.page_geometry_for(pid, page["id"])
    assert Rect(**geo["safe"]).contains(art)
    for t in texts:  # does not sit on top of the visible text lines
        if t["kind"] == "text" and t.get("text"):
            from cbs.render import wrap_text
            lines = wrap_text(t["text"], t.get("bold", False), float(t["size_pt"]), in_to_pt(float(t["w"])))
            text_rect = Rect(float(t["x"]), float(t["y"]), float(t["w"]), len(lines) * float(t["size_pt"]) * 1.25 / 72)
            assert not art.intersects(text_rect)
    # full-page frame behind the text: image first (drawn underneath), fills the safe area
    belongs = intros[1]
    r2 = studio.set_intro_description(belongs["page_id"], "A frame of starfish and waves.", "behind_text")
    generation.start_generation(studio, runner, pid, [r2["scene_id"]], {}, True, replace_page_ids=[belongs["page_id"]])
    runner.run_one()
    assert "FRAME around the edges" in mock.last["prompt"] and mock.last["size"] == "1024x1536"
    els = studio.page(belongs["page_id"])["elements"]
    assert els[0]["kind"] == "image" and any(e["kind"] == "text" for e in els[1:])
    # descriptions and placement survive re-planning, and the intro scene is not reused by an illustration page
    generation.plan_from_description(studio, pid, "Original sea animals at the beach", 10)
    rows = {r["label"]: r for r in studio.intro_descriptions(pid)}
    assert rows["This book belongs to"]["description"] == "A frame of starfish and waves." and rows["This book belongs to"]["placement"] == "behind_text"
    intro_scenes = {r["scene_id"] for r in studio.intro_descriptions(pid) if r["scene_id"]}
    assert not intro_scenes & {p["scene_id"] for p in studio.pages(pid) if p["kind"] == "illustration"}
    with pytest.raises(ValueError):
        studio.set_intro_description(intros[2]["page_id"], "x", "sideways")
    illus = [p for p in studio.pages(pid) if p["kind"] == "illustration"][0]
    with pytest.raises(ValueError):
        studio.set_intro_description(illus["id"], "nope")


def test_protected_names_in_cover_and_intro_descriptions(studio, runner, mock):
    pid = studio.create_project("IP", {"title": "IP"})
    studio.update_cover(pid, {"back_description": "Batman waving"})
    rep = preflight.run(studio, build_snapshot(studio, pid))
    assert any(f["code"] == "protected_name" and "back cover description" in f["message"] for f in rep["findings"])
    generation.start_generation(studio, runner, pid, [], {}, True, back_cover=True)
    runner.run_one()
    assert mock.calls == 0  # never sent to the provider


def test_api(settings, monkeypatch, mock):
    monkeypatch.setenv("CBS_SEED_SAMPLE", "0")
    from fastapi.testclient import TestClient
    from cbs.api import create_app
    H = {"x-cbs-client": "1"}
    app = create_app(settings)
    with TestClient(app) as c:
        pid = c.post("/api/projects", json={"name": "a", "spec": {"illustration_count": 10}}, headers=H).json()["project"]["id"]
        intros = c.get(f"/api/projects/{pid}/intro-descriptions").json()
        assert c.post(f"/api/pages/{intros[0]['page_id']}/generate-intro", json={}, headers=H).status_code == 400  # no description yet
        r = c.put(f"/api/pages/{intros[0]['page_id']}/intro-description", json={"description": "Shells", "placement": "behind_text"}, headers=H)
        assert r.json()["placement"] == "behind_text"
        est = c.post(f"/api/pages/{intros[0]['page_id']}/generate-intro", json={}, headers=H).json()
        assert est["count"] == 1
        assert c.post(f"/api/pages/{intros[0]['page_id']}/generate-intro", json={"confirm": True}, headers=H).status_code == 200
        app.state.runner.run_one()
        assert c.get(f"/api/projects/{pid}/intro-descriptions").json()[0]["version_id"]
        assert c.put(f"/api/projects/{pid}/cover", json={"front_description": "Octopus"}, headers=H).json()["data"]["front_description"] == "Octopus"
        assert c.post(f"/api/projects/{pid}/autobook/cover", json={"which": "sideways"}, headers=H).status_code == 400
        assert c.post(f"/api/projects/{pid}/autobook/cover", json={"which": "back", "confirm": True}, headers=H).status_code == 200
        app.state.runner.run_one()
        assert c.get(f"/api/projects/{pid}/cover").json()["data"]["back_art_version_id"]
