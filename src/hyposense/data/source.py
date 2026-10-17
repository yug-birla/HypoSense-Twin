"""Official-source acquisition: pinned figshare download, checksum verification, safe extraction.

The archive is fetched from the version pinned in configs/dataset.yaml. The MD5 published by
figshare is verified, and the SHA-256 is recorded. Only the ShanghaiT2DM members are extracted:
macOS resource forks (``__MACOSX/``), ``.DS_Store`` and the T1DM folder are skipped by an
allow-list. Nothing is ever modified in place.
"""

from __future__ import annotations

import json
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from hyposense.common.config import REPO_ROOT, load_config
from hyposense.common.hashing import file_digests
from hyposense.common.provenance import utc_now_iso


class SourceIntegrityError(RuntimeError):
    """A downloaded or extracted file does not match its pinned checksum or expected layout."""


@dataclass(frozen=True)
class ArchiveSpec:
    version: int
    file_id: int
    file_name: str
    size: int
    md5: str
    sha256: str | None
    doi: str
    url: str


def dataset_config() -> dict[str, Any]:
    return load_config("dataset.yaml")


def archive_spec(version: int | None = None, cfg: dict[str, Any] | None = None) -> ArchiveSpec:
    cfg = cfg or dataset_config()
    v = int(version if version is not None else cfg["canonical_version"])
    entry = cfg["versions"][v]
    return ArchiveSpec(
        version=v,
        file_id=int(entry["file_id"]),
        file_name=str(entry["file_name"]),
        size=int(entry["size"]),
        md5=str(entry["md5"]),
        sha256=entry.get("sha256"),
        doi=str(entry["doi"]),
        url=cfg["download_url_template"].format(file_id=entry["file_id"]),
    )


def archive_path(spec: ArchiveSpec, cfg: dict[str, Any] | None = None) -> Path:
    cfg = cfg or dataset_config()
    return Path(REPO_ROOT / cfg["paths"]["downloads"] / f"diabetes_datasets_v{spec.version}.zip")


def verify_archive(path: Path, spec: ArchiveSpec) -> dict[str, Any]:
    """Check size, figshare MD5 and (if pinned) SHA-256. Raises SourceIntegrityError on mismatch."""
    size = path.stat().st_size
    sha, md5 = file_digests(path)
    problems = []
    if size != spec.size:
        problems.append(f"size {size} != pinned {spec.size}")
    if md5 != spec.md5:
        problems.append(f"md5 {md5} != figshare {spec.md5}")
    if spec.sha256 and sha != spec.sha256:
        problems.append(f"sha256 {sha} != pinned {spec.sha256}")
    if problems:
        raise SourceIntegrityError(f"{path.name}: " + "; ".join(problems))
    return {"size": size, "md5": md5, "sha256": sha}


def fetch_archive(
    version: int | None = None, *, force: bool = False, timeout_s: int = 300
) -> dict[str, Any]:
    """Download (if absent) and verify the pinned archive; write a provenance sidecar JSON."""
    cfg = dataset_config()
    spec = archive_spec(version, cfg)
    dest = archive_path(spec, cfg)
    sidecar = dest.with_suffix(".provenance.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        digests = verify_archive(dest, spec)
        retrieved = (
            json.loads(sidecar.read_text(encoding="utf-8"))["retrieved_utc"]
            if sidecar.exists()
            else None
        )
    else:
        tmp = dest.with_suffix(".part")
        with urllib.request.urlopen(spec.url, timeout=timeout_s) as resp, tmp.open("wb") as out:
            shutil.copyfileobj(resp, out)
        try:
            digests = verify_archive(tmp, spec)
        except SourceIntegrityError:
            tmp.unlink(missing_ok=True)
            raise
        tmp.replace(dest)
        retrieved = utc_now_iso()
    record = {
        "dataset": cfg["dataset"],
        "source": "figshare",
        "collection_doi": cfg["collection"]["doi"],
        "article_id": cfg["article"]["id"],
        "version": spec.version,
        "version_doi": spec.doi,
        "file_id": spec.file_id,
        "url": spec.url,
        "retrieved_utc": retrieved,
        **digests,
        "licence": cfg["licence"],
    }
    sidecar.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def detect_wrapper(names: list[str], cfg: dict[str, Any]) -> str | None:
    """Top-level folder wrapping the dataset (v2-v4 use 'diabetes datasets/'), else None."""
    rec_dir = cfg["extract"]["recordings_dir"]
    tops = {
        PurePosixPath(n).parts[0]
        for n in names
        if len(PurePosixPath(n).parts) >= 3
        and PurePosixPath(n).parts[1] == rec_dir
        and PurePosixPath(n).parts[0] != "__MACOSX"
    }
    if len(tops) > 1:
        raise SourceIntegrityError(f"ambiguous archive layout: {sorted(tops)}")
    return tops.pop() if tops else None


def allowed_member(name: str, cfg: dict[str, Any], wrapper: str | None = None) -> str | None:
    """Return the relative output path for an allowed archive member, else None."""
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts:
        raise SourceIntegrityError(f"unsafe archive member path: {name!r}")
    if not p.parts or p.parts[0] == "__MACOSX" or p.name.startswith(".") or name.endswith("/"):
        return None
    if wrapper is not None:
        if p.parts[0] != wrapper:
            return None
        p = PurePosixPath(*p.parts[1:])
        name = p.as_posix()
    ex = cfg["extract"]
    if len(p.parts) == 2 and p.parts[0] == ex["recordings_dir"] and p.suffix in (".xls", ".xlsx"):
        return name
    if len(p.parts) == 1 and (p.name == ex["summary_file"] or p.name in ex["extra_files"]):
        return name
    return None


def extract_archive(version: int | None = None, *, overwrite: bool = False) -> list[Path]:
    """Extract the allow-listed T2DM members of the verified canonical archive."""
    cfg = dataset_config()
    spec = archive_spec(version, cfg)
    src = archive_path(spec, cfg)
    verify_archive(src, spec)
    out_root = REPO_ROOT / cfg["paths"]["extracted"]
    if out_root.exists() and any(out_root.iterdir()):
        if not overwrite:
            raise SourceIntegrityError(
                f"{out_root} is not empty; refusing to overwrite raw data (use overwrite=True)"
            )
        shutil.rmtree(out_root)
    written: list[Path] = []
    with zipfile.ZipFile(src) as zf:
        wrapper = detect_wrapper(zf.namelist(), cfg)
        for info in sorted(zf.infolist(), key=lambda i: i.filename):
            rel = allowed_member(info.filename, cfg, wrapper)
            if rel is None:
                continue
            target = out_root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as fin, target.open("wb") as fout:
                shutil.copyfileobj(fin, fout)
            written.append(target)
    return written
