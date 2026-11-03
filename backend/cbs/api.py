"""FastAPI application. Binds to localhost by default; no authentication in the local edition."""
from __future__ import annotations

import io
import json
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import exporter, generation, preflight, pricing, stories, video
from .config import APP_VERSION, Settings
from .db import jdump, jload, now_iso
from .geometry import Rect, fit_element, print_profiles, resolve_config
from .imaging import UploadRejected, open_flat
from .jobs import DuplicateJob, JobRunner
from .provenance import disclosure
from .render import cover_layout_json, render_cover_png, render_interior_page_png
from .snapshot import build_snapshot
from .studio import Conflict, NotFound, Studio

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
BUILD_ID = "2026-11-03-story-pages"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    studio = Studio(settings)
    runner = JobRunner(studio)

    @asynccontextmanager
    async def lifespan(app):
        if settings.start_worker:
            runner.start()
        # seed the sample only once per installation, so deleting it is permanent
        if studio.db.q1("SELECT 1 FROM projects WHERE is_sample=1"):
            studio.set_setting("sample_seeded", True)
        elif os.environ.get("CBS_SEED_SAMPLE", "1") == "1" and not studio.get_setting("sample_seeded"):
            from .seed import seed_sample
            seed_sample(studio)
            studio.set_setting("sample_seeded", True)
        yield
        runner.stop()

    app = FastAPI(title="Coloring Book Studio", version=APP_VERSION, lifespan=lifespan)
    app.state.studio, app.state.runner = studio, runner
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver", "[::1]"])

    @app.middleware("http")
    async def csrf_guard(request: Request, call_next):
        # Mutating requests must carry a custom header, which browsers will not send cross-site without CORS.
        if request.url.path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS"):
            if request.headers.get("x-cbs-client") != "1":
                return JSONResponse({"detail": "Missing X-CBS-Client header"}, status_code=403)
        return await call_next(request)

    @app.exception_handler(NotFound)
    async def _nf(_, e):
        return JSONResponse({"detail": f"Not found: {e}"}, status_code=404)

    @app.exception_handler(Conflict)
    async def _cf(_, e):
        return JSONResponse({"detail": str(e)}, status_code=409)

    @app.exception_handler(UploadRejected)
    async def _ur(_, e):
        return JSONResponse({"detail": str(e)}, status_code=400)

    @app.exception_handler(ValueError)
    async def _ve(_, e):
        return JSONResponse({"detail": str(e)}, status_code=400)

    @app.exception_handler(DuplicateJob)
    async def _dj(_, e):
        return JSONResponse({"detail": "An identical job is already queued or running.", "job_id": e.job_id}, status_code=409)

    S, R = studio, runner

    async def body(request: Request) -> dict:
        try:
            return await request.json()
        except Exception:  # noqa: BLE001
            raise HTTPException(400, "Expected a JSON body")

    # ------------------------------------------------------------------ meta
    @app.get("/api/health")
    def health():
        return {"ok": True, "version": APP_VERSION, "time": now_iso()}

    @app.get("/api/meta")
    def meta():
        prof = print_profiles()
        return {"version": APP_VERSION, "build": BUILD_ID, "data_dir": str(settings.data_dir), "print_profiles": prof,
                "video": video.available(), "ai": generation.get_provider(S).status(), "bind": f"{settings.host}:{settings.port}"}

    # ------------------------------------------------------------------ projects
    @app.get("/api/projects")
    def projects():
        return S.list_projects()

    @app.post("/api/projects")
    async def create_project(request: Request):
        b = await body(request)
        pid = S.create_project(b.get("name"), b.get("spec") or {})
        return project_full(pid)

    @app.post("/api/projects/sample")
    def create_sample():
        from .seed import seed_sample
        return project_full(seed_sample(S))

    def project_full(pid):
        row = S.project_row(pid)
        spec = S.spec(pid)
        latest = S.db.q1("SELECT * FROM preflight_runs WHERE project_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1", (pid,))
        return {"project": {**row, "release_approval": jload(row["release_approval"])}, "spec": spec,
                "config": resolve_config(spec).as_dict(), "style_guide": S.style_guide(pid),
                "listing": S.listing(pid), "scenes": S.scenes(pid), "pages": S.pages(pid), "assembly": S.assembly(pid),
                "cover": S.cover(pid),
                "preflight_summary": ({**jload(latest["summary"]), "created_at": latest["created_at"],
                                       "layout_revision": latest["layout_revision"]} if latest else None)}

    @app.get("/api/projects/{pid}")
    def get_project(pid: str):
        return project_full(pid)

    @app.patch("/api/projects/{pid}")
    async def patch_project(pid: str, request: Request):
        b = await body(request)
        if "name" in b:
            S.rename_project(pid, str(b["name"]))
        return project_full(pid)

    @app.delete("/api/projects/{pid}")
    def delete_project(pid: str):
        S.backup_now(pid)
        S.delete_project(pid)
        return {"deleted": pid, "note": "A backup was saved before deletion."}

    @app.get("/api/projects/{pid}/backup")
    def backup(pid: str):
        data = S.export_project_archive(pid)
        name = f"{S.spec(pid)['title'][:40].replace(' ', '-')}.cbsproj"
        return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.post("/api/projects/{pid}/backup-now")
    def backup_now(pid: str):
        p = S.backup_now(pid)
        return {"saved": p.name}

    @app.post("/api/projects/import")
    async def import_project(file: UploadFile = File(...)):
        data = await file.read()
        pid = S.import_project_archive(data)
        return project_full(pid)

    # ------------------------------------------------------------------ book brief (.md)
    async def _brief_text(request: Request, file: UploadFile | None) -> str:
        from .brief import MAX_BRIEF_BYTES
        if file is not None:
            raw = await file.read(MAX_BRIEF_BYTES + 1)
        else:
            raw = str((await body(request)).get("text", "")).encode("utf-8")
        if len(raw) > MAX_BRIEF_BYTES:
            raise ValueError("The brief is larger than 2 MB.")
        if b"\x00" in raw:
            raise ValueError("That doesn't look like a text (.md) file.")
        return raw.decode("utf-8", errors="replace")

    @app.get("/api/brief/template.json")
    def brief_template_json():
        from .brief import template_json
        return Response(template_json(), media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="book-brief-template.json"'})

    @app.get("/api/projects/{pid}/brief.json")
    def project_export_brief_json(pid: str):
        from .brief import export_brief_json
        name = re.sub(r"[^A-Za-z0-9._-]+", "-", S.spec(pid)["title"]).strip("-")[:60] or "book"
        return Response(export_brief_json(S, pid), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{name}-brief.json"'})

    @app.get("/api/brief/template")
    def brief_template():
        from .config import PROFILE_DIR
        return Response((PROFILE_DIR / "book-brief-template.md").read_text(), media_type="text/markdown",
                        headers={"Content-Disposition": 'attachment; filename="book-brief-template.md"'})

    @app.post("/api/brief/parse")
    async def brief_parse(request: Request, file: UploadFile | None = File(None)):
        from .brief import parse_brief
        return parse_brief(await _brief_text(request, file))

    @app.post("/api/projects/from-brief")
    async def project_from_brief(request: Request, file: UploadFile | None = File(None)):
        from .brief import apply_brief, parse_brief, spec_from_settings
        parsed = parse_brief(await _brief_text(request, file))
        spec, _ = spec_from_settings(parsed["data"])
        pid = S.create_project(spec.get("title") or "Untitled book", {k: v for k, v in spec.items() if k != "theme"})
        res = apply_brief(S, pid, parsed["data"])
        return {"project_id": pid, "warnings": parsed["warnings"] + res["warnings"], "changes": res["changes"]}

    @app.post("/api/projects/{pid}/brief")
    async def project_apply_brief(pid: str, request: Request, file: UploadFile | None = File(None)):
        from .brief import apply_brief, parse_brief
        S.project_row(pid)
        parsed = parse_brief(await _brief_text(request, file))
        S.backup_now(pid)  # safety net before overwriting settings and descriptions
        res = apply_brief(S, pid, parsed["data"])
        return {"project_id": pid, "warnings": parsed["warnings"] + res["warnings"], "changes": res["changes"]}

    @app.get("/api/projects/{pid}/brief.md")
    def project_export_brief(pid: str):
        from .brief import export_brief
        name = re.sub(r"[^A-Za-z0-9-]+", "-", S.spec(pid)["title"]).strip("-")[:50] or "book"
        return Response(export_brief(S, pid), media_type="text/markdown",
                        headers={"Content-Disposition": f'attachment; filename="{name}-brief.md"'})

    # ------------------------------------------------------------------ spec / style / listing
    @app.put("/api/projects/{pid}/spec")
    async def put_spec(pid: str, request: Request):
        S.update_spec(pid, await body(request))
        return project_full(pid)

    @app.post("/api/projects/{pid}/spec/apply-slots")
    def apply_slots(pid: str):
        return {"added": S.ensure_illustration_slots(pid)}

    @app.put("/api/projects/{pid}/style")
    async def put_style(pid: str, request: Request):
        return S.update_style_guide(pid, await body(request))

    @app.put("/api/projects/{pid}/listing")
    async def put_listing(pid: str, request: Request):
        return S.update_listing(pid, await body(request))

    # ------------------------------------------------------------------ style presets, heroes, protected names
    @app.get("/api/style-presets")
    def style_presets():
        from .planning import load_presets
        return load_presets()

    @app.post("/api/projects/{pid}/style/preset")
    async def apply_preset(pid: str, request: Request):
        b = await body(request)
        return S.apply_style_preset(pid, b.get("key", ""), b.get("master"))

    # ------------------------------------------------------------------ story pages (text facing each picture)
    @app.get("/api/projects/{pid}/stories")
    def get_stories(pid: str):
        S.project_row(pid)
        sp = S.spec(pid)
        return {"facing_text": bool(sp.get("facing_text")), "story_words": int(sp.get("story_words") or 400),
                "rows": stories.list_stories(S, pid)}

    @app.put("/api/pages/{page_id}/story")
    async def put_story(page_id: str, request: Request):
        b = await body(request)
        return stories.set_story(S, page_id, b.get("text", ""), b.get("title"))

    @app.post("/api/projects/{pid}/stories/bulk")
    async def bulk_stories(pid: str, request: Request):
        b = await body(request)
        return stories.bulk_set(S, pid, b.get("text", ""))

    @app.post("/api/projects/{pid}/stories/estimate")
    async def stories_estimate(pid: str, request: Request):
        b = await body(request)
        rows = stories.list_stories(S, pid)
        ids = b.get("page_ids") or [r["page_id"] for r in rows if b.get("overwrite") or not r["text"].strip()]
        return stories.estimate_stories(S, pid, ids)

    @app.post("/api/projects/{pid}/stories/write")
    async def stories_write(pid: str, request: Request):
        b = await body(request)
        try:
            return stories.start_writing(S, R, pid, b.get("page_ids"), bool(b.get("confirm")), bool(b.get("overwrite")))
        except DuplicateJob as e:
            raise HTTPException(409, f"Stories are already being written (job {e.job_id}).")

    @app.get("/api/projects/{pid}/stories/{page_id}/preview.png")
    def story_preview(pid: str, page_id: str, dpi: int = 60):
        from .snapshot import build_snapshot
        snap = build_snapshot(S, pid)
        num = next((e["number"] for e in snap["assembly"]["pages"] if e.get("story_for") == page_id), None)
        if num is None:
            raise HTTPException(404, "This book has no story page for that picture (turn on story pages in Book setup).")
        return Response(render_interior_page_png(snap, S.storage.read, num, min(max(dpi, 20), 150)), media_type="image/png",
                        headers={"Cache-Control": "no-store"})

    @app.get("/api/projects/{pid}/approve-all")
    def approve_all_plan(pid: str):
        from .bulk_review import plan
        S.project_row(pid)
        return plan(S, pid)

    @app.post("/api/projects/{pid}/approve-all")
    async def approve_all(pid: str, request: Request):
        from .bulk_review import approve_everything
        b = await body(request)
        return approve_everything(S, pid, confirm=bool(b.get("confirm")), creator=b.get("creator"),
                                  ai_for_unknown=b.get("ai_for_unknown") or "leave")

    @app.post("/api/projects/{pid}/unapprove-all")
    def unapprove_all(pid: str):
        from .bulk_review import unapprove_pages
        return unapprove_pages(S, pid)

    @app.post("/api/projects/{pid}/listing/draft")
    def listing_draft(pid: str):
        from .listing_draft import draft_listing
        S.project_row(pid)
        return draft_listing(S, pid)

    @app.post("/api/listing/check")
    async def listing_check(request: Request):
        from .listing_draft import listing_checks
        b = await body(request)
        return {"checks": listing_checks({k: b.get(k) for k in ("title", "subtitle", "description", "keywords")})}

    @app.post("/api/projects/{pid}/series/next")
    async def series_next(pid: str, request: Request):
        from .series import start_next_book
        b = await body(request)
        return start_next_book(S, pid, (b.get("title") or "").strip() or None)

    @app.post("/api/projects/{pid}/heroes/suggest")
    async def suggest_hero(pid: str, request: Request):
        from .heroes import suggest_hero as sh, suggest_team
        b = await body(request)
        seed = b.get("seed")
        if b.get("kind") == "team":
            return suggest_team(seed)
        taken = {c.get("name", "") for c in S.style_guide(pid).get("characters", [])} | {str(n) for n in b.get("taken", [])}
        return sh(seed, taken)

    @app.post("/api/ip-check")
    async def ip_check_text(request: Request):
        from .ip_guard import find
        b = await body(request)
        return {"hits": find(str(b.get("text", ""))[:100000]),
                "note": "Checks a list of well-known names only. Not legal advice; a clean result is not a clearance."}

    @app.get("/api/projects/{pid}/ip-check")
    def ip_check_project(pid: str):
        return {"hits": S.ip_check(pid), "note": "Checks a list of well-known names only. Not legal advice."}

    # ------------------------------------------------------------------ scenes
    @app.get("/api/projects/{pid}/scenes")
    def scenes(pid: str):
        return {"scenes": S.scenes(pid), "warnings": S.plan_warnings(pid)}

    @app.post("/api/projects/{pid}/scenes")
    async def add_scene(pid: str, request: Request):
        return S.save_scene(pid, await body(request))

    @app.put("/api/projects/{pid}/scenes/{sid}")
    async def put_scene(pid: str, sid: str, request: Request):
        return S.save_scene(pid, await body(request), sid)

    @app.delete("/api/projects/{pid}/scenes/{sid}")
    def del_scene(pid: str, sid: str):
        S.delete_scene(pid, sid)
        return {"deleted": sid}

    @app.post("/api/projects/{pid}/scenes/draft")
    async def draft(pid: str, request: Request):
        b = await body(request)
        S.draft_plan(pid, b.get("count"), bool(b.get("replace")))
        return {"scenes": S.scenes(pid), "warnings": S.plan_warnings(pid)}

    # ------------------------------------------------------------------ assets
    @app.get("/api/projects/{pid}/assets")
    def assets(pid: str, kind: str | None = None):
        return S.assets(pid, kind)

    @app.post("/api/projects/{pid}/assets")
    async def upload(pid: str, file: UploadFile = File(...), declaration: str = Form("{}"), kind: str = Form("artwork")):
        if kind not in ("artwork", "cover_art", "reference", "template"):
            raise HTTPException(400, "bad kind")
        data = await file.read(settings.max_upload_bytes + 1)
        try:
            decl = json.loads(declaration)
        except json.JSONDecodeError:
            raise HTTPException(400, "declaration must be JSON")
        decl.pop("generation", None)  # generation metadata is recorded only by the app itself
        decl.pop("is_demo", None)
        return S.import_asset(pid, file.filename or "upload", data, decl, kind=kind)

    @app.get("/api/assets/{aid}")
    def get_asset(aid: str):
        return S.asset(aid)

    @app.patch("/api/assets/{aid}")
    async def patch_asset(aid: str, request: Request):
        return S.update_asset_provenance(aid, await body(request))

    thumb_dir = settings.data_dir / "cache" / "thumbs"
    thumb_dir.mkdir(parents=True, exist_ok=True)

    @app.get("/api/versions/{vid}/image")
    def version_image(vid: str, max: int = 0):
        v = S.version(vid)
        if max <= 0:
            return Response(S.storage.read(v["storage_key"]), media_type=v["mime"], headers={"Cache-Control": "max-age=31536000, immutable"})
        max = min(max, 2400)
        cp = thumb_dir / f"{v['sha256']}-{max}.png"
        if not cp.exists():
            im = open_flat(S.storage.read(v["storage_key"]))
            im.thumbnail((max, max), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "PNG", optimize=True)
            cp.write_bytes(buf.getvalue())
        return Response(cp.read_bytes(), media_type="image/png", headers={"Cache-Control": "max-age=31536000, immutable"})

    @app.get("/api/versions/{vid}")
    def get_version(vid: str):
        return S.version(vid)

    @app.post("/api/versions/{vid}/derive")
    async def derive(vid: str, request: Request):
        return S.derive_version(vid, await body(request))

    @app.post("/api/versions/{vid}/cover-art")
    def cover_art(vid: str):
        return S.derive_cover_art(vid)

    @app.get("/api/versions/{vid}/analysis")
    def analysis(vid: str):
        return {**S.asset_analysis(vid), "label": "Heuristic estimates – not a quality certification."}

    # ------------------------------------------------------------------ pages
    @app.get("/api/projects/{pid}/assembly")
    def assembly(pid: str):
        return S.assembly(pid)

    @app.post("/api/projects/{pid}/pages")
    async def add_page(pid: str, request: Request):
        b = await body(request)
        return S.add_page(pid, b.get("kind", "illustration"), b.get("after"))

    @app.post("/api/projects/{pid}/pages/reorder")
    async def reorder(pid: str, request: Request):
        b = await body(request)
        res = S.reorder_pages(pid, b["order"])
        return {**res, "assembly": S.assembly(pid), "cover": S.cover(pid)}

    @app.get("/api/pages/{page_id}")
    def get_page(page_id: str):
        p = S.page(page_id)
        return {"page": p, "geometry": S.page_geometry_for(p["project_id"], page_id)}

    @app.put("/api/pages/{page_id}/elements")
    async def put_elements(page_id: str, request: Request):
        b = await body(request)
        return S.save_elements(page_id, b["elements"], b.get("reason", "edit"))

    @app.post("/api/pages/{page_id}/duplicate")
    def dup(page_id: str):
        return S.duplicate_page(page_id)

    @app.delete("/api/pages/{page_id}")
    def del_page(page_id: str):
        pid = S.page(page_id)["project_id"]
        S.delete_page(page_id)
        return {"deleted": page_id, "assembly": S.assembly(pid), "cover": S.cover(pid)}

    @app.post("/api/pages/{page_id}/approve")
    async def approve(page_id: str, request: Request):
        b = await body(request)
        return S.set_page_approval(page_id, bool(b.get("approved", True)), b.get("note"))

    @app.patch("/api/pages/{page_id}")
    async def patch_page(page_id: str, request: Request):
        return S.update_page_meta(page_id, await body(request))

    @app.get("/api/pages/{page_id}/history")
    def history(page_id: str):
        return S.page_history(page_id)

    @app.post("/api/pages/{page_id}/restore/{hid}")
    def restore(page_id: str, hid: str):
        return S.restore_page_history(page_id, hid)

    @app.post("/api/pages/{page_id}/place")
    async def place(page_id: str, request: Request):
        b = await body(request)
        return S.place_asset(page_id, b["version_id"], b.get("fit", "safe"))

    @app.post("/api/pages/{page_id}/fit")
    async def fit(page_id: str, request: Request):
        """Server-side fit for a single element (same geometry code as export)."""
        b = await body(request)
        p = S.page(page_id)
        geo = S.page_geometry_for(p["project_id"], page_id)
        target = Rect(**(geo["safe"] if b.get("target", "safe") == "safe" else geo["trim"]))
        el = b["element"]
        return fit_element(el, S.version(el["asset_version_id"]), target)

    @app.get("/api/pages/{page_id}/preview.png")
    def page_preview(page_id: str, dpi: int = 60):
        p = S.page(page_id)
        snap = build_snapshot(S, p["project_id"])
        num = next(x["number"] for x in snap["assembly"]["pages"] if x["page_id"] == page_id)
        return Response(render_interior_page_png(snap, S.storage.read, num, min(max(dpi, 20), 150)), media_type="image/png",
                        headers={"Cache-Control": "no-store"})

    # ------------------------------------------------------------------ cover
    @app.get("/api/projects/{pid}/cover")
    def get_cover(pid: str):
        c = S.cover(pid)
        snap = build_snapshot(S, pid)
        return {**c, "layout": cover_layout_json(snap)}

    @app.put("/api/projects/{pid}/cover")
    async def put_cover(pid: str, request: Request):
        S.update_cover(pid, await body(request))
        return get_cover(pid)

    @app.post("/api/projects/{pid}/cover/recalc")
    def recalc(pid: str):
        S.recalc_cover(pid)
        return get_cover(pid)

    @app.get("/api/projects/{pid}/cover/preview.png")
    def cover_preview(pid: str, dpi: int = 40):
        snap = build_snapshot(S, pid)
        return Response(render_cover_png(snap, S.storage.read, min(max(dpi, 10), 100)), media_type="image/png",
                        headers={"Cache-Control": "no-store"})

    # ------------------------------------------------------------------ preflight / disclosure / pricing
    @app.post("/api/projects/{pid}/preflight")
    def run_preflight(pid: str):
        return preflight.run_and_store(S, pid)

    @app.get("/api/projects/{pid}/preflight/latest")
    def latest_preflight(pid: str):
        r = S.db.q1("SELECT * FROM preflight_runs WHERE project_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1", (pid,))
        if not r:
            return None
        findings = [dict(f) | {"detail": jload(f["detail"])} for f in S.db.q("SELECT * FROM preflight_findings WHERE run_id=?", (r["id"],))]
        findings.sort(key=lambda f: (preflight.SEVERITY_ORDER[f["severity"]], f["page_number"] or 0))
        cur = S.project_row(pid)["layout_revision"]
        return {**jload(r["summary"]), "run_id": r["id"], "created_at": r["created_at"], "findings": findings,
                "outdated": r["layout_revision"] != cur}

    @app.get("/api/projects/{pid}/disclosure")
    def get_disclosure(pid: str):
        return disclosure(build_snapshot(S, pid))

    @app.get("/api/pricing/profiles")
    def pricing_profiles():
        return S.pricing_profiles()

    @app.put("/api/pricing/profiles")
    async def put_pricing_profile(request: Request):
        return S.save_pricing_profile(await body(request))

    @app.post("/api/projects/{pid}/pricing")
    async def calc_pricing(pid: str, request: Request):
        b = await body(request)
        spec = S.spec(pid)
        cfg = resolve_config(spec)
        asm = S.assembly(pid)
        prof = S.active_pricing_profile(spec.get("marketplace", "Amazon.com"))
        return pricing.calculate(prof, max(asm["page_count"], 24), cfg.large_trim, b.get("list_price", "9.99"), b.get("scenario"))

    # ------------------------------------------------------------------ exports & jobs
    @app.post("/api/projects/{pid}/exports")
    async def start_export(pid: str, request: Request):
        b = await body(request)
        return exporter.request_export(S, R, pid, b.get("mode", "draft"), bool(b.get("include_sources")), bool(b.get("acknowledged_review")))

    @app.get("/api/projects/{pid}/exports")
    def exports(pid: str):
        return exporter.list_exports(S, pid)

    @app.get("/api/exports/{eid}/files/{rel:path}")
    def export_file(eid: str, rel: str):
        try:
            p = exporter.export_file_path(S, eid, rel)
        except KeyError:
            raise HTTPException(404, "File not found")
        mt = {"pdf": "application/pdf", "zip": "application/zip", "json": "application/json", "md": "text/markdown",
              "png": "image/png", "jpg": "image/jpeg"}.get(p.suffix.lstrip("."), "application/octet-stream")
        return FileResponse(p, media_type=mt, filename=p.name, content_disposition_type="inline" if mt == "application/pdf" else "attachment")

    @app.get("/api/jobs")
    def jobs(project_id: str | None = None):
        return R.list(project_id)

    @app.get("/api/jobs/{jid}")
    def job(jid: str):
        try:
            return R.get(jid)
        except KeyError:
            raise HTTPException(404, "job not found")

    @app.post("/api/jobs/{jid}/cancel")
    def cancel(jid: str):
        return R.cancel(jid)

    @app.post("/api/jobs/{jid}/retry")
    def retry(jid: str):
        return R.retry(jid)

    # ------------------------------------------------------------------ AI generation (optional)
    @app.get("/api/ai/status")
    def ai_status():
        prov = generation.get_provider(S)
        sec = generation.SecretStore(settings.secrets_path)
        return {"status": prov.status(), "capabilities": prov.capabilities(), "settings": S.get_setting("ai_provider", {}) or {},
                "defaults": generation.default_settings(prov),
                "text_models": __import__("cbs.providers.openai_text", fromlist=["x"]).TEXT_MODEL_CHOICES,
                "key_source": sec.source("OPENAI_API_KEY")}

    @app.put("/api/ai/settings")
    async def ai_settings(request: Request):
        b = await body(request)
        cur = S.get_setting("ai_provider", {}) or {}
        for k in ("model", "per_image_estimate", "spending_limit", "text_model", "per_story_estimate"):
            if k in b:
                v = b[k]
                if k in ("per_image_estimate", "spending_limit", "per_story_estimate") and v not in (None, ""):
                    from decimal import Decimal
                    if Decimal(str(v)) < 0:
                        raise ValueError(f"{k} must be ≥ 0")
                    v = str(v)
                cur[k] = v if v != "" else None
        S.set_setting("ai_provider", cur)
        return ai_status()

    @app.post("/api/ai/test")
    def ai_test():
        prov = generation.get_provider(S)
        if not hasattr(prov, "test_connection"):
            return {"ok": True, "message": "Test provider (mock) – no real connection."}
        return prov.test_connection()

    @app.put("/api/ai/key")
    async def ai_key(request: Request):
        b = await body(request)
        generation.SecretStore(settings.secrets_path).set("OPENAI_API_KEY", b.get("api_key"))
        return ai_status()

    @app.post("/api/projects/{pid}/generate/estimate")
    async def gen_estimate(pid: str, request: Request):
        b = await body(request)
        return generation.estimate(S, pid, len(b.get("scene_ids", [])), b.get("settings", {}), b.get("scene_ids", []))

    @app.post("/api/projects/{pid}/generate")
    async def gen(pid: str, request: Request):
        b = await body(request)
        return generation.start_generation(S, R, pid, b.get("scene_ids", []), b.get("settings", {}), bool(b.get("confirm")))

    @app.post("/api/projects/{pid}/autobook/plan")
    async def autobook_plan(pid: str, request: Request):
        b = await body(request)
        return generation.plan_from_description(S, pid, b.get("description", ""), int(b.get("count", 20)), b.get("preset"))

    @app.get("/api/projects/{pid}/autobook/status")
    def autobook_status(pid: str):
        return generation.autobook_status(S, pid)

    def _is_generated(vid):
        if not vid:
            return False
        try:
            a = S.asset(S.version(vid)["asset_id"])
        except NotFound:
            return False
        g = a.get("generation") or {}
        return bool(g.get("provider")) and not g.get("derived_from_asset")

    @app.post("/api/projects/{pid}/autobook/generate")
    async def autobook_generate(pid: str, request: Request):
        """mode=sample: first empty page only. mode=rest: all remaining empty pages (needs an approved sample)."""
        b = await body(request)
        st = generation.autobook_status(S, pid)
        ids = st["empty_scene_ids"]
        mode = b.get("mode", "rest")
        front = back = False
        if mode == "everything":
            ids = ids + [r["scene_id"] for r in S.intro_descriptions(pid) if r["description"] and not r["version_id"] and r["scene_id"]]
            cd = S.cover(pid)["data"]
            front = not cd.get("front_art_version_id") or bool(cd.get("front_description")) and not _is_generated(cd.get("front_art_version_id"))
            back = bool(cd.get("back_description")) and not cd.get("back_art_version_id")
            if not ids and not front and not back:
                raise ValueError("Everything already has artwork. Use Regenerate on anything you want to replace.")
        elif not ids:
            raise ValueError("Every illustration page already has artwork. Use Regenerate on pages you want to replace.")
        ids = ids[:1] if mode == "sample" else ids
        if not b.get("confirm"):
            est = generation.estimate(S, pid, len(ids) + int(front) + int(back), b.get("settings", {}), ids)
            est["breakdown"] = {"pages": len([i for i in ids if i in st["empty_scene_ids"]]), "intro": len([i for i in ids if i not in st["empty_scene_ids"]]),
                                "front_cover": front, "back_cover": back}
            return est
        return generation.start_generation(S, R, pid, ids, b.get("settings", {}), True, auto_cover=not front,
                                           cover=front, back_cover=back)

    @app.post("/api/projects/{pid}/autobook/cover")
    async def autobook_cover(pid: str, request: Request):
        b = await body(request)
        which = b.get("which", "front")
        if which not in ("front", "back"):
            raise ValueError("which must be front or back")
        if not b.get("confirm"):
            return generation.estimate(S, pid, 1, b.get("settings", {}), [])
        return generation.start_generation(S, R, pid, [], b.get("settings", {}), True,
                                           cover=which == "front", back_cover=which == "back")

    @app.get("/api/projects/{pid}/intro-descriptions")
    def intro_descriptions(pid: str):
        return S.intro_descriptions(pid)

    @app.put("/api/pages/{page_id}/intro-description")
    async def put_intro_description(page_id: str, request: Request):
        b = await body(request)
        return S.set_intro_description(page_id, str(b.get("description", "")), b.get("placement"))

    @app.post("/api/pages/{page_id}/generate-intro")
    async def generate_intro(page_id: str, request: Request):
        b = await body(request)
        p = S.page(page_id)
        if p["kind"] != "intro":
            raise ValueError("Not an introductory page.")
        row = next(r for r in S.intro_descriptions(p["project_id"]) if r["page_id"] == page_id)
        if not row["description"]:
            raise ValueError("Write a description for this page first.")
        if not b.get("confirm"):
            return generation.estimate(S, p["project_id"], 1, b.get("settings", {}), [row["scene_id"]])
        return generation.start_generation(S, R, p["project_id"], [row["scene_id"]], b.get("settings", {}), True,
                                           replace_page_ids=[page_id])

    @app.get("/api/projects/{pid}/page-descriptions")
    def page_descriptions(pid: str):
        return S.page_descriptions(pid)

    @app.put("/api/pages/{page_id}/description")
    async def put_page_description(page_id: str, request: Request):
        b = await body(request)
        return S.set_page_description(page_id, str(b.get("description", "")))

    @app.post("/api/projects/{pid}/page-descriptions/bulk")
    async def bulk_descriptions(pid: str, request: Request):
        b = await body(request)
        return S.bulk_page_descriptions(pid, str(b.get("text", "")), bool(b.get("add_pages", True)))

    @app.post("/api/pages/{page_id}/regenerate")
    async def regenerate(page_id: str, request: Request):
        b = await body(request)
        p = S.page(page_id)
        if p["approved"]:
            raise ValueError("This page is approved. Remove the approval first if you really want to replace it.")
        if not p["scene_id"]:
            raise ValueError("This page has no scene description to generate from.")
        return generation.start_generation(S, R, p["project_id"], [p["scene_id"]], b.get("settings", {}), bool(b.get("confirm")),
                                           replace_page_ids=[page_id])

    @app.post("/api/projects/{pid}/generations/recover")
    def gen_recover(pid: str):
        return {"recovered_asset_ids": generation.recover_unimported(S, pid)}

    @app.get("/api/projects/{pid}/generations")
    def gens(pid: str):
        return generation.generation_requests(S, pid)

    # ------------------------------------------------------------------ promo video
    @app.get("/api/video/status")
    def video_status():
        return video.available()

    @app.post("/api/projects/{pid}/promo")
    async def promo(pid: str, request: Request):
        b = await body(request)
        av = video.available()
        if not av["available"]:
            raise HTTPException(409, av["reason"])
        d = float(b.get("duration_s", 12))
        if not 4 <= d <= 30:
            raise ValueError("Duration must be 4–30 seconds")
        return R.enqueue("promo_video", pid, {"duration_s": d, "captions": b.get("captions", []), "title": b.get("title"),
                                              "max_pages": int(b.get("max_pages", 4))}, dedupe_key=f"promo:{pid}")

    @app.get("/api/videos/{name}")
    def get_video(name: str):
        p = (settings.exports_dir / "videos" / name).resolve()
        if p.parent != (settings.exports_dir / "videos").resolve() or not p.is_file():
            raise HTTPException(404, "not found")
        return FileResponse(p, media_type="video/mp4")

    # ------------------------------------------------------------------ frontend
    if FRONTEND_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="static")

        @app.get("/{full_path:path}")
        def spa(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(404)
            f = (FRONTEND_DIST / full_path).resolve()
            if full_path and f.is_file() and FRONTEND_DIST.resolve() in f.parents:
                return FileResponse(f)
            # never cache the page shell, so an updated app is picked up on the next reload
            return FileResponse(FRONTEND_DIST / "index.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    else:
        @app.get("/")
        def no_ui():
            return JSONResponse({"detail": "Frontend not built. Run `npm run build` in frontend/."})

    return app
