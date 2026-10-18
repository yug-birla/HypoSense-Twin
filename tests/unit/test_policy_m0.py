"""Policy gate (Table 14.1 + P-C1) and M0 trend rule tests. All data SYNTHETIC."""

from __future__ import annotations

import math

import pytest

from hyposense.features.cgm import CGMFeatureConfig
from hyposense.models.m0 import M0Scorer, projection, theta_to_tau
from hyposense.policy.decide import (
    PolicyRules,
    PolicyState,
    classify,
    gate,
    passes,
    should_notify,
)
from tests.unit.state_helpers import CFG, cgm, run, steady

RULES = PolicyRules.from_config(CFG)
C = CGMFeatureConfig.from_config(CFG)
M0 = M0Scorer(C)


def last(points):  # type: ignore[no-untyped-def]
    return run(cgm(points))[-1]


# ---------------------------------------------------------------- policy gate
def test_gate_requests_a_forecast_when_sufficient_and_not_low() -> None:
    g = gate(last(steady(0, 150)), RULES)
    assert g.queries_model and g.state is None


def test_low_reading_is_low_now_even_when_insufficient_p_c1() -> None:
    g = gate(last([*steady(0, 60), (75, 64.8)]), RULES)  # warm-up AND low
    assert g.state is PolicyState.LOW_NOW and "CGM_LOW" in g.tags and "WARM_UP" in g.tags


def test_insufficient_only_for_non_low_readings() -> None:
    g = gate(last([*steady(0, 150), (185, 120.0)]), RULES)  # 35-min gap
    assert g.state is PolicyState.INSUFFICIENT_DATA and "AFTER_GAP" in g.tags
    assert gate(last(steady(0, 60)), RULES).state is PolicyState.INSUFFICIENT_DATA  # warm-up


def test_in_episode_and_recent_episode_are_low_now() -> None:
    base = [*steady(0, 150), (165, 64.8), (180, 63.0)]  # onset at 165, confirmed at 180
    g = gate(last([*base, (195, 72.0)]), RULES)  # >= 70 but the episode has not ended
    assert g.state is PolicyState.LOW_NOW and g.tags == ("IN_EPISODE",)
    # recovery pair 195, 210 -> episode ends at 195 (confirmed at 210); <60 min after -> LOW NOW
    g = gate(last([*base, (195, 72.0), (210, 75.6), (225, 80.0)]), RULES)
    assert g.state is PolicyState.LOW_NOW and g.tags == ("RECENT_EPISODE",)
    pts = [*base, *steady(195, 255, 90.0)]  # 255 - 195 = 60 min after the end -> forecast
    assert gate(last(pts), RULES).queries_model


def test_classify_and_cooldown() -> None:
    assert classify(0.5, 0.5, 0.2, strict=False) is PolicyState.ALERT
    assert classify(0.5, 0.5, 0.2, strict=True) is PolicyState.WATCH  # M0 strict comparator
    assert classify(0.1, 0.5, 0.2, strict=False) is PolicyState.NO_ALERT
    assert classify(math.nan, 0.5, 0.2, strict=False) is PolicyState.INSUFFICIENT_DATA
    assert should_notify(PolicyState.ALERT, 3600, 0, RULES)  # exactly 60 min: allowed
    assert not should_notify(PolicyState.ALERT, 3599, 0, RULES)
    assert not should_notify(PolicyState.WATCH, 9999, None, RULES)


# ---------------------------------------------------------------- M0
def test_m0_flat_falling_rising() -> None:
    flat = last([(0, 100.0), (15, 100.0), (30, 100.0)])
    assert projection(flat, C) == 100.0 and M0(flat) == -100.0
    fall = last([(0, 130.0), (15, 115.0), (30, 100.0)])  # -1 mg/dL/min
    assert projection(fall, C) == pytest.approx(40.0)
    rise = last([(0, 70.0), (15, 85.0), (30, 100.0)])
    assert projection(rise, C) == pytest.approx(160.0)


def test_m0_minimum_history_and_strict_threshold() -> None:
    two = last([(10, 130.0), (30, 100.0)])  # only 2 readings in (t - 35, t]
    assert math.isnan(projection(two, C)) and math.isnan(M0(two))
    assert not passes(M0(two), theta_to_tau(80.0), strict=True)  # undefined never alerts
    fall = last([(0, 130.0), (15, 115.0), (30, 100.0)])  # projection exactly 40
    assert passes(M0(fall), theta_to_tau(45.0), strict=True)  # 40 < 45 -> ALERT
    assert not passes(M0(fall), theta_to_tau(40.0), strict=True)  # 40 < 40 is false


def test_exact_tie_at_theta_on_the_data_grid_never_alerts() -> None:
    """S5 finding (ADR-036). 45 mg/dL lies on the data grid, so a projection can be exactly 45.
    It must come out as exactly 45.0, not 45 +/- 1e-14, so the strict rule resolves the tie (no
    alert); and mathematically equal projections are bitwise equal (ties switch together).
    With 3 equally spaced readings the projection is 3 y3 - 2 y1 (exact by hand)."""
    at45 = last([(0, 85.5), (15, 79.2), (30, 72.0)])  # 216 - 171 = 45
    assert projection(at45, C) == 45.0
    assert not passes(M0(at45), theta_to_tau(45.0), strict=True)  # 45 < 45 is false
    assert passes(M0(at45), theta_to_tau(45.1), strict=True)
    a = last([(0, 88.2), (15, 79.2), (30, 75.6)])  # 226.8 - 176.4 = 50.4
    b = last([(0, 82.8), (15, 77.4), (30, 72.0)])  # 216 - 165.6 = 50.4
    assert projection(a, C) == projection(b, C) == 50.4
    c = last([(0, 99.9), (15, 86.4), (30, 72.9)])  # 218.7 - 199.8 = 18.9
    assert projection(c, C) == 18.9
    d = last([(0, 78.1), (15, 65.0), (30, 70.0)])  # 210 - 156.2 = 53.8
    assert projection(d, C) == 53.8  # the former float-sum version gave 53.80000000000001
