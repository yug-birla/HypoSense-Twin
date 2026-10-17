"""Deterministic dataset manifest (SHA-256 per file) and verification.

`data/MANIFEST.json` is committed and pins the extracted official copy: path (POSIX, relative to
the extraction root), size and SHA-256 of every file, plus the source archive record. The
manifest's own identity is `files_sha256`, a hash over the sorted file entries only, so it is
independent of retrieval time and the same files always give the same value. The loader refuses
to read data that does not verify (Blueprint §10.1).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hyposense.common.config import REPO_ROOT
from hyposense.common.hashing import sha256_file, sha256_json

MANIFEST_SCHEMA = 1


class ChecksumError(RuntimeError):
    """Raw data on disk does not match the committed manifest."""


@dataclass(frozen=True)
class FileEntry:
    path: str
    size: int
    sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {"path": self.path, "size": self.size, "sha256": self.sha256}


def scan_files(root: Path) -> list[FileEntry]:
    """All regular files under root, sorted by POSIX relative path (deterministic)."""
    if not root.is_dir():
        raise FileNotFoundError(f"data root not found: {root}")
    entries = [
        FileEntry(path=p.relative_to(root).as_posix(), size=p.stat().st_size, sha256=sha256_file(p))
        for p in root.rglob("*")
        if p.is_file()
    ]
    return sorted(entries, key=lambda e: e.path)


def files_hash(entries: list[FileEntry]) -> str:
    return sha256_json([e.as_dict() for e in entries])


def build_manifest(root: Path, archive_record: dict[str, Any] | None) -> dict[str, Any]:
    entries = scan_files(root)
    return {
        "schema": MANIFEST_SCHEMA,
        "root": _rel_to_repo(root),
        "archive": archive_record,
        "n_files": len(entries),
        "files_sha256": files_hash(entries),
        "files": [e.as_dict() for e in entries],
    }


def write_manifest(manifest: dict[str, Any], json_path: Path, sha256sum_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    root = manifest["root"]
    lines = [f"{f['sha256']}  {root}/{f['path']}" for f in manifest["files"]]
    sha256sum_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_manifest(json_path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(json_path.read_text(encoding="utf-8"))
    if data.get("schema") != MANIFEST_SCHEMA:
        raise ChecksumError(f"{json_path}: unsupported manifest schema {data.get('schema')!r}")
    return data


def verify_manifest(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Compare files on disk with the manifest. Raises ChecksumError listing every difference."""
    expected = {f["path"]: f for f in manifest["files"]}
    actual = {e.path: e for e in scan_files(root)}
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(
        p
        for p in set(expected) & set(actual)
        if expected[p]["sha256"] != actual[p].sha256 or expected[p]["size"] != actual[p].size
    )
    recomputed = files_hash([actual[p] for p in sorted(actual)])
    if missing or extra or changed or recomputed != manifest["files_sha256"]:
        raise ChecksumError(
            f"manifest verification failed for {root}: missing={missing} extra={extra} "
            f"changed={changed}"
        )
    return {"verified": True, "n_files": len(actual), "files_sha256": recomputed}


def _rel_to_repo(p: Path) -> str:
    try:
        return p.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return p.resolve().as_posix()
