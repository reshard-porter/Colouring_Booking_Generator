"""Master style suffix, fine-detail cleanup and the adult pen-and-ink preset."""
import numpy as np
from PIL import Image, ImageDraw

from cbs import generation, preflight
from cbs.imaging import print_ready
from cbs.snapshot import build_snapshot

MASTER = ("Black-and-white adult coloring book page, pure white background, no grayscale shading, intricate indie pen-and-ink "
          "line art, 0.1mm Micron fineliner style, delicate botanical stippling and organic woodgrain cross-hatching, crisp "
          "enclosed shapes, vertical 8.5x11 aspect ratio, full-page margin-to-margin composition.")


def test_master_style_is_appended_verbatim_and_replaces_builtin_style(studio):
    pid = studio.create_project("Adult", {"title": "Forest Dreams", "audience": "Adults", "age_min": None, "age_max": None})
    generation.plan_from_description(studio, pid, "Original woodland animals in an enchanted forest, detailed and calming.", 12)
    studio.update_style_guide(pid, {"master_style": MASTER, "cleanup_mode": "fine"})
    scene = studio.scenes(pid)[0]
    p = generation.build_prompt(studio.spec(pid), studio.style_guide(pid), scene)
    assert p.rstrip().endswith(MASTER)                     # at the very end, word for word
    assert "no hatching or stippling" not in p and "Keep a clean white margin" not in p  # no contradicting built-in rules
    assert "Original characters only" in p and "no text" in p and "BOOK DESCRIPTION" in p
    ref = generation.build_prompt(studio.spec(pid), studio.style_guide(pid), scene, with_reference=True)
    assert ref.startswith("Image 1 is a STYLE REFERENCE") and ref.rstrip().endswith(MASTER)
    assert MASTER not in generation.build_cover_prompt(studio.spec(pid), studio.style_guide(pid))  # cover is full color
    # without a master style, the built-in kids' rules apply
    studio.update_style_guide(pid, {"master_style": ""})
    assert "no hatching or stippling" in generation.build_prompt(studio.spec(pid), studio.style_guide(pid), scene)


def test_master_style_limits_and_protected_names(studio):
    import pytest
    pid = studio.create_project("x", {})
    with pytest.raises(ValueError, match="3000"):
        studio.update_style_guide(pid, {"master_style": "x" * 3001})
    with pytest.raises(ValueError):
        studio.update_style_guide(pid, {"cleanup_mode": "medium"})
    studio.update_style_guide(pid, {"master_style": "in the style of Studio Ghibli"})
    s = studio.save_scene(pid, {"subject": "an original fox", "action": "sleeping", "setting": "forest"})
    est = generation.estimate(studio, pid, 1, {}, [s["id"]])
    assert any("Studio Ghibli" in p or "studio ghibli" in p.lower() for p in est["problems"])


def _stipple_image():
    im = Image.new("L", (2400, 3200), 255)
    d = ImageDraw.Draw(im)
    d.ellipse([400, 400, 2000, 2800], outline=0, width=6)
    rng = np.random.default_rng(3)
    for x, y in rng.integers(700, 1700, size=(400, 2)):
        d.ellipse([x, y, x + 3, y + 3], fill=0)  # ~4 px stipple dots
    return im


def _count_dots(im):
    from scipy import ndimage
    a = np.asarray(im) < 128
    lab, n = ndimage.label(a)
    sizes = ndimage.sum(a, lab, index=np.arange(1, n + 1))
    return int(((sizes >= 4) & (sizes <= 40)).sum())


def test_fine_cleanup_keeps_stippling_bold_removes_it():
    src = _stipple_image()
    before = _count_dots(src)
    fine = print_ready(src, fine=True)
    bold = print_ready(src, fine=False)
    assert before > 300
    assert _count_dots(fine) >= before * 0.95
    assert _count_dots(bold) < before * 0.1


def test_adult_preset_sets_fine_mode_and_relaxes_kid_heuristics(studio):
    pid = studio.create_project("Adult2", {"title": "Botanica"})
    sg = studio.apply_style_preset(pid, "adult_pen_ink")
    assert sg["cleanup_mode"] == "fine" and "tiny repeating patterns" not in sg["avoid"]
    studio.update_style_guide(pid, {"master_style": MASTER})
    sg = studio.apply_style_preset(pid, "classic_cartoon")
    assert sg["cleanup_mode"] == "fine"  # kept, because a master style is set
    studio.update_style_guide(pid, {"master_style": ""})
    assert studio.apply_style_preset(pid, "classic_cartoon")["cleanup_mode"] == "bold"
    # preflight does not flag "tiny regions" for fine-detail books
    studio.apply_style_preset(pid, "adult_pen_ink")
    page = [p for p in studio.pages(pid) if p["kind"] == "illustration"][0]
    from cbs.imaging import to_png_bytes
    a = studio.import_asset(pid, "intricate.png", to_png_bytes(_stipple_image()),
                            {"source_type": "user_created", "rights_declaration": "owner_declared", "ai_involvement": "none"})
    studio.place_asset(page["id"], a["current_version_id"])
    rep = preflight.run(studio, build_snapshot(studio, pid))
    assert not any(f["code"] == "tiny_regions" for f in rep["findings"])
