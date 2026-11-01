"""Image validation, non-destructive edit operations and quality heuristics (Pillow + NumPy/SciPy)."""
from __future__ import annotations

import io
import re
import warnings
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from scipy import ndimage


class UploadRejected(ValueError):
    pass


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"


def safe_display_name(name: str) -> str:
    base = re.split(r"[\\/]", name or "")[-1]
    base = re.sub(r"[^A-Za-z0-9._ -]+", "_", base).strip(" .")
    return (base or "upload")[:120]


@dataclass
class ValidatedImage:
    mime: str
    ext: str
    width: int
    height: int
    dpi: tuple[float, float] | None
    has_alpha: bool


def validate_image_bytes(data: bytes, *, max_bytes: int, max_pixels: int, max_side: int) -> ValidatedImage:
    if not data:
        raise UploadRejected("The file is empty.")
    if len(data) > max_bytes:
        raise UploadRejected(f"File is larger than the {max_bytes // (1024 * 1024)} MB limit.")
    # Identify the format by its magic bytes FIRST. PNG/JPEG files may legitimately contain XML text in
    # metadata (XMP, C2PA content credentials), so only non-PNG/JPEG data is ever treated as SVG.
    if data.startswith(PNG_MAGIC):
        mime, ext, fmt = "image/png", "png", "PNG"
    elif data.startswith(JPEG_MAGIC):
        mime, ext, fmt = "image/jpeg", "jpg", "JPEG"
    else:
        head = data[:1024].lstrip().lower()
        if head.startswith(b"<?xml") or head.startswith(b"<svg") or b"<svg" in head:
            raise UploadRejected("SVG is not supported in this version: SVG files can contain scripts and external "
                                 "references, and no sanitizing renderer is bundled. Export your drawing as PNG at 300 DPI.")
        raise UploadRejected("Only PNG and JPEG files are supported (file content did not match either format).")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        old = Image.MAX_IMAGE_PIXELS
        Image.MAX_IMAGE_PIXELS = max_pixels
        try:
            with Image.open(io.BytesIO(data)) as im:
                if im.format != fmt:
                    raise UploadRejected("File extension/content mismatch.")
                w, h = im.size
                if w * h > max_pixels or max(w, h) > max_side:
                    raise UploadRejected(f"Image is {w}×{h} px, larger than the {max_side}px / {max_pixels:,} pixel safety limit.")
                if min(w, h) < 16:
                    raise UploadRejected("Image is too small to be artwork.")
                im.verify()
            with Image.open(io.BytesIO(data)) as im:
                im.load()  # full decode catches truncated/damaged files
                dpi = im.info.get("dpi")
                has_alpha = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
        except (Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise UploadRejected("Image dimensions exceed the decompression-bomb safety limit.")
        except UploadRejected:
            raise
        except Exception as e:  # noqa: BLE001
            raise UploadRejected(f"The image could not be decoded ({type(e).__name__}). It may be damaged.")
        finally:
            Image.MAX_IMAGE_PIXELS = old
    d = (float(dpi[0]), float(dpi[1])) if dpi else None
    return ValidatedImage(mime, ext, w, h, d, has_alpha)


def open_flat(data: bytes, background=(255, 255, 255)) -> Image.Image:
    """Decode and composite transparency over the intended (white paper) background."""
    im = Image.open(io.BytesIO(data))
    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, background + (255,))
        bg.alpha_composite(im)
        return bg.convert("RGB")
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    return im


def to_png_bytes(im: Image.Image, dpi: float | None = None) -> bytes:
    buf = io.BytesIO()
    kw = {"optimize": True}
    if dpi:
        kw["dpi"] = (dpi, dpi)
    im.save(buf, "PNG", **kw)
    return buf.getvalue()


# --- edit operations (each produces a NEW immutable version) --------------------------------

def apply_operation(src: Image.Image, op: dict) -> Image.Image:
    t = op.get("type")
    if t == "adjust":
        im = src.convert("L") if op.get("grayscale", True) else src.convert("RGB")
        b = float(op.get("brightness", 1.0))
        c = float(op.get("contrast", 1.0))
        if not (0.2 <= b <= 3 and 0.2 <= c <= 4):
            raise ValueError("brightness/contrast out of range")
        im = ImageEnhance.Brightness(im).enhance(b)
        return ImageEnhance.Contrast(im).enhance(c)
    if t == "threshold":
        level = int(op.get("level", 160))
        if not 1 <= level <= 254:
            raise ValueError("threshold out of range")
        g = np.asarray(src.convert("L"))
        return Image.fromarray(np.where(g < level, 0, 255).astype(np.uint8), "L")
    if t == "cleanup":
        # Remove isolated dark specks smaller than `min_area` px and lightly smooth edges.
        min_area = int(op.get("min_area", 40))
        g = np.asarray(src.convert("L"))
        dark = g < 128
        lab, n = ndimage.label(dark)
        if n:
            sizes = ndimage.sum(dark, lab, index=np.arange(1, n + 1))
            small = np.isin(lab, np.nonzero(sizes < min_area)[0] + 1)
            g = np.where(small, 255, g).astype(np.uint8)
        im = Image.fromarray(g, "L")
        if op.get("smooth", True):
            im = im.filter(ImageFilter.MedianFilter(3))
        return im
    if t == "erase":
        im = src.convert("L") if src.mode == "L" else src.convert("RGB")
        W, H = im.size
        fill = 255 if im.mode == "L" else (255, 255, 255)
        from PIL import ImageDraw
        dr = ImageDraw.Draw(im)
        for s in op.get("shapes", []):
            if s.get("shape", "rect") == "rect":
                x, y, w, h = (float(s[k]) for k in ("x", "y", "w", "h"))
                dr.rectangle([x * W, y * H, (x + w) * W, (y + h) * H], fill=fill)
            elif s["shape"] == "circle":
                cx, cy, r = float(s["cx"]) * W, float(s["cy"]) * H, float(s["r"]) * W
                dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)
        return im
    if t == "upscale":
        f = float(op.get("factor", 2))
        if not 1 < f <= 4:
            raise ValueError("upscale factor must be in (1, 4]")
        return src.resize((round(src.width * f), round(src.height * f)), Image.LANCZOS)
    if t == "print_ready":
        return print_ready(src, margin_frac=float(op.get("margin_frac", 0.03)), fine=bool(op.get("fine", False)))
    if t == "colorize":
        return colorize_line_art(src, seed=int(op.get("seed", 7)))
    raise ValueError(f"Unknown operation '{t}'")


def otsu_level(g: np.ndarray) -> int:
    hist = np.bincount(g.ravel(), minlength=256).astype(np.float64)
    total = hist.sum()
    sum_all = np.dot(np.arange(256), hist)
    w_b = sum_b = 0.0
    best, level = -1.0, 128
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b, m_f = sum_b / w_b, (sum_all - sum_b) / w_f
        between = w_b * w_f * (m_b - m_f) ** 2
        if between > best:
            best, level = between, t
    return level


def print_ready(src: Image.Image, margin_frac: float = 0.03, fine: bool = False) -> Image.Image:
    """Make generated line art print-ready for a black-ink interior:
    pure black/white (Otsu threshold, clamped), remove isolated specks, close pin-hole gaps that would
    create un-colorable dots, and crop surrounding empty space (keeping a small margin)."""
    g = np.asarray(src.convert("L"))
    level = int(min(200, max(110, otsu_level(g))))
    dark = g < level
    n = dark.size
    lab, cnt = ndimage.label(dark)
    if cnt:
        sizes = ndimage.sum(dark, lab, index=np.arange(1, cnt + 1))
        # fine mode keeps stippling: only single stray pixels are removed
        specks = np.nonzero(sizes < (2 if fine else max(12, n * 0.000004)))[0] + 1
        dark[np.isin(lab, specks)] = False
    white = ~dark
    wl, wc = ndimage.label(white) if not fine else (None, 0)
    if wc:
        wsizes = ndimage.sum(white, wl, index=np.arange(1, wc + 1))
        holes = np.nonzero(wsizes < max(6, n * 0.0000015))[0] + 1
        dark[np.isin(wl, holes)] = True
    ys, xs = np.nonzero(dark)
    out = np.where(dark, 0, 255).astype(np.uint8)
    if len(xs):
        H, W = out.shape
        pad = int(max(H, W) * margin_frac)
        x0, x1 = max(0, xs.min() - pad), min(W, xs.max() + 1 + pad)
        y0, y1 = max(0, ys.min() - pad), min(H, ys.max() + 1 + pad)
        if (x1 - x0) * (y1 - y0) > 0.2 * H * W:  # never crop to a sliver
            out = out[y0:y1, x0:x1]
    return Image.fromarray(out, "L")


PALETTE = [(255, 205, 86), (120, 200, 240), (255, 150, 140), (150, 220, 140), (200, 170, 240),
           (255, 180, 90), (130, 220, 210), (250, 140, 190), (190, 230, 120), (240, 220, 140)]


def colorize_line_art(src: Image.Image, seed: int = 7) -> Image.Image:
    """Make a colored *cover* version of line art by filling enclosed white regions.
    Line pixels stay black. This is a simple fill, not a painting."""
    g = np.asarray(src.convert("L"))
    white = g >= 200
    lab, n = ndimage.label(white)
    out = np.stack([g, g, g], axis=-1).astype(np.uint8)
    if n == 0:
        return Image.fromarray(out, "RGB")
    sizes = ndimage.sum(white, lab, index=np.arange(1, n + 1))
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    rng = np.random.default_rng(seed)
    colors = np.zeros((n + 1, 3), dtype=np.uint8)
    min_area = g.size * 0.0004
    for i in range(1, n + 1):
        if i in border:
            colors[i] = (232, 246, 255)
        elif sizes[i - 1] >= min_area:
            colors[i] = PALETTE[int(rng.integers(0, len(PALETTE)))]
        else:
            colors[i] = (255, 255, 255)
    fill = colors[lab]
    mask = white[..., None]
    out = np.where(mask, fill, out)
    return Image.fromarray(out.astype(np.uint8), "RGB")


# --- analysis / heuristics ------------------------------------------------------------------

def dhash(im: Image.Image, size: int = 16) -> int:
    g = im.convert("L").resize((size + 1, size), Image.LANCZOS)
    a = np.asarray(g, dtype=np.int16)
    bits = (a[:, 1:] > a[:, :-1]).flatten()
    v = 0
    for b in bits:
        v = (v << 1) | int(b)
    return v


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def analyze(im: Image.Image) -> dict:
    """Heuristic measurements used by preflight. These are NOT quality certifications."""
    rgb = im.convert("RGB")
    small = rgb.copy()
    small.thumbnail((900, 900))
    arr = np.asarray(small).astype(np.int16)
    g = np.asarray(small.convert("L"))
    sat = arr.max(axis=2) - arr.min(axis=2)
    color_fraction = float((sat > 40).mean())
    dark = g < 100
    black_coverage = float(dark.mean())
    mid = (g >= 60) & (g <= 200)
    # discount antialiasing: mid-gray pixels touching dark lines are edges, not fills
    near_line = ndimage.binary_dilation(dark, iterations=2)
    gray_fill_fraction = float((mid & ~near_line).mean())
    # enclosed coloring regions
    white = g >= 200
    lab, n = ndimage.label(white)
    tiny = 0
    regions = 0
    specks = 0
    if n:
        sizes = ndimage.sum(white, lab, index=np.arange(1, n + 1))
        px_per_sq_in_est = (small.width / 7.5) ** 2  # assumes ~7.5in placed width; heuristic
        tiny = int(((sizes > 3) & (sizes < 0.02 * px_per_sq_in_est)).sum())
        regions = int((sizes >= 0.02 * px_per_sq_in_est).sum())
    dlab, dn = ndimage.label(dark)
    if dn:
        dsizes = ndimage.sum(dark, dlab, index=np.arange(1, dn + 1))
        specks = int((dsizes <= 4).sum())
    return {
        "color_fraction": round(color_fraction, 4),
        "black_coverage": round(black_coverage, 4),
        "gray_fill_fraction": round(gray_fill_fraction, 4),
        "tiny_regions": tiny,
        "colorable_regions": regions,
        "isolated_specks": specks,
        "dhash": f"{dhash(rgb):064x}",
    }
