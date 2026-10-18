# Clinical-Pharmacist / Clinician Review Packet (S3)

**Status: NOT YET REVIEWED.** This packet lists what a reviewer should confirm or correct. The
software does not depend on the review to run. Every reported result states the review status
(`configs/pharma.yaml: reviewed_by: null`).

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
