"""Book briefs written in other layouts (e.g. by another AI chat): plain 'Heading:' lines, [Bracket] sections, one-line
'- Page N:' items, numbered character lists, and JSON briefs."""
import json

import pytest

from cbs import generation
from cbs.brief import apply_brief, export_brief, export_brief_json, parse_brief, spec_from_settings, template_json
from cbs.config import PROFILE_DIR

PLAIN = """# SYSTEM PROMPT: GEAR GANG BOOK GENERATOR

Book Metadata:
- Working Title: Gear Gang: Book 1
- Subtitle: The Windmill Fix: A Rescue Crew Coloring Book
- Author: Test Author
- Target Audience: Children ages 3–7 (Min: 3, Max: 7)
- Format: 3 Intro Pages, 12 Illustrations, 8.5 x 11 in Vertical Trim
- Drawing Difficulty: Large enclosed shapes and bold outlines

Master Visual Style Directive (Apply to all pages):
Children's coloring page, thick bold outlines. Hand-drawn cartoon style (inspired by Bluey and PAW Patrol). Include one hidden acorn per page.

Character & Vehicle Reference Sheet:
1. Moss (Hedgehog): Leader. Red scarf, tool belt. Drives the Leaf-Truck (wooden truck).
2. Fig (Owl): Sky-Scout. Round goggles.
Has a tiny satchel.

Page-by-Page Generation Prompts:

[Introductory Pages]
- Intro 1 (Badge): A shield badge with a blank "Junior Fixer" name banner.
- Intro 2 (Crew): Two portrait boxes showing Moss and Fig.
- Intro 3 (Swatches): Big splat shapes for testing crayons.

[Act I: The Wind Stops]
- Page 1: Moss and Fig having a picnic under the windmill.
- Page 2: The windmill sails stop turning.
- Page 3: Tug-of-War Day: Everyone pulls a rope.
- Page 4: A sign reads: closed for repairs.
- Page 5: Fig flies up to look.
- Page 6: Moss opens the toolbox.

[Act II: The Fix]
- Page 7: Moss tightens a bolt.
- Page 8: Fig holds the lantern.
- Page 9: The sails creak.
- Page 10: The sails spin again.
- Page 11: A party by the windmill.
- Page 12 (Cliffhanger): A mysterious map blows in through the window.
"""


def test_plain_heading_layout_is_read():
    r = parse_brief(PLAIN)
    d, s, w = r["data"], r["summary"], " ".join(r["warnings"])
    assert s["title"] == "Gear Gang: Book 1" and s["author"] == "Test Author" and s["audience"] == "Children"
    assert s["described_pages"] == 12 and s["intro_pages"] == 3 and s["characters"] == 2 and s["intro_exact"]
    assert s["acts"] == ["Act I: The Wind Stops", "Act II: The Fix"] and d["pages"][6]["act"] == "Act II: The Fix"
    assert d["pages"][11]["label"] == "Cliffhanger" and d["pages"][11]["description"].startswith("A mysterious map")
    assert d["pages"][2]["label"] == "Tug-of-War Day" and d["pages"][2]["description"] == "Everyone pulls a rope."
    assert d["pages"][3]["label"] == "" and d["pages"][3]["description"] == "A sign reads: closed for repairs."  # a sentence, not a label
    assert [i["label"] for i in d["intro"]] == ["Badge", "Crew", "Swatches"] and {i["placement"] for i in d["intro"]} == {"full_page"}
    moss, fig = d["characters"]
    assert moss["name"] == "Moss" and moss["role"] == "Leader" and moss["appearance"].startswith("Hedgehog. Red scarf")
    assert "satchel" in fig["appearance"]  # continuation line joins the character above
    # the brand reference is removed from the style; nothing else protected remains, so nothing is blocked
    assert "Bluey" not in d["master_style"] and "PAW" not in d["master_style"]
    assert d["master_style"].startswith("Children's coloring page") and "Hand-drawn cartoon style. Include one hidden acorn" in d["master_style"]
    assert "Removed “(inspired by Bluey and PAW Patrol)”" in w and "looks like a protected name" not in w
    assert "Gear Gang: Book 1 — The Windmill Fix" in d["book_description"] and "Act I: The Wind Stops" in d["book_description"]
    spec, sw = spec_from_settings(d)
    assert sw == [] and spec["age_min"] == 3 and spec["age_max"] == 7 and spec["trim"] == "8.5x11" and spec["illustration_count"] == 12


def test_plain_layout_applies_exact_intro_pages(studio):
    parsed = parse_brief(PLAIN)
    spec, _ = spec_from_settings(parsed["data"])
    pid = studio.create_project(spec["title"], {k: v for k, v in spec.items() if k != "theme"})
    res = apply_brief(studio, pid, parsed["data"])
    assert res["assembly"]["intro_count"] == 3 and res["assembly"]["page_count"] == 3 + 12 * 2 + 1  # +1 parity blank
    intro = studio.intro_descriptions(pid)
    assert [r["label"] for r in intro] == ["Badge", "Crew", "Swatches"] and all(r["placement"] == "full_page" for r in intro)
    assert all(not [e for e in studio.page(r["page_id"])["elements"] if e["kind"] == "text"] for r in intro)
    assert any("Removed default intro pages" in c for c in res["changes"]) and any("copyright" in x for x in res["warnings"])
    assert studio.spec(pid)["intro_pages"] == 3
    rows = studio.page_descriptions(pid)
    assert rows[0]["label"] == "1. Moss and Fig having a picnic under…" and rows[11]["label"] == "12. Cliffhanger"
    sg = studio.style_guide(pid)
    assert sg["cleanup_mode"] == "bold" and [c["name"] for c in sg["characters"]] == ["Moss", "Fig"]
    from cbs.preflight import run_and_store
    rep = run_and_store(studio, pid)
    codes = [f["code"] for f in rep.get("findings", rep.get("errors", []) + rep.get("warnings", []))]
    assert "intro_count_mismatch" not in codes and "protected_name" not in codes
    # full-page intro prompt: portrait, quoted words allowed, nothing about app text
    p = generation.build_intro_prompt(studio.spec(pid), sg, intro[0])
    assert "full-page, portrait-shaped" in p and "no words other than ones quoted" in p and "DO NOT draw any words" not in p
    assert "Junior Fixer" in p
    # re-importing the same brief changes nothing about the intro pages
    apply_brief(studio, pid, parse_brief(PLAIN)["data"])
    assert [r["page_id"] for r in studio.intro_descriptions(pid)] == [r["page_id"] for r in intro]
    # round trip: Markdown and JSON exports read back the same book
    again = parse_brief(export_brief(studio, pid))
    assert again["summary"]["intro_exact"] and [i["placement"] for i in again["data"]["intro"]] == ["full_page"] * 3
    assert [p["description"] for p in again["data"]["pages"]] == [r["description"] for r in rows]
    j = parse_brief(export_brief_json(studio, pid))
    assert j["summary"]["format"] == "json" and j["summary"]["described_pages"] == 12 and j["summary"]["intro_labels"] == ["Badge", "Crew", "Swatches"]


def test_full_page_intro_art_fills_safe_area(studio):
    from conftest import line_art_png
    parsed = parse_brief(PLAIN)
    spec, _ = spec_from_settings(parsed["data"])
    pid = studio.create_project(spec["title"], {k: v for k, v in spec.items() if k != "theme"})
    apply_brief(studio, pid, parsed["data"])
    r = studio.intro_descriptions(pid)[0]
    asset = studio.import_asset(pid, "badge.png", line_art_png(1200, 1600))
    studio.place_intro_art(r["page_id"], asset["current_version_id"], "full_page")
    img = next(e for e in studio.page(r["page_id"])["elements"] if e["kind"] == "image")
    safe = studio.page_geometry_for(pid, r["page_id"])["safe"]
    assert img["w"] > safe["w"] * 0.95  # 3:4 art across the whole safe area (a free-space band would be much smaller)


def test_json_brief():
    obj = {
        "title": "Ocean Pals",
        "settings": {"author": "Sam", "ages": "4-8", "trim": "8.5x11", "illustrations": 3},
        "master_style": "Bold outlines.",
        "characters": [{"name": "Kai", "role": "turtle", "appearance": "green shell"}],
        "intro_pages": [{"label": "Welcome", "placement": "full page picture", "description": "Bubbles."}],
        "pages": ["A turtle swims.", {"page": 2, "label": "Reef", "description": "A reef."}, {"page": 3, "prompt": "A whale."}],
        "front_cover": "Kai waving.",
        "listing": {"keywords": ["ocean", "turtle"], "description": "Fun."},
        "colour": "blue",
    }
    r = parse_brief(json.dumps(obj))
    d, s = r["data"], r["summary"]
    assert s["format"] == "json" and s["title"] == "Ocean Pals" and s["described_pages"] == 3 and s["characters"] == 1
    assert [p["description"] for p in d["pages"]] == ["A turtle swims.", "A reef.", "A whale."] and d["pages"][1]["label"] == "Reef"
    assert d["intro"][0]["placement"] == "full_page" and d["front_cover"] == "Kai waving." and d["listing"]["keywords"] == ["ocean", "turtle"]
    assert any("colour" in w for w in r["warnings"])
    spec, _ = spec_from_settings(d)
    assert spec["age_min"] == 4 and spec["age_max"] == 8 and spec["illustration_count"] == 3
    # ```json fences (as chat apps paste them) are fine; broken JSON gets a clear message
    assert parse_brief("```json\n" + json.dumps(obj) + "\n```")["summary"]["title"] == "Ocean Pals"
    with pytest.raises(ValueError, match="missing comma or quote"):
        parse_brief('{"title": "x" "pages": []}')


def test_json_template_matches_markdown_template():
    md = parse_brief((PROFILE_DIR / "book-brief-template.md").read_text())
    js = parse_brief(template_json())
    assert js["warnings"] == []
    for k in ("title", "author", "audience", "described_pages", "intro_pages", "characters", "has_master_style",
              "has_front_cover", "has_back_cover", "has_back_cover_text", "has_listing"):
        assert js["summary"][k] == md["summary"][k], k
    assert js["data"]["pages"] == md["data"]["pages"] and js["data"]["characters"] == md["data"]["characters"]


def test_order_gaps_and_mixed_forms():
    md = """## Pages
**Page 2:** Second.
Page 1 – First.
3. Third.
- Page 5: Fifth.
"""
    r = parse_brief(md)
    assert [p["description"] for p in r["data"]["pages"]] == ["First.", "Second.", "Third.", "Fifth."]
    w = " ".join(r["warnings"])
    assert "out of order" in w and "page(s) 4" in w


def test_template_still_reads_as_before():
    r = parse_brief((PROFILE_DIR / "book-brief-template.md").read_text())
    assert r["warnings"] == [] and not r["summary"]["intro_exact"]
    assert [i["placement"] for i in r["data"]["intro"]] == ["free_space", "behind_text"]


def test_api_json_and_everything_with_full_page_intros(settings, monkeypatch):
    monkeypatch.setenv("CBS_SEED_SAMPLE", "0")
    from fastapi.testclient import TestClient
    from cbs.api import create_app
    from cbs.providers.mock import MockProvider
    H = {"x-cbs-client": "1"}
    mock = MockProvider()
    generation.set_test_provider(mock)
    app = create_app(settings)
    S, R = app.state.studio, app.state.runner
    try:
        with TestClient(app) as c:
            t = c.get("/api/brief/template.json")
            assert t.status_code == 200 and json.loads(t.text)["pages"]
            r = c.post("/api/projects/from-brief", files={"file": ("gear.md", PLAIN.encode(), "text/markdown")}, headers=H).json()
            pid = r["project_id"]
            assert any("Removed" in w for w in r["warnings"])
            c.post(f"/api/projects/{pid}/autobook/generate", json={"mode": "sample", "confirm": True}, headers=H)
            R.run_one()
            st = c.get(f"/api/projects/{pid}/autobook/status").json()
            vid = next(p["version_id"] for p in st["pages"] if p["version_id"])
            c.patch(f"/api/assets/{S.version(vid)['asset_id']}", json={"review_status": "approved"}, headers=H)
            c.put("/api/ai/settings", json={"per_image_estimate": "0.10", "spending_limit": "5"}, headers=H)
            est = c.post(f"/api/projects/{pid}/autobook/generate", json={"mode": "everything"}, headers=H).json()
            assert est["allowed"] and est["breakdown"]["pages"] == 11 and est["breakdown"]["intro"] == 3
            c.post(f"/api/projects/{pid}/autobook/generate", json={"mode": "everything", "confirm": True}, headers=H)
            R.run_one()
            intro = S.intro_descriptions(pid)
            assert all(r["version_id"] for r in intro)
            js = c.get(f"/api/projects/{pid}/brief.json")
            assert js.status_code == 200 and json.loads(js.text)["intro_pages"][0]["placement"] == "full_page"
    finally:
        generation.set_test_provider(None)
