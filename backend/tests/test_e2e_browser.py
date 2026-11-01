"""Browser journey: new project → import art → edit → arrange pages → cover → preflight → download ZIP.
Runs the real server (built frontend required) in a subprocess with a fresh data dir and drives Chromium."""
import io
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

import pytest
from pypdf import PdfReader

from conftest import line_art_png

ROOT = Path(__file__).resolve().parents[2]
SHOTS = ROOT / "docs" / "screenshots"


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        pytest.skip("frontend not built (run npm run build in frontend/)")
    port = _free_port()
    data = tmp_path_factory.mktemp("e2e-data")
    env = {**os.environ, "CBS_DATA_DIR": str(data), "CBS_PORT": str(port), "CBS_SEED_SAMPLE": "0"}
    env.pop("OPENAI_API_KEY", None)
    proc = subprocess.Popen([sys.executable, "-m", "cbs"], cwd=ROOT / "backend", env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/api/health", timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    else:
        proc.kill()
        raise RuntimeError("server did not start")
    yield base
    proc.terminate()
    proc.wait(10)


def test_browser_journey(server, tmp_path):
    from playwright.sync_api import expect, sync_playwright
    files = []
    for i in range(10):
        p = tmp_path / f"page-{i + 1:02d}.png"
        p.write_bytes(line_art_png(seed=i))
        files.append(str(p))
    SHOTS.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.set_default_timeout(30000)
        # 1. new project via the guided form
        page.goto(server + "/")
        page.get_by_role("button", name="+ New book").click()
        page.get_by_label("Working title").fill("Journey Book")
        page.get_by_label("Author / pen name").fill("Jo Tester")
        page.get_by_label("Illustrations").fill("10")
        page.get_by_role("button", name="Create book").click()
        expect(page.get_by_role("heading", name="Plan & style")).to_be_visible()
        pid = page.url.split("/p/")[1].split("/")[0]
        # 2. offline scene plan
        page.get_by_role("button", name="Draft 10 scenes").click()
        expect(page.locator(".scene")).to_have_count(10)
        # 3. import artwork with a rights declaration
        page.goto(f"{server}/#/p/{pid}/artwork")
        page.locator(".dropzone input[type=file]").set_input_files(files)
        expect(page.get_by_text("Imported 10 file(s)")).to_be_visible(timeout=60000)
        expect(page.locator(".asset")).to_have_count(10)
        page.screenshot(path=str(SHOTS / "journey-1-artwork.png"))
        # 4. place first artwork through the UI → editor opens
        page.locator(".asset").first.get_by_role("button", name="Place on page…").click()
        page.get_by_role("button", name="Illustration 1").first.click()
        expect(page.get_by_text("✓ Saved")).to_be_visible()
        # 5. edit: select, nudge with keyboard, threshold (new version), keep, fit to safe area
        page.locator("svg.canvas rect.hit[data-kind=image]").first.click()
        page.keyboard.press("ArrowRight")
        expect(page.get_by_text("✓ Saved")).to_be_visible()
        page.get_by_role("button", name="Apply threshold").click()
        page.get_by_role("button", name="Keep change").click()
        page.get_by_role("button", name="Fit to safe area").click()
        expect(page.get_by_text("✓ Saved")).to_be_visible()
        expect(page.get_by_text("Effective resolution")).to_contain_text("300 DPI")
        page.screenshot(path=str(SHOTS / "journey-2-editor.png"))
        # remaining pages placed via the same API the UI uses
        full = json.loads(urllib.request.urlopen(f"{server}/api/projects/{pid}").read())
        assets = json.loads(urllib.request.urlopen(f"{server}/api/projects/{pid}/assets").read())
        illus = [p for p in full["pages"] if p["kind"] == "illustration"]
        for p, a in zip(illus[1:], assets[1:]):
            r = page.request.post(f"{server}/api/pages/{p['id']}/place", data={"version_id": a["current_version_id"]}, headers={"X-CBS-Client": "1"})
            assert r.ok
        # 6. pages: approve all, reorder
        page.goto(f"{server}/#/p/{pid}/pages")
        expect(page.get_by_text("24 interior pages")).to_be_visible()
        for _ in range(10):
            page.get_by_role("button", name="Approve", exact=True).first.click()
            page.wait_for_timeout(250)
        expect(page.get_by_text("Approved illustrations: 10 / 10")).to_be_visible()
        page.get_by_role("button", name="Move later").nth(4).click()
        expect(page.get_by_text("Page order updated")).to_be_visible()
        page.screenshot(path=str(SHOTS / "journey-3-pages.png"))
        # 7. cover: colored version of an interior illustration
        page.goto(f"{server}/#/p/{pid}/cover")
        page.get_by_label("Make a colored version of an interior illustration").select_option(index=1)
        expect(page.get_by_text("Colored cover art created")).to_be_visible(timeout=60000)
        page.get_by_role("button", name="Save & update preview").click()
        page.wait_for_timeout(1500)
        page.screenshot(path=str(SHOTS / "journey-4-cover.png"))
        # 8. preflight
        page.goto(f"{server}/#/p/{pid}/preflight")
        page.get_by_role("button", name="Run preflight").click()
        expect(page.locator(".banner")).to_contain_text("Technical checks pass", timeout=60000)
        page.screenshot(path=str(SHOTS / "journey-5-preflight.png"), full_page=True)
        # 9. release export + download
        page.goto(f"{server}/#/p/{pid}/export")
        page.get_by_label("I reviewed these items and accept responsibility for them").check()
        page.get_by_role("button", name="Export print-release package").click()
        link = page.get_by_role("link", name="Download ZIP").first
        expect(link).to_be_visible(timeout=120000)
        page.screenshot(path=str(SHOTS / "journey-6-export.png"), full_page=True)
        with page.expect_download() as dl:
            link.click()
        path = tmp_path / "downloaded.zip"
        dl.value.save_as(path)
        b.close()
    assert not errors, errors
    z = zipfile.ZipFile(path)
    assert "interior.pdf" in z.namelist() and "cover.pdf" in z.namelist() and "publishing-checklist.md" in z.namelist()
    r = PdfReader(io.BytesIO(z.read("interior.pdf")))
    assert len(r.pages) == 24 and {(float(p.mediabox.width), float(p.mediabox.height)) for p in r.pages} == {(612.0, 792.0)}
    assert "PRINT-RELEASE CANDIDATE" in z.read("publishing-checklist.md").decode()
    prov = json.loads(z.read("provenance.json"))
    edited = [a for a in prov["assets"] if any(v["operation"] and v["operation"].get("type") == "threshold" for v in a["versions_used"])]
    assert edited and edited[0]["source_type"] == "user_created"
