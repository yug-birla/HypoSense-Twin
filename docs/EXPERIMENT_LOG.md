# Experiment Log

Append-only index of experiment runs. The full provenance of each run is in
`experiments/runs/<run_id>/manifest.json` (ADR-010). **A result without provenance is not a
valid project result** (CLAUDE.md §13).

Run-ID convention: `<partition>-<model|task>-<seq>`, e.g. `T-M0-001`, `T-M1-tune-001`,
`E-confirm-001`. Partition is `T` (tuning), `E` (sealed; only after freeze), `ALL-AGG`
(aggregate audit, P-C5) or `NONE` (no data).

## Runs executed in this repository

_None yet._ No dataset has been loaded and no model has been trained.

## Evidence inherited from the blueprint (not reproduced here)

| Item | Source | Status in this repo |
|---|---|---|
| Audit counts (Section 8, App. A) | Blueprint author's `audit.py`/`audit2.py` on a GitHub mirror | **NOT REPRODUCED** — scripts not in repo; to be re-derived on the official copy in S1–S3 |
| Exploratory M0 on T (Table A.2: 0.64 sens at 1.07 FA/day, θ=55) | `audit2.py` on mirror, original partition | **NOT REPRODUCED** — target for S5 (numbers may differ if the partition is regenerated, P-C4) |

## Planned runs (Blueprint App. H, Table H.1)

| Run ID | Partition | Model | Purpose | Stage | Status |
|---|---|---|---|---|---|
| ALL-AGG-audit-structural-001 | ALL-AGG | — | G0/G1 structural audit | S1 | PENDING |
| ALL-AGG-audit-events-001 | ALL-AGG | — | G2/G3b event audit | S2 | PENDING |
| ALL-AGG-audit-meds-001 | ALL-AGG | — | G3 medication audit | S3 | PENDING |
| T-M0-001 | T | M0 | exploratory operating curve (compare Table A.2) | S5 | PENDING |
| T-M1-tune-001 | T | M1 | Optuna ≤30 trials, inner log-loss; num_boost_round rule (P-B2) | S6 | PENDING |
| T-calib-bench-001 | T | M1–M3 | calibration benchmark (P-B1) | S6 | PENDING |
| T-ladder-001 | T | M1–M3 | development ladder; Gate G4 | S6 | PENDING |
| E-confirm-001 | E | M0–M3 | **confirmatory, once, after freeze** | S9 | PENDING |

## Entry template

```
## <run_id> — <title>
- Date (UTC):
- Partition / patients:
- Git commit (clean?):
- Dataset manifest hash:
- Config hash:
- Seeds:
- Model / feature / dictionary / kernel versions:
- Package lock hash:
- Hypothesis or purpose:
- Pre-specified decision rule (written BEFORE running):
- Result (MEASURED):
- Interpretation:
- Decision:
- Artefacts:
```
