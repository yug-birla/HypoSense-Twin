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
- **Class**: A · **Date**: 2026-10-18 · **Commit**: bd813d1 (implemented in S4; see ADR-032)

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

---

## DEC-2026-10-18-A · Owner approvals of Class C proposals
- **Decision**: The project owner approved **P-C1** (current CGM < 70 → LOW NOW, including floor
  readings), **P-C2** (deterministic first-crossing operating-curve / budget / τA method),
  **P-C3** (causal policy replay; OUTCOME-UNKNOWN notifications excluded from TRUE/FALSE and
  reported separately), **P-C5** (aggregate-only integrity access to E before freeze, with
  safeguards) and **P-C6** (τW by the same framework on total notifications). **P-C4** was
  delegated: use the originals if found, else regenerate deterministically. They were found
  (ADR-016).
- **Recorded in**: [protocol/ANALYSIS_PLAN.md](protocol/ANALYSIS_PLAN.md) §1–3 (exact
  algorithms and edge cases).
- **Class**: C (approved) · **Date**: 2026-10-18 · **Commit**: this S1 documentation commit

## ADR-016 · Official T/E partition = the blueprint author's original, verified and hash-locked
- **Decision**: Import `audit_outputs/partition.csv` from the blueprint source bundle as
  `configs/partition.csv` v1.0.0, with columns (patient_id, partition) only. SHA-256
  `ccdcbce0…2449578` is pinned in configs/default.yaml and checked on every load. Provenance is
  in `configs/partition.provenance.json`.
- **Context**: P-C4. The originals were found at
  `C:\Users\Lenovo\Downloads\HypoSense_v2_sources\` (zip sha256 `0f361a10…`; bundle
  partition.csv hashed in the provenance file).
- **Alternatives**: regenerate with seed 2026 (option B).
- **Evidence (MEASURED)**: `reproduce_audit2_split` (an exact re-implementation of audit2.py
  lines 14–20) reproduces the original assignment for **100/100 patients** from the file's own
  stratum column (numpy 2.4.x). T/E = 30/70; stratum sizes 9/18/30/43; T per stratum 3/5/9/13.
  These match the blueprint (22 treated T, 51 treated E).
- **Reason**: It preserves the blueprint's pre-registered split exactly. Before any modelling,
  its assignment is identical to option B with the original algorithm anyway.
- **Consequences**: Per-patient episode counts and strata of E patients were deliberately not
  copied into the repository (P-C5). Two verifications are pending: the has-L1 stratum of 2003
  and 2029 under v5 (S2), and the treated flag against the production parser (S3). A stratum
  change would be reported, not "fixed", because stratification only balances the split. The
  partition **must never be regenerated or edited**; changing the pin needs a Class C decision.
- **Class**: C (approved delegation) · **Date**: 2026-10-18 · **Commit**: 4c1eaad

## ADR-017 · Canonical dataset = figshare article 21600933 **v5**; v1/v2 used only to reconcile
- **Decision**: Analyse only v5 (2023-10-30, MD5 `4bfb61cf…`, SHA-256 `59b5f5c4…`). Download
  v1 and v2 (v2 = v3 = v4 by MD5) solely to explain differences from the blueprint's mirror
  audit. They are extracted to `data/raw/reconciliation/` and never analysed.
- **Evidence (MEASURED)**: v1 and v2 reproduce **every** structural blueprint number exactly
  (112,287 CGM; interval histogram; 827/2166 dose entries; 3802/742 diet; 3262 CBG; …). v5
  differs only in 2003_0 and 2029_0, exactly the files named in the publisher's v5 note. The data
  descriptor's published "Total CGM measurements 112,475" (VERIFIED from nature.com) equals the
  v5 timepoint-row count. The 13 rows without CGM are the documented device-change rows in
  2029_0.
- **Consequences**: Blueprint mirror numbers are superseded by the v5 measurements. Event and
  medication-parse counts are re-derived in S2/S3. The blueprint's mirror was pre-2023-10-26
  figshare content.
- **Class**: A (data-source pinning; implements G0) · **Date**: 2026-10-18 · **Commit**: 4c1eaad

## ADR-018 · Scoped dataset access as the sealed-partition safeguard
- **Decision**: `load_dataset(scope)` has three scopes:
  - `TUNING_ONLY` opens T files only. It is the only scope for modelling and design.
  - `AGGREGATE_AUDIT` is confined by a static test to `hyposense.audit` and the CLI validate
    command; its outputs are aggregate-only, with an allow-listed per-recording table.
  - `ALL_AFTER_FREEZE` refuses until the freeze machinery exists.

  Direct `load_partition` use is confined to `data/` and `audit/`.
- **Context**: Approved P-C5 ("implement technical safeguards where practical").
- **Alternatives**: convention only; OS-level separation of E files (rejected: heavy and brittle
  on Windows).
- **Consequences**: Every S2+ modelling entry point must call `load_dataset(TUNING_ONLY)`. The
  static tests fail otherwise.
- **Class**: A (implements a C requirement) · **Date**: 2026-10-18 · **Commit**: 4c1eaad

## ADR-019 · Loader conventions
- **Decision**:
  - Cells are read raw (`dtype=object`) and parsed explicitly.
  - Rows are never deleted. Problems become per-row flags plus `LoadIssue` records. Exclusions
    happen only in `cgm_series()`, which counts every exclusion by reason.
  - Sub-second timestamps are **rounded** to the nearest second, not truncated, and flagged.
  - Unparseable text in medication columns is a warning, with the raw text preserved for the S3
    parser. Unparseable CGM/CBG is an error.
  - The header table is explicit; an unknown column is an error.
  - File names are authoritative for identity. Sheet names and file-name dates are only checked.
- **Evidence**: S1 audit. 13 sub-second timestamps (float drift in the 2029_0 device-change
  rows) would otherwise shift 1 s earlier. Pump-suspension text and a misplaced oral agent sit
  in CSII columns. pandas type inference turns empty dose columns into float64.
- **Class**: A · **Date**: 2026-10-18 · **Commit**: 4c1eaad

## ADR-020 · Aggregate-only audit evidence and gate results are committed
- **Decision**: Commit `experiments/runs/ALL-AGG-*/` and `artifacts/gates/` (aggregate-only,
  provenance-stamped). Raw and derived patient-level data stay git-ignored.
- **Reason**: The repository is the project memory (CLAUDE.md §13), so gate evidence must
  survive outside the working copy.
- **Class**: A · **Date**: 2026-10-18 · **Commit**: this S1 documentation commit

## ADR-021 · `ruff format` adopted repository-wide
- **Decision**: Use `ruff format` (black-compatible, line length 100). One per-file E501
  exception covers the Markdown report template.
- **Class**: A · **Date**: 2026-10-18 · **Commit**: 4c1eaad

---

## ADR-022 · Label package design: explicit state machine, typed outputs, differential testing
- **Decision**: `src/hyposense/labels/` has four distinct layers:
  - episodes: an explicit index-based state machine;
  - eligibility: masks plus a first-failing reason code per reading;
  - labels: y ∈ {1, 0, −1};
  - recording-level assembly.

  Validity and annotations are separate modules that never alter episodes. All constants come
  from `LabelConfig.from_config` (Class C keys locked by test).
- **Alternatives**: vectorised run-length logic (harder to audit); reusing the original
  audit.py code (untyped, no reason codes).
- **Evidence (MEASURED)**:
  - 34 hand-labelled trace fixtures + 4 loader-path cases (38) were written first; 74 tests failed before implementation.
  - Hypothesis differential tests compare against a verbatim transcription of the executable
    spec: 400 random traces each for episodes and eligibility, all identical.
  - 7/7 injected boundary mutants were killed.
  - Exact reproduction of all 48 blueprint event values on figshare v1/v2.
- **Consequences**: S4 features and S5 evaluation consume `RecordingLabels`. The live path may
  not import `labels` (import guard).
- **Class**: A · **Date**: 2026-10-18 · **Commit**: 32f3245

## DEC-2026-10-18-B · Operational label protocol adopted = blueprint executable specification
- **Decision**: ANALYSIS_PLAN §0 makes three Table 5.1 wordings precise exactly as the
  blueprint's own audit code did. All 48 reported numbers depend on these readings:
  - (1) the recovery pair must be ≤ 20 min apart, like the onset pair;
  - (2) a prediction time needs t − recording start ≥ 120 min, which equals the policy
    warm-up;
  - (3) after a GAP ending, refractory starts at the first post-gap reading.
- **Why not Class C approval first**: nothing changes relative to the blueprint. The blueprint's
  numbers were produced under exactly these semantics, and 48/48 exact reproduction proves the
  equivalence. Recorded transparently; the owner may object.
- **Class**: C-clarification (no change) · **Date**: 2026-10-18 · **Commit**: 32f3245

## ADR-023 · Legacy treated definition isolated; G2 provisional until S3
- **Decision**: The blueprint audit's treated rule lives only in `audit/legacy.py`. It is used
  for reproduction and the provisional G2. The production treated status comes from the S3
  medication parser.
- **Evidence (MEASURED)**: the legacy rule gives 73 treated patients. A stricter variant (an
  i.v. cell counts only if it names an insulin) also gives 73, so 0 patients depend on non-insulin
  i.v. fluids. Partition strata on v5 equal the provenance counts exactly (9/18/30/43; T
  3/5/9/13), so the 2003/2029 re-check passes.
- **Class**: A · **Date**: 2026-10-18 · **Commit**: 32f3245

---

## DEC-2026-10-18-C · P-C8 approved (sensor-failure handling)
- **Decision (owner)**: all three parts of P-C8 are approved.
  - (a) A run of ≥ 8 consecutive CGM readings ≤ 40 mg/dL is flagged SENSOR FAILURE SUSPECTED. It
    is a measurement-quality annotation that never alters the canonical labels.
  - (b) During such a run, keep LOW NOW and add the warning "SENSOR FAULT SUSPECTED — verify
    sensor and obtain capillary glucose". The state is never NO ALERT, the low is never hidden,
    and no treatment advice is given.
  - (c) Sensitivity analysis SA9 excludes flagged episodes and intervals.
- **Recorded in**: ANALYSIS_PLAN §0c (exact SA9 rule); `data.quality.sensor_fault_suspected`
  (causal flag, tested); `labels.annotations.floor_runs` (offline). UI handling is deferred to S7/S8.
- **Class**: C (approved) · **Date**: 2026-10-18 · **Commit**: 48941d8

## ADR-024 · Medication parsing: content-aware, column-specific grammars, nothing dropped
- **Decision**:
  - The versioned dictionary (`configs/drug_dictionary.csv`) separates SOURCE_FACT mapping from
    ASSUMPTION modelling.
  - Deterministic normalisation covers unicode spaces and full-width punctuation.
  - Each column has a grammar; classification follows CONTENT, and the source column is kept.
  - Every component gets one of PARSED / PARSED_WITH_WARNING / AMBIGUOUS / NON_TARGET_MEDICATION
    / NON_MEDICATION / UNPARSEABLE, plus flags.
  - Doses are never invented, and implausible units are kept and flagged.
- **Evidence (MEASURED, v5)**:
  - 4,653 cells; 0 UNPARSEABLE, 0 AMBIGUOUS.
  - Insulin s.c. 828/828 and oral 2,171/2,171 parsed to drug + dose.
  - The legacy regex's misses are resolved: "scilin m30", and the misplaced acarbose that it read
    as insulin.
- **Class**: A · **Date**: 2026-10-18 · **Commit**: 48941d8

## ADR-025 · Exact summation in the exposure engine (bitwise causality)
- **Decision**: Row sums use `math.fsum` instead of BLAS matrix-vector products.
- **Evidence**: With BLAS, full-record vs truncated-record exposure differed by about 1 ulp,
  because the summation order depends on vector length. In the S3 smoke test this produced
  bitwise mismatches in most sampled T recordings; the failing checks were not counted. With
  fsum: 0/5,984 on real T data, and the Hypothesis property test passes.
- **Reason**: CLAUDE.md §11 requires *identical* feature vectors.
- **Cost**: 0.24 ms per reading (MEASURED), adequate for replay.
- **Class**: A · **Date**: 2026-10-18 · **Commit**: 48941d8

## ADR-026 · CSII basal reconstruction with a 6-hour continuation cap (a-priori representation choice)
- **Decision**:
  - A programmed basal rate becomes r/4-IU micro-boluses every 15 min until the next pump entry
    or suspension, **at most 6 h after its entry**; beyond that, pump delivery is UNKNOWN
    (quality PARTIAL for 24 h).
  - Projections continue the currently programmed rate (P-B3 resolved: option b).
- **Context**: Blueprint: "rate persists until the next rate entry".
- **Evidence (MEASURED)**:
  - T pump segments are 180–300 min; only 4 of 1,055 pump-entry intervals exceed 6 h.
  - In **all 21** recordings whose pump entries end early, s.c. insulin follows (a pump→injection
    transition). The literal blueprint rule would have fabricated a median of 39.5 h (up to
    168 h) of basal insulin in those recordings.
- **Class**: B (decided a priori from structure; no outcome data used) · **Date**: 2026-10-18 · **Commit**: 48941d8

## ADR-027 · Kernel parameters sourced from regulatory labels (no ILLUSTRATIVE values remain)
- **Decision**: pharma.yaml v1.0.0 has per-parameter status, source and note
  (docs/medication/PARAMETER_SOURCES.md). Changes vs the blueprint's illustrative values:
  - NPH duration 900 → **1440 min** (labels: ~24 h);
  - degludec 1440 → **2520 min** (≥ 42 h);
  - gliclazide split into **MR** (t½ 16 h, tmax 9 h, D_max 120) and **IR** (t½ 11 h, tmax 4 h,
    D_max 320);
  - glimepiride t½ 6.5 h / tmax 2.5 h;
  - gliquidone D_max 120 mg (label); t½ 3 h remains an ASSUMPTION;
  - basal-analogue window fixed as [lag, lag + duration) (P-B4 resolved).
- **Evidence**: 15/16 items verified against FDA SPL, EMA SmPC and national SmPCs, with quotes.
  Unverified items are recorded as ASSUMPTION.
- **Consequences**: Pharmacist review is still pending (`reviewed_by: null`). No claim of clinical
  validity is made.
- **Class**: B (kernel parameters; set before any model result) · **Date**: 2026-10-18 · **Commit**: 48941d8

## DEC-2026-10-18-D · Production treated population (replaces the S2 legacy definition)
- **Decision**: Treated = ≥ 1 parsed administration of insulin (any route), a sulfonylurea or a
  glinide (ANALYSIS_PLAN §0b). This gives 72 patients (T 22, E 50). Artefact:
  `artifacts/population/treated_patients.csv`, sha256 `2016d3e3…`.
- **Difference from legacy**: patient 2078 (E) is untreated. The legacy rule counted a misplaced
  "acarbose 50 mg" cell in the CSII column as insulin.
- **G2 re-check**: PASS and unchanged (154 E-treated L1 episodes in 30 patients; m_w 9.23).
  2078 has no L1 episode. The partition is not re-split; only the strata label of one patient
  changes (E:2 → E:0).
- **Class**: C-clarification (correct application of the approved definition; not a change) ·
  **Date**: 2026-10-18 · **Commit**: 48941d8

## ADR-028 · i.v. glucose handled as a confounder flag only (P-B5 resolved: FLAG ONLY)
- **Evidence (MEASURED)**:
  - 3 events (2 patients), all in E, none in T.
  - Volume and concentration are known; **rate and duration are never recorded**.
  - All 3 are co-administered with i.v. insulin in the same bag; 0 have a CGM < 70 within ± 2 h.
- **Decision**: no feature, and not insulin exposure. Kept as an event with the GLUCOSE_INFUSION
  flag for audit and future sensitivity analyses.
- **Class**: B · **Date**: 2026-10-18 · **Commit**: 48941d8

## ADR-029 · Provenance porcelain parsing fix
- **Defect**: `_git()` stripped stdout, so a leading-space status line lost its first path
  character. Only false *dirty* flags were possible, so earlier `dirty=False` evidence stands.
- **Fix**: keep leading spaces; parse with `parse_porcelain`; regression test added.
- **Class**: A · **Date**: 2026-10-18 · **Commit**: 88cdeac

---

## ADR-030 · Feature specification v1.0.0: one registry, a generated export, operational choices fixed a priori
- **Decision**:
  - `features/spec.py` is the single authoritative definition of every feature: group, dtype,
    unit, source, computation, availability, missingness policy, indicators, status, SA8 lab tag
    and version.
  - `artifacts/features/feature_spec.json` is its generated, committed export. A test fails on
    drift, and the spec hash is pinned in the regression suite. Model levels are fixed by group
    (M1 38 / M2 72 / M3r 95 / M3 100).
- **Operational choices** (App. D leaves these open). They were fixed before any model was fitted
  and without any outcome-based selection:
  - **Lags:** the reading nearest t − L within ± 7.5 min, ties going to the earlier reading.
  - **Trend window:** slopes and M0 use (t − Δ − 5 min, t] with ≥ 3 readings, the executable
    spec's M0 window (audit2.py; ANALYSIS_PLAN §0d). Exact least-squares sums agree with
    polyfit to 1e-9.
  - **Statistics:** half-open (t − W, t]; SD with ddof = 1; a young recording uses the readings it
    has.
  - **Minutes < 80** = 15 min × the count of such readings.
  - **Minutes since a reading < 70:** capped at 1440, NaN if none.
  - **Own percentile:** mid-rank, requiring ≥ 24 h of history.
  - **Sensor day:** counted from the recording start. P-C7, if approved, does not re-anchor it.
  - **Meals:** rows sharing a timestamp form one meal. Content is unknown when the diet text is
    the "not recorded" marker (MEASURED on T: "Data not available" and 未记录 always occur
    together, 201 rows).
  - **Regimen flags** come from the drug dictionary. `rx_basal` covers basal analogues and NPH,
    consistent with the M3r `insulin_basal` category.
  - **Static validity ranges** are wide and catch gross errors only. eGFR's bound was widened to
    400 so that the extreme-but-recorded value of 257 on T is kept (S3 keep-and-flag rule).
  - **Values and digests:** float64 values with one canonical NaN; SHA-256 snapshot digests.
    The blueprint specified float32 and SHA-1, but rounding would blur threshold ties.
- **Pre-release change:** v1.0.0 was regenerated once inside S4 (the G7 indicator definition,
  after the independent review), before any model or official evidence used it. Final spec
  sha256 `82fc54e9…`; the superseded dirty run 1 used the earlier `0e87630c…`.
- **Class**: B (representation, decided a priori) · **Date**: 2026-10-18 · **Commit**: bd813d1, d75ff1b

## ADR-031 · Patient State Engine design (implements ARCHITECTURE §4.4)
- **Decision**: `PatientState` is a frozen dataclass.
  - **Blocks:** context; CGM (series + causal episode tracker + last low); data quality;
    medication (S3 engines); meals; CBG; forecast; ledger.
  - **`update(event)`** is strict and deterministic. It accepts only the canonical order (ts,
    then dose → meal → CGM → CBG), refuses another recording's events, duplicate CGM readings
    and malformed values, and uses only (previous state, event).
  - **`try_update`** returns the previous state tagged SYSTEM_ERROR, and snapshots of a tagged
    state are refused.
  - **Histories** are persistent append-only logs: O(1) amortised, immutable prefixes, copy on
    branch.
- **Recording boundary:** one state per recording; nothing carries over (ANALYSIS_PLAN §0 item
  10). Recordings are ordered by first timestamp, never by number.
- **No duplicated rule logic:**
  - The quality flags reuse the authoritative `data.quality` functions on 2- and 8-reading tails.
  - The live path cannot import `labels/`, so the episode rule is restated causally. The causal
    tracker is tied to `labels.build_episodes` by a differential test (Hypothesis, 400 examples
    + 22 hand-labelled fixtures) and by real T data (33,464 readings, 0 mismatches).
- **Class**: A · **Date**: 2026-10-18 · **Commit**: bd813d1

## ADR-032 · Offline feature generation is the replay (ADR-004 implemented)
- **Decision**:
  - The training table is produced by replaying each recording through `PatientState.update` and
    calling the same `FeatureBuilder.union` after every CGM reading. There is no batch path.
  - `snapshot(state, level)` is a fixed selection of the union.
  - Before freeze, the builder accepts only a TUNING_ONLY dataset.
- **Evidence (MEASURED)**:
  - parity (T audit): 133,856 snapshot comparisons, 0 mismatches;
  - live-path cost, serial single-process benchmark on all 34 T recordings (median of 3):
    `update()` 71 µs per event and `snapshot(M3)` 0.66 ms, 0.74 ms per reading in total
    (p50 0.65 ms, p99 1.79 ms);
  - T table (33,464 readings) built in 14.6 s on 15 processes (audit run 4).
- **Performance change (profiled first):** `raw_timing` re-categorised every logged event at
  every reading (43 % of feature time on the heaviest recording). `RawTiming` now builds the
  per-category arrays once per log length, with the same semantics. The S3 exposure engine,
  now the main cost, is left unchanged because it is adequate.
- **Class**: A · **Date**: 2026-10-18 · **Commit**: bd813d1

## ADR-033 · Missingness policy and indicators
- **Decision**: Every feature has exactly one missingness policy:
  - REQUIRED: guaranteed finite at label-eligible times; asserted by the audit (0 violations on
    31,292 eligible T rows);
  - NEVER_MISSING;
  - NAN_WITH_INDICATOR.
- **Indicators** belong to the *missingness source*. Features with the same source share one
  indicator, which avoids duplicate columns.
- **M3 exposure clusters:** the indicator is the class quality code, App. D's "timing-unknown
  indicators". The exposure is NaN exactly when the quality is TIMING_UNKNOWN, DOSE_UNKNOWN or
  FORMULATION_UNKNOWN.
- **M3r:** per the S3 contract, TIMING_UNKNOWN masks min_since, last_dose and dose_24h (n_24h
  keeps the true count). `<cat>_missing` = any NaN in the category.
- **Semantics:** ZERO is always a true zero; NaN meanings (NOT_OBSERVED / INSUFFICIENT_HISTORY /
  UNKNOWN / TIMING_UNKNOWN) are recorded per feature; there is no imputation.
- **Prescribed regimen:** like the labs, it is stay-level context used at every t (M2 `rx_*`;
  the M3/M3r TIMING_UNKNOWN rule). MEASURED on T: first logged dose ≤ 9.2 h (insulin) / ≤ 20 h
  (SU) after recording start; 1 SU prescription never logged. This residual risk is documented
  (independent review finding); it is not a protocol change.
- **Class**: B (representation, a priori) · **Date**: 2026-10-18 · **Commit**: bd813d1, d75ff1b

## ADR-034 · S4 defects found by measurement and review, and their fixes
- **Table-hash defect.**
  - Observed: two identical builds reported different table hashes.
  - Cause: `frame_sha256` hashed pandas `str` columns via `.to_numpy().tobytes()`, i.e. object
    *pointers*. The feature arrays were bitwise identical.
  - Fix: value-based hashing, with a regression test. The superseded run
    `T-AGG-audit-features-20261018T110633Z` is kept as a record.
- **Independent review** (no CRITICAL or HIGH findings; no leakage path found). Fixed:
  - the G7 indicator now covers a dose of unknown size;
  - `OutcomeLedger.finalize` resolves fully observed windows to 0 at recording end (ANALYSIS_PLAN
    §2.4);
  - the engine cache is `init=False`, so it is never shared via `replace`;
  - **defence-in-depth sealed guard:** `data.dataset.assert_not_sealed` in the recording
    adapter, so even a mis-scoped call cannot build E features before freeze;
  - the CGM feature config must match the names the spec fixes;
  - unrecognised regimen text is flagged;
  - the audit reports only quartiles for static features, for privacy.
- **Audit bounds bug:** names starting `cgm_min_` captured `cgm_min_below80_24h` and
  `cgm_min_since_low70`, giving false "impossible value" flags. Fixed; both are within [0, 1440].
- **Class**: A · **Date**: 2026-10-18 · **Commit**: d75ff1b

## DEC-2026-10-18-E · ANALYSIS_PLAN §0d adopted (M0 operational definition = executable spec)
- **Decision**: M0 is defined as audit2.py computes it:
  - window (t − 35 min, t], ≥ 3 readings;
  - least-squares slope;
  - projection g(t) + H × slope, anchored at the current reading.
- One implementation (`features.cgm`) serves M0 (S5) and the group-1/2 features.
- It clarifies Table 11.1 and changes no number. S5 must reproduce Table A.2 with it.
- **Class**: C-clarification (= executable spec, like §0) · **Date**: 2026-10-18 · **Commit**: dcb164f

## ADR-035 · Feature-audit runtime: Windows power-throttling opt-out (engineering only; no scientific effect)
- **Observed**: official feature-audit runs 2 and 3 took 16.1 and 19.3 min (run 1: 7.1 min). The
  audit printed nothing until the end, so it looked stalled.
- **Diagnosis (MEASURED)**: not hung.
  - All 15 workers stayed CPU-active, at ~27 % of a core each.
  - No disk I/O or paging, no lock or network wait, no recursion. Only the 34 TUNING
    recordings were processed; no evaluation or full-dataset work.
  - Logical CPUs 12–15 (the i7-13620H's 4 efficiency cores) ran at 100 % while the 12 P-core
    threads were nearly idle. Affinity was 0xFFFF and priority Normal.
- **Root cause**: Windows 11 power throttling (EcoQoS) scheduled the console-less background
  workers on the efficiency cores.
- **Change** (commit df90031):
  - `common/runtime.disable_power_throttling()` (SetProcessInformation /
    ProcessPowerThrottling, with a typed HANDLE) in the audit main process and every worker;
  - `single_threaded_math_env()` for spawned workers;
  - per-phase progress on stderr and phase wall times in the audit output.
- **Effect**:
  - A/B on the build phase: 54.2 / 65.4 s without vs 32.1 / 35.3 s with the opt-out.
  - Official runs 4 and 5: 10.0 / 10.1 min. Truncation is ~8 of the 10 min because it rebuilds
    every truncated record independently. That cost is inherent to the proof and is accepted for
    an offline validation audit; the test is not weakened.
- **Scientific effect: none.** results_sha256 `db39f39a…` and table sha256 `a5b6ac93…` are
  identical in runs 2–5 (before and after the change).
- **Class**: A · **Date**: 2026-10-18 · **Commit**: df90031

## ADR-036 · Exact rational trend arithmetic (S5 finding; feature spec v1.0.1)
- **Observed:**
  - The legacy Table A.2 reproduction matched exactly at 7 of 8 θ.
  - At θ = 45, FA/day was lower by 0.01 (treated 0.72 vs 0.73; all patients 0.78 vs 0.79),
    with identical warned counts.
- **Diagnosis:**
  - 45 is the only Table A.2 threshold on the 1.8 mg/dL data grid. 44 decision readings on v2 T
    have a projection mathematically equal to 45.
  - Floating-point sums (ours and np.polyfit alike) put them at 45 ± 1e-13, so float noise
    decided the strict rule "projection < θ". The same noise split mathematically tied scores
    into distinct grid values, against ANALYSIS_PLAN §3.4 ("ties switch together").
- **Fix:** least-squares slope and projection in exact rational arithmetic on the 0.1 mg/dL grid
  (integer seconds), rounded once (`features.cgm.ls_slope_exact`, `trend_projection`). Off-grid
  values fall back to the float's exact binary value, which is still deterministic.
- **Spec:** feature spec v1.0.1 (sha256 `90329804…`); six features changed in the last bits
  (slopes, acceleration, M0 projections).
- **Re-verification:** S4 feature audit re-run on clean `3487373`: truncation 31,292/0, parity
  133,856/0, perturbation 1,200/0, tracker 0 (results `a66c8bd1…`).
- **Class**: A (numerical correctness of an approved rule) · **Date**: 2026-10-18 · **Commit**: c6734a1

## ADR-037 · Evaluation harness design (S5)
- **Decision:**
  - **Model-agnostic input:** `EvalRecording` (per CGM reading: policy gate, scores, label
    eligibility; onsets and warnable flags from the S2 label builder).
  - **Policy replay:** exact accounting per ANALYSIS_PLAN §2.
  - **Operating curve:** exact via per-recording step functions over each recording's distinct
    scores, aggregated to per-patient arrays on the pooled grid. One code path serves the full
    sample and every bootstrap resample. A resample keeps exactly its own grid columns (§3.4).
    The curve is tested against direct replay (Hypothesis) and against explicit resamples.
  - **Bootstrap:** paired patient-cluster bootstrap with draw-count weights (multiplicity
    kept); the patient set is verified across paired statistics.
  - **Metric registry:** one definition per metric, at `artifacts/evaluation/metric_registry.json`.
- **Rejected:** an ordinary ROC/threshold library (no cooldown, no episode semantics); quantile
  threshold grids (§3.2 forbids them).
- **Evidence:**
  - one threshold evaluates in 13 ms;
  - the exact M0 curve takes 4.8 s (treated T) and 6.2 s (all T);
  - 2,000 bootstrap resamples take 1.5–1.7 s.
- **Class**: A · **Date**: 2026-10-18 · **Commit**: c6734a1, 671a7ca

## ADR-038 · Policy core implemented in S5 (needed by the evaluation's policy replay)
- **Decision:** `policy/decide.py` implements:
  - `gate`: Table 14.1 priorities 1–4, with P-C1 (CGM < 70 → LOW NOW before sufficiency), and
    in-episode / < 60 min after an episode end from the causal tracker;
  - `classify`: a NaN score → INSUFFICIENT DATA, never NO ALERT;
  - `should_notify`: ≥ 3600 s since the last notification.

  The offline replay uses the same functions; a stepwise-vs-vectorised test ties them together.
  Tags, logging and the live service remain S7.
- **Class**: A · **Date**: 2026-10-18 · **Commit**: c6734a1, 671a7ca

## DEC-2026-10-18-F · Table A.2 reproduction outcome and §3 implementation clarifications
- **Reproduction** (v2 = mirror-equivalent, TUNING, the executable spec's label-eligible decision
  times):
  - 7 of 8 rows MATCH exactly.
  - θ = 45 is an EXPECTED DIFFERENCE (exact-tie resolution):
    - episodes, days and lead match;
    - 44 exact ties;
    - every reference value lies between the protocol (tie-exclusive) and tie-inclusive values.
  - The polyfit-replay diagnostic reproduces the treated row exactly (27, 0.73). It does NOT
    reproduce the all-patients row (62 / 0.78 vs 63 / 0.79). The mechanism is therefore only
    partly demonstrated: the residual is attributed to the author's numerics / file conversion
    (HYPOTHESIS).
- **Reference discrepancy:** the bundled audit2.py hard-codes θ ∈ (60, 70, 80, 90), while its
  output JSON holds 40–80 and a lead-30 block, so the output came from another version of the
  script.
- **Clarifications** are recorded as ANALYSIS_PLAN §5.3 (DRAFT, awaiting the owner): cooldown
  per recording; exact ties; partial area as a signed clipped path integral; window metrics only
  for probabilities; operationalised abstention coverage. None changes a number on T.
- **Class**: C-clarification (pending owner approval; not blocking S6) · **Date**: 2026-10-18 · **Commit**: 671a7ca
