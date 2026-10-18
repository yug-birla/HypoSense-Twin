# Next Steps

Ordered execution queue. Updated: 2026-10-18 (end of S3).
Each item lists: objective · dependency · acceptance criteria · difficulty · parallel? ·
approval needed?

## P0 — Blocking

1. **S4 — Patient State Engine + causal Feature Builder**  ← *next task*
   - Objective:
     - `PatientState` (CGMState with a causal episode tracker, MedicationExposureState wrapping
       the S3 engine, DataQualityState with sufficiency and the P-C8 flag, ForecastState,
       OutcomeLedger) with a deterministic `update()` over ordered events (dose → meal → CGM);
     - feature groups 1–6 (App. D), and assembly of group 7 (M3r) and group 8 (M3) per model
       level with `_missing` indicators;
     - the static allow-list (never the "Hypoglycemia (yes/no)" field);
     - `feature_spec.json`;
     - snapshot generation for **T patients only** (TUNING_ONLY scope);
     - throughput profile.
   - Dependency: S2 labels, S3 engines (done).
   - Acceptance:
     - **full-snapshot truncation equality** (every level, random t incl. dose times, episode
       boundaries and gaps; Hypothesis and real T), bitwise;
     - replay determinism of the state sequence;
     - the ledger never feeds features;
     - feature-spec mismatch raises;
     - leakage suite green.
   - Difficulty: high · Parallel: S5 metric code can start in parallel · Approval: none.

## P1 — Core

1. **S5 — Evaluation harness** implementing ANALYSIS_PLAN §2–3 and §0c (SA9) exactly; paired
   cluster bootstrap; §5–6; M0 on T (Table A.2 should reproduce exactly).
2. **S6 — Development experiments on T**, each with its decision rule written first:
   - M1 tuning;
   - M2 / M3r / M3 ladder;
   - P-B1 calibration benchmark;
   - P-B2 rounds rule;
   - P-B6 sensor-artefact handling;
   - **P-B7 combined secretagogue**;
   - **P-B8 compact M3 / detemir duration**;
   - G4.
3. **S7 — Policy** (P-C1; **P-C8b** LOW NOW + SENSOR FAULT SUSPECTED; P-C7 if approved), replay,
   FastAPI + SSE. Parallel from S4.

## P2 — Product / Demo

1. S8 — Next.js frontend: exposure timeline with quality badges, the P-C8b warning, and the
   data honesty card.
2. Early submittable version (S0–S5 + minimal S7–S8, labelled DEVELOPMENT).
3. FREEZE → S9 → S10.
4. Remote repository + CI.

## P3 — Enhancements

1. Docker image. 2. LR robustness R3. 3. Carbohydrate estimation E3. 4. E1/M4 not planned.

## Decisions awaiting the owner (non-blocking for S4)

- **P-C7** — restart warm-up after a CGM gap > 120 min (hook implemented). Needed before S7.
- Pharmacist review of `docs/medication/PHARMACIST_REVIEW.md`, whenever a reviewer is available.
  It does not block engineering; the review status is reported in every result.

## LOW-PRIORITY / PRE-SUBMISSION (deferred by owner instruction, 2026-10-18)

Do **not** spend development time on these, and do not ask the owner about them, unless they
become genuinely blocking.
- Team name; college name; author ordering.
- Final submission folder naming (`TeamName_CollegeName`) and packaging details.
- Video credits; acknowledgements.
- Final deck branding; final report cover page.
- Final git author identity cleanup.
- LICENSE holder line and DATA_LICENSES.md wording.
