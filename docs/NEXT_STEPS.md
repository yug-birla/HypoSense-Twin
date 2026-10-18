# Next Steps

Ordered execution queue. Updated: 2026-10-18 (end of S5).
Each item lists: objective · dependency · acceptance criteria · difficulty · parallel? ·
approval needed?

## P0 — Blocking

1. **S6 — Development experiments on T**  ← *next task (not started)*. Write each decision rule
   before the experiment runs.
   - **Inputs:**
     - the tuning feature table for spec v1.0.1 (`data/processed/features/v1.0.1/`, written by run
       T-AGG-audit-features-20261018T133142Z);
     - labels joined offline;
     - the S5 harness, with `EvalRecording` scores joined on (recording_key, ts).
   - **Work:**
     - LightGBM wrapper and artefacts (ADR-009);
     - M1 tuning (≤ 30 Optuna trials, inner grouped CV, log-loss);
     - the M2 / M3r / M3 ladder;
     - P-B1 calibration; P-B2 rounds rule; P-B6 sensor artefacts; P-B7; P-B8; P-B9 (declare the
       quality codes categorical);
     - **G4**: M1 vs M0 on T inner CV, with the M1 operating curve computed.
   - **Acceptance:**
     - G4 evaluated per Table 21.1;
     - every result through `hyposense.evaluation` with provenance and status DEVELOPMENT;
     - window metrics and calibration reported.
   - **Approval:** none (Class B). The owner should confirm ANALYSIS_PLAN §5 before freeze.

## P1 — Core

1. **S7 — Policy** (P-C1; **P-C8b** LOW NOW + SENSOR FAULT SUSPECTED; P-C7 if approved), replay,
   FastAPI + SSE. Parallel from S4.
   - Replay service on `PatientState.try_update` + `FeatureBuilder.snapshot`.
   - Define a recovery policy after SYSTEM_ERROR, e.g. a late or back-dated chart entry (S4
     review finding 6).
   - Use `OutcomeLedger.finalize` at recording end.
   - Extend `policy/decide.py` (S5 core): tags, decision log, acknowledgements.

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
