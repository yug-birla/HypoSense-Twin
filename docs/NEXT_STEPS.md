# Next Steps

Ordered execution queue. Updated: 2026-10-19 (S9/S10 built and rehearsed; freeze blocked by human
gates). Each item lists its objective, dependency, acceptance criteria and whether approval is
needed.

## P0 — Blocking (human)

1. **Pharmacist review** of the medication kernels: docs/medication/PHARMACIST_REVIEW.md.
   - **No change or wording only:** fill the sign-off table and set `configs/pharma.yaml
     reviewed_by`.
   - **Material change:** apply it on T only, then rerun:
     - the medication, exposure, causality and feature audits;
     - the ladder, if feature values change;
     - `hyposense dev r4`;
     - the rehearsal;
     - `hyposense dev candidate` twice.
   - **Alternative:** an explicit, recorded owner waiver. It is never assumed.
2. **Owner approval of P-C11:** ANALYSIS_PLAN §5.7 items 1–33.
   - Change the §5.7 status line and the P-C11 status to APPROVED.
   - Add a DECISION_LOG entry.
   - Then rerun the candidate pair only if CODE_PATHS changed. A docs-only change does not
     require it.

## P0 — Then (agent, mechanical; do not change anything in between)

3. `uv run hyposense freeze`. All checks must PASS, and `artifacts/freeze/FREEZE.json` is
   written. Commit it.
4. Merge `prefreeze-finalization` into main, then verify the freeze record on main:
   `verify_freeze_record`, which the confirm command performs.
5. `uv run hyposense confirm --freeze artifacts/freeze/FREEZE.json`, **exactly once**.
   - Expected runtime about 35 min, at 4 workers.
   - Commit `experiments/runs/E-AGG-confirm-*`; row-level outputs stay private.
   - If a software bug appears afterwards: STOP and document it. Never silently fix and
     rerun.
6. S10:
   - `uv run hyposense report` → docs/results/ (RESULTS.md, MODEL_CARD.md, figures);
   - `hyposense serve --held-out` with the demo cases;
   - screenshots;
   - EXPERIMENT_LOG / PROGRESS / CURRENT_STATE with the honest verdict. A negative result is
     a valid result.

## P2 — Product / Demo

0. DONE (2026-10-19): the new-data intake, Ask panel and live sessions are verified in Edge
   (DEC-2026-10-19-P). The demo runs now: `uv run hyposense serve`.

1. The demo story uses held-out replay of the pre-selected TP/FN/FP cases (§5.7 item 30). No
   cherry-picking.
2. Remote repository and CI.

## P3 — Enhancements

1. Docker image. 2. LICENSE file. 3. Carbohydrate estimation E3. 4. E1/M4 not planned.

## LOW-PRIORITY / PRE-SUBMISSION (deferred by owner instruction, 2026-10-18)

Do **not** spend development time on these, and do not ask the owner about them, unless they
become genuinely blocking.
- Team name; college name; author ordering.
- Final submission folder naming (`TeamName_CollegeName`) and packaging details.
- Video credits; acknowledgements.
- Final deck branding; final report cover page.
- Final git author identity cleanup.
- LICENSE holder line and DATA_LICENSES.md wording.
