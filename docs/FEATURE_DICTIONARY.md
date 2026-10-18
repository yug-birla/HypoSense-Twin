# Feature Dictionary

**Status: spec v1.0.0, implemented (S4).**

**Authoritative definition:** `src/hyposense/features/spec.py`, the registry with one definition per
feature. Its committed, generated export is
[`artifacts/features/feature_spec.json`](../artifacts/features/feature_spec.json)
(sha256 `82fc54e9…`). A test fails if the export drifts from the registry, and artefacts check
feature names against it (`FeatureSpecMismatch`). This page is the human-readable summary; where
they differ, the registry wins.

**Sources verified for every group:**
- Blueprint Appendix D Table D.1 (groups 1–8);
- Table 11.1 (model ladder);
- §10.2 and §25.1 (half-open windows; NaN, never 0; `_missing` indicators);
- §12.2 and Table 12.1 (exposure, per-kg, missing timing);
- the S3 contracts for groups 7 and 8 (this page, S3 version);
- the executable specification `audit2.py` (M0 trend projection).

## Model levels

| Level | Groups | Features | Role |
|---|---|---|---|
| M1 | G1 CGM level · G2 CGM trend · G3 CGM variability/history · G4 time | 38 | CGM-only baseline |
| M2 | M1 + G5 static context · G6 meal timing | 72 | primary comparator |
| M3r | M2 + G7 raw medication timing + G78 CSII / i.v. flags | 95 | representation check (C2b) |
| M3 | M2 + G8 medication exposure state + G78 CSII / i.v. flags | 100 | proposed model |

- **M3 − M2 is exactly G8 ∪ G78, and M3r − M2 is exactly G7 ∪ G78** (`test_level_membership`).
  The confirmatory comparison changes one thing: medication exposure.
- G7 never enters M3 and G8 never enters M3r.
- The CSII / i.v. flags (G78) are defined once and shared by M3r and M3, as Table 11.1 lists
  them for both.

## Conventions (all groups)

- **Causality.** A feature at reading t uses only events with ts ≤ t. Same-timestamp order is
  dose → meal → CGM, so a dose or meal charted at t is known at t.
- **Tests.** Equality is checked bitwise:
  - truncation equality at every label-eligible T time (`hyposense audit features`);
  - Hypothesis truncation and future-perturbation tests;
  - loader-level truncation.
- **Recording-scoped.** All history (CGM, episodes, meals, medication) is per recording and never
  crosses a recording boundary (ANALYSIS_PLAN §0 item 10).
- **Windows.** History windows are half-open, (t − Δ, t].
  - **Trend windows** (slopes, M0 projection) use (t − Δ − 5 min, t]. This is the executable
    spec's M0 window, so a nominal 30-min window holds the readings at t − 30, t − 15 and t on
    the 15-min grid.
- **Arithmetic.** Sums are exact (`math.fsum`), and every NaN is the canonical NaN.
  - Values are float64. The blueprint's float32 is not used, because rounding would blur
    threshold ties.
  - Snapshot digests are SHA-256.
- **Time of day** uses the local clock (+08:00, ASSUMPTION).

## Missingness policy (one per feature; no imputation anywhere)

| Policy | Meaning |
|---|---|
| `REQUIRED` | Finite at every label-eligible time, guaranteed by the eligibility rules (reading at t, ≥ 7 readings in (t − 120, t], ≥ 120 min of record). It may be NaN only at non-eligible readings, and the audit asserts this. |
| `NEVER_MISSING` | Finite at every reading: counts, flags, time, indicators, quality codes. |
| `NAN_WITH_INDICATOR` | NaN when unknown. The listed indicator column is 1 exactly when the documented missingness source applies. Features with the same missingness source share one indicator. |

**What a NaN means** is recorded per feature:
- NOT_OBSERVED: nothing of that kind logged before t;
- INSUFFICIENT_HISTORY;
- UNKNOWN: the value is absent or unusable;
- TIMING_UNKNOWN (Table 12.1).

**ZERO is always a true zero**, documented per feature (e.g. "no exposure of this class at t",
"nothing logged in the past 24 h").

For the M3 exposure clusters, the class quality code (`quality_<class>`) *is* the indicator.
The exposure is NaN exactly when the quality is TIMING_UNKNOWN, DOSE_UNKNOWN or
FORMULATION_UNKNOWN. This is App. D's "timing-unknown indicators".

## G1 CGM level (M1–M3)

| Feature | Definition | Missing |
|---|---|---|
| `cgm` | g(t) | REQUIRED |
| `cgm_lag15`, `_lag30`, `_lag45`, `_lag60` | reading nearest to t − L within ± 7.5 min (ties → earlier) | NaN + `cgm_lagL_missing` |
| `cgm_m0_proj30`, `cgm_m0_proj60` | g(t) + H × `cgm_slope30`, the M0 trend rule (audit2.py: LS slope over (t − 35, t], ≥ 3 readings) | NaN + `cgm_slope30_missing` |

## G2 CGM trend (M1–M3)

| Feature | Definition | Missing |
|---|---|---|
| `cgm_slope30`, `cgm_slope60` | least-squares slope (mg/dL/min) over (t − Δ − 5, t], ≥ 3 readings | NaN + `cgm_slopeΔ_missing` |
| `cgm_slope120` | same over (t − 125, t] | REQUIRED |
| `cgm_accel` | slope30 − slope60 | NaN + both slope indicators |
| `cgm_n_falling` | consecutive strictly falling steps ending at t; a step > 20 min ends the run | NEVER_MISSING |

## G3 CGM variability and personal history (M1–M3)

| Feature | Definition | Missing |
|---|---|---|
| `cgm_{min,mean,sd}_{2h,6h,24h}` | over (t − W, t]; SD with ddof = 1; a younger recording uses what it has | REQUIRED |
| `cgm_cv_24h` | sd_24h / mean_24h | REQUIRED |
| `cgm_min_below80_24h` | 15 min × readings < 80 in (t − 24 h, t] | REQUIRED |
| `cgm_prior_l1_onsets` | L1 onsets confirmed by t (causal tracker, label rule with one-reading confirmation lag) | NEVER_MISSING |
| `cgm_min_since_low70` | minutes since the latest reading < 70, capped at 1440 | NaN + indicator (no low yet) |
| `cgm_pct_own` | mid-rank percentile of g(t) among the recording's readings ≤ t | NaN + indicator (< 24 h of history) |
| `sensor_day` | ⌊(t − first reading)/24 h⌋ + 1 | NEVER_MISSING |

## G4 Time (M1–M3)

| Feature | Definition |
|---|---|
| `hour_sin` | sin(2πh/24) |
| `hour_cos` | cos(2πh/24) |
| `night` | 1 if 00:00 ≤ local time < 06:00 |

## G5 Static context (M2–M3)

- **Fields:**
  - `age_y`, `sex_male`, `bmi`, `weight_kg`, `diabetes_duration_y`;
  - the labs, `hba1c_mmol_mol`, `egfr` and `c_peptide_fasting_nmol_l`, which are tagged `lab` and
    removed in SA8;
  - each with its own `<name>_missing`.
- **Source:** the recording's own summary row, through an allow-list. "Hypoglycemia (yes/no)" and
  identifiers are never read.
- **Missing values:** "/", blank, unparseable or outside a wide validity range → NaN, counted.
- **Regimen flags** (parsed from "Hypoglycemic Agents" with the drug dictionary): `rx_insulin`,
  `rx_premix`, `rx_basal` (basal analogue or NPH), `rx_short_rapid`, `rx_su`, `rx_glinide`,
  `rx_metformin`, `rx_agi`, `rx_dpp4`, `rx_sglt2`, `rx_glp1`, `rx_tzd`.
  - 0 = not named in the regimen.
  - NaN + `rx_missing` if the field is empty. "none" gives all-zero flags.
- **Temporal status** (Blueprint §10.2): labs may be measured up to 6 months before or after the
  CGM period. They are patient-level context, constant over the recording and available at
  every t. This is the accepted, documented residual risk, and SA8 removes them. They are never
  treated as time-stamped events.

## G6 Meal timing (M2–M3)

| Feature | Definition | Missing |
|---|---|---|
| `meal_min_since` | minutes since the latest logged meal, capped at 720 | NaN + `meal_none_logged` |
| `meal_last_3h` | meal logged in (t − 180, t] | NEVER_MISSING |
| `meals_today` | meals since local midnight, up to t | NEVER_MISSING |
| `meal_last_content_unknown` | latest meal's diet text is the "not recorded" marker ("Data not available" / 未记录) | NaN + `meal_none_logged` |

A meal is a timed diet entry; entries sharing a timestamp form one meal. There is no
carbohydrate estimation and no nutrition parsing (E3 deferred).

## G7 Raw medication timing (M3r only; S3 contract)

- **Categories:** `insulin_bolus` (rapid, regular and premix injections; CSII boluses),
  `insulin_basal` (basal analogue and NPH injections), `su`, `glinide`.
- **Per category:**
  - `_min_since_last`: capped at 1440;
  - `_last_dose`;
  - `_dose_24h`: over (t − 24 h, t];
  - `_n_24h`.
- **Missing:**
  - If the class is TIMING_UNKNOWN (prescribed, nothing logged within 36 h; Table 12.1),
    min_since, last_dose and dose_24h are NaN. n_24h keeps the true count.
  - `<cat>_missing` = 1 if any of min_since / last_dose / dose_24h is NaN: never logged before
    t, class timing unknown, or a dose of unknown size (0 such cases in T; S4 review fix).

## G78 CSII / i.v. flags (M3r and M3)

| Feature | Definition |
|---|---|
| `csii_active` | a programmed basal rate is in force (≤ 6 h after entry, not suspended) |
| `csii_rate_iu_h` | the current programmed rate (0 if none) |
| `iv_insulin_recent` | an i.v. insulin entry in (t − 4 h, t] |

## G8 Medication exposure state (M3 only; S3 contract + S4 derived terms)

| Feature | Definition |
|---|---|
| `act_prandial`, `act_intermediate`, `act_basal`, `act_insulin_total` | insulin activity (IU/h) by kernel family and in total |
| `iob_insulin` | insulin on board (IU) |
| `insulin_p30`, `insulin_p60` | total activity at t + 30 / 60 from doses ≤ t (+ the current CSII basal rate) |
| `act_su`, `su_p30`, `su_p60` | dose/D_max-scaled Bateman exposure (dimensionless) and its projections |
| `act_glinide`, `glinide_p30`, `glinide_p60` | the same for glinides |
| `min_since_insulin`, `min_since_su`, `min_since_glinide` | capped at 1440; NaN + `min_since_<x>_missing` if never logged |
| `delta_insulin_60` | insulin_p60 − act_insulin_total (App. D "Δexposure next 60 min") |
| `delta_su_60` | su_p60 − act_su |
| `act_insulin_total_per_kg` | act_insulin_total / weight_kg. NaN if weight is unknown; weight is never imputed |
| `quality_insulin`, `quality_sulfonylurea`, `quality_glinide` | QualityState codes: 0 KNOWN, 1 PARTIAL, 2 TIMING_UNKNOWN, 3 DOSE_UNKNOWN, 4 FORMULATION_UNKNOWN, 5 NO_LOGGED_MEDICATION |

The exposure clusters are NaN when the class quality is TIMING_UNKNOWN, DOSE_UNKNOWN or
FORMULATION_UNKNOWN. NO_LOGGED_MEDICATION gives a true 0. Kernel parameters and their provenance
are in configs/pharma.yaml and docs/medication/PARAMETER_SOURCES.md. The kernels are
population-level shapes, not clinically validated and not dosing tools.

## Non-feature columns of the offline table (metadata; never model inputs)

| Column | Meaning |
|---|---|
| `sufficient`, `gap_before`, `floor`, `rapid_change`, `warmup`, `history_ok` | data-quality state at t (policy sufficiency, Table 14.1 priority 2) |
| `sensor_fault_suspected` | P-C8a causal flag |
| `in_episode_causal` | the causal tracker's in-episode status (policy LOW NOW / refractory, S7) |

Label columns (eligible, y) and the hindsight sensor-floor-run mask for SA9 / P-B6 are joined
offline from `labels/`. The live path never sees them.

## Excluded by design

- "Hypoglycemia (yes/no)", patient or recording identifiers, the treated status (population
  only), CBG (display only), the forecast state and outcome ledger (display and audit only), and
  i.v. glucose (confounder flag only, ADR-028).
- No carbohydrate estimate, no physiological-model output (group 9 / M4 not planned).
