"""Honest pricing calculator using Decimal arithmetic and a dated, editable marketplace profile."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

CENT = Decimal("0.01")


def D(x) -> Decimal:
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Not a number: {x!r}")


def money(x: Decimal) -> str:
    return str(x.quantize(CENT, rounding=ROUND_HALF_UP))


def printing_cost(profile: dict, page_count: int, large_trim: bool, ink: str = "black") -> Decimal:
    cat = "large" if large_trim else "regular"
    for b in profile["printing_cost_bands"]:
        if b["ink"] == ink and b["trim_category"] == cat and b["min_pages"] <= page_count <= b["max_pages"]:
            return D(b["fixed"]) + D(b["per_page"]) * page_count
    raise ValueError(f"No printing-cost band for {page_count} pages ({cat} trim, {ink} ink) in profile {profile['id']}")


def royalty_rate(profile: dict, list_price: Decimal) -> Decimal:
    for t in profile["royalty_tiers"]:
        lo = D(t["min_price"]) if "min_price" in t else None
        hi = D(t["max_price"]) if "max_price" in t else None
        if (lo is None or list_price >= lo) and (hi is None or list_price <= hi):
            return D(t["rate"])
    raise ValueError("Price is outside the royalty tiers in this profile")


def calculate(profile: dict, page_count: int, large_trim: bool, list_price, scenario: dict | None = None) -> dict:
    price = D(list_price)
    if price <= 0:
        raise ValueError("List price must be positive")
    pc = printing_cost(profile, page_count, large_trim)
    rate = royalty_rate(profile, price)
    royalty = rate * price - pc
    min_price_50 = None
    out = {
        "profile_id": profile["id"], "marketplace": profile["marketplace"], "currency": profile["currency"],
        "checked_on": profile["checked_on"], "sources": profile["sources"],
        "note": profile.get("effective_note"),
        "formula": "Estimated royalty = royalty rate × tax-exclusive list price − printing cost",
        "list_price": money(price), "page_count": page_count, "trim_category": "large" if large_trim else "regular",
        "printing_cost": money(pc), "royalty_rate": str(rate),
        "royalty_per_copy_exact": str(royalty), "royalty_per_copy": money(royalty),
        "royalty_negative": royalty < 0,
        "expanded_distribution": profile.get("expanded_distribution", {"enabled": False}),
    }
    if royalty < 0:
        out["warning"] = "At this price the printing cost exceeds your royalty share; KDP will not accept it."
    if scenario:
        q = int(scenario.get("copies", 0))
        if q < 0:
            raise ValueError("copies must be ≥ 0")
        ads = D(scenario.get("ad_cost_per_sale", 0)) * q
        fixed = sum((D(scenario.get(k, 0)) for k in ("artwork_costs", "proof_costs", "other_costs")), Decimal(0))
        revenue = price * q
        roy_total = royalty * q
        profit = roy_total - ads - fixed
        out["scenario"] = {
            "copies": q,
            "customer_sales_revenue": money(revenue),
            "royalties": money(roy_total),
            "advertising": money(ads),
            "fixed_costs": money(fixed),
            "estimated_profit": money(profit),
            "break_even_copies": (int((fixed / (royalty - D(scenario.get("ad_cost_per_sale", 0)))).to_integral_value(rounding="ROUND_CEILING"))
                                  if royalty - D(scenario.get("ad_cost_per_sale", 0)) > 0 else None),
            "disclaimer": "A scenario based on the numbers you entered — not a sales prediction.",
        }
    return out
