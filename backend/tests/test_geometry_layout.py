"""Units, trim/bleed geometry, margins, cover maths, page assembly and stale-cover invalidation."""
import pytest

from cbs.geometry import (Rect, cover_geometry, effective_dpi_for, fit_element, min_gutter, min_outside, page_geometry,
                          resolve_config, rotated_bounds)
from cbs.layout import assemble
from cbs.studio import DEFAULT_SPEC
from cbs.units import effective_dpi, in_to_mm, in_to_pt, mm_to_in, pt_to_in, px_to_in

from conftest import make_small_book


def test_unit_conversions():
    assert in_to_pt(8.5) == 612 and in_to_pt(11) == 792
    assert pt_to_in(72) == 1
    assert in_to_mm(1) == pytest.approx(25.4)
    assert mm_to_in(3.2) == pytest.approx(0.125984, abs=1e-6)
    assert px_to_in(3000, 300) == 10
    assert effective_dpi(1024, 8) == 128


def _pages(n_intro, n_illus):
    return [{"id": f"i{k}", "kind": "intro"} for k in range(n_intro)] + [{"id": f"p{k}", "kind": "illustration"} for k in range(n_illus)]


def test_fixture_A_default_book_84_pages_612x792():
    spec = dict(DEFAULT_SPEC)
    asm = assemble(_pages(4, 40), spec)
    assert asm["page_count"] == 84
    cfg = resolve_config(spec)
    for e in asm["pages"]:
        g = page_geometry(cfg, e["number"], 84)
        assert (in_to_pt(g.media_w), in_to_pt(g.media_h)) == (612, 792)
    # illustrations on 5,7,9,... with blank reverses 6,8,10,...
    kinds = {e["number"]: e["kind"] for e in asm["pages"]}
    assert all(kinds[n] == "illustration" for n in range(5, 84, 2))
    assert all(kinds[n] == "blank" for n in range(6, 85, 2))
    assert asm["blank_count"] == 40


def test_fixture_B_full_bleed_621x810_and_outside_edges():
    cfg = resolve_config({**DEFAULT_SPEC, "interior_bleed": True})
    odd, even = page_geometry(cfg, 5, 84), page_geometry(cfg, 6, 84)
    assert (in_to_pt(odd.media_w), in_to_pt(odd.media_h)) == (621, 810)
    assert (in_to_pt(even.media_w), in_to_pt(even.media_h)) == (621, 810)
    # recto: trim starts at left edge (bleed on the outside = right); verso: bleed on the left
    assert odd.trim_origin_x == 0 and even.trim_origin_x == 0.125
    assert odd.trim_origin_y == even.trim_origin_y == 0.125
    assert odd.inside_edge == "left" and even.inside_edge == "right"
    assert odd.outside_margin >= 0.375  # bleed minimum outside margin


def test_margins_and_safe_area():
    assert min_gutter(84) == 0.375 and min_gutter(151) == 0.5 and min_gutter(828) == 0.875
    assert min_outside(False) == 0.25 and min_outside(True) == 0.375
    cfg = resolve_config(DEFAULT_SPEC)
    g = page_geometry(cfg, 5, 84)
    assert (g.safe.x, g.safe.y, g.safe.w, g.safe.h) == (0.5, 0.5, 7.5, 10.0)
    cfg2 = resolve_config({**DEFAULT_SPEC, "safe_margin_in": 0.25})
    g2 = page_geometry(cfg2, 5, 400)  # gutter band 301-500 = 0.625 overrides the smaller safe margin
    assert g2.inside_margin == 0.625 and g2.safe.x == 0.625


def test_fixture_C_cover_geometry():
    cfg = resolve_config(DEFAULT_SPEC)
    g = cover_geometry(cfg, 84)
    assert g["spine_width_in"] == pytest.approx(0.189168, abs=1e-9)
    assert g["full_width_in"] == pytest.approx(17.439168, abs=1e-6)
    assert g["full_height_in"] == pytest.approx(11.25, abs=1e-9)
    # spine text: page rule (>79) passes, but 0.189 in spine minus 2×0.0625 clearances is too narrow
    assert g["spine_text"]["page_rule_ok"] and not g["spine_text"]["fits"] and not g["spine_text"]["eligible"]
    # barcode reservation: lower right of back cover, 0.25 from trim and spine
    b = g["barcode"]
    assert b["w"] == 2.0 and b["h"] == 1.2
    assert b["x"] + b["w"] == pytest.approx(0.125 + 8.5 - 0.25)
    assert b["y"] + b["h"] == pytest.approx(0.125 + 11 - 0.25)
    assert cover_geometry(cfg, 300)["spine_text"]["eligible"]


def test_unsupported_configs_rejected():
    from cbs.geometry import UnsupportedConfiguration
    with pytest.raises(UnsupportedConfiguration):
        resolve_config({**DEFAULT_SPEC, "trim": "5x8"})
    with pytest.raises(UnsupportedConfiguration):
        resolve_config({**DEFAULT_SPEC, "binding": "hardcover"})


def test_parity_blank_for_odd_intro_and_even_total():
    asm = assemble(_pages(3, 5), DEFAULT_SPEC)
    assert asm["pages"][3]["kind"] == "blank" and asm["pages"][3]["blank_reason"] == "parity"
    assert all(e["number"] % 2 == 1 for e in asm["pages"] if e["kind"] == "illustration")
    assert asm["page_count"] % 2 == 0 and asm["parity_notes"]
    asm2 = assemble(_pages(3, 4), {**DEFAULT_SPEC, "blank_backs": False})  # 7 pages -> end blank
    assert asm2["page_count"] % 2 == 0 and asm2["pages"][-1]["blank_reason"] == "end"


def test_reorder_remove_keep_blank_backs_and_invalidate_cover(studio):
    pid = make_small_book(studio)
    assert studio.assembly(pid)["page_count"] == 24
    assert not studio.cover(pid)["stale"]
    pages = studio.pages(pid)
    ids = [p["id"] for p in pages]
    # move last illustration to be first illustration
    new = ids[:4] + [ids[-1]] + ids[4:-1]
    studio.reorder_pages(pid, new)
    asm = studio.assembly(pid)
    assert asm["pages"][4]["page_id"] == ids[-1] and asm["pages"][5]["kind"] == "blank"
    assert not studio.cover(pid)["stale"]  # order change does not change page count
    studio.delete_page(ids[5])
    asm = studio.assembly(pid)
    assert asm["page_count"] == 22
    for e in asm["pages"]:
        if e["kind"] == "illustration":
            assert e["number"] % 2 == 1 and asm["pages"][e["number"]]["kind"] == "blank"
    c = studio.cover(pid)
    assert c["stale"] and "24 to 22" in c["stale_reasons"][0]
    c2 = studio.recalc_cover(pid)
    assert not c2["stale"] and c2["geometry"]["page_count"] == 24  # min 24 used for geometry; preflight flags <24
    studio.duplicate_page(ids[6])
    assert studio.assembly(pid)["page_count"] == 24


def test_fit_and_rotation_bounds():
    v = {"width_px": 2000, "height_px": 1000}
    el = {"kind": "image", "x": 0, "y": 0, "w": 1, "rotation": 90, "crop": {}}
    out = fit_element(el, v, Rect(0.5, 0.5, 7.5, 10))
    r = rotated_bounds(Rect(out["x"], out["y"], out["w"], out["w"] / 2), 90)
    assert Rect(0.5, 0.5, 7.5, 10).contains(r)
    assert out["w"] == pytest.approx(10.0)  # long side fills the page height after rotation


def test_crop_changes_effective_dpi():
    v = {"width_px": 3000, "height_px": 3000}
    full = effective_dpi_for({"kind": "image", "x": 0, "y": 0, "w": 7.5, "crop": {}}, v)
    half = effective_dpi_for({"kind": "image", "x": 0, "y": 0, "w": 7.5, "crop": {"l": 0.25, "r": 0.25}}, v)
    assert full == pytest.approx(400) and half == pytest.approx(200)
