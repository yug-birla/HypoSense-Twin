# Next Steps

Ordered execution queue. Updated: 2026-10-18 (end of S6).
Each item lists: objective · dependency · acceptance criteria · difficulty · parallel? ·
approval needed?

## P0 — Blocking

1. **Owner decisions before freeze** (they do not block S7 engineering):
   - ANALYSIS_PLAN §5 draft;
   - **P-C9** (level-rule reference baseline);
   - **P-B8** (M3_compact as canonical M3, or keep the baseline);
   - P-C7;
   - pharmacist review of the kernels;
   - **P-B6** (implement the exclusion for all models and rerun the ladder, or drop it);
   - ANALYSIS_PLAN §5 must also state the pre-registration gaps from review F6 (P-B8
     population, metric clip, raw vs calibrated scores for P-B6).
   - Recommended Class B runs on T before freeze: **P-B10** (floored calibrator) and
     **P-B11** (fit-variance repeat).
2. **S7 — Policy, replay, API**  ← *next engineering task (not started)*:
   - extend `policy/decide.py` (tags, P-C8b, decision log, acknowledgements);
   - replay service on `PatientState.try_update` + `FeatureBuilder.snapshot` + frozen M3 /
     calibrator;
   - SYSTEM_ERROR recovery;
   - FastAPI + SSE;
   - `OutcomeLedger.finalize`.

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
