"""Per-page descriptions: storage, prompts, re-planning, bulk paste, generation."""
import pytest

from cbs import generation, preflight
from cbs.providers.mock import MockProvider
from cbs.snapshot import build_snapshot


def test_page_description_drives_prompt_and_survives_replanning(studio):
    pid = studio.create_project("Desc", {"title": "Forest"})
    generation.plan_from_description(studio, pid, "Original woodland animals in a calm forest", 10)
    rows = studio.page_descriptions(pid)
    assert len(rows) == 10 and rows[0]["illustration_number"] == 1 and rows[0]["page_number"] == 5 and rows[0]["draft_summary"]
    d3 = "A hedgehog wearing a knitted scarf, sitting on a mossy log, reading a tiny book; ferns and toadstools around."
    studio.set_page_description(rows[2]["page_id"], d3)
    scene = next(sc for sc in studio.scenes(pid) if sc["id"] == studio.page(rows[2]["page_id"])["scene_id"])
    p = generation.build_prompt(studio.spec(pid), studio.style_guide(pid), scene)
    assert "THIS PAGE MUST SHOW: " + d3 in p
    assert scene["subject"] not in p  # the auto-drafted subject is not mixed in
    studio.update_style_guide(pid, {"master_style": "MASTER STYLE TEXT."})
    p = generation.build_prompt(studio.spec(pid), studio.style_guide(pid), scene)
    assert d3 in p and p.rstrip().endswith("MASTER STYLE TEXT.")
    # re-planning keeps the owner's descriptions, even with a smaller page count
    generation.plan_from_description(studio, pid, "Original woodland animals, now in winter", 3)
    rows2 = studio.page_descriptions(pid)
    assert any(r["description"] == d3 for r in rows2)
    # editing the scene card keeps the description too
    sc = next(x for x in studio.scenes(pid) if x.get("description") == d3)
    studio.save_scene(pid, {**{k: v for k, v in sc.items() if k not in ("id", "position")}, "subject": "Edited"}, sc["id"])
    assert any(r["description"] == d3 for r in studio.page_descriptions(pid))


def test_description_on_page_without_plan_and_limits(studio):
    pid = studio.create_project("Fresh", {"title": "Fresh", "illustration_count": 2})
    rows = studio.page_descriptions(pid)
    assert rows[0]["scene_id"] is None
    r = studio.set_page_description(rows[0]["page_id"], "A whale blowing bubble rings.")
    assert r["scene_id"] and r["description"] == "A whale blowing bubble rings."
    with pytest.raises(ValueError, match="4000"):
        studio.set_page_description(rows[1]["page_id"], "x" * 4001)
    intro = [p for p in studio.pages(pid) if p["kind"] == "intro"][0]
    with pytest.raises(ValueError):
        studio.set_page_description(intro["id"], "nope")


def test_bulk_paste_fills_in_order_and_adds_pages(studio):
    pid = studio.create_project("Bulk", {"title": "Bulk", "illustration_count": 2})
    text = "Page 1: A cat on a windowsill.\n\nPage 2) A dog with a kite.\n\n\nIllustration 3 - A bird bath with sparrows.\r\n\r\npg. 4: A rabbit garden."
    r = studio.bulk_page_descriptions(pid, text)
    assert r["filled"] == 4 and r["pages_added"] == 2
    assert [x["description"] for x in r["rows"]] == ["A cat on a windowsill.", "A dog with a kite.", "A bird bath with sparrows.", "A rabbit garden."]
    assert studio.spec(pid)["illustration_count"] == 4 and studio.assembly(pid)["illustration_count"] == 4
    with pytest.raises(ValueError):
        studio.bulk_page_descriptions(pid, "   \n\n  ")


def test_generation_uses_description_and_protected_names_flagged(studio, runner):
    pid = studio.create_project("Gen", {"title": "Gen", "illustration_count": 10})
    rows = studio.page_descriptions(pid)
    studio.set_page_description(rows[0]["page_id"], "A lighthouse keeper owl polishing the big lamp.")
    mock = MockProvider()
    generation.set_test_provider(mock)
    try:
        sid = studio.page(rows[0]["page_id"])["scene_id"]
        assert sid in generation.autobook_status(studio, pid)["empty_scene_ids"]
        generation.start_generation(studio, runner, pid, [sid], {}, confirm=True)
        runner.run_one()
        assert "lighthouse keeper owl" in mock.last["prompt"]
        assert studio.page_descriptions(pid)[0]["version_id"]
    finally:
        generation.set_test_provider(None)
    studio.set_page_description(rows[1]["page_id"], "Pikachu having a picnic")
    rep = preflight.run(studio, build_snapshot(studio, pid))
    assert any(f["code"] == "protected_name" and f["detail"]["term"] == "pikachu" for f in rep["findings"])


def test_api(settings, monkeypatch):
    monkeypatch.setenv("CBS_SEED_SAMPLE", "0")
    from fastapi.testclient import TestClient
    from cbs.api import create_app
    H = {"x-cbs-client": "1"}
    with TestClient(create_app(settings)) as c:
        pid = c.post("/api/projects", json={"name": "a", "spec": {"illustration_count": 2}}, headers=H).json()["project"]["id"]
        rows = c.get(f"/api/projects/{pid}/page-descriptions").json()
        r = c.put(f"/api/pages/{rows[1]['page_id']}/description", json={"description": "A frog band."}, headers=H)
        assert r.status_code == 200 and r.json()["description"] == "A frog band."
        r = c.post(f"/api/projects/{pid}/page-descriptions/bulk", json={"text": "One.\n\nTwo.\n\nThree."}, headers=H).json()
        assert r["filled"] == 3 and r["pages_added"] == 1
