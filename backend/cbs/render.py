"""PDF rendering. The SAME draw functions produce production PDFs and on-screen previews.

Production output never contains guides, crop marks, overlays or watermarks: those exist only in
the browser UI (and on the clearly labelled contact sheet, which is not an upload file).
"""
from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from .config import FONT_DIR
from .geometry import (PrintConfig, Rect, crop_px, element_rect, page_geometry, to_pdf_rect, image_rect)
from .imaging import open_flat
from .units import in_to_pt

FONT_REGULAR = "CBS-Sans"
FONT_BOLD = "CBS-Sans-Bold"
_fonts_registered = False


def register_fonts():
    global _fonts_registered
    if not _fonts_registered:
        pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(FONT_DIR / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, str(FONT_DIR / "DejaVuSans-Bold.ttf")))
        _fonts_registered = True


class Cancelled(Exception):
    pass


# --- image loading ---------------------------------------------------------------------------

class ImageCache:
    """Loads asset versions by storage key, applies crop, flattens transparency on white paper,
    converts for the target ink and caps resolution (to keep files reasonable without harming lines)."""

    def __init__(self, read_bytes: Callable[[str], bytes]):
        self.read_bytes = read_bytes
        self._cache: dict = {}

    def get(self, version: dict, crop: dict | None, placed_w_in: float, mode: str, max_dpi: int) -> Image.Image:
        key = (version["sha256"], tuple(sorted((crop or {}).items())), round(placed_w_in, 4), mode, max_dpi)
        if key in self._cache:
            return self._cache[key]
        im = open_flat(self.read_bytes(version["storage_key"]))
        box = crop_px(im.width, im.height, crop)
        im = im.crop(box)
        im = im.convert("L") if mode == "L" else im.convert("RGB")
        target_w = int(math.ceil(placed_w_in * max_dpi))
        if im.width > target_w * 1.02:
            im = im.resize((target_w, max(1, round(im.height * target_w / im.width))), Image.LANCZOS)
        if len(self._cache) > 12:
            self._cache.clear()
        self._cache[key] = im
        return im


# --- text ------------------------------------------------------------------------------------

def wrap_text(text: str, bold: bool, size_pt: float, width_pt: float) -> list[str]:
    register_fonts()
    font = FONT_BOLD if bold else FONT_REGULAR
    lines: list[str] = []
    for para in (text or "").split("\n"):
        if not para.strip():
            lines.append("")
            continue
        lines.extend(simpleSplit(para, font, size_pt, width_pt) or [""])
    return lines


def text_fits(el: dict) -> bool:
    lines = wrap_text(el.get("text", ""), el.get("bold", False), float(el.get("size_pt", 12)), in_to_pt(float(el["w"])))
    return len(lines) * float(el.get("size_pt", 12)) * 1.25 <= in_to_pt(float(el["h"])) + 0.5


def draw_text_box(c: Canvas, x_pt, y_top_pt, w_pt, h_pt, text, size, bold, align, color=black):
    register_fonts()
    font = FONT_BOLD if bold else FONT_REGULAR
    lines = wrap_text(text, bold, size, w_pt)
    leading = size * 1.25
    c.setFillColor(color)
    c.setFont(font, size)
    y = y_top_pt - size * 0.95
    for ln in lines:
        if align == "center":
            c.drawCentredString(x_pt + w_pt / 2, y, ln)
        elif align == "right":
            c.drawRightString(x_pt + w_pt, y, ln)
        else:
            c.drawString(x_pt, y, ln)
        y -= leading


STORY_MAX_PT, STORY_MIN_PT, STORY_LEADING = 16.0, 10.0, 1.4


def layout_story(text: str, title: str, w_pt: float, h_pt: float) -> dict | None:
    """Largest body size (16 → 10 pt) at which the title and story fit the safe area; None if it doesn't fit at 10 pt."""
    title = (title or "").strip()
    paras = [p.strip() for p in re.split(r"\n\s*\n", (text or "").strip()) if p.strip()]
    size = STORY_MAX_PT
    while size >= STORY_MIN_PT - 1e-6:
        tpt = round(size * 1.5, 1)
        tlines = wrap_text(title, True, tpt, w_pt) if title else []
        used = len(tlines) * tpt * 1.2 + (size * 1.2 if tlines else 0)
        blines: list[list[str]] = []
        for para in paras:
            blines.append(wrap_text(para.replace("\n", " "), False, size, w_pt))
        used += sum(len(b) for b in blines) * size * STORY_LEADING + max(len(blines) - 1, 0) * size * 0.7
        if used <= h_pt:
            return {"title_pt": tpt, "body_pt": size, "title_lines": tlines, "paragraphs": blines, "height_pt": used}
        size = round(size - 0.5, 1)
    return None


def draw_story_page(c: Canvas, geo, story: dict | None):
    """Story text on the left page facing its illustration: optional bold title, then paragraphs, top-aligned in the safe area."""
    if not story or not (story.get("text") or "").strip():
        return []
    x, y, w, h = to_pdf_rect(geo, geo.safe)
    lay = layout_story(story["text"], story.get("title", ""), w, h)
    overflow = lay is None
    if overflow:  # draw at the minimum size and stop at the bottom margin; preflight reports it as an error
        size = STORY_MIN_PT
        lay = {"title_pt": size * 1.5, "body_pt": size,
               "title_lines": wrap_text(story.get("title", ""), True, size * 1.5, w) if story.get("title") else [],
               "paragraphs": [wrap_text(p.replace("\n", " "), False, size, w) for p in re.split(r"\n\s*\n", story["text"].strip()) if p.strip()]}
    register_fonts()
    c.setFillColor(black)
    top = y + h
    cur = top
    if lay["title_lines"]:
        c.setFont(FONT_BOLD, lay["title_pt"])
        for ln in lay["title_lines"]:
            cur -= lay["title_pt"] * 1.2
            c.drawCentredString(x + w / 2, cur + lay["title_pt"] * 0.25, ln)
        cur -= lay["body_pt"] * 1.2
    c.setFont(FONT_REGULAR, lay["body_pt"])
    lead = lay["body_pt"] * STORY_LEADING
    for k, para in enumerate(lay["paragraphs"]):
        for ln in para:
            if cur - lead < y - 0.5:
                break
            cur -= lead
            c.drawString(x, cur + lay["body_pt"] * 0.3, ln)
        cur -= lay["body_pt"] * 0.7
    return [{"story": True, "body_pt": lay["body_pt"], "overflow": overflow}]


def fit_font_size(text, bold, max_pt, min_pt, w_pt, h_pt, max_lines=3) -> float:
    size = max_pt
    while size > min_pt:
        lines = wrap_text(text, bold, size, w_pt)
        if len(lines) <= max_lines and len(lines) * size * 1.25 <= h_pt:
            return size
        size -= 1
    return min_pt


# --- interior pages --------------------------------------------------------------------------

def _set_boxes(c: Canvas, geo):
    tx0 = in_to_pt(geo.trim_origin_x)
    ty0 = in_to_pt(geo.media_h - geo.trim_origin_y - geo.trim.h)
    trim = (tx0, ty0, tx0 + in_to_pt(geo.trim.w), ty0 + in_to_pt(geo.trim.h))
    media = (0, 0, in_to_pt(geo.media_w), in_to_pt(geo.media_h))
    c.setTrimBox(trim)
    c.setBleedBox(media)
    c.setCropBox(media)


def draw_interior_page(c: Canvas, cfg: PrintConfig, page_count: int, entry: dict, snapshot: dict, images: ImageCache):
    geo = page_geometry(cfg, entry["number"], max(page_count, 24))
    c.setPageSize((in_to_pt(geo.media_w), in_to_pt(geo.media_h)))
    _set_boxes(c, geo)
    if entry["kind"] == "blank":
        return []
    if entry["kind"] == "story":
        return draw_story_page(c, geo, entry.get("story"))
    placements = []
    for el in sorted(entry.get("elements", []), key=lambda e: e.get("z", 0)):
        if el["kind"] == "image":
            v = snapshot["versions"][el["asset_version_id"]]
            r = image_rect(el, v["width_px"], v["height_px"])
            x, y, w, h = to_pdf_rect(geo, r)
            im = images.get(v, el.get("crop"), r.w, "L", 600)
            c.saveState()
            c.translate(x + w / 2, y + h / 2)
            rot = float(el.get("rotation", 0) or 0)
            if rot:
                c.rotate(-rot)
            c.drawImage(ImageReader(im), -w / 2, -h / 2, w, h)
            c.restoreState()
            placements.append({"element_id": el.get("id"), "asset_version_id": el["asset_version_id"],
                               "asset_id": v["asset_id"], "sha256": v["sha256"], "rect_in": r.d(), "rotation": rot,
                               "crop": el.get("crop"), "embedded_px": [im.width, im.height]})
        elif el["kind"] == "text":
            r = Rect(float(el["x"]), float(el["y"]), float(el["w"]), float(el["h"]))
            x, y, w, h = to_pdf_rect(geo, r)
            draw_text_box(c, x, y + h, w, h, el.get("text", ""), float(el.get("size_pt", 12)), bool(el.get("bold")),
                          el.get("align", "left"))
            placements.append({"element_id": el.get("id"), "text": True, "rect_in": r.d()})
        elif el["kind"] == "shape":
            r = Rect(float(el["x"]), float(el["y"]), float(el["w"]), float(el.get("h", 0)))
            x, y, w, h = to_pdf_rect(geo, r)
            c.setStrokeColor(black)
            c.setLineWidth(float(el.get("stroke_pt", 2.5)))
            if el.get("shape") == "line":
                c.line(x, y + h, x + w, y)
            else:
                c.roundRect(x, y, w, h, min(w, h) * 0.08, stroke=1, fill=0)
            placements.append({"element_id": el.get("id"), "shape": el.get("shape"), "rect_in": r.d()})
    return placements


def render_interior(snapshot: dict, read_bytes, out_path: Path, progress=None, cancelled=None) -> list[dict]:
    register_fonts()
    cfg = PrintConfig(**snapshot["config"])
    asm = snapshot["assembly"]
    c = Canvas(str(out_path), pageCompression=1, invariant=1, initialFontName=FONT_REGULAR)
    c.setTitle(snapshot["spec"]["title"])
    c.setAuthor(snapshot["spec"].get("author", ""))
    c.setCreator("Coloring Book Studio")
    c.setProducer("Coloring Book Studio (ReportLab)")
    images = ImageCache(read_bytes)
    manifest = []
    total = len(asm["pages"])
    for i, entry in enumerate(asm["pages"]):
        if cancelled and cancelled():
            raise Cancelled()
        placements = draw_interior_page(c, cfg, asm["page_count"], entry, snapshot, images)
        c.showPage()
        manifest.append({"pdf_page": entry["number"], "kind": entry["kind"], "blank_reason": entry.get("blank_reason"),
                         "page_id": entry.get("page_id") or entry.get("story_for"), "placements": placements})
        if progress:
            progress((i + 1) / total, f"Interior page {i + 1} of {total}")
    c.save()
    return manifest


def render_interior_page_png(snapshot: dict, read_bytes, page_number: int, dpi: int = 60) -> bytes:
    """Preview of one page using the exact production drawing code, rasterized with PDFium."""
    register_fonts()
    cfg = PrintConfig(**snapshot["config"])
    asm = snapshot["assembly"]
    entry = asm["pages"][page_number - 1]
    buf = io.BytesIO()
    c = Canvas(buf, pageCompression=1, initialFontName=FONT_REGULAR)
    draw_interior_page(c, cfg, asm["page_count"], entry, snapshot, ImageCache(read_bytes))
    c.showPage()
    c.save()
    return rasterize_pdf_page(buf.getvalue(), 0, dpi)


def rasterize_pdf_page(pdf: bytes | str | Path, index: int, dpi: int) -> bytes:
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(pdf if not isinstance(pdf, Path) else str(pdf))
    try:
        page = doc[index]
        bmp = page.render(scale=dpi / 72)
        im = bmp.to_pil()
        out = io.BytesIO()
        im.save(out, "PNG")
        return out.getvalue()
    finally:
        doc.close()


# --- cover ---------------------------------------------------------------------------------

def _hex(s, default="#ffffff"):
    try:
        return HexColor(s or default)
    except Exception:  # noqa: BLE001
        return HexColor(default)


def cover_layout(snapshot: dict) -> dict:
    """Deterministic placement of every cover element, in inches from the cover's top-left."""
    cv = snapshot["cover"]
    d, g = cv["data"], cv["geometry"]
    spec = snapshot["spec"]
    title = d.get("title") or spec["title"]
    subtitle = d.get("subtitle") if d.get("subtitle") is not None else spec.get("subtitle", "")
    author = d.get("author") or spec.get("author", "")
    fs, bs, bc = (Rect(**g[k]) for k in ("front_safe", "back_safe", "barcode"))
    title_box = Rect(fs.x + 0.1, fs.y + 0.15, fs.w - 0.2, 2.0)
    title_pt = fit_font_size(title, True, float(d.get("title_pt", 54)), 18, in_to_pt(title_box.w - 0.3), in_to_pt(title_box.h - 0.2), 3)
    tlines = wrap_text(title, True, title_pt, in_to_pt(title_box.w - 0.3))
    title_h = (len(tlines) * title_pt * 1.25) / 72 + 0.35
    title_box = Rect(title_box.x, title_box.y, title_box.w, title_h)
    sub_pt = float(d.get("subtitle_pt", 22))
    sub_box = Rect(fs.x, title_box.y2 + 0.15, fs.w, (len(wrap_text(subtitle, False, sub_pt, in_to_pt(fs.w))) * sub_pt * 1.25) / 72 + 0.05) if subtitle else Rect(fs.x, title_box.y2, fs.w, 0)
    author_pt = float(d.get("author_pt", 20))
    author_box = Rect(fs.x, fs.y2 - 0.55, fs.w, 0.5)
    art_area = Rect(fs.x, sub_box.y2 + 0.2, fs.w, author_box.y - 0.15 - (sub_box.y2 + 0.2))
    art = None
    if d.get("front_art_version_id") and d["front_art_version_id"] in snapshot["versions"]:
        v = snapshot["versions"][d["front_art_version_id"]]
        aspect = v["height_px"] / v["width_px"]
        w = min(art_area.w, art_area.h / aspect) * float(d.get("art_scale", 1.0))
        h = w * aspect
        art = Rect(art_area.x + (art_area.w - w) / 2 + float(d.get("art_offset_x", 0)),
                   art_area.y + (art_area.h - h) / 2 + float(d.get("art_offset_y", 0)), w, h)
    copy_pt = float(d.get("back_copy_pt", 15))
    back_copy_box = Rect(bs.x + 0.1, bs.y + 0.2, bs.w - 0.2, min(bs.h * 0.5, bc.y - bs.y - 0.4))
    thumbs = []
    ids = [x for x in d.get("back_thumbnail_version_ids", []) if x in snapshot["versions"]][:4]
    if ids:
        gap = 0.2
        tw = (bs.w - gap * (len(ids) - 1)) / max(len(ids), 3)
        th = tw * 11 / 8.5
        ty = min(back_copy_box.y2 + 0.3, bc.y - 0.3 - th)
        total_w = tw * len(ids) + gap * (len(ids) - 1)
        x0 = bs.x + (bs.w - total_w) / 2
        for i, vid in enumerate(ids):
            thumbs.append({"version_id": vid, "rect": Rect(x0 + i * (tw + gap), ty, tw, th)})
    back_art = None
    if d.get("back_art_version_id") and d["back_art_version_id"] in snapshot["versions"]:
        v = snapshot["versions"][d["back_art_version_id"]]
        lines = wrap_text(d.get("back_copy", ""), False, copy_pt, in_to_pt(back_copy_box.w)) if (d.get("back_copy") or "").strip() else []
        top = back_copy_box.y + (len(lines) * copy_pt * 1.25) / 72 + (0.3 if lines else 0)
        area = Rect(bs.x, top, bs.w, max(0.5, bc.y - 0.25 - top))
        aspect = v["height_px"] / v["width_px"]
        w = min(area.w, area.h / aspect)
        h = w * aspect
        back_art = Rect(area.x + (area.w - w) / 2, area.y + (area.h - h) / 2, w, h)
        thumbs = []  # a back-cover illustration replaces the sample-page thumbnails
    spine_text = None
    if d.get("spine_text_enabled") and g["spine_text"]["eligible"]:
        ss = Rect(**g["spine_safe"])
        spine_text = {"text": d.get("spine_text") or f"{title}  •  {author}", "rect": ss, "size_pt": float(d.get("spine_text_pt", 10))}
    return {"title": title, "title_pt": title_pt, "title_box": title_box, "subtitle": subtitle, "subtitle_pt": sub_pt,
            "subtitle_box": sub_box, "author": author, "author_pt": author_pt, "author_box": author_box,
            "art_area": art_area, "art": art, "back_copy": d.get("back_copy", ""), "back_copy_pt": copy_pt,
            "back_copy_box": back_copy_box, "thumbs": thumbs, "back_art": back_art, "barcode": bc, "spine_text": spine_text}


def cover_layout_json(snapshot: dict) -> dict:
    L = cover_layout(snapshot)
    out = {}
    for k, v in L.items():
        if isinstance(v, Rect):
            out[k] = v.d()
        elif k == "thumbs":
            out[k] = [{"version_id": t["version_id"], "rect": t["rect"].d()} for t in v]
        elif k == "spine_text" and v:
            out[k] = {**v, "rect": v["rect"].d()}
        else:
            out[k] = v
    return out


def render_cover(snapshot: dict, read_bytes, out_path, *, dpi_cap: int = 400) -> dict:
    register_fonts()
    g = snapshot["cover"]["geometry"]
    d = snapshot["cover"]["data"]
    L = cover_layout(snapshot)
    W, H = g["full_width_in"], g["full_height_in"]
    c = Canvas(str(out_path) if not isinstance(out_path, io.BytesIO) else out_path, pageCompression=1, invariant=1, initialFontName=FONT_REGULAR)
    c.setPageSize((in_to_pt(W), in_to_pt(H)))
    c.setTitle(f"{L['title']} – cover")
    c.setCreator("Coloring Book Studio")
    bleed = g["bleed_in"]
    c.setTrimBox((in_to_pt(bleed), in_to_pt(bleed), in_to_pt(W - bleed), in_to_pt(H - bleed)))
    c.setBleedBox((0, 0, in_to_pt(W), in_to_pt(H)))
    c.setCropBox((0, 0, in_to_pt(W), in_to_pt(H)))

    def R(r: Rect):  # cover inches (y down) -> pdf pts
        return in_to_pt(r.x), in_to_pt(H - r.y - r.h), in_to_pt(r.w), in_to_pt(r.h)

    bg, accent = _hex(d.get("background"), "#8fd3f4"), _hex(d.get("accent"), "#ffd166")
    c.setFillColor(bg)
    c.rect(0, 0, in_to_pt(W), in_to_pt(H), stroke=0, fill=1)
    # decorative sand band along the bottom (extends into bleed)
    c.setFillColor(accent)
    p = c.beginPath()
    p.moveTo(0, 0)
    p.lineTo(0, in_to_pt(1.1))
    steps = 60
    for i in range(steps + 1):
        x = W * i / steps
        p.lineTo(in_to_pt(x), in_to_pt(1.1 + 0.12 * math.sin(i / steps * math.pi * 10)))
    p.lineTo(in_to_pt(W), 0)
    p.close()
    c.drawPath(p, stroke=0, fill=1)
    images = ImageCache(read_bytes)
    if L["art"]:
        v = snapshot["versions"][d["front_art_version_id"]]
        x, y, w, h = R(L["art"])
        c.setFillColor(white)
        c.roundRect(x - 6, y - 6, w + 12, h + 12, 14, stroke=0, fill=1)
        c.drawImage(ImageReader(images.get(v, None, L["art"].w, "RGB", dpi_cap)), x, y, w, h)
    # title plate
    x, y, w, h = R(L["title_box"])
    c.setFillColor(white)
    c.setStrokeColor(accent)
    c.setLineWidth(4)
    c.roundRect(x, y, w, h, 18, stroke=1, fill=1)
    tb = L["title_box"]
    draw_text_box(c, x + in_to_pt(0.15), y + h - in_to_pt(0.17), w - in_to_pt(0.3), h, L["title"], L["title_pt"], True,
                  "center", _hex(d.get("title_color"), "#1d3557"))
    tc = _hex(d.get("text_color"), "#1d3557")
    if L["subtitle"]:
        x, y, w, h = R(L["subtitle_box"])
        draw_text_box(c, x, y + h, w, h, L["subtitle"], L["subtitle_pt"], False, "center", tc)
    x, y, w, h = R(L["author_box"])
    draw_text_box(c, x, y + h, w, h, L["author"], L["author_pt"], True, "center", tc)
    # back cover
    x, y, w, h = R(L["back_copy_box"])
    draw_text_box(c, x, y + h, w, h, L["back_copy"], L["back_copy_pt"], False, "left", tc)
    if L.get("back_art"):
        v = snapshot["versions"][d["back_art_version_id"]]
        x, y, w, h = R(L["back_art"])
        c.setFillColor(white)
        c.roundRect(x - 5, y - 5, w + 10, h + 10, 12, stroke=0, fill=1)
        c.drawImage(ImageReader(images.get(v, None, L["back_art"].w, "RGB", dpi_cap)), x, y, w, h)
    for t in L["thumbs"]:
        v = snapshot["versions"][t["version_id"]]
        x, y, w, h = R(t["rect"])
        c.setFillColor(white)
        c.setStrokeColor(tc)
        c.setLineWidth(1.5)
        c.rect(x, y, w, h, stroke=1, fill=1)
        im = images.get(v, None, t["rect"].w, "RGB", 300)
        aspect = im.height / im.width
        iw = min(w - 8, (h - 8) / aspect)
        c.drawImage(ImageReader(im), x + (w - iw) / 2, y + (h - iw * aspect) / 2, iw, iw * aspect)
    # barcode reservation: plain white box where Amazon places the barcode (no outline, no text)
    x, y, w, h = R(L["barcode"])
    c.setFillColor(white)
    c.rect(x, y, w, h, stroke=0, fill=1)
    if L["spine_text"]:
        st = L["spine_text"]
        sx, sy, sw, sh = R(st["rect"])
        c.saveState()
        c.translate(sx + sw / 2, sy + sh / 2)
        c.rotate(-90)  # top-to-bottom spine text
        c.setFillColor(tc)
        c.setFont(FONT_BOLD, st["size_pt"])
        c.drawCentredString(0, -st["size_pt"] * 0.35, st["text"])
        c.restoreState()
    c.showPage()
    c.save()
    return cover_layout_json(snapshot)


def render_cover_png(snapshot: dict, read_bytes, dpi: int = 40) -> bytes:
    buf = io.BytesIO()
    render_cover(snapshot, read_bytes, buf, dpi_cap=120)
    return rasterize_pdf_page(buf.getvalue(), 0, dpi)


# --- contact sheet ----------------------------------------------------------------------------

def render_contact_sheet(snapshot: dict, interior_pdf: Path, cover_pdf: Path | None, out_path: Path, status_line: str,
                         progress=None, cancelled=None):
    import pypdfium2 as pdfium
    register_fonts()
    c = Canvas(str(out_path), pageCompression=1, invariant=1, initialFontName=FONT_REGULAR)
    PW, PH = 11 * 72, 8.5 * 72  # landscape letter
    c.setTitle("Proof preview – not an upload file")
    title = snapshot["spec"]["title"]
    if cover_pdf:
        c.setPageSize((PW, PH))
        doc = pdfium.PdfDocument(str(cover_pdf))
        im = doc[0].render(scale=60 / 72).to_pil()
        doc.close()
        c.setFont(FONT_BOLD, 14)
        c.drawString(36, PH - 40, f"PROOF PREVIEW – {title} – full cover (not an upload file)")
        c.setFont(FONT_REGULAR, 9)
        c.drawString(36, PH - 56, status_line)
        aw, ah = PW - 72, PH - 110
        s = min(aw / im.width, ah / im.height)
        c.drawImage(ImageReader(im), 36, 40, im.width * s, im.height * s)
        c.showPage()
    doc = pdfium.PdfDocument(str(interior_pdf))
    n = len(doc)
    cols, rows = 6, 3
    per = cols * rows
    asm = snapshot["assembly"]["pages"]
    for start in range(0, n, per):
        if cancelled and cancelled():
            doc.close()
            raise Cancelled()
        c.setPageSize((PW, PH))
        c.setFont(FONT_BOLD, 12)
        c.drawString(36, PH - 32, f"PROOF PREVIEW – {title} – interior pages {start + 1}–{min(n, start + per)} of {n}")
        c.setFont(FONT_REGULAR, 8)
        c.drawString(36, PH - 46, status_line)
        cw, chh = (PW - 72) / cols, (PH - 80) / rows
        for k in range(start, min(n, start + per)):
            i = k - start
            col, row = i % cols, i // cols
            im = doc[k].render(scale=24 / 72).to_pil()
            bw, bh = cw - 14, chh - 22
            s = min(bw / im.width, bh / im.height)
            x = 36 + col * cw + (cw - im.width * s) / 2
            y = PH - 60 - (row + 1) * chh + 16
            c.drawImage(ImageReader(im), x, y, im.width * s, im.height * s)
            c.setStrokeColorRGB(0.6, 0.6, 0.6)
            c.setLineWidth(0.5)
            c.rect(x, y, im.width * s, im.height * s)
            kind = asm[k]["kind"] if k < len(asm) else "?"
            label = f"p.{k + 1} {'(blank back)' if asm[k].get('blank_reason') == 'back' else 'story text' if kind == 'story' else kind}"
            c.setFillColorRGB(0, 0, 0)
            c.drawCentredString(36 + col * cw + cw / 2, y - 10, label)
        c.showPage()
        if progress:
            progress(min(1.0, (start + per) / n), "Contact sheet")
    doc.close()
    c.save()
