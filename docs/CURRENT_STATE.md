# HypoSense Twin — Current Project State

_Last updated: 2026-10-19 (S9/S10 built and rehearsed on T; freeze blocked by two human gates).
This is the canonical snapshot. Read it first, then [NEXT_STEPS.md](NEXT_STEPS.md) and
[PROGRESS.md](PROGRESS.md)._

## Current Phase
**PRE-FREEZE: EVERYTHING TECHNICAL DONE; FREEZE BLOCKED BY HUMAN GATES.**
- **Branch:** `prefreeze-finalization`. It is not merged to main; the merge happens after the
  freeze record exists.
- **S9 confirmatory runner:** built and fully rehearsed on T (`T-AGG-rehearsal-20261019T070224Z`,
  clean `94a7246`, B = 2000).
  - Its numbers equal the independent S6 run exactly.
  - Held-out replay parity: 0 / 31,416 mismatches.
- **S10 presentation path:** built and frozen with the code.
  - Held-out replay (`serve --held-out`).
  - `GET /api/confirmatory` and the Evidence Confirmatory panel (PENDING).
  - `hyposense report` (results, model card, figures).
- **Freeze candidate:** rebuilt twice on final code `57292dc`, identical (`c0cbe721…`, the same as
  on `a7efa25`).
- **`hyposense freeze`** (2026-10-19, on `7babc4f`): **ERROR — FREEZE ABORTED**. 11 checks pass,
  including 546 Python tests and the frontend suite. The 3 failing checks are all human gates:
  - `pharmacist_review`: no review, no waiver;
  - `class_c_resolved`: P-C11 awaiting;
  - `analysis_plan_final`: §5.7 is marked awaiting approval (P-C11).
- **E is SEALED.** No E feature, prediction or result exists. No `FREEZE.json` exists.

## Overall Status
**FREEZE BLOCKED — PHARMACIST REVIEW REQUIRED (and P-C11 approval).**

## Completed Components
| Component | Status | Key files | Evidence |
|---|---|---|---|
| S1 data foundation | DONE; G0 PASS, G1 PASS | `src/hyposense/data/` | `ALL-AGG-audit-structural-20261017T2135*` |
| S2 labels + event audit | DONE; G3b TRIGGERED | `src/hyposense/labels/` | `ALL-AGG-audit-events-20261017T2212*` |
| S3 medication (parser, exposure M3, raw timing M3r, treated set) | DONE; G3 PASS, G2 PASS | `src/hyposense/medication/` | `ALL-AGG-audit-medication-20261018T0952*` |
| **S4 Patient State Engine** | **DONE** | `src/hyposense/state/` (events, history, cgm, quality, medication, context, ledger, patient, stream) | unit + leakage tests; causal tracker = labels (33,464 T readings, 0 mismatches) |
| **S4 causal Feature Builder** (offline = replay) | **DONE** | `src/hyposense/features/` (spec, cgm, context, medication, snapshot, build, export) | truncation 31,292 / 0; parity 133,856 / 0; perturbation 1,200 / 0 |
| **S4 feature specification v1.0.0** | **DONE, locked** | `features/spec.py` → `artifacts/features/feature_spec.json` (v1.0.1, sha256 `90329804…`) | regression lock; docs/FEATURE_DICTIONARY.md |
| **S5 evaluation harness + policy core + M0 + bootstrap** | **DONE** | `src/hyposense/evaluation/`, `policy/decide.py`, `models/m0.py`, `artifacts/evaluation/metric_registry.json` | Table A.2 7 MATCH + 1 EXPECTED; `T-AGG-eval-m0-20261018T1406*`/`T1407*` (results `7864a0d0…`, identical) |
| **S6 learned-model development (T)** | **DONE; G4 PASS** | `models/lgbm.py`, `calibration/methods.py`, `evaluation/{folds,devdata,s6_run}.py` | `T-AGG-dev-s6-20261018T1444*`/`T1500*` (results `e81268ae…`, identical); `artifacts/gates/G4.json` |
| **S8 frontend** | **DONE** | `frontend/` (Next.js static export), `api/` display + evidence fields, `evaluation/s8_evidence.py`; docs/FRONTEND.md | `T-AGG-dev-evidence-20261018T184314Z` (curves `18cb4d0e…`); `T-AGG-s8-ui-audit-20261018T190216Z` (a11y, 0 violations); DEC-2026-10-19-K |
| **S7 policy, replay, API** | **DONE** | `policy/{decide,messages}.py`, `models/artifact.py`, `replay/{runner,session}.py`, `api/{app,schemas,service}.py`, `evaluation/{s7_artifact,s7_bench}.py` | `T-AGG-s7-engineering-20261018T163321Z` / `T-AGG-s7-engineering-20261018T163810Z` (results `6d2517cd…`, identical); DEC-2026-10-18-J |
| **S4 feature audit (T only)** | **DONE** | `audit/features.py`, `hyposense audit features` | `T-AGG-audit-features-20261018T1215*`, `T1225*` (results_sha256 `db39f39a…`, identical in runs 2–5) |

## Model Feature Contracts (verified from features/spec.py)
| Level | Groups | Features |
|---|---|---|
| M1 | G1 CGM level, G2 CGM trend, G3 CGM variability/history, G4 time | 38 |
| M2 | M1 + G5 static context, G6 meal timing | 72 |
| M3r | M2 + G7 raw medication timing + G78 CSII / i.v. flags | 95 |
| M3 | M2 + G8 exposure state + G78 CSII / i.v. flags | 100 |

M3 − M2 is exactly G8 ∪ G78, and M3r − M2 is exactly G7 ∪ G78 (`test_level_membership`).

## In Progress
None. Work stopped at the freeze boundary (human gates).

## Pending Components (dependency order)
1. Pharmacist review or explicit owner waiver (human). Owner approval of P-C11.
2. `hyposense freeze` → merge `prefreeze-finalization` to main.
3. S9: `hyposense confirm --freeze artifacts/freeze/FREEZE.json`, exactly once.
4. S10:
   - `hyposense report` → docs/results/;
   - held-out demo (`serve --held-out`) with the demo cases of ANALYSIS_PLAN §5.7 item 30;
   - screenshots;
   - final honesty review.

## Scientific Status
| Item | Status |
|---|---|
| Data | figshare v5 verified (G0, G1) |
| Labels | protocol-exact; v5: 348 L1 episodes / 107,210 prediction times |
| Treated population | 72 (T 22, E 50) |
| Gates | G0 PASS · G1 PASS · G2 PASS · G3 PASS · G3b TRIGGERED (artifacts/gates/) |
| Kernels | label-sourced (15/16 verified); pharmacist review PENDING |
| Causality (S4) | **bitwise truncation equality at every eligible T time; future perturbation 0 / 1,200; parity 0 / 133,856** |
| Static context | labs and prescribed regimen are recording-level context (Blueprint §10.2); labs removed in SA8; regimen timing documented (ADR-033) |
| M0 (DEVELOPMENT, T) | sens@1FA 0.626 (95 % CI 0.491–0.837) treated, 0.610 (0.418–0.810) all; θA 54.0 / 52.2 mg/dL; precision 0.12 / 0.16; median lead 45 / 30 min |
| Gates | **G4 PASS** (tests, pipeline on T, M1 curve) |
| Ladder (DEVELOPMENT, treated T, sens@1FA) | M0 0.626 · M1 0.857 · M2 0.875 · M3r 0.929 · M3 0.911 (ceiling 0.946). C0 +0.231 (0.094–0.437). C1 / C2a / C2b / M3−M2 intervals include 0 |
| DEVELOPMENT artefact (S7) | `M3-development-9590a582b0c1` (T only; τA 0.123, τW 0.025); rebuild bitwise identical |
| Freeze candidate (DEC-2026-10-19-M) | full M3, S6 hyperparameters at full precision, 113 rounds, seed 2026, `isotonic_interp_floored` (P-B10 verdict INCONCLUSIVE preserved), no P-B6 exclusion (sensitivity only); `M3-development-3271a3206765`, τA 0.1230, τW 0.0251 |
| Sealed evaluation (E) | **SEALED.** S4 used TUNING_ONLY only. Feature generation refuses other scopes, and the adapter refuses E patients (`assert_not_sealed`). No E feature, prediction or per-patient analysis exists. |

## Performance
| Path | Measured |
|---|---|
| Live / replay (serial benchmark, all T) | `update()` 71 µs per event; `snapshot(M3)` 0.66 ms; **0.74 ms per reading** (p99 1.79 ms) |
| Exhaustive validation audit (15 workers) | **~10 min** (runs 4–5), of which truncation is ~8 min by design (independent rebuild per eligible time) |
| Runtime incident | runs 2–3 took 16–19 min: Windows E-core throttling. Fixed by the throttling opt-out (ADR-035). No scientific effect (identical hashes) |

## Testing Status
| Suite | Result |
|---|---|
| Python (unit, leakage, regression, integration, E2E) | **546 passed** (inside `hyposense freeze`, 2026-10-19, on `7babc4f`) |
| Frontend (Vitest) | **33 passed** |
| Lint / format / types | ruff clean; mypy --strict clean (104 files); tsc strict clean |

## Engineering (S7, T)
- **Latency:** per reading p50 1.5 ms / p99 4.5 ms; API ward p50
  3.2 ms.
- **Parity:** offline vs live, 0 mismatches.
- **Determinism:** identical decision logs.
- **Error injection:** no poisoning.

## UI Status
**Built (S8).** Ward board, Patient review, Evidence; replay controls; SSE live updates; acknowledgement.
`cd frontend && npm ci && npm run build`, then `uv run hyposense serve`. Accessibility: 0 WCAG A/AA
violations (axe). Desktop/laptop/tablet ≥ 1024 px. Design and contracts: docs/FRONTEND.md.

## Open Issues
| Issue | Severity | Status / mitigation |
|---|---|---|
| Freeze blocked: pharmacist review absent; P-C11 awaiting | **BLOCKING** | Human action; nothing is bypassed or fabricated |
| Primary endpoint near the ceiling on T (M2 0.875, M3 0.911 vs 0.946); limited headroom for H1 | MEDIUM (scientific) | Report honestly; S2/S3 secondary |
| Model-fit variance ≥ the M2/M3 differences on T | MEDIUM (interpretation) | P-B11: M3 ≥ M2 in 15/15 configurations; SA7 seeds reported |
| R3 logistic regression overfits the patient-level `rx_*` flags (T rehearsal sens 0.30) | LOW (disclosed) | ANALYSIS_PLAN §5.7 item 26; learner unchanged |
| R2 CGM removal lowers sensitivity strongly (random 20 %: ~0.5 on T) | LOW (expected: sufficiency abstention) | Reported as robustness, not tuned |
| M1 below a non-learned CGM-level rule on T (0.857 vs 0.911) | MEDIUM (interpretation) | P-C9: post-hoc reference only |
| Floored calibrator compresses the low tail (fold-4 floor) | LOW (disclosed) | ANALYSIS_PLAN §5.4 item 12 |
| Stale placeholder test names in traceability rows P-01–P-05 and FZ-07 | LOW (docs) | The real tests are named in those rows' notes |
| No Dockerfile; no LICENSE file | LOW | Not required for the demo path |

## Open Decisions
| Decision | Recommendation | Approval required? | Blocking? |
|---|---|---|---|
| Pharmacist review of kernels | Use the packet (docs/medication/PHARMACIST_REVIEW.md) | Human reviewer, or explicit owner waiver | **Yes (freeze)** |
| P-C11 operational definitions of S9 (ANALYSIS_PLAN §5.7 items 1–33) | Approve | Yes (Class C) | **Yes (freeze)** |

All earlier decisions are resolved: §6 reading (DEC-2026-10-19-N); P-B6, P-B8, P-B10, P-B12, P-C7,
P-C9 and P-C10 (DEC-2026-10-19-M). The LLM layer was dropped.

## Last Verified Commit
- Code: `94a7246` (S9/S10). The candidate pair ran on `57292dc`, which has no code change since
  `94a7246`. The freeze attempt ran on `7babc4f`.
- Documentation commit: see `git log -1`.

## Next Recommended Task
1. **Human:** complete the pharmacist review (docs/medication/PHARMACIST_REVIEW.md), or have the
   owner explicitly approve a waiver.
2. **Owner:** approve P-C11 (ANALYSIS_PLAN §5.7 items 1–33).
3. Then:
   - `uv run hyposense freeze`
   - merge to main
   - `uv run hyposense confirm --freeze artifacts/freeze/FREEZE.json` (once)
   - `uv run hyposense report`
   - `uv run hyposense serve --held-out`

Do not run S9 before a freeze record exists.
