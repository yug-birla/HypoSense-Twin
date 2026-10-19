# Model card — HypoSense Twin

> **Status: REHEARSAL (development; never evidence).** Generated from a T-only rehearsal of the confirmatory code. These are NOT confirmatory results and must not be cited as evidence.

## Intended use

- Research and decision-support **prototype**. It is NOT a medical device and does not diagnose, treat or recommend medication or insulin doses.
- Output: the risk of a CGM-detected level-1 hypoglycaemia episode (CGM < 70 mg/dL) within 60 min, with a minimum lead of 15 min. The supported action is human review / capillary confirmation.
- Out of scope: outpatient use, paediatrics, populations other than the source dataset, and any autonomous action.

## Model

- Selected by the pre-specified rule: **M3**.
- Final artefact: `data/processed/confirm/T-AGG-rehearsal-20261019T172643Z/models/M3-final-20261019T172643Z` (version `M3-development-3271a3206765`), retrained on all patients with the S7 procedure. Its thresholds are τA 0.1230 and τW 0.0251.
- Learner: LightGBM (S6 hyperparameters, frozen before freeze), seed 2026. Calibration: canonical floored isotonic.
- Alert policy: separate deterministic module (WATCH / ALERT / LOW NOW / INSUFFICIENT DATA / SYSTEM ERROR), 1 false alert per patient-day budget.

## Data

- Source: public ShanghaiT2DM CGM dataset (100 patients with type 2 diabetes, 109 recordings). Patient-level partition: tuning T (30) and sealed evaluation E (70).
- Medication exposure from documented pharmacological kernels (configs/pharma.yaml).
- Kernel review: **no completed clinical-pharmacist review** (docs/medication/PHARMACIST_REVIEW.md).

## Performance (held-out, treated patients)

- sens@1FA: M2 87.5 %, M3 91.1 %; Δ +3.6 pp (95 % CI -4.2 pp to +8.8 pp).
- H1 (medication exposure adds value): **not supported**.
- Full tables: RESULTS.md.

## Limitations

- Single dataset and single centre; no external validation.
- CGM-detected labels, not capillary-confirmed; sensor artefacts are possible.
- Medication records come from retrospective documentation; administration times may be imprecise (R1 jitter analysis).
- Few events per patient; wide confidence intervals.
- No prospective or clinical-outcome evaluation; no claim of clinical benefit.

Source document: `T-AGG-rehearsal-20261019T172643Z` (results SHA-256 `37c4aa0a6d7fbf9567b385bf2c23d93fb14f7576b048cbbe8ce6f61ff7954613`).
