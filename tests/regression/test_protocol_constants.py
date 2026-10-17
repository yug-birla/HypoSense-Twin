"""Protocol-constant lock.

Class C constants (CLAUDE.md §3) are pinned here against the blueprint. If this test fails,
someone changed the scientific protocol: that needs an approved proposal in docs/PROPOSALS.md
and a docs/DECISION_LOG.md entry, then a deliberate update of this test in the same commit.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str) -> dict[str, Any]:
    with (ROOT / "configs" / name).open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    assert isinstance(data, dict)
    return data


@pytest.fixture(scope="module")
def cfg() -> dict[str, Any]:
    return _load("default.yaml")


def test_event_definition_matches_blueprint_table_5_1(cfg: dict[str, Any]) -> None:
    assert cfg["event"] == {
        "threshold_mgdl": 70,
        "l2_threshold_mgdl": 54,
        "min_run": 2,
        "max_step_min": 20,
        "max_gap_min": 30,
        "horizon_min": 60,
        "min_lead_min": 15,
        "refractory_min": 60,
    }


def test_eligibility_matches_blueprint(cfg: dict[str, Any]) -> None:
    assert cfg["eligibility"] == {
        "history_min": 120,
        "min_readings_in_history": 7,
        "follow_up_min": 60,
    }


def test_population_partition_cv_bootstrap(cfg: dict[str, Any]) -> None:
    assert cfg["population"]["primary"] == "treated"
    assert cfg["population"]["treated_def"] == ["insulin_any", "sulfonylurea", "glinide"]
    assert cfg["partition"]["seed"] == 2026
    assert cfg["partition"]["frac_T"] == 0.30
    assert cfg["cv"] == {"folds": 5, "seed": 2026, "inner_folds": 4}
    assert cfg["bootstrap"]["resamples"] == 2000
    assert cfg["bootstrap"]["seed"] == 2027
    assert cfg["bootstrap"]["unit"] == "patient"


def test_policy_budgets(cfg: dict[str, Any]) -> None:
    pol = cfg["policy"]
    assert pol["fa_budget_alert"] == 1.0
    assert pol["fa_budget_watch"] == 3.0
    assert pol["cooldown_min"] == 60


def test_pharma_not_freezable_while_illustrative() -> None:
    """Records the freeze precondition: no kernel may be ILLUSTRATIVE at freeze.

    Today every kernel is ILLUSTRATIVE, so this asserts the version string says so. When the
    values are sourced, this test must be updated to require status SOURCED + source + reviewer.
    """
    pharma = _load("pharma.yaml")
    statuses = [
        k["status"]
        for group in ("insulin", "secretagogue")
        for k in pharma[group].values()
    ]
    if any(s == "ILLUSTRATIVE" for s in statuses):
        assert "illustrative" in pharma["version"], (
            "pharma.yaml holds ILLUSTRATIVE kernels but its version does not say so"
        )


def test_exponential_kernels_satisfy_shape_constraint() -> None:
    """Eq. 3 needs 1 - 2*t_peak/t_dur > 0."""
    pharma = _load("pharma.yaml")
    for name, k in pharma["insulin"].items():
        if k["family"] == "exponential":
            assert 0 < k["t_peak_min"] < k["t_dur_min"] / 2, name
