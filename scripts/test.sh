#!/usr/bin/env bash
# Run all automated tests (unit, export/file verification, jobs, browser journey).
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d .venv ] && . .venv/bin/activate
pip install -q -r backend/requirements-dev.txt
python -m playwright install chromium >/dev/null 2>&1 || true
(cd frontend && npm run build)
cd backend && python -m pytest -v tests
