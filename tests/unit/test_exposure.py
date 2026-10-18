"""Kernel, exposure-engine and raw-timing tests: causality, shape, additivity, quality states.
All events SYNTHETIC."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from hyposense.common.config import load_config
from hyposense.medication.dictionary import load_dictionary
from hyposense.medication.exposure import ExposureEngine, QualityState, load_kernel_set
from hyposense.medication.kernels import BatemanKernel, ExponentialKernel, FlatKernel
from hyposense.medication.parse import Context, parse_cell
from hyposense.medication.timing import raw_timing

D = load_dictionary()
PH = load_config("pharma.yaml")
KS = load_kernel_set(PH, 36)
T0 = 1_600_000_000
H = 3600
GRID = np.arange(0, 1801, 0.25)  # minutes


def ev(value: object, column: str, minute: float, row: int = 2):  # type: ignore[no-untyped-def]
    ctx = Context("shanghai_t2dm:2001", "r", T0 + int(minute * 60), column, row, str(value))
    return list(parse_cell(value, column, ctx, D, PH["formulation_rules"]).events)


def q(engine: ExposureEngine, minute: float, cls: str) -> QualityState:
    return engine.quality(np.array([T0 + int(minute * 60)]))[cls][0]


def at(engine: ExposureEngine, minutes: list[float]) -> dict[str, np.ndarray]:
    return engine.compute(np.array([T0 + int(m * 60) for m in minutes], dtype=np.int64))


# ---------------- kernels ----------------


@pytest.mark.parametrize(("tp", "td"), [(75, 300), (150, 480), (360, 900)])
def test_exponential_kernel_shape(tp: float, td: float) -> None:
    k = ExponentialKernel(tp, td)
    a = k.activity(GRID)
    assert k.activity(np.array([-5.0, 0.0]))[0] == 0 and k.activity(np.array([0.0]))[0] == 0
    assert abs(GRID[np.argmax(a)] - tp) <= 0.5
    assert abs(np.trapezoid(a, GRID) - 1.0) < 0.01
    assert np.all(a[td < GRID] == 0) and np.all(a >= 0)
    ob = k.on_board(GRID)
    assert k.on_board(np.array([-1.0]))[0] == 0 and ob[0] == 1.0
    assert np.all(np.diff(ob) <= 1e-12) and np.all(ob[td <= GRID] == 0)
    # on-board is the complement of cumulative activity
    cum = np.concatenate([[0], np.cumsum((a[1:] + a[:-1]) / 2 * np.diff(GRID))])
    assert np.max(np.abs((1 - ob) - cum)[td > GRID]) < 0.01


def test_flat_kernel() -> None:
    k = FlatKernel(60, 1440)
    a = k.activity(GRID)
    assert np.all(a[GRID < 60] == 0) and a[GRID == 60][0] == pytest.approx(1 / 1440)
    big = np.arange(0, 1600, 0.25)
    assert abs(np.trapezoid(k.activity(big), big) - 1) < 0.01
    assert k.on_board(np.array([-1.0, 0.0, 30.0, 780.0, 1500.0])).tolist() == [0, 1, 1, 0.5, 0]


@pytest.mark.parametrize(("th", "tm"), [(720, 240), (60, 60), (300, 150)])
def test_bateman_kernel(th: float, tm: float) -> None:
    k = BatemanKernel(th, tm)
    t = np.arange(0, 20 * th, 1.0)
    v = k.activity(t)
    assert v[0] == 0 and k.activity(np.array([-1.0]))[0] == 0
    assert abs(t[np.argmax(v)] - tm) <= 1 and abs(v.max() - 1.0) < 1e-4
    assert k.ka > np.log(2) / th
    after = t >= k.support
    assert np.all(v[after] == 0) and v[(t > tm) & ~after].min() >= 0.01 - 1e-9


def test_invalid_kernel_parameters() -> None:
    with pytest.raises(ValueError):
        ExponentialKernel(200, 300)  # t_peak >= t_dur / 2
    with pytest.raises(ValueError):
        BatemanKernel(60, 100)  # t_max >= t_half / ln 2


# ---------------- exposure engine ----------------


def test_zero_before_and_at_dose_full_on_board_at_dose() -> None:
    eng = ExposureEngine(ev("insulin aspart, 10 IU", "insulin_sc", 60), KS)
    o = at(eng, [0, 59, 60, 61, 135])
    assert o["act_prandial"][:3].tolist() == [0.0, 0.0, 0.0]
    assert o["iob_insulin"][:3].tolist() == [0.0, 0.0, 10.0]  # convention: dose at t is on board
    assert o["min_since_insulin"][2] == 0.0 and np.isnan(o["min_since_insulin"][0])
    assert o["act_prandial"][4] > o["act_prandial"][3] > 0  # rising toward the 75-min peak


def test_overlapping_doses_are_additive() -> None:
    a = ev("insulin aspart, 6 IU", "insulin_sc", 0)
    b = ev("Novolin R, 4 IU", "insulin_sc", 30, row=3)
    m = list(range(0, 600, 15))
    both, ea, eb = (at(ExposureEngine(x, KS), m) for x in (a + b, a, b))
    for k in ("act_prandial", "iob_insulin", "insulin_p30", "insulin_p60"):
        np.testing.assert_allclose(both[k], ea[k] + eb[k], rtol=0, atol=1e-12)


def test_repeated_doses_accumulate_then_decay() -> None:
    evs = [e for k in range(3) for e in ev("insulin aspart, 5 IU", "insulin_sc", k * 60, row=k)]
    o = at(ExposureEngine(evs, KS), [130, 200, 300, 420])
    assert o["iob_insulin"][0] > o["iob_insulin"][1] > o["iob_insulin"][2] > 0.0
    assert o["iob_insulin"][3] == 0.0  # last dose (120 min) ends at 120 + 300 = 420 min


def test_premix_split_and_basal_group() -> None:
    o = at(ExposureEngine(ev("insulin aspart 70/30, 10 IU", "insulin_sc", 0), KS), [0])
    assert o["iob_insulin"][0] == pytest.approx(10.0)
    o = at(ExposureEngine(ev("insulin aspart 70/30, 10 IU", "insulin_sc", 0), KS), [120])
    assert o["act_prandial"][0] > 0 and o["act_intermediate"][0] > 0 and o["act_basal"][0] == 0
    o = at(ExposureEngine(ev("insulin glargine, 24 IU", "insulin_sc", 0), KS), [30, 120])
    assert o["act_basal"].tolist() == [0.0, pytest.approx(24 / 1440 * 60)]


def test_secretagogue_scaled_by_dmax() -> None:
    o = at(
        ExposureEngine(ev("gliclazide 60 mg", "oral_agents", 0), KS),
        [PH["secretagogue"]["gliclazide_mr"]["t_max_min"]["value"]],
    )
    assert o["act_su"][0] == pytest.approx(60 / 120, rel=1e-6)


def test_future_dose_does_not_change_the_past() -> None:
    base = ev("insulin aspart, 6 IU", "insulin_sc", 0)
    fut = (
        base
        + ev("insulin aspart, 50 IU", "insulin_sc", 200, row=9)
        + ev("gliclazide 120 mg", "oral_agents", 200, row=9)
    )
    m = list(range(0, 200, 5))
    a, b = at(ExposureEngine(base, KS), m), at(ExposureEngine(fut, KS), m)
    for k in a:
        assert np.array_equal(a[k], b[k], equal_nan=True), k


def test_moving_a_dose_later_changes_only_later_exposure() -> None:
    early = at(ExposureEngine(ev("insulin aspart, 6 IU", "insulin_sc", 60), KS), range(0, 400, 15))
    late = at(ExposureEngine(ev("insulin aspart, 6 IU", "insulin_sc", 120), KS), range(0, 400, 15))
    idx = np.arange(0, 400, 15)
    assert np.array_equal(early["act_prandial"][idx < 60], late["act_prandial"][idx < 60])
    assert not np.array_equal(early["act_prandial"][idx > 60], late["act_prandial"][idx > 60])


def test_quality_states() -> None:
    eng = ExposureEngine(ev("Novolin R", "insulin_sc", 0), KS)  # dose unknown
    assert q(eng, 60, "insulin") is QualityState.DOSE_UNKNOWN
    assert np.isnan(at(eng, [60])["act_prandial"][0])
    pres = ExposureEngine([], KS, frozenset({"insulin"}))
    assert q(pres, 60, "insulin") is QualityState.TIMING_UNKNOWN
    assert np.isnan(at(pres, [60])["iob_insulin"][0])
    none = ExposureEngine([], KS)
    assert q(none, 60, "insulin") is QualityState.NO_LOGGED_MEDICATION
    assert at(none, [60])["iob_insulin"][0] == 0.0
    unk = ExposureEngine(ev("gliclazide 50 mg", "oral_agents", 0), KS)
    assert q(unk, 60, "sulfonylurea") is QualityState.FORMULATION_UNKNOWN
    inf = ExposureEngine(ev("gliclazide 15 mg", "oral_agents", 0), KS)
    assert q(inf, 60, "sulfonylurea") is QualityState.PARTIAL
    tmax = PH["secretagogue"]["gliclazide_mr"]["t_max_min"]["value"]
    assert at(inf, [tmax])["act_su"][0] == pytest.approx(15 / 120, rel=1e-6)
    stale = ExposureEngine(ev("insulin aspart, 6 IU", "insulin_sc", 0), KS, frozenset({"insulin"}))
    assert q(stale, 36 * 60 - 1, "insulin") is QualityState.KNOWN
    assert q(stale, 36 * 60 + 1, "insulin") is QualityState.TIMING_UNKNOWN


def test_csii_basal_reconstruction_suspend_and_cap() -> None:
    evs = ev(0.4, "csii_basal", 0) + ev(0.0, "csii_basal", 240, row=3)
    o = at(ExposureEngine(evs, KS), [0, 120, 239, 240, 599, 600])
    # a 0-rate entry is a programmed segment too; every segment ends at the 6-h cap (240 + 360)
    assert o["csii_active"].tolist() == [1.0, 1.0, 1.0, 1.0, 1.0, 0.0]
    assert o["csii_rate_iu_h"].tolist() == [0.4, 0.4, 0.4, 0.0, 0.0, 0.0]
    assert o["iob_insulin"][1] > 0
    sus = ev(0.4, "csii_basal", 0) + ev(
        "temporarily suspend insulin delivery", "csii_basal", 60, row=3
    )
    o = at(ExposureEngine(sus, KS), [30, 61])
    assert o["csii_active"].tolist() == [1.0, 0.0]
    capped = ExposureEngine(ev(0.5, "csii_basal", 0), KS)  # no later pump entry: cap at 6 h
    o = at(capped, [359, 360, 480])
    assert o["csii_active"].tolist() == [1.0, 0.0, 0.0]
    assert q(capped, 480, "insulin") is QualityState.PARTIAL
    # projection continues the programmed rate (P-B3); without continuation it is smaller
    with_cont = at(capped, [60])["insulin_p60"][0]
    without = at(ExposureEngine(ev(0.5, "csii_basal", 0), replace(KS, project_pump=False)), [60])[
        "insulin_p60"
    ][0]
    assert with_cont > without > 0


def test_iv_insulin_flag_only() -> None:
    eng = ExposureEngine(ev("500ml 0.9% sodium chloride, 8 IU Novolin R", "insulin_iv", 0), KS)
    o = at(eng, [10, 239, 241])
    assert o["iv_insulin_recent"].tolist() == [1.0, 1.0, 0.0]
    assert o["act_prandial"].tolist() == [0.0, 0.0, 0.0]  # no kernel: rate unknown
    assert q(eng, 10, "insulin") is QualityState.PARTIAL


def test_deterministic() -> None:
    evs = ev("insulin aspart 70/30, 14 IU", "insulin_sc", 0) + ev(
        "gliclazide 30 mg", "oral_agents", 10, row=4
    )
    m = list(range(0, 1000, 15))
    a, b = at(ExposureEngine(evs, KS), m), at(ExposureEngine(list(reversed(evs)), KS), m)
    for k in a:
        assert np.array_equal(a[k], b[k], equal_nan=True)


@st.composite
def schedules(draw):  # type: ignore[no-untyped-def]
    n = draw(st.integers(0, 12))
    cells = [
        ("insulin aspart, 6 IU", "insulin_sc"),
        ("insulin aspart 70/30, 14 IU", "insulin_sc"),
        ("insulin glargine, 10 IU", "insulin_sc"),
        ("gliclazide 30 mg", "oral_agents"),
        ("gliclazide 15 mg", "oral_agents"),
        ("repaglinide 1 mg", "oral_agents"),
        (0.4, "csii_basal"),
        (0.7, "csii_basal"),
        (5.0, "csii_bolus"),
        ("temporarily suspend insulin delivery", "csii_basal"),
        ("Novolin R", "insulin_sc"),
        ("500ml 5% glucose, 6 IU Novolin R", "insulin_iv"),
    ]
    picks = draw(st.lists(st.sampled_from(cells), min_size=n, max_size=n))
    mins = draw(st.lists(st.integers(0, 3000), min_size=n, max_size=n))
    evs = [
        e for k, ((v, c), m) in enumerate(zip(picks, mins, strict=True)) for e in ev(v, c, m, row=k)
    ]
    t = draw(st.integers(0, 3200))
    return evs, t


@settings(max_examples=150, deadline=None)
@given(schedules())
def test_truncation_equality(case) -> None:  # type: ignore[no-untyped-def]
    evs, minute = case
    t = np.array([T0 + minute * 60], dtype=np.int64)
    pres = frozenset({"insulin", "sulfonylurea"})
    full = ExposureEngine(evs, KS, pres).compute(t)
    trunc = ExposureEngine([e for e in evs if e.ts <= t[0]], KS, pres).compute(t)
    for k in full:
        assert np.array_equal(full[k], trunc[k], equal_nan=True), k
    rf, rt = raw_timing(evs, t), raw_timing([e for e in evs if e.ts <= t[0]], t)
    for k in rf:
        assert np.array_equal(rf[k], rt[k], equal_nan=True), k


# ---------------- raw timing (M3r) ----------------


def test_raw_timing() -> None:
    evs = (
        ev("insulin aspart, 6 IU", "insulin_sc", 0)
        + ev("insulin aspart, 4 IU", "insulin_sc", 600, row=3)
        + ev("insulin glargine, 10 IU", "insulin_sc", 100, row=4)
        + ev("Novolin R", "insulin_sc", 1500, row=5)
    )
    o = raw_timing(evs, np.array([T0 - 60, T0 + 700 * 60, T0 + 1450 * 60, T0 + 1500 * 60]))
    assert np.isnan(o["insulin_bolus_min_since_last"][0]) and o["insulin_bolus_n_24h"][0] == 0
    assert o["insulin_bolus_min_since_last"][1] == 100 and o["insulin_bolus_last_dose"][1] == 4
    assert o["insulin_bolus_dose_24h"][1] == 10 and o["insulin_bolus_n_24h"][1] == 2
    assert o["insulin_bolus_dose_24h"][2] == 4  # the 0-min dose left the (t-24h, t] window
    assert np.isnan(o["insulin_bolus_dose_24h"][3])  # unknown dose in window: no fake total
    assert o["insulin_basal_min_since_last"][1] == 600
    assert o["su_n_24h"].tolist() == [0, 0, 0, 0]


def test_raw_timing_cap() -> None:
    o = raw_timing(ev("gliclazide 30 mg", "oral_agents", 0), np.array([T0 + 5000 * 60]))
    assert o["su_min_since_last"][0] == 1440.0
