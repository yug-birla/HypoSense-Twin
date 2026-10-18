"""Patient State Engine tests (S4): history structures, the causal episode tracker (differential
against the offline label builder), data-quality state, update contract, recording boundaries,
determinism, failure handling, ledger and adapters. All data SYNTHETIC."""

from __future__ import annotations

import itertools
import math
from dataclasses import replace

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from hyposense.data.quality import QualityThresholds, cgm_quality_flags, sensor_fault_suspected
from hyposense.data.records import CGMSeries
from hyposense.labels.config import LabelConfig
from hyposense.labels.eligibility import history_mask
from hyposense.labels.episodes import EndReason, build_episodes
from hyposense.state.cgm import EpisodeRule, EpisodeTracker
from hyposense.state.context import parse_context
from hyposense.state.events import CGMReading, MalformedEventError
from hyposense.state.history import AppendLog, SeriesLog
from hyposense.state.ledger import Forecast
from hyposense.state.patient import (
    OutOfOrderEventError,
    PatientState,
    RecordingBoundaryError,
    StateError,
)
from hyposense.state.stream import MEAL_UNKNOWN_MARKERS, order_recordings
from tests.unit.label_fixtures import EPISODE_FIXTURES
from tests.unit.state_helpers import (
    CFG,
    ENGINE,
    RK,
    T0,
    D,
    cbg,
    cgm,
    context,
    meal,
    med,
    run,
    steady,
    stream,
)

RULE = EpisodeRule(70.0, 1200, 1800)


# ---------------------------------------------------------------- history structures
def test_append_log_prefixes_are_immutable_and_branches_do_not_interfere() -> None:
    a = AppendLog[int]().append(1).append(2)
    b = a.append(3)
    c = a.append(30)  # branch from the older snapshot
    assert a.items() == (1, 2) and b.items() == (1, 2, 3) and c.items() == (1, 2, 30)
    assert b.append(4).items() == (1, 2, 3, 4) and c.items() == (1, 2, 30)


def test_series_log_growth_and_branching() -> None:
    s = SeriesLog()
    snaps = []
    for i in range(600):  # forces several capacity doublings
        s = s.append(i * 900, float(i))
        snaps.append(s)
    assert len(snaps[10].ts) == 11 and snaps[10].values[-1] == 10.0
    branch = snaps[10].append(99_999, -1.0)
    assert snaps[11].values[-1] == 11.0 and branch.values[-1] == -1.0 and len(branch) == 12
    with pytest.raises(ValueError):
        snaps[5].ts[0] = 1  # read-only views


# ---------------------------------------------------------------- causal episode tracker
def _offline(ts: np.ndarray, g: np.ndarray):  # type: ignore[no-untyped-def]
    return build_episodes(ts, g, 70.0, min_run=2, max_step_s=1200, max_gap_s=1800, level="L1")


def _end_known(e, k: int) -> bool:  # type: ignore[no-untyped-def]
    """The offline end is causally known at reading k (RECOVERED needs the next reading)."""
    if e.end_reason is EndReason.RECORD_END:
        return False
    return k >= (e.end_index + 1 if e.end_reason is EndReason.RECOVERED else e.end_index)


def _check_tracker(ts: np.ndarray, g: np.ndarray) -> None:
    eps = _offline(ts, g)
    tr = EpisodeTracker(RULE)
    for k in range(len(ts)):
        tr = tr.step(int(ts[k]), float(g[k]))
        confirmed = [e for e in eps if e.onset_index + 1 <= k]
        assert tr.n_onsets == len(confirmed), k
        if confirmed:
            assert tr.onset_ts == confirmed[-1].onset_ts

        # an episode is "in progress" causally iff its onset is confirmed and its end not yet
        live = [e for e in confirmed if not _end_known(e, k)]
        assert tr.in_episode == bool(live), k
        ended = [e for e in confirmed if _end_known(e, k)]
        if ended:
            assert tr.last_end_ts == ended[-1].end_ts
            assert tr.last_end_reason == ended[-1].end_reason.value


@pytest.mark.parametrize("fx", EPISODE_FIXTURES, ids=lambda f: f.name)
def test_tracker_matches_hand_labelled_fixtures(fx) -> None:  # type: ignore[no-untyped-def]
    ts = np.array([1_600_000_000 + m * 60 for m, _ in fx.readings], dtype=np.int64)
    g = np.array([v for _, v in fx.readings], dtype=float)
    _check_tracker(ts, g)


@st.composite
def series(draw):  # type: ignore[no-untyped-def]
    n = draw(st.integers(2, 60))
    steps = draw(
        st.lists(
            st.sampled_from([5, 10, 15, 15, 15, 20, 21, 30, 31, 45]), min_size=n - 1, max_size=n - 1
        )
    )
    vals = draw(
        st.lists(st.sampled_from([50.4, 54.0, 68.4, 70.2, 72.0, 100.8]), min_size=n, max_size=n)
    )
    ts = np.cumsum([0, *steps]).astype(np.int64) * 60 + 1_600_000_000
    return ts, np.array(vals)


@settings(max_examples=400, deadline=None)
@given(series())
def test_tracker_equals_offline_builder_with_confirmation_lag(case) -> None:  # type: ignore[no-untyped-def]
    _check_tracker(*case)


# ---------------------------------------------------------------- data quality
@settings(max_examples=150, deadline=None)
@given(series())
def test_quality_state_equals_authoritative_flag_functions(case) -> None:  # type: ignore[no-untyped-def]
    ts, g = case
    g = np.where(g < 60, 39.6, g)  # include sensor-floor values
    states = run(cgm(((t - T0) / 60, v) for t, v in zip(ts - ts[0] + T0, g, strict=True)))
    thr = QualityThresholds()
    full = CGMSeries(RK, ts - ts[0] + T0, g, np.zeros(len(ts), np.int64), {})
    flags = cgm_quality_flags(full, thr)
    fault = sensor_fault_suspected(full, thr)
    lc = LabelConfig.from_config(CFG)
    hist = history_mask(full.ts, replace(lc, min_time_since_start_s=0))  # count rule only
    for k, s in enumerate(states):
        q = s.quality
        assert q is not None
        assert q.gap_before == flags.gap_before[k] and q.floor == flags.floor[k]
        assert q.rapid_change == flags.rapid_change[k] and q.warmup == flags.warmup[k]
        assert q.sensor_fault_suspected == fault[k]
        assert q.history_ok == hist[k]


def test_sufficiency_reasons() -> None:
    s = run(cgm(steady(0, 150)))[-1]
    assert s.quality is not None and s.quality.sufficient and s.quality.reasons == ()
    s = run(cgm([*steady(0, 150), (185, 120.0)]))[-1]  # 35-min gap before t
    assert s.quality is not None and "AFTER_GAP" in s.quality.reasons
    s = run(cgm(steady(0, 60)))[-1]
    assert s.quality is not None and {"WARM_UP", "INSUFFICIENT_HISTORY"} <= set(s.quality.reasons)
    floor = run(cgm([*steady(0, 150), *steady(165, 270, 39.6)]))[-1]  # 8 floor readings
    assert floor.quality is not None
    assert floor.quality.sensor_fault_suspected and "SENSOR_FLOOR" in floor.quality.reasons


# ---------------------------------------------------------------- update contract
def test_start_and_update_advance_time_and_counts() -> None:
    states = run(
        [*cgm(steady(0, 30)), meal(10), *med("insulin aspart 70/30 10 IU", "insulin_sc", 15)]
    )
    assert [s.n_events for s in states] == list(range(1, len(states) + 1))
    assert all(
        a.ts is not None and b.ts is not None and a.ts <= b.ts
        for a, b in itertools.pairwise(states)
    )
    last = states[-1]
    assert last.cgm.n == 3 and len(last.meals) == 1 and len(last.medication.events) == 1


def test_same_timestamp_order_is_dose_meal_cgm_cbg() -> None:
    dose = med("insulin aspart 70/30 10 IU", "insulin_sc", 15)[0]
    reading = cgm([(15, 120.0)])[0]
    s = PatientState.start(context(), ENGINE)
    s = s.update(dose).update(meal(15)).update(reading).update(cbg(15, 118.0))
    assert s.n_events == 4
    with pytest.raises(OutOfOrderEventError):
        PatientState.start(context(), ENGINE).update(reading).update(dose)  # dose after CGM at t
    with pytest.raises(OutOfOrderEventError):
        s.update(cgm([(0, 100.0)])[0])  # earlier timestamp
    with pytest.raises(OutOfOrderEventError):
        PatientState.start(context(), ENGINE).update(reading).update(reading)  # duplicate


def test_recording_boundary_is_enforced() -> None:
    other = CGMReading("9001_1_20201001", T0, 100.0, 2)
    with pytest.raises(RecordingBoundaryError):
        PatientState.start(context(), ENGINE).update(other)


def test_malformed_input_and_safe_degradation() -> None:
    s = run(cgm(steady(0, 150)))[-1]
    bad = CGMReading(RK, T0 + 9000, math.nan, 99)
    with pytest.raises(MalformedEventError):
        s.update(bad)
    tagged = s.try_update(bad)
    assert tagged.error is not None and "MalformedEventError" in tagged.error
    assert tagged.ts == s.ts  # previous content, explicitly tagged, never "current"
    from tests.unit.state_helpers import BUILDER

    with pytest.raises(StateError):
        BUILDER.snapshot(tagged, "M1")
    with pytest.raises(StateError):
        tagged.update(cgm([(200, 100.0)])[0])
    assert BUILDER.snapshot(s, "M1").values.shape == (38,)


def test_snapshot_only_at_a_cgm_reading() -> None:
    from tests.unit.state_helpers import BUILDER

    s = run([*cgm(steady(0, 150)), meal(160)])[-1]
    with pytest.raises(StateError):
        BUILDER.snapshot(s, "M1")


def test_replay_is_deterministic() -> None:
    events = [
        *cgm(steady(0, 600, 110.0)),
        meal(100),
        *med("gliclazide 30 mg", "oral_agents", 90),
        *med("insulin aspart 70/30 12 IU", "insulin_sc", 95),
        cbg(200, 101.0),
    ]
    a = [s.digest() for s in run(events)]
    b = [s.digest() for s in run(list(reversed(events)))]  # input order irrelevant once sorted
    assert a == b and len(set(a)) == len(a)


def test_same_past_different_future_gives_identical_current_state() -> None:
    past = [*cgm(steady(0, 300)), meal(100), *med("gliclazide 30 mg", "oral_agents", 90)]
    fut_a = [*cgm(steady(315, 600, 60.0)), *med("insulin aspart 70/30 20 IU", "insulin_sc", 330)]
    fut_b = [*cgm(steady(315, 600, 180.0)), meal(400)]
    sa = run(past + fut_a)
    sb = run(past + fut_b)
    n = len(past)
    assert sa[n - 1].digest() == sb[n - 1].digest()
    # branching from a shared prefix state does not disturb the prefix
    base = run(past)[-1]
    d0 = base.digest()
    base.update(fut_a[0])
    base.update(fut_b[0])
    assert base.digest() == d0


# ---------------------------------------------------------------- ledger
def test_ledger_reconciles_causally() -> None:
    states = run(cgm([*steady(0, 120), (135, 66.6), (150, 64.8), *steady(165, 300)]))
    s0 = states[8]  # t = 120 min
    s = s0.record_forecast(Forecast(s0.ts or 0, "M3", "test", 0.4))
    for st_next in cgm([(135, 66.6), (150, 64.8), *steady(165, 300)]):
        s = s.update(st_next)
    resolved = s.ledger.resolved.items()
    assert len(resolved) == 1 and resolved[0].outcome == 1
    assert resolved[0].resolved_ts == T0 + 150 * 60  # onset at 135 confirmed by the 150 reading
    quiet = run(cgm(steady(0, 300)))
    s = quiet[8].record_forecast(Forecast(quiet[8].ts or 0, "M3", "test", 0.1))
    for e in cgm(steady(135, 300)):
        s = s.update(e)
    r = s.ledger.resolved.items()
    assert len(r) == 1 and r[0].outcome == 0 and r[0].resolved_ts == T0 + 195 * 60
    with pytest.raises(StateError):
        quiet[8].record_forecast(Forecast(T0, "M3", "test", 0.1))


# ---------------------------------------------------------------- adapters
def test_static_context_parsing() -> None:
    plaus = {k: (float(v[0]), float(v[1])) for k, v in CFG["features"]["static_plausible"].items()}
    row = {
        "age_y": 61,
        "sex_code": 1,
        "bmi": "/",
        "weight_kg": 900,
        "duration_y": " 5 ",
        "hba1c_mmol_mol": "abc",
        "egfr": 90,
        "c_peptide_fasting_nmol_l": None,
        "prescribed_hypoglycemic_agents": "Novolin 30R, metformin, gliclazide",
        "summary_hypoglycemia_flag": "yes",
    }
    c = parse_context("shanghai_t2dm:1", "1_0_20200101", row, D, plaus)
    assert c.values["age_y"] == 61 and c.values["sex_male"] == 0.0
    assert math.isnan(c.values["bmi"]) and math.isnan(c.values["weight_kg"])  # '/', implausible
    assert c.values["diabetes_duration_y"] == 5.0 and math.isnan(c.values["hba1c_mmol_mol"])
    assert {"bmi: missing", "weight_kg: implausible", "hba1c_mmol_mol: unparseable"} <= set(
        c.issues
    )
    assert c.regimen["rx_premix"] == 1 and c.regimen["rx_insulin"] == 1
    assert c.regimen["rx_metformin"] == 1 and c.regimen["rx_su"] == 1
    assert c.regimen["rx_basal"] == 0 and c.regimen["rx_glinide"] == 0
    assert c.prescribed_classes >= {"insulin", "sulfonylurea"}
    none = parse_context(
        "shanghai_t2dm:1", "1_0_20200101", {"prescribed_hypoglycemic_agents": "none"}, D, plaus
    )
    assert all(v == 0 for v in none.regimen.values())
    empty = parse_context("shanghai_t2dm:1", "1_0_20200101", {}, D, plaus)
    assert all(math.isnan(v) for v in empty.regimen.values())


def test_meal_unknown_markers_and_recording_order() -> None:
    assert "data not available" in MEAL_UNKNOWN_MARKERS and "未记录" in MEAL_UNKNOWN_MARKERS
    late = stream(
        cgm([(600, 100.0)], rk="9001_0_20200913"), context(recording_key="9001_0_20200913")
    )
    early = stream(
        cgm([(0, 100.0)], rk="9001_1_20200901"), context(recording_key="9001_1_20200901")
    )
    early = replace(early, events=(CGMReading("9001_1_20200901", T0 - 86400 * 10, 100.0, 2),))
    ordered = order_recordings([late, early])
    assert [s.identity.period for s in ordered] == [1, 0]  # by time, not by number


def test_ledger_finalize_at_recording_end() -> None:
    states = run(cgm(steady(0, 180)))
    s = states[8].record_forecast(Forecast(states[8].ts or 0, "M3", "t", 0.2))  # t_f = 120
    for e in cgm(steady(135, 180)):
        s = s.update(e)
    assert len(s.ledger.pending) == 1  # last reading exactly t_f + 60: not yet resolved
    led, unknown = s.ledger.finalize(T0 + 180 * 60)
    assert unknown == () and led.resolved.items()[0].outcome == 0  # FALSE (ANALYSIS_PLAN §2.4)
    short = states[8].record_forecast(Forecast(states[8].ts or 0, "M3", "t", 0.2))
    led2, unknown2 = short.ledger.finalize(T0 + 150 * 60)
    assert len(unknown2) == 1 and len(led2.resolved) == 0  # OUTCOME-UNKNOWN


def test_engine_cache_is_not_shared_through_replace() -> None:
    a = run([*cgm(steady(0, 120)), *med("gliclazide 30 mg", "oral_agents", 30)])[-1]
    b = run([*cgm(steady(0, 120)), *med("gliclazide 120 mg", "oral_agents", 30)])[-1]
    t = a.ts or 0
    first = a.medication.at(t).exposure["act_su"]
    swapped = replace(a.medication, events=b.medication.events)
    assert swapped.at(t).exposure["act_su"] == b.medication.at(t).exposure["act_su"] != first


def test_unrecognised_regimen_text_is_flagged() -> None:
    plaus = {k: (float(v[0]), float(v[1])) for k, v in CFG["features"]["static_plausible"].items()}
    c = parse_context("p", "1_0_20200101", {"prescribed_hypoglycemic_agents": "xyzzy"}, D, plaus)
    assert "regimen: no recognised drug in non-empty text" in c.issues
