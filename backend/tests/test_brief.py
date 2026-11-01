"""Book brief (.md): parse, apply (new + existing book), export round-trip, and 'Create everything'."""
import pytest

from cbs import generation
from cbs.brief import apply_brief, export_brief, parse_brief, spec_from_settings
from cbs.config import PROFILE_DIR
from cbs.providers.mock import MockProvider

TEMPLATE = (PROFILE_DIR / "book-brief-template.md").read_text()


def full_brief(n_pages=12):
    pages = "\n\n".join(f"### Page {i + 1}: Scene {i + 1}\nA hedgehog doing activity number {i + 1} in the night garden." for i in range(n_pages))
    return TEMPLATE.split("\n## Pages\n")[0] + "\n## Pages\n\n" + pages + "\n\n## Listing\n- Keywords: a, b, c\n### Description\nNice book.\n"


def test_template_parses_cleanly():
    r = parse_brief(TEMPLATE)
    s = r["summary"]
    assert r["warnings"] == []
    assert s["title"] == "Moonlit Garden Friends" and s["author"] == "Your Pen Name" and s["audience"] == "Adults"
    assert s["described_pages"] == 3 and s["intro_pages"] == 2 and s["characters"] == 2
    assert s["has_master_style"] and s["has_front_cover"] and s["has_back_cover"] and s["has_back_cover_text"] and s["has_listing"]
    d = r["data"]
    assert d["intro"][1]["placement"] == "behind_text" and d["intro"][0]["placement"] == "free_space"
    assert d["characters"][0]["role"] == "main character" and "glasses" in d["characters"][0]["appearance"]
    assert len(d["listing"]["keywords"]) == 7 and "BOOK BRIEF TEMPLATE" not in str(d)  # comments ignored


def test_forgiving_formats_and_warnings():
    md = """# Book: Tiny Dragons
## Book Setup
**Author:** Sam
* Ages: 4 to 7
- Trim size: 8.5 x 11
- Paper: Cream
- Favourite colour: blue
## Story
Small friendly original dragons.
## Illustrations
Page 1: A dragon baking bread.

Page 2) A dragon in a hammock.

Pikachu visits the dragons.
## Weird Section
x
"""
    r = parse_brief(md)
    d = r["data"]
    assert d["title"] == "Tiny Dragons" and d["settings"]["author"] == "Sam"
    assert [p["description"] for p in d["pages"]] == ["A dragon baking bread.", "A dragon in a hammock.", "Pikachu visits the dragons."]
    spec, w = spec_from_settings(d)
    assert spec["age_min"] == 4 and spec["age_max"] == 7 and spec["trim"] == "8.5x11" and spec["paper"] == "bw_cream"
    assert spec["theme"] == "Small friendly original dragons." and spec["illustration_count"] == 3
    joined = " ".join(r["warnings"])
    assert "Weird Section" in joined and "Favourite colour" in joined and "Pikachu" in joined
    big = "# T\n## Pages\n### Page 1\n" + "x" * 4100
    r2 = parse_brief(big)
    assert len(r2["data"]["pages"][0]["description"]) == 4000 and "shortened" in " ".join(r2["warnings"])
    with pytest.raises(ValueError):
        parse_brief("x" * (2 * 1024 * 1024 + 10))


def test_apply_to_new_book_fills_everything(studio):
    parsed = parse_brief(full_brief(12))
    spec, _ = spec_from_settings(parsed["data"])
    pid = studio.create_project(spec["title"], {k: v for k, v in spec.items() if k != "theme"})
    res = apply_brief(studio, pid, parsed["data"])
    assert res["warnings"] == [] and res["assembly"]["page_count"] == 28  # 4 intro + 12×2
    sp, sg = studio.spec(pid), studio.style_guide(pid)
    assert sp["title"] == "Moonlit Garden Friends" and sp["audience"] == "Adults" and sp["age_min"] is None and "night garden" in sp["theme"]
    assert sg["preset"] == "adult_pen_ink" and sg["cleanup_mode"] == "fine" and sg["master_style"].startswith("Black-and-white adult")
    assert [c["name"] for c in sg["characters"]] == ["Juniper the Hedgehog", "Pip the Moth"]
    rows = studio.page_descriptions(pid)
    assert len(rows) == 12 and rows[4]["description"].startswith("A hedgehog doing activity number 5") and rows[4]["label"] == "5. Scene 5"
    intro = {r["label"]: r for r in studio.intro_descriptions(pid)}
    assert intro["This book belongs to"]["placement"] == "behind_text" and "vines" in intro["This book belongs to"]["description"]
    cd = studio.cover(pid)["data"]
    assert "full moon" in cd["front_description"] and "Pip the moth" in cd["back_description"] and cd["back_copy"].startswith("Slow down")
    ls = studio.listing(pid)
    assert ls["keywords"] == ["a", "b", "c"] and ls["description"] == "Nice book." and ls["list_price"] == "9.99" and ls["age_range"] == "Adults"
    title_texts = [e["text"] for e in studio.pages(pid)[0]["elements"] if e["kind"] == "text"]
    assert title_texts[0] == "Moonlit Garden Friends" and title_texts[2] == "Your Pen Name"
    # the generation prompt for a page uses its brief description + master style
    sc = next(x for x in studio.scenes(pid) if x["id"] == studio.page(rows[0]["page_id"])["scene_id"])
    p = generation.build_prompt(sp, sg, sc)
    assert "THIS PAGE MUST SHOW: A hedgehog doing activity number 1" in p and p.rstrip().endswith(sg["master_style"])


def test_apply_to_existing_book_keeps_art_and_round_trips(studio):
    from conftest import make_small_book
    pid = make_small_book(studio)  # 10 illustrated, approved pages
    before = [p["elements"][0]["asset_version_id"] for p in studio.pages(pid) if p["kind"] == "illustration"]
    res = apply_brief(studio, pid, parse_brief(full_brief(5))["data"])
    assert any("kept" in w for w in res["warnings"])  # pages with art are never deleted
    after = [p["elements"][0]["asset_version_id"] for p in studio.pages(pid) if p["kind"] == "illustration"]
    assert after == before
    assert [r["description"][:30] for r in studio.page_descriptions(pid)][:5] == ["A hedgehog doing activity numb"] * 5
    md = export_brief(studio, pid)
    again = parse_brief(md)
    assert again["warnings"] == [] and again["data"]["title"] == "Moonlit Garden Friends"
    assert again["data"]["master_style"] == studio.style_guide(pid)["master_style"]
    assert [p["description"] for p in again["data"]["pages"]][:5] == [r["description"] for r in studio.page_descriptions(pid)][:5]
    assert again["data"]["intro"][1]["placement"] == "behind_text"


def test_api_create_from_brief_and_everything(settings, monkeypatch):
    monkeypatch.setenv("CBS_SEED_SAMPLE", "0")
    from fastapi.testclient import TestClient
    from cbs.api import create_app
    H = {"x-cbs-client": "1"}
    mock = MockProvider()
    generation.set_test_provider(mock)
    app = create_app(settings)
    S, R = app.state.studio, app.state.runner
    try:
        with TestClient(app) as c:
            t = c.get("/api/brief/template")
            assert t.status_code == 200 and "## Pages" in t.text and "attachment" in t.headers["content-disposition"]
            files = {"file": ("brief.md", full_brief(10).encode(), "text/markdown")}
            prev = c.post("/api/brief/parse", files=files, headers=H).json()
            assert prev["summary"]["described_pages"] == 10
            assert c.post("/api/brief/parse", files={"file": ("x.md", b"\x00\x01binary", "text/plain")}, headers=H).status_code == 400
            r = c.post("/api/projects/from-brief", files={"file": ("brief.md", full_brief(10).encode(), "text/markdown")}, headers=H).json()
            pid = r["project_id"]
            assert S.assembly(pid)["page_count"] == 24
            # sample → approve → create everything (9 pages + 2 intro + front + back) in one job
            c.post(f"/api/projects/{pid}/autobook/generate", json={"mode": "sample", "confirm": True}, headers=H)
            R.run_one()
            st = c.get(f"/api/projects/{pid}/autobook/status").json()
            vid = next(p["version_id"] for p in st["pages"] if p["version_id"])
            c.patch(f"/api/assets/{S.version(vid)['asset_id']}", json={"review_status": "approved"}, headers=H)
            c.put("/api/ai/settings", json={"per_image_estimate": "0.10", "spending_limit": "5"}, headers=H)
            est = c.post(f"/api/projects/{pid}/autobook/generate", json={"mode": "everything"}, headers=H).json()
            assert est["allowed"] and est["breakdown"] == {"pages": 9, "intro": 2, "front_cover": True, "back_cover": True} and est["count"] == 13
            c.post(f"/api/projects/{pid}/autobook/generate", json={"mode": "everything", "confirm": True}, headers=H)
            R.run_one()
            assert mock.calls == 14
            st = c.get(f"/api/projects/{pid}/autobook/status").json()
            assert all(p["version_id"] for p in st["pages"])
            assert all(r["version_id"] for r in S.intro_descriptions(pid) if r["description"])
            cd = S.cover(pid)["data"]
            assert cd["front_art_version_id"] and cd["back_art_version_id"]
            assert S.asset(S.version(cd["front_art_version_id"])["asset_id"])["display_name"] == "MOCK-cover-art.png"
            again = c.post(f"/api/projects/{pid}/autobook/generate", json={"mode": "everything"}, headers=H)
            assert again.status_code == 400 and "already has artwork" in again.json()["detail"]
            md = c.get(f"/api/projects/{pid}/brief.md")
            assert md.status_code == 200 and "# Moonlit Garden Friends" in md.text
            # applying a brief to an existing book makes a backup first
            r2 = c.post(f"/api/projects/{pid}/brief", files={"file": ("b.md", full_brief(10).encode(), "text/markdown")}, headers=H)
            assert r2.status_code == 200 and list(settings.backups_dir.glob(f"{pid}-*.cbsproj"))
    finally:
        generation.set_test_provider(None)
