# Architecture

**Choice:** one Python process (FastAPI + an in-process background worker thread) with SQLite and a content-addressed file store, plus a React/TypeScript single-page UI that the same process serves. No second server language, queue service, or cloud dependency. Python was chosen because the print-critical parts (PDF writing with ReportLab, PDF reading with pypdf, rasterizing with PDFium, image processing with Pillow/NumPy/SciPy) are mature and permissively licensed there.

```
Browser (React/TS) ──HTTP /api──► FastAPI (localhost only, CSRF header guard, trusted hosts)
                                      │
                    ┌─────────────────┼───────────────────────────┐
                    ▼                 ▼                           ▼
              Studio service     JobRunner thread           Render engine
       (projects, assets, pages,  (SQLite jobs table:        geometry.py ─┐
        cover, backups)            queued/running/…,          layout.py   ├─ shared by preview,
                    │              dedupe, cancel, retry,     render.py ──┘  export & preflight
                    ▼              restart recovery)          verify.py (re-opens real files)
        SQLite (WAL) + files/ab/<sha256>.png  ◄──── immutable asset versions
```

## Key decisions

- **Canonical units:** inches for all stored geometry, converted to PDF points (72/in) only at render time. Pixels only become DPI in combination with a placed physical size (`effective_dpi = cropped pixels / placed inches`); metadata DPI is stored but never trusted.
- **One geometry module** (`geometry.py`) feeds the editor API, the exact preview (which renders the page through the export code and rasterizes it with PDFium), preflight, and the exporter, so preview and output cannot disagree.
- **Images can't be stretched:** an image element stores x, y, width, rotation and crop; height is always derived from the cropped aspect ratio.
- **Blank backs are derived, not stored.** Only content pages are persisted; `layout.assemble` inserts blank reverses, a visible parity page after an odd intro block, and an end page for even counts. Reordering/deleting can't break the rule.
- **Immutable asset versions.** Every edit (adjust, threshold, cleanup, erase, upscale, colorize) writes a new version file keyed by SHA-256 with `parent_version_id` and the operation. Provenance (source, rights, AI involvement, generation record) lives on the asset, so every version inherits it; AI-generated assets can't be downgraded to “no AI”. Upscaled versions keep `original_width_px`, and preflight judges resolution by the original detail.
- **Snapshots:** an export first freezes the full project (spec, assembled pages, element placements, referenced versions + hashes, cover, listing, pricing profile) into `export_snapshots` with its SHA-256. The job renders only from that snapshot and writes `manifest.json` mapping every PDF page to the exact asset versions and placements.
- **Verification after export:** `verify.py` re-opens interior and cover PDFs: page count, MediaBox/TrimBox per page, fonts embedded, blank pages truly white, no color on a black-ink interior, cover size, barcode area white, file sizes. A failing check fails the job.
- **Stale cover:** cover geometry stores the page count and paper it was computed for; any mismatch marks it stale (UI banner + preflight error) until recalculated.
- **Jobs:** durable rows with status, timestamps, progress, attempts/max_attempts, cancel flag and dedupe key (partial unique index ⇒ one active export per project). On restart, interrupted idempotent jobs are re-queued; billable generation jobs become `needs_attention` and their requests `unknown_outcome` — never blindly retried.
- **Replaceable interfaces:** `Storage` protocol (`LocalFileStorage`), `ImageProvider` protocol (`OpenAIImagesProvider`, test-only `MockProvider`), job handlers registry, JSON print profiles and pricing profiles (pricing profiles are versioned rows in SQLite and editable via API).
- **Security for a local app:** binds 127.0.0.1 and refuses other hosts; TrustedHost middleware against DNS rebinding; mutating requests require an `X-CBS-Client` header (blocks cross-site form posts); uploads are sniffed by magic bytes, size- and pixel-limited (decompression-bomb guard), fully decoded, names sanitized; storage keys are path-checked; SVG is refused; API keys live in env or a 0600 file and are never returned or exported.

## Data model (SQLite, `migrations/001_init.sql`)

projects · book_specs · style_guides · listings · scenes · assets · asset_versions · pages · page_elements · page_history · cover_layouts · jobs · preflight_runs · preflight_findings · export_snapshots · exports · pricing_profiles · settings · generation_requests
