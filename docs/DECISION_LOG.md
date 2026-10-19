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

## DEC-2026-10-18-G · S6 development protocol (PRE-REGISTERED before any model is fitted)
Written and committed before the first LightGBM fit. Development (T) only. E stays sealed.
Status of every result: DEVELOPMENT.

1. **Data.**
   - Rows and features: the v1.0.1 tuning feature table (`data/processed/features/v1.0.1/`,
     table `acb1be1f…`, clean 3487373).
   - Labels: joined offline (S2 builder).
   - Training rows: label-eligible prediction times of the training patients (all T patients:
     treated and untreated; ANALYSIS_PLAN §2.2).
   - Predictions are made at EVERY reading, because the S5 policy replay needs scores wherever
     the policy queries.
   - Feature sets: exactly `level_names(M1/M2/M3r/M3)` (38 / 72 / 95 / 100).
2. **Folds** (patient-grouped, stratified by treated × has-L1, deterministic, seed 2026):
   - 5 outer folds over T (`cv.folds`);
   - 4 inner folds within each outer training set (`cv.inner_folds`);
   - 4 folds over all T for M1 tuning.
3. **M1 tuning** (Blueprint §11.1):
   - Optuna TPE, seed 2026, 30 trials.
   - Search space = `configs/default.yaml model.search_space`.
   - Fixed: objective binary, metric binary_logloss, no class weighting, seed 2026,
     deterministic, num_threads 1, bagging_freq 1 (so that bagging_fraction acts),
     max 2,000 rounds.
   - Early stopping: 100 rounds on the held-out fold.
   - Trial objective = mean held-out log-loss at each fold's best iteration. Every trial is
     recorded.
4. **P-B2 adopted as proposed:** `num_boost_round` = the median per-fold best iteration of the
   winning trial. Every later fit uses that fixed count with no early stopping.
5. **Shared hyperparameters** for M2, M3r and M3, with the same folds, seeds, calibration and
   threshold procedure.
   - **P-B9 adopted a priori:** `quality_*` are declared categorical (they appear only in
     M3-family sets). All canonical columns are kept; the number of inert columns is reported.
6. **Calibration** (canonical = isotonic):
   - Per outer fold, the calibrator is fitted on the 4-fold inner out-of-fold RAW predictions of
     the outer-training patients (eligible rows) and applied to the held-out fold.
   - **P-B1 challengers:** Platt (logistic on logit p) and isotonic with linear interpolation
     between knots.
   - **Rule (on M1 pooled held-out eligible rows):** adopt a challenger only if its log-loss is
     lower than isotonic's by ≥ 1 % relative AND its ECE is not higher. Ties go to isotonic. One
     method then applies to all models.
   - **Band rule (§11.1):** M1 held-out calibration slope outside [0.8, 1.25] → risk bands in the UI.
7. **Ladder evaluation** (S5 harness, unchanged): pooled outer-OOF calibrated predictions per
   model; M0 scores unchanged.
   - Populations: treated T (primary-analogue) and all T.
   - Event metrics: sens@1FA (first crossing) and partial area, each with a 2,000-resample paired
     patient-cluster bootstrap (seed 2027); operating point at the first-crossing τ.
   - Window metrics on eligible rows: log-loss, Brier, AUPRC, ECE, slope / intercept.
   - Paired differences (sens@1FA, partial area, window log-loss):
     - C0 M1−M0 (event metrics only; M0 has no probabilities);
     - C1 M2−M1;
     - C2a M3r−M2;
     - C2b M3−M3r;
     - M3−M2 (development preview, NOT H1).
   - Patient-weighted sensitivity is reported (P-B6 b).
8. **P-B6 (c) variant**, applied to training only (labels and evaluation unchanged). Exclude
   from training:
   - (i) eligible rows whose label window (t, t+60] overlaps a sensor-floor run;
   - (ii) every row of recordings with ≥ 5 CGM < 70 readings paired to a CBG (± 8 min), all of
     those CBG ≥ 70.

   **Rule:** adopt for training only if M1 held-out log-loss on the UNAFFECTED T patients
   improves by ≥ 1 % relative. Rankings, sens@1FA and calibration are reported both ways.
9. **P-B8 (a) M3_compact** = M3 minus {insulin_p30, insulin_p60, su_p30, su_p60, glinide_p30,
   glinide_p60, act_insulin_total_per_kg}. It keeps the activities, IOB, Δ60 terms,
   minutes-since, quality codes and flags (S4 evidence).
   - **Rule:** recorded as "candidate preferred" only if its held-out log-loss is ≥ 1 % relative
     lower than M3's AND its sens@1FA is not lower.
   - M3_baseline stays canonical unless the owner approves a change before freeze.
   - **P-B8 (b) detemir duration:** not run on T; it is a kernel sensitivity that belongs to SA6.
10. **P-B7:** NOT RUN. T has 0 glinide patients, so combining SU and glinide is identical to
    the baseline on T by construction (uninformative). M3_baseline remains.
11. **Explanation:** grouped TreeSHAP (LightGBM `pred_contrib`), mean |contribution| per
    feature group on held-out eligible rows. Descriptive only, never causal.
12. **Overfitting checks:** train vs held-out log-loss per fold, per-fold best iterations, and
    prediction concentration.
13. **G4** (Table 21.1 = IMPLEMENTATION_PLAN S6): PASS iff all tests pass, the pipeline runs
    end-to-end on T, and the M1 operating curve is computed. M1 vs M0 is reported with its
    paired interval. On failure, M0 becomes the operational baseline.
14. **Reproducibility:** the full workflow runs twice on one clean commit; trials, OOF
    predictions and metric hashes must be identical.

- **Known limitation, accepted:** the hyperparameters are tuned on all of T and then reused in
  T's outer CV. The learned models' T results are therefore optimistic relative to M0 (which has
  no tuning) and are not out-of-sample for tuning. This is why T results are DEVELOPMENT only;
  the confirmatory run on E has no such overlap.
- **Class**: B (development procedures; pre-registered) · **Date**: 2026-10-18 · **Commit**: this commit

## DEC-2026-10-18-H · S6 development outcomes under the pre-registered rules (DEC-2026-10-18-G)
Evidence: T-AGG-dev-s6-20261018T144427Z and T150030Z on clean fd34ecf; identical results_sha256
`e81268ae…`. DEVELOPMENT only.

- **P-B2 / tuning.** Best trial #20:
  - learning_rate 0.0418, num_leaves 16, min_data_in_leaf 603, feature_fraction 0.601,
    bagging_fraction 0.940, lambda_l2 9.41;
  - CV log-loss 0.04626 ± 0.0285 (fold SD);
  - per-fold best iterations 193 / 111 / 116 / 39 → **num_boost_round = 113** (median).

  The 30 trials span only 0.0463–0.0503, so the hyperparameters are weakly identified; fold
  composition dominates. **Frozen as the shared set for M1/M2/M3r/M3.**
- **P-B1 calibration → ADOPTED `isotonic_interp`** for all models. **FRAGILE**: see DEC-2026-10-18-I (F1). M1 pooled held-out values:

  | Calibrator | Log-loss | ECE | Outcome |
  |---|---|---|---|
  | isotonic (canonical) | 0.04308 | 0.00082 | — |
  | isotonic_interp | 0.04017 (−6.7 %) | 0.00060 | rule met |
  | Platt | 0.04037 | 0.00133 | fails the ECE condition |

  Band rule: slope 0.97 → percentages in the UI.
- **P-B9 adopted a priori:** quality codes are categorical. Inert columns (no split in any outer
  model): M1 7, M2 19, M3r 30, M3 31. *[Corrected, DEC-2026-10-18-I F5]*: some are near-constant,
  others are redundant missingness indicators or patient-level variables suppressed by
  min_data_in_leaf = 603 (top-value share 53–84 %).
  No columns are pruned.
- **P-B6 → rule met on M1; adoption PENDING implementation and owner decision** *[corrected,
  DEC-2026-10-18-I F2]*.
  - Measured: M1 held-out log-loss on the 28 unaffected T patients 0.02954 vs 0.03018
    (−2.1 % ≥ 1 %).
  - Excluded from training: 876 eligible rows (2 CBG-contradicted recordings; 1 floor-window
    row).
  - Labels and evaluation are unchanged. The *intent* is to apply the exclusion to every
    model and the confirmatory training folds. That is **not implemented**: the canonical
    ladder above uses `pb6=False`.
  - Weak evidence, reported honestly: the all-T log-loss is not improved (+0.0006, CI includes 0).
- **P-B8 (a) M3_compact → "candidate preferred"** (rule met: all-T log-loss −3.1 %; treated
  sens@1FA 0.929 ≥ 0.911).
  - **M3_baseline stays canonical.** A change needs owner approval before freeze (PROPOSALS
    P-B8).
  - **P-B8 (b)** not run (SA6).
- **P-B7:** not run (0 glinide patients in T).
- **G4: PASS** (`artifacts/gates/G4.json`):
  - tests 415/415;
  - the pipeline runs end-to-end on T;
  - the M1 curve is computed.

  M1−M0 sens@1FA (treated T) = +0.231 (95 % CI 0.094 to 0.437).
- **Interpretation (development):** M1 ≫ M0. M2, M3r and M3 do not separate on T: every
  C1 / C2a / C2b / M3−M2 interval includes 0, with differences of 1–3 episodes. Treated-T
  sens@1FA (0.86–0.93) sits near the warnable ceiling (0.946).
- **Post-hoc diagnostic** (not pre-registered; used for no selection): a no-learning rule
  "alert if CGM < 81 mg/dL" reaches treated-T sens@1FA 0.911, above M1 (0.857). Its threshold
  is chosen on T by the harness, like every τ. *[Corrected, DEC-2026-10-18-I F4]*: this
  shows the endpoint is easy for a level rule and that M0 is a weak reference. It is **not**
  evidence against leakage; that evidence is the S4 truncation and feature audits and the S6
  isolation checks. This raises P-C9.
- **Class**: B (pre-registered rules applied) · **Date**: 2026-10-18 · **Commit**: fd34ecf

## DEC-2026-10-18-I · S6 independent review: outcome and corrections

- **Context.** Independent ML review of commits 877e9bf..8d8c3fe (review only, E not accessed).
  The reviewer re-derived the folds (exact match) and reproduced pooled raw M1 held-out log-loss
  (0.040247).
- **Verified:**
  - patient isolation (tuning, outer, inner, calibrator);
  - fairness: same folds, params, rounds, seed and calibrator for every model; nested feature
    sets M1 ⊂ M2 ⊂ M3r, M2 ⊂ M3;
  - rules coded as pre-registered;
  - score alignment into the harness;
  - bootstrap pairing;
  - determinism.

  The tuning-overlap optimism stays as pre-declared. No CRITICAL or HIGH finding.
- **F1 (MEDIUM) — P-B1 adoption is fragile.**
  - Canonical isotonic outputs exactly 0 on 9,761 eligible rows, 3 of them positive. Each
    costs ≈ 34.5 nats at the 1e-15 clip, which is the whole log-loss gap.
  - Without those 3 rows the interp gain is −0.6 %, below the 1 % rule.
  - isotonic_interp still outputs 0 on 6,944 rows.
  - Raw scores (0.04025) ≈ interp (0.04017), so calibration buys ECE only, not log-loss.
  - **Decision:** isotonic_interp stays the rule-selected calibrator, labelled FRAGILE. A floored
    calibrator challenger is proposed (P-B10). The UI must never display a 0 % risk. Both apply
    before freeze.
- **F2 (MEDIUM) — P-B6 was decided on M1 only and is not implemented canonically.**
  - The unaffected-patient gain depends on the calibrator:

    | Scores | Gain |
    |---|---|
    | raw | +2.3 % |
    | isotonic_interp | +2.3 % |
    | Platt | +1.9 % |
    | canonical isotonic | −0.6 % (rule fails) |

  - The evidence comes from 2 affected patients.
  - **Status → "rule met; adoption PENDING implementation"** (owner decision before freeze). If
    adopted, it is implemented for all models, and the ladder is rerun before freeze.
- **F3 (MEDIUM, interpretation) — fit variance is the same size as the effects.**
  - Dropping 876 rows of 2 patients moved M1 by +4 episodes. That is larger than any
    C1 / C2a / C2b / M3−M2 difference (1–3 episodes).
  - The patient bootstrap does not include model-fit variance.
  - **Ordering among M2 / M3r / M3 / M3_compact / M1_pb6 on T is uninformative.**
  - A seed / fold-permutation repeat on T is proposed (P-B11).
- **F4 (LOW–MEDIUM):** the "not leakage" inference and the "no-learning" label were corrected
  (DEC-H, P-C9, PROGRESS).
- **F5 (LOW):** the inert-column explanation was corrected in DEC-H.
- **F6 (LOW) — pre-registration gaps.**
  - P-B8 used all-T log-loss with treated sens. The treated log-loss (−4.1 %) also meets the
    rule, so the outcome is unchanged.
  - The P-B1 / P-B6 metric clip (1e-15) and P-B6 on calibrated scores are not specified.
  - These must be stated in ANALYSIS_PLAN §5 before freeze (pending owner; not changed here).
- **F7 (LOW) — fixed** in fce4c4b:
  - the P-B1 / B6 / B8 rules and the P-B6 masks are now pure functions;
  - 6 new SYNTHETIC fixture tests cover the label, mask, contradiction rule, the three
    decisions and OOF assembly;
  - 421 tests pass.
- **F8 (LOW) — fixed:**
  - the `s6_inputs.parquet` sha256 is now in the run provenance;
  - the smoke-run calibrator-order fix is explained in EXPERIMENT_LOG.
- **F9 (LOW, suspected):** pooled OOF from 5 fold calibrators. This is standard and applied
  equally to all models. A per-fold check is optional.
- **Verification run:** `T-AGG-dev-s6-20261018T153341Z` on clean fce4c4b gave the same results_sha256 `e81268ae…` as
  the official runs. The refactor leaves results unchanged.
- **Class**: A (code / tests / docs); B (P-B10, P-B11 proposals) · **Date**: 2026-10-18 · **Commit**: fce4c4b

## DEC-2026-10-18-J · S7: policy, replay and API (implementation decisions + review outcome)

Class A unless marked. Code: 457b770 (S7), 9b154bf (review fixes). No protocol change.

- **Single policy implementation.**
  - `policy.decide.gate` (S5) is shared by the live runner and the offline evaluation replay.
  - `decide()` composes `gate`, `classify` and `should_notify`. It never raises; a malformed
    inference response (None, NaN, outside [0, 1]) becomes SYSTEM_ERROR.
  - Tags (LOW_CONFIDENCE, MED_TIMING_UNKNOWN:<class>, EVENT_REJECTED) qualify forecast states
    only and never change the state or the notification (property-tested).
  - `current()` turns a decision older than 20 min into INSUFFICIENT DATA (NO_RECENT_READING),
    so a stale prediction is never shown as current.
  - Display texts are fixed in `policy/messages.py`: never "safe", no treatment advice.
  - Probability text is `<1%` / `>99%` at the extremes, so 0 % is never shown (DEC-2026-10-18-I
    F1).
  - Offline evaluation uses vectorised equivalents of `classify` / `should_notify`. Equivalence
    is shown by tests and by the measured parity below (review F8; the docstring is corrected).
- **Strict artefact (ADR-009 realised; `models/artifact.py`).**
  - Contents: model.txt, calibrator.json, policy.json, feature_range.json, manifest.json.
  - Refusal conditions:
    - any file hash differs;
    - a file is missing;
    - the feature-spec, config, pharma or dictionary hash differs from the running system;
    - the level or feature list differs;
    - the content is corrupt;
    - thresholds fall outside 0 ≤ τW ≤ τA ≤ 1, or the strict comparator is set;
    - the calibrator is not a monotone map into [0, 1].
  - `--expect-sha` pins the manifest. A CONFIRMATORY artefact must be pinned, so a manifest
    edit cannot relabel a DEVELOPMENT model (review F1).
- **DEVELOPMENT artefact (T only; `evaluation/s7_artifact.py`).** It mirrors the deployment
  procedure on T with the frozen S6 choices:
  - S6 hyperparameters and 113 rounds, verified against results hash `e81268ae…`;
  - grouped OOF over T (S6 outer folds);
  - isotonic_interp fitted on the OOF predictions;
  - τA and τW by ANALYSIS_PLAN §3.5–3.6 on all T patients;
  - final fit on all eligible T rows;
  - P-B6 not applied (pending); M3_baseline.

  `M3-development-9590a582b0c1`: τA = 0.1230, τW = 0.0251. Rebuilds are bitwise identical. It is labelled
  DEVELOPMENT everywhere and is never evidence.
- **Replay.**
  - Recordings share a RELATIVE clock (offset from each recording's first event).
  - Total order: (offset, event rank, recording_key, stream position).
  - Speed affects pacing only.
  - Seek rebuilds from the start into a new log segment.
  - Logs go to logs/replay/<session>/ as decisions.jsonl, acks.jsonl, rejected.jsonl and
    session.json. Only session.json holds wall-clock fields, so the decision-log SHA-256 is the
    determinism fingerprint.
- **Error recovery** (resolves the S4 finding "one malformed event ends the twin"):
  - Live input check: glucose must lie in [20, 600] mg/dL (Table 25.1).
  - A rejected event (malformed, implausible, out-of-order, duplicate or foreign) is
    quarantined. It yields a SYSTEM_ERROR record at its time, and the previous immutable state
    is kept, so later state is never poisoned.
  - A rejected dose, meal or CBG adds the EVENT_REJECTED tag for 36 h.
  - An inference, gate or snapshot exception is SYSTEM_ERROR for that reading only.
  - After 5 consecutive rejections the runner halts until reset (circuit breaker).
- **API** (FastAPI + SSE, ADR-008; contract in ARCHITECTURE §4.10).
  - Typed, `extra=forbid` requests, with every control bounded.
  - Recordings come from the T catalogue only, addressed by key, never by path.
  - Errors are typed with no stack trace; binds to 127.0.0.1; no network calls.
  - All service access is serialised by one asyncio lock. Mutations (seek/step/advance/select)
    run off the event loop, and the clock tick is capped at 1 s (review F3).
  - The stream is versioned (v1) with message types session / tick / decision / notification /
    error / bed_state / acknowledgement. `bed_state` pushes every change of the DISPLAYED state,
    including staleness (review F4).
  - Explanations (top-3 grouped TreeSHAP on the raw margin) are given for the current forecast
    only (review F5).
  - Slow subscribers are disconnected; at most 16 subscribers.
- **Acknowledgement.** Exactly the four reason codes, with user_role ∈ {nurse, physician,
  researcher}. Only notifications can be acknowledged, once each; acknowledgements are logged
  to acks.jsonl.
  - **Deviation from Table 25.1:** no free-text `note` field. This is privacy-safe and nothing
    downstream reads it.
- **P-C7 (Class C, pending).** Not implemented. The blueprint warm-up rule stays active
  (`warmup_restart_after_gap_min: null`) and the hook is ready.
- **Measured (`T-AGG-s7-engineering-20261018T163321Z`, `T-AGG-s7-engineering-20261018T163810Z`; clean 9b154bf; results `6d2517cd…`, identical):**
  - **Parity:** offline vs live on all 34 T recordings (33,464
    readings): 0 time, forecast-set, probability (bitwise), notification and gate-state
    mismatches.
  - **Determinism:** identical decision-log hashes across two full replays.
  - **Error injection:** 30 events on 6 real records; 0 later
    decisions changed; final states equal.
  - **Long run:** 13.94 days at ×600 with no retained memory growth.
  - **Latency:**
    - per reading end-to-end p50 1.5 ms / p99 4.5 ms (target
      < 200 ms);
    - snapshot 0.89 ms, predict 0.11 ms,
      decide 0.007 ms;
    - API (TestClient) ward 3.2 ms, patient
      4.0 ms;
    - replay throughput 629 events/s.
  - **In-sample description only:** LOW_CONFIDENCE on 16.1% of forecasts (→ P-B12);
    MED_TIMING_UNKNOWN on 3.8%.
- **Negative / superseded:** `T-AGG-s7-engineering-20261018T161559Z` (clean 457b770). Its error-injection design put 5 bad
  events back to back, which tripped the circuit breaker, so later events were refused. That
  is correct behaviour, but an invalid poisoning test. The benchmark was fixed (injections
  spaced) and rerun.
- **Review** (independent, 457b770): no CRITICAL or HIGH findings.
  - F1, F2, F3, F4, F5, F6, F8, F9 and F10 are fixed in 9b154bf, with tests.
  - F7, the display semantics of a rejected non-CGM event, is raised as P-C10 for the owner.
- **Class**: A (+ P-C10 / P-B12 raised) · **Date**: 2026-10-18 · **Commit**: 457b770, 9b154bf

## DEC-2026-10-19-K · S8: clinical frontend (implementation decisions + review outcome)

Class A. Code: 7b66be1 (S8), 25c2d88 (review fixes). No protocol change. Design and architecture:
docs/FRONTEND.md.

- **Stack as ADR-007/008**, with versions moved to releases outside known advisories and at least two
  weeks old: Next 16.3.8 (static export), React 19.3.0, ECharts 6.1.0 (SVG renderer,
  tree-shaken), TanStack Query, Tailwind 4, Vitest 5, Radix (dialog, tooltip). `npm audit`: 0.
  shadcn/ui was not adopted: two Radix primitives and our own tokens were enough, and a library
  look was explicitly unwanted.
- **No scientific logic in the browser.** These are added to the backend instead:
  - bed and patient display fields: trend from the canonical `cgm_slope30`, `reason`, a
    deterministic `summary`, `stale` and `cgm_low` from the policy rules;
  - a 24-h `timeline`;
  - `ledger_entries` from the twin's OutcomeLedger, including OUTCOME_UNKNOWN at the end of a
    recording;
  - typed `/api/meta` and `/api/evidence`, with `excludes_zero` computed server-side;
  - the post-hoc level-rule diagnostic, quoted from S6.

  An unknown state string renders as SYSTEM ERROR.
- **Deterministic summary** (`policy/messages.summary`) replaces the dropped LLM idea. It is a
  template over validated fields: unavailable values are omitted, there is no advice, and it is
  unit-tested.
- **Evidence curves** (`hyposense dev evidence`): the S6 OOF scores are checked against their
  recorded hash and run through the canonical S5 harness. They reproduce S6 sens@1FA exactly
  (10/10) and contain aggregates only.
- **P-C10 (PENDING)**: `serve --pc10 badge` is a development switch for option (b). The default
  remains the current specification (SYSTEM ERROR).
- **P-B12**: LOW_CONFIDENCE is rendered as a quiet tertiary tag and never as a warning.
- **Lost connection**: if the service or stream is unreachable, ward and patient states are
  hidden, a banner says the values are not current, and the replay controls are disabled.
  Stale values are never shown as current.
- **Static export serving**: Next 16 requests `__next.<seg>.__PAGE__.txt` while the export
  writes `__next.<seg>/__PAGE__.txt`. A narrow, traversal-safe mapping in `ExportFiles` fixes
  this. Before the fix, client navigation logged 25 × 404.
- **Screenshots** show T patient traces, so they stay in the git-ignored
  `artifacts/screenshots/`.
- **Negative / superseded runs**:
  - `T-AGG-dev-evidence-20261018T174431Z` and `T-AGG-s8-ui-audit-20261018T183303Z` ran on an
    uncommitted tree. They were deleted and regenerated on clean commits.
  - Two audits taken at 18:45 queried a stale server left over from the interrupted session.
    They were deleted.
  - `T-AGG-s8-ui-audit-20261018T184552Z` / `T-AGG-s8-ui-audit-20261018T184600Z` (clean, 9f457b5) are superseded by the post-review audits.
- **Review** (independent, 4 perspectives): no CRITICAL findings.
  - **F1 (HIGH):** a stale ward stayed on screen after the backend died.
  - **F2:** the notification column was clipped at 1280 px.
  - **F3:** the wording scan was vacuous; `\b` in a JS template literal is a backspace
    character. It now has positive controls.
  - **F4:** C0 was over-readable. A caveat and the post-hoc level-rule diagnostic are now shown;
    P-C9 remains pending.
  - **F5–F10:** duplicated thresholds, a colour-only status under 1280 px, extra tab stops,
    chart gaps, slider reset, reconnect scope.

  All ten are fixed in 25c2d88, with tests where testable.
- **Class**: A · **Date**: 2026-10-19 · **Commit**: 7b66be1, 25c2d88

## DEC-2026-10-19-L · Pre-freeze Class B: P-B10, P-B11, P-B12 (T only, DEVELOPMENT)

- **Protocol**: written before any run (docs/PROPOSALS.md, commit 6b1ad05).
  - Fixed grid: fold seeds {2026, 2028, 2029} × model seeds {2026, 2028–2031}.
  - Frozen S6 hyperparameters at full precision, 113 rounds, S5/S6 harness.
- **Runner**: `hyposense dev prefreeze` (evaluation/prefreeze.py). E was never loaded.
- **Runs**:
  - **Official**: `T-AGG-dev-prefreeze-20261019T032309Z` and `T-AGG-dev-prefreeze-20261019T034056Z`, both on clean e0931cf. `results_sha256` `432869dc…` is identical across the two.
  - **Integrity gate**: the canonical configuration reproduces the S6 `oof_sha256` bitwise, using the full-precision hyperparameters.
  - **Superseded**: `T-AGG-dev-prefreeze-20261019T023957Z` (913864e) computed P-B10 LL_u/ECE on treated rows. The pre-specified set is the P-B1 set (all patients' pooled held-out rows, as in S6 P-B1). It was fixed in e0931cf; the protocol itself is ambiguous, since "primary population: treated" sits next to "(the P-B1 set)" (review F1).
    - In the superseded run, P-B10 was NO MATERIAL DIFFERENCE with R3 11/15.
    - With the corrected set, R3 is 4/15, so the outcome becomes INCONCLUSIVE.
    - In both runs nothing is adopted.
  - **No other runs**: no runs preceded the rule commit 6b1ad05.
- **P-B10 → INCONCLUSIVE** (pre-specified rule; current `isotonic_interp` stays).
  - **M1, canonical, P-B1 set:**
    - LL_u: current 0.04017, floored 0.04019, Platt 0.04037, raw 0.04025.
    - ECE: current 0.00060, floored 0.00060.
    - Exact 0 outputs: current 6947, floored 0.
    - sens@1FA and partial area are identical (R0 holds for all grid models).
  - **Canonical outcome**: NO MATERIAL DIFFERENCE.
  - **Across the 15 configurations**: {'NO MATERIAL DIFFERENCE': 4, 'ADOPT floored': 11}, so R3 is 4/15 → INCONCLUSIVE.
  - **Why the configurations disagree**: in 11/15 configurations the current calibrator outputs **exactly 1.0** on some held-out rows (up to 27 on M1), negatives included, and in one configuration exactly 0 on 2 positives. Its unclipped log-loss is then infinite (R1), while the floored version never reaches 0 or 1 and costs at most ~0.05 % log-loss.
  - **Weakness of R3** (review F2): R3 compares against the canonical *label*, and the canonical seed happens to be one of only 4 where the current calibrator is admissible.
  - **Rule kept**: the rule is applied as written, and the floored-calibrator question is raised for the owner.
  - **P-B6 SENSITIVITY** (M1_pb6, canonical): NO MATERIAL DIFFERENCE.
- **P-B11 (descriptive; isotonic_interp; treated; 15 configurations; only 3 independent fold partitions)**:
  - **sens@1FA, mean ± SD:**
    - M1 0.864 ± 0.039
    - M2 0.873 ± 0.034
    - M3r 0.879 ± 0.042
    - M3 0.907 ± 0.018
    - M3_compact 0.907 ± 0.025
  - **Contrasts** (first better / second better / ties):
    - M3−M2: sens 12/0/3 (median +0.0357, leaning); area 13/2/0 (median +0.0127, stable); log-loss 10/5/0 (median -0.0004, unstable).
    - M2−M1: sens 7/3/5 (median +0.0000, leaning).
    - M3r−M2: sens 7/3/5 (median +0.0000, leaning).
    - M3−M3r: sens 11/2/2 (median +0.0357, leaning).
    - M3_compact−M3: sens 5/3/7 (median +0.0000, leaning); area 8/7/0 (median +0.0045, unstable); log-loss 9/6/0 (median -0.0001, unstable).
  - **Ranking**: M3 ranked first on sens@1FA in 9/15 configurations. The calibrator choice changed the M1–M3 ranking in 0/15.
  - **Reading**: 45 readings (5 contrasts × 3 metrics) under the current calibrator; only M3−M2 partial area reaches "stable" (13/2). M3 never ranked below M2 on sens@1FA (12 better, 3 ties), but the median gain is one episode-step (+0.036).
- **P-B12 → REMOVE TAG** (pre-specified rule; M3, current calibrator, OOF ranges from training folds only):
  - C0 current: 57.4% tagged; separation -0.097 [-0.198, +0.042], 0/15 configs positive.
  - C1 key inputs: 26.6% tagged; separation -0.175 [-0.274, -0.079], 0/15 configs positive.
  - C2 0.1–99.9 %: 45.1% tagged; separation -0.008 [-0.108, +0.145], 5/15 configs positive.
  - **No candidate separates reliability**: tagged forecasts are, if anything, *more* informative (higher BSS).
  - **The S7 figure was in-sample**: "16.1 %" was measured in-sample. On held-out patients the current tag fires on ~57 %, driven by per-patient static context (BMI/age/weight) and medication exposure falling outside other patients' ranges (review F3).
- **Class A fixes**:
  - **Full precision**: `frozen_params` now reads the full-precision S6 best trial from trials.csv (results.json rounds to 6 digits). It is shared with the S7 DEVELOPMENT artefact builder.
  - **Stale artefact** (review F5): the existing artefact `M3-dev-20261018T160956Z` was built with the rounded values. It is kept so the S7/S8 evidence stays reproducible, and will be rebuilt at freeze.
  - **Review F6/F7**: `pb12_criteria` extracted and boundary-tested; a "tied" stability reading added. Neither case occurs in the official runs.
- **Recorded, not changed**:
  - **Inner folds** (review F8): in non-canonical configurations the inner folds use the fold seed.
  - **Bootstrap** (review F7): non-finite bootstrap resamples in the P-B12 CI are dropped, and the count was not stored.
- **Not decided here (owner)**:
  - adopting the floored calibrator despite INCONCLUSIVE;
  - implementing REMOVE TAG in the live runner and UI (Table 14.1 lists LOW CONFIDENCE, display only);
  - P-B8, P-B6, P-C7, P-C9, P-C10, ANALYSIS_PLAN §5.
- **Review** (independent): no CRITICAL findings; F1–F9 addressed (code or documentation).
- **Class**: B · **Date**: 2026-10-19 · **Commits**: 6b1ad05, 913864e, e0931cf, d8d3c7c, eb5baae

## DEC-2026-10-19-M · Final pre-freeze resolution (owner-approved)

Owner approval 2026-10-19. Canonical text: ANALYSIS_PLAN §5 and §6 (FINAL). Branch
`prefreeze-finalization`.

- **P-B10 → canonical calibrator = `isotonic_interp_floored`.** FINAL HUMAN PROTOCOL DECISION,
  distinct from the experimental verdict, which stays **INCONCLUSIVE** (DEC-2026-10-19-L,
  unchanged).
  - **Reasons:** no exact 0 %/100 % outputs; sens@1FA and partial area unchanged; canonical
    log-loss cost negligible (0.04019 vs 0.04017); 11/15 development configurations favoured
    adoption; the unfloored calibrator gave exact edge probabilities on held-out rows in 11/15.
  - **Floor:** the pre-specified p_lo rule, with no new value.
- **P-B12 → LOW_CONFIDENCE removed from the live product:** policy metadata, API, SSE, UI,
  summary and active docs. The history (tested, rejected) is preserved. Genuine quality flags
  are kept: SENSOR FAULT SUSPECTED, MED_TIMING_UNKNOWN, INPUT REJECTED / EVENT_REJECTED,
  INSUFFICIENT DATA and SYSTEM ERROR.
- **P-B8 → canonical M3 = full M3 (100 features).** M3_compact is a DEVELOPMENT ablation only.
  - **Reasons:** no consistent advantage (P-B11); M3 ranked first more often; slightly lower
    variability of the primary metric; the intended full exposure representation is more
    defensible.
- **P-B6 → SENSITIVITY ONLY (SA9).** The canonical population is unchanged.
  - **Reasons:** evidence comes from very few affected T patients; the result depends partly on
    calibration.
- **P-C7 → approved for the POLICY ONLY.** The warm-up re-anchors after a CGM gap > 120 min
  (strict), and LOW NOW still applies. Labels and label eligibility are unchanged.
  - **Consequence:** a label-eligible time after such a gap cannot alert, for every model alike.
  - **Measured on T:** 0 gaps > 120 min, so T results are unaffected. In E it affects at most
    one recording.
- **P-C9 → CGM-level rule = POST-HOC DEVELOPMENT REFERENCE** (alerts at CGM < 81 mg/dL; S6
  diagnostic; not retuned). It is not M0, not M1, plays no role in G4 or H1, and is never
  confirmatory.
- **P-C10 → option (b):** keep the current clinical state, show the INPUT REJECTED badge,
  quarantine and log the rejected input, continue processing later valid events, and keep the
  circuit breaker. A rejected CGM reading remains SYSTEM ERROR.
- **ANALYSIS_PLAN §5 → FINAL** (17 items) and **§6 → FINAL** (Blueprint §15 selection rule and
  Table 20.4).
- **Pharmacist review:** the Blueprint §12.3 requires it before freeze. No human review has been
  received, and no owner waiver ("no pharmacist available") is recorded, so **freeze is blocked
  on this item only**. Nothing about the review is fabricated.
- **Class**: C (owner-approved) · **Date**: 2026-10-19

### DEC-2026-10-19-M · addendum: freeze-candidate verification and final review

- **Freeze candidate:** `T-AGG-candidate-20261019T045108Z` / `T-AGG-candidate-20261019T045338Z` on a7efa25, identical (`c0cbe721…`). Artefact
  `M3-development-3271a3206765` (format 2, floored calibrator, full precision).
- **Floor consequence (disclosed, rule unchanged):** in fold 4, p_lo = 0.47 % (M2) / 0.26 % (M3)
  and ≈ 70 % of that fold's rows are clamped. Pooled ECE M2 0.0013 → 0.0022 and M3 0.0013 →
  0.0017; slope ≈ 1.07–1.08 (inside the band rule). sens@1FA, area, thresholds and decisions are
  unchanged.
- **§6 selection rule:** its literal reading is written out (E-treated, pooled OOF calibrated
  probabilities, point estimates, "not worse" = ≤, no tolerance). No criterion was added. **Owner
  confirmation requested.** If the owner reads the rule differently, that is a Class C change
  before freeze.
- **Final review** (five perspectives): no CRITICAL or HIGH findings. Fixed:
  - **F1:** the Evidence page showed the S6 calibrator's ECE next to the served calibrator.
  - **F2:** the freeze tool now ties the committed artefact to the candidate run record.
  - **F3:** stale docs.
  - **F5:** the floor consequence was undisclosed.
  - **F6:** a cross-reference.
  - **F7:** the freeze tool now fails on unreadable runs, refuses to overwrite and runs the
    frontend tests.
  - **F8:** the limitations now say the pharmacist review is PENDING.
  - **F4:** handled as the literal reading above.
- **Freeze attempt:** `hyposense freeze` → **ERROR — FREEZE ABORTED**. The only failing invariant
  is `pharmacist_review`; see PROGRESS.
