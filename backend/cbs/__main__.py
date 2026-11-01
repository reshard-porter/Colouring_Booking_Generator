"""Start the local server:  python -m cbs  (from the backend/ directory)."""
from __future__ import annotations

import argparse
import sys

import uvicorn

from .api import create_app
from .config import Settings


def main():
    ap = argparse.ArgumentParser(description="Coloring Book Studio – local server")
    ap.add_argument("--host", default=None, help="Default 127.0.0.1 (localhost only)")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--data-dir", default=None)
    a = ap.parse_args()
    s = Settings()
    if a.host:
        s.host = a.host
    if a.port:
        s.port = a.port
    if a.data_dir:
        from pathlib import Path
        s.data_dir = Path(a.data_dir).expanduser().resolve()
    if s.host not in ("127.0.0.1", "localhost", "::1"):
        print("Refusing to bind to a non-local address: the local edition has no authentication. "
              "Add authentication and project isolation before exposing it.", file=sys.stderr)
        sys.exit(2)
    print(f"Coloring Book Studio → http://{s.host}:{s.port}   (data: {s.data_dir})")
    uvicorn.run(create_app(s), host=s.host, port=s.port, log_level="info")


if __name__ == "__main__":
    main()
