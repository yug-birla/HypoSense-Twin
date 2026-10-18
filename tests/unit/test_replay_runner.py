"""S7 runner and session: decisions at every reading, error recovery without state poisoning,
no stale prediction reuse, circuit breaker, deterministic logs and seek. All data SYNTHETIC."""

from __future__ import annotations

import dataclasses
import itertools
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from hyposense.models.artifact import RuntimeModel, load_artifact
from hyposense.policy.decide import PolicyState
from hyposense.replay.runner import Pipeline, TwinRunner
from hyposense.replay.session import DecisionLog, ReplaySession
from hyposense.state.events import CGMReading, StateEvent
from tests.unit.artifact_helpers import synthetic_artifact
from tests.unit.state_helpers import (
    BUILDER,
    CFG,
    ENGINE,
    PHARMA,
    RK,
    T0,
    cbg,
    cgm,
    context,
    meal,
    med,
    stream,
)


@pytest.fixture(scope="module")
def model(tmp_path_factory: pytest.TempPathFactory) -> RuntimeModel:
    d = synthetic_artifact(tmp_path_factory.mktemp("art") / "M1-dev", tau_alert=0.3, tau_watch=0.1)
    return load_artifact(d, CFG, PHARMA)


def trace() -> list[tuple[float, float]]:
    """24 h with two dips, so every forecast state and a LOW NOW appear."""
    pts = []
    for i in range(96):
        m = 15.0 * i
        v = (
            140.0
            - 70.0 * math.exp(-(((m - 600) / 90.0) ** 2))
            - 80.0 * math.exp(-(((m - 1100) / 60.0) ** 2))
        )
        pts.append((m, round(v / 1.8) * 1.8))
    return pts


def events() -> list[StateEvent]:
    return [
        *cgm(trace()),
        meal(300),
        cbg(610, 80.0),
        *med("gliclazide 30mg", "oral_agents", 420),
        *med("insulin aspart 8u", "insulin_sc", 470),
    ]


def run_runner(model: RuntimeModel, evs: list[StateEvent]) -> TwinRunner:
    st = stream(evs)
    r = TwinRunner(st, Pipeline(ENGINE, BUILDER, model))
    for j, e in enumerate(st.events):
        r.feed(j, e)
    r.finish()
    return r


def by_ts(r: TwinRunner) -> dict[int, tuple[Any, ...]]:
    return {
        x.decision.ts: (x.decision.state, x.decision.p, x.decision.notify, x.decision.tags)
        for x in r.decisions
        if x.decision.state is not PolicyState.SYSTEM_ERROR
    }


def test_one_decision_per_reading_with_every_state(model: RuntimeModel) -> None:
    r = run_runner(model, events())
    n_cgm = len(trace())
    assert len(r.decisions) == n_cgm and not r.rejected
    states = {x.decision.state for x in r.decisions}
    assert {PolicyState.INSUFFICIENT_DATA, PolicyState.LOW_NOW, PolicyState.NO_ALERT} <= states
    assert PolicyState.ALERT in states
    notified = [x.decision.ts for x in r.decisions if x.decision.notify]
    assert notified and all(b - a >= 3600 for a, b in itertools.pairwise(notified))
    assert r.unknown_outcomes is not None


@pytest.mark.parametrize(
    "bad",
    [
        lambda: CGMReading(RK, T0 + 600 * 60 + 7, math.nan, 9001),  # malformed value
        lambda: CGMReading(RK, T0 + 600 * 60 + 7, 1000.0, 9002),  # implausible value
        lambda: CGMReading(RK, T0 + 600 * 60, 120.0, 9003),  # duplicate reading time
        lambda: CGMReading("9999_0_20200101", T0 + 600 * 60 + 7, 120.0, 9004),  # other recording
    ],
)
def test_rejected_event_does_not_poison_later_state(model: RuntimeModel, bad: Any) -> None:
    clean = run_runner(model, events())
    st = stream(events())
    evs = list(st.events)
    k = next(i for i, e in enumerate(evs) if e.ts >= T0 + 600 * 60) + 1
    r = TwinRunner(st, Pipeline(ENGINE, BUILDER, model))
    for j, e in enumerate([*evs[:k], bad(), *evs[k:]]):
        r.feed(j, e)
    r.finish()
    errors = [x for x in r.decisions if x.decision.state is PolicyState.SYSTEM_ERROR]
    assert len(errors) == 1 and errors[0].decision.reasons == ("EVENT_REJECTED",)
    assert errors[0].decision.p is None and len(r.rejected) == 1
    assert by_ts(r) == by_ts(clean)  # identical decisions before and after the rejection
    assert r.state.digest() == clean.state.digest()


def test_out_of_order_event_is_rejected_and_recovered(model: RuntimeModel) -> None:
    clean = run_runner(model, events())
    st = stream(events())
    evs = list(st.events)
    late = CGMReading(RK, T0 + 60, 120.0, 9100)  # far in the past
    r = TwinRunner(st, Pipeline(ENGINE, BUILDER, model))
    for j, e in enumerate([*evs[:40], late, *evs[40:]]):
        r.feed(j, e)
    assert r.rejected[0]["error"] == "OutOfOrderEventError"
    assert by_ts(r) == by_ts(clean)


def test_rejected_dose_tags_later_forecasts_without_changing_them(model: RuntimeModel) -> None:
    clean = run_runner(model, events())
    st = stream(events())
    evs = list(st.events)
    k = next(i for i, e in enumerate(evs) if e.ts >= T0 + 500 * 60)
    bad = dataclasses.replace(med("gliclazide 30mg", "oral_agents", 400)[0], ts=T0 + 100 * 60)
    r = TwinRunner(st, Pipeline(ENGINE, BUILDER, model))
    for j, e in enumerate([*evs[:k], bad, *evs[k:]]):
        r.feed(j, e)
    after = [x for x in r.decisions if x.decision.p is not None and x.seq > k]
    assert after and all("EVENT_REJECTED" in x.decision.tags for x in after)
    a, b = by_ts(r), by_ts(clean)
    assert {t: v[:3] for t, v in a.items()} == {t: v[:3] for t, v in b.items()}


class _Booster:
    def __init__(self, real: Any, fail_at: int, nan: bool = False) -> None:
        self.real, self.fail_at, self.nan, self.calls = real, fail_at, nan, 0

    def predict(self, X: Any, **kw: Any) -> Any:
        self.calls += 1
        if self.calls == self.fail_at:
            if self.nan:
                return np.array([math.nan])
            raise RuntimeError("inference backend failure")
        return self.real.predict(X, **kw)


@pytest.mark.parametrize("nan", [False, True])
def test_inference_failure_is_system_error_and_never_stale(model: RuntimeModel, nan: bool) -> None:
    clean = run_runner(model, events())
    fail_at = 20
    broken = dataclasses.replace(model, booster=_Booster(model.booster, fail_at, nan))
    r = run_runner(broken, events())
    errs = [x for x in r.decisions if x.decision.state is PolicyState.SYSTEM_ERROR]
    assert len(errs) == 1 and errs[0].decision.reasons == ("INFERENCE_ERROR",)
    assert errs[0].decision.p is None and errs[0].raw is None
    t_err = errs[0].decision.ts
    assert r.current is not None
    a, b = by_ts(r), by_ts(clean)
    assert {t: v for t, v in a.items() if t != t_err} == {t: v for t, v in b.items() if t != t_err}


def test_circuit_breaker_halts_after_consecutive_rejections(model: RuntimeModel) -> None:
    st = stream(events())
    r = TwinRunner(st, Pipeline(ENGINE, BUILDER, model, max_consecutive_errors=3))
    for j, e in enumerate(st.events[:30]):
        r.feed(j, e)
    for i in range(3):
        r.feed(100 + i, CGMReading(RK, T0 + 9_000 * 60 + i, math.nan, 9200 + i))
    assert r.halted and r.current is not None
    assert r.current.decision.reasons == ("RUNNER_HALTED",)
    n = len(r.decisions)
    assert r.feed(200, st.events[30]) is None and len(r.decisions) == n  # refused


def test_session_log_is_deterministic_and_seek_equals_fresh_replay(
    model: RuntimeModel, tmp_path: Path
) -> None:
    rk2 = "9001_1_20200914"
    streams = [stream(events()), stream(cgm(trace(), rk=rk2), context(recording_key=rk2))]
    pipe = Pipeline(ENGINE, BUILDER, model)
    hashes = []
    for k in range(2):
        log = DecisionLog(tmp_path / f"s{k}", {"k": k})
        s = ReplaySession(streams, pipe, log)
        s.step(10**6)
        hashes.append(log.sha256())
        log.close()
    assert hashes[0] == hashes[1]
    # a seek back to 0 into a new segment reproduces the uninterrupted log exactly
    s = ReplaySession(streams, pipe, DecisionLog(tmp_path / "seg1", {}))
    s.advance_to(900 * 60)
    seg2 = DecisionLog(tmp_path / "seg2", {})
    s.seek(0, seg2)
    s.step(10**6)
    assert seg2.sha256() == hashes[0]
    seg2.close()
    s = ReplaySession(streams, pipe, None)
    s.advance_to(800 * 60)
    s.advance_to(1300 * 60)
    s.seek(700 * 60, None)
    fresh = ReplaySession(streams, pipe, None)
    fresh.advance_to(700 * 60)
    assert [r.state.digest() for r in s.runners] == [r.state.digest() for r in fresh.runners]
    with pytest.raises(ValueError):
        s.seek(s.duration + 1, None)
