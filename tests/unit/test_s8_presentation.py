"""S8 backend presentation: deterministic summary / reason / trend templates, static export path
mapping, P-C10 display mode. All data SYNTHETIC."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from hyposense.api.app import rsc_segment_path
from hyposense.models.artifact import load_artifact
from hyposense.policy.decide import PolicyDecision, PolicyState
from hyposense.policy.messages import (
    GROUP_LABEL,
    clock_text,
    reason_line,
    summary,
    trend_category,
)
from hyposense.replay.runner import Pipeline, TwinRunner
from tests.unit.artifact_helpers import synthetic_artifact
from tests.unit.state_helpers import BUILDER, CFG, ENGINE, PHARMA, cgm, med, steady, stream

OFF = 8 * 3600


def d(state: PolicyState, p: float | None = None, reasons=(), tags=()) -> PolicyDecision:  # type: ignore[no-untyped-def]
    return PolicyDecision(0, state, p, tuple(reasons), tuple(tags))


def test_summary_is_deterministic_and_omits_unavailable_values() -> None:
    alert = d(
        PolicyState.ALERT, 0.183, ("P_AT_OR_ABOVE_TAU_ALERT",), ("MED_TIMING_UNKNOWN:sulfonylurea",)
    )
    s = summary(alert, 6 * 3600 + 15 * 60, ["G1_cgm_level", "G8_medication_exposure"], OFF)
    assert s == (
        "ALERT since 14:15 · estimated risk 18% · main associated factors: glucose level and "
        "estimated medicine activity · medication timing unknown (sulfonylurea)"
    )
    assert summary(alert, 0, [], OFF) == summary(alert, 0, [], OFF)  # deterministic
    low = summary(d(PolicyState.LOW_NOW, None, ("CGM_LOW",)), None, [], OFF)
    assert low == "LOW NOW · verify with capillary glucose"  # no risk, no time: omitted
    fault = summary(
        d(PolicyState.LOW_NOW, None, ("CGM_LOW", "SENSOR_FAULT_SUSPECTED")), None, [], OFF
    )
    assert "sensor fault suspected" in fault
    for text in (s, low, fault):
        assert "safe" not in text.lower().split() and "dose" not in text.lower()


def test_reason_line_names_associations_never_causes() -> None:
    w = d(PolicyState.WATCH, 0.05, ("P_AT_OR_ABOVE_TAU_WATCH",))
    assert (
        reason_line(w, ["G1_cgm_level", "G3_cgm_history", "G4_time"])
        == "Elevated risk; most associated with glucose level and recent glucose history"
    )
    assert reason_line(w, []) == "At or above the WATCH threshold"
    assert (
        reason_line(d(PolicyState.NO_ALERT, 0.001), [])
        == "Estimated risk below the watch threshold"
    )
    assert "Sensor fault" in reason_line(
        d(PolicyState.LOW_NOW, None, ("CGM_LOW", "SENSOR_FAULT_SUSPECTED")), []
    )
    assert (
        reason_line(d(PolicyState.INSUFFICIENT_DATA, None, ("WARM_UP",)), [])
        == "Sensor warm-up period"
    )
    assert set(GROUP_LABEL) >= {"G1_cgm_level", "G8_medication_exposure"}


@pytest.mark.parametrize(
    ("rate", "cat"),
    [
        (None, None),
        (math.nan, None),
        (0.0, "steady"),
        (0.99, "steady"),
        (1.0, "rising"),
        (-1.5, "falling"),
        (2.0, "rising_fast"),
        (-3.0, "falling_fast"),
    ],
)
def test_trend_category(rate: float | None, cat: str | None) -> None:
    assert trend_category(rate) == cat


def test_clock_text_uses_the_record_clock() -> None:
    assert clock_text(0, OFF) == "08:00"
    assert clock_text(16 * 3600 + 59, OFF) == "00:00"


def test_static_export_segment_mapping_is_narrow_and_traversal_safe() -> None:
    assert (
        rsc_segment_path("evidence/__next.evidence.__PAGE__.txt")
        == "evidence/__next.evidence/__PAGE__.txt"
    )
    assert (
        rsc_segment_path("evidence\\__next.evidence.__PAGE__.txt")
        == "evidence/__next.evidence/__PAGE__.txt"
    )
    for bad in (
        "__next.__PAGE__.txt",
        "x/__next.a..b.txt",
        "../__next.a.b.txt",
        "a/__next.a.b.c.txt",
        "index.html",
    ):
        assert rsc_segment_path(bad) is None


def test_pc10_badge_mode_keeps_the_clinical_state(tmp_path: Path) -> None:
    """P-C10 option (b) development setting: a rejected dose leaves no SYSTEM_ERROR record."""
    model = load_artifact(synthetic_artifact(tmp_path / "a"), CFG, PHARMA)
    evs = [*cgm(steady(0, 300))]
    st = stream(evs)
    bad = med("gliclazide 30mg", "oral_agents", 100)[0]
    import dataclasses

    late = dataclasses.replace(bad, ts=st.events[0].ts - 60)  # out of order -> rejected
    for mode, expect_error in ((True, 1), (False, 0)):
        r = TwinRunner(st, Pipeline(ENGINE, BUILDER, model, reject_non_cgm_as_error=mode))
        for j, e in enumerate([*st.events[:10], late, *st.events[10:]]):
            r.feed(j, e)
        errors = [x for x in r.decisions if x.decision.state is PolicyState.SYSTEM_ERROR]
        assert len(errors) == expect_error and len(r.rejected) == 1
        assert r.rejected[0]["at"] is not None
