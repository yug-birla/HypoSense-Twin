# HypoSense Twin — Current Project State

_Last updated: 2026-10-18 (end of S6). This is the canonical snapshot. Read it first, then
[NEXT_STEPS.md](NEXT_STEPS.md) and [PROGRESS.md](PROGRESS.md)._

## Current Phase
**S6 — complete and reviewed.** Next: **S7** (policy, replay, API). Owner decisions are pending
before freeze. S7 has **not** been started.

## Overall Status
**IMPLEMENTATION.** Learned models have been developed on T. G4 PASS. E is still sealed.

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
None. S4 ended at a clean boundary.

## Pending Components (dependency order)
1. **S5**:
   - the evaluation harness (ANALYSIS_PLAN §2–3, §0c SA9);
   - paired cluster bootstrap;
   - M0 on T using `features.cgm` (ANALYSIS_PLAN §0d). Table A.2 should reproduce.
2. S6:
   - M1 tuning and the ladder on T;
   - P-B1, P-B2, P-B6, P-B7, P-B8, P-B9;
   - G4.
3. S7 (policy incl. P-C1, P-C8b; P-C7 pending), S8 frontend; FREEZE → S9 → S10.

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
| Frozen candidates (S6) | shared LightGBM hyperparameters (trial #20), 113 rounds, calibrator isotonic_interp (rule-selected, FRAGILE → P-B10), quality codes categorical. P-B6 exclusion: rule met, PENDING implementation and owner decision |
| Sealed evaluation (E) | **SEALED.** S4 used TUNING_ONLY only. Feature generation refuses other scopes, and the adapter refuses E patients (`assert_not_sealed`). No E feature, prediction or per-patient analysis exists. |

## Performance
| Path | Measured |
|---|---|
| Live / replay (serial benchmark, all T) | `update()` 71 µs per event; `snapshot(M3)` 0.66 ms; **0.74 ms per reading** (p99 1.79 ms) |
| Exhaustive validation audit (15 workers) | **~10 min** (runs 4–5), of which truncation is ~8 min by design (independent rebuild per eligible time) |
| Runtime incident | runs 2–3 took 16–19 min: Windows E-core throttling. Fixed by the throttling opt-out (ADR-035). No scientific effect (identical hashes) |

## Testing Status
| Category | Status |
|---|---|
| Unit | 372/372 |
| Leakage / static guards | 18/18 |
| Regression | 10/10 |
| Integration (real data, T / aggregate) | 21/21 |
| Lint / format / types | ruff clean; mypy --strict clean (83 files) |

Last full run: `uv run pytest -q` → **421 passed** (2026-10-18, after the S6 review fixes).

## UI Status
Not started (S7/S8).

## Open Issues
| Issue | Severity | Proposed solution |
|---|---|---|
| Sensor artefacts in T (2075, 2077) distort development metrics | HIGH for S6 | P-B6 (rule written first); 1 eligible T row has a label window overlapping a sensor-floor run |
| Redundancy: projections ≈ current exposure (ρ 0.987–0.999); M3 ≈ M3r for basal / SU | MEDIUM | P-B8 compact M3 (keep Δ60); C2b |
| 21 columns constant on eligible T rows (glinide channel, some static indicators, `su_last_dose`) | MEDIUM for S6 tuning | P-B9 (keep the canonical spec; report inert columns) |
| Quality codes categorical but stored as floats | LOW | P-B9 (declare categorical identically for all models) |
| ANALYSIS_PLAN §5 (bootstrap + §2–3 implementation clarifications) DRAFT | MEDIUM | owner approval before freeze |
| Table A.2 θ = 45 all-patients residual (63/0.79 vs 62/0.77) | LOW | exact-tie bracket; partly demonstrated (DEC-2026-10-18-F) |
| M1 is below a non-learned CGM-level rule on T (0.857 vs 0.911); M0 is a weak reference | MEDIUM (interpretation) | P-C9 |
| Primary endpoint near the ceiling on T (M2 0.875, M3 0.911 vs 0.946); limited headroom for H1 | MEDIUM (scientific) | report honestly; secondary window log-loss |
| Model-fit variance ≥ M2/M3r/M3 differences on T; ladder ordering uninformative (review F3) | MEDIUM (interpretation) | P-B11 |
| Hyperparameters weakly identified (30 trials within 0.004 log-loss) | LOW | shared set frozen; R4 retuning is a robustness analysis |
| S6 evaluation / bootstrap runtime 11–14 min | LOW | acceptable offline |
| Live path: one malformed / back-dated event ends the twin (SYSTEM_ERROR) | LOW (S7) | recovery policy for the replay service in S7 |
| Kernel assumptions; pharmacist review | MEDIUM | review packet; SA6 |
| P-C7 warm-up after sensor change | LOW | hook implemented; decide before S7 |

## Open Decisions
| Decision | Recommendation | Approval required? | Blocking? |
|---|---|---|---|
| P-C7 warm-up restart after gap > 120 min | Approve | Yes | Before S7 |
| P-B1, P-B2, P-B6, P-B7, P-B8, P-B9 | Run as planned S6 experiments | No (Class B) | — |
| ANALYSIS_PLAN §5 draft | Approve | Yes | Before freeze |
| P-C9 level-rule reference baseline | Approve (secondary) | Yes | Before freeze |
| P-B6 training exclusion (implement for all models + rerun ladder, or drop) | Decide | Yes | Before freeze |
| P-B10 floored calibrator / P-B11 fit-variance repeat (Class B, T only) | Run (recommended) | No | Before freeze |
| P-B8 M3_compact as canonical M3 | Keep M3_baseline (preserves the primary definition); compact as secondary | Yes | Before freeze |
| Pharmacist review | Use the packet when a reviewer is available | — | No |

## Last Verified Commit
- Code: `fd34ecf` (S6). The official development runs ran on it, clean and identical.
- Documentation commit: see `git log -1`.

## Next Recommended Task
**S7: policy, replay and API.** Owner decisions are pending before freeze.
