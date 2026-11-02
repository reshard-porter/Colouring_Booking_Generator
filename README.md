# Coloring Book Studio

![tests](https://github.com/reshard-porter/Colouring_Booking_Generator/actions/workflows/tests.yml/badge.svg)

Coloring Book Studio is a local app that turns a book idea into a KDP-ready coloring book. Import one brief file, pick a kid-friendly style, and OpenAI draws every page, intro page and cover. The app cleans the line art, lays out pages, sizes the cover, checks print rules, and exports interior and cover PDFs with a listing draft and AI disclosure.

- Works with **no subscription and no AI key**: import → edit → layout → cover → preflight → export all run offline after installation.
- Binds to **localhost only**. No accounts, no analytics, nothing leaves your computer unless you use optional AI generation.
- Does **not** talk to Amazon. There is no public KDP publishing API; the app never asks for Amazon credentials and never claims approval. “Ready for your KDP review” is the best status it gives.

> New to this? Read the [beginner walkthrough](docs/WALKTHROUGH.md).

## What runs now

| Area | Status |
|---|---|
| Projects, autosave, SQLite + file storage, migrations, portable backup/import (`.cbsproj`) | ✅ |
| Guided setup, offline scene planner with variety warnings, style guide | ✅ |
| PNG/JPEG import with rights/AI declarations, immutable versions, SHA-256 hashes | ✅ |
| Page editor: move/resize/rotate/crop/align, fit to page/safe area, undo/redo, autosave, page history restore, brightness/contrast, threshold, cleanup, eraser, before/after compare, text objects (embedded DejaVu font), trim/safe/binding overlays, keyboard controls, exact print preview | ✅ |
| Deterministic layout: intro pages, illustrations on right-hand pages, auto blank backs, parity pages, reorder/duplicate/delete/approve | ✅ |
| Interior PDF (no-bleed and full-bleed), cover PDF, contact sheet, ZIP package — verified by re-opening the real files | ✅ |
| Cover designer: geometry from page count + paper, barcode reservation, spine-text eligibility, colored cover art from interior art, official-template overlay, thumbnail check, stale-cover detection | ✅ |
| Preflight (errors / warnings / heuristics / human review), clickable, blocks release on errors | ✅ |
| Pricing calculator (Decimal, dated Amazon.com profile, scenarios) | ✅ |
| Listing draft, proposed AI-disclosure summary, KDP checklist | ✅ |
| Style presets for ORIGINAL characters: classic cartoon, anime-inspired, superhero comic, chibi/kawaii — drive scene drafts and AI prompts | ✅ |
| Original hero-team builder: team name/motto/HQ/emblem, heroes with role/powers/costume/emblem, offline name suggestions | ✅ |
| Protected-name check (Justice League, Marvel, popular anime, Disney, etc.): live warnings while typing, preflight errors in titles/keywords/cover/page text (block release), warnings in scenes/characters, refuses AI prompts; owner-declared licenses with evidence downgrade to review | ✅ (list-based, not legal advice) |
| Durable jobs: progress, cancel, bounded retry, restart recovery, duplicate-export prevention | ✅ |
| **Create with AI**: describe the book → pages planned → one sample to approve → remaining pages generated 3 at a time in the sample's style, made print-ready (pure black/white, specks removed, margins cropped), placed; optional full-color AI cover art; per-page quality checks and Regenerate (approved pages never replaced) | ✅ mocked end-to-end + browser test · ⚠ needs your OpenAI key, billed per image |
| **Listing helpers**: “Draft from my book” writes the Amazon description, back-cover text and keyword ideas from the book's own details (no sales claims, no search data); live checks for KDP's limits (title + subtitle ≤ 200, description ≤ 4000, 7 keyword boxes × 50); series name and number | ✅ tests + browser run |
| **Approve everything**: one confirmed step declares rights for the book's artwork, approves unreviewed artwork and every illustration page with art (AI status never downgraded; demo art, flagged art and empty pages excluded; page approvals can be taken back) | ✅ tests + browser run |
| **Next book in a series**: one click starts Book 2 with the same size, ages, style, master style, characters, intro pages and cover colors – story, pages, art and back text start empty | ✅ tests + browser run |
| **Kids' drawing styles (ages 3–7)**: 10 crayon-friendly presets (big & bold, cute animals, storybook, vehicles, sticker, doodle, find-and-color, fairy-tale, chibi, classic), each with its own style text; replace / combine / keep an existing master style, with restore | ✅ tests + browser run |
| **Book brief (.md or .json)**: one Markdown or JSON file (template layout, or free-form layouts such as plain `Heading:` lines, `[Act I]` sections and `- Page N:` lines) fills settings, book description, master style, characters/team, front & back cover, intro pages, every page description and the listing; preview before applying; export any book as a brief; **Create everything** generates all pages, intro art and both covers in one run | ✅ tests + browser run (templates: `docs/book-brief-template.md`, `docs/book-brief-template.json`) |
| OpenAI adapter checked against OpenAI's docs (2026-10-30): GPT Image 2.5 Sunburst/Flare & GPT Image 2, print-size 2400×3200 (≈320 DPI), style-reference edits, free “Test connection”, clear messages for bad key / organization verification / no credit, safe retries | ✅ contract tests with simulated OpenAI responses · ⚠ **not live-tested** – OpenAI isn't reachable from the build environment |
| Promo video (1080×1920 silent MP4 via FFmpeg) | ✅ when FFmpeg is installed; otherwise disabled with an explanation |
| SVG import | ❌ deliberately unsupported (no sanitizing renderer bundled) |

## Requirements

- Python **3.11+** (tested on 3.12 and 3.13)
- Node.js **20+** (tested on 22.23) — only needed to build the UI
- Optional: **FFmpeg** on your PATH for promo videos (book exports don't need it)

## Setup & start

```bash
scripts/setup.sh      # creates .venv, installs pinned Python deps, builds the UI
scripts/start.sh      # → http://127.0.0.1:8765
```

Manual equivalent:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.lock
(cd frontend && npm ci && npm run build)
cd backend && python -m cbs            # options: --port 8765 --data-dir PATH
```

On first start the app seeds the editable sample project **“Cute Island Adventures (sample)”**. Data lives in `~/.local/share/coloring-book-studio` (override with `CBS_DATA_DIR`). See `.env.example` for all settings.

UI development with hot reload: run the backend as above, then `cd frontend && npm run dev` (proxies `/api` to port 8765).

## Tests

```bash
scripts/test.sh                       # everything, incl. Chromium browser journey
cd backend && python -m pytest tests  # same, if deps are installed
```

What is tested and the exact results of the last run: [docs/VERIFICATION.md](docs/VERIFICATION.md).

## Sample exports

`sample-output/` contains a genuine package exported from the seeded project:

- `cute-island-adventures-draft-*.zip` — interior.pdf (84 pages, 612×792 pt), cover.pdf (17.439167 × 11.25 in), preview/contact-sheet.pdf, listing.md, preflight.json/.md, provenance.json, project.json, pricing.json, publishing-checklist.md, manifest.json
- `package/` — the same files unzipped
- `promo-sample.mp4` — 12 s, 1080×1920, H.264, no audio

It is a **DRAFT** package on purpose: the 40 sample illustrations are procedurally drawn **demonstration art** (made by `backend/cbs/democraft.py`, not by AI, not commercially reviewed) with undeclared rights, so a print-release package is correctly blocked until a human reviews them. Regenerate with `python scripts/export_sample.py`.

## Repository layout

```
backend/
  cbs/                 Python package (FastAPI app, worker, PDF engine)
    api.py             HTTP API + serves the built UI
    studio.py          service layer (projects, assets, pages, cover, backups)
    geometry.py        print geometry: trim, bleed, margins, placement, cover wrap
    layout.py          deterministic page assembly (blank backs, parity)
    render.py          interior/cover/contact-sheet rendering (ReportLab) + previews (PDFium)
    preflight.py       checks + report
    verify.py          re-opens exported PDFs and checks them
    exporter.py        snapshot → files → verification → ZIP (background job)
    jobs.py            durable SQLite job runner
    pricing.py         Decimal royalty calculator
    provenance.py      provenance records + proposed AI disclosure
    generation.py      optional AI workflow, budget, secrets
    providers/         image-provider interface, OpenAI adapter, test-only mock
    video.py           FFmpeg promo renderer
    imaging.py         upload validation, edit operations, heuristics
    democraft.py       procedural demo art for the sample
    profiles/          dated KDP print + pricing profiles (with sources)
    migrations/        SQL migrations
    assets/fonts/      DejaVu Sans (embedded in PDFs) + license
  tests/               pytest suite incl. browser journey
frontend/              React + TypeScript (Vite)
scripts/               setup/start/test, sample export
docs/                  architecture, walkthrough, licenses, verification, screenshots
sample-output/         genuine exported sample package + promo video
```

## Known limitations & what needs you

- **KDP rules change.** Profiles in `backend/cbs/profiles/` are dated 2026-10-30 and were read from KDP help pages (via search-indexed copies; direct fetching was blocked here). Before uploading, compare cover dimensions with KDP's [cover calculator](https://kdp.amazon.com/cover-calculator) and prices with the [royalty calculator](https://kdp.amazon.com/en_US/royalty-calculator).
- **Conflicts we flagged:** one KDP page text mentions the barcode at the lower *left* while the barcode help pages say lower *right* (the app reserves lower-right); KDP's “>79 pages” spine-text rule vs. third-party minimum spine widths (the app requires both the rule and a physical fit, so the 84-page default has **no spine text**).
- **AI generation** needs your own OpenAI API key and costs money; OpenAI may also require you to verify your organization before image models work. `gpt-image-1` was shut down by OpenAI on 2026-10-23, so the app now uses GPT Image 2.5. The adapter follows OpenAI's official API reference and is covered by contract tests, but has not made a real request (OpenAI isn't reachable from where it was built). Prices are never invented: you enter a per-image estimate, otherwise cost shows as “unknown” and batches stay disabled. Sizes above 3.7 MP (including the 2400×3200 print size) are marked “experimental” by OpenAI; if results disappoint, switch to Standard 1632×2176.
- **Colors:** the cover is RGB; no CMYK conversion or PDF/X claim. Order a proof copy.
- **Interior presets:** 8.5×11, 8×10, 8.5×8.5 in, black ink on white or cream. Maximum page counts per trim are not verified (preflight warns above 150 pages).
- **Protected-name check** uses a curated list of well-known names; it can't recognise every character, can't see drawings that imitate a character, and isn't legal advice. Search any hero name before publishing. The app deliberately has no feature for drawing existing copyrighted characters.
- **Heuristics** (gray fills, tiny regions, near-duplicates…) are estimates, not quality or legal certification.
- The editor's on-screen text is close to, but not guaranteed identical to, print; use **Exact print preview**, which uses the export renderer.
- Single-user local edition: no authentication. Don't expose it to a network without adding auth and project isolation (the server refuses non-local hosts).

## Owner actions before publishing

1. Replace the demo art (or declare rights for your own), approve every page.
2. Fill in listing description, ISBN choice, and answer KDP's AI questions yourself.
3. Export a print-release package, open the PDFs, upload to KDP, check the KDP previewer, order a proof.
