"""Medication feature groups G7 (M3r), G78 (shared CSII / i.v. flags) and G8 (M3), assembled from
the S3 engine outputs at t (`state.medication.MedicationSnapshot`). No medication logic lives
here: only the contract-level assembly from docs/FEATURE_DICTIONARY.md.

- G7 (M3r): `raw_timing`. A category whose class is TIMING_UNKNOWN (prescribed, nothing logged
  within 36 h; Table 12.1) has min_since_last, last_dose and dose_24h set to NaN (not zero).
  This is the S3 contract ("set to NaN by the feature builder (S4)").
- G8 (M3): `ExposureEngine` outputs. The engine already sets NaN for classes whose timing, dose
  or formulation is unknown, and reports the class quality code. S4 adds the contract's derived
  terms: Delta exposure over the next 60 min, and insulin activity per kg (weight known only).
"""

from __future__ import annotations

import math

from hyposense.medication.exposure import QualityState
from hyposense.state.medication import MedicationSnapshot

CATEGORY_CLASS = {
    "insulin_bolus": "insulin",
    "insulin_basal": "insulin",
    "su": "sulfonylurea",
    "glinide": "glinide",
}
G8_EXPOSURE = (
    "act_prandial",
    "act_intermediate",
    "act_basal",
    "act_insulin_total",
    "iob_insulin",
    "insulin_p30",
    "insulin_p60",
    "act_su",
    "su_p30",
    "su_p60",
    "act_glinide",
    "glinide_p30",
    "glinide_p60",
    "min_since_insulin",
    "min_since_su",
    "min_since_glinide",
)
G78 = ("csii_active", "csii_rate_iu_h", "iv_insulin_recent")


def raw_timing_features(m: MedicationSnapshot) -> dict[str, float]:
    out: dict[str, float] = {}
    for cat, cls in CATEGORY_CLASS.items():
        unknown = m.quality[cls] is QualityState.TIMING_UNKNOWN
        for var in ("min_since_last", "last_dose", "dose_24h", "n_24h"):
            v = m.timing[f"{cat}_{var}"]
            out[f"{cat}_{var}"] = math.nan if unknown and var != "n_24h" else v
    for cat in CATEGORY_CLASS:
        out[f"{cat}_missing"] = float(math.isnan(out[f"{cat}_min_since_last"]))
    return out


def flag_features(m: MedicationSnapshot) -> dict[str, float]:
    return {k: m.exposure[k] for k in G78}


def exposure_features(m: MedicationSnapshot, weight_kg: float) -> dict[str, float]:
    e = m.exposure
    out = {k: e[k] for k in G8_EXPOSURE}
    out["delta_insulin_60"] = e["insulin_p60"] - e["act_insulin_total"]
    out["delta_su_60"] = e["su_p60"] - e["act_su"]
    out["act_insulin_total_per_kg"] = (
        e["act_insulin_total"] / weight_kg if math.isfinite(weight_kg) else math.nan
    )
    for cls in ("insulin", "sulfonylurea", "glinide"):
        out[f"quality_{cls}"] = e[f"quality_{cls}"]
    for key in ("insulin", "su", "glinide"):
        out[f"min_since_{key}_missing"] = float(math.isnan(e[f"min_since_{key}"]))
    return out
