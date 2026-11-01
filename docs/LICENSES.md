# Dependency & license notes

Audited 2026-10-30 from installed package metadata. All runtime dependencies are permissive; none are copyleft in a way that affects distributing this app.

## Python runtime (`backend/requirements.lock`)

| Package | Version | License |
|---|---|---|
| fastapi | 0.162.0 | MIT |
| starlette | 1.7.0 | BSD-3-Clause |
| uvicorn | 0.54.0 | BSD-3-Clause |
| python-multipart | 0.0.32 | Apache-2.0 |
| pydantic / pydantic-core | 2.13.5 / 2.46.5 | MIT |
| httpx / httpcore / h11 | 0.28.1 / 1.0.9 / 0.16.0 | BSD-3 / BSD-3 / MIT |
| anyio, sniffio, click, idna, typing-extensions, annotated-types, annotated-doc, typing-inspection, charset-normalizer | – | MIT / BSD / PSF |
| opentelemetry-api (required by fastapi) | 1.45.2 | Apache-2.0 |
| certifi | 2026.10.18 | MPL-2.0 (file-level; unmodified use is fine) |
| Pillow | 12.3.0 | MIT-CMU (HPND) |
| ReportLab (open-source toolkit) | 5.0.1 | BSD |
| pypdf | 6.17.0 | BSD-3-Clause |
| pypdfium2 (bundles PDFium) | 5.13.0 | BSD-3-Clause / Apache-2.0 (+ PDFium's BSD-style deps) |
| NumPy | 2.5.3 | BSD-3-Clause (+ bundled permissive) |
| SciPy | 1.18.1 | BSD-3-Clause |

Dev/test only: pytest 9.1.1 (MIT), Playwright 1.63.0 (Apache-2.0).

## Frontend (`frontend/package-lock.json`)

Shipped in the UI bundle: react, react-dom, scheduler (MIT). Build tools only (not shipped): vite, rolldown, @vitejs/plugin-react, postcss, nanoid, picocolors, tinyglobby, fdir, picomatch, source-map-js (MIT/ISC/BSD), typescript (Apache-2.0), detect-libc (Apache-2.0), lightningcss (MPL-2.0, build-time only).

## Fonts

DejaVu Sans / DejaVu Sans Bold (`backend/cbs/assets/fonts`, copied to `frontend/public`): Bitstream Vera license + public-domain DejaVu changes — free to use, embed and redistribute, including commercially; full text in `DejaVu-LICENSE.txt`. These fonts are embedded (subset) in every exported PDF.

## External tools (not bundled)

FFmpeg is invoked as a separate program if the user has it installed. Its license (LGPL or GPL depending on the build) applies to that binary, not to this app's code.

## Content

- Sample illustrations are generated at runtime by `democraft.py` (code in this repository) — demonstration placeholders, not AI output, not commercially reviewed.
- KDP rule values in `profiles/*.json` are facts with source URLs and dates; they are not copied text.
- AI providers' outputs are governed by the provider's terms. The app makes no claims about exclusivity, copyrightability or commercial-use rights.
