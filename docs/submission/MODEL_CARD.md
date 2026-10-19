# Model card — HypoSense Twin (pre-confirmatory)

> **Status: DEVELOPMENT.** This card describes the frozen-to-be **candidate**. The confirmatory
> sections are **PENDING** until the official evaluation on the sealed partition has run. After
> that run, `uv run hyposense report` regenerates the confirmatory model card from the frozen
> results (`docs/results/MODEL_CARD.md`).

## Intended use

- **Purpose:** research and decision support. The model estimates the risk that a new
  CGM-detected Level 1 low-glucose episode (< 70 mg/dL) begins within the next 60 minutes, at
  least 15 minutes ahead, for adults with type 2 diabetes treated with insulin or insulin
  secretagogues.
- **Supported action:** human review and capillary glucose confirmation per local protocol.
  States prioritise attention.
- **Setting:** retrospective replay and silent-mode research only.

## Prohibited use

- Not a medical device; not for clinical decisions without independent confirmation.
- Never used to recommend, adjust or simulate insulin or any medication dose or treatment.
- Not validated for children, type 1 diabetes, outpatients, other populations, other sensors,
  or data imported through the new-patient intake (no accuracy claim applies to uploaded data).

## Model

| Item | Value (from `artifacts/models/M3-candidate-*/manifest.json`) |
|---|---|
| Version | `M3-development-3271a3206765` (status DEVELOPMENT) |
| Level | M3: CGM + context + meals + medication exposure, 100 features (feature spec v1.0.1) |
| Learner | LightGBM binary classifier |
| Hyperparameters | num_leaves 16, learning_rate 0.0418, min_data_in_leaf 603, feature_fraction 0.600, bagging_fraction 0.940, lambda_l2 9.41 (tuned on M1 in S6, `T-AGG-dev-s6-20261018T144427Z`) |
| Rounds, seed, threads | 113 rounds, seed 2026, 1 thread, deterministic |
| Calibration | `isotonic_interp_floored` (isotonic interpolation with a lower floor), fitted on inner out-of-fold predictions |
| Thresholds | ALERT τA = 0.1230 (≤ 1 false alert per patient-day on development OOF); WATCH τW = 0.0251 |
| Policy | Deterministic; notification cooldown 60 min; no reading for > 20 min means no current forecast |
| Training data | Tuning partition T (30 patients) only |

## Data

- **Dataset:** ShanghaiT2DM v5 (official figshare copy, CC BY 4.0), verified by SHA-256
  manifest.
- **Partition:** a patient-level, pre-specified split into T (30) and a sealed evaluation set E
  (70).
- **Target labels:** CGM-detected Level 1 episodes, using the run rules in
  `docs/protocol/ANALYSIS_PLAN.md`.

## Features

- **CGM:** level, lags, slopes, variability and history.
- **Time:** time of day.
- **Static context:** age, sex, BMI, weight, diabetes duration, HbA1c, eGFR, fasting C-peptide,
  prescribed regimen flags, and missing-value indicators.
- **Meals:** meal timing.
- **Pump / IV insulin:** CSII and i.v. flags.
- **Medication exposure:** estimated activity and on-board amounts for prandial, intermediate and
  basal insulin, sulfonylureas and glinides, plus projections, times since the last dose, and
  medication-quality states.
- Every feature is computed causally. Bitwise truncation equality was verified at 31,292 times;
  offline/live parity has 0 mismatches.

## Validation

| | Development (T, nested patient-grouped CV) | Confirmatory (sealed E) |
|---|---|---|
| Sensitivity @ 1 FA/day, treated, M3 | 91.1 % (95 % CI 78.8–100) | **PENDING** |
| Sensitivity @ 1 FA/day, treated, M2 | 87.5 % (78.1–100) | **PENDING** |
| Δ M3 − M2 | +3.6 points (−4.2 to +8.8): no reliable difference | **PENDING (H1)** |
| Calibration (served calibrator, T) | ECE 0.0017, slope 1.07 | **PENDING** |

The development numbers are optimistic: tuning, calibration and thresholds were chosen on T.

## Medication assumptions

- Exposure comes from fixed population-level, label-sourced kernels (`configs/pharma.yaml`,
  `docs/medication/PARAMETER_SOURCES.md`).
- Recorded dose times are treated as administration times. The real timing may differ (tested
  in robustness analysis R1).
- **The kernels have not yet been reviewed by a clinical pharmacist**
  (`docs/medication/PHARMACIST_REVIEW.md`).

## Uncertainty and limitations

- Small samples give wide intervals.
- One centre; internal validation only.
- CGM-detected labels: CGM and capillary glucose disagree around 70 mg/dL.
- No forecast is given when recent CGM data are insufficient.
- Attributions (grouped TreeSHAP) are associations, not causes.
- Generalisation is unknown.
