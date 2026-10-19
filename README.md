# HypoSense Twin v2

An exposure-aware patient-state digital twin that forecasts whether a **CGM-detected Level 1
hypoglycaemia episode** will begin within the next 60 minutes (warned ≥15 minutes ahead) in
adults with type 2 diabetes treated with insulin or insulin secretagogues. It then prompts a
human to perform a capillary check.

> **Research and decision-support prototype, for retrospective, silent-mode evaluation.**
> **Not a medical device.** It never recommends, adjusts or simulates doses, and never labels
> a patient "safe".

## Status

| Stage | Status |
|---|---|
| S1–S8 data, labels, medication exposure, state engine, features, evaluation harness, models, policy, replay, API, frontend | **DONE** (development on the tuning partition T only) |
| S9 confirmatory runner and S10 presentation path (held-out replay, Evidence panel, report generator) | **BUILT and rehearsed on T**; not run on E |
| Protocol freeze | **BLOCKED.** It needs (1) a clinical-pharmacist review of the medication kernels and (2) owner approval of P-C11 (ANALYSIS_PLAN §5.7) |
| Confirmatory result (sealed partition E) | **PENDING.** E has never been opened |

Details: [docs/CURRENT_STATE.md](docs/CURRENT_STATE.md) and [docs/NEXT_STEPS.md](docs/NEXT_STEPS.md).

## The one question this project tests (pre-specified, H1)

In treated patients of the sealed evaluation partition, does adding time-resolved medication
exposure (**M3**) to a strong CGM-plus-context model (**M2**) increase episode sensitivity at
1.0 false alert per patient-day? The question counts as answered only if the paired 95%
patient-cluster bootstrap interval of the difference excludes zero.
Status: **HYPOTHESIS** (untested on E).

### Development evidence (T only, DEVELOPMENT, not confirmatory)

These numbers come from nested patient-grouped CV on the 30 tuning patients (22 treated, 56
episodes), in run `T-AGG-dev-s6-20261018T1444*`. Hyperparameters, calibration and thresholds were
chosen on T, so the numbers are optimistic and must not be read as the H1 answer.

sens@1FA, treated patients:

| Model | sens@1FA |
|---|---|
| M0 trend baseline | 0.626 |
| M1 CGM | 0.857 |
| M2 + context | 0.875 |
| M3r + raw medication timing | 0.929 |
| M3 + exposure | 0.911 |

M3 − M2 = +3.6 pp, and the 95 % CI includes 0.

## Model ladder

| Level | Inputs | Features |
|---|---|---|
| M0 | deterministic CGM trend score | — |
| M1 | CGM level, trend, variability, time | 38 |
| M2 | M1 + static context + meal timing | 72 |
| M3r | M2 + raw medication timing | 95 |
| M3 | M2 + medication exposure state (documented kernels) | 100 |

## Reproduce (CLAUDE.md §49)

Requirements: Python 3.11, [uv](https://docs.astral.sh/uv/), Node 20+.

```bash
uv sync                                   # .venv from uv.lock
uv run hyposense --help                   # every step below is a CLI command
# 1. data: acquisition and verification steps are in data/README.md (figshare, SHA-256 pinned)
uv run hyposense gates show               # G0–G4 gate status
# 2–4. structure, labels, medication, features (audits; features on T only before freeze)
uv run hyposense audit run
uv run hyposense audit events
uv run hyposense audit medication
uv run hyposense audit features
# 5. development models on T (S6 ladder; ~15 min)
uv run hyposense dev s6
uv run hyposense dev candidate            # freeze-candidate artefact (run twice; must be identical)
# 6. confirmatory pipeline rehearsal on T (identical code; REHEARSAL, never evidence)
uv run hyposense confirm --rehearsal
uv run hyposense report --rehearsal T-AGG-rehearsal-<ts>
# 7. freeze (fails closed unless every invariant holds), then S9 exactly once
uv run hyposense freeze
uv run hyposense confirm --freeze artifacts/freeze/FREEZE.json
uv run hyposense report                   # docs/results/: RESULTS.md, MODEL_CARD.md, figures
# 8. demo
cd frontend && npm ci && npm run build && cd ..
uv run hyposense serve                    # T replay with the development model
uv run hyposense serve --held-out         # after S9: E patients with their own fold models
uv run pytest -q && (cd frontend && npx vitest run)
```

Open http://127.0.0.1:8000 for the Ward board, Patient review and Evidence view.

## Safeguards

- **Sealed partition.**
  - E is refused by the dataset loader, the feature adapter and the stream builder.
  - Only a verified freeze record can unlock it: hashes of the code tree, configs, data,
    partition, analysis plan, locks and candidate artefact must match.
  - The confirmatory runner refuses a second official run.
- **Leakage.**
  - Bitwise truncation equality holds at every eligible T time.
  - Perturbing future events changes no feature (0 / 1,200).
  - Offline features equal live features (0 / 133,856 mismatches).
- **Model and policy are separate modules.** Low predicted risk is distinct from INSUFFICIENT
  DATA, and an inference failure shows SYSTEM ERROR, never an old prediction.

## Where to start

| You want to… | Read |
|---|---|
| Know where the project stands | [docs/CURRENT_STATE.md](docs/CURRENT_STATE.md), [docs/NEXT_STEPS.md](docs/NEXT_STEPS.md) |
| Understand the design | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/FRONTEND.md](docs/FRONTEND.md) |
| Read the frozen-to-be analysis plan | [docs/protocol/ANALYSIS_PLAN.md](docs/protocol/ANALYSIS_PLAN.md) |
| Check that a blueprint requirement is covered | [docs/REQUIREMENTS_TRACEABILITY.md](docs/REQUIREMENTS_TRACEABILITY.md) |
| Review proposals, decisions and runs | [docs/PROPOSALS.md](docs/PROPOSALS.md), [docs/DECISION_LOG.md](docs/DECISION_LOG.md), [docs/EXPERIMENT_LOG.md](docs/EXPERIMENT_LOG.md) |
| Review the medication kernels | [docs/medication/PHARMACIST_REVIEW.md](docs/medication/PHARMACIST_REVIEW.md) |
| Read the specification | [docs/HypoSense_Twin_v2_Blueprint.docx](docs/HypoSense_Twin_v2_Blueprint.docx) (authoritative); [searchable extraction](docs/blueprint/HypoSense_Twin_v2_Blueprint.extracted.md) |

## Data

ShanghaiT2DM (Zhao et al., *Scientific Data* 2023; CC BY 4.0;
doi:10.6084/m9.figshare.c.6310860). The data are **not** in this repository. See
[data/README.md](data/README.md).

## Licence

Code: MIT. Data: CC BY 4.0, attributed to the dataset authors.
