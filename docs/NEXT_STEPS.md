# Next Steps

Ordered execution queue. Updated: 2026-10-18 (end of S4).
Each item lists: objective · dependency · acceptance criteria · difficulty · parallel? ·
approval needed?

## P0 — Blocking

1. **S5 — Evaluation harness and M0**  ← *next task (not started)*
   - Objective:
     - `evaluation/` implementing ANALYSIS_PLAN §2–3 exactly, plus §0c (SA9): causal policy
       replay semantics, episode hits and lead time, notifications with the 60-min cooldown,
       TRUE / FALSE / OUTCOME-UNKNOWN classes, FA / patient-day, operating curve with the
       first-crossing rule, sens@budget;
     - paired patient-cluster bootstrap (B = 2,000, seed 2027);
     - M0 using `features.cgm` (ANALYSIS_PLAN §0d) on T, which should reproduce Table A.2.
   - Dependency: S2 labels, S4 features (done).
   - Acceptance:
     - metric unit tests on hand-built fixtures (test-first);
     - bootstrap determinism;
     - Table A.2 reproduced on T (or the differences explained);
     - the freeze guard refuses E.
   - Difficulty: medium · Approval: none (§5–6 of the plan to be written for owner review).

## P1 — Core

1. **S6 — Development experiments on T**, each with its decision rule written first
   (input: `data/processed/features/v1.0.0/tuning_features.parquet` + labels joined offline):
   - M1 tuning;
   - M2 / M3r / M3 ladder;
   - P-B1 calibration benchmark;
   - P-B2 rounds rule;
   - P-B6 sensor-artefact handling;
   - **P-B7 combined secretagogue**;
   - **P-B8 compact M3 / detemir duration** (S4 evidence: keep Δ60, drop the near-duplicate
     projections and per-kg);
   - **P-B9 categorical quality codes; report T-inert columns**;
   - G4.
2. **S7 — Policy** (P-C1; **P-C8b** LOW NOW + SENSOR FAULT SUSPECTED; P-C7 if approved), replay,
   FastAPI + SSE. Parallel from S4.
   - Replay service on `PatientState.try_update` + `FeatureBuilder.snapshot`.
   - Define a recovery policy after SYSTEM_ERROR, e.g. a late or back-dated chart entry (S4
     review finding 6).
   - Use `OutcomeLedger.finalize` at recording end.

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
