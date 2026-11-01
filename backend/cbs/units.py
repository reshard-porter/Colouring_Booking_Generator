"""Physical units. Canonical unit for stored dimensions is the INCH (as Decimal-safe floats
rounded to 1e-6). PDF uses 72 points per inch. Pixels only make sense together with a
physical placed size (effective DPI) – never from file metadata alone."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

POINTS_PER_INCH = 72.0
MM_PER_INCH = 25.4


def in_to_pt(inches: float) -> float:
    return float(inches) * POINTS_PER_INCH


def pt_to_in(points: float) -> float:
    return float(points) / POINTS_PER_INCH


def mm_to_in(mm: float) -> float:
    return float(mm) / MM_PER_INCH


def in_to_mm(inches: float) -> float:
    return float(inches) * MM_PER_INCH


def px_to_in(px: float, dpi: float) -> float:
    if dpi <= 0:
        raise ValueError("dpi must be positive")
    return float(px) / float(dpi)


def in_to_px(inches: float, dpi: float) -> int:
    return int(round(float(inches) * float(dpi)))


def effective_dpi(pixels: float, placed_inches: float) -> float:
    """Pixels actually available per inch of printed size. Metadata DPI is irrelevant."""
    if placed_inches <= 0:
        return 0.0
    return float(pixels) / float(placed_inches)


def dround(value: float | Decimal, places: int = 6) -> float:
    q = Decimal(1).scaleb(-places)
    return float(Decimal(str(value)).quantize(q, rounding=ROUND_HALF_UP))
