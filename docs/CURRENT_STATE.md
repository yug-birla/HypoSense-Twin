# HypoSense Twin — Current Project State

_Last updated: 2026-10-18 (S0 planning run). This file is the canonical snapshot. Read it
first, then [NEXT_STEPS.md](NEXT_STEPS.md) and [PROGRESS.md](PROGRESS.md)._

## Current Phase
**S0 — Repository and environment** (engineering complete; human items open). The next phase
is **S1 — data acquisition and structural audit**.

## Overall Status
**PLANNING** → ready to start IMPLEMENTATION once the P0 human decisions are made.

## Completed Components
| Component | Status | Files | Tests |
|---|---|---|---|
| Blueprint understanding pass + searchable extraction | DONE | `docs/BLUEPRINT_DIGEST.md`, `docs/blueprint/…extracted.md`, `scripts/extract_blueprint.py` | — |
| Git repository (branch `main`) | DONE | `.gitignore`, `.gitattributes` | — |
| Python environment (3.11.9, uv, lockfile) | DONE | `pyproject.toml`, `uv.lock`, `.python-version` | `uv sync` OK |
| Package skeleton (12 subpackages, responsibilities documented; no logic) | DONE | `src/hyposense/**/__init__.py`, `cli.py` (stub) | ruff + mypy strict clean |
| Draft configuration | DONE (DRAFT, unfrozen) | `configs/default.yaml`, `configs/pharma.yaml` (ILLUSTRATIVE) | constant lock |
| Protocol-constant lock | DONE | `tests/regression/test_protocol_constants.py` | 6/6 pass |
| Import-boundary leakage guard | DONE | `tests/leakage/test_import_boundaries.py` | 10/10 pass |
| Project control documents | DONE | `docs/*.md` | — |

## In Progress
None. The run ended at a clean boundary.

## Pending Components (dependency order)
1. S1: official data fetch, MANIFEST, adapter v0, structural audit (G0, G1)
2. S2: schemas, label builder (test-first), event audit (G2, G3b), partition + guard
3. S3: drug dictionary, parser, kernels, exposure, pharma sourcing (G3)
4. S4: state engine, causal features, truncation-equality test
5. S5: evaluation harness, metrics, bootstrap, M0, ANALYSIS_PLAN.md
6. S6: M1 tuning, M2/M3r/M3 on T, calibration benchmark (G4)
7. S7: policy, replay, API (parallel from S4)
8. S8: frontend (parallel from S7)
9. FREEZE → S9 confirmatory → S10 demo and submission

## Scientific Status
| Item | Status |
|---|---|
| Dataset | **NOT PRESENT** in the repository; official copy not yet downloaded |
| Labels | not implemented |
| Partition | **not created.** The blueprint's `partition.csv` and audit scripts are missing (P-C4) |
| Models | none implemented or trained |
| Calibration | not implemented |
| Evaluation | not implemented; operationalisation of the primary endpoint pending (P-C2, P-C3) |
| Sealed evaluation (E) | **SEALED.** No E data accessed by this project; no freeze |
| Blueprint audit numbers | VERIFIED by the blueprint author on a mirror; **NOT REPRODUCED here** |

## Current Models
| Model | Implemented | Trained | Validated | Artefact | Result |
|---|---|---|---|---|---|
| M0 trend | no | n/a | no | no | none |
| M1 CGM-only | no | no | no | no | none |
| M2 CGM + context | no | no | no | no | none |
| M3r raw timing | no | no | no | no | none |
| M3 exposure | no | no | no | no | none |
| M4 (optional) | not planned (ADR-015) | — | — | — | — |

## Data Status
- Dataset available: **no**.
- Official copy verified: **no** (Gate G0 PENDING).
- Hashes: none yet (`data/MANIFEST.sha256` is created in S1).
- Audit completed: **no** (the blueprint audit was on a third-party mirror and is not
  reproducible here).
- Known discrepancies: mirror 112,287 vs published 112,475 CGM readings (−188), per the
  blueprint.

## Testing Status
| Category | Status |
|---|---|
| Unit | none yet |
| Integration | none yet |
| Leakage | import-boundary guard: 10/10 pass (truncation equality pending S4) |
| Reproducibility | none yet |
| Regression | protocol-constant lock: 6/6 pass |
| E2E | none yet |
| Lint / types | ruff clean; mypy --strict clean (14 files) |

Last full run: `uv run pytest -q` → **16 passed** (2026-10-18).

## UI Status
| View | Status |
|---|---|
| Ward Board | not started (S8) |
| Patient Review | not started (S8) |
| Evidence View | not started (S8) |
| Replay | not started (S7) |

## Open Issues
| Issue | Severity | Proposed solution |
|---|---|---|
| Competition registration reportedly closes **18 Oct 2026 19:00 IST** (today); status unknown | **CRITICAL (delivery)** | Owner confirms or registers immediately |
| Blueprint partition file and audit scripts missing from the repo | HIGH | P-C4: request the originals; else regenerate before any modelling |
| Primary endpoint not computable unambiguously (cooldown non-monotonicity, threshold grid, isotonic ties) | HIGH | P-C2 + P-B1 |
| Evaluation semantics for FA counting / policy replay unspecified | HIGH | P-C3 |
| Sensor-floor lows shown as INSUFFICIENT DATA (safety) | MEDIUM | P-C1 |
| Kernel parameters ILLUSTRATIVE; pharmacist availability unknown | MEDIUM | Source from product labels in S3; ask the owner about reviewer access |
| Official dataset not downloaded | HIGH (blocking S1) | S1 task |
| No remote repository or CI | LOW | Create once the owner chooses repo name and visibility |
| CLAUDE.md §2 points to `docs/blueprint/…docx`; file is at `docs/…docx` | LOW | H-1 |
| Machine git identity is "Yug Birla <2006yugb@gmail.com>"; commits are authored with it | LOW | Owner confirms or sets a repo-local identity |

## Open Decisions
| Decision | Options | Recommendation | Approval required? |
|---|---|---|---|
| P-C1 policy priority for current lows | blueprint order / LOW NOW first | LOW NOW first | **Yes** |
| P-C2 operating-curve and τ rule | as written / first-crossing rule | first-crossing rule | **Yes** |
| P-C3 evaluation semantics | unspecified / causal replay + follow-up exclusion | causal replay | **Yes** |
| P-C4 partition provenance | A originals / B regenerate | A, else B | **Yes** |
| P-C5 outcome-blind E access before freeze | none / aggregate-only scope | aggregate-only scope | **Yes** |
| P-C6 τW definition | ambiguous / total notifications, first crossing | total notifications | **Yes** |
| P-B1 calibration method | isotonic / Platt / interpolated isotonic | benchmark on T with a pre-written rule | No (experiment) |
| P-B2 boosting rounds | early stopping / fixed tuned count | fixed tuned count | No (record before S6) |
| P-B3 CSII basal in projections | literal / continue current rate | continue (a priori) | No (record in S3) |

## Last Verified Commit
- Commit: `5314ba9c8e64a06f672a9edbbd1b11b07c3b173c` (branch `main`)
- Date: 2026-10-18
- Summary: S0 baseline — scaffolding, environment, configs, control documents, 16 passing tests.

## Next Recommended Task
**S1 — Acquire the official ShanghaiT2DM copy from figshare, pin it with
`data/MANIFEST.sha256`, implement adapter v0 (column-variant mapping and timestamp parsing),
and run the structural audit for Gates G0/G1.** Fetching and checksumming can start
immediately. The audit pass over E files waits for approval of P-C5.
