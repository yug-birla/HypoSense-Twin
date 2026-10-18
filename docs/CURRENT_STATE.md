# HypoSense Twin — Current Project State

_Last updated: 2026-10-18 (end of S3). This is the canonical snapshot. Read it first, then
[NEXT_STEPS.md](NEXT_STEPS.md) and [PROGRESS.md](PROGRESS.md)._

## Current Phase
**S3 — complete and reviewed.** Next: **S4** (patient state engine + causal feature builder +
truncation-equality test). S4 has **not** been started, per the owner's instruction.

## Overall Status
**IMPLEMENTATION.** Data, labels and medication foundations are verified. No model work yet.

## Completed Components
| Component | Status | Key files | Evidence |
|---|---|---|---|
| S1 data foundation | DONE; G0 PASS, G1 PASS | `src/hyposense/data/` | `ALL-AGG-audit-structural-20261017T2135*` |
| S2 labels + event audit | DONE; G3b TRIGGERED | `src/hyposense/labels/` | `ALL-AGG-audit-events-20261017T2212*`, 48/48 legacy reproduction |
| **S3 drug dictionary + parser** | **DONE** | `configs/drug_dictionary.csv`, `medication/{dictionary,parse,events,recording}.py` | 4,653/4,653 cells recognised |
| **S3 kernels + exposure engine (M3)** | **DONE** | `medication/{kernels,exposure}.py`, `configs/pharma.yaml` v1.0.0 | bitwise truncation equality (synthetic property test + real T) |
| **S3 raw timing (M3r)** | **DONE** | `medication/timing.py` | truncation tests |
| **S3 production treated set** | **DONE** | `artifacts/population/treated_patients.csv` (sha256 `2016d3e3…`) | 72 patients (T 22 / E 50) |
| **G3 / G2 re-check** | **G3 PASS; G2 PASS (production definition, unchanged)** | `artifacts/gates/G3.json`, `G2.json` | `ALL-AGG-audit-medication-20261018T0952*` |
| P-C8 causal sensor-fault flag | DONE (policy and UI handling: S7/S8) | `data/quality.py` | causality test |
| Representation contracts | DONE | `docs/FEATURE_DICTIONARY.md` | — |

## In Progress
None. S3 ended at a clean boundary.

## Pending Components (dependency order)
1. **S4**: PatientState (CGM, exposure, quality, forecast, ledger); feature groups 1–6 and the
   assembly of 7–8 per model level; `feature_spec.json`; truncation-equality test over full
   snapshots; T-only snapshot generation.
2. S5: evaluation harness (ANALYSIS_PLAN §2–3, SA9), M0 on T (Table A.2 should reproduce exactly).
3. S6: M1 tuning; ladder on T; P-B1 (calibration), P-B2, P-B6, P-B7, P-B8; G4.
4. S7 (policy incl. P-C1, P-C8b; P-C7 pending), S8 frontend; FREEZE → S9 → S10.

## Scientific Status
| Item | Status |
|---|---|
| Data | figshare v5 verified (G0, G1) |
| Labels | protocol-exact (48/48 legacy reproduction); v5: 348 L1 episodes / 107,210 prediction times |
| Treated population | **production parser**: 72 (T 22, E 50). Legacy 73: the difference is 2078, whose misplaced acarbose cell was mis-read as insulin |
| G2 | **PASS**, unchanged: 154 E-treated L1 episodes in 30 patients; m_w 9.23; half-width 0.113 |
| G3 | **PASS**: parse 1.0; day coverage median 1.0; timing on the 15-min grid (99.93 %); 50 E-treated with variation |
| G3b | TRIGGERED (consequences in design) |
| Kernels | label-sourced (15/16 verified); remaining ASSUMPTIONS listed; pharmacist review PENDING |
| i.v. glucose | FLAG ONLY (3 events, E only, rate unknown) |
| Sealed evaluation (E) | **SEALED.** Aggregate-only medication statistics; representation QA on T only |

## Current Models
None implemented (M0–M3 in S5/S6; M4 not planned).

## Data Status
- Manifest `5f9d65b4…`; partition `ccdcbce0…`; drug dictionary and pharma hashes in the S3 audit
  provenance.
- Audits (all two-run deterministic, clean commits):
  - structural `…20261017T2135*`;
  - events `…20261017T2212*`;
  - medication `…20261018T0952*` (results_sha256 `29148c8e…`, commit `88cdeac`).

## Testing Status
| Category | Status |
|---|---|
| Unit | 249/249 |
| Leakage / static guards | 12/12 (+ medication truncation property test in unit; full-snapshot truncation in S4) |
| Regression | 9/9 |
| Integration (real data) | 11/11 |
| Lint / format / types | clean; mypy --strict clean (52 files) |

Last full run: `uv run pytest -q` → **281 passed** (2026-10-18).

## UI Status
Not started (S7/S8). P-C8b warning text and timing badges are specified.

## Open Issues
| Issue | Severity | Proposed solution |
|---|---|---|
| Sensor artefacts in T (2075, 2077) distort development metrics | HIGH for S6 | P-B6 (S6, rule written first) |
| M3 vs M3r substantial overlap (ρ ≈ 0.7–0.8); projections ≈ current (ρ 0.97) | MEDIUM | P-B8 compact-M3 experiment; C2b will quantify |
| Glinide channel empty in T (0 patients) | LOW | P-B7 combined secretagogue candidate |
| Kernel assumptions (gliquidone t½, basal lag, protamine ≈ NPH, Gansulin/SciLin composition) | MEDIUM | Pharmacist review packet; SA6 duration scaling |
| Glimepiride D_max conflict (US 8 vs EU 6 mg) | LOW | Pharmacist review |
| P-C7 warm-up after sensor change | LOW | Hook implemented; decide before S7 |

## Open Decisions
| Decision | Recommendation | Approval required? | Blocking? |
|---|---|---|---|
| P-C7 warm-up restart after gap > 120 min | Approve | Yes | Before S7 |
| P-B1, P-B2, P-B6, P-B7, P-B8 | Run as planned S6 experiments | No (Class B) | — |
| Pharmacist review | Use the packet when a reviewer is available | — | No |

## Last Verified Commit
- Code: `88cdeac` (S3 + provenance fix; official medication audits reference it).
- Documentation and evidence commit: see `git log -1`.
- Date: 2026-10-18.

## Next Recommended Task
**S4: patient state engine and causal feature builder.**
- Implement `PatientState` with deterministic `update()` over ordered events.
- Implement feature groups 1–6 and assemble groups 7–8 from the S3 engines.
- Write `feature_spec.json`.
- Run full-snapshot truncation-equality tests at every model level.
- Generate snapshots for T patients only and profile them.
