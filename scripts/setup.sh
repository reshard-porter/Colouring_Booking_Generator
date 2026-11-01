#!/usr/bin/env bash
# One-time setup. Requires Python 3.11+ (tested 3.12/3.13). Node.js is only needed if frontend/dist is missing.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
if ! $PY -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
  echo "Python 3.11 or newer is required (found: $($PY --version 2>&1)). Install it from python.org and run again." >&2
  exit 1
fi
[ -d .venv ] || $PY -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade --quiet pip || true
echo "Installing Python packages (this can take a few minutes)…"
for attempt in 1 2 3; do
  if pip install --default-timeout=120 --retries 10 -r backend/requirements.lock; then ok=1; break; fi
  echo "Download interrupted – retrying ($attempt/3)…"; sleep 5
done
[ "${ok:-}" = 1 ] || { echo "Could not download the Python packages. Check your internet connection (or VPN) and run scripts/setup.sh again." >&2; exit 1; }
if [ ! -f frontend/dist/index.html ]; then
  if command -v npm >/dev/null; then (cd frontend && npm ci && npm run build)
  else echo "frontend/dist is missing and Node.js is not installed. Install Node.js 20+ and run setup again." >&2; exit 1; fi
fi
python -c "import uvicorn, fastapi, reportlab, PIL, pypdfium2, scipy" && echo "Setup complete. Start the app with:  scripts/start.sh"
