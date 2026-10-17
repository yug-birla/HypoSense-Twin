"""Deterministic hashing helpers (files, bytes, canonical JSON)."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

_CHUNK = 1 << 20


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digests(path: Path) -> tuple[str, str]:
    """Return (sha256, md5) of a file, streamed.

    MD5 is computed only to match the checksum figshare publishes.
    """
    sha, md5 = hashlib.sha256(), hashlib.md5(usedforsecurity=False)
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            sha.update(chunk)
            md5.update(chunk)
    return sha.hexdigest(), md5.hexdigest()


def sha256_file(path: Path) -> str:
    return file_digests(path)[0]


def _normalise(obj: Any) -> Any:
    """Make an object canonically JSON-serialisable (NaN/inf are not valid JSON)."""
    if isinstance(obj, float):
        if math.isnan(obj):
            return "NaN"
        if math.isinf(obj):
            return "Infinity" if obj > 0 else "-Infinity"
        return obj
    if isinstance(obj, dict):
        return {str(k): _normalise(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_normalise(v) for v in obj]
    return obj


def canonical_json(obj: Any) -> str:
    """Key-sorted, compact, ASCII-safe JSON: identical objects give identical strings."""
    return json.dumps(_normalise(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(obj: Any) -> str:
    return sha256_bytes(canonical_json(obj).encode("utf-8"))
