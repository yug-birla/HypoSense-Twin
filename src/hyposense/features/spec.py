"""The canonical feature specification: ONE authoritative definition per feature.

Sources (verified, S4):
- Blueprint Appendix D Table D.1 (groups 1-8; model columns);
- Table 11.1 (model ladder);
- §25.1 (half-open windows; NaN, never 0; `_missing` indicators);
- docs/FEATURE_DICTIONARY.md (the S3 contracts for groups 7 and 8);
- configs/default.yaml `features` (window and cap constants).

The registry below is the single source of truth. `artifacts/features/feature_spec.json` is its
generated, committed export. A regression test fails if the two differ, and artefacts check
names against it (`FeatureSpecMismatch`).

Model levels (Table 11.1, App. D). M2 vs M3 differ ONLY by the exposure group (G8) and the
shared CSII / i.v. flags. M2 vs M3r differ only by the raw-timing group (G7) and the same flags.
    M1  = G1 CGM level + G2 CGM trend + G3 CGM variability/history + G4 time
    M2  = M1 + G5 static context + G6 meal timing
    M3r = M2 + G7 raw medication timing + G78 CSII / i.v. flags
    M3  = M2 + G8 medication exposure state + G78 CSII / i.v. flags

Missingness policy (one per feature, §25.1; no statistical imputation anywhere):
    REQUIRED            finite at every label-eligible time (guaranteed by the eligibility rules:
                        a reading at t, >= 7 readings in (t - 120 min, t], >= 120 min of record).
                        The audit asserts it. It may be NaN only at non-eligible readings.
    NEVER_MISSING       finite at every reading (counts, flags, time, indicators, quality codes)
    NAN_WITH_INDICATOR  NaN when unknown. The listed indicator column(s) are 1 exactly when the
                        documented missingness source applies. Features whose missingness
                        source is identical by construction share one indicator.
NaN meanings: NOT_OBSERVED (nothing of that kind logged before t), INSUFFICIENT_HISTORY,
UNKNOWN (value absent or unusable), TIMING_UNKNOWN (Table 12.1).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from hyposense.common.hashing import sha256_json


class Group(StrEnum):
    G1 = "G1_cgm_level"
    G2 = "G2_cgm_trend"
    G3 = "G3_cgm_history"
    G4 = "G4_time"
    G5 = "G5_static_context"
    G6 = "G6_meal_timing"
    G7 = "G7_raw_medication_timing"
    G78 = "G78_csii_iv_flags"
    G8 = "G8_medication_exposure"


class Missing(StrEnum):
    REQUIRED = "REQUIRED"
    NEVER_MISSING = "NEVER_MISSING"
    NAN_WITH_INDICATOR = "NAN_WITH_INDICATOR"


LEVEL_GROUPS: dict[str, tuple[Group, ...]] = {
    "M1": (Group.G1, Group.G2, Group.G3, Group.G4),
    "M2": (Group.G1, Group.G2, Group.G3, Group.G4, Group.G5, Group.G6),
    "M3r": (Group.G1, Group.G2, Group.G3, Group.G4, Group.G5, Group.G6, Group.G7, Group.G78),
    "M3": (Group.G1, Group.G2, Group.G3, Group.G4, Group.G5, Group.G6, Group.G78, Group.G8),
}
LEVELS = tuple(LEVEL_GROUPS)


class FeatureSpecMismatch(ValueError):
    """Feature names or order differ from the specification (Table 25.2 `snapshot`)."""


@dataclass(frozen=True)
class FeatureDef:
    name: str
    group: Group
    dtype: str  # float | binary | count | categorical
    unit: str
    source: str
    computation: str
    availability: str  # what information up to t it uses
    missing: Missing
    nan_meaning: str | None = None
    indicators: tuple[str, ...] = ()
    zero_meaning: str | None = None
    ref: str = ""  # blueprint / contract reference
    status: str = "BLUEPRINT"  # BLUEPRINT | OPERATIONALISED | S3_CONTRACT | INDICATOR | DERIVED
    lab: bool = False  # laboratory value (removed in SA8)
    version: str = "1.0.0"
    causal: bool = field(default=True)


def _ind(name: str, group: Group, means: str, ref: str = "§25.1") -> FeatureDef:
    return FeatureDef(
        name=name,
        group=group,
        dtype="binary",
        unit="0/1",
        source="indicator",
        computation=f"1 if {means}, else 0",
        availability="same information as the features it indicates",
        missing=Missing.NEVER_MISSING,
        ref=ref,
        status="INDICATOR",
    )


CGM = "CGM readings of this recording with ts <= t"


def _g1() -> list[FeatureDef]:
    out = [
        FeatureDef(
            "cgm",
            Group.G1,
            "float",
            "mg/dL",
            CGM,
            "g(t), the reading at t",
            "t",
            Missing.REQUIRED,
            ref="App. D group 1",
        ),
    ]
    for lag in (15, 30, 45, 60):
        out.append(
            FeatureDef(
                f"cgm_lag{lag}",
                Group.G1,
                "float",
                "mg/dL",
                CGM,
                f"value of the reading nearest to t - {lag} min within +/- lag_tolerance_min "
                "(7.5 min); ties go to the earlier reading",
                f"readings in [t - {lag} - 7.5, t - {lag} + 7.5] min (all < t)",
                Missing.NAN_WITH_INDICATOR,
                "NOT_OBSERVED (no reading near that time)",
                (f"cgm_lag{lag}_missing",),
                ref="App. D group 1",
                status="OPERATIONALISED",
            )
        )
    for h in (30, 60):
        out.append(
            FeatureDef(
                f"cgm_m0_proj{h}",
                Group.G1,
                "float",
                "mg/dL",
                CGM,
                f"M0 trend projection g(t) + {h} x cgm_slope30 (executable spec audit2.py: "
                "least-squares slope over (t - 35 min, t], >= 3 readings)",
                "readings in (t - 35 min, t]",
                Missing.NAN_WITH_INDICATOR,
                "INSUFFICIENT_HISTORY (< 3 readings)",
                ("cgm_slope30_missing",),
                ref="App. D group 1; Table 11.1 M0",
                status="OPERATIONALISED",
            )
        )
    out += [
        _ind(f"cgm_lag{lag}_missing", Group.G1, f"no reading within 7.5 min of t - {lag}")
        for lag in (15, 30, 45, 60)
    ]
    return out


def _g2() -> list[FeatureDef]:
    out = []
    for w in (30, 60, 120):
        req = w == 120  # >= 7 readings in (t - 120, t] at eligible t => >= 3 in (t - 125, t]
        out.append(
            FeatureDef(
                f"cgm_slope{w}",
                Group.G2,
                "float",
                "mg/dL/min",
                CGM,
                f"least-squares slope of g on time over (t - {w} - 5 min, t] "
                "(trend_window_tolerance_min = 5, the M0 window convention); exact sums",
                f"readings in (t - {w + 5} min, t]",
                Missing.REQUIRED if req else Missing.NAN_WITH_INDICATOR,
                None if req else "INSUFFICIENT_HISTORY (< 3 readings in the window)",
                () if req else (f"cgm_slope{w}_missing",),
                ref="App. D group 2",
                status="OPERATIONALISED",
            )
        )
    out += [
        FeatureDef(
            "cgm_accel",
            Group.G2,
            "float",
            "mg/dL/min",
            CGM,
            "cgm_slope30 - cgm_slope60 (App. D: 'slope 30 - slope 60')",
            "readings in (t - 65 min, t]",
            Missing.NAN_WITH_INDICATOR,
            "INSUFFICIENT_HISTORY",
            ("cgm_slope30_missing", "cgm_slope60_missing"),
            ref="App. D group 2",
        ),
        FeatureDef(
            "cgm_n_falling",
            Group.G2,
            "count",
            "readings",
            CGM,
            "number of consecutive strictly falling steps ending at t; a step longer "
            "than event.max_step_min (20 min) ends the run",
            "readings up to t",
            Missing.NEVER_MISSING,
            zero_meaning="g(t) is not below the previous reading",
            ref="App. D group 2",
            status="OPERATIONALISED",
        ),
        _ind("cgm_slope30_missing", Group.G2, "< 3 readings in (t - 35 min, t]"),
        _ind("cgm_slope60_missing", Group.G2, "< 3 readings in (t - 65 min, t]"),
    ]
    return out


def _g3() -> list[FeatureDef]:
    out = []
    for w, lab in ((120, "2h"), (360, "6h"), (1440, "24h")):
        for stat, desc, unit in (
            ("min", "minimum", "mg/dL"),
            ("mean", "mean (exact sum)", "mg/dL"),
            ("sd", "sample standard deviation (ddof = 1)", "mg/dL"),
        ):
            out.append(
                FeatureDef(
                    f"cgm_{stat}_{lab}",
                    Group.G3,
                    "float",
                    unit,
                    CGM,
                    f"{desc} of readings in (t - {w} min, t]; a recording younger than the "
                    "window uses the readings it has",
                    f"readings in (t - {w} min, t]",
                    Missing.REQUIRED,
                    ref="App. D group 3",
                )
            )
    out += [
        FeatureDef(
            "cgm_cv_24h",
            Group.G3,
            "float",
            "fraction",
            CGM,
            "cgm_sd_24h / cgm_mean_24h",
            "readings in (t - 1440 min, t]",
            Missing.REQUIRED,
            ref="App. D group 3",
        ),
        FeatureDef(
            "cgm_min_below80_24h",
            Group.G3,
            "float",
            "min",
            CGM,
            "15 (nominal sampling interval) x number of readings < 80 mg/dL in (t - 24 h, t]",
            "readings in (t - 1440 min, t]",
            Missing.REQUIRED,
            zero_meaning="no reading < 80 mg/dL in the past 24 h",
            ref="App. D group 3",
            status="OPERATIONALISED",
        ),
        FeatureDef(
            "cgm_prior_l1_onsets",
            Group.G3,
            "count",
            "episodes",
            CGM + " (causal episode tracker, state.cgm)",
            "L1 onsets in this recording confirmed at or before t (onset at reading i is "
            "confirmed by reading i+1; same rule as the label builder)",
            "readings up to t",
            Missing.NEVER_MISSING,
            zero_meaning="no confirmed L1 onset in the recording so far",
            ref="App. D group 3",
        ),
        FeatureDef(
            "cgm_min_since_low70",
            Group.G3,
            "float",
            "min",
            CGM,
            "minutes since the latest reading < 70 mg/dL, capped at 1440",
            "readings up to t",
            Missing.NAN_WITH_INDICATOR,
            "NOT_OBSERVED (no reading < 70 in the recording so far)",
            ("cgm_min_since_low70_missing",),
            ref="App. D group 3",
            status="OPERATIONALISED",
        ),
        FeatureDef(
            "cgm_pct_own",
            Group.G3,
            "float",
            "percentile (0-100)",
            CGM,
            "mid-rank percentile of g(t) among all readings of the recording up to t: "
            "100 x (#{g < g(t)} + 0.5 #{g = g(t)}) / n",
            "readings up to t",
            Missing.NAN_WITH_INDICATOR,
            "INSUFFICIENT_HISTORY (t - first reading < 24 h)",
            ("cgm_pct_own_missing",),
            ref="App. D group 3",
            status="OPERATIONALISED",
        ),
        FeatureDef(
            "sensor_day",
            Group.G3,
            "count",
            "day",
            CGM,
            "floor((t - first reading of the recording) / 24 h) + 1",
            "first reading and t",
            Missing.NEVER_MISSING,
            ref="App. D group 3",
            status="OPERATIONALISED",
        ),
        _ind("cgm_min_since_low70_missing", Group.G3, "no reading < 70 so far"),
        _ind("cgm_pct_own_missing", Group.G3, "t - first reading < 24 h"),
    ]
    return out


def _g4() -> list[FeatureDef]:
    clock = "local clock (+08:00, ASSUMPTION) of t"
    return [
        FeatureDef(
            "hour_sin",
            Group.G4,
            "float",
            "-",
            clock,
            "sin(2 pi h / 24), h = hour of day",
            "t",
            Missing.NEVER_MISSING,
            ref="App. D group 4",
        ),
        FeatureDef(
            "hour_cos",
            Group.G4,
            "float",
            "-",
            clock,
            "cos(2 pi h / 24)",
            "t",
            Missing.NEVER_MISSING,
            ref="App. D group 4",
        ),
        FeatureDef(
            "night",
            Group.G4,
            "binary",
            "0/1",
            clock,
            "1 if 00:00 <= local time < 06:00",
            "t",
            Missing.NEVER_MISSING,
            ref="App. D group 4",
        ),
    ]


_STATIC = (
    ("age_y", "float", "years", "Age (years)", False),
    ("sex_male", "binary", "0/1", "Gender (Female=1, Male=2) -> 1 if male", False),
    ("bmi", "float", "kg/m2", "BMI (kg/m2)", False),
    ("weight_kg", "float", "kg", "Weight (kg)", False),
    ("diabetes_duration_y", "float", "years", "Duration of diabetes (years)", False),
    ("hba1c_mmol_mol", "float", "mmol/mol", "HbA1c (mmol/mol)", True),
    ("egfr", "float", "ml/min/1.73m2", "Estimated Glomerular Filtration Rate", True),
    ("c_peptide_fasting_nmol_l", "float", "nmol/L", "Fasting C-peptide (nmol/L)", True),
)
_RX = (
    ("rx_insulin", "any insulin"),
    ("rx_premix", "premixed insulin (analogue or human)"),
    ("rx_basal", "basal insulin (basal analogue or NPH)"),
    ("rx_short_rapid", "short (regular human) or rapid-analogue insulin"),
    ("rx_su", "sulfonylurea"),
    ("rx_glinide", "glinide"),
    ("rx_metformin", "metformin"),
    ("rx_agi", "alpha-glucosidase inhibitor"),
    ("rx_dpp4", "DPP-4 inhibitor"),
    ("rx_sglt2", "SGLT2 inhibitor"),
    ("rx_glp1", "GLP-1 receptor agonist"),
    ("rx_tzd", "thiazolidinedione"),
)
STATIC_AVAIL = (
    "patient-level context of this recording's summary row; constant over the "
    "recording (Blueprint §10.2: accepted residual risk; labs may post-date CGM)"
)


def _g5() -> list[FeatureDef]:
    out = [
        FeatureDef(
            name,
            Group.G5,
            dtype,
            unit,
            f"summary sheet: {col}",
            "value of this recording's summary row ('/' or blank or implausible -> NaN)",
            STATIC_AVAIL,
            Missing.NAN_WITH_INDICATOR,
            "UNKNOWN",
            (f"{name}_missing",),
            ref="App. D group 5",
            lab=lab,
        )
        for name, dtype, unit, col, lab in _STATIC
    ]
    out += [
        FeatureDef(
            name,
            Group.G5,
            "binary",
            "0/1",
            "summary sheet: Hypoglycemic Agents (drug dictionary)",
            f"1 if the prescribed regimen names {desc}",
            STATIC_AVAIL,
            Missing.NAN_WITH_INDICATOR,
            "UNKNOWN (regimen field empty)",
            ("rx_missing",),
            zero_meaning="not named in the prescribed regimen",
            ref="App. D group 5",
        )
        for name, desc in _RX
    ]
    out += [_ind(f"{name}_missing", Group.G5, f"{name} is unknown") for name, *_ in _STATIC]
    out.append(_ind("rx_missing", Group.G5, "the prescribed-regimen field is empty"))
    return out


def _g6() -> list[FeatureDef]:
    src = "diet entries of this recording with ts <= t"
    return [
        FeatureDef(
            "meal_min_since",
            Group.G6,
            "float",
            "min",
            src,
            "minutes since the latest logged meal, capped at 720",
            "meals up to t",
            Missing.NAN_WITH_INDICATOR,
            "NOT_OBSERVED (no meal logged so far)",
            ("meal_none_logged",),
            ref="App. D group 6",
        ),
        FeatureDef(
            "meal_last_3h",
            Group.G6,
            "binary",
            "0/1",
            src,
            "1 if a meal is logged in (t - 180 min, t]",
            "meals up to t",
            Missing.NEVER_MISSING,
            zero_meaning="no meal logged in the last 3 h",
            ref="App. D group 6",
        ),
        FeatureDef(
            "meals_today",
            Group.G6,
            "count",
            "meals",
            src,
            "meals logged since local midnight, up to t",
            "meals up to t",
            Missing.NEVER_MISSING,
            zero_meaning="no meal logged today so far",
            ref="App. D group 6",
        ),
        FeatureDef(
            "meal_last_content_unknown",
            Group.G6,
            "binary",
            "0/1",
            src,
            "1 if the latest logged meal has no recorded content ('Data not available')",
            "meals up to t",
            Missing.NAN_WITH_INDICATOR,
            "NOT_OBSERVED (no meal logged so far)",
            ("meal_none_logged",),
            ref="App. D group 6",
        ),
        _ind("meal_none_logged", Group.G6, "no meal logged in the recording so far"),
    ]


CATEGORY_CLASS = {
    "insulin_bolus": "insulin",
    "insulin_basal": "insulin",
    "su": "sulfonylurea",
    "glinide": "glinide",
}


def _g7() -> list[FeatureDef]:
    src = "parsed medication events with ts <= t (medication.timing.raw_timing)"
    out = []
    for cat, cls in CATEGORY_CLASS.items():
        unit = "IU" if cat.startswith("insulin") else "mg"
        tu = f"TIMING_UNKNOWN for class {cls} (Table 12.1)"
        out += [
            FeatureDef(
                f"{cat}_min_since_last",
                Group.G7,
                "float",
                "min",
                src,
                "minutes since the latest administration, capped at 1440",
                "administrations up to t",
                Missing.NAN_WITH_INDICATOR,
                f"NOT_OBSERVED (none logged before t) or {tu}",
                (f"{cat}_missing",),
                ref="App. D group 7; FEATURE_DICTIONARY",
                status="S3_CONTRACT",
            ),
            FeatureDef(
                f"{cat}_last_dose",
                Group.G7,
                "float",
                unit,
                src,
                "dose of the latest administration",
                "administrations up to t",
                Missing.NAN_WITH_INDICATOR,
                f"NOT_OBSERVED, {tu}, or the dose is unknown (0 cases in T)",
                (f"{cat}_missing",),
                ref="App. D group 7; FEATURE_DICTIONARY",
                status="S3_CONTRACT",
            ),
            FeatureDef(
                f"{cat}_dose_24h",
                Group.G7,
                "float",
                unit,
                src,
                "total dose in (t - 24 h, t]",
                "administrations in (t - 24 h, t]",
                Missing.NAN_WITH_INDICATOR,
                f"{tu}, or a dose in the window is unknown (0 cases in T)",
                (f"{cat}_missing",),
                zero_meaning="nothing of this category logged in the past 24 h",
                ref="App. D group 7; FEATURE_DICTIONARY",
                status="S3_CONTRACT",
            ),
            FeatureDef(
                f"{cat}_n_24h",
                Group.G7,
                "count",
                "administrations",
                src,
                "administrations in (t - 24 h, t]",
                "administrations in (t - 24 h, t]",
                Missing.NEVER_MISSING,
                zero_meaning="none logged in the past 24 h",
                ref="App. D group 7; FEATURE_DICTIONARY",
                status="S3_CONTRACT",
            ),
        ]
    out += [
        _ind(
            f"{cat}_missing",
            Group.G7,
            f"any of {cat}_min_since_last / _last_dose / _dose_24h is NaN (none logged before "
            f"t, class {cls} TIMING_UNKNOWN, or a dose of unknown size)",
            ref="§25.1; FEATURE_DICTIONARY",
        )
        for cat, cls in CATEGORY_CLASS.items()
    ]
    return out


def _g78() -> list[FeatureDef]:
    src = "parsed CSII / i.v. events with ts <= t (ExposureEngine)"
    return [
        FeatureDef(
            "csii_active",
            Group.G78,
            "binary",
            "0/1",
            src,
            "a programmed basal rate is in force at t (<= 6 h after its entry, not suspended)",
            "pump entries up to t",
            Missing.NEVER_MISSING,
            ref="App. D groups 7-8; ADR-026",
            status="S3_CONTRACT",
        ),
        FeatureDef(
            "csii_rate_iu_h",
            Group.G78,
            "float",
            "IU/h",
            src,
            "the currently programmed basal rate (0 if none in force)",
            "pump entries up to t",
            Missing.NEVER_MISSING,
            zero_meaning="no basal rate in force",
            ref="FEATURE_DICTIONARY",
            status="S3_CONTRACT",
        ),
        FeatureDef(
            "iv_insulin_recent",
            Group.G78,
            "binary",
            "0/1",
            src,
            "an i.v. insulin entry in (t - 4 h, t]",
            "i.v. entries up to t",
            Missing.NEVER_MISSING,
            ref="App. D groups 7-8; §12.2",
            status="S3_CONTRACT",
        ),
    ]


def _g8() -> list[FeatureDef]:
    src = "parsed medication events with ts <= t (ExposureEngine, configs/pharma.yaml)"
    qi, qs, qg = ("quality_insulin",), ("quality_sulfonylurea",), ("quality_glinide",)
    nan = "TIMING_UNKNOWN / DOSE_UNKNOWN / FORMULATION_UNKNOWN for the class (quality code)"
    ref = "App. D group 8; FEATURE_DICTIONARY"

    def exp(name: str, unit: str, comp: str, ind: tuple[str, ...]) -> FeatureDef:
        return FeatureDef(
            name,
            Group.G8,
            "float",
            unit,
            src,
            comp,
            "administrations up to t",
            Missing.NAN_WITH_INDICATOR,
            nan,
            ind,
            zero_meaning="no exposure of this class at t",
            ref=ref,
            status="S3_CONTRACT",
        )

    out = [
        exp(
            "act_prandial",
            "IU/h",
            "sum dose x weight x a(t - t_i), rapid + regular "
            "components incl. premix fast fractions and CSII micro-boluses",
            qi,
        ),
        exp("act_intermediate", "IU/h", "the same for NPH components", qi),
        exp("act_basal", "IU/h", "the same for basal analogues (flat kernels)", qi),
        exp("act_insulin_total", "IU/h", "act_prandial + act_intermediate + act_basal", qi),
        exp("iob_insulin", "IU", "sum dose x (1 - A(t - t_i)) over all insulin components", qi),
        exp(
            "insulin_p30",
            "IU/h",
            "total insulin activity at t + 30 from doses <= t plus the "
            "current CSII basal rate (no future injections)",
            qi,
        ),
        exp("insulin_p60", "IU/h", "the same at t + 60", qi),
        exp("act_su", "dimensionless", "sum (dose / D_max) x peak-normalised Bateman kernel", qs),
        exp("su_p30", "dimensionless", "act_su at t + 30 from doses <= t", qs),
        exp("su_p60", "dimensionless", "act_su at t + 60 from doses <= t", qs),
        exp("act_glinide", "dimensionless", "as act_su, for glinides", qg),
        exp("glinide_p30", "dimensionless", "act_glinide at t + 30 from doses <= t", qg),
        exp("glinide_p60", "dimensionless", "act_glinide at t + 60 from doses <= t", qg),
    ]
    for key, cls in (("insulin", "insulin"), ("su", "sulfonylurea"), ("glinide", "glinide")):
        out.append(
            FeatureDef(
                f"min_since_{key}",
                Group.G8,
                "float",
                "min",
                src,
                f"minutes since the latest {cls} administration, capped at 1440",
                "administrations up to t",
                Missing.NAN_WITH_INDICATOR,
                "NOT_OBSERVED (none logged before t)",
                (f"min_since_{key}_missing",),
                ref=ref,
                status="S3_CONTRACT",
            )
        )
    out += [
        FeatureDef(
            "delta_insulin_60",
            Group.G8,
            "float",
            "IU/h",
            src,
            "insulin_p60 - act_insulin_total (App. D 'Delta exposure next 60 min')",
            "administrations up to t",
            Missing.NAN_WITH_INDICATOR,
            nan,
            qi,
            ref=ref,
            status="DERIVED",
        ),
        FeatureDef(
            "delta_su_60",
            Group.G8,
            "float",
            "dimensionless",
            src,
            "su_p60 - act_su",
            "administrations up to t",
            Missing.NAN_WITH_INDICATOR,
            nan,
            qs,
            ref=ref,
            status="DERIVED",
        ),
        FeatureDef(
            "act_insulin_total_per_kg",
            Group.G8,
            "float",
            "IU/h/kg",
            src + "; summary weight",
            "act_insulin_total / weight_kg (§12.2: 'per kg body weight when weight is known')",
            "administrations up to t; static weight",
            Missing.NAN_WITH_INDICATOR,
            nan + "; or weight unknown",
            ("quality_insulin", "weight_kg_missing"),
            ref="App. D group 8; §12.2",
            status="DERIVED",
        ),
    ]
    for cls in ("insulin", "sulfonylurea", "glinide"):
        out.append(
            FeatureDef(
                f"quality_{cls}",
                Group.G8,
                "categorical",
                "code",
                src,
                "QualityState code: 0 KNOWN, 1 PARTIAL, 2 TIMING_UNKNOWN, 3 DOSE_UNKNOWN, "
                "4 FORMULATION_UNKNOWN, 5 NO_LOGGED_MEDICATION (the 'timing-unknown "
                "indicators' of App. D)",
                "administrations and regimen up to t",
                Missing.NEVER_MISSING,
                ref=ref,
                status="S3_CONTRACT",
            )
        )
    out += [
        _ind(f"min_since_{k}_missing", Group.G8, f"no {c} administration logged before t")
        for k, c in (("insulin", "insulin"), ("su", "sulfonylurea"), ("glinide", "glinide"))
    ]
    return out


def _build() -> tuple[FeatureDef, ...]:
    return tuple(_g1() + _g2() + _g3() + _g4() + _g5() + _g6() + _g7() + _g78() + _g8())


FEATURES: tuple[FeatureDef, ...] = _build()
BY_NAME: dict[str, FeatureDef] = {f.name: f for f in FEATURES}
UNION_NAMES: tuple[str, ...] = tuple(f.name for f in FEATURES)


def level_names(level: str) -> tuple[str, ...]:
    if level not in LEVEL_GROUPS:
        raise FeatureSpecMismatch(f"unknown model level {level!r}")
    groups = set(LEVEL_GROUPS[level])
    return tuple(f.name for f in FEATURES if f.group in groups)


def check_names(level: str, names: Sequence[str]) -> None:
    expected = level_names(level)
    if tuple(names) != expected:
        missing = sorted(set(expected) - set(names))
        extra = sorted(set(names) - set(expected))
        raise FeatureSpecMismatch(
            f"{level}: names differ from feature_spec (missing={missing}, extra={extra}, "
            f"order_differs={not missing and not extra})"
        )


def spec_document(feature_cfg: dict[str, Any]) -> dict[str, Any]:
    """The exported specification (artifacts/features/feature_spec.json) without its hash."""
    return {
        "spec_version": str(feature_cfg["spec_version"]),
        "description": "HypoSense Twin v2 canonical feature specification (generated from "
        "src/hyposense/features/spec.py; do not edit by hand)",
        "constants": feature_cfg,
        "levels": {lvl: list(level_names(lvl)) for lvl in LEVELS},
        "level_groups": {lvl: [g.value for g in gs] for lvl, gs in LEVEL_GROUPS.items()},
        "features": [
            {
                **asdict(f),
                "group": f.group.value,
                "missing": f.missing.value,
                "indicators": list(f.indicators),
                "models": [lvl for lvl in LEVELS if f.group in LEVEL_GROUPS[lvl]],
            }
            for f in FEATURES
        ],
    }


def spec_sha256(feature_cfg: dict[str, Any]) -> str:
    return sha256_json(spec_document(feature_cfg))
