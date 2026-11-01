"""Print geometry: profiles, interior page boxes, safe areas, element placement and cover wrap.

All physical values are inches (canonical). Element coordinates are inches relative to the
TRIM box's top-left corner with y pointing down. Conversion to PDF points (72/in, y up)
happens only in `to_pdf_rect`.

This single module is used by the browser preview API, the PDF renderer and preflight, so the
preview and the export cannot drift apart.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from functools import lru_cache

from .config import PROFILE_DIR
from .units import dround, in_to_pt


class UnsupportedConfiguration(ValueError):
    pass


@lru_cache(maxsize=1)
def print_profiles() -> dict:
    return json.loads((PROFILE_DIR / "print_profiles.json").read_text())


@dataclass(frozen=True)
class PrintConfig:
    trim_key: str
    paper_key: str
    interior_bleed: bool
    trim_w: float
    trim_h: float
    spine_per_page: float
    large_trim: bool
    safe_margin: float

    def as_dict(self) -> dict:
        return asdict(self)


def resolve_config(spec: dict) -> PrintConfig:
    prof = print_profiles()
    trim_key = spec.get("trim", "8.5x11")
    paper_key = spec.get("paper", "bw_white")
    trim = prof["trims"].get(trim_key)
    if not trim or not trim.get("validated"):
        raise UnsupportedConfiguration(f"Trim size '{trim_key}' is not a validated preset in this app.")
    if paper_key not in trim["papers"]:
        raise UnsupportedConfiguration(f"Paper/ink '{paper_key}' is not validated for trim {trim_key}.")
    if spec.get("binding", "paperback") != "paperback":
        raise UnsupportedConfiguration("Only paperback binding is supported in this version.")
    paper = prof["papers"][paper_key]
    return PrintConfig(
        trim_key=trim_key,
        paper_key=paper_key,
        interior_bleed=bool(spec.get("interior_bleed", False)),
        trim_w=float(trim["width_in"]),
        trim_h=float(trim["height_in"]),
        spine_per_page=float(paper["spine_in_per_page"]),
        large_trim=bool(trim["large_trim"]),
        safe_margin=float(spec.get("safe_margin_in", prof["default_safe_margin_in"])),
    )


def min_gutter(page_count: int) -> float:
    for band in print_profiles()["gutter_bands"]:
        if band["min_pages"] <= page_count <= band["max_pages"]:
            return float(band["inside_in"])
    raise UnsupportedConfiguration(f"Page count {page_count} is outside the supported 24–828 range.")


def min_outside(bleed: bool) -> float:
    m = print_profiles()["outside_margin_min_in"]
    return float(m["bleed" if bleed else "no_bleed"])


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def x2(self) -> float:
        return self.x + self.w

    @property
    def y2(self) -> float:
        return self.y + self.h

    def contains(self, other: "Rect", tol: float = 1e-6) -> bool:
        return (other.x >= self.x - tol and other.y >= self.y - tol and
                other.x2 <= self.x2 + tol and other.y2 <= self.y2 + tol)

    def intersects(self, other: "Rect") -> bool:
        return not (other.x >= self.x2 or other.x2 <= self.x or other.y >= self.y2 or other.y2 <= self.y)

    def d(self) -> dict:
        return {"x": dround(self.x), "y": dround(self.y), "w": dround(self.w), "h": dround(self.h)}


@dataclass(frozen=True)
class PageGeometry:
    page_number: int
    side: str                 # "recto" (odd, right-hand) or "verso" (even, left-hand)
    media_w: float
    media_h: float
    trim_origin_x: float      # trim box offset inside media box, from left
    trim_origin_y: float      # from top
    trim: Rect                # in trim coordinates (always 0,0,w,h)
    safe: Rect                # in trim coordinates
    inside_margin: float
    outside_margin: float
    inside_edge: str          # "left" or "right"

    def d(self) -> dict:
        return {
            "page_number": self.page_number, "side": self.side,
            "media_w": dround(self.media_w), "media_h": dround(self.media_h),
            "media_w_pt": dround(in_to_pt(self.media_w), 3), "media_h_pt": dround(in_to_pt(self.media_h), 3),
            "trim_origin_x": self.trim_origin_x, "trim_origin_y": self.trim_origin_y,
            "trim": self.trim.d(), "safe": self.safe.d(),
            "inside_margin": self.inside_margin, "outside_margin": self.outside_margin,
            "inside_edge": self.inside_edge,
        }


def page_geometry(cfg: PrintConfig, page_number: int, page_count: int) -> PageGeometry:
    prof = print_profiles()
    recto = page_number % 2 == 1
    if cfg.interior_bleed:
        b = prof["interior_bleed"]
        media_w = cfg.trim_w + b["add_width_in"]
        media_h = cfg.trim_h + b["add_height_in"]
        # Bleed goes on the OUTSIDE edge: right edge for recto pages, left edge for verso pages.
        trim_x = 0.0 if recto else float(b["add_width_in"])
        trim_y = float(b["add_height_in"]) / 2
    else:
        media_w, media_h, trim_x, trim_y = cfg.trim_w, cfg.trim_h, 0.0, 0.0
    inside = max(cfg.safe_margin, min_gutter(page_count))
    outside = max(cfg.safe_margin, min_outside(cfg.interior_bleed))
    inside_edge = "left" if recto else "right"
    left = inside if recto else outside
    right = outside if recto else inside
    safe = Rect(left, outside, cfg.trim_w - left - right, cfg.trim_h - 2 * outside)
    return PageGeometry(page_number, "recto" if recto else "verso", dround(media_w), dround(media_h),
                        trim_x, trim_y, Rect(0, 0, cfg.trim_w, cfg.trim_h), safe, inside, outside, inside_edge)


def to_pdf_rect(geo: PageGeometry, r: Rect) -> tuple[float, float, float, float]:
    """Trim-relative inch rect (y down) -> PDF points (x, y_bottom, w, h)."""
    x = in_to_pt(geo.trim_origin_x + r.x)
    y = in_to_pt(geo.media_h - geo.trim_origin_y - r.y - r.h)
    return x, y, in_to_pt(r.w), in_to_pt(r.h)


# --- element placement ---------------------------------------------------------------------

def crop_px(width_px: int, height_px: int, crop: dict | None) -> tuple[int, int, int, int]:
    """Return (left, top, right, bottom) pixel box for a fractional crop."""
    c = crop or {}
    l, t = float(c.get("l", 0)), float(c.get("t", 0))
    r, b = float(c.get("r", 0)), float(c.get("b", 0))
    if min(l, t, r, b) < 0 or l + r >= 0.98 or t + b >= 0.98:
        raise ValueError("Invalid crop")
    return (int(round(width_px * l)), int(round(height_px * t)),
            int(round(width_px * (1 - r))), int(round(height_px * (1 - b))))


def image_rect(el: dict, width_px: int, height_px: int) -> Rect:
    """Placed rectangle (pre-rotation) for an image element. Height is ALWAYS derived from the
    cropped aspect ratio, so artwork can never be stretched."""
    x0, y0, x1, y1 = crop_px(width_px, height_px, el.get("crop"))
    cw, ch = x1 - x0, y1 - y0
    w = float(el["w"])
    return Rect(float(el["x"]), float(el["y"]), w, w * ch / cw)


def element_rect(el: dict, version: dict | None) -> Rect:
    if el["kind"] == "image":
        if version is None:
            raise ValueError("image element without version")
        return image_rect(el, version["width_px"], version["height_px"])
    return Rect(float(el["x"]), float(el["y"]), float(el["w"]), float(el["h"]))


def rotated_bounds(r: Rect, rotation_deg: float) -> Rect:
    if not rotation_deg:
        return r
    a = math.radians(rotation_deg)
    c, s = abs(math.cos(a)), abs(math.sin(a))
    bw, bh = r.w * c + r.h * s, r.w * s + r.h * c
    cx, cy = r.x + r.w / 2, r.y + r.h / 2
    return Rect(cx - bw / 2, cy - bh / 2, bw, bh)


def effective_dpi_for(el: dict, version: dict) -> float:
    x0, y0, x1, y1 = crop_px(version["width_px"], version["height_px"], el.get("crop"))
    r = image_rect(el, version["width_px"], version["height_px"])
    return min((x1 - x0) / r.w, (y1 - y0) / r.h)


def fit_element(el: dict, version: dict, target: Rect) -> dict:
    """Fit (contain) an image element into target, preserving aspect & rotation, centered."""
    r = image_rect(el, version["width_px"], version["height_px"])
    a = math.radians(float(el.get("rotation", 0) or 0))
    c, s = abs(math.cos(a)), abs(math.sin(a))
    aspect = r.h / r.w
    # bounding box for width w: W = w*(c + aspect*s), H = w*(s + aspect*c)
    w = min(target.w / (c + aspect * s), target.h / (s + aspect * c))
    h = w * aspect
    out = dict(el)
    out["w"] = dround(w)
    out["x"] = dround(target.x + (target.w - w) / 2)
    out["y"] = dround(target.y + (target.h - h) / 2)
    return out


# --- cover --------------------------------------------------------------------------------

def cover_geometry(cfg: PrintConfig, page_count: int, spine_text_pt: float | None = None) -> dict:
    cv = print_profiles()["cover"]
    bleed = float(cv["bleed_in"])
    spine = page_count * cfg.spine_per_page
    full_w = 2 * cfg.trim_w + spine + 2 * bleed
    full_h = cfg.trim_h + 2 * bleed
    safe_m = float(cv["safe_margin_from_trim_in"])
    back = Rect(bleed, bleed, cfg.trim_w, cfg.trim_h)
    spine_r = Rect(bleed + cfg.trim_w, bleed, spine, cfg.trim_h)
    front = Rect(bleed + cfg.trim_w + spine, bleed, cfg.trim_w, cfg.trim_h)
    bc = cv["barcode"]
    off = float(bc["min_offset_from_trim_and_spine_in"])
    barcode = Rect(back.x2 - off - bc["width_in"], back.y2 - off - bc["height_in"], bc["width_in"], bc["height_in"])
    clear = float(cv["spine_fold_clearance_in"])
    spine_avail = max(0.0, spine - 2 * clear)
    page_ok = page_count > int(cv["spine_text_min_pages_exclusive"])
    pt = spine_text_pt or float(cv["spine_text_min_font_pt"])
    needed = max(pt, float(cv["spine_text_min_font_pt"])) / 72.0
    fits = spine_avail >= needed
    reasons = []
    if not page_ok:
        reasons.append(f"KDP prints spine text only on books with more than {cv['spine_text_min_pages_exclusive']} pages.")
    if not fits:
        reasons.append(f"Usable spine width is {spine_avail:.3f} in after {clear} in fold clearances; "
                       f"{max(pt, cv['spine_text_min_font_pt']):.1f} pt text needs {needed:.3f} in.")
    return {
        "page_count": page_count,
        "spine_coefficient_in": cfg.spine_per_page,
        "paper": cfg.paper_key,
        "bleed_in": bleed,
        "spine_width_in": dround(spine),
        "full_width_in": dround(full_w),
        "full_height_in": dround(full_h),
        "full_width_pt": dround(in_to_pt(full_w), 3),
        "full_height_pt": dround(in_to_pt(full_h), 3),
        "back": back.d(), "spine": spine_r.d(), "front": front.d(),
        "back_safe": Rect(back.x + safe_m, back.y + safe_m, back.w - 2 * safe_m, back.h - 2 * safe_m).d(),
        "front_safe": Rect(front.x + safe_m, front.y + safe_m, front.w - 2 * safe_m, front.h - 2 * safe_m).d(),
        "spine_safe": Rect(spine_r.x + clear, spine_r.y + safe_m, spine_avail, spine_r.h - 2 * safe_m).d(),
        "barcode": barcode.d(),
        "spine_text": {"eligible": page_ok and fits, "page_rule_ok": page_ok, "fits": fits,
                       "available_in": dround(spine_avail), "reasons": reasons},
        "profile_version": print_profiles()["profile_set_version"],
        "conflicts": cv["conflicts"],
    }
