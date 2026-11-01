"""Preflight: deterministic technical errors/warnings, labelled artwork heuristics, and
human publishing-review items. Heuristics cannot certify artistic quality or legal ownership."""
from __future__ import annotations

from .db import jdump, new_id, now_iso
from .geometry import (PrintConfig, Rect, cover_geometry, effective_dpi_for, element_rect, page_geometry,
                       rotated_bounds)
from .imaging import hamming
from .render import text_fits, cover_layout

SEVERITY_ORDER = {"error": 0, "warning": 1, "heuristic": 2, "review": 3}
CATEGORY = {"error": "technical_error", "warning": "technical_warning", "heuristic": "artwork_heuristic",
            "review": "human_review"}


class Findings:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, severity, code, message, page_id=None, page_number=None, **detail):
        self.items.append({"severity": severity, "category": CATEGORY[severity], "code": code, "message": message,
                           "page_id": page_id, "page_number": page_number, "detail": detail})


def run(studio, snap: dict) -> dict:
    F = Findings()
    cfg = PrintConfig(**snap["config"])
    asm = snap["assembly"]
    n = asm["page_count"]
    spec = snap["spec"]

    # --- configuration & page count ---
    if n < 24:
        F.add("error", "page_count_low", f"Interior has {n} pages; KDP paperbacks need at least 24.")
    if n > 828:
        F.add("error", "page_count_high", f"Interior has {n} pages; above the 828-page maximum in this profile.")
    if n > 150:
        F.add("warning", "page_count_verify", "Above 150 pages: confirm the maximum page count for this trim/paper in KDP's trim-size table.")
    if n % 2:
        F.add("error", "odd_page_count", "Interior page count is odd.")
    for note in asm.get("parity_notes", []):
        F.add("warning", "parity_correction", note)
    if spec.get("blank_backs", True):
        for p in asm["pages"]:
            if p["kind"] == "illustration":
                nxt = asm["pages"][p["number"]] if p["number"] < n else None
                if p["number"] % 2 == 0 or not nxt or nxt["kind"] != "blank":
                    F.add("error", "blank_back_rule", "Illustration is not on a right-hand page followed by a blank back.",
                          p["page_id"], p["number"])
    if asm["illustration_count"] != int(spec.get("illustration_count", asm["illustration_count"])):
        F.add("warning", "illustration_count_mismatch",
              f"Book plan targets {spec['illustration_count']} illustrations; the layout has {asm['illustration_count']}.")
    if asm["intro_count"] != int(spec.get("intro_pages", asm["intro_count"])):
        F.add("warning", "intro_count_mismatch", f"Plan says {spec['intro_pages']} introductory pages; layout has {asm['intro_count']}.")

    fine_mode = (snap.get("style_guide") or {}).get("cleanup_mode") == "fine"
    # --- per-page checks ---
    hashes: dict[str, list] = {}
    dhashes: list[tuple[int, str, int, str]] = []
    unapproved = 0
    for p in asm["pages"]:
        if p["kind"] == "blank":
            continue
        geo = page_geometry(cfg, p["number"], max(n, 24))
        els = p.get("elements", [])
        pid_, num = p["page_id"], p["number"]
        if p["kind"] == "illustration":
            if not any(e["kind"] == "image" for e in els):
                F.add("error", "empty_illustration", "Illustration page has no artwork.", pid_, num)
            if not p.get("approved"):
                unapproved += 1
        for el in els:
            v = snap["versions"].get(el.get("asset_version_id")) if el["kind"] == "image" else None
            if el["kind"] == "image":
                if v is None:
                    F.add("error", "missing_asset", "Placed artwork is missing from the project.", pid_, num)
                    continue
                if not studio.storage.exists(v["storage_key"]):
                    F.add("error", "missing_file", "Artwork file is missing from storage.", pid_, num, version=el["asset_version_id"])
                    continue
                from .storage import sha256_bytes
                if sha256_bytes(studio.storage.read(v["storage_key"])) != v["sha256"]:
                    F.add("error", "damaged_file", "Artwork file does not match its recorded hash (damaged).", pid_, num)
                    continue
            r = rotated_bounds(element_rect(el, v), float(el.get("rotation", 0) or 0))
            if not geo.trim.contains(r):
                F.add("error", "outside_trim", f"{el['kind'].title()} extends beyond the trim edge and would be cut off.", pid_, num, element_id=el.get("id"))
            elif not geo.safe.contains(r):
                F.add("error", "outside_safe_area",
                      f"{el['kind'].title()} extends into the margin (safe area is {geo.inside_margin} in inside / {geo.outside_margin} in outside).",
                      pid_, num, element_id=el.get("id"))
            if el["kind"] == "text" and not text_fits(el):
                F.add("warning", "text_overflow", "Text does not fit inside its text box.", pid_, num, element_id=el.get("id"))
            if el["kind"] == "image":
                dpi = effective_dpi_for(el, v)
                detail_dpi = dpi * v["original_width_px"] / v["width_px"] if v.get("upscaled") else dpi
                note = (f" (enlarged version; original detail is {detail_dpi:.0f} DPI — enlarging does not add detail)"
                        if v.get("upscaled") else "")
                if detail_dpi < 150:
                    F.add("error", "low_resolution", f"Effective resolution is {detail_dpi:.0f} DPI at this size{note}; target is 300 DPI.",
                          pid_, num, effective_dpi=round(detail_dpi, 1))
                elif detail_dpi < 300:
                    F.add("warning", "below_300dpi", f"Effective resolution is {detail_dpi:.0f} DPI at this size{note}; target is 300 DPI.",
                          pid_, num, effective_dpi=round(detail_dpi, 1))
                hashes.setdefault(v["sha256"], []).append((pid_, num))
                a = studio.asset_analysis(el["asset_version_id"])
                dhashes.append((int(a["dhash"], 16), pid_, num, v["sha256"]))
                if a["color_fraction"] > 0.01:
                    F.add("warning", "color_in_black_ink", f"{a['color_fraction']:.1%} of the artwork is colored; a black-ink interior prints it as gray.", pid_, num)
                if a["gray_fill_fraction"] > 0.03:
                    F.add("heuristic", "gray_fill", f"About {a['gray_fill_fraction']:.1%} of the image is gray fill rather than line; coloring pages usually avoid shading.", pid_, num)
                if a["black_coverage"] > (0.5 if fine_mode else 0.35):
                    F.add("heuristic", "heavy_black", f"Black covers about {a['black_coverage']:.0%} of the image; heavy black areas leave little to color.", pid_, num)
                if a["tiny_regions"] > 60 and not fine_mode:
                    F.add("heuristic", "tiny_regions", f"{a['tiny_regions']} very small enclosed areas detected; may be hard for ages {spec.get('age_min')}–{spec.get('age_max')}.", pid_, num)
                if a["isolated_specks"] > 80:
                    F.add("heuristic", "noisy_edges", f"{a['isolated_specks']} isolated specks detected; consider Cleanup.", pid_, num)
    for sha, where in hashes.items():
        if len(where) > 1:
            F.add("warning", "duplicate_artwork", f"The same artwork appears on pages {', '.join(str(w[1]) for w in where)}.",
                  where[1][0], where[1][1])
    for i in range(len(dhashes)):
        for j in range(i + 1, len(dhashes)):
            if dhashes[i][3] != dhashes[j][3] and hamming(dhashes[i][0], dhashes[j][0]) <= 3:
                F.add("heuristic", "near_duplicate", f"Pages {dhashes[i][2]} and {dhashes[j][2]} look very similar (perceptual hash).",
                      dhashes[j][1], dhashes[j][2])

    # --- cover ---
    cv = snap["cover"]
    if cv.get("stale"):
        F.add("error", "cover_stale", "Cover geometry is stale: " + " ".join(cv["stale_reasons"]) + " Open the cover designer and recalculate.")
    fresh = cover_geometry(cfg, max(n, 24), float(cv["data"].get("spine_text_pt") or 10))
    g = cv["geometry"]
    if abs(fresh["full_width_in"] - g["full_width_in"]) > 0.001 or abs(fresh["full_height_in"] - g["full_height_in"]) > 0.001:
        F.add("error", "cover_size_mismatch", f"Cover is {g['full_width_in']}×{g['full_height_in']} in but should be "
                                            f"{fresh['full_width_in']}×{fresh['full_height_in']} in for {n} pages.")
    if cv["data"].get("spine_text_enabled") and not fresh["spine_text"]["eligible"]:
        F.add("error", "spine_text_ineligible", "Spine text is enabled but not allowed: " + " ".join(fresh["spine_text"]["reasons"]))
    L = cover_layout(snap)
    bc = L["barcode"]
    for name in ("back_copy_box",):
        if L[name].intersects(bc) and L["back_copy"].strip():
            F.add("error", "barcode_overlap", "Back-cover text overlaps the barcode reservation.")
    if L.get("back_art"):
        if L["back_art"].intersects(bc):
            F.add("error", "barcode_overlap", "The back-cover illustration overlaps the barcode reservation.")
        if not Rect(**g["back_safe"]).contains(L["back_art"]):
            F.add("warning", "back_art_outside_safe", "The back-cover illustration extends outside the back safe area.")
    for t in L["thumbs"]:
        if t["rect"].intersects(bc):
            F.add("error", "barcode_overlap", "A back-cover thumbnail overlaps the barcode reservation.")
    fs, bs = Rect(**g["front_safe"]), Rect(**g["back_safe"])
    for key in ("title_box", "subtitle_box", "author_box"):
        if L[key].h > 0 and not fs.contains(L[key]):
            F.add("error", "cover_text_outside_safe", f"Cover {key.split('_')[0]} extends outside the front safe area.")
    if L["art"] and not fs.contains(L["art"]):
        F.add("warning", "cover_art_outside_safe", "Front artwork extends outside the safe area; edges may be trimmed.")
    if not L["art"]:
        F.add("warning", "cover_no_art", "The front cover has no artwork selected.")
    else:
        v = snap["versions"][cv["data"]["front_art_version_id"]]
        dpi = v["width_px"] / L["art"].w
        if v.get("upscaled"):
            dpi = dpi * v["original_width_px"] / v["width_px"]
        if dpi < 300:
            F.add("warning", "cover_art_dpi", f"Front cover art is {dpi:.0f} effective DPI (target 300).")
    listing = snap["listing"]
    titles = {"cover": (L["title"] or "").strip(), "listing": (listing.get("title") or "").strip(), "book plan": (spec.get("title") or "").strip()}
    if len(set(t.lower() for t in titles.values())) > 1:
        F.add("warning", "title_mismatch", "Title differs between " + ", ".join(f"{k}: “{v}”" for k, v in titles.items()) + ".")
    if (cv["data"].get("author") or spec.get("author", "")).strip() != (listing.get("author") or "").strip():
        F.add("warning", "author_mismatch", "Author name on the cover differs from the listing.")

    # --- protected names (heuristic list; not legal advice) ---
    from .ip_guard import scan_project
    for h in scan_project(snap):
        if h["licensed"]:
            F.add("review", "licensed_name", f"“{h['matched']}” in {h['where']} – you declared a license ({h['license_evidence']}). "
                  "Make sure it covers print books sold on Amazon.", h.get("page_id"), h.get("page_number"), term=h["term"])
        else:
            F.add(h["severity"], "protected_name",
                  f"“{h['matched']}” in {h['where']} looks like a protected character/brand ({h['owner']}). Using it without a "
                  "license risks takedown and account action. Replace it with your own original name or design.",
                  h.get("page_id"), h.get("page_number"), term=h["term"], where=h["where"])

    # --- human publishing review ---
    if unapproved:
        F.add("review", "unapproved_pages", f"{unapproved} illustration page(s) have not been approved by you.")
    groups: dict[str, list] = {"demo_artwork": [], "rights_unknown": [], "ai_unknown": [], "ai_disclosure": [], "asset_flagged": []}
    for aid, a in snap["assets"].items():
        if a.get("is_demo"):
            groups["demo_artwork"].append((aid, a["display_name"]))
        if a["rights_declaration"] == "unknown":
            groups["rights_unknown"].append((aid, a["display_name"]))
        if a["ai_involvement"] == "unknown":
            groups["ai_unknown"].append((aid, a["display_name"]))
        if a["ai_involvement"] == "ai_generated":
            groups["ai_disclosure"].append((aid, a["display_name"]))
        if a["review_status"] in ("needs_changes", "rejected"):
            groups["asset_flagged"].append((aid, a["display_name"]))
    texts = {
        "demo_artwork": "{n} artwork file(s) are demonstration sample art. Replace them or confirm you accept them before publishing.",
        "rights_unknown": "Rights are not declared for {n} artwork file(s). Declare who created them and your right to sell them.",
        "ai_unknown": "AI involvement is unknown for {n} artwork file(s); KDP's disclosure questions need it.",
        "ai_disclosure": "{n} artwork file(s) are AI-generated; you must disclose AI-generated images to KDP.",
        "asset_flagged": "{n} artwork file(s) are marked as needing changes or rejected.",
    }
    for code, items in groups.items():
        if items:
            F.add("review", code, texts[code].format(n=len(items)), asset_ids=[i[0] for i in items],
                  names=[i[1] for i in items][:50])
    if not (listing.get("description") or "").strip():
        F.add("review", "listing_description", "The listing description is empty. “Draft from my book” on the Listing page writes a first version.")
    from .listing_draft import listing_checks
    for c in listing_checks(listing):
        if c["severity"] != "tip":
            F.add("warning", "listing_" + c["code"], c["message"])
    from .studio import DEFAULT_COVER
    back = (snap["cover"]["data"].get("back_copy") or "").strip()
    if not back:
        F.add("review", "back_cover_text", "The back cover has no text. “Draft back-cover text” on the Cover page writes a first version.")
    elif back == DEFAULT_COVER["back_copy"].strip() and not snap["project"]["is_sample"]:
        F.add("warning", "back_cover_sample_text", "The back-cover text is still the sample book's text (sunny island, 40 illustrations). "
                                                   "Replace it on the Cover page.")
    if listing.get("isbn_choice", "undecided") == "undecided":
        F.add("review", "isbn_choice", "Decide whether to use a free KDP ISBN or your own.")

    # dedupe identical demo/rights messages so the report stays readable
    seen, items = set(), []
    for f in F.items:
        key = (f["code"], f["page_id"], f["message"])
        if key not in seen:
            seen.add(key)
            items.append(f)
    items.sort(key=lambda f: (SEVERITY_ORDER[f["severity"]], f["page_number"] or 0))
    counts = {s: sum(1 for f in items if f["severity"] == s) for s in SEVERITY_ORDER}
    if counts["error"]:
        status, label = "blocked", "Blocked – fix technical errors before a print-release package"
    elif counts["review"]:
        status, label = "needs_review", "Technical checks pass – human review items remain"
    else:
        status, label = "ready_for_kdp_review", "Ready for your KDP review"
    return {"status": status, "status_label": label, "counts": counts, "findings": items, "page_count": n,
            "disclaimer": "Preflight checks files against this app's dated KDP profile. Passing preflight is not Amazon approval. "
                          "Artwork heuristics are estimates and cannot certify quality or legal ownership."}


def run_and_store(studio, pid: str) -> dict:
    from .snapshot import build_snapshot
    snap = build_snapshot(studio, pid)
    rep = run(studio, snap)
    rid = new_id("pf")
    with studio.db.tx():
        studio.db.x("INSERT INTO preflight_runs(id, project_id, created_at, layout_revision, summary) VALUES (?,?,?,?,?)",
                    (rid, pid, now_iso(), snap["layout_revision"], jdump({k: rep[k] for k in ("status", "status_label", "counts", "page_count", "disclaimer")})))
        for f in rep["findings"]:
            studio.db.x("INSERT INTO preflight_findings(id, run_id, severity, category, code, message, page_id, page_number, detail) VALUES (?,?,?,?,?,?,?,?,?)",
                        (new_id("pff"), rid, f["severity"], f["category"], f["code"], f["message"], f["page_id"], f["page_number"], jdump(f["detail"])))
    rep["run_id"] = rid
    rep["created_at"] = now_iso()
    return rep


def to_markdown(rep: dict, title: str) -> str:
    lines = [f"# Preflight report – {title}", "", f"**Status:** {rep['status_label']}", "",
             f"Interior pages: {rep['page_count']}", "",
             f"> {rep['disclaimer']}", ""]
    heads = {"error": "Technical errors (block release)", "warning": "Technical warnings",
             "heuristic": "Artwork quality heuristics (estimates – review them)", "review": "Human publishing-review items"}
    for sev, head in heads.items():
        items = [f for f in rep["findings"] if f["severity"] == sev]
        lines.append(f"## {head} ({len(items)})")
        lines.append("")
        if not items:
            lines.append("None.")
        for f in items:
            where = f"page {f['page_number']}: " if f.get("page_number") else ""
            lines.append(f"- `{f['code']}` {where}{f['message']}")
        lines.append("")
    return "\n".join(lines)
