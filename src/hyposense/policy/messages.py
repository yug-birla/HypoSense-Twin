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


STATE_LABEL = {
    PolicyState.SYSTEM_ERROR: "SYSTEM ERROR",
    PolicyState.INSUFFICIENT_DATA: "INSUFFICIENT DATA",
    PolicyState.LOW_NOW: "LOW NOW",
    PolicyState.ALERT: "ALERT",
    PolicyState.WATCH: "WATCH",
    PolicyState.NO_ALERT: "NO ALERT",
}
GROUP_LABEL = {  # features.spec.Group values -> display names (associations, not causes)
    "G1_cgm_level": "CGM level",
    "G2_cgm_trend": "CGM trend",
    "G3_cgm_history": "CGM history",
    "G4_time": "time of day",
    "G5_static_context": "patient context",
    "G6_meal_timing": "meal timing",
    "G7_raw_medication_timing": "medication timing",
    "G78_csii_iv_flags": "pump / i.v. insulin",
    "G8_medication_exposure": "medication exposure",
}
# Display convention for the trend arrow (mg/dL/min of the canonical 30-min slope, cgm_slope30):
# |rate| < 1 steady, 1-2 rising/falling, >= 2 rapidly. A presentation constant, never a model input.
TREND_STEPS = (1.0, 2.0)


def trend_category(rate: float | None) -> str | None:
    if rate is None or rate != rate:  # NaN: fewer than 3 readings in the window
        return None
    a = abs(rate)
    if a < TREND_STEPS[0]:
        return "steady"
    word = "rising" if rate > 0 else "falling"
    return f"{word}_fast" if a >= TREND_STEPS[1] else word


def clock_text(ts: int, utc_offset_s: int) -> str:
    m = ((ts + utc_offset_s) // 60) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def summary(
    d: PolicyDecision,
    since_ts: int | None,
    groups: list[str],
    utc_offset_s: int,
) -> str:
    """Deterministic one-line summary from validated fields only. Unavailable values are
    omitted, never guessed. No advice, no new interpretation."""
    head = STATE_LABEL[d.state]
    if since_ts is not None:
        head += f" since {clock_text(since_ts, utc_offset_s)}"
    parts = [head]
    pt = probability_text(d.p)
    if pt is not None:
        parts.append(f"estimated risk {pt}")
    if "SENSOR_FAULT_SUSPECTED" in d.reasons:
        parts.append("sensor fault suspected")
    elif d.state is PolicyState.LOW_NOW:
        parts.append("verify with capillary glucose")
    if groups:
        names = [GROUP_LABEL.get(g, g) for g in groups[:2]]
        parts.append("main associated factors: " + " and ".join(names))
    timing = sorted(t.split(":", 1)[1] for t in d.tags if t.startswith("MED_TIMING_UNKNOWN:"))
    if timing:
        parts.append("medication timing unknown (" + ", ".join(timing) + ")")
    if "LOW_CONFIDENCE" in d.tags:
        parts.append("some inputs outside the development range")
    if "EVENT_REJECTED" in d.tags:
        parts.append("a recent input was rejected")
    return " · ".join(parts)


def reason_line(d: PolicyDecision, groups: list[str]) -> str:
    """The most specific reason for the displayed state, for one-line lists (ward board).
    Forecast states name the top associated factor groups (never causes); other states use the
    policy reason text. Deterministic; empty pieces are omitted."""
    if d.state in (PolicyState.ALERT, PolicyState.WATCH, PolicyState.NO_ALERT):
        if d.state is PolicyState.NO_ALERT:
            return "Below the WATCH threshold"
        if groups:
            return "Associated: " + ", ".join(GROUP_LABEL.get(g, g) for g in groups[:2])
        return (
            "At or above the "
            + ("ALERT" if d.state is PolicyState.ALERT else "WATCH")
            + " threshold"
        )
    for r in d.reasons:
        if r == "SENSOR_FAULT_SUSPECTED":
            return "Sensor fault suspected: verify sensor and capillary glucose"
    for r in d.reasons:
        if r in REASON_TEXT:
            return REASON_TEXT[r].rstrip(".")
    return STATE_TEXT[d.state].rstrip(".")
