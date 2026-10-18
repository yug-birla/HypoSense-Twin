"""Evaluation harness tests (S5): hand-computable SYNTHETIC fixtures for ANALYSIS_PLAN §2-4.

Every expected value below was derived by hand from the written rules. Times are minutes."""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from hyposense.evaluation.bootstrap import (
    draw_weights,
    paired_bootstrap,
    sens_at_budget_stat,
)
from hyposense.evaluation.data import EvalRecording
from hyposense.evaluation.metrics import (
    FALSE,
    TRUE,
    UNKNOWN,
    EventRules,
    calibration,
    classify_notifications,
    curve,
    notification_indices,
    operating_point,
    partial_area,
    patient_curves,
    select_threshold,
    sens_at_budget,
    window_metrics,
)

R = EventRules()
M = 60


def rec(
    minutes: list[float],
    scores: list[float],
    onsets: list[float] = (),  # type: ignore[assignment]
    *,
    eligible: list[bool] | None = None,
    queried: list[bool] | None = None,
    patient: str = "p1",
    key: str = "p1_0",
    last: float | None = None,
) -> EvalRecording:
    ts = np.array([int(m * M) for m in minutes], dtype=np.int64)
    n = len(ts)
    gate = np.where(np.array(queried if queried is not None else [True] * n), 0, 2).astype(np.int8)
    on = np.array([int(o * M) for o in onsets], dtype=np.int64)
    return EvalRecording(
        patient_key=patient,
        recording_key=key,
        ts=ts,
        gate_code=gate,
        eligible=np.array(eligible if eligible is not None else [True] * n),
        onsets=on,
        warnable=np.ones(len(on), dtype=bool),
        first_ts=int(ts[0]),
        last_ts=int(last * M) if last is not None else int(ts[-1]),
        scores={"m": np.array(scores, dtype=np.float64)},
    )


def op(r: EvalRecording | list[EvalRecording], tau: float, strict: bool = False):  # type: ignore[no-untyped-def]
    return operating_point(r if isinstance(r, list) else [r], "m", tau, strict, R)


# ---------------------------------------------------------------- episode hits
@pytest.mark.parametrize(
    ("alert_at", "hit", "lead"),
    [(40, True, 60.0), (85, True, 15.0), (25, False, None), (90, False, None)],
)
def test_episode_hit_window_is_closed_minus60_to_minus15(alert_at, hit, lead) -> None:  # type: ignore[no-untyped-def]
    # onset at 100: window [40, 85]; one alerting reading at `alert_at`; others below threshold
    minutes = sorted({0, 25, 40, 85, 90, 200})
    scores = [0.9 if m == alert_at else 0.1 for m in minutes]
    out = op(rec(minutes, scores, [100]), 0.5)
    assert out["hits"] == int(hit)
    if hit:
        assert out["lead_min"]["median"] == lead


def test_multiple_alerts_in_window_one_hit_earliest_lead() -> None:
    out = op(rec([0, 45, 60, 75, 200], [0.1, 0.9, 0.9, 0.9, 0.1], [100]), 0.5)
    assert out["hits"] == 1 and out["lead_min"]["median"] == 55.0


def test_hit_needs_a_label_eligible_queried_reading() -> None:
    r = rec([0, 50, 200], [0.1, 0.9, 0.1], [100], eligible=[True, False, True])
    assert op(r, 0.5)["hits"] == 0
    r = rec([0, 50, 200], [0.1, 0.9, 0.1], [100], queried=[True, False, True])
    assert op(r, 0.5)["hits"] == 0


# ---------------------------------------------------------------- notification outcomes
def test_notification_outcome_classes() -> None:
    t = np.array([0, 100 * M, 200 * M], dtype=np.int64)
    onsets = np.array([60 * M, 100 * M], dtype=np.int64)
    # t=0: onset exactly at +60 -> TRUE; t=100: onset at t itself is not in (t, t+60] -> FALSE
    # (last reading 260 >= 160); t=200: last reading 250 < 260 -> UNKNOWN
    c = classify_notifications(t, onsets, 250 * M, 3600)
    assert c.tolist() == [TRUE, FALSE, UNKNOWN]
    assert classify_notifications(np.array([200 * M]), onsets, 260 * M, 3600).tolist() == [FALSE]


def test_unknown_outcomes_are_never_counted_as_true_or_false() -> None:
    r = rec([0, 15, 30], [0.9, 0.1, 0.1])  # notification at 0, record ends at 30 < 60
    out = op(r, 0.5)
    assert out["notifications"] == {"true": 0, "false": 0, "outcome_unknown": 1}
    assert math.isnan(out["alert_precision"]) and out["fa_per_day"] == 0.0


# ---------------------------------------------------------------- cooldown
def test_cooldown_greedy_with_exact_60_minute_boundary() -> None:
    ts = np.array([m * M for m in (0, 15, 30, 45, 60, 75, 120)], dtype=np.int64)
    alert = np.ones(len(ts), dtype=bool)
    assert (ts[notification_indices(ts, alert, 3600)] // M).tolist() == [0, 60, 120]
    ts2 = np.array([0, 59 * M], dtype=np.int64)
    assert len(notification_indices(ts2, np.ones(2, bool), 3600)) == 1


def test_two_nearby_episodes_and_repeated_alerts() -> None:
    # alerts continuously from 0 to 150 every 15 min; onsets at 70 and 140
    minutes = [*range(0, 151, 15), 400]
    r = rec(minutes, [0.9] * 11 + [0.1], [70, 140])
    out = op(r, 0.5)
    # notifications at 0 (TRUE: 70 in (0,60]? no -> FALSE), 60 (TRUE: 70), 120 (TRUE: 140)
    assert out["notifications"] == {"true": 2, "false": 1, "outcome_unknown": 0}
    assert out["hits"] == 2


# ---------------------------------------------------------------- patient-days
def test_monitored_days_sum_over_recordings_of_unequal_length() -> None:
    a = rec([0, 1440], [0.1, 0.1], key="p1_0")
    b = rec([0, 720], [0.1, 0.1], key="p1_1")
    c = rec([0, 2880], [0.1, 0.1], patient="p2", key="p2_0")
    out = op([a, b, c], 0.5)
    assert out["monitored_days"] == pytest.approx(1 + 0.5 + 2)
    pc = patient_curves([a, b, c], "m", False, R)
    assert pc.days.tolist() == [1.5, 2.0]


# ---------------------------------------------------------------- operating curve
def test_curve_ties_switch_together_and_sentinel_first() -> None:
    r = rec([0, 100, 300], [0.7, 0.7, 0.2], last=500)
    pc = patient_curves([r], "m", False, R)
    assert pc.tau[0] == math.inf and pc.tau[1:].tolist() == [0.7, 0.2]
    c = curve(pc)
    days = 500 / 1440
    assert c.fa_per_day.tolist() == pytest.approx([0, 2 / days, 3 / days])


def test_fa_can_decrease_as_threshold_lowers_cooldown() -> None:
    # onset at 10; base alert at 30 is FALSE; lowering tau adds an alert at 0 that is TRUE and
    # suppresses the FALSE one (cooldown) -> FA/day decreases
    r = rec([0, 30, 300], [0.5, 0.9, 0.1], [10], last=300)
    c = curve(patient_curves([r], "m", False, R))
    assert c.fa_per_day[1] > 0 and c.fa_per_day[2] == 0
    assert c.non_monotone_steps == 1


def test_curve_equals_direct_recomputation_no_alerts_and_all_alerts() -> None:
    r = rec([0, 15, 30, 45, 200, 400], [0.1, 0.4, 0.8, 0.3, 0.6, 0.2], [60, 230])
    pc = patient_curves([r], "m", False, R)
    c = curve(pc)
    assert c.fa_per_day[0] == 0 and c.sensitivity[0] == 0  # sentinel: no alerts
    for k, tau in enumerate(pc.tau[1:], start=1):
        o = op(r, float(tau))
        assert c.fa_per_day[k] == pytest.approx(o["fa_per_day"])
        assert c.sensitivity[k] == pytest.approx(o["sensitivity"])


@st.composite
def random_recordings(draw):  # type: ignore[no-untyped-def]
    recs = []
    for p in range(draw(st.integers(1, 3))):
        n = draw(st.integers(2, 25))
        steps = draw(st.lists(st.sampled_from([5, 15, 15, 30, 61]), min_size=n - 1, max_size=n - 1))
        minutes = np.cumsum([0, *steps]).tolist()
        scores = draw(
            st.lists(
                st.sampled_from([0.1, 0.2, 0.5, 0.5, 0.8, float("nan")]), min_size=n, max_size=n
            )
        )
        onsets = sorted(set(draw(st.lists(st.integers(0, int(minutes[-1]) + 30), max_size=3))))
        q = draw(st.lists(st.booleans(), min_size=n, max_size=n))
        e = draw(st.lists(st.booleans(), min_size=n, max_size=n))
        recs.append(
            rec(minutes, scores, onsets, eligible=e, queried=q, patient=f"p{p}", key=f"p{p}_0")
        )
    return recs


@settings(max_examples=150, deadline=None)
@given(random_recordings(), st.booleans())
def test_step_function_curve_equals_direct_policy_replay(recs, strict) -> None:  # type: ignore[no-untyped-def]
    pc = patient_curves(recs, "m", strict, R)
    c = curve(pc)
    for k, tau in enumerate(pc.tau):
        o = operating_point(recs, "m", float(tau), strict, R)
        assert c.fa_per_day[k] == pytest.approx(o["fa_per_day"])
        if c.n_episodes:
            assert c.sensitivity[k] == pytest.approx(o["sensitivity"])


# ---------------------------------------------------------------- first-crossing sens@B (§3.4, §4)
def _arr(*v: float) -> np.ndarray:
    return np.array(v, dtype=np.float64)


def test_sens_at_budget_interpolates_at_first_crossing() -> None:
    b = sens_at_budget(_arr(0, 0.5, 1.5), _arr(0, 0.4, 0.8), _arr(np.inf, 0.9, 0.5), 1.0)
    assert b.value == pytest.approx(0.6) and b.a == 1 and b.k_star == 2 and b.tau_a == 0.9


def test_sens_at_budget_exact_hit_at_fa_equals_budget() -> None:
    b = sens_at_budget(_arr(0, 1.0, 1.5), _arr(0, 0.5, 0.9), _arr(np.inf, 0.9, 0.5), 1.0)
    assert b.value == 0.5 and b.f_a == 1.0


def test_sens_at_budget_k_star_is_1_interpolates_from_sentinel() -> None:
    b = sens_at_budget(_arr(0, 1.5), _arr(0, 0.6), _arr(np.inf, 0.9), 1.0)
    assert b.value == pytest.approx(0.4) and b.k_star_is_1 and b.tau_a == math.inf


def test_sens_at_budget_not_reached_uses_most_lenient_point() -> None:
    b = sens_at_budget(_arr(0, 0.2, 0.5), _arr(0, 0.3, 0.5), _arr(np.inf, 0.9, 0.5), 1.0)
    assert b.value == 0.5 and b.budget_not_reached and b.tau_a == 0.5


def test_sens_at_budget_ignores_later_dips_below_budget() -> None:
    F, S = _arr(0, 0.8, 1.2, 0.9, 1.1), _arr(0, 0.5, 0.6, 0.7, 0.8)
    b = sens_at_budget(F, S, _arr(np.inf, 5, 4, 3, 2), 1.0)
    assert b.value == pytest.approx(0.5 + 0.2 * 0.1 / 0.4) and b.a == 1


def test_threshold_selection_tau_a_and_tau_w() -> None:
    r = rec([0, 100, 200, 300, 2000], [0.9, 0.8, 0.7, 0.6, 0.1], last=2000)
    c = curve(patient_curves([r], "m", False, R))
    days = 2000 / 1440
    # F at the grid: 0, 0.72, 1.44, ... (each extra alert adds one FALSE notification)
    ta = select_threshold(c, 1.0, "fa")
    assert ta.tau_a == 0.9 and ta.f_a == pytest.approx(1 / days)
    tw = select_threshold(c, 3.0, "notifications")
    assert tw.tau_a == pytest.approx(0.6)  # 4 notifications / 1.39 d = 2.88 <= 3


# ---------------------------------------------------------------- partial area (§3.7)
def test_partial_area_monotone_curve_by_hand() -> None:
    area, reached = partial_area(_arr(0, 1, 3), _arr(0, 0.5, 1))
    assert reached and area == pytest.approx((0.1875 + 0.625) / 1.5)


def test_partial_area_boundaries_no_internal_point_duplicates_degenerate() -> None:
    assert partial_area(_arr(0, 3), _arr(0, 0.9))[0] == pytest.approx(0.5625 / 1.5)
    assert partial_area(_arr(0, 0.5, 2.0), _arr(0, 0.2, 0.8))[0] == pytest.approx(0.75 / 1.5)
    assert partial_area(_arr(0, 1, 1, 3), _arr(0, 0.5, 0.6, 1))[0] == pytest.approx(
        (0.1875 + 0.7) / 1.5
    )
    assert partial_area(_arr(0, 0), _arr(0, 0)) == (0.0, False)


# ---------------------------------------------------------------- bootstrap (§5.12-5.15)
def test_bootstrap_draws_are_deterministic_and_keep_multiplicity() -> None:
    w1 = draw_weights(5, 50, 2027)
    assert np.array_equal(w1, draw_weights(5, 50, 2027))
    assert (w1.sum(axis=1) == 5).all() and (w1 > 1).any()  # duplicates kept


def test_weighted_curve_equals_curve_with_duplicated_patient() -> None:
    a = rec([0, 30, 300], [0.9, 0.5, 0.2], [60], patient="A", key="A_0")
    b = rec([0, 100, 600], [0.4, 0.8, 0.1], [], patient="B", key="B_0")
    a2 = rec([0, 30, 300], [0.9, 0.5, 0.2], [60], patient="A2", key="A2_0")
    w = curve(patient_curves([a, b], "m", False, R), np.array([2.0, 1.0]))
    d = curve(patient_curves([a, a2, b], "m", False, R))
    assert np.allclose(w.fa_per_day, d.fa_per_day) and np.allclose(w.sensitivity, d.sensitivity)


def test_one_patient_bootstrap_is_degenerate() -> None:
    pc = patient_curves([rec([0, 30, 300], [0.9, 0.5, 0.2], [60])], "m", False, R)
    res = paired_bootstrap({"s": sens_at_budget_stat(pc, 1.0)}, 1, 200, 2027)
    assert res.ci95["s"][0] == res.ci95["s"][1] == res.point["s"]


def test_paired_difference_uses_the_same_draws() -> None:
    vals = np.array([0.2, 0.5, 0.9, 0.4])
    res = paired_bootstrap(
        {
            "A": lambda w: float(w @ vals / w.sum()),
            "B": lambda w: float(w @ (vals - 0.1) / w.sum()),
        },
        4,
        500,
        2027,
        differences={"A-B": ("A", "B")},
    )
    assert np.allclose(res.draws["A-B"], 0.1)  # identical draws -> constant difference
    assert res.ci95["A-B"][0] == pytest.approx(0.1) and res.ci95["A-B"][1] == pytest.approx(0.1)


def test_bootstrap_percentile_interval_on_a_known_case() -> None:
    rng = np.random.default_rng(0)
    vals = rng.normal(0.5, 0.1, 200)
    res = paired_bootstrap({"mean": lambda w: float(w @ vals / w.sum())}, 200, 2000, 2027)
    se = vals.std(ddof=1) / np.sqrt(200)
    lo, hi = res.ci95["mean"]
    assert lo == pytest.approx(vals.mean() - 1.96 * se, abs=0.004)
    assert hi == pytest.approx(vals.mean() + 1.96 * se, abs=0.004)


def test_resamples_without_episodes_are_counted_not_dropped() -> None:
    a = rec([0, 30, 300], [0.9, 0.5, 0.2], [60], patient="A", key="A_0")
    b = rec([0, 100, 600], [0.4, 0.8, 0.1], [], patient="B", key="B_0")
    pc = patient_curves([a, b], "m", False, R)
    res = paired_bootstrap({"s": sens_at_budget_stat(pc, 1.0)}, 2, 400, 2027)
    assert res.undefined_resamples["s"] > 0  # draws of only B have no episodes


# ---------------------------------------------------------------- window-level and calibration
def test_window_metrics_by_hand_and_probability_guard() -> None:
    y = np.array([0, 1, 1, 0])
    p = np.array([0.1, 0.8, 0.6, 0.3])
    m = window_metrics(y, p)
    ll = -(np.log(0.9) + np.log(0.8) + np.log(0.6) + np.log(0.7)) / 4
    assert m["log_loss"] == pytest.approx(ll)
    assert m["brier"] == pytest.approx((0.01 + 0.04 + 0.16 + 0.09) / 4)
    assert m["auprc"] == pytest.approx(1.0)
    with pytest.raises(ValueError):
        window_metrics(y, np.array([-1.0, 0.5, 0.5, 2.0]))  # an M0 score is not a probability


def test_calibration_of_a_perfectly_calibrated_model() -> None:
    rng = np.random.default_rng(1)
    p = rng.uniform(0.01, 0.99, 20000)
    y = (rng.uniform(size=20000) < p).astype(int)
    c = calibration(y, p)
    assert c["ece"] < 0.02 and c["slope"] == pytest.approx(1.0, abs=0.1)
    assert c["intercept"] == pytest.approx(0.0, abs=0.1) and len(c["reliability"]) == 10


def test_committed_metric_registry_matches_code() -> None:
    import json

    from hyposense.common.config import REPO_ROOT
    from hyposense.evaluation.registry import METRICS, registry_document, registry_sha256

    doc = json.loads(
        (REPO_ROOT / "artifacts" / "evaluation" / "metric_registry.json").read_text(
            encoding="utf-8"
        )
    )
    assert doc["sha256"] == registry_sha256()
    assert {k: v for k, v in doc.items() if k != "sha256"} == json.loads(
        json.dumps(registry_document())
    )
    names = [m.name for m in METRICS]
    assert len(names) == len(set(names))  # one definition per metric


def test_cooldown_is_per_recording_and_unqueried_readings_never_notify() -> None:
    a = rec([0, 15, 200], [0.1, 0.9, 0.1], patient="p1", key="p1_0")  # notification at 15
    b = rec([0, 10, 300], [0.9, 0.1, 0.1], patient="p1", key="p1_1")  # its own recording
    out = op([a, b], 0.5)
    assert sum(out["notifications"].values()) == 2  # no cooldown carried across recordings
    low = rec([0, 15, 200], [0.9, 0.9, 0.1], queried=[False, True, True])  # LOW NOW at 0
    o = op(low, 0.5)
    assert sum(o["notifications"].values()) == 1  # only the queried reading at 15 notifies
