"""Pre-freeze final resolution (DEC-2026-10-19-M): P-C7 post-gap sufficiency (policy only),
P-C10 rejected auxiliary input, canonical floored calibrator and artefact fail-closed checks,
LOW_CONFIDENCE removal. All data SYNTHETIC."""

from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from hyposense.calibration.methods import fit
from hyposense.common.hashing import sha256_bytes
from hyposense.evaluation.data import GATE_CODES, replay_decisions
from hyposense.labels.config import LabelConfig
from hyposense.models.artifact import (
    ArtifactIncompatible,
    RuntimeModel,
    load_artifact,
    write_artifact,
)
from hyposense.policy.decide import PolicyRules, PolicyState, Thresholds, decide, gate
from hyposense.replay.runner import Pipeline, TwinRunner
from hyposense.state.events import CBGReading, MealEvent
from tests.unit.artifact_helpers import synthetic_artifact
from tests.unit.state_helpers import (
    BUILDER,
    CFG,
    ENGINE,
    PHARMA,
    RK,
    T0,
    cgm,
    med,
    run,
    steady,
    stream,
)

RULES = PolicyRules.from_config(CFG)


# ---------------------------------------------------------------- P-C7
def _after_gap(gap_min: float, n_after: int, value: float = 120.0) -> list[Any]:
    pts = steady(0, 300, value)
    start = 300 + gap_min
    pts += [(start + 15 * i, value) for i in range(n_after)]
    return run(cgm(pts))


def test_pc7_is_policy_only_labels_unchanged() -> None:
    assert ENGINE.sufficiency.warmup_restart_after_gap_s == 120 * 60
    assert LabelConfig.from_config(CFG).warmup_restart_after_gap_s is None


def test_pc7_gap_exactly_at_boundary_does_not_restart() -> None:
    s = _after_gap(120, 9)
    first = s[len(steady(0, 300))]
    assert first.quality is not None and not first.quality.warmup  # anchor = recording start
    assert gate(s[-1], RULES).queries_model  # 9 post-gap readings span 120 min: forecast allowed


def test_pc7_gap_above_boundary_restarts_warmup() -> None:
    s = _after_gap(121, 9)
    first = s[len(steady(0, 300))]
    assert first.quality is not None and first.quality.warmup
    assert first.quality.warmup_anchor_ts == first.ts  # re-anchored at the first post-gap reading
    g = gate(first, RULES)
    assert g.state is PolicyState.INSUFFICIENT_DATA and "WARM_UP" in g.tags


def test_pc7_insufficient_until_requirements_are_re_earned_then_restored() -> None:
    s = _after_gap(180, 10)
    post = s[len(steady(0, 300)) :]
    # 105 min after the gap: 8 readings (history ok) but warm-up not over -> no forecast
    assert gate(post[7], RULES).state is PolicyState.INSUFFICIENT_DATA
    assert "WARM_UP" in gate(post[7], RULES).tags
    # 120 min after the gap: warm-up over and >= 7 readings -> forecast restored
    assert gate(post[8], RULES).queries_model


def test_pc7_alert_not_permitted_without_history_but_low_now_is() -> None:
    s = _after_gap(180, 3)
    g = gate(s[-1], RULES)
    d = decide(g, 0.99, int(s[-1].ts or 0), None, RULES, Thresholds(0.5, 0.2))
    assert d.state is PolicyState.INSUFFICIENT_DATA and d.p is None and not d.notify
    low_states = run(cgm([*steady(0, 300), (480, 120.0), (495, 64.8)]))
    g_low = gate(low_states[-1], RULES)
    assert g_low.state is PolicyState.LOW_NOW and "WARM_UP" in g_low.tags  # P-C1 precedence


def test_pc7_offline_replay_and_live_runner_agree_across_long_gap(tmp_path: Path) -> None:
    model = load_artifact(
        synthetic_artifact(tmp_path / "a", tau_alert=0.3, tau_watch=0.1), CFG, PHARMA
    )
    pts = [*steady(0, 300), *[(450 + 15 * i, 120.0 - 3 * i) for i in range(14)]]
    st = stream(cgm(pts))
    ts, codes, _ = replay_decisions(st, ENGINE, RULES, {})
    r = TwinRunner(st, Pipeline(ENGINE, BUILDER, model))
    for j, e in enumerate(st.events):
        r.feed(j, e)
    assert [x.decision.ts for x in r.decisions] == ts.tolist()
    for k, x in enumerate(r.decisions):
        if x.decision.p is None:
            assert GATE_CODES[x.decision.state] == codes[k]
        else:
            assert codes[k] == GATE_CODES[None]
    post = [x for x in r.decisions if x.decision.ts >= T0 + 450 * 60]
    assert post[0].decision.state is PolicyState.INSUFFICIENT_DATA  # warm-up after the gap


# ---------------------------------------------------------------- P-C10
@pytest.fixture(scope="module")
def model(tmp_path_factory: pytest.TempPathFactory) -> RuntimeModel:
    d = synthetic_artifact(tmp_path_factory.mktemp("art") / "M1", tau_alert=0.3, tau_watch=0.1)
    return load_artifact(d, CFG, PHARMA)


def _trace() -> list[tuple[float, float]]:
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


def _bad(kind: str, at_ts: int) -> Any:
    if kind == "dose":  # out of order (back-dated)
        return dataclasses.replace(med("gliclazide 30mg", "oral_agents", 100)[0], ts=T0 + 60)
    if kind == "meal":  # out of order
        return MealEvent(RK, T0 + 60, 9100, True)
    if kind == "cbg":  # implausible capillary value
        return CBGReading(RK, at_ts + 5, 5000.0, 9200)
    raise ValueError(kind)


@pytest.mark.parametrize(
    ("state", "kind"),
    [
        (PolicyState.NO_ALERT, "dose"),
        (PolicyState.ALERT, "dose"),
        (PolicyState.LOW_NOW, "meal"),
        (PolicyState.WATCH, "cbg"),
    ],
)
def test_pc10_rejected_auxiliary_event_keeps_clinical_state(
    model: RuntimeModel, state: PolicyState, kind: str
) -> None:
    st = stream(cgm(_trace()))
    clean = TwinRunner(st, Pipeline(ENGINE, BUILDER, model))
    for j, e in enumerate(st.events):
        clean.feed(j, e)
    k = next(i for i, x in enumerate(clean.decisions) if x.decision.state is state)
    r = TwinRunner(st, Pipeline(ENGINE, BUILDER, model))
    for j, e in enumerate(st.events[: k + 1]):
        r.feed(j, e)
    before = r.current
    assert before is not None and before.decision.state is state
    out = r.feed(10_000, _bad(kind, before.decision.ts))
    assert out is None  # no SYSTEM_ERROR record
    assert r.current is before and r.current.decision.state is state  # state kept
    assert len(r.rejected) == 1 and r.rejected[0]["event"] != "CGMReading"  # logged
    assert r.rejected_until is not None  # EVENT_REJECTED tag window
    for j, e in enumerate(st.events[k + 1 :], start=k + 1):  # later valid events succeed
        r.feed(j, e)
    later = {x.decision.ts: (x.decision.state, x.decision.p) for x in r.decisions}
    ref = {x.decision.ts: (x.decision.state, x.decision.p) for x in clean.decisions}
    assert later == ref
    assert not any(x.decision.state is PolicyState.SYSTEM_ERROR for x in r.decisions)


def test_pc10_input_rejected_badge_is_shown(model: RuntimeModel, tmp_path: Path) -> None:
    from hyposense.api.service import Service

    rk2 = RK
    st = stream(cgm(_trace()))
    svc = Service(model.directory, [st], log_root=tmp_path / "logs")
    svc.select([rk2])
    svc.step(40)
    r = svc._require().runners[0]
    r.feed(10_000, _bad("cbg", r.state.ts or T0))
    bed = svc.ward().beds[0]
    assert "INPUT_REJECTED" in bed.badges and bed.decision.state != "SYSTEM_ERROR"
    assert svc.patient(rk2).input_rejected


def test_pc10_circuit_breaker_still_halts(model: RuntimeModel) -> None:
    st = stream(cgm(_trace()))
    r = TwinRunner(st, Pipeline(ENGINE, BUILDER, model, max_consecutive_errors=3))
    for j, e in enumerate(st.events[:20]):
        r.feed(j, e)
    for i in range(3):
        r.feed(100 + i, _bad("meal", 0))
    assert r.halted and r.current is not None
    assert r.current.decision.state is PolicyState.SYSTEM_ERROR
    assert r.current.decision.reasons == ("RUNNER_HALTED",)
    assert r.feed(200, st.events[20]) is None


def test_pc10_rejected_cgm_is_still_system_error(model: RuntimeModel) -> None:
    st = stream(cgm(_trace()))
    r = TwinRunner(st, Pipeline(ENGINE, BUILDER, model))
    for j, e in enumerate(st.events[:30]):
        r.feed(j, e)
    bad = dataclasses.replace(st.events[29], ts=st.events[29].ts + 7, value_mgdl=math.nan)
    rec = r.feed(999, bad)
    assert rec is not None and rec.decision.state is PolicyState.SYSTEM_ERROR


# ---------------------------------------------------------------- calibrator + artefact
def _data(seed: int = 3) -> tuple[Any, Any]:
    rng = np.random.default_rng(seed)
    p = rng.uniform(0, 1, 5000)
    y = (rng.uniform(0, 1, 5000) < p**5).astype(np.int64)
    return p, y


def test_floored_calibrator_bounds_monotone_deterministic() -> None:
    p, y = _data()
    a, b = fit("isotonic_interp_floored", p, y), fit("isotonic_interp_floored", p, y)
    assert a.params == b.params  # deterministic p_lo and knots
    lo = a.params["p_lo"]
    grid = np.linspace(-1, 2, 5001)
    out = a.apply(grid)
    assert np.all(np.diff(out) >= 0) and out.min() >= lo > 0 and out.max() <= 1 - lo < 1
    assert not np.any(out == 0.0) and not np.any(out == 1.0)
    base = fit("isotonic_interp", p, y).apply(grid)
    inside = (base > lo) & (base < 1 - lo)
    assert np.array_equal(out[inside], base[inside])  # unchanged where not clamped
    # operating behaviour unchanged for any threshold above the floor
    for tau in (0.05, 0.1, 0.3, 0.7):
        assert np.array_equal(out >= tau, base >= tau)


def test_floored_calibrator_survives_artifact_roundtrip(tmp_path: Path) -> None:
    d = synthetic_artifact(tmp_path / "a")
    m = load_artifact(d, CFG, PHARMA)
    cal = json.loads((d / "calibrator.json").read_text("utf-8"))
    assert cal["method"] == m.calibrator.method == "isotonic_interp_floored"
    assert cal["params"] == m.calibrator.params
    man = json.loads((d / "manifest.json").read_text("utf-8"))
    assert man["format_version"] == "2.0.0" and set(man["files"]) == {
        "model.txt",
        "calibrator.json",
        "policy.json",
    }
    for name, h in man["files"].items():
        assert sha256_bytes((d / name).read_bytes()) == h
    assert not (d / "feature_range.json").exists()  # P-B12: removed


def test_non_canonical_calibrator_is_refused(tmp_path: Path) -> None:
    import pandas as pd

    from hyposense.features.spec import level_names
    from hyposense.models.lgbm import base_params, train

    names = level_names("M1")
    rng = np.random.default_rng(1)
    X = pd.DataFrame(rng.normal(100, 30, (400, len(names))), columns=list(names))
    y = (X["cgm"] < 90).astype(np.int64).to_numpy()
    m = train(X, y, {**base_params(CFG), "num_leaves": 4, "min_data_in_leaf": 20}, 10)
    write_artifact(
        tmp_path / "x",
        level="M1",
        model_text=m.model_text,
        calibrator=fit("isotonic_interp", m.predict(X), y),
        thresholds=Thresholds(0.5, 0.2),
        rules=RULES,
        status="DEVELOPMENT",
        cfg=CFG,
        pharma=PHARMA,
        provenance={},
    )
    with pytest.raises(ArtifactIncompatible, match="canonical"):
        load_artifact(tmp_path / "x", CFG, PHARMA)


def test_format_1_artifact_is_refused(tmp_path: Path) -> None:
    d = synthetic_artifact(tmp_path / "a")
    man = json.loads((d / "manifest.json").read_text("utf-8"))
    man["format_version"] = "1.0.0"
    (d / "manifest.json").write_text(json.dumps(man), "utf-8")
    with pytest.raises(ArtifactIncompatible):
        load_artifact(d, CFG, PHARMA)


# ---------------------------------------------------------------- P-B12 removal
def test_low_confidence_is_never_emitted(model: RuntimeModel) -> None:
    from hyposense.policy import messages

    st = stream([*cgm([(m, 400.0 if 400 < m < 700 else v) for m, v in _trace()])])
    r = TwinRunner(st, Pipeline(ENGINE, BUILDER, model))
    for j, e in enumerate(st.events):
        r.feed(j, e)
    assert not any("LOW_CONFIDENCE" in x.decision.tags for x in r.decisions)
    assert "LOW_CONFIDENCE" not in messages.TAG_TEXT
    assert not hasattr(model, "out_of_range")
