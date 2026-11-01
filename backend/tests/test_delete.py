"""Deleting a book removes it, keeps a backup, and the sample is not re-seeded on restart."""
from fastapi.testclient import TestClient

from cbs.api import create_app


def test_delete_book_and_sample_stays_deleted(settings, monkeypatch):
    monkeypatch.setenv("CBS_SEED_SAMPLE", "1")
    monkeypatch.setattr("cbs.seed.seed_sample", lambda st: st.create_project("Sample", {"illustration_count": 2}, is_sample=True))
    H = {"x-cbs-client": "1"}
    with TestClient(create_app(settings)) as c:
        projects = c.get("/api/projects").json()
        assert len(projects) == 1
        pid = projects[0]["id"]
        assert c.delete(f"/api/projects/{pid}").status_code == 403  # CSRF guard
        r = c.delete(f"/api/projects/{pid}", headers=H)
        assert r.status_code == 200 and c.get("/api/projects").json() == []
        assert c.get(f"/api/projects/{pid}").status_code == 404
    assert list(settings.backups_dir.glob(f"{pid}-*.cbsproj"))
    with TestClient(create_app(settings)) as c:  # restart
        assert c.get("/api/projects").json() == []
