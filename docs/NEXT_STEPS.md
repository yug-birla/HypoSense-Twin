# Next Steps

Ordered execution queue. Updated: 2026-10-18 (end of S2).
Each item lists: objective · dependency · acceptance criteria · difficulty · parallel? ·
approval needed?

## P0 — Blocking

1. **S3 — Medication normalisation and exposure engine (G3)**  ← *next task*
   - Objective:
     - versioned `configs/drug_dictionary.csv`;
     - `parse_dose` (multi-component text, units, plausible ranges, gliclazide formulation
       rule);
     - CSII bolus/basal including pump-suspension text (basal 0), the misplaced "acarbose 50 mg"
       in CSII bolus, the CSII-basal entry and IV fluids in the i.v. column (P-B5), "scilin m30",
       "glarigine", and the sitagliptin/metformin combination;
     - kernels (Eq. 1–6) with label-sourced `pharma.yaml` (P-B3/P-B4 decided a priori);
     - `exposure_at` with causality tests;
     - the production **treated status**, replacing `audit/legacy.py` for scientific use;
     - the aggregate medication audit and G3;
     - **re-evaluate G2** with production treated status and compare with the provisional PASS.
   - Dependency: S2 (done).
   - Acceptance:
     - ≥ 99 % dictionary coverage; no fabricated administration times;
     - the kernel test list in TEST_STRATEGY passes;
     - G3 measured;
     - the treated set is compared with legacy (73) and every difference explained;
     - G2 re-run.
   - Difficulty: high · Parallel: kernel maths needs no data · Approval: pharmacist review if
     available (record status otherwise).

## P1 — Core

1. **S4 — State engine + causal features; truncation-equality test.** Must consume
   `RecordingLabels` and the S3 exposure state. Labels stay offline. · Dependency: S3.
2. **S5 — Evaluation harness implementing ANALYSIS_PLAN §2–3 exactly** (fixtures listed in §4);
   paired cluster bootstrap; ANALYSIS_PLAN §5–6; M0 on T (Table A.2 should reproduce exactly:
   the T data equal the mirror). Metric code can start now (it depends only on S2 labels).
3. **S6 — M1 tuning, M2/M3r/M3 on T, calibration benchmark (P-B1), boosting-round rule (P-B2),
   sensor-artefact handling comparison (P-B6, decision rule written first), G4.**
4. **S7 — Policy (P-C1 approved; P-C7/P-C8 if approved), replay, FastAPI + SSE** · Parallel
   from S4.

## P2 — Product / Demo

1. S8 — Next.js frontend on T-patient replay · parallel from S7.
2. Early submittable version (S0–S5 + minimal S7–S8, labelled DEVELOPMENT).
3. FREEZE → S9 → S10.
4. Remote repository + CI workflow.

## P3 — Enhancements

1. Docker image. 2. LR robustness R3. 3. Carbohydrate estimation E3. 4. E1/M4 not planned.

## Decisions awaiting the owner (non-blocking for S3)

- **P-C8**: sensor-failure rule (≥ 8 consecutive readings ≤ 40 mg/dL), policy tag SENSOR FAULT
  SUSPECTED, new SA9. Needed before S6 tuning / S7 policy.
- **P-C7**: restart warm-up after a CGM gap > 120 min. The hook is implemented; needed before
  S7.

## LOW-PRIORITY / PRE-SUBMISSION (deferred by owner instruction, 2026-10-18)

Do **not** spend development time on these, and do not ask the owner about them, unless they
become genuinely blocking.
- Team name; college name; author ordering.
- Final submission folder naming (`TeamName_CollegeName`) and packaging details.
- Video credits; acknowledgements.
- Final deck branding; final report cover page.
- Final git author identity cleanup.
- LICENSE holder line and DATA_LICENSES.md wording.
