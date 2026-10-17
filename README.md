# HypoSense Twin v2

An exposure-aware patient-state digital twin that forecasts whether a **CGM-detected Level 1
hypoglycaemia episode** will begin within the next 60 minutes (warned ≥15 minutes ahead) in
adults with type 2 diabetes treated with insulin or insulin secretagogues. It then prompts a
human to perform a capillary check.

> **Research and decision-support prototype, for retrospective, silent-mode evaluation.**
> **Not a medical device.** It never recommends, adjusts or simulates doses, and never labels
> a patient "safe".

## Status

**S1 complete.** The official dataset is acquired and verified (Gates G0 and G1 PASS). No model
has been trained. **No performance result exists.** See
[docs/CURRENT_STATE.md](docs/CURRENT_STATE.md).

## The one question this project tests (pre-specified, H1)

In treated patients of the sealed evaluation partition, does adding time-resolved medication
exposure (**M3**) to a strong CGM-plus-context model (**M2**) increase episode sensitivity at
1.0 false alert per patient-day? The question counts as answered only if the paired 95%
patient-cluster bootstrap interval of the difference excludes zero.
Status: **HYPOTHESIS**.

## Where to start

| You want to… | Read |
|---|---|
| Know where the project stands | [docs/CURRENT_STATE.md](docs/CURRENT_STATE.md), [docs/NEXT_STEPS.md](docs/NEXT_STEPS.md) |
| Understand the design | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| See the build sequence | [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) |
| Check that a blueprint requirement is covered | [docs/REQUIREMENTS_TRACEABILITY.md](docs/REQUIREMENTS_TRACEABILITY.md) |
| Review open proposals and decisions | [docs/PROPOSALS.md](docs/PROPOSALS.md), [docs/DECISION_LOG.md](docs/DECISION_LOG.md) |
| Read the specification | [docs/HypoSense_Twin_v2_Blueprint.docx](docs/HypoSense_Twin_v2_Blueprint.docx) (authoritative); [searchable extraction](docs/blueprint/HypoSense_Twin_v2_Blueprint.extracted.md) |

## Development setup

Requirements: Python 3.11, [uv](https://docs.astral.sh/uv/), and Node 20+ for the frontend (S8).

```bash
uv sync                 # creates .venv from uv.lock
uv run pytest           # runs the test suite
uv run hyposense --help # CLI; data acquisition steps are in data/README.md
uv run hyposense gates show
```

## Data

ShanghaiT2DM (Zhao et al., *Scientific Data* 2023; CC BY 4.0;
doi:10.6084/m9.figshare.c.6310860). The data are **not** in this repository. See
[data/README.md](data/README.md).

## Licence

Code: MIT. Data: CC BY 4.0, attributed to the dataset authors.
