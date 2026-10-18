"""Fixed display texts for policy decisions (Blueprint §14.2 "Shown to user", §16.2-16.4;
ANALYSIS_PLAN §0c, §1). Pure presentation of a decision: no rule is evaluated here.

Constraints (§16.3, REQ P-09): never the word "safe"; no dose, medication or treatment advice;
the supported action is human review and capillary confirmation.
"""

from __future__ import annotations

from hyposense.policy.decide import PolicyDecision, PolicyState

LABEL_CAVEAT = (
    "Forecasts refer to CGM-detected lows. Confirm with capillary glucose according to local "
    "protocol. Risk states prioritise attention; they are not validated clinical actions."
)
STATE_TEXT = {
    PolicyState.SYSTEM_ERROR: "System error: no current risk estimate.",
    PolicyState.INSUFFICIENT_DATA: "Insufficient data: no risk estimate.",
    PolicyState.LOW_NOW: "Current or recent low glucose: verify with capillary glucose.",
    PolicyState.ALERT: "High risk of a low within 60 minutes: review the patient.",
    PolicyState.WATCH: "Elevated risk of a low within 60 minutes.",
    PolicyState.NO_ALERT: "Risk below the WATCH threshold.",
}
REASON_TEXT = {
    "SENSOR_FAULT_SUSPECTED": "SENSOR FAULT SUSPECTED: verify sensor and obtain capillary glucose.",
    "SENSOR_FLOOR": "Reading at the sensor floor.",
    "RAPID_CHANGE": "Rapid glucose change.",
    "AFTER_GAP": "First reading after a data gap.",
    "WARM_UP": "Sensor warm-up period.",
    "INSUFFICIENT_HISTORY": "Too few recent readings.",
    "NO_READING": "No reading at this time.",
    "NO_RECENT_READING": "No reading for more than 20 minutes.",
    "IN_EPISODE": "Inside a low-glucose episode.",
    "RECENT_EPISODE": "Less than 60 minutes after a low-glucose episode.",
    "CGM_LOW": "Current CGM reading below 70 mg/dL.",
}
TAG_TEXT = {
    "LOW_CONFIDENCE": "Low confidence: an input is outside the development range.",
    "MED_TIMING_UNKNOWN": "Medication timing unknown.",
    "EVENT_REJECTED": (
        "A recent input event was rejected; medication information may be incomplete."
    ),
}


def texts(d: PolicyDecision) -> tuple[str, ...]:
    out = [STATE_TEXT[d.state]]
    out += [REASON_TEXT[r] for r in d.reasons if r in REASON_TEXT]
    out += [TAG_TEXT[t.split(":")[0]] for t in d.tags if t.split(":")[0] in TAG_TEXT]
    return tuple(dict.fromkeys(out))


def probability_text(p: float | None) -> str | None:
    """Percentages (band rule, DEC-2026-10-18-H). Never '0 %' or '100 %' (review F1)."""
    if p is None:
        return None
    if p < 0.01:
        return "<1%"
    if p > 0.99:
        return ">99%"
    return f"{round(p * 100):d}%"
