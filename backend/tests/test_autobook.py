"""'Create with AI' flow with the test-only mock provider: describe → plan → sample → approve → batch → regenerate."""
import pytest

from cbs import generation, preflight
from cbs.providers.mock import MockProvider
from cbs.snapshot import build_snapshot


@pytest.fixture
def mock_provider():
    m = MockProvider()
    generation.set_test_provider(m)
    yield m
    generation.set_test_provider(None)


def test_autobook_flow(settings, monkeypatch, mock_provider):
    monkeypatch.setenv("CBS_SEED_SAMPLE", "0")
    from fastapi.testclient import TestClient
    from cbs.api import create_app
    app = create_app(settings)
    S, R = app.state.studio, app.state.runner
    H = {"x-cbs-client": "1"}
    with TestClient(app) as c:
        pid = c.post("/api/projects", json={"name": "AI book", "spec": {"title": "Ocean Pals", "author": "Me"}}, headers=H).json()["project"]["id"]
        # protected names in the description are refused
        r = c.post(f"/api/projects/{pid}/autobook/plan", json={"description": "Pikachu and friends at the beach", "count": 6}, headers=H)
        assert r.status_code == 400 and "Pokémon" in r.json()["detail"]
        r = c.post(f"/api/projects/{pid}/autobook/plan", json={"description": "Cute original sea animals having beach adventures for kids", "count": 10, "preset": "chibi_cute"}, headers=H)
        assert r.status_code == 200, r.text
        assert r.json()["assembly"]["illustration_count"] == 10 and len(r.json()["scenes"]) == 10
        st = c.get(f"/api/projects/{pid}/autobook/status").json()
        assert len(st["empty_scene_ids"]) == 10 and not st["approved_sample"]
        # batch before an approved sample is refused
        est = c.post(f"/api/projects/{pid}/autobook/generate", json={"mode": "rest"}, headers=H).json()
        assert not est["allowed"]
        # sample: exactly one image, theme in the prompt, cleaned, placed, cover created
        c.post(f"/api/projects/{pid}/autobook/generate", json={"mode": "sample", "confirm": True}, headers=H)
        R.run_one()
        assert mock_provider.calls == 1
        req = generation.generation_requests(S, pid)[0]
        assert "BOOK DESCRIPTION:\nCute original sea animals" in req["prompt"] and "chibi" in req["prompt"].lower()
        assert "no gray tones" in req["prompt"] and "STYLE REFERENCE" not in req["prompt"]
        st = c.get(f"/api/projects/{pid}/autobook/status").json()
        filled = [p for p in st["pages"] if p["version_id"]]
        assert len(filled) == 1
        v = S.version(filled[0]["version_id"])
        assert v["ai_involvement"] == "ai_generated"
        chain = []
        cur = v
        while cur["parent_version_id"]:
            chain.append(cur["operation"]["type"])
            cur = S.version(cur["parent_version_id"])
        assert chain[-1] == "print_ready" and "upscale" in chain  # mock art is small → smooth-enlarged and flagged
        assert v["upscaled"] and v["original_width_px"] == 1024
        assert S.cover(pid)["data"]["front_art_version_id"]
        # approve sample, set budget, generate the rest
        c.patch(f"/api/assets/{v['asset_id']}", json={"review_status": "approved"}, headers=H)
        c.put("/api/ai/settings", json={"per_image_estimate": "0.10", "spending_limit": "2.00"}, headers=H)
        est = c.post(f"/api/projects/{pid}/autobook/generate", json={"mode": "rest"}, headers=H).json()
        assert est["allowed"] and est["count"] == 9 and est["estimated_cost"] == "0.90"
        c.post(f"/api/projects/{pid}/autobook/generate", json={"mode": "rest", "confirm": True}, headers=H)
        R.run_one()
        # every later page was generated with the approved sample as a style reference
        assert mock_provider.last["references"] == 1
        assert "STYLE REFERENCE" in generation.generation_requests(S, pid)[0]["prompt"]
        st = c.get(f"/api/projects/{pid}/autobook/status").json()
        assert all(p["version_id"] for p in st["pages"]) and mock_provider.calls == 10
        # approve one page; regenerate another; approved page refused
        a, b = st["pages"][0], st["pages"][1]
        c.post(f"/api/pages/{a['page_id']}/approve", json={"approved": True}, headers=H)
        assert c.post(f"/api/pages/{a['page_id']}/regenerate", json={"confirm": True}, headers=H).status_code == 400
        assert c.post(f"/api/pages/{b['page_id']}/regenerate", json={"confirm": True}, headers=H).status_code == 200
        R.run_one()
        st2 = c.get(f"/api/projects/{pid}/autobook/status").json()
        assert st2["pages"][1]["version_id"] != b["version_id"] and st2["pages"][0]["version_id"] == a["version_id"]
        # the generated book passes technical preflight (AI disclosure is a review item)
        rep = preflight.run(S, build_snapshot(S, pid))
        assert rep["counts"]["error"] == 0, [f["message"] for f in rep["findings"] if f["severity"] == "error"]
        assert any(f["code"] == "ai_disclosure" for f in rep["findings"])
        # quality checks are reported per page
        assert all("check" in p for p in st2["pages"])
        # AI cover art: one colored image, stored as cover art, set on the cover
        est = c.post(f"/api/projects/{pid}/autobook/cover", json={}, headers=H).json()
        assert est["count"] == 1
        c.post(f"/api/projects/{pid}/autobook/cover", json={"confirm": True}, headers=H)
        R.run_one()
        cover_assets = [a for a in S.assets(pid, "cover_art") if a["display_name"] == "MOCK-cover-art.png"]
        assert cover_assets and S.cover(pid)["data"]["front_art_version_id"] == cover_assets[0]["current_version_id"]
        assert "no text" in mock_provider.last["prompt"].lower()
        # spending limit stops further requests: 11 priced images × 0.10 = 1.10 spent (sample had no price yet)
        c.put("/api/ai/settings", json={"spending_limit": "1.15"}, headers=H)
        c.post(f"/api/pages/{st2['pages'][2]['page_id']}/approve", json={"approved": False}, headers=H)
        r = c.post(f"/api/pages/{st2['pages'][2]['page_id']}/regenerate", json={"confirm": True}, headers=H)
        assert r.status_code == 400 and "spending limit" in r.json()["detail"]


def test_long_description_kept_in_full(studio):
    pid = studio.create_project("Long", {"title": "Long"})
    desc = ("A gentle original dragon named Pip who loves gardening, with round wings, freckles and a tiny watering can. " * 40)[:3990]
    generation.plan_from_description(studio, pid, desc, 10)
    assert studio.spec(pid)["theme"] == desc  # nothing cut off
    scene = studio.scenes(pid)[0]
    p = generation.build_prompt(studio.spec(pid), studio.style_guide(pid), scene)
    assert desc in p and "BOOK DESCRIPTION:" in p


def test_ten_thousand_word_description(studio):
    from cbs.ip_guard import find
    pid = studio.create_project("Huge", {"title": "Huge"})
    studio.update_style_guide(pid, {"characters": [{"name": "Captain Thunderpaw", "role": "leader"}, {"name": "Doctor Gumdrop", "role": "inventor"}]})
    overview = "OVERVIEW: a cheerful book about two original heroes who help their seaside town.\n\n"
    filler = [f"Paragraph {i}: the town has bakeries, gardens and a little harbour with boats and gulls and lots of friendly neighbours." for i in range(495)]
    special = "Captain Thunderpaw has a striped cape with a smiling-sun emblem and big round goggles and loves rescuing kittens."
    paras = filler[:300] + [special] + filler[300:]
    desc = overview + "\n\n".join(paras)
    n = len(desc.split())
    assert 9000 < n <= 10000, n
    generation.plan_from_description(studio, pid, desc, 10)
    assert studio.spec(pid)["theme"] == desc  # the full 10,000-word description is stored
    scenes = studio.scenes(pid)
    s = next(x for x in scenes if x["subject"].startswith("Captain Thunderpaw"))
    p = generation.build_prompt(studio.spec(pid), studio.style_guide(pid), s)
    assert len(p) <= 32000                       # OpenAI's maximum prompt length
    assert "excerpt relevant to this page" in p
    assert "OVERVIEW: a cheerful book" in p      # opening overview always included
    assert special in p                          # paragraph about this page's character included
    assert not find(p)
    cover = generation.build_cover_prompt(studio.spec(pid), studio.style_guide(pid))
    assert len(cover) <= 32000 and "OVERVIEW" in cover
    with pytest.raises(ValueError, match="10,000 words"):
        generation.plan_from_description(studio, pid, desc + " word" * 1200, 10)
    with pytest.raises(ValueError, match="10,000 words"):
        studio.update_spec(pid, {"theme": desc + " word" * 1200})
