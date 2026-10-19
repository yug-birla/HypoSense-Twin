"""S7 policy: decide() over Table 14.1, boundaries, cooldown and persistence, tags, malformed
inference, staleness, invariants and display texts. All data SYNTHETIC."""

from __future__ import annotations

import math
import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from hyposense.policy import messages
from hyposense.policy.decide import (
    Gate,
    PolicyDecision,
    PolicyRules,
    PolicyState,
    Thresholds,
    current,
    decide,
    gate,
)
from tests.unit.state_helpers import CFG, cgm, run, steady

RULES = PolicyRules.from_config(CFG)
TH = Thresholds(0.5, 0.2)
FORECAST = Gate(None)
TAGS = ("MED_TIMING_UNKNOWN:insulin", "MED_TIMING_UNKNOWN:sulfonylurea", "EVENT_REJECTED")


def test_rules_come_from_configuration() -> None:
    assert PolicyRules(70.0, 3600, 3600, 1200) == RULES


def test_non_forecast_states_carry_no_probability_and_never_notify() -> None:
    for st_ in (PolicyState.LOW_NOW, PolicyState.INSUFFICIENT_DATA, PolicyState.SYSTEM_ERROR):
        d = decide(Gate(st_, ("X",)), 0.99, 100, None, RULES, TH, TAGS)
        assert d.state is st_ and d.p is None and not d.notify and d.reasons == ("X",)
        assert d.tags == ()  # tags qualify forecast states only (Table 14.1)


def test_threshold_boundaries_are_inclusive() -> None:
    assert decide(FORECAST, 0.5, 0, None, RULES, TH).state is PolicyState.ALERT  # p = tau_A
    assert decide(FORECAST, math.nextafter(0.5, 0), 0, None, RULES, TH).state is PolicyState.WATCH
    assert decide(FORECAST, 0.2, 0, None, RULES, TH).state is PolicyState.WATCH  # p = tau_W
    below = math.nextafter(0.2, 0)
    assert decide(FORECAST, below, 0, None, RULES, TH).state is PolicyState.NO_ALERT
    no_watch = Thresholds(0.5, None)
    assert decide(FORECAST, 0.3, 0, None, RULES, no_watch).state is PolicyState.NO_ALERT


def test_cooldown_and_alert_persistence() -> None:
    a = decide(FORECAST, 0.9, 0, None, RULES, TH)
    assert a.state is PolicyState.ALERT and a.notify
    b = decide(FORECAST, 0.9, 3599, 0, RULES, TH)
    assert b.state is PolicyState.ALERT and not b.notify  # ALERT stays visible in cooldown
    assert decide(FORECAST, 0.9, 3600, 0, RULES, TH).notify  # exactly 60 min
    assert not decide(FORECAST, 0.3, 9999, 0, RULES, TH).notify  # WATCH never notifies


@given(
    p=st.floats(0.0, 1.0),
    last=st.one_of(st.none(), st.integers(-10_000, 10_000)),
    tags=st.lists(st.sampled_from(TAGS), max_size=3),
)
def test_tags_never_change_state_or_notification(
    p: float, last: int | None, tags: list[str]
) -> None:
    plain = decide(FORECAST, p, 10_000, last, RULES, TH)
    tagged = decide(FORECAST, p, 10_000, last, RULES, TH, tuple(tags))
    assert (tagged.state, tagged.p, tagged.notify) == (plain.state, plain.p, plain.notify)
    assert set(tagged.tags) == set(tags)


@pytest.mark.parametrize("p", [None, math.nan, math.inf, -0.01, 1.01])
def test_malformed_inference_is_system_error(p: float | None) -> None:
    d = decide(FORECAST, p, 5, None, RULES, TH)
    assert d.state is PolicyState.SYSTEM_ERROR and d.p is None and not d.notify
    assert d.reasons == ("MALFORMED_INFERENCE",)


def test_low_now_with_sensor_fault_is_distinguishable_p_c8b() -> None:
    pts = [*steady(0, 150), *[(165 + 15 * i, 39.6) for i in range(8)]]
    s = run(cgm(pts))[-1]
    d = decide(gate(s, RULES), 0.0, int(s.ts or 0), None, RULES, TH)
    assert d.state is PolicyState.LOW_NOW and "SENSOR_FAULT_SUSPECTED" in d.reasons
    shown = messages.texts(d)
    assert any("SENSOR FAULT SUSPECTED" in x for x in shown)
    assert any("capillary" in x for x in shown)
    ordinary = decide(
        gate(run(cgm([*steady(0, 150), (165, 64.8)]))[-1], RULES), None, 0, None, RULES, TH
    )
    assert (
        ordinary.state is PolicyState.LOW_NOW and "SENSOR_FAULT_SUSPECTED" not in ordinary.reasons
    )


def test_stale_decision_is_never_current() -> None:
    d = decide(FORECAST, 0.9, 1000, None, RULES, TH)
    assert current(d, 1000 + 1200, RULES) is d
    late = current(d, 1000 + 1201, RULES)
    assert late.state is PolicyState.INSUFFICIENT_DATA and late.p is None
    assert late.reasons == ("NO_RECENT_READING",) and not late.notify
    err = decide(Gate(PolicyState.SYSTEM_ERROR, ("STATE_ERROR",)), None, 0, None, RULES, TH)
    assert current(err, 10**6, RULES) is err  # an error is not hidden by staleness


def test_decision_and_threshold_invariants() -> None:
    with pytest.raises(ValueError):
        PolicyDecision(0, PolicyState.WATCH, 0.3, (), (), True)  # notify implies ALERT
    with pytest.raises(ValueError):
        PolicyDecision(0, PolicyState.LOW_NOW, 0.3, ())  # no probability in LOW NOW
    with pytest.raises(ValueError):
        Thresholds(0.2, 0.5)  # tau_W > tau_A
    with pytest.raises(ValueError):
        Thresholds(math.inf, None)


def test_display_texts_are_safe_and_carry_no_treatment_advice() -> None:
    corpus = [
        messages.LABEL_CAVEAT,
        *messages.STATE_TEXT.values(),
        *messages.REASON_TEXT.values(),
        *messages.TAG_TEXT.values(),
    ]
    assert set(messages.STATE_TEXT) == set(PolicyState)
    for text in corpus:
        low = text.lower()
        assert not re.search(r"\bsafe\b", low), text  # never "safe" (§16.3, REQ P-09)
        for word in (
            "dose",
            "units",
            "inject",
            "administer",
            "insulin",
            "carbohydrate",
            "glucagon",
        ):
            assert word not in low, (word, text)


def test_probability_text_never_shows_zero_or_certainty() -> None:
    assert messages.probability_text(None) is None
    assert messages.probability_text(0.0) == "<1%"
    assert messages.probability_text(0.0099) == "<1%"
    assert messages.probability_text(0.01) == "1%"
    assert messages.probability_text(0.5) == "50%"
    assert messages.probability_text(1.0) == ">99%"
