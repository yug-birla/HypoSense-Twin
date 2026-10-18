# Next Steps

Ordered execution queue. Updated: 2026-10-19 (end of S8).
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
2. **Pre-freeze Class B runs on T** ← *next engineering task*:
   - P-B10 (floored calibrator);
   - P-B11 (fit variance);
   - P-B12 (LOW CONFIDENCE definition).
3. Owner decisions (CURRENT_STATE "Open Decisions"): P-C7, P-C9, P-C10, P-B6, P-B8,
   ANALYSIS_PLAN §5, pharmacist review.
4. FREEZE (IMPLEMENTATION_PLAN), then S9.

## P1 — Core

1. S7 done (DEC-2026-10-18-J). Freeze machinery next after S8 (IMPLEMENTATION_PLAN).

## P2 — Product / Demo

1. S8 done (DEC-2026-10-19-K). Remaining polish: P-C10 display once decided; screenshots for
   the submission (T only).
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
