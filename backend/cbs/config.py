"""Runtime configuration. Everything is local-first; nothing here requires a network."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
FONT_DIR = PACKAGE_DIR / "assets" / "fonts"
PROFILE_DIR = PACKAGE_DIR / "profiles"
APP_VERSION = "0.5.1"


def default_data_dir() -> Path:
    env = os.environ.get("CBS_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return (base / "coloring-book-studio").resolve()


@dataclass
class Settings:
    data_dir: Path = field(default_factory=default_data_dir)
    host: str = field(default_factory=lambda: os.environ.get("CBS_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.environ.get("CBS_PORT", "8765")))
    # Upload safety limits
    max_upload_bytes: int = 40 * 1024 * 1024
    max_image_pixels: int = 60_000_000  # ~7700 x 7700; protects against decompression bombs
    max_image_side: int = 12000
    start_worker: bool = True

    @property
    def db_path(self) -> Path:
        return self.data_dir / "studio.sqlite3"

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def secrets_path(self) -> Path:
        return self.data_dir / "secrets.json"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.files_dir, self.exports_dir, self.backups_dir):
            d.mkdir(parents=True, exist_ok=True)
