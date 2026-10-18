"""Deterministic decision policy core (Blueprint Table 14.1; approved P-C1, ANALYSIS_PLAN §1;
P-C8b). `gate` is shared verbatim by the live service (S7) and the offline policy replay that
defines every endpoint (ANALYSIS_PLAN §2). The offline harness applies `passes` and the cooldown
in vectorised form (`evaluation.metrics.passes`, `notification_indices`); their equivalence with
`classify` / `should_notify` is asserted by tests and by the measured S7 live/offline parity.
The policy never imports model code.

Rules, evaluated top to bottom at a CGM reading t (the state must be at that reading):
1. SYSTEM ERROR: the state carries an error tag.
2. LOW NOW: CGM(t) < 70 mg/dL, whatever the sufficiency flags (P-C1). Sufficiency reasons are
   attached as tags (SENSOR_FLOOR, RAPID_CHANGE, AFTER_GAP, WARM_UP, SENSOR_FAULT_SUSPECTED).
3. INSUFFICIENT DATA: no reading at t, or a reading >= 70 that fails sufficiency (gap > 20 min,
   < 7 readings in (t - 120 min, t], warm-up, rapid change).
4. LOW NOW: t is inside a causally confirmed L1 episode, or < 60 min after one ended
   (Table 14.1 priority 3).
5. Otherwise a forecast is requested. Its score decides ALERT / WATCH / NO ALERT (`classify`).

Notification: an ALERT at t notifies iff no notification was issued in the previous 60 min,
i.e. t - last_notification >= 3600 s (Section 14.3; the executable spec uses the same >=).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from hyposense.state.patient import PatientState


class PolicyState(StrEnum):
    SYSTEM_ERROR = "SYSTEM_ERROR"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    LOW_NOW = "LOW_NOW"
    ALERT = "ALERT"
    WATCH = "WATCH"
    NO_ALERT = "NO_ALERT"


@dataclass(frozen=True)
class PolicyRules:
    low_mgdl: float = 70.0
    post_episode_s: int = 3600  # LOW NOW for < 60 min after an episode ended
    cooldown_s: int = 3600
    max_gap_s: int = 1200  # no reading for > 20 min: the last decision is no longer current

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> PolicyRules:
        return cls(
            low_mgdl=float(cfg["event"]["threshold_mgdl"]),
            post_episode_s=int(cfg["event"]["refractory_min"]) * 60,
            cooldown_s=int(cfg["policy"]["cooldown_min"]) * 60,
            max_gap_s=int(cfg["policy"]["max_gap_min"]) * 60,
        )


@dataclass(frozen=True)
class Thresholds:
    """Frozen operating thresholds of a deployed model (ANALYSIS_PLAN §3.5-3.6; policy.json).
    Learned models alert at p >= tau (non-strict)."""

    tau_alert: float
    tau_watch: float | None
    strict: bool = False

    def __post_init__(self) -> None:
        if not math.isfinite(self.tau_alert):
            raise ValueError("tau_alert must be finite")
        if self.tau_watch is not None and not self.tau_watch >= 0.0:
            raise ValueError("tau_watch must be >= 0")
        if self.tau_watch is not None and not self.tau_watch <= self.tau_alert:
            raise ValueError("tau_watch must be <= tau_alert (ANALYSIS_PLAN §3.6)")


@dataclass(frozen=True)
class PolicyDecision:
    """One decision at a CGM reading (Blueprint Table 25.1). `reasons` say why the state was
    reached; `tags` are uncertainty qualifiers that NEVER change the state (§14.3)."""

    ts: int
    state: PolicyState
    p: float | None
    reasons: tuple[str, ...]
    tags: tuple[str, ...] = ()
    notify: bool = False

    def __post_init__(self) -> None:
        if self.notify and self.state is not PolicyState.ALERT:
            raise ValueError("notify implies ALERT (Table 25.1 invariant)")
        if self.p is not None and self.state not in FORECAST_STATES:
            raise ValueError(f"{self.state} carries no probability (Table 14.1)")


@dataclass(frozen=True)
class Gate:
    """The model-independent part of a decision. state None = a forecast is requested."""

    state: PolicyState | None
    tags: tuple[str, ...] = ()

    @property
    def queries_model(self) -> bool:
        return self.state is None


def gate(s: PatientState, rules: PolicyRules) -> Gate:
    if s.error is not None:
        return Gate(PolicyState.SYSTEM_ERROR, ("STATE_ERROR",))
    if not s.at_cgm_reading or s.quality is None:
        return Gate(PolicyState.INSUFFICIENT_DATA, ("NO_READING",))
    g = float(s.cgm.series.values[-1])
    q = s.quality
    if g < rules.low_mgdl:
        return Gate(PolicyState.LOW_NOW, ("CGM_LOW", *q.reasons))
    if not q.sufficient:
        return Gate(PolicyState.INSUFFICIENT_DATA, q.reasons)
    tr = s.cgm.tracker
    t = int(s.cgm.series.ts[-1])
    if tr.in_episode:
        return Gate(PolicyState.LOW_NOW, ("IN_EPISODE",))
    if tr.last_end_ts is not None and t - tr.last_end_ts < rules.post_episode_s:
        return Gate(PolicyState.LOW_NOW, ("RECENT_EPISODE",))
    return Gate(None)


def passes(score: float, tau: float, strict: bool) -> bool:
    """Score orientation (ANALYSIS_PLAN §3.1): higher = riskier. Learned models alert at
    score >= tau; M0 at score > tau (its rule is projection < theta). NaN never alerts."""
    if math.isnan(score):
        return False
    return score > tau if strict else score >= tau


def classify(score: float, tau_alert: float, tau_watch: float | None, strict: bool) -> PolicyState:
    """A requested forecast that is undefined (NaN, e.g. M0 with < 3 readings in 35 min) is
    INSUFFICIENT DATA, never NO ALERT: low risk and no information are different states
    (CLAUDE.md §17). In the offline replay a NaN score likewise never alerts."""
    if math.isnan(score):
        return PolicyState.INSUFFICIENT_DATA
    if passes(score, tau_alert, strict):
        return PolicyState.ALERT
    if tau_watch is not None and passes(score, tau_watch, strict):
        return PolicyState.WATCH
    return PolicyState.NO_ALERT


def should_notify(
    state: PolicyState, t: int, last_notification_ts: int | None, rules: PolicyRules
) -> bool:
    return state is PolicyState.ALERT and (
        last_notification_ts is None or t - last_notification_ts >= rules.cooldown_s
    )


FORECAST_STATES = frozenset({PolicyState.ALERT, PolicyState.WATCH, PolicyState.NO_ALERT})


def system_error(t: int, reason: str) -> PolicyDecision:
    return PolicyDecision(t, PolicyState.SYSTEM_ERROR, None, (reason,))


def decide(
    g: Gate,
    p: float | None,
    t: int,
    last_notification_ts: int | None,
    rules: PolicyRules,
    th: Thresholds,
    tags: tuple[str, ...] = (),
) -> PolicyDecision:
    """Table 14.1 for one reading: the gate, then the calibrated probability. Never raises: any
    failure, and any malformed inference response (None, NaN, outside [0, 1]) while a forecast
    is requested, is SYSTEM ERROR. Tags qualify forecast states only and never change them."""
    try:
        if g.state is not None:
            return PolicyDecision(t, g.state, None, g.tags)
        if p is None or not isinstance(p, float) or not 0.0 <= p <= 1.0:
            return system_error(t, "MALFORMED_INFERENCE")
        state = classify(p, th.tau_alert, th.tau_watch, th.strict)
        reason = {
            PolicyState.ALERT: "P_AT_OR_ABOVE_TAU_ALERT",
            PolicyState.WATCH: "P_AT_OR_ABOVE_TAU_WATCH",
            PolicyState.NO_ALERT: "P_BELOW_TAU_WATCH",
        }[state]
        notify = should_notify(state, t, last_notification_ts, rules)
        return PolicyDecision(t, state, p, (reason,), tuple(sorted(set(tags))), notify)
    except Exception:  # pragma: no cover - defensive: decide() must never raise
        return system_error(t, "POLICY_EXCEPTION")


def current(d: PolicyDecision, now: int, rules: PolicyRules) -> PolicyDecision:
    """The decision as displayed at clock time `now`. With no reading for more than the
    sufficiency gap (Table 14.1 priority 2: "no reading at t"), the last decision is not
    current: INSUFFICIENT DATA, no probability. A stale prediction is never shown as current."""
    if d.state is PolicyState.SYSTEM_ERROR or now - d.ts <= rules.max_gap_s:
        return d
    return PolicyDecision(now, PolicyState.INSUFFICIENT_DATA, None, ("NO_RECENT_READING",))
