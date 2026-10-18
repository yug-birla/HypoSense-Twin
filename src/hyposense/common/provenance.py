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
    """Raw git stdout without trailing newlines. Leading spaces are KEPT because the porcelain
    status columns are significant (S3 fix: stripping them mangled the first path)."""
    try:
        out = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.rstrip("\r\n")


# Generated outputs do not make the source tree dirty; any other change (tracked or untracked) does.
OUTPUT_DIRS = ("experiments/runs/", "artifacts/")


def parse_porcelain(status: str) -> list[str]:
    """Paths from `git status --porcelain` v1 lines (two status columns, a space, the path)."""
    return [ln[3:].strip().strip('"') for ln in status.splitlines() if ln.strip()]


def git_state() -> dict[str, Any]:
    commit = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain", "--untracked-files=all")
    if status is None:
        return {"commit": commit, "dirty": None}
    relevant = [p for p in parse_porcelain(status) if not p.startswith(OUTPUT_DIRS)]
    return {
        "commit": commit.strip() if commit else commit,
        "dirty": bool(relevant),
        "dirty_paths": relevant[:20],
    }


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
