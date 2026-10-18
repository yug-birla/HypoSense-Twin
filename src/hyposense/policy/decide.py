"""Deterministic decision policy core (Blueprint Table 14.1; approved P-C1, ANALYSIS_PLAN §1;
P-C8b). The SAME functions run live (S7) and in the offline policy replay that defines every
endpoint (ANALYSIS_PLAN §2). The policy never imports model code.

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

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> PolicyRules:
        return cls(
            low_mgdl=float(cfg["event"]["threshold_mgdl"]),
            post_episode_s=int(cfg["event"]["refractory_min"]) * 60,
            cooldown_s=int(cfg["policy"]["cooldown_min"]) * 60,
        )


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
