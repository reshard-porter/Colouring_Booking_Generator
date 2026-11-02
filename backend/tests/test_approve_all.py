"""'Approve everything': declare rights for the book's artwork and approve all illustration pages that have art."""
import pytest

from cbs.bulk_review import approve_everything, plan, unapprove_pages
from conftest import line_art_png


def _book_with_art(studio, n_art=10, ai_vids=()):
    pid = studio.create_project("Approve", {"illustration_count": 12, "author": "R. Porter"})
    pages = [p for p in studio.pages(pid) if p["kind"] == "illustration"]
    aids = []
    for i, p in enumerate(pages[:n_art]):
        decl = {"source_type": "unknown", "ai_involvement": "unknown", "rights_declaration": "unknown"}
        if i in ai_vids:
            decl = {"source_type": "ai_generated", "ai_involvement": "ai_generated", "rights_declaration": "unknown",
                    "creator": "openai gpt-image-2.5", "generation": {"provider": "openai", "model": "gpt-image-2.5"}}
        a = studio.import_asset(pid, f"p{i}.png", line_art_png(900, 1200, seed=i), decl)
        studio.place_asset(p["id"], a["current_version_id"])
        aids.append(a["id"])
    return pid, aids


def test_plan_then_approve_everything(studio):
    pid, aids = _book_with_art(studio, ai_vids=(0, 1))
    studio.update_asset_provenance(aids[2], {"review_status": "needs_changes"})
    pl = plan(studio, pid)
    assert pl["pages_to_approve"] == 10 and len(pl["pages_without_art"]) == 2
    assert pl["rights_to_declare"] == 9 and pl["ai_unknown"] == 7 and pl["ai_generated"] == 2 and len(pl["flagged"]) == 1
    with pytest.raises(ValueError, match="confirmation"):
        approve_everything(studio, pid, confirm=False)
    r = approve_everything(studio, pid, confirm=True, ai_for_unknown="none")
    assert r["pages_approved"] == 10 and r["rights_declared"] == 9 and r["artwork_approved"] == 9 and r["ai_status_set"] == 7
    a0, a2, a5 = studio.asset(aids[0]), studio.asset(aids[2]), studio.asset(aids[5])
    assert a0["ai_involvement"] == "ai_generated" and a0["rights_declaration"] == "owner_declared" and a0["creator"] == "openai gpt-image-2.5"
    assert a2["review_status"] == "needs_changes" and a2["rights_declaration"] == "unknown"  # flagged art is left alone
    assert a5["ai_involvement"] == "none" and a5["source_type"] == "user_created" and a5["creator"] == "R. Porter"
    assert "Approve everything" in a5["review_notes"]
    from cbs.preflight import run_and_store
    found = {f["code"]: f["message"] for f in run_and_store(studio, pid)["findings"]}
    assert found["unapproved_pages"].startswith("2 illustration page(s)")  # only the two pages that have no art yet
    assert "ai_disclosure" in found  # AI images still need disclosing
    assert r["still_open"]["flagged"] == ["p2.png"] and len(r["still_open"]["pages_without_art"]) == 2
    # second run: nothing left to do; undo takes back page approvals only
    again = approve_everything(studio, pid, confirm=True)
    assert again["pages_approved"] == again["rights_declared"] == 0
    assert unapprove_pages(studio, pid)["pages_unapproved"] == 10
    assert studio.asset(aids[5])["rights_declaration"] == "owner_declared"


def test_leave_ai_unknown_and_demo_art_untouched(studio):
    pid2, aids = _book_with_art(studio, n_art=3)
    approve_everything(studio, pid2, confirm=True)  # default: leave AI unknown
    assert all(studio.asset(a)["ai_involvement"] == "unknown" for a in aids)
    demo = studio.import_asset(pid2, "demo.png", line_art_png(900, 1200, seed=9),
                               {"source_type": "demo_sample", "ai_involvement": "none", "rights_declaration": "unknown", "is_demo": True})
    p = [p for p in studio.pages(pid2) if p["kind"] == "illustration"][5]
    studio.place_asset(p["id"], demo["current_version_id"])
    pl = plan(studio, pid2)
    assert pl["demo_art"] == ["demo.png"] and pl["rights_to_declare"] == 0
    approve_everything(studio, pid2, confirm=True)
    assert studio.asset(demo["id"])["rights_declaration"] == "unknown"
    with pytest.raises(ValueError):
        approve_everything(studio, pid2, confirm=True, ai_for_unknown="maybe")


def test_api(settings, monkeypatch):
    monkeypatch.setenv("CBS_SEED_SAMPLE", "0")
    from fastapi.testclient import TestClient
    from cbs.api import create_app
    H = {"x-cbs-client": "1"}
    app = create_app(settings)
    with TestClient(app) as c:
        pid, _ = _book_with_art(app.state.studio, n_art=4)
        assert c.get(f"/api/projects/{pid}/approve-all").json()["pages_to_approve"] == 4
        assert c.post(f"/api/projects/{pid}/approve-all", json={}, headers=H).status_code == 400
        r = c.post(f"/api/projects/{pid}/approve-all", json={"confirm": True, "ai_for_unknown": "ai_assisted"}, headers=H).json()
        assert r["pages_approved"] == 4 and r["ai_status_set"] == 4
        assert c.post(f"/api/projects/{pid}/unapprove-all", headers=H).json()["pages_unapproved"] == 4
