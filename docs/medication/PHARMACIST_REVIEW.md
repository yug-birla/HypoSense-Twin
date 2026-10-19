# Clinical-Pharmacist / Clinician Review Packet (S3)

**Status: PHARMACIST REVIEW PENDING (2026-10-19).** No review has been received. This is the
only remaining blocker of the protocol freeze (Blueprint §12.3; DEC-2026-10-19-M):
`hyposense freeze` aborts while `configs/pharma.yaml: reviewed_by` is null and no owner waiver is
recorded. Nothing in this packet is pre-approved.

**Scope of the review: pharmacologic plausibility only.** Please judge whether the medication
mapping and exposure assumptions are reasonable population-level research representations. Do not
judge predictive performance, which is evaluated separately and is not part of this review.

Files under review (hashes are recorded in the freeze record):
- `configs/drug_dictionary.csv`: canonical drug dictionary and class mapping;
- `configs/pharma.yaml`: kernel parameters with per-parameter status, source and note;
- `docs/medication/PARAMETER_SOURCES.md`: the label and literature source for each parameter.

Context: HypoSense Twin is a research and decision-support prototype, **not a medical device**. It
never recommends doses. The kernels below turn *logged* doses into population-level exposure time
courses, which are used as candidate predictors of CGM-detected lows.

## 1. Product mapping (configs/drug_dictionary.csv)

| Source text (as logged) | Mapped to | Kernel components | Confidence |
|---|---|---|---|
| insulin aspart 70/30 | biphasic insulin aspart 30 | 0.30 rapid + 0.70 NPH | composition VERIFIED (label); protamine-aspart ≈ NPH is an ASSUMPTION |
| Novolin 30R, Humulin 70/30 | human premix 30/70 | 0.30 regular + 0.70 NPH | VERIFIED (labels) |
| SciLin M30 | human premix 30/70 | 0.30 regular + 0.70 NPH | ASSUMPTION (only Bioton Gensulin M30 confirmed) |
| Gansulin 40R | human premix 40/60 | 0.40 regular + 0.60 NPH | ASSUMPTION (which fraction is 40 % not confirmed) |
| Novolin R, Gansulin R | regular human | regular | VERIFIED |
| insulin aspart, glulisine | rapid analogue | rapid | VERIFIED |
| insulin glargine (also "glarigine"), detemir, degludec | basal analogues | flat (product-specific duration) | VERIFIED durations; flat shape is an ASSUMPTION |
| CSII bolus / basal (column: Novolin R) | regular human via pump | regular; basal → 15-min micro-boluses | column header = SOURCE FACT |
| gliclazide 30/60/120 mg | gliclazide MR | Bateman MR | dose rule (ASSUMPTION, Blueprint App. B) |
| gliclazide 15 mg | gliclazide MR (half of a 30 mg MR tablet) | Bateman MR | **INFERRED: please confirm** |
| gliclazide 40 mg | gliclazide IR (half of an 80 mg tablet) | Bateman IR | dose rule (ASSUMPTION) |
| glimepiride, gliquidone | sulfonylureas | Bateman | VERIFIED tmax |
| repaglinide | glinide | Bateman | VERIFIED |

## 2. Kernel parameters to confirm (configs/pharma.yaml; sources in PARAMETER_SOURCES.md)

| Kernel | Parameters | Status | Question |
|---|---|---|---|
| rapid analogue | peak 75 min, duration 300 min | label range + OpenAPS | Appropriate for hospitalised T2D? |
| regular human | peak 150 min, duration 480 min | label | Longer at high doses in obesity: acceptable? |
| NPH | peak 390 min, duration 1440 min | label (was 900 min in the blueprint) | Confirm a 24-h duration |
| glargine / detemir | flat 1440 min after a 60-min lag | duration from label; lag and shape are ASSUMPTIONS | Detemir duration is dose-dependent |
| degludec | flat 2520 min after 60 min | label (≥ 42 h) | — |
| gliclazide MR | t½ 16 h, tmax 9 h, D_max 120 mg | midpoints of label ranges | A Bateman curve cannot reproduce the 6–12 h plateau |
| gliclazide IR | t½ 11 h, tmax 4 h, D_max 320 mg | midpoints | — |
| glimepiride | t½ 6.5 h, tmax 2.5 h, D_max 8 mg | label (EU says 6 mg) | Which D_max applies to Chinese practice? |
| gliquidone | t½ 3 h (**assumption**), tmax 2.5 h, D_max 120 mg | t½ unverified | Supply a primary source for t½ |
| repaglinide | t½ 1 h, tmax 1 h, D_max 16 mg | label | — |

## 3. Data-handling rules to confirm

1. **CSII basal:** a programmed rate is assumed to continue at most 6 h after its entry. Logged
   segments are 3–5 h. In all 21 recordings where pump entries stop early, s.c. insulin follows,
   which indicates a switch from pump to injections.
2. **Pump suspension text** means delivery is 0 from that time until the next rate entry.
3. **i.v. insulin bags** (insulin added to saline or 5 % glucose with KCl): the infusion rate is
   not recorded, so they are a flag only, with no kernel.
4. **i.v. 5 % glucose** is not insulin exposure. It is a confounder flag only (3 events).
5. **Dose times** are the charted row times, at 15-min resolution. That they reflect actual
   administration time is an ASSUMPTION; robustness test R1 jitters them.
6. **Implausible units on non-target drugs** (e.g. "voglibose 0.2 g") are kept as written and
   flagged, never corrected.

## 4. Unknown timing and unknown dose

- **No guessed times.** An administration time is never fabricated. If the regimen lists a drug
  class but no entry is logged within 36 h (`medication.timing_unknown_after_h`), exposure
  features are **missing, not zero**. The forecast carries a "medication timing unknown" tag,
  and the UI shows "Timing unknown: <class>".
- **Missing dose.** An entry with no parsable dose is quality DOSE_UNKNOWN. No dose is imputed.
- **Unknown formulation.** A formulation that cannot be identified is quality
  FORMULATION_UNKNOWN. Dose-rule inferences (e.g. gliclazide 15 mg → MR) are flagged INFERRED.
- **Unknown pump delivery.** Pump delivery beyond the 6-h continuation cap is UNKNOWN (quality
  PARTIAL for 24 h, ADR-026).

## 5. Questions for the reviewer (pharmacologic plausibility only)

1. Is any drug classified incorrectly (section 1)?
2. Are any action-duration assumptions unreasonable (section 2)? In particular, consider NPH
   24 h, degludec ≥ 42 h, gliclazide MR t½ 16 h / tmax 9 h, and the gliquidone t½ ASSUMPTION.
3. Is decomposing premixed insulins into a rapid/regular fraction plus an NPH fraction acceptable
   for a research representation? This includes protamine-aspart modelled with the NPH kernel.
4. Are the insulin exposure kernels plausible population-level approximations? The rapid and
   regular kernels are curvilinear; basal analogues are flat after a 60-min lag.
5. Are the sulfonylurea and glinide representations acceptable? These are Bateman curves scaled
   by dose / D_max, and a Bateman curve cannot reproduce the gliclazide MR 6–12 h plateau.
6. Is the pump handling conservative and reasonable? A programmed basal rate is assumed to
   continue for at most 6 h; suspension text means zero delivery; the reservoir insulin is
   regular human insulin.
7. Is any assumption materially misleading, i.e. one that could cause the exposure state to
   misrepresent a patient's pharmacologic situation in a way that matters?
8. Which assumptions must remain explicitly labelled in reports and in the user interface?

## 6. Explicit assumptions still requiring professional review

- Rapid-analogue peak of 75 min (community-documented curve within the label range).
- Basal-analogue lag of 60 min and flat profile (glargine, detemir); the detemir duration is
  dose-dependent.
- Protamine-aspart ≈ NPH. Gansulin 40R = 40 % regular / 60 % NPH. SciLin M30 = 30/70.
- Gliclazide 15 mg = half of a 30 mg MR tablet (INFERRED). Gliclazide 40 mg = half of an 80 mg IR
  tablet.
- Gliquidone t½ of 3 h (ASSUMPTION; no primary source). Glimepiride D_max of 8 mg (FDA) vs 6 mg
  (EU); the Chinese label has not been checked.
- CSII basal continuation cap of 6 h. i.v. insulin is a 4-h flag only, with no kernel. Dose times
  are the charted row times.

## 7. Reviewer sign-off

Complete and return. The project owner records the result in `configs/pharma.yaml`
(`reviewed_by`) and in the DECISION_LOG. A **material** kernel or medication change stops the
freeze. It is applied on T only, and the affected medication, exposure, causality, feature-audit
and (if feature values change materially) development-ladder checks are rerun before freeze.

| Field | Entry |
|---|---|
| Reviewer name and qualification | |
| Date | |
| Q1–Q8 answers (or "see comments") | |
| Changes required (none / wording only / material) | |
| Assumptions to keep labelled | |
| Comments | |
| Signature | |

