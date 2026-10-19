"""Freeze tooling fails closed (IMPLEMENTATION_PLAN FREEZE; DEC-2026-10-19-M). SYNTHETIC inputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hyposense import freeze as F
from hyposense.data.dataset import AccessScope, SealedPartitionError, load_dataset


def test_plan_must_be_final() -> None:
    final = (
        "## 5. Primary analysis\nStatus: **FINAL x**\n"
        "## 6. Interpretation matrix\nStatus: **FINAL y**\n"
    )
    assert F.plan_is_final(final)[0]
    assert not F.plan_is_final(final.replace("**FINAL x**", "**DRAFT (S5)**"))[0]
    assert not F.plan_is_final("## 5. Primary analysis\nStatus: **FINAL**\n")[0]  # §6 missing


def test_awaiting_class_c_is_detected() -> None:
    text = "### P-C7 · x\n**Status: AWAITING APPROVAL**\n### P-B1 · y\n**Status: AWAITING**\n"
    assert F.open_class_c(text) == ["P-C7"]  # Class B awaiting does not block
    assert F.open_class_c("### P-C7 · x\n**Status: APPROVED 2026**\n") == []


def test_pharmacist_review_is_mandatory_unless_reviewed_or_waived() -> None:
    assert not F.pharmacist_status({"reviewed_by": None})[0]
    assert F.pharmacist_status({"reviewed_by": "Dr X, PharmD, 2026-11-01"})[0]
    assert F.pharmacist_status({"reviewed_by": None, "pharmacist_waiver": "owner, reason"})[0]


def test_e_runs_are_detected(tmp_path: Path) -> None:
    (tmp_path / "T-AGG-x").mkdir()
    (tmp_path / "T-AGG-x" / "results.json").write_text(json.dumps({"results": {"partition": "T"}}))
    assert F.e_partition_runs(tmp_path) == []
    (tmp_path / "E-AGG-y").mkdir()
    (tmp_path / "E-AGG-y" / "results.json").write_text(json.dumps({"results": {"partition": "E"}}))
    assert F.e_partition_runs(tmp_path) == ["E-AGG-y"]


def test_any_failed_invariant_aborts_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake(run_tests: bool = True) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        return [
            {"check": "clean_working_tree", "status": "PASS", "detail": ""},
            {"check": "pharmacist_review", "status": "ERROR", "detail": "PENDING"},
        ], {}

    monkeypatch.setattr(F, "evaluate", fake)
    monkeypatch.setattr(F, "FREEZE_JSON", tmp_path / "FREEZE.json")
    rep = F.freeze(write=True)
    assert rep["result"] == "ERROR — FREEZE ABORTED" and rep["errors"] == 1
    assert not (tmp_path / "FREEZE.json").exists()


def test_confirmatory_access_still_refused_before_s9() -> None:
    with pytest.raises(SealedPartitionError):
        load_dataset(AccessScope.ALL_AFTER_FREEZE)
