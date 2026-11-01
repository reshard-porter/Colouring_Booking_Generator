import io
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cbs.config import Settings  # noqa: E402
from cbs.jobs import JobRunner  # noqa: E402
from cbs.studio import Studio  # noqa: E402
from cbs import exporter, generation, video  # noqa: E402,F401  (register job handlers)


@pytest.fixture
def settings(tmp_path):
    s = Settings(data_dir=tmp_path / "data")
    s.start_worker = False
    return s


@pytest.fixture
def studio(settings):
    st = Studio(settings)
    yield st
    st.db.close()


@pytest.fixture
def runner(studio):
    return JobRunner(studio)


def line_art_png(w=2250, h=3000, seed=0, dpi=None, mode="L") -> bytes:
    im = Image.new(mode, (w, h), 255 if mode == "L" else (255, 255, 255))
    d = ImageDraw.Draw(im)
    lw = max(4, w // 160)
    d.ellipse([w * 0.2, h * 0.2, w * 0.8, h * 0.6], outline=0, width=lw)
    d.rectangle([w * (0.1 + 0.02 * seed), h * 0.65, w * 0.6, h * 0.9], outline=0, width=lw)
    d.line([w * 0.1, h * (0.1 + 0.01 * seed), w * 0.9, h * 0.15], fill=0, width=lw)
    for k in range(seed % 5 + 1):
        d.ellipse([w * (0.3 + 0.08 * k), h * 0.3, w * (0.36 + 0.08 * k), h * 0.36], outline=0, width=lw)
    buf = io.BytesIO()
    im.save(buf, "PNG", **({"dpi": (dpi, dpi)} if dpi else {}))
    return buf.getvalue()


OWNER_DECL = {"source_type": "user_created", "rights_declaration": "owner_declared", "ai_involvement": "none", "creator": "Test Owner"}


def make_small_book(studio, n_illus=10, intro=4, **spec):
    """A complete book (24 pages with defaults) using imported, owner-declared art."""
    pid = studio.create_project("Test book", {"title": "Test Book", "author": "Test Owner", "illustration_count": n_illus,
                                               "intro_pages": intro, **spec})
    studio.update_listing(pid, {"title": "Test Book", "author": "Test Owner", "description": "A test.", "isbn_choice": "free_kdp"})
    illus = [p for p in studio.pages(pid) if p["kind"] == "illustration"]
    for i, p in enumerate(illus):
        a = studio.import_asset(pid, f"art{i}.png", line_art_png(seed=i), OWNER_DECL)
        studio.place_asset(p["id"], a["current_version_id"])
        studio.set_page_approval(p["id"], True)
    first = studio.pages(pid)[intro]["elements"][0]["asset_version_id"]
    cover_art = studio.derive_cover_art(first)
    studio.update_cover(pid, {"front_art_version_id": cover_art["current_version_id"]})
    for a in studio.assets(pid):
        studio.update_asset_provenance(a["id"], {"review_status": "approved"})
    return pid
