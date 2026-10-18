"""ABSOLUTE LEAKAGE RULE tests for the state engine and feature builder (CLAUDE.md §11; Blueprint
Table H.2 test_no_future_leak, test_state_updates, test_features_ignore_ledger).

- Truncation equality: features at t from the complete record == features from the record
  truncated exactly at t. Bitwise, every level, every CGM time. Synthetic streams cover CGM gaps,
  lows / episode boundaries, sensor-floor runs, s.c. / oral / CSII / i.v. medication, pump
  suspension, dose times coinciding with readings, and meals with unknown content.
- Truncation through the loader: the same on SYNTHETIC workbooks (adapter included).
- Future perturbation: altering future CGM, medication, meals or outcomes never changes t.
- Offline vs replay parity: the offline table equals `snapshot(state, level)` replay.
- The ledger / forecast state never influences features.
All data SYNTHETIC. The real-data versions run in tests/integration and `hyposense audit features`.
"""

from __future__ import annotations

import ast
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from hyposense.data.loader import load_recording
from hyposense.features.build import build_recording
from hyposense.features.snapshot import LEVEL_INDEX, FeatureInputs
from hyposense.features.spec import LEVELS
from hyposense.state.events import CGMReading, StateEvent, sort_key
from hyposense.state.ledger import Forecast
from hyposense.state.patient import PatientState
from hyposense.state.stream import recording_stream
from tests.conftest import row
from tests.unit.state_helpers import (
    BUILDER,
    CFG,
    ENGINE,
    PHARMA,
    T0,
    D,
    cgm,
    meal,
    med,
    stream,
)

PKG = Path(__file__).resolve().parents[2] / "src" / "hyposense"

MED_CHOICES = [
    ("insulin aspart 70/30 10 IU", "insulin_sc"),
    ("novolin r 6 IU", "insulin_sc"),
    ("insulin glargine 14 IU", "insulin_sc"),
    ("novolin n 8 IU", "insulin_sc"),
    ("gliclazide 30 mg", "oral_agents"),
    ("gliclazide 15 mg", "oral_agents"),
    ("glimepiride 2 mg", "oral_agents"),
    ("repaglinide 1 mg", "oral_agents"),
    ("metformin 500 mg", "oral_agents"),
    (4.0, "csii_bolus"),
    (0.8, "csii_basal"),
    (0.0, "csii_basal"),
    ("temporarily suspend insulin delivery", "csii_basal"),
    ("novolin r 20 IU + 0.9% sodium chloride 500 ml", "insulin_iv"),
]


def union_at_end(events: list[StateEvent]) -> np.ndarray:
    s = PatientState.start(stream(events).context, ENGINE)
    for e in sorted(events, key=sort_key):
        s = s.update(e)
    return BUILDER.union(FeatureInputs.of(s))


def full_rows(events: list[StateEvent]) -> tuple[np.ndarray, np.ndarray]:
    rf = build_recording(stream(events), ENGINE, BUILDER)
    return rf.ts, rf.X


@st.composite
def scenarios(draw):  # type: ignore[no-untyped-def]
    n = draw(st.integers(10, 70))
    steps = draw(
        st.lists(
            st.sampled_from([15, 15, 15, 15, 10, 20, 25, 35, 90]), min_size=n - 1, max_size=n - 1
        )
    )
    minutes = np.cumsum([0, *steps]).tolist()
    vals = draw(
        st.lists(
            st.sampled_from([39.6, 52.2, 64.8, 68.4, 70.2, 79.2, 95.4, 140.4, 250.2]),
            min_size=n,
            max_size=n,
        )
    )
    events: list[StateEvent] = list(cgm(zip(minutes, vals, strict=True)))
    k = draw(st.integers(0, 12))
    for j in range(k):
        value, col = draw(st.sampled_from(MED_CHOICES))
        on_reading = draw(st.booleans())
        m = draw(st.sampled_from(minutes)) if on_reading else draw(st.integers(0, minutes[-1] + 30))
        events += med(value, col, m, row=8000 + j)
    for j in range(draw(st.integers(0, 6))):
        events.append(meal(draw(st.sampled_from(minutes)), draw(st.booleans()), row=9000 + j))
    return events


def _truncate(events: list[StateEvent], t: int) -> list[StateEvent]:
    return [e for e in events if e.ts <= t]


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(scenarios())
def test_truncation_equality_every_cgm_time(events) -> None:  # type: ignore[no-untyped-def]
    ts, X = full_rows(events)
    for k, t in enumerate(ts.tolist()):
        got = union_at_end(_truncate(events, t))
        assert got.tobytes() == X[k].tobytes(), (k, t)


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(scenarios(), st.data())
def test_future_perturbation_never_changes_the_present(events, data) -> None:  # type: ignore[no-untyped-def]
    ts, X = full_rows(events)
    k = data.draw(st.integers(0, len(ts) - 1))
    t = int(ts[k])
    future_cgm = [e for e in events if isinstance(e, CGMReading) and e.ts > t]
    variants = {
        "future_cgm": [e for e in events if not (isinstance(e, CGMReading) and e.ts > t)]
        + [replace(e, value_mgdl=50.4) for e in future_cgm],
        "future_medication": events
        + med("insulin aspart 70/30 40 IU", "insulin_sc", (t - T0) / 60 + 15, row=99_001)
        + med("gliclazide 120 mg", "oral_agents", (t - T0) / 60 + 1, row=99_002),
        "future_meal": [*events, meal((t - T0) / 60 + 5, row=99_003)],
        "future_outcome": [e for e in events if not (isinstance(e, CGMReading) and e.ts > t)]
        + cgm([((t - T0) / 60 + 15, 52.2), ((t - T0) / 60 + 30, 50.4)])
        + [e for e in future_cgm if e.ts > t + 1800],
    }
    for name, ev in variants.items():
        ev = [e for e in ev if not (isinstance(e, CGMReading) and e.ts > t)] + sorted(
            {e.ts: e for e in ev if isinstance(e, CGMReading) and e.ts > t}.values(),
            key=lambda e: e.ts,
        )
        ts2, X2 = full_rows(ev)
        k2 = int(np.searchsorted(ts2, t))
        assert ts2[k2] == t
        assert X2[k2].tobytes() == X[k].tobytes(), name


def test_offline_table_equals_event_by_event_replay_snapshots() -> None:
    events = [
        *cgm((m, 100.0 + 30 * np.sin(m / 90)) for m in range(0, 2000, 15)),
        *med("insulin aspart 70/30 12 IU", "insulin_sc", 400),
        *med("gliclazide 30 mg", "oral_agents", 405),
        *med(0.8, "csii_basal", 600),
        *med(4.0, "csii_bolus", 615),
        meal(390),
        meal(700, known=False),
    ]
    ts, X = full_rows(events)
    s = PatientState.start(stream(events).context, ENGINE)
    k = 0
    for e in sorted(events, key=sort_key):
        s = s.try_update(e)
        assert s.error is None
        if isinstance(e, CGMReading):
            for lvl in LEVELS:
                snap = BUILDER.snapshot(s, lvl)
                assert snap.values.tobytes() == X[k, LEVEL_INDEX[lvl]].tobytes()
            k += 1
    assert k == len(ts)


def test_features_ignore_forecast_state_and_ledger() -> None:
    events = [*cgm((m, 120.0 - m / 20) for m in range(0, 600, 15))]
    s = PatientState.start(stream(events).context, ENGINE)
    for e in events:
        s = s.update(e)
    other = s.record_forecast(Forecast(s.ts or 0, "M3", "x", 0.99))
    other = replace(other, ledger=replace(other.ledger, pending=(), horizon_s=1))
    assert (
        BUILDER.union(FeatureInputs.of(s)).tobytes()
        == BUILDER.union(FeatureInputs.of(other)).tobytes()
    )


def test_feature_package_cannot_reach_the_ledger_or_labels() -> None:
    for py in sorted((PKG / "features").rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        mods |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        assert "hyposense.state.ledger" not in mods, py
        assert not any(m.startswith(("hyposense.labels", "hyposense.audit")) for m in mods), py
    src = (PKG / "features" / "snapshot.py").read_text(encoding="utf-8")
    assert "state.ledger" not in src and "state.forecast" not in src


# ---------------------------------------------------------------- through the loader
def _workbook_rows() -> list[list[object]]:
    start = datetime(2021, 3, 1, 6, 0)
    rows: list[list[object]] = []
    for i in range(160):
        t = start + timedelta(minutes=15 * i)
        if 70 <= i < 74:
            continue  # a 75-min CGM gap
        v = 64.8 if 40 <= i < 44 else 39.6 if 100 <= i < 109 else 110 + 20 * np.sin(i / 7)
        kw: dict[str, object] = {}
        if i % 24 == 4:
            kw["insulin_sc"] = "insulin aspart 70/30 10 IU"
            kw["diet_en"], kw["diet_cn"] = "rice 100 g", "rice"
        if i % 24 == 12:
            kw["oral"] = "gliclazide 30 mg, metformin 500 mg"
            kw["diet_en"], kw["diet_cn"] = "Data not available", "未记录"
        if i == 50:
            kw["csii_basal"] = 0.8
        if i == 60:
            kw["csii_basal"] = "temporarily suspend insulin delivery"
        rows.append(row(t, round(float(v), 1), **kw))
    return rows


def test_truncation_equality_through_the_loader(make_workbook, tmp_path) -> None:  # type: ignore[no-untyped-def]
    rows = _workbook_rows()
    rules = PHARMA["formulation_rules"]
    plaus = {k: (float(v[0]), float(v[1])) for k, v in CFG["features"]["static_plausible"].items()}
    full = load_recording(make_workbook("9002_0_20210301.xlsx", rows, directory=tmp_path / "full"))
    rf = build_recording(recording_stream(full, D, rules, None, plaus), ENGINE, BUILDER)
    assert len(rf.ts) == 156
    for k in range(0, len(rf.ts), 5):
        t_local = rows[k][0]
        cut = [r for r in rows if r[0] <= t_local]
        rec = load_recording(
            make_workbook("9002_0_20210301.xlsx", cut, directory=tmp_path / f"c{k}")
        )
        s = recording_stream(rec, D, rules, None, plaus)
        st_ = PatientState.start(s.context, ENGINE)
        for e in s.events:
            st_ = st_.update(e)
        assert BUILDER.union(FeatureInputs.of(st_)).tobytes() == rf.X[k].tobytes(), k
