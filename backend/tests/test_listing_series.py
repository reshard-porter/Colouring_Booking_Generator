"""Listing draft from the book, KDP field checks, back-cover text defaults, and the next book in a series."""
from cbs.brief import apply_brief, parse_brief, spec_from_settings
from cbs.listing_draft import draft_listing, listing_checks
from cbs.series import next_title, start_next_book
from cbs.studio import DEFAULT_COVER

from test_brief_layouts import PLAIN


def _book(studio):
    parsed = parse_brief(PLAIN)
    spec, _ = spec_from_settings(parsed["data"])
    pid = studio.create_project(spec["title"], {k: v for k, v in spec.items() if k != "theme"})
    res = apply_brief(studio, pid, parsed["data"])
    return pid, res


def test_new_books_do_not_inherit_the_sample_back_text(studio):
    pid = studio.create_project("Plain book")
    assert studio.cover(pid)["data"]["back_copy"] == ""
    sample = studio.create_project("Sample", is_sample=True)
    assert studio.cover(sample)["data"]["back_copy"] == DEFAULT_COVER["back_copy"]
    from cbs.preflight import run_and_store
    codes = [f["code"] for f in run_and_store(studio, pid)["findings"]]
    assert "back_cover_text" in codes
    studio.update_cover(pid, {"back_copy": DEFAULT_COVER["back_copy"]})  # an old book still carrying the sample text
    codes = [f["code"] for f in run_and_store(studio, pid)["findings"]]
    assert "back_cover_sample_text" in codes


def test_brief_without_back_text_gets_a_drafted_one(studio):
    pid, res = _book(studio)
    back = studio.cover(pid)["data"]["back_copy"]
    assert back.startswith("Join Moss and Fig") and "12 pictures to color" in back and "ages 3–7" in back
    assert any("Back-cover text drafted" in c for c in res["changes"])


def test_listing_draft_uses_only_the_books_facts(studio):
    pid, _ = _book(studio)
    d = draft_listing(studio, pid)
    desc = d["description"]
    assert desc.startswith("Join Moss and Fig in The Windmill Fix – 12 original coloring pages for kids ages 3–7.")
    assert "in 2 parts: The Wind Stops and The Fix" in desc and "• Moss – hedgehog, leader" in desc
    assert "12 illustrations, each on its own page with a blank back" in desc and "badge, crew and swatches" in desc
    assert len(desc) <= 4000 and d["checks"] == []
    for word in ("bestseller", "best-selling", "#1", "guaranteed", "award"):
        assert word not in desc.lower()
    kws = d["keywords"]
    assert kws[0] == "coloring book for kids ages 3-7" and "hedgehog coloring pages for kids" in kws
    assert len(kws) <= 7 and all(len(k) <= 50 for k in kws) and len(set(kws)) == len(kws)


def test_listing_checks():
    long = {"title": "T" * 120, "subtitle": "S" * 90, "description": "x" * 4001,
            "keywords": ["a" * 51, "coloring book", "windmill", '"quoted"', "k5", "k6", "k7", "k8"]}
    codes = {c["code"] for c in listing_checks(long)}
    assert {"title_too_long", "description_too_long", "keyword_too_long", "too_many_keywords", "keyword_quotes", "keyword_generic"} <= codes
    ok = {"title": "Gear Gang", "subtitle": "The Windmill Fix", "description": "A" * 300, "keywords": ["windmill gear", "toddler crayons"]}
    assert [c["code"] for c in listing_checks(ok)] == ["keyword_repeats_title"]
    assert listing_checks({"title": "x" * 100, "subtitle": "y" * 100}) == []  # exactly 200 is allowed


def test_next_title():
    assert next_title("Sprocket Squad: Book 1") == ("Sprocket Squad: Book 2", "Sprocket Squad", 2)
    assert next_title("Moon Friends") == ("Moon Friends: Book 2", "Moon Friends", 2)
    assert next_title("Ocean Pals Volume 3")[0] == "Ocean Pals: Volume 4"


def test_start_next_book_copies_look_not_story(studio):
    pid, _ = _book(studio)
    studio.apply_style_preset(pid, "storybook_adventure", "combine")
    studio.update_cover(pid, {"background": "#123456"})
    r = start_next_book(studio, pid)
    new = r["project_id"]
    sp, sg = studio.spec(new), studio.style_guide(new)
    assert r["title"] == sp["title"] == "Gear Gang: Book 2" and sp["subtitle"] == "" and sp["theme"] == ""
    assert sp["age_min"] == 3 and sp["illustration_count"] == 12 and sp["trim"] == "8.5x11"
    assert sg["master_style"] == studio.style_guide(pid)["master_style"] and [c["name"] for c in sg["characters"]] == ["Moss", "Fig"]
    intro = studio.intro_descriptions(new)
    assert [x["label"] for x in intro] == ["Badge", "Crew", "Swatches"] and all(x["placement"] == "full_page" for x in intro)
    assert all(not x["version_id"] for x in intro) and intro[0]["description"].startswith("A shield badge")
    assert all(not row["description"] for row in studio.page_descriptions(new))
    cv = studio.cover(new)["data"]
    assert cv["background"] == "#123456" and cv["back_copy"] == "" and not cv["front_art_version_id"]
    ls = studio.listing(new)
    assert ls["series_name"] == "Gear Gang" and ls["series_number"] == "2" and ls["description"] == ""
    assert studio.listing(pid)["series_name"] == "Gear Gang" and studio.listing(pid)["series_number"] == "1"
    assert studio.assembly(new)["page_count"] == studio.assembly(pid)["page_count"]
    # Book 3 from Book 2 counts on
    assert start_next_book(studio, new)["title"] == "Gear Gang: Book 3"


def test_api_listing_draft_check_and_series(settings, monkeypatch):
    monkeypatch.setenv("CBS_SEED_SAMPLE", "0")
    from fastapi.testclient import TestClient
    from cbs.api import create_app
    H = {"x-cbs-client": "1"}
    app = create_app(settings)
    with TestClient(app) as c:
        pid = c.post("/api/projects/from-brief", files={"file": ("g.md", PLAIN.encode(), "text/markdown")}, headers=H).json()["project_id"]
        d = c.post(f"/api/projects/{pid}/listing/draft", headers=H).json()
        assert d["description"].startswith("Join Moss") and d["back_copy"]
        chk = c.post("/api/listing/check", json={"title": "x" * 201, "keywords": []}, headers=H).json()["checks"]
        assert chk[0]["code"] == "title_too_long"
        r = c.post(f"/api/projects/{pid}/series/next", json={}, headers=H).json()
        assert r["title"] == "Gear Gang: Book 2" and c.get(f"/api/projects/{r['project_id']}").status_code == 200
