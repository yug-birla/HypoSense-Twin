# Next Steps

Ordered execution queue. Updated: 2026-10-18 (end of S1).
Each item lists: objective · dependency · acceptance criteria · difficulty · parallel? ·
approval needed?

## P0 — Blocking

1. **S2 — Schemas, label builder (test-first), event audit (G2, G3b)**  ← *next task*
   - Objective:
     - typed event contracts (`Observation`, `EpisodeLabel`; `DoseEvent`/`MealEvent` shells
       for S3);
     - ≥20 hand-labelled SYNTHETIC fixtures for every Table 5.1 rule, written and seen to fail
       first;
     - `build_episodes` and `eligible_times` on `cgm_series()`;
     - aggregate event audit: L1/L2/single-reading counts, patients with episodes, warnable
       share, prediction times and positives, CGM–CBG agreement for G3b;
     - G2/G3b gate JSON;
     - re-check of the has-L1 strata for 2003/2029 (report only).
   - Dependency: S1 (done).
   - Acceptance:
     - fixtures pass;
     - **figshare v2 reproduces the blueprint's event numbers exactly** (348 L1 / 96 L2 / 430
       single / 61 patients / 107,041 prediction times / 1,188 positives / 306 warnable), or
       every difference is explained;
     - v5 numbers measured and reconciled;
     - G2 and G3b evaluated;
     - the leakage and static suites stay green;
     - labels are offline-only (import guard).
   - Difficulty: medium–high · Parallel: no (critical path) · Approval: none.

## P1 — Core

1. **S3 — Drug dictionary, dose parser, kernels, exposure; G3**
   - Must handle the S1 findings:
     - pump-suspension text → basal rate 0;
     - "acarbose 50 mg" misplaced in CSII bolus;
     - a CSII basal entry and IV fluids (KCl, NaCl, 5% glucose) in the i.v. column (P-B5);
     - "scilin m30"; the typo "glarigine";
     - combination tablet "sitagliptin phosphate/metformin hydrochloride".
   - Also: P-B3/P-B4 a-priori decisions; re-check the treated flag against the partition strata.
   - Dependency: S2 · Acceptance: ≥99% dictionary coverage; all kernel tests; pharma.yaml
     sourced; G3 measured · Difficulty: high · Parallel: kernel maths needs no data ·
     Approval: pharmacist review (if available).
2. **S4 — State engine + causal features; truncation-equality test** · Dependency: S3 ·
   Difficulty: high.
3. **S5 — Evaluation harness implementing ANALYSIS_PLAN §2–3 exactly** (fixtures listed in §4),
   paired cluster bootstrap, ANALYSIS_PLAN §5–6, M0 on T (exact Table A.2 reproduction expected)
   · Dependency: S4 (metric code can start after S2) · Difficulty: high.
4. **S6 — M1 tuning, M2/M3r/M3 on T, calibration benchmark (P-B1), boosting-round rule (P-B2),
   G4** · Dependency: S5 · Difficulty: medium.
5. **S7 — Policy (incl. approved P-C1; P-C7 if approved), replay, FastAPI + SSE** ·
   Dependency: S4 schemas · Parallel: **yes** · Difficulty: medium.

## P2 — Product / Demo

1. **S8 — Next.js frontend** (Ward Board, Patient Review, Evidence view) on T-patient replay ·
   Dependency: S7 API · Parallel: **yes**.
2. **Early submittable version** (S0–S5 + minimal S7–S8, M0 on T replay, labelled DEVELOPMENT).
3. **FREEZE → S9 → S10** per [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).
4. Remote repository + CI workflow (pytest + ruff + mypy on push) · low difficulty.

## P3 — Enhancements (only after P0–P2 are healthy)

1. Docker image for the demo.
2. Logistic-regression robustness run R3 (after S9).
3. Carbohydrate estimation E3 from the English diet text.
4. E1/M4 reduced physiology — not planned (ADR-015).

## Decisions awaiting the owner (non-blocking for S2)

- **P-C7** — restart warm-up after a CGM gap > 120 min (sensor replacement). Needed before S7.

## LOW-PRIORITY / PRE-SUBMISSION (deferred by owner instruction, 2026-10-18)

Do **not** spend development time on these, and do not ask the owner about them, unless they
become genuinely blocking. Handle near submission.
- Team name; college name; author ordering.
- Final submission folder naming (`TeamName_CollegeName`) and submission packaging details.
- Video credits; acknowledgements.
- Final deck branding; final report cover-page details.
- Final git author identity cleanup (commits currently use the machine's global identity).
- LICENSE holder line and DATA_LICENSES.md wording (content is known: MIT code, CC BY 4.0 data).
