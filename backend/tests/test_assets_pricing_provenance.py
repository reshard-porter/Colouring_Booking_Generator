"""Effective DPI, pricing, provenance inheritance and upload validation."""
import io
import zlib
import struct

import pytest
from PIL import Image

from cbs import preflight
from cbs.imaging import UploadRejected, safe_display_name
from cbs.pricing import calculate
from cbs.provenance import disclosure
from cbs.snapshot import build_snapshot
from cbs.studio import Conflict

from conftest import OWNER_DECL, line_art_png, make_small_book


def test_fixture_E_1024px_at_8in_is_128dpi_despite_300dpi_metadata(studio):
    pid = make_small_book(studio)
    page = [p for p in studio.pages(pid) if p["kind"] == "illustration"][0]
    data = line_art_png(1024, 1365, dpi=300)
    a = studio.import_asset(pid, "small.png", data, OWNER_DECL)
    v = a["versions"][0]
    assert v["dpi_meta_x"] == pytest.approx(300, abs=0.5)  # metadata says 300…
    el = {"kind": "image", "asset_version_id": v["id"], "x": 0.25, "y": 0.5, "w": 8.0, "rotation": 0, "crop": {}}
    from cbs.geometry import effective_dpi_for
    assert effective_dpi_for(el, v) == pytest.approx(128.0)  # …but only 128 px per printed inch
    studio.save_elements(page["id"], [{**el, "x": 0.25}])
    rep = preflight.run(studio, build_snapshot(studio, pid))
    low = [f for f in rep["findings"] if f["code"] == "low_resolution"]
    assert low and low[0]["detail"]["effective_dpi"] == pytest.approx(128.0)
    assert rep["status"] == "blocked"


def test_upscaling_does_not_pass_low_resolution(studio):
    pid = make_small_book(studio)
    page = [p for p in studio.pages(pid) if p["kind"] == "illustration"][0]
    a = studio.import_asset(pid, "small.png", line_art_png(1024, 1365), OWNER_DECL)
    up = studio.derive_version(a["current_version_id"], {"type": "upscale", "factor": 4})
    assert up["width_px"] == 4096 and up["original_width_px"] == 1024 and up["upscaled"]
    studio.save_elements(page["id"], [{"kind": "image", "asset_version_id": up["id"], "x": 0.5, "y": 0.5, "w": 7.5, "crop": {}}])
    rep = preflight.run(studio, build_snapshot(studio, pid))
    f = [x for x in rep["findings"] if x["code"] == "low_resolution"]
    assert f and "enlarged" in f[0]["message"] and f[0]["detail"]["effective_dpi"] < 150


@pytest.mark.parametrize("price,rate,royalty", [("9.98", "0.50", "2.15"), ("9.99", "0.60", "3.15"), ("12.99", "0.60", "4.95")])
def test_fixture_D_pricing_boundaries(studio, price, rate, royalty):
    prof = studio.active_pricing_profile()
    r = calculate(prof, 84, True, price)
    assert r["printing_cost"] == "2.84" and r["royalty_rate"] == rate and r["royalty_per_copy"] == royalty
    assert r["checked_on"] == "2026-10-30" and r["sources"]["official_calculator"].startswith("https://kdp.amazon.com")


def test_pricing_decimal_and_bands(studio):
    prof = studio.active_pricing_profile()
    r = calculate(prof, 84, True, "9.99")
    from decimal import Decimal
    assert Decimal(r["royalty_per_copy_exact"]) == Decimal("3.154")  # exact: 0.60×9.99 − 2.84, no float noise
    assert calculate(prof, 120, True, "9.99")["printing_cost"] == "3.04"  # 1.00 + 120*0.017
    assert calculate(prof, 84, False, "9.99")["printing_cost"] == "2.30"
    neg = calculate(prof, 84, True, "4.99")
    assert neg["royalty_negative"] and "warning" in neg
    sc = calculate(prof, 84, True, "9.99", {"copies": 10, "ad_cost_per_sale": "1.00", "proof_costs": "5.00"})["scenario"]
    assert sc["customer_sales_revenue"] == "99.90" and sc["royalties"] == "31.54" and sc["estimated_profit"] == "16.54"
    assert r["expanded_distribution"]["enabled"] is False


def test_fixture_F_ai_generated_stays_ai_generated_through_edits(studio):
    pid = make_small_book(studio)
    a = studio.import_asset(pid, "gen.png", line_art_png(seed=3), {
        "source_type": "ai_generated", "rights_declaration": "unknown",
        "generation": {"provider": "openai", "model": "gpt-image-1", "prompt": "turtle"}})
    assert a["ai_involvement"] == "ai_generated"
    v = a["current_version_id"]
    v = studio.derive_version(v, {"type": "threshold", "level": 150})["id"]
    v = studio.derive_version(v, {"type": "cleanup", "min_area": 30})["id"]
    v = studio.derive_version(v, {"type": "erase", "shapes": [{"shape": "rect", "x": 0.1, "y": 0.1, "w": 0.1, "h": 0.1}]})["id"]
    page = [p for p in studio.pages(pid) if p["kind"] == "illustration"][0]
    studio.save_elements(page["id"], [{"kind": "image", "asset_version_id": v, "x": 1, "y": 1, "w": 5, "crop": {"l": 0.1, "t": 0.1, "r": 0, "b": 0}}])
    ver = studio.version(v)
    assert ver["ai_involvement"] == "ai_generated" and ver["version_no"] == 4
    with pytest.raises(Conflict):
        studio.update_asset_provenance(a["id"], {"ai_involvement": "none"})
    d = disclosure(build_snapshot(studio, pid))
    assert d["images"]["interior"]["ai_generated"] == 1 and "YES" in d["images"]["interior"]["proposed_answer"]
    cover = studio.derive_cover_art(v)
    assert cover["ai_involvement"] == "ai_generated" and cover["generation"]["derived_from_version"] == v
    # the original import is still there, unchanged
    orig = studio.asset(a["id"])["versions"][0]
    assert orig["operation"]["type"] == "original_import" and studio.storage.exists(orig["storage_key"])


def test_upload_validation(studio):
    pid = studio.create_project("u", {"illustration_count": 1})
    with pytest.raises(UploadRejected, match="SVG"):
        studio.import_asset(pid, "x.svg", b'<?xml version="1.0"?><svg onload="alert(1)"></svg>')
    with pytest.raises(UploadRejected, match="Only PNG and JPEG"):
        studio.import_asset(pid, "x.png", b"GIF89a....")
    with pytest.raises(UploadRejected, match="empty"):
        studio.import_asset(pid, "x.png", b"")
    good = line_art_png(400, 400)
    with pytest.raises(UploadRejected):
        studio.import_asset(pid, "trunc.png", good[: len(good) // 2])
    # decompression bomb: tiny file, enormous declared dimensions
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", 30000, 30000, 1, 0, 0, 0, 0)
    bomb = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\x00" * 1000)) + chunk(b"IEND", b"")
    with pytest.raises(UploadRejected, match="limit"):
        studio.import_asset(pid, "bomb.png", bomb)
    studio.settings.max_upload_bytes = 1000
    with pytest.raises(UploadRejected, match="larger"):
        studio.import_asset(pid, "big.png", good)
    studio.settings.max_upload_bytes = 40 * 1024 * 1024
    a = studio.import_asset(pid, "../../etc/pass wd<>.png", good, OWNER_DECL)
    assert a["display_name"] == "pass wd_.png"
    assert safe_display_name("..\\..\\x.png") == "x.png"
    with pytest.raises(ValueError):
        studio.storage.path("../../outside")
    # JPEG with transparency-free content and RGBA PNG are flattened onto white
    rgba = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    buf = io.BytesIO(); rgba.save(buf, "PNG")
    t = studio.import_asset(pid, "t.png", buf.getvalue(), OWNER_DECL)
    from cbs.imaging import open_flat
    assert open_flat(studio.version_bytes(t["current_version_id"])).getpixel((5, 5)) == (255, 255, 255)
    # invalid provenance values are refused; rights are never inferred from file names
    with pytest.raises(ValueError):
        studio.import_asset(pid, "licensed-by-disney.png", good, {"rights_declaration": "yes"})
    assert studio.import_asset(pid, "public-domain-owned.png", good)["rights_declaration"] == "unknown"
