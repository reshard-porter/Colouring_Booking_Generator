#!/usr/bin/env bash
# Start Coloring Book Studio on http://127.0.0.1:8765 (this computer only). Stop with Ctrl+C.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a
if [ -d .venv ]; then . .venv/bin/activate; fi
if ! python -c "import uvicorn, fastapi" 2>/dev/null; then
  echo "The app's Python packages aren't installed yet. Run:  scripts/setup.sh" >&2
  exit 1
fi
if [ ! -f frontend/dist/index.html ]; then
  echo "The user interface hasn't been built. Run:  scripts/setup.sh" >&2
  exit 1
fi
cd backend && exec python -m cbs "$@"
