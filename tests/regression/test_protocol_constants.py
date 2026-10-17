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
        "min_time_since_start_min": 120,  # executable spec = policy warm-up (ANALYSIS_PLAN §0)
        "warmup_restart_after_gap_min": None,  # P-C7 PENDING; must stay None until approved
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


def test_gate_criteria_match_blueprint_table_21_1(cfg: dict[str, Any]) -> None:
    assert cfg["gates"]["g0"] == {
        "expected_recording_files": 109,
        "expected_patients": 100,
        "published_cgm_readings": 112475,
    }
    assert cfg["gates"]["g2"] == {
        "min_episodes": 100,
        "min_patients_with_episode": 20,
        "max_ci_half_width": 0.15,
        "icc_ref": 0.15,
        "p_ref": 0.65,
        "icc_grid": [0.05, 0.15, 0.30],
    }
    assert cfg["gates"]["g3b"] == {
        "max_unconfirmed_share": 0.50,
        "pair_window_min": 8,
        "episode_cbg_tail_min": 15,
    }
    assert cfg["gates"]["g1"] == {
        "min_cgm_parse_rate": 0.99,
        "min_interval_le_rate": 0.99,
        "max_interval_min": 20,
    }


def test_partition_is_pinned(cfg: dict[str, Any]) -> None:
    """ADR-016: the official split is immutable. Changing this pin requires an approved
    Class C decision; never regenerate the partition because results are inconvenient."""
    assert cfg["partition"]["sha256"] == (
        "ccdcbce02b049992b0ca09bd99a2a5b8c49bcf49940f3a68ed6ca69cd2449578"
    )
    assert cfg["partition"]["version"] == "1.0.0"


def test_canonical_dataset_version_is_pinned() -> None:
    ds = _load("dataset.yaml")
    assert ds["canonical_version"] == 5
    v5 = ds["versions"][5]
    assert v5["md5"] == "4bfb61cfa506b48155fd9e841ee48e21"
    assert v5["sha256"] == "59b5f5c4053a32bb6b7827844a0191597dc82228fe88ce332a189fdfc659c4cb"
    assert all(isinstance(k, str) for k in ds["version_notes"][5]["changed_recordings"])


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
        k["status"] for group in ("insulin", "secretagogue") for k in pharma[group].values()
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
