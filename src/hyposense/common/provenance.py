"""Provenance stamps for every generated artefact (CLAUDE.md §13)."""

from __future__ import annotations

import platform
import subprocess
from datetime import UTC, datetime
from importlib import metadata
from typing import Any

from hyposense import __version__
from hyposense.common.config import REPO_ROOT
from hyposense.common.hashing import sha256_file

KEY_PACKAGES = (
    "numpy",
    "pandas",
    "openpyxl",
    "xlrd",
    "pyyaml",
    "pydantic",
    "scikit-learn",
    "lightgbm",
)


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip()


def git_state() -> dict[str, Any]:
    commit = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain")
    return {"commit": commit, "dirty": bool(status) if status is not None else None}


def package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in KEY_PACKAGES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def environment() -> dict[str, Any]:
    lock = REPO_ROOT / "uv.lock"
    return {
        "hyposense": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": package_versions(),
        "uv_lock_sha256": sha256_file(lock) if lock.exists() else None,
    }


def make_run_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
