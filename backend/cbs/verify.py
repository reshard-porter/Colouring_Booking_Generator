"""Post-export verification of the ACTUAL files (not the UI state)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from pypdf import PdfReader

TOL_PT = 0.01


def _fonts_embedded(reader: PdfReader) -> tuple[list[str], list[str]]:
    embedded, missing = set(), set()
    for page in reader.pages:
        res = page.get("/Resources")
        if not res:
            continue
        res = res.get_object()
        fonts = res.get("/Font")
        if not fonts:
            continue
        for _, ref in fonts.get_object().items():
            f = ref.get_object()
            name = str(f.get("/BaseFont"))
            desc = f.get("/FontDescriptor")
            if desc is None and f.get("/DescendantFonts"):
                desc = f["/DescendantFonts"][0].get_object().get("/FontDescriptor")
            desc = desc.get_object() if desc is not None else None
            if desc is not None and any(k in desc for k in ("/FontFile", "/FontFile2", "/FontFile3")):
                embedded.add(name)
            else:
                missing.add(name)
    return sorted(embedded), sorted(missing)


def verify_interior(path: Path, expected_pages: int, expected_media_pt: list[tuple[float, float]],
                    blank_pages: list[int], expected_trim_pt: tuple[float, float]) -> dict:
    errors, info = [], {}
    reader = PdfReader(str(path))
    n = len(reader.pages)
    info["page_count"] = n
    if n != expected_pages:
        errors.append(f"Expected {expected_pages} pages, found {n}.")
    sizes = set()
    for i, page in enumerate(reader.pages):
        mb = page.mediabox
        w, h = float(mb.width), float(mb.height)
        sizes.add((round(w, 3), round(h, 3)))
        if i < len(expected_media_pt):
            ew, eh = expected_media_pt[i]
            if abs(w - ew) > TOL_PT or abs(h - eh) > TOL_PT:
                errors.append(f"Page {i + 1} is {w}×{h} pt; expected {ew}×{eh} pt.")
        tb = page.trimbox
        if abs(float(tb.width) - expected_trim_pt[0]) > TOL_PT or abs(float(tb.height) - expected_trim_pt[1]) > TOL_PT:
            errors.append(f"Page {i + 1} TrimBox is {float(tb.width)}×{float(tb.height)} pt.")
        if page.get("/Rotate", 0):
            errors.append(f"Page {i + 1} has a /Rotate entry.")
    info["page_sizes_pt"] = sorted(sizes)
    embedded, missing = _fonts_embedded(reader)
    info["fonts_embedded"], info["fonts_not_embedded"] = embedded, missing
    if missing:
        errors.append(f"Fonts not embedded: {missing}")
    # Render-based checks: blank pages are truly white; nothing but black/gray ink appears.
    doc = pdfium.PdfDocument(str(path))
    nonwhite_blank = []
    color_pages = []
    for i in range(n):
        im = doc[i].render(scale=20 / 72).to_pil().convert("RGB")
        a = np.asarray(im).astype(np.int16)
        if (i + 1) in blank_pages and (a < 250).any():
            nonwhite_blank.append(i + 1)
        sat = (a.max(axis=2) - a.min(axis=2))
        if (sat > 12).mean() > 0.0005:
            color_pages.append(i + 1)
    doc.close()
    if nonwhite_blank:
        errors.append(f"Intentional blank pages contain marks: {nonwhite_blank}")
    if color_pages:
        errors.append(f"Color found on black-ink interior pages: {color_pages[:10]}")
    info["blank_pages_verified"] = len(blank_pages) - len(nonwhite_blank)
    info["file_size_bytes"] = path.stat().st_size
    if info["file_size_bytes"] > 650 * 1024 * 1024:
        errors.append("Interior PDF exceeds 650 MB.")
    return {"ok": not errors, "errors": errors, "info": info}


def verify_cover(path: Path, expected_w_pt: float, expected_h_pt: float, barcode_rect_pt: tuple[float, float, float, float]) -> dict:
    errors, info = [], {}
    reader = PdfReader(str(path))
    if len(reader.pages) != 1:
        errors.append(f"Cover must be a single page; found {len(reader.pages)}.")
    p = reader.pages[0]
    w, h = float(p.mediabox.width), float(p.mediabox.height)
    info["size_pt"] = [w, h]
    info["size_in"] = [round(w / 72, 6), round(h / 72, 6)]
    if abs(w - expected_w_pt) > TOL_PT or abs(h - expected_h_pt) > TOL_PT:
        errors.append(f"Cover is {w}×{h} pt; expected {expected_w_pt}×{expected_h_pt} pt.")
    embedded, missing = _fonts_embedded(reader)
    info["fonts_embedded"], info["fonts_not_embedded"] = embedded, missing
    if missing:
        errors.append(f"Fonts not embedded: {missing}")
    # barcode area must render as plain white
    doc = pdfium.PdfDocument(str(path))
    scale = 50 / 72
    im = doc[0].render(scale=scale).to_pil().convert("RGB")
    doc.close()
    x, y, bw, bh = barcode_rect_pt
    H = im.height
    box = (int(x * scale) + 2, int(H - (y + bh) * scale) + 2, int((x + bw) * scale) - 2, int(H - y * scale) - 2)
    a = np.asarray(im.crop(box))
    info["barcode_area_white"] = bool((a >= 250).all())
    if not info["barcode_area_white"]:
        errors.append("Barcode reservation area is not plain white.")
    info["file_size_bytes"] = path.stat().st_size
    if info["file_size_bytes"] > 40 * 1024 * 1024:
        errors.append("Cover PDF exceeds 40 MB.")
    return {"ok": not errors, "errors": errors, "info": info}
