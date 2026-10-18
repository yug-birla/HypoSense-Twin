# Feature Dictionary

Status: **medication groups 7 (M3r) and 8 (M3) are CONTRACTS, implemented as causal state functions
in S3.** Groups 1–6 are specified by Blueprint App. D and will be implemented in S4. Every
feature at time t uses only information with timestamp ≤ t (bitwise truncation-equality tests).
Missing values are NaN, never 0. Each optional feature carries an `_missing` indicator, added by
the S4 feature builder.

| Group | Models | Source module |
|---|---|---|
| 1 CGM level · 2 CGM trend · 3 CGM variability/history · 4 time | M1–M3 | `features/` (S4) |
| 5 static context (age, sex, BMI, weight, duration, HbA1c, eGFR, C-peptide, prescribed-regimen flags) | M2–M3 | `features/` (S4); regimen flags from `medication.recording.prescribed_classes` |
| 6 meal timing | M2–M3 | `features/` (S4) |
| **7 raw medication timing** | **M3r only** | `medication/timing.py::raw_timing` + shared engine flags |
| **8 medication exposure state** | **M3 only** | `medication/exposure.py::ExposureEngine.compute` |

M2 and M3 differ **only** by group 8. M2 and M3r differ only by group 7 (CLAUDE.md §5).

## Group 7 — raw medication timing (M3r; 19 variables)

Categories: **insulin_bolus** (rapid, regular and premix injections; CSII boluses), **insulin_basal**
(basal analogue and NPH injections), **su**, **glinide**.

| Variable (per category) | Unit | Definition | Missing |
|---|---|---|---|
| `<cat>_min_since_last` | min | t − latest administration ≤ t, capped at 1440 | NaN if none logged before t |
| `<cat>_last_dose` | IU / mg | dose of that administration | NaN if none, or dose unknown |
| `<cat>_dose_24h` | IU / mg | total dose with ts in (t − 24 h, t] | NaN if any dose in the window is unknown |
| `<cat>_n_24h` | count | administrations in (t − 24 h, t] | — |
| `csii_active` | 0/1 | a programmed basal rate is in force at t (≤ 6 h after its entry, not suspended) | — |
| `csii_rate_iu_h` | IU/h | the current programmed basal rate (0 if none) | — |
| `iv_insulin_recent` | 0/1 | an i.v. insulin bag logged in (t − 4 h, t] | — |

## Group 8 — medication exposure state (M3; baseline = blueprint representation)

| Variable | Unit | Definition |
|---|---|---|
| `act_prandial` | IU/h | Σ dose × weight × a(t − tᵢ) over rapid-analogue and regular-human components (including premix fast fractions and CSII bolus/basal micro-boluses) |
| `act_intermediate` | IU/h | the same for NPH components (NPH injections; protamine fraction of premixes) |
| `act_basal` | IU/h | the same for basal analogues (flat kernels) |
| `act_insulin_total` | IU/h | sum of the three |
| `iob_insulin` | IU | insulin on board, Σ dose × (1 − A(t − tᵢ)), over all insulin components (basal included) |
| `insulin_p30`, `insulin_p60` | IU/h | total insulin activity at t + 30 / t + 60 from doses with ts ≤ t, plus continuation of the currently programmed CSII basal rate. Never assumes future injections |
| `act_su` | dimensionless | Σ (dose / D_max) × peak-normalised Bateman curve (formulation-specific for gliclazide) |
| `su_p30`, `su_p60` | dimensionless | `act_su` projected from past doses |
| `act_glinide`, `glinide_p30`, `glinide_p60` | dimensionless | as SU, for glinides |
| `min_since_insulin`, `min_since_su`, `min_since_glinide` | min | capped at 1440. NaN if never logged |
| `csii_active`, `csii_rate_iu_h`, `iv_insulin_recent` | — | as group 7 (shared flags) |
| `quality_insulin`, `quality_sulfonylurea`, `quality_glinide` | enum code | KNOWN / PARTIAL / TIMING_UNKNOWN / DOSE_UNKNOWN / FORMULATION_UNKNOWN / NO_LOGGED_MEDICATION |

S4 derives `delta_insulin_60 = insulin_p60 − act_insulin_total` and `delta_su_60 = su_p60 − act_su`,
the Δexposure terms of Blueprint App. D. It also derives `act_insulin_total_per_kg` when weight is
known.

### Missing / uncertainty semantics (Blueprint Table 12.1, S3 brief §3.15)

- **TIMING_UNKNOWN**: the class is prescribed (summary sheet) but nothing has been logged within
  36 h, and no pump segment is active. Its exposure variables are NaN.
- **DOSE_UNKNOWN** and **FORMULATION_UNKNOWN**: an affected administration is still within its
  kernel support. That class's variables are NaN.
- **PARTIAL**: the values are computed, but one of the following applies:
  - an inferred formulation (gliclazide 15 mg);
  - an i.v. insulin bag within 4 h, whose rate is unknown;
  - pump delivery unknown after the 6-h continuation cap (within 24 h).
- **NO_LOGGED_MEDICATION**: the class is neither prescribed nor logged. Variables are 0, which is a
  true zero.

### Conventions

- **Dose at exactly t:** a dose charted at t is known at t. Its activity is 0 at τ = 0, its
  on-board value is the full dose, and minutes-since is 0.
- **Summation:** exact (`math.fsum`), so full and truncated records give bitwise-identical values.
- **Not clinically validated:** kernels are population-level label-derived shapes
  (docs/medication/PARAMETER_SOURCES.md). They are neither patient-specific nor dosing tools.

## Groups excluded by design

- "Hypoglycemia (yes/no)" and any patient identifier: never features.
- Treated status: population definition only, never a model input.
- i.v. glucose: a confounder / data-quality flag only (S3.6). Not a feature: 3 events, E only,
  rate unknown.
