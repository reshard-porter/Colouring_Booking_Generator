"""Deterministic interior assembly.

Content pages (intro + illustration) are stored in order. Blank reverses and parity pages are
DERIVED here, never stored, so reordering/removing pages can't break the blank-back rule.
"""
from __future__ import annotations


def assemble(pages: list[dict], spec: dict) -> dict:
    blank_backs = bool(spec.get("blank_backs", True))
    intro = [p for p in pages if p["kind"] == "intro"]
    illus = [p for p in pages if p["kind"] == "illustration"]
    out: list[dict] = []
    notes: list[str] = []

    def emit(kind, page=None, reason=None):
        n = len(out) + 1
        out.append({"number": n, "side": "recto" if n % 2 else "verso", "kind": kind,
                    "page_id": page["id"] if page else None, "blank_reason": reason})

    for p in intro:
        emit("intro", p)
    if spec.get("facing_text") and illus:
        # Story layout: every illustration is a right-hand page with its story on the left-hand page facing it.
        # The story for picture k+1 is printed on the back of picture k, so no separate blank backs are needed.
        if len(out) % 2 == 0:
            emit("blank", reason="parity")
            notes.append("Inserted a blank page after the introductory pages so every story starts on a left-hand page "
                         "facing its picture.")
        for p in illus:
            n = len(out) + 1
            out.append({"number": n, "side": "verso", "kind": "story", "page_id": None, "story_for": p["id"], "blank_reason": None})
            emit("illustration", p)
        if len(out) % 2 == 1:
            emit("blank", reason="end")
            notes.append("Added a final blank page so the interior has an even page count.")
        return _summary(out, intro, illus, notes)
    if blank_backs and illus and len(out) % 2 == 1:
        emit("blank", reason="parity")
        notes.append(f"Inserted a blank page after the {len(intro)} introductory pages so every illustration "
                     "starts on a right-hand (odd) page with a blank back.")
    for p in illus:
        emit("illustration", p)
        if blank_backs:
            emit("blank", reason="back")
    if len(out) % 2 == 1:
        emit("blank", reason="end")
        notes.append("Added a final blank page so the interior has an even page count.")
    return _summary(out, intro, illus, notes)


def _summary(out, intro, illus, notes) -> dict:
    return {
        "pages": out,
        "page_count": len(out),
        "illustration_count": len(illus),
        "intro_count": len(intro),
        "blank_count": sum(1 for p in out if p["kind"] == "blank"),
        "story_count": sum(1 for p in out if p["kind"] == "story"),
        "parity_notes": notes,
    }
