"""S9 pure rules (ANALYSIS_PLAN §5.1, §5.7, §6) and the E unlock guard. SYNTHETIC inputs only;
no E data is ever read."""

from __future__ import annotations

import math

import numpy as np
import pytest

from hyposense.evaluation.confirm import (
    contrast_reading,
    fa_at_sensitivity,
    h1_supported,
    interpretation_rows,
    select_model,
)


def test_h1_requires_lower_bound_above_zero() -> None:
    assert h1_supported([0.001, 0.2])
    assert not h1_supported([0.0, 0.2])  # strictly > 0
    assert not h1_supported([-0.05, 0.2])


S = {"M1": 0.80, "M2": 0.85, "M3r": 0.86, "M3": 0.88}
LL = {"M1": 0.032, "M2": 0.031, "M3r": 0.031, "M3": 0.030}


def test_selection_h1_supported_deploys_m3() -> None:
    assert select_model(True, S, LL, 0.6)["selected"] == "M3"


def test_selection_point_estimate_and_logloss_rule() -> None:
    assert select_model(False, S, LL, 0.6)["selected"] == "M3"  # higher sens, LL not worse
    worse = {**LL, "M3": 0.0311}
    assert select_model(False, S, worse, 0.6)["selected"] == "M2"  # LL worse -> M2
    equal_ll = {**LL, "M3": LL["M2"]}
    assert select_model(False, S, equal_ll, 0.6)["selected"] == "M3"  # "not worse" = <=
    tie = {**S, "M3": S["M2"]}
    assert select_model(False, tie, LL, 0.6)["selected"] == "M2"  # ties -> simpler
    lower = {**S, "M3": 0.80}
    assert select_model(False, lower, LL, 0.6)["selected"] == "M2"


def test_selection_m0_fallback_only_if_no_learned_model_beats_it() -> None:
    assert select_model(False, S, LL, 0.90)["selected"] == "M0"
    assert select_model(False, S, LL, 0.88)["selected"] == "M0"  # M3 == M0: no model beats it
    assert select_model(False, {**S, "M3": 0.881}, LL, 0.88)["selected"] == "M3"


def test_contrast_reading() -> None:
    assert contrast_reading([0.01, 0.1], 0.05).startswith("first better")
    assert contrast_reading([-0.1, -0.01], -0.05).startswith("second better")
    assert contrast_reading([-0.1, 0.1], 0.02).startswith("≈")


def _c(lo: float, hi: float, point: float) -> dict[str, object]:
    return {"point": point, "ci95": [lo, hi]}


def test_interpretation_rows_are_mechanical() -> None:
    c = {"preview_M3-M2:sens1": _c(0.01, 0.2, 0.1), "C2b_M3-M3r:sens1": _c(-0.1, 0.1, 0.0)}
    assert interpretation_rows(c, True) == ["Δ CI > 0; M3 ≈ M3r"]
    c = {
        "preview_M3-M2:sens1": _c(-0.05, 0.2, 0.05),
        "preview_M3-M2:logloss": _c(-0.002, 0.001, -0.0005),
    }
    assert interpretation_rows(c, True) == ["Δ point estimate > 0, CI includes 0; S3 favours M3"]
    c = {"preview_M3-M2:sens1": _c(-0.1, 0.1, -0.01), "C1_M2-M1:sens1": _c(-0.1, 0.1, 0.0)}
    assert interpretation_rows(c, False) == ["Δ ≈ 0; S3 ≈ 0", "M2 ≈ M1", "Learned models ≤ M0"]


def test_fa_at_sensitivity_interpolates_first_crossing() -> None:
    F = np.array([0.0, 0.5, 1.0, 2.0])
    S = np.array([0.0, 0.4, 0.8, 0.9])
    assert fa_at_sensitivity(F, S, 0.6) == pytest.approx(0.75)
    assert fa_at_sensitivity(F, S, 0.8) == pytest.approx(1.0)
    assert math.isnan(fa_at_sensitivity(F, S, 0.95))


def test_perturbations_are_deterministic_and_bounded() -> None:
    from hyposense.evaluation.confirm_data import drop_cgm, jitter_doses
    from hyposense.medication.events import MedicationEvent
    from hyposense.state.events import CGMReading
    from tests.unit.state_helpers import cgm, med, steady, stream

    st = stream([*cgm(steady(0, 1440)), *med("insulin aspart 8u", "insulin_sc", 300)])
    a, b = jitter_doses(st, 30, 7), jitter_doses(st, 30, 7)
    assert a.events == b.events
    d0 = next(e for e in st.events if isinstance(e, MedicationEvent))
    d1 = next(e for e in a.events if isinstance(e, MedicationEvent))
    assert abs(d1.ts - d0.ts) <= 30 * 60
    n = sum(isinstance(e, CGMReading) for e in st.events)
    for blocks in (False, True):
        r = drop_cgm(st, 0.2, blocks, 3)
        kept = sum(isinstance(e, CGMReading) for e in r.events)
        assert kept <= n - int(np.ceil(0.2 * n))
        assert drop_cgm(st, 0.2, blocks, 3).events == r.events


def test_e_unlock_refuses_anything_but_a_verified_freeze() -> None:
    from hyposense.data.dataset import (
        AccessScope,
        SealedPartitionError,
        load_dataset,
        sealed_unlocked,
        unlock_sealed_partition,
    )
    from hyposense.freeze import FreezeVerificationError, VerifiedFreeze

    with pytest.raises(SealedPartitionError):
        unlock_sealed_partition({"record_sha256": "forged"})
    with pytest.raises(FreezeVerificationError):
        VerifiedFreeze(object(), {"record_sha256": "x"})  # cannot be constructed outside verify
    assert not sealed_unlocked()
    with pytest.raises(SealedPartitionError):
        load_dataset(AccessScope.ALL_AFTER_FREEZE)


def test_official_run_refuses_bootstrap_override() -> None:
    from hyposense.evaluation.confirm import ConfirmRefused, run_confirm

    with pytest.raises(ConfirmRefused):
        run_confirm("official", smoke_resamples=10)
