"""Label-builder tests: hand-labelled fixtures, loader-path cases, invariants, and differential
tests against a verbatim transcription of the blueprint's executable specification (audit.py).
All data SYNTHETIC."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from hyposense.common.config import load_config
from hyposense.data.loader import load_recording
from hyposense.labels.build import label_recording
from hyposense.labels.config import LabelConfig
from hyposense.labels.eligibility import (
    Ineligibility,
    build_prediction_labels,
    warnable_onsets,
)
from hyposense.labels.episodes import Episode, build_episodes
from tests.conftest import WorkbookFactory, row
from tests.unit.label_fixtures import (
    COVERAGE,
    ELIGIBILITY_FIXTURES,
    EPISODE_FIXTURES,
    Fixture,
)

BASE = 1_600_000_020  # arbitrary epoch origin (s)
CFG = LabelConfig()


def _arrays(fx: Fixture) -> tuple[np.ndarray, np.ndarray]:
    ts = np.array([BASE + 60 * m for m, _ in fx.readings], dtype=np.int64)
    g = np.array([v for _, v in fx.readings], dtype=np.float64)
    return ts, g


def _episodes(ts: np.ndarray, g: np.ndarray, thr: float, min_run: int, level: str) -> list:
    return list(
        build_episodes(
            ts,
            g,
            thr,
            min_run=min_run,
            max_step_s=CFG.max_step_s,
            max_gap_s=CFG.max_gap_s,
            level=level,
        )
    )


def _as_tuples(eps: list[Episode]) -> list[tuple]:
    out = []
    for e in eps:
        end = None if e.end_ts is None else (e.end_ts - BASE) // 60
        out.append(((e.onset_ts - BASE) // 60, end, e.end_reason.value, e.nadir_mgdl, e.n_readings))
    return out


ALL = EPISODE_FIXTURES + ELIGIBILITY_FIXTURES


def test_fixture_count_and_checklist_coverage() -> None:
    assert len(ALL) >= 30
    assert set(COVERAGE) == set(range(1, 31))


@pytest.mark.parametrize("fx", ALL, ids=lambda f: f.name)
def test_l1_episodes(fx: Fixture) -> None:
    ts, g = _arrays(fx)
    assert _as_tuples(_episodes(ts, g, 70.0, 2, "L1")) == fx.l1


@pytest.mark.parametrize("fx", [f for f in ALL if f.l2 is not None], ids=lambda f: f.name)
def test_l2_episodes(fx: Fixture) -> None:
    ts, g = _arrays(fx)
    assert _as_tuples(_episodes(ts, g, 54.0, 2, "L2")) == fx.l2


@pytest.mark.parametrize("fx", [f for f in ALL if f.single is not None], ids=lambda f: f.name)
def test_single_reading_episodes(fx: Fixture) -> None:
    ts, g = _arrays(fx)
    assert _as_tuples(_episodes(ts, g, 70.0, 1, "L1_single")) == fx.single


def _labels(fx: Fixture):  # type: ignore[no-untyped-def]
    ts, g = _arrays(fx)
    cfg = LabelConfig(
        warmup_restart_after_gap_s=None if fx.restart_gap_min is None else fx.restart_gap_min * 60
    )
    eps = _episodes(ts, g, 70.0, 2, "L1")
    return build_prediction_labels(ts, g, eps, cfg), cfg, eps


@pytest.mark.parametrize("fx", ELIGIBILITY_FIXTURES, ids=lambda f: f.name)
def test_eligibility_labels_and_reasons(fx: Fixture) -> None:
    lab, cfg, eps = _labels(fx)
    minutes = [(int(t) - BASE) // 60 for t in lab.ts]
    eligible = {m for m, e in zip(minutes, lab.eligible, strict=True) if e}
    positive = {m for m, e, y in zip(minutes, lab.eligible, lab.y, strict=True) if e and y == 1}
    if fx.eligible is not None:
        assert eligible == fx.eligible
    if fx.positive is not None:
        assert positive == fx.positive
    by_min = dict(zip(minutes, lab.reason.tolist(), strict=True))
    for m, name in fx.reasons.items():
        assert Ineligibility(by_min[m]).name == name, (fx.name, m)
    if fx.warnable:
        onsets = np.array([e.onset_ts for e in eps], dtype=np.int64)
        flags = dict(
            zip(
                ((onsets - BASE) // 60).tolist(),
                warnable_onsets(lab, onsets, cfg).tolist(),
                strict=True,
            )
        )
        assert flags == fx.warnable


@pytest.mark.parametrize("fx", ELIGIBILITY_FIXTURES, ids=lambda f: f.name)
def test_label_invariants(fx: Fixture) -> None:
    lab, cfg, eps = _labels(fx)
    assert np.all(lab.y[~lab.eligible] == -1)  # no label off-eligibility
    assert np.all(np.isin(lab.y[lab.eligible], [0, 1]))
    assert np.all(lab.value[lab.eligible] >= 70.0)  # never a current low
    assert np.array_equal(lab.eligible, lab.reason == Ineligibility.ELIGIBLE)
    onsets = np.array([e.onset_ts for e in eps], dtype=np.int64)
    for t, e, y in zip(lab.ts, lab.eligible, lab.y, strict=True):  # y == 1 <=> onset in (t, t+H]
        if e:
            assert y == int(np.any((onsets > t) & (onsets <= t + cfg.horizon_s)))


def test_unsorted_or_duplicate_input_rejected() -> None:
    with pytest.raises(ValueError):
        build_episodes(
            np.array([0, 900, 900], dtype=np.int64),
            np.array([60.0, 60.0, 60.0]),
            70.0,
            min_run=2,
            max_step_s=1200,
            max_gap_s=1800,
            level="L1",
        )
    with pytest.raises(ValueError):
        build_episodes(
            np.array([0, 900], dtype=np.int64),
            np.array([60.0, np.nan]),
            70.0,
            min_run=2,
            max_step_s=1200,
            max_gap_s=1800,
            level="L1",
        )
    assert (
        build_episodes(
            np.array([], dtype=np.int64),
            np.array([]),
            70.0,
            min_run=2,
            max_step_s=1200,
            max_gap_s=1800,
            level="L1",
        )
        == ()
    )


def test_config_matches_protocol_file() -> None:
    cfg = LabelConfig.from_config(load_config())
    assert cfg == LabelConfig()
    assert cfg.sha256 == LabelConfig().sha256


# ---------------- loader path (missing CGM, duplicates, multiple recordings) ----------------

T0 = datetime(2021, 3, 1, 8, 0)


def _rows(spec: list[tuple[int, float | None]]) -> list[list[object]]:
    return [
        row(T0 + timedelta(minutes=m), v, diet_en=None if v is not None else "Rice 50 g")
        for m, v in spec
    ]


def test_missing_cgm_row_breaks_onset_confirmation(make_workbook: WorkbookFactory) -> None:
    spec = [(0, 100.0), (15, 65.0), (30, None), (45, 60.0), (60, 75.0), (75, 80.0)]
    lab = label_recording(load_recording(make_workbook("2001_0_20210301.xlsx", _rows(spec))), CFG)
    assert lab.l1 == ()  # 15 -> 45 is 30 min > 20 min
    assert [((e.onset_ts - lab.series.ts[0]) // 60, e.n_readings) for e in lab.l1_single] == [
        (15, 2)
    ]


@pytest.mark.parametrize("second", [65.0, 90.0])
def test_duplicate_timestamps_first_row_wins(make_workbook: WorkbookFactory, second: float) -> None:
    spec = [(0, 100.0), (15, 65.0), (15, second), (30, 60.0), (45, 75.0), (60, 80.0)]
    lab = label_recording(load_recording(make_workbook("2001_0_20210301.xlsx", _rows(spec))), CFG)
    assert [((e.onset_ts - lab.series.ts[0]) // 60, e.end_reason.value) for e in lab.l1] == [
        (15, "recovered")
    ]


def test_multiple_recordings_are_labelled_independently(make_workbook: WorkbookFactory) -> None:
    # Patient 2001: period 1 is chronologically EARLIER than period 0 (order mismatch).
    a_spec = [(m, 100.0) for m in range(0, 301, 15)] + [(315, 66.0), (330, 64.0)]
    b_spec = [(0, 65.0), (15, 62.0), (30, 80.0), (45, 85.0)] + [
        (m, 100.0) for m in range(60, 301, 15)
    ]
    a = load_recording(make_workbook("2001_1_20210301.xlsx", _rows(a_spec)))
    b_rows = [row(datetime(2021, 3, 3, 8, 0) + timedelta(minutes=m), v) for m, v in b_spec]
    b = load_recording(make_workbook("2001_0_20210303.xlsx", b_rows))
    la, lb = label_recording(a, CFG), label_recording(b, CFG)
    assert [e.end_reason.value for e in la.l1] == ["record_end"]
    assert [e.end_reason.value for e in lb.l1] == ["recovered"]
    # B's refractory and warm-up derive only from B: eligible from B-start + 120 min
    b_min = ((lb.prediction.ts - lb.series.ts[0]) // 60).tolist()
    elig = {m for m, e in zip(b_min, lb.prediction.eligible, strict=True) if e}
    assert elig == set(range(120, 241, 15))
    assert la.patient_key == lb.patient_key == "shanghai_t2dm:2001"
    # order invariance
    again = [label_recording(r, CFG) for r in (b, a)]
    assert [len(x.l1) for x in again] == [1, 1]
    assert np.array_equal(again[1].prediction.y, la.prediction.y)


# ---------------- differential tests vs the blueprint's executable specification ----------------
# Verbatim logic of HypoSense_v2_sources/audit_scripts/audit.py (lines 72-92, 133-147),
# transcribed here as an independent oracle. It is NOT production code.


def _oracle_episodes(ts, g, thr, min_run=2, max_step=20, max_gap=30):  # type: ignore[no-untyped-def]
    eps = []
    i = 0
    n = len(g)
    while i < n:
        if g[i] < thr:
            run_ok = True
            for k in range(1, min_run):
                if (
                    i + k >= n
                    or not (g[i + k] < thr)
                    or (ts[i + k] - ts[i + k - 1]) > max_step * 60
                ):
                    run_ok = False
                    break
            if run_ok:
                j = i + 1
                end = None
                reason = "record_end"
                while j < n:
                    if (ts[j] - ts[j - 1]) > max_gap * 60:
                        end = j
                        reason = "gap"
                        break
                    if (
                        g[j] >= thr
                        and j + 1 < n
                        and g[j + 1] >= thr
                        and (ts[j + 1] - ts[j]) <= max_step * 60
                    ):
                        end = j
                        reason = "recovered"
                        break
                    j += 1
                eps.append((i, end, reason))
                i = end if end is not None else n
                continue
        i += 1
    return eps


def _oracle_eligibility(ts, g):  # type: ignore[no-untyped-def]
    e1 = _oracle_episodes(ts, g, 70)
    in_ep = np.zeros(len(g), bool)
    refr = np.zeros(len(g), bool)
    onset_ts = []
    for a, b, _ in e1:
        bb = b if b is not None else len(g)
        in_ep[a:bb] = True
        onset_ts.append(ts[a])
        if b is not None:
            refr |= (ts >= ts[b]) & (ts < ts[b] + 3600)
    onset_ts = np.array(onset_ts)
    elig, pos = [], []
    for k in range(len(g)):
        if g[k] < 70 or in_ep[k] or refr[k]:
            elig.append(False)
            pos.append(False)
            continue
        hist = (ts[k] - ts[0]) >= 7200 and np.sum((ts <= ts[k]) & (ts > ts[k] - 7200)) >= 7
        nxt = onset_ts[(onset_ts > ts[k]) & (onset_ts <= ts[k] + 3600)] if len(onset_ts) else []
        follow = (ts[-1] - ts[k]) >= 3600 or len(nxt) > 0
        ok = bool(hist and follow)
        elig.append(ok)
        pos.append(ok and len(nxt) > 0)
    return np.array(elig), np.array(pos)


@st.composite
def traces(draw):  # type: ignore[no-untyped-def]
    n = draw(st.integers(min_value=0, max_value=60))
    steps = draw(
        st.lists(
            st.sampled_from([5, 10, 14, 15, 15, 15, 15, 16, 20, 21, 25, 30, 31, 45, 130]),
            min_size=n,
            max_size=n,
        )
    )
    vals = draw(
        st.lists(
            st.sampled_from(
                [39.6, 50.4, 52.2, 54.0, 55.8, 66.6, 68.4, 70.0, 70.2, 72.0, 90.0, 120.0]
            ),
            min_size=n,
            max_size=n,
        )
    )
    ts = (
        np.cumsum(np.array([0, *steps[1:]], dtype=np.int64) * 60) + BASE
        if n
        else np.array([], dtype=np.int64)
    )
    return ts.astype(np.int64), np.array(vals, dtype=np.float64)


@settings(max_examples=400, deadline=None)
@given(traces())
def test_episodes_match_executable_spec(tr) -> None:  # type: ignore[no-untyped-def]
    ts, g = tr
    for thr, min_run, level in ((70.0, 2, "L1"), (54.0, 2, "L2"), (70.0, 1, "L1_single")):
        ours = [
            (
                e.onset_index,
                None if e.end_reason.value == "record_end" else e.end_index,
                e.end_reason.value,
            )
            for e in _episodes(ts, g, thr, min_run, level)
        ]
        assert ours == _oracle_episodes(ts, g, thr, min_run=min_run)


@settings(max_examples=400, deadline=None)
@given(traces())
def test_eligibility_matches_executable_spec(tr) -> None:  # type: ignore[no-untyped-def]
    ts, g = tr
    eps = _episodes(ts, g, 70.0, 2, "L1")
    lab = build_prediction_labels(ts, g, eps, CFG)
    elig, pos = _oracle_eligibility(ts, g)
    assert np.array_equal(lab.eligible, elig)
    assert np.array_equal(lab.eligible & (lab.y == 1), pos)
