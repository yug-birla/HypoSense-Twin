# Decision Log (Architecture Decision Records)

Append-only. Superseded decisions are marked, never deleted.
Fields: Decision · Context · Alternatives · Evidence · Reason · Consequences · Class · Date ·
Commit. Pending scientific decisions are in [PROPOSALS.md](PROPOSALS.md) until approved.

---

## ADR-001 · Build architecture D: exposure-aware risk twin (inherited from blueprint)
- **Decision**: Implement Blueprint v2.0 architecture D. M3 is the proposed model, M2 the
  primary comparator, and M0/M1 are reported baselines. The physiological ODE and UKF are
  removed from the predictive path.
- **Context / Alternatives / Evidence**: Blueprint §4.1–4.3 (Table 4.1, ADR-001 in the
  blueprint).
- **Reason**: It is the only design that tests the central idea cleanly with identifiable
  components.
- **Consequences**: The fallback branches of Table 20.4 and §21 apply unchanged.
- **Class**: C (accepted as the protocol baseline) · **Date**: 2026-10-18 · **Commit**: initial

## ADR-002 · Repository layout: `src/hyposense/<subpackages>`, `configs/`, `artifacts/`
- **Decision**: Use an installable `src/`-layout package with subpackages data, labels,
  medication, state, features, models, calibration, policy, evaluation, replay, api and common.
  Configuration lives in `configs/` and frozen artefacts in `artifacts/`.
- **Context**: The blueprint (§24) uses a flat `hyposense/` package with `config/` and
  `artefacts/`. CLAUDE.md §20 suggests `src/` with these subpackages.
- **Alternatives**: the blueprint's flat layout.
- **Evidence**: The `src/` layout stops tests from importing the working directory by
  accident. Subpackages make import-boundary tests possible (ADR-014).
- **Reason**: Module boundaries that tests can enforce, especially live path vs offline.
- **Consequences**: Paths in the blueprint (§24, App. F) are translated as `config/ → configs/`
  and `artefacts/ → artifacts/`.
- **Class**: A · **Date**: 2026-10-18 · **Commit**: initial

## ADR-003 · Environment: Python 3.11 + uv with a committed lockfile
- **Decision**: Use `uv` to manage the environment. `uv.lock` is committed. Python is pinned
  to 3.11 (`.python-version`, `requires-python >=3.11,<3.12`).
- **Context**: Blueprint Table 18.1 asks for Python 3.11 with a pinned lockfile.
- **Alternatives**: pip-tools, conda, poetry.
- **Evidence**: uv 0.10.8 is installed. `uv sync` resolved and installed the full stack in one
  step (2026-10-18): lightgbm 4.7.0, scikit-learn 1.9.1, pandas 3.0.6, pydantic 2.14.1,
  shap 0.51.0, optuna 5.0.0, fastapi 0.143.3.
- **Reason**: Fast, cross-platform, reproducible lockfile.
- **Consequences**: **pandas 3.x** is in use (copy-on-write by default, new string dtype).
  Code must not rely on pandas 2 chained-assignment behaviour.
- **Class**: A · **Date**: 2026-10-18 · **Commit**: initial

## ADR-004 · One causal feature implementation shared by offline training and live replay
- **Decision**: Features are pure functions of a `CausalView` (history truncated at t). The
  offline training matrix is produced by calling the *same* functions at every reading. There
  is no separate vectorised batch path.
- **Context**: CLAUDE.md §11 (truncation equality). The risk is train/serve skew if batch and
  streaming implementations differ.
- **Alternatives**: (a) vectorised pandas features for training plus an incremental
  implementation for replay, with cross-checks; (b) a streaming-only implementation.
- **Evidence**: The cost estimate is about 112k snapshots × tens of µs, i.e. seconds to
  minutes. This is to be **measured** in S4. If it proves too slow, optimise inside the same
  functions.
- **Reason**: It makes truncation equality structural rather than tested-for, and removes a
  whole class of skew bugs.
- **Consequences**: Feature functions must be efficient on numpy slices. Performance is
  profiled in S4.
- **Class**: A · **Date**: 2026-10-18 · **Commit**: pending (S4)

## ADR-005 · The audit is built on production modules; audit work is split across S1–S3
- **Decision**: The audit reuses the adapter, label builder and dose parser. S1 audits
  structure (G0/G1), S2 audits events (G2/G3b) and S3 audits medication (G3).
- **Context**: The blueprint's audit scripts (`audit.py`, `audit2.py`) are not in the
  repository. A standalone audit would duplicate episode and parse logic.
- **Alternatives**: Re-create standalone audit scripts.
- **Evidence**: CLAUDE.md §41 prohibits duplicated scientific logic. Audit numbers and model
  inputs must come from the same code.
- **Reason**: One implementation of each scientific rule, and audit numbers that exactly
  describe what the models see.
- **Consequences**: The stage plan reorders the blueprint's S1 (see IMPLEMENTATION_PLAN.md).
  Gate G2/G3 outcomes are known at the end of S2/S3 rather than S1.
- **Class**: A · **Date**: 2026-10-18 · **Commit**: pending

## ADR-006 · `hyposense` CLI replaces the Makefile
- **Decision**: Provide a Python entry point `hyposense <audit|freeze|confirm|demo|…>` in
  place of `make` targets.
- **Context**: Blueprint §23.2 uses `make audit && make freeze && make confirm && make demo`.
  `make` is not installed on the Windows development machine.
- **Alternatives**: GNU make via MSYS, `just`, `nox`.
- **Evidence**: `which make` → not found (2026-10-18).
- **Reason**: Cross-platform with zero extra tooling.
- **Consequences**: The README documents the CLI equivalents of the blueprint's make targets.
- **Class**: A · **Date**: 2026-10-18 · **Commit**: initial (stub)

## ADR-007 · Frontend: Next.js + TypeScript + Tailwind + shadcn/ui + ECharts, static export served by FastAPI
- **Decision**: Build the UI as a Next.js (App Router) application, statically exported and
  served by FastAPI. Use shadcn/ui (Radix) primitives, Apache ECharts for clinical time series
  and evidence charts, and TanStack Query for data fetching. No Streamlit.
- **Context**: The blueprint (§17) specifies React (Vite) + Recharts with a Streamlit fallback.
  The project owner requires a professional web application and rejects Streamlit
  (2026-10-18).
- **Alternatives**: Vite + React (simpler; no SSR needed); Recharts (limited annotation: no
  native mark areas or brushing on large series); visx (flexible, but much more code); Plotly
  (heavy bundle).
- **Evidence**: The required charts need mark areas (episodes, warning windows), mark lines
  (70 mg/dL, τ), dual axes (CGM vs exposure), data zoom and reliability diagrams. ECharts
  supports all of these natively.
- **Reason**: The owner's stated preference (Next.js). A static export keeps the demo a single
  offline process.
- **Consequences**: Static export restricts dynamic routes, so patients are selected with query
  parameters or client-side state. Node is needed for builds only, not at demo time.
- **Class**: A · **Date**: 2026-10-18 · **Commit**: pending (S8)

## ADR-008 · API transport: REST + server-sent events; TypeScript types generated from OpenAPI
- **Decision**: REST for snapshots and commands, SSE for the replay clock and decision events,
  and `openapi-typescript` to generate frontend types.
- **Context**: The blueprint has the frontend polling once per second.
- **Alternatives**: polling; WebSockets.
- **Reason**: SSE is one-directional, simple in FastAPI and reconnects automatically. Polling
  can show a stale state between polls. Generated types prevent contract drift (CLAUDE.md §21).
- **Consequences**: The UI implements a stale-stream state (ARCHITECTURE §4.11).
- **Class**: A · **Date**: 2026-10-18 · **Commit**: pending (S7)

## ADR-009 · Artefacts never use pickle
- **Decision**: Store the LightGBM native text model, the calibrator as JSON, the feature spec,
  the policy and the manifest, each with a SHA-256.
- **Alternatives**: joblib/pickle.
- **Reason**: The files are deterministic, diffable and hashable, carry no code-execution risk,
  and stay stable across library versions.
- **Class**: A · **Date**: 2026-10-18 · **Commit**: pending (S6)

## ADR-010 · File-based experiment provenance (no MLflow)
- **Decision**: Every run writes `experiments/runs/<run_id>/manifest.json` and `results.json`
  with full provenance (CLAUDE.md §13). `docs/EXPERIMENT_LOG.md` indexes the runs.
- **Alternatives**: MLflow, Weights & Biases.
- **Reason**: Offline, dependency-free, auditable in git, and enough for about 20 planned runs.
- **Class**: A · **Date**: 2026-10-18 · **Commit**: pending (S5)

## ADR-011 · Partition guard and freeze manifest enforce the sealed partition in code
- **Decision**: All record access goes through a `DataAccess` scope. E-patient records are
  reachable only (a) as aggregate audit reports (P-C5), or (b) after a valid freeze manifest
  exists that matches the current code and configuration.
- **Context**: Blueprint R8, `test_freeze_guard`, CLAUDE.md §12.
- **Reason**: Separation that relies only on discipline is not auditable.
- **Class**: A (implements a C requirement) · **Date**: 2026-10-18 · **Commit**: pending (S2)

## ADR-012 · Standalone analysis plan hashed at freeze
- **Decision**: Before freeze, write `docs/protocol/ANALYSIS_PLAN.md`. It contains the exact
  definitions, metrics, operating-curve and τ rules (P-C2), evaluation semantics (P-C3),
  secondary/sensitivity analyses, and the interpretation matrix. It is hashed into the freeze
  manifest.
- **Context**: The blueprint treats §19–20 of the .docx as the analysis plan. A Word document
  is hard to diff, and the operational details are underspecified.
- **Reason**: A machine-diffable pre-registration that matches the code.
- **Class**: A · **Date**: 2026-10-18 · **Commit**: pending (S5)

## ADR-013 · Demo fallback is a recorded replay video plus static Evidence exports
- **Decision**: If the live demo fails Gate G7, use the recorded video and static exports.
  Streamlit is not a fallback.
- **Context**: Blueprint §26 lists "Slip → Streamlit fallback". The project owner rejects
  Streamlit.
- **Class**: A · **Date**: 2026-10-18 · **Commit**: initial

## ADR-014 · Protocol-constant lock and import-boundary tests from day one
- **Decision**: `tests/regression/test_protocol_constants.py` pins every Class C constant in
  `configs/default.yaml`. `tests/leakage/test_import_boundaries.py` forbids live-path imports
  of `labels`/`evaluation` and policy imports of model code.
- **Reason**: Turns CLAUDE.md §3 (Class C) and §19 (model/policy separation) into failing
  tests rather than conventions.
- **Evidence**: 16 tests passing (2026-10-18).
- **Class**: A · **Date**: 2026-10-18 · **Commit**: initial

## ADR-015 · E1 / M4 (reduced physiology) is deprioritised to P3 and not planned
- **Decision**: Plan no work on E1/M4 unless the core (S0–S9) is complete with time to spare.
  If attempted, Gate G6 applies unchanged.
- **Context**: Blueprint §13.2 (optional, gated). CLAUDE.md §7 discourages ODEs and Kalman
  filters unless they solve a demonstrated problem.
- **Reason**: G6 is unlikely to pass with these data, and the event ends 20 Nov 2026.
- **Class**: B (scope) · **Date**: 2026-10-18 · **Commit**: initial
