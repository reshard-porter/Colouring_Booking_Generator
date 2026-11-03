"""Story pages: text on the left page facing each illustration (layout, storage, fit, preflight, export, AI writing, briefs)."""
import json

import httpx
import pytest

from cbs import stories
from cbs.brief import apply_brief, export_brief, parse_brief, spec_from_settings
from cbs.layout import assemble
from cbs.providers.base import ProviderOutcomeUnknown, ProviderRequestFailed
from cbs.providers.openai_text import MockTextProvider, OpenAITextProvider, extract_text
from conftest import line_art_png

PARA = ("Barnaby the red panda tugged the long rope with all his might, his brass helmet wobbling as he pulled. "
        "Behind him, Pippa dug her paws into the soft grass and giggled, while Dozer leaned back like a little bulldozer. ")
STORY_420 = "\n\n".join([(PARA * 3).strip()] * 4)  # ≈ 450 words in 4 paragraphs


def _book(studio, n=12, intro=True):
    pid = studio.create_project("Story book", {"illustration_count": n, "facing_text": True, "author": "R. Porter",
                                               "age_min": 3, "age_max": 7})
    if not intro:
        for p in [p for p in studio.pages(pid) if p["kind"] == "intro"]:
            studio.delete_page(p["id"])
    return pid


def _art(studio, pid):
    for i, r in enumerate(stories.list_stories(studio, pid)):
        a = studio.import_asset(pid, f"p{i}.png", line_art_png(900, 1200, seed=i))
        studio.place_asset(r["page_id"], a["current_version_id"])


def test_layout_story_faces_each_picture():
    pages = [{"id": f"i{k}", "kind": "intro"} for k in range(4)] + [{"id": f"p{k}", "kind": "illustration"} for k in range(3)]
    a = assemble(pages, {"facing_text": True})
    kinds = [(e["number"], e["side"], e["kind"], e.get("story_for") or e["page_id"]) for e in a["pages"]]
    assert kinds[4:] == [(5, "recto", "blank", None), (6, "verso", "story", "p0"), (7, "recto", "illustration", "p0"),
                         (8, "verso", "story", "p1"), (9, "recto", "illustration", "p1"),
                         (10, "verso", "story", "p2"), (11, "recto", "illustration", "p2"), (12, "verso", "blank", None)]
    assert a["story_count"] == 3 and a["page_count"] % 2 == 0
    b = assemble(pages[1:], {"facing_text": True})  # 3 intro pages: the first story is page 4, no parity blank
    assert [e["kind"] for e in b["pages"][3:5]] == ["story", "illustration"] and b["pages"][3]["number"] == 4
    # same book without story pages: blank backs as before
    assert [e["kind"] for e in assemble(pages, {"blank_backs": True})["pages"]][4:6] == ["illustration", "blank"]


def test_story_storage_survives_replanning_and_page_moves(studio):
    pid = _book(studio)
    rows = stories.list_stories(studio, pid)
    assert len(rows) == 12 and rows[0]["story_page_number"] == 6 and rows[0]["picture_page_number"] == 7
    r = stories.set_story(studio, rows[0]["page_id"], STORY_420, "The Big Pull")
    assert r["words"] >= 400 and r["fits"] and 10 <= r["font_pt"] <= 16 and r["title"] == "The Big Pull" and not r["ai"]
    studio.draft_plan(pid, 12, replace=True)
    assert stories.list_stories(studio, pid)[0]["text"] == STORY_420
    ids = [p["id"] for p in studio.pages(pid)]
    ill = [p["id"] for p in studio.pages(pid) if p["kind"] == "illustration"]
    studio.reorder_pages(pid, [i for i in ids if i not in ill] + ill[1:] + ill[:1])  # move picture 1 to the end
    assert stories.list_stories(studio, pid)[-1]["text"] == STORY_420  # the story moves with its picture
    with pytest.raises(ValueError):
        stories.set_story(studio, rows[0]["page_id"], "x" * 9001)
    with pytest.raises(ValueError):
        stories.set_story(studio, [p for p in studio.pages(pid) if p["kind"] == "intro"][0]["id"], "hi")
    studio.delete_page(ill[0])
    assert studio.db.q1("SELECT COUNT(*) n FROM page_stories WHERE page_id=?", (ill[0],))["n"] == 0


def test_bulk_paste_split():
    parts = stories.split_pasted("Page 1: The Big Pull\nBarnaby pulled.\n\nPippa laughed.\n\n### Story 2\nA cloud blew.\n---\nUnnumbered text.")
    assert parts == [(1, "The Big Pull", "Barnaby pulled.\n\nPippa laughed."), (2, "", "A cloud blew."), (None, "", "Unnumbered text.")]
    long_heading = stories.split_pasted("Page 3: Barnaby looked through the big brass periscope and spotted the dark lighthouse far away.")
    assert long_heading == [(3, "", "Barnaby looked through the big brass periscope and spotted the dark lighthouse far away.")]


def test_bulk_set_and_fit_and_preflight(studio):
    pid = _book(studio, n=10)
    _art(studio, pid)
    text = "\n\n".join(f"Page {i + 1}: Title {i + 1}\n{STORY_420}" for i in range(8))
    res = stories.bulk_set(studio, pid, text + "\n\nPage 30: too far\nnothing")
    assert res["filled"] == 8 and res["ignored"] == 1
    rows = stories.list_stories(studio, pid)
    stories.set_story(studio, rows[8]["page_id"], PARA)  # short
    stories.set_story(studio, rows[7]["page_id"], (PARA * 6 + "\n\n") * 6)  # ≈ 8,000 characters: too long for one page
    from cbs.preflight import run_and_store
    rep = run_and_store(studio, pid)
    found = {f["code"]: f for f in rep["findings"]}
    assert "blank_back_rule" not in found and "story_layout_rule" not in found
    assert found["story_empty"]["severity"] == "warning" and "1 story page" in found["story_empty"]["message"]
    assert found["story_short"]["severity"] == "heuristic"
    assert found["story_too_long"]["severity"] == "error" and found["story_too_long"]["page_number"] == rows[7]["story_page_number"]
    assert stories.list_stories(studio, pid)[7]["fits"] is False


def test_export_prints_story_pages(studio, tmp_path):
    from cbs.geometry import PrintConfig, page_geometry
    from cbs.render import render_interior
    from cbs.snapshot import build_snapshot
    from cbs.units import in_to_pt
    from cbs.verify import verify_interior
    pid = _book(studio, n=10)
    _art(studio, pid)
    for r in stories.list_stories(studio, pid):
        stories.set_story(studio, r["page_id"], STORY_420, f"Part {r['illustration_number']}")
    snap = build_snapshot(studio, pid)
    asm = snap["assembly"]
    assert asm["page_count"] == 4 + 1 + 20 + 1 and asm["story_count"] == 10
    out = tmp_path / "interior.pdf"
    man = render_interior(snap, studio.storage.read, out)
    st = [m for m in man if m["kind"] == "story"]
    assert len(st) == 10 and all(m["placements"][0]["story"] and not m["placements"][0]["overflow"] for m in st)
    cfg = PrintConfig(**snap["config"])
    media = []
    for e in asm["pages"]:
        g = page_geometry(cfg, e["number"], max(asm["page_count"], 24))
        media.append((in_to_pt(g.media_w), in_to_pt(g.media_h)))
    v = verify_interior(out, asm["page_count"], media, [e["number"] for e in asm["pages"] if e["kind"] == "blank"],
                        (in_to_pt(cfg.trim_w), in_to_pt(cfg.trim_h)))
    assert v["ok"], v["errors"]
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(out))
    txt = doc[5].get_textpage().get_text_range()
    assert "Part 1" in txt and "Barnaby the red panda" in txt  # page 6 is the story facing picture 1 on page 7
    assert doc[6].get_textpage().get_text_range().strip() == ""  # the picture page has no text


def test_ai_writing_job_budget_and_disclosure(studio):
    from cbs.jobs import JobRunner
    runner = JobRunner(studio)
    pid = _book(studio, n=3)
    sg = studio.style_guide(pid)
    studio.update_style_guide(pid, {"characters": [{"name": "Barnaby", "role": "leader", "appearance": "Red panda with a brass helmet"}]})
    rows = stories.list_stories(studio, pid)
    studio.set_page_description(rows[0]["page_id"], "Barnaby and friends playing tug-of-war outside the treehouse.")
    mock = MockTextProvider(words=430)
    stories.set_test_text_provider(mock)
    try:
        est = stories.estimate_stories(studio, pid, [r["page_id"] for r in rows])
        assert not est["allowed"] and any("Cost per story is unknown" in p for p in est["problems"])
        studio.set_setting("ai_provider", {"per_story_estimate": "0.02", "spending_limit": "0.05"})
        with pytest.raises(ValueError, match="confirmation"):
            stories.start_writing(studio, runner, pid, None, confirm=False)
        est = stories.estimate_stories(studio, pid, [r["page_id"] for r in rows])
        assert est["allowed"] and est["estimated_cost"] == "0.06" or not est["allowed"]
        assert any("exceed your spending limit" in p for p in est["problems"])  # 3 × 0.02 > 0.05
        studio.set_setting("ai_provider", {"per_story_estimate": "0.02", "spending_limit": "1"})
        job = stories.start_writing(studio, runner, pid, None, confirm=True)
        runner.run_one()
        j = runner.get(job["id"])
        assert j["status"] == "succeeded" and j["result"]["written"] == [1, 2, 3]
        rows = stories.list_stories(studio, pid)
        assert all(r["ai"] and r["words"] >= 400 for r in rows)
        assert mock.calls == 3 and "MOCK story sentence" in mock.last["prompt"]  # page 3 sees page 2's ending
        first_prompt = studio.db.q("SELECT prompt FROM generation_requests WHERE project_id=? ORDER BY created_at", (pid,))[0]["prompt"]
        assert "tug-of-war outside the treehouse" in first_prompt and "Barnaby: leader; Red panda" in first_prompt
        assert "400–520 words" in mock.last["instructions"] and "ages 3–7" in mock.last["instructions"]
        assert studio.listing(pid)["text_ai_involvement"] == "ai_generated"
        from cbs.generation import budget
        assert budget(studio, pid)["estimated_spent"] == "0.06"
        # editing AI text keeps it recorded as AI-written
        r = stories.set_story(studio, rows[0]["page_id"], rows[0]["text"] + " The end.")
        assert r["ai"] and r["edited_after_ai"]
        # nothing missing now
        with pytest.raises(ValueError, match="No pages selected"):
            stories.start_writing(studio, runner, pid, None, confirm=True)
    finally:
        stories.set_test_text_provider(None)


def test_ai_text_with_protected_name_is_not_used(studio):
    from cbs.jobs import JobRunner
    runner = JobRunner(studio)
    pid = _book(studio, n=1)

    class Bad(MockTextProvider):
        def write(self, instructions, prompt, max_output_tokens=4000):
            return {"text": "Pikachu came to visit.", "usage": {}, "request_id": None, "model": "mock"}
    stories.set_test_text_provider(Bad())
    try:
        job = stories.start_writing(studio, runner, pid, None, confirm=True)
        runner.run_one()
        res = runner.get(job["id"])["result"]
        assert res["written"] == [] and "Pikachu" in res["failed"][0]["error"]
        assert stories.list_stories(studio, pid)[0]["text"] == ""
    finally:
        stories.set_test_text_provider(None)


def test_openai_text_contract():
    seen = {}

    def ok(req):
        seen["url"], seen["body"] = str(req.url), json.loads(req.content)
        return httpx.Response(200, json={"id": "resp_1", "model": "gpt-5.6-terra", "status": "completed",
                                         "output": [{"type": "reasoning", "summary": []},
                                                    {"type": "message", "role": "assistant",
                                                     "content": [{"type": "output_text", "text": "Once upon a time.", "annotations": []}]}],
                                         "usage": {"input_tokens": 300, "output_tokens": 600}}, headers={"x-request-id": "req_9"})
    p = OpenAITextProvider("sk-test", transport=httpx.MockTransport(ok), sleep=lambda s: None)
    r = p.write("be nice", "picture 1")
    assert seen["url"] == "https://api.openai.com/v1/responses" and seen["body"]["model"] == "gpt-5.6-terra"
    assert seen["body"]["instructions"] == "be nice" and seen["body"]["input"] == "picture 1" and seen["body"]["reasoning"] == {"effort": "low"}
    assert r["text"] == "Once upon a time." and r["request_id"] == "req_9" and r["usage"]["output_tokens"] == 600
    assert extract_text({"output_text": " Hi "}) == "Hi"
    calls = []

    def no_reasoning(req):
        b = json.loads(req.content)
        calls.append("reasoning" in b)
        if "reasoning" in b:
            return httpx.Response(400, json={"error": {"message": "Unsupported parameter: 'reasoning' for this model."}})
        return ok(req)
    assert OpenAITextProvider("sk", transport=httpx.MockTransport(no_reasoning), sleep=lambda s: None).write("a", "b")["text"]
    assert calls == [True, False]
    with pytest.raises(ProviderRequestFailed, match="401"):
        OpenAITextProvider("sk", transport=httpx.MockTransport(lambda r: httpx.Response(401, json={"error": {"message": "bad key"}}))).write("a", "b")

    def slow(req):
        raise httpx.ReadTimeout("slow", request=req)
    with pytest.raises(ProviderOutcomeUnknown):
        OpenAITextProvider("sk", transport=httpx.MockTransport(slow)).write("a", "b")
    with pytest.raises(ProviderRequestFailed, match="no text"):
        OpenAITextProvider("sk", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"output": [], "status": "incomplete"}))).write("a", "b")


def test_brief_story_round_trip(studio):
    md = """# Gear Gang
## Settings
- Story words: 420
## Pages
### Page 1: Tug of war
All five heroes tug a rope.

Story title: The Big Pull
Story:
Barnaby grabbed the rope.

Pippa laughed and pulled too.
### Page 2
A wind cloud.

Story: The cloud huffed and puffed.
""" + "\n".join(f"### Page {i}\nScene {i}." for i in range(3, 11))
    parsed = parse_brief(md)
    d = parsed["data"]
    assert parsed["summary"]["stories"] == 2 and d["facing_text"] and d["pages"][0]["story_title"] == "The Big Pull"
    assert d["pages"][0]["story"] == "Barnaby grabbed the rope.\n\nPippa laughed and pulled too." and d["pages"][0]["description"] == "All five heroes tug a rope."
    spec, _ = spec_from_settings(d)
    assert spec["facing_text"] and spec["story_words"] == 420
    pid = studio.create_project(spec["title"], {k: v for k, v in spec.items() if k != "theme"})
    res = apply_brief(studio, pid, d)
    assert any("2 story page(s) set" in c for c in res["changes"])
    rows = stories.list_stories(studio, pid)
    assert rows[1]["text"] == "The cloud huffed and puffed." and rows[0]["title"] == "The Big Pull"
    again = parse_brief(export_brief(studio, pid))
    assert again["data"]["pages"][0]["story"] == rows[0]["text"] and again["data"]["facing_text"]
    js = parse_brief(json.dumps({"title": "J", "settings": {"story pages": "yes"},
                                 "pages": [{"page": 1, "description": "A turtle.", "story": "Tilly swam.", "story_title": "Swim"}]}))
    assert js["data"]["pages"][0]["story"] == "Tilly swam." and js["data"]["facing_text"]


def test_backup_keeps_stories_and_series_keeps_setting(studio):
    pid = _book(studio, n=10)
    rows = stories.list_stories(studio, pid)
    stories.set_story(studio, rows[2]["page_id"], "Kept story.", "Kept")
    new = studio.import_project_archive(studio.export_project_archive(pid))
    assert stories.list_stories(studio, new)[2]["text"] == "Kept story."
    from cbs.series import start_next_book
    b2 = start_next_book(studio, pid)["project_id"]
    assert studio.spec(b2)["facing_text"] and all(not r["text"] for r in stories.list_stories(studio, b2))


def test_api(settings, monkeypatch):
    monkeypatch.setenv("CBS_SEED_SAMPLE", "0")
    from fastapi.testclient import TestClient
    from cbs.api import create_app
    H = {"x-cbs-client": "1"}
    app = create_app(settings)
    with TestClient(app) as c:
        S = app.state.studio
        pid = S.create_project("Api", {"illustration_count": 10})
        d = c.get(f"/api/projects/{pid}/stories").json()
        assert d["facing_text"] is False and len(d["rows"]) == 10 and d["story_words"] == 400
        rows = d["rows"]
        assert c.get(f"/api/projects/{pid}/stories/{rows[0]['page_id']}/preview.png").status_code == 404
        c.put(f"/api/projects/{pid}/spec", json={"facing_text": True, "story_words": 380}, headers=H)
        r = c.put(f"/api/pages/{rows[0]['page_id']}/story", json={"title": "T", "text": STORY_420}, headers=H).json()
        assert r["words"] > 400 and r["protected_names"] == []
        png = c.get(f"/api/projects/{pid}/stories/{rows[0]['page_id']}/preview.png")
        assert png.status_code == 200 and png.content[:4] == b"\x89PNG"
        b = c.post(f"/api/projects/{pid}/stories/bulk", json={"text": "Page 2\nTwo.\n\nPage 3\nThree."}, headers=H).json()
        assert b["filled"] == 2
        est = c.post(f"/api/projects/{pid}/stories/estimate", json={}, headers=H).json()
        assert est["count"] == 7
        assert c.put(f"/api/projects/{pid}/spec", json={"story_words": 5}, headers=H).status_code == 400
        s = c.get("/api/ai/status").json()
        assert s["text_models"][0]["id"] == "gpt-5.6-terra"
        c.put("/api/ai/settings", json={"text_model": "gpt-5.6-luna", "per_story_estimate": "0.01"}, headers=H)
        assert c.get("/api/ai/status").json()["settings"]["text_model"] == "gpt-5.6-luna"
