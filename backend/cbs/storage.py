"""Storage interface + local filesystem implementation (content-addressed, immutable)."""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Protocol


class Storage(Protocol):
    def put(self, data: bytes, ext: str) -> tuple[str, str]: ...
    def read(self, key: str) -> bytes: ...
    def path(self, key: str) -> Path: ...
    def exists(self, key: str) -> bool: ...


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class LocalFileStorage:
    """Files are stored by SHA-256, so stored objects are immutable and de-duplicated.
    Keys are relative paths (never absolute) so projects stay portable."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, data: bytes, ext: str) -> tuple[str, str]:
        digest = sha256_bytes(data)
        ext = ext.lower().lstrip(".")
        if not ext.isalnum() or len(ext) > 5:
            raise ValueError("bad extension")
        key = f"{digest[:2]}/{digest}.{ext}"
        dest = self.root / key
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=dest.parent)
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, dest)
        return key, digest

    def path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError("invalid storage key")
        return p

    def read(self, key: str) -> bytes:
        return self.path(key).read_bytes()

    def exists(self, key: str) -> bool:
        try:
            return self.path(key).is_file()
        except ValueError:
            return False
