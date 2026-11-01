"""Export pipeline against the ACTUAL files, jobs durability, restore, generation safety, video."""
import io
import json
import os
import zipfile

import numpy as np
import pypdfium2 as pdfium
import pytest
from pypdf import PdfReader

from cbs import exporter, generation, preflight
from cbs.config import Settings
from cbs.jobs import DuplicateJob, JobRunner
from cbs.providers.mock import MockProvider
from cbs.studio import Studio

from conftest import OWNER_DECL, line_art_png, make_small_book


def _export(studio, runner, pid, mode="release", ack=True):
    j = exporter.request_export(studio, runner, pid, mode, acknowledged_review=ack)
    runner.run_one()
    return runner.get(j["id"])


def test_fixture_G_no_api_key_import_to_valid_release_zip(studio, runner, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert not generation.get_provider(studio).status()["configured"]
    pid = make_small_book(studio)
    rep = preflight.run_and_store(studio, pid)
    assert rep["counts"]["error"] == 0, rep["findings"]
    j = _export(studio, runner, pid)
    assert j["status"] == "succeeded", j["error"]
    e = exporter.list_exports(studio, pid)[0]
    zpath = exporter.export_file_path(studio, e["id"], "zip")
    z = zipfile.ZipFile(zpath)
    names = set(z.namelist())
    for required in ["interior.pdf", "cover.pdf", "preview/contact-sheet.pdf", "listing.md", "preflight.json", "preflight.md",
                     "provenance.json", "project.json", "pricing.json", "publishing-checklist.md", "manifest.json"]:
        assert required in names
    interior = PdfReader(io.BytesIO(z.read("interior.pdf")))
    assert len(interior.pages) == 24
    assert all((float(p.mediabox.width), float(p.mediabox.height)) == (612.0, 792.0) for p in interior.pages)
    cover = PdfReader(io.BytesIO(z.read("cover.pdf")))
    w, h = float(cover.pages[0].mediabox.width) / 72, float(cover.pages[0].mediabox.height) / 72
    assert w == pytest.approx(2 * 8.5 + 24 * 0.002252 + 0.25, abs=0.001) and h == pytest.approx(11.25, abs=0.001)
    manifest = json.loads(z.read("manifest.json"))
    pages = manifest["files"]["interior.pdf"]["pages"]
    assert len(pages) == 24 and pages[4]["placements"][0]["sha256"]
    assert pages[5]["kind"] == "blank" and pages[5]["placements"] == []
    # no secrets, absolute paths or storage keys leak into the package
    blob = b"".join(z.read(n) for n in names if n.endswith((".json", ".md")))
    assert str(studio.settings.data_dir).encode() not in blob
    assert b"storage_key" not in z.read("project.json")
    assert b"OPENAI_API_KEY" not in blob


def test_fixture_A_and_I_sample_book_files_have_no_guides(studio, runner):
    from cbs.seed import seed_sample
    pid = seed_sample(studio)
    j = _export(studio, runner, pid, mode="draft", ack=False)
    assert j["status"] == "succeeded", j["error"]
    e = exporter.list_exports(studio, pid)[0]
    pdf = exporter.export_file_path(studio, e["id"], "interior.pdf")
    r = PdfReader(str(pdf))
    assert len(r.pages) == 84 and {(float(p.mediabox.width), float(p.mediabox.height)) for p in r.pages} == {(612.0, 792.0)}
    text = "".join(p.extract_text() or "" for p in r.pages).lower()
    for word in ("safe area", "trim", "bleed", "guide", "draft", "watermark", "preview"):
        assert word not in text
    doc = pdfium.PdfDocument(str(pdf))
    for i in (4, 5, 30):  # illustration, blank back, another illustration
        a = np.asarray(doc[i].render(scale=50 / 72).to_pil().convert("L"))
        m = int(0.5 * 50) - 2  # outside the 0.5 in safe margin there must be nothing printed
        assert a[:m].min() >= 250 and a[-m:].min() >= 250 and a[:, :m].min() >= 250 and a[:, -m:].min() >= 250
        if i == 5:
            assert a.min() >= 250  # blank reverse is truly blank
        else:
            assert a.min() < 50  # artwork is actually there
    doc.close()
    cover = exporter.export_file_path(studio, e["id"], "cover.pdf")
    cr = PdfReader(str(cover))
    assert float(cr.pages[0].mediabox.width) / 72 == pytest.approx(17.439168, abs=0.0002)
    assert "barcode" not in (cr.pages[0].extract_text() or "").lower()
    assert e["verification"]["interior"]["info"]["fonts_not_embedded"] == []


def test_release_blocked_by_errors_and_needs_ack(studio, runner):
    pid = make_small_book(studio)
    studio.add_page(pid, "illustration")  # empty illustration -> technical error, page count 26 -> stale cover
    j = _export(studio, runner, pid)
    assert j["status"] == "failed" and "blocked" in j["error"]
    pid2 = make_small_book(studio)
    a = studio.assets(pid2)[0]
    studio.update_asset_provenance(a["id"], {"rights_declaration": "unknown"})
    j2 = _export(studio, runner, pid2, ack=False)
    assert j2["status"] == "failed" and "Human review" in j2["error"]
    j3 = _export(studio, runner, pid2, ack=True)
    assert j3["status"] == "succeeded"


def test_duplicate_export_prevented_and_cancel(studio, runner):
    pid = make_small_book(studio)
    j = exporter.request_export(studio, runner, pid, "draft")
    with pytest.raises(DuplicateJob):
        exporter.request_export(studio, runner, pid, "draft")
    c = runner.cancel(j["id"])
    assert c["status"] == "canceled"
    j2 = exporter.request_export(studio, runner, pid, "draft")  # allowed again once inactive
    assert j2["status"] == "queued"


def test_failed_export_and_interrupted_job_recovery(settings, studio, runner):
    pid = make_small_book(studio)
    # damage a stored file -> export fails cleanly with a useful error
    v = studio.version(studio.pages(pid)[4]["elements"][0]["asset_version_id"])
    path = studio.storage.path(v["storage_key"])
    original = path.read_bytes()
    path.write_bytes(b"corrupt")
    j = _export(studio, runner, pid, mode="draft")
    assert j["status"] == "failed"
    path.write_bytes(original)
    # simulate a crash mid-export: job left in 'running'
    j = exporter.request_export(studio, runner, pid, "draft")
    studio.db.x("UPDATE jobs SET status='running', attempts=1 WHERE id=?", (j["id"],))
    st2 = Studio(settings)  # "restart"
    r2 = JobRunner(st2)
    assert j["id"] in r2.recover()
    assert r2.get(j["id"])["status"] == "queued"
    r2.run_one()
    assert r2.get(j["id"])["status"] == "succeeded"


def test_fixture_H_reopen_restores_project_and_assets(settings):
    st = Studio(settings)
    pid = make_small_book(st)
    before = st.pages(pid)
    st.db.close()
    st2 = Studio(settings)
    after = st2.pages(pid)
    assert [p["id"] for p in after] == [p["id"] for p in before]
    for p in after:
        for el in p["elements"]:
            if el["kind"] == "image":
                v = st2.version(el["asset_version_id"])
                assert st2.storage.exists(v["storage_key"])
    # portable archive round-trip creates an independent copy with verified hashes
    data = st2.export_project_archive(pid)
    new = st2.import_project_archive(data)
    assert new != pid and st2.assembly(new)["page_count"] == 24
    assert len(st2.assets(new)) == len(st2.assets(pid))


def test_generation_controls_and_unknown_outcome(studio, runner):
    pid = make_small_book(studio)
    studio.draft_plan(pid, 3)
    scenes = [s["id"] for s in studio.scenes(pid)]
    mock = MockProvider()
    generation.set_test_provider(mock)
    try:
        assert mock.status()["live"] is False  # never masquerades as live generation
        with pytest.raises(ValueError, match="explicit"):
            generation.start_generation(studio, runner, pid, scenes[:1], {}, confirm=False)
        est = generation.estimate(studio, pid, 3, {})
        assert not est["allowed"] and any("ONE candidate" in p for p in est["problems"])
        assert est["estimated_cost"] == "unknown"
        j = generation.start_generation(studio, runner, pid, scenes[:1], {}, confirm=True)
        runner.run_one()
        assert runner.get(j["id"])["status"] == "succeeded"
        gen_asset = [a for a in studio.assets(pid) if a["generation"] and a["generation"].get("provider") == "mock"][0]
        assert gen_asset["ai_involvement"] == "ai_generated" and gen_asset["display_name"].startswith("MOCK-")
        studio.update_asset_provenance(gen_asset["id"], {"review_status": "approved"})
        studio.set_setting("ai_provider", {"per_image_estimate": "0.20", "spending_limit": "0.50"})
        est = generation.estimate(studio, pid, 3, {})
        assert not est["allowed"] and any("exceed" in p for p in est["problems"])  # 0.20 spent + 0.60 > 0.50
        # unknown outcome: never retried, flagged for attention
        mock.behavior = "unknown"
        j = generation.start_generation(studio, runner, pid, scenes[1:2], {}, confirm=True)
        runner.run_one()
        jj = runner.get(j["id"])
        assert jj["status"] == "needs_attention"
        with pytest.raises(ValueError):
            runner.retry(j["id"])
        states = [g["state"] for g in generation.generation_requests(studio, pid)]
        assert "unknown_outcome" in states
        # definite rejection: marked failed, no estimated cost counted
        mock.behavior = "fail"
        studio.set_setting("ai_provider", {"per_image_estimate": "0.20", "spending_limit": "5"})
        j = generation.start_generation(studio, runner, pid, scenes[2:3], {}, confirm=True)
        runner.run_one()
        jj = runner.get(j["id"])
        assert jj["status"] == "failed" and "mock rejection" in jj["error"]
        # approved pages are never overwritten by generation
        approved = [p for p in studio.pages(pid) if p["approved"]]
        assert all(p["elements"] for p in approved)
    finally:
        generation.set_test_provider(None)


def test_api_key_is_never_returned(settings, monkeypatch):
    monkeypatch.setenv("CBS_SEED_SAMPLE", "0")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from fastapi.testclient import TestClient
    from cbs.api import create_app
    with TestClient(create_app(settings)) as c:
        H = {"x-cbs-client": "1"}
        assert c.put("/api/ai/key", json={"api_key": "sk-test-SECRET123"}).status_code == 403  # CSRF header required
        r = c.put("/api/ai/key", json={"api_key": "sk-test-SECRET123"}, headers=H)
        assert r.status_code == 200 and "SECRET123" not in r.text and r.json()["status"]["configured"]
        assert "SECRET123" not in c.get("/api/meta").text
        assert oct(os.stat(settings.secrets_path).st_mode & 0o777) == "0o600"
        assert c.get("/api/health", headers={"host": "evil.example"}).status_code == 400


def test_promo_video_real_mp4(studio, runner):
    from cbs import video
    if not video.available()["available"]:
        pytest.skip("ffmpeg not installed")
    pid = make_small_book(studio, n_illus=10)
    j = runner.enqueue("promo_video", pid, {"duration_s": 4, "captions": ["Hello"], "max_pages": 2})
    runner.run_one()
    jj = runner.get(j["id"])
    assert jj["status"] == "succeeded", jj["error"]
    v = jj["result"]["verification"]
    assert (v["width"], v["height"]) == (1080, 1920) and v["decode_ok"] and v["audio_streams"] == 0 and abs(v["duration_s"] - 4) < 0.5
