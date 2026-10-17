"""Partition reproduction, integrity lock and immutability tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from hyposense.common.config import REPO_ROOT, load_config
from hyposense.common.hashing import sha256_file
from hyposense.data.partition import (
    PartitionIntegrityError,
    load_partition,
    reproduce_audit2_split,
)

PINNED = "ccdcbce02b049992b0ca09bd99a2a5b8c49bcf49940f3a68ed6ca69cd2449578"


def test_split_is_deterministic_and_stratified() -> None:
    strata = {
        f"{2000 + i}": (0 if i < 9 else 1 if i < 27 else 2 if i < 57 else 3) for i in range(100)
    }
    a = reproduce_audit2_split(strata, 2026, 0.30)
    assert a == reproduce_audit2_split(strata, 2026, 0.30)
    assert a != reproduce_audit2_split(strata, 2027, 0.30)
    per = {s: sum(1 for p, v in a.items() if v == "T" and strata[p] == s) for s in range(4)}
    # int(round(0.3 * n)): 9 -> 3, 18 -> 5 (5.4), 30 -> 9, 43 -> 13 (12.9)
    assert per == {0: 3, 1: 5, 2: 9, 3: 13}


def test_split_uses_bankers_rounding_like_the_original() -> None:
    # 0.3 * 5 = 1.5 -> round() == 2 ; 0.3 * 15 = 4.5 -> round() == 4 (banker's)
    five = reproduce_audit2_split({str(i): 0 for i in range(5)}, 1, 0.30)
    fifteen = reproduce_audit2_split({str(i): 0 for i in range(15)}, 1, 0.30)
    assert sum(v == "T" for v in five.values()) == 2
    assert sum(v == "T" for v in fifteen.values()) == 4


def test_official_partition_is_pinned_and_immutable() -> None:
    cfg = load_config()
    assert cfg["partition"]["sha256"] == PINNED, "pinned partition hash changed (ADR-016)"
    assert sha256_file(REPO_ROOT / "configs" / "partition.csv") == PINNED
    part = load_partition()
    assert len(part) == 100
    assert sum(v == "T" for v in part.values()) == 30
    assert sum(v == "E" for v in part.values()) == 70


def test_partition_file_holds_no_outcome_columns() -> None:
    header = (REPO_ROOT / "configs" / "partition.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header == "patient_id,partition"


def test_tampered_partition_is_refused(tmp_path: Path) -> None:
    src = (REPO_ROOT / "configs" / "partition.csv").read_text(encoding="utf-8")
    p = tmp_path / "partition.csv"
    p.write_text(src.replace("2000,E", "2000,T"), encoding="utf-8")
    with pytest.raises(PartitionIntegrityError):
        load_partition(p, PINNED)


def test_malformed_partition_is_refused(tmp_path: Path) -> None:
    p = tmp_path / "partition.csv"
    p.write_text("patient_id,partition\n2000,X\n", encoding="utf-8")
    with pytest.raises(PartitionIntegrityError):
        load_partition(p, sha256_file(p))
