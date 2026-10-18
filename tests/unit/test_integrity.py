"""Hashing, time conversion, manifest, archive allow-list and quality-flag tests (SYNTHETIC)."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np
import pytest

from hyposense.common.hashing import canonical_json, file_digests, sha256_json
from hyposense.common.timeconv import local_naive_to_epoch_s, parse_utc_offset
from hyposense.data.manifest import (
    ChecksumError,
    build_manifest,
    read_manifest,
    verify_manifest,
    write_manifest,
)
from hyposense.data.quality import QualityThresholds, cgm_quality_flags
from hyposense.data.records import CGMSeries
from hyposense.data.source import (
    ArchiveSpec,
    SourceIntegrityError,
    allowed_member,
    dataset_config,
    detect_wrapper,
    verify_archive,
)

# ---------- hashing ----------


def test_file_digests_match_hashlib(tmp_path: Path) -> None:
    p = tmp_path / "f.bin"
    data = bytes(range(256)) * 9000
    p.write_bytes(data)
    assert file_digests(p) == (hashlib.sha256(data).hexdigest(), hashlib.md5(data).hexdigest())


def test_canonical_json_is_order_independent_and_nan_safe() -> None:
    assert canonical_json({"b": 1, "a": [1.5, math.nan]}) == canonical_json(
        {"a": [1.5, math.nan], "b": 1}
    )
    assert sha256_json({"x": 1}) != sha256_json({"x": 2})
    assert "NaN" in canonical_json({"v": math.nan})


# ---------- time ----------


def test_utc_offset_parsing() -> None:
    assert parse_utc_offset("+08:00") == 28800
    assert parse_utc_offset("-05:30") == -19800
    for bad in ("+8", "UTC+8", "08:00", "+08"):
        with pytest.raises(ValueError):
            parse_utc_offset(bad)


def test_local_to_epoch_exact() -> None:
    local = np.array(["1970-01-01T08:00:00", "2020-11-02T09:40:00"], dtype="datetime64[us]")
    out = local_naive_to_epoch_s(local, 28800)
    assert out.tolist() == [0, 1604281200]


# ---------- manifest ----------


def _tree(root: Path) -> None:
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "b.xls").write_bytes(b"bbb")
    (root / "a.xlsx").write_bytes(b"aaa")


def test_manifest_roundtrip_and_determinism(tmp_path: Path) -> None:
    root = tmp_path / "data"
    _tree(root)
    m1 = build_manifest(root, {"version": 5})
    m2 = build_manifest(root, {"version": 5, "retrieved_utc": "different"})
    assert m1["files_sha256"] == m2["files_sha256"]  # independent of retrieval metadata
    assert [f["path"] for f in m1["files"]] == ["a.xlsx", "sub/b.xls"]
    j, s = tmp_path / "M.json", tmp_path / "M.sha256"
    write_manifest(m1, j, s)
    assert verify_manifest(root, read_manifest(j))["verified"]
    assert (
        s.read_text(encoding="utf-8")
        .splitlines()[0]
        .startswith(hashlib.sha256(b"aaa").hexdigest() + "  ")
    )


@pytest.mark.parametrize("tamper", ["modify", "add", "remove"])
def test_manifest_detects_tampering(tmp_path: Path, tamper: str) -> None:
    root = tmp_path / "data"
    _tree(root)
    m = build_manifest(root, None)
    if tamper == "modify":
        (root / "a.xlsx").write_bytes(b"aab")
    elif tamper == "add":
        (root / "extra.xls").write_bytes(b"x")
    else:
        (root / "sub" / "b.xls").unlink()
    with pytest.raises(ChecksumError):
        verify_manifest(root, m)


# ---------- archive allow-list ----------


def test_allowed_member_filters_archive() -> None:
    cfg = dataset_config()
    assert allowed_member("Shanghai_T2DM/2001_0_20201102.xlsx", cfg) is not None
    assert allowed_member("Shanghai_T2DM_Summary.xlsx", cfg) is not None
    assert allowed_member("note.txt", cfg) is not None
    for skip in (
        "__MACOSX/Shanghai_T2DM/._2001_0_20201102.xlsx",
        "Shanghai_T1DM/1001_0.xlsx",
        "Shanghai_T2DM/.DS_Store",
        "data_analysis.ipynb",
        "Shanghai_T2DM/",
    ):
        assert allowed_member(skip, cfg) is None
    for unsafe in ("../evil.xlsx", "/abs/Shanghai_T2DM/x.xlsx"):
        with pytest.raises(SourceIntegrityError):
            allowed_member(unsafe, cfg)


def test_wrapper_folder_detection() -> None:
    cfg = dataset_config()
    names = [
        "diabetes datasets/Shanghai_T2DM/2001_0_20201102.xlsx",
        "diabetes datasets/Shanghai_T2DM_Summary.xlsx",
        "__MACOSX/diabetes datasets/x",
    ]
    w = detect_wrapper(names, cfg)
    assert w == "diabetes datasets"
    assert allowed_member(names[0], cfg, w) == "Shanghai_T2DM/2001_0_20201102.xlsx"
    assert detect_wrapper(["Shanghai_T2DM/2001_0_20201102.xlsx"], cfg) is None


def test_verify_archive_rejects_mismatch(tmp_path: Path) -> None:
    p = tmp_path / "a.zip"
    p.write_bytes(b"content")
    good = ArchiveSpec(
        5,
        1,
        "a.zip",
        7,
        hashlib.md5(b"content").hexdigest(),
        hashlib.sha256(b"content").hexdigest(),
        "doi",
        "url",
    )
    assert verify_archive(p, good)["size"] == 7
    bad = ArchiveSpec(5, 1, "a.zip", 7, "0" * 32, None, "doi", "url")
    with pytest.raises(SourceIntegrityError):
        verify_archive(p, bad)


# ---------- quality flags ----------


def test_cgm_quality_flags() -> None:
    # intervals (min): 15, 15, 25, 15, 15, 100
    ts = np.array([0, 900, 1800, 3300, 4200, 5100, 11100], dtype=np.int64)
    g = np.array([100.0, 99.0, 40.0, 120.0, 180.0, 245.0, 246.0])
    s = CGMSeries("k", ts, g, np.arange(7, dtype=np.int64), {})
    f = cgm_quality_flags(s, QualityThresholds())
    assert f.gap_before.tolist() == [False, False, False, True, False, False, True]
    assert f.floor.tolist() == [False, False, True, False, False, False, False]
    # 120->180 in 15 min = 4.0 mg/dL/min is NOT > 4; 180->245 = 4.33 is
    assert f.rapid_change.tolist() == [False, False, False, False, False, True, False]
    assert f.warmup.tolist() == [True, True, True, True, True, True, False]


# ---------- provenance ----------


def test_git_dirty_ignores_generated_outputs_only(monkeypatch: pytest.MonkeyPatch) -> None:
    from hyposense.common import provenance

    def fake(status: str):  # type: ignore[no-untyped-def]
        return lambda *a: "abc123" if a[0] == "rev-parse" else status

    monkeypatch.setattr(
        provenance, "_git", fake("?? experiments/runs/X/a.json\n?? artifacts/gates/G0.json")
    )
    assert provenance.git_state()["dirty"] is False
    monkeypatch.setattr(
        provenance, "_git", fake("?? experiments/runs/X/a.json\n?? src/hyposense/new.py")
    )
    assert provenance.git_state()["dirty"] is True
    monkeypatch.setattr(provenance, "_git", fake(" M configs/default.yaml"))
    assert provenance.git_state()["dirty"] is True
    monkeypatch.setattr(provenance, "_git", fake(""))
    assert provenance.git_state()["dirty"] is False


def test_sensor_fault_suspected_is_causal_and_needs_8_readings() -> None:
    from hyposense.data.quality import sensor_fault_suspected

    ts = np.arange(0, 12 * 900, 900, dtype=np.int64)
    g = np.array([100, 39.6, 39.6, 39.6, 39.6, 39.6, 39.6, 39.6, 39.6, 39.6, 120, 39.6])
    flags = sensor_fault_suspected(
        CGMSeries("k", ts, g, np.arange(12, dtype=np.int64), {}), QualityThresholds()
    )
    # run starts at index 1; the 8th consecutive floor reading is index 8
    assert flags.tolist() == [False] * 8 + [True, True, False, False]
    # causal: the flag at k is unchanged when the series is truncated at k
    for k in range(1, 12):
        sub = CGMSeries("k", ts[: k + 1], g[: k + 1], np.arange(k + 1, dtype=np.int64), {})
        assert sensor_fault_suspected(sub, QualityThresholds())[-1] == flags[k]


def test_porcelain_parsing_keeps_first_path_intact(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression (S3): a leading-space status line used to lose its first path character."""
    from hyposense.common import provenance

    assert provenance.parse_porcelain(" M artifacts/gates/G2.json\n?? src/x.py") == [
        "artifacts/gates/G2.json",
        "src/x.py",
    ]
    monkeypatch.setattr(
        provenance,
        "_git",
        lambda *a: "abc" if a[0] == "rev-parse" else " M artifacts/gates/G2.json",
    )
    assert provenance.git_state()["dirty"] is False
