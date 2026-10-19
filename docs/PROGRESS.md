# Progress Log

Append-only, chronological. Never delete entries.

---

## 2026-10-18 — S0: Understanding, repository audit and project control system

### Objective
Establish a professional execution baseline before any implementation: understand the
blueprint and CLAUDE.md, audit the repository, review the architecture critically, and create
the project control documents and minimal scaffolding.

### Work Completed
- Read CLAUDE.md and the full Blueprint v2.0 (all parts and appendices, 17 figures inspected
  for architecture, policy state machine and UI wireframe).
- Repository audit: the repository contained only `CLAUDE.md` and
  `docs/HypoSense_Twin_v2_Blueprint.docx`. It was not a git repository and had no code, data,
  audit scripts or partition file.
- Created a reproducible blueprint extraction (`scripts/extract_blueprint.py`, stdlib only) and
  a structured digest that classifies every element as REQUIRED, RECOMMENDED, OPTIONAL,
  EXPERIMENTAL, REJECTED, PENDING or ASSUMPTION.
- Initialised git (`main`), the Python 3.11 environment with uv and a committed lockfile, the
  `src/hyposense` package skeleton (12 subpackages with documented responsibilities and no
  logic), and a CLI stub.
- Draft `configs/default.yaml` (Appendix F, with Class A/B/C markings) and
  `configs/pharma.yaml` (all kernels ILLUSTRATIVE and blocked from freeze).
- Tests: protocol-constant lock (Class C values pinned) and import-boundary leakage guard.
- Control documents: ARCHITECTURE, IMPLEMENTATION_PLAN, REQUIREMENTS_TRACEABILITY,
  TEST_STRATEGY, DECISION_LOG (ADR-001…015), EXPERIMENT_LOG, PROPOSALS, CURRENT_STATE,
  NEXT_STEPS, PROGRESS, BLUEPRINT_DIGEST.

### Files Changed
New: `.gitignore`, `.gitattributes`, `.python-version`, `pyproject.toml`, `uv.lock`,
`README.md`, `configs/default.yaml`, `configs/pharma.yaml`, `data/README.md`,
`scripts/extract_blueprint.py`, `src/hyposense/__init__.py`, `src/hyposense/cli.py`,
`src/hyposense/<12 subpackages>/__init__.py`, `tests/regression/test_protocol_constants.py`,
`tests/leakage/test_import_boundaries.py`, `docs/*.md`,
`docs/blueprint/HypoSense_Twin_v2_Blueprint.extracted.md`, and placeholder `.gitkeep` files.
Unchanged: `CLAUDE.md` and the blueprint .docx.

### Tests Executed
- `uv sync --python 3.11` → environment created (Python 3.11.9).
- `uv run pytest -q` → **16 passed**.
- `uv run ruff check src tests scripts` → all checks passed.
- `uv run mypy src` (strict) → no issues in 14 files.
- `uv run hyposense --version` → stub responds.

### Results
A scaffolding-only baseline. **No data was loaded, no model was trained and no scientific
result exists.**

### Problems Found
1. The competition registration deadline (REPORTED) is 18 Oct 2026 19:00 IST, which is today.
2. The blueprint's audit scripts and `partition.csv` are absent, so none of the VERIFIED audit
   numbers can be reproduced from this repository (P-C4).
3. The primary-endpoint computation is ambiguous: cooldown makes FA/day possibly
   non-monotone, the threshold grid is unspecified, and isotonic produces ties (P-C2, P-B1).
4. FA counting and the policy-replay semantics in evaluation are unspecified (P-C3).
5. Safety: Table 14.1's order hides sensor-floor lows as INSUFFICIENT DATA (P-C1).
6. The τW definition is ambiguous (P-C6). The boosting-round procedure in confirmatory
   training is undefined (P-B2). CSII basal handling in projections is open (P-B3).
7. `make` is unavailable on the development machine, so a CLI replaces it (ADR-006).
8. The CLAUDE.md blueprint path is wrong (H-1).

### Decisions Made
ADR-001 to ADR-015 (DECISION_LOG.md). Class A items that took effect now: ADR-002, 003, 006
(stub), 013 and 014. All Class C items are awaiting approval.

### Remaining Work
See NEXT_STEPS.md (P0: registration, Class C decisions, request originals, S1).

### Commit
`5314ba9` — S0 baseline (authored with the machine's git identity; see CURRENT_STATE open issues).

### Next Task
S1: official data acquisition and structural audit (G0/G1).

---

## 2026-10-18 — S1: Official data acquisition, production loader, structural audit, G0/G1

### Objective
Establish a trustworthy data foundation: the official source with provenance, a production
loader that later stages reuse, an aggregate structural audit, reconciliation against the
blueprint, machine-readable G0/G1, and the P-C4 partition.

### Work Completed
- **Startup check**: HEAD `9617413` matched the documented S0 state, and the tree was clean.
- **P-C4**: searched the repository, the E: drive and the user folders. The blueprint author's
  source bundle (`HypoSense_v2_sources[.zip]` in Downloads) holds `partition.csv`, `audit.py`
  and `audit2.py`. The scripts were read (not executed). An exact re-implementation of the
  split reproduces the original 100/100. Imported as `configs/partition.csv` v1.0.0
  (patient_id, partition only), SHA-256 pinned (ADR-016).
  - Finding: the shipped `audit2.py` is not the exact version that produced
    `audit2_summary.json` (its θ grid and output keys differ), so the bundle's provenance is
    PARTIAL.
- **Official data**: figshare article 21600933. Five versions exist, with three distinct
  contents (v1; v2 = v3 = v4; v5). v5 (2023-10-30) is canonical; v1/v2 were downloaded for
  reconciliation. All three are verified against figshare MD5, with SHA-256 pinned. v5's
  `note.txt` documents +188 rows in 2003_0 and 2029_0, including a CGM device replacement.
- **Manifest**: 111 files; files_sha256 `5f9d65b4…`; verified on every `load_dataset`.
- **Loader**:
  - strict identity and discovery;
  - an explicit table for the 5 header variants;
  - raw-cell parsing; per-row flags and typed issues; no deletion;
  - +08:00 epoch seconds, with sub-second values rounded;
  - an explicit CGM-series exclusion account;
  - summary loader (one row per recording).
- **Scoped access**: TUNING_ONLY / AGGREGATE_AUDIT / ALL_AFTER_FREEZE, with static
  confinement tests (P-C5 safeguards).
- **Structural audit** (aggregate-only), figshare version reconciliation, mechanical blueprint
  reconciliation, and **G0/G1** gate JSON.
- **Verification**: the published 112,475 was VERIFIED against the data descriptor's table on
  nature.com.
- **Timezone evidence**: local-hour histograms (meals peak at 07/11/17).
- **CLI**: `data fetch|extract|manifest|validate`, `partition verify`, `audit run`,
  `gates show`.
- **Approved P-C1/2/3/5/6** recorded. `docs/protocol/ANALYSIS_PLAN.md` §1–3 written with the
  exact first-crossing algorithm, edge cases, the OUTCOME-UNKNOWN class and the τW definition.

### Files Changed
- New:
  - `configs/dataset.yaml`, `configs/partition.csv`, `configs/partition.provenance.json`,
    `configs/reference/blueprint_audit.yaml`;
  - `data/MANIFEST.json`, `data/MANIFEST.sha256`;
  - `scripts/import_original_partition.py`;
  - `src/hyposense/common/{hashing,config,provenance,timeconv}.py`;
  - `src/hyposense/data/{source,manifest,columns,records,loader,summary,quality,partition,dataset}.py`;
  - `src/hyposense/audit/{__init__,structural,versions,reconcile,gates,partition_check,run}.py`;
  - `tests/conftest.py`, 6 unit test files, `tests/integration/test_real_data.py`;
  - `docs/protocol/ANALYSIS_PLAN.md`;
  - evidence: `experiments/runs/ALL-AGG-audit-structural-20261017T2135*/`,
    `artifacts/gates/G0.json`, `artifacts/gates/G1.json`.
- Modified: `configs/default.yaml` (partition pin, gate criteria), `pyproject.toml` (ruff
  per-file ignore), `.gitignore` (evidence paths), `src/hyposense/cli.py`, test guards and
  locks, `README.md`, `data/README.md`, all control docs.

### Tests Executed
- `uv run pytest -q` → **93 passed**: unit 67, leakage/static 12, regression 9,
  integration 5 on real data.
- `uv run ruff check src tests scripts` → clean. `uv run ruff format` → applied (ADR-021).
- `uv run mypy src` (strict) → clean, 34 files.
- `uv run hyposense audit run` twice on clean commit `f68f98a` → identical results_sha256
  `09e780bd…`; G0 PASS, G1 PASS.
- `uv run hyposense partition verify` → PASS.

### Results (MEASURED, figshare v5)
- 109 recordings / 100 patients; 112,475 rows (= published, VERIFIED); 112,462 CGM readings.
- 1170.6 monitored days; CGM parse rate 1.0; 99.99% of intervals ≤20 min.
- Blueprint structural values: 11 MATCH, 8 EXPECTED DIFFERENCE, 0 UNEXPLAINED. v1/v2
  reproduce every blueprint structural value exactly, so the blueprint mirror = pre-2023-10-26
  figshare content.

### Problems Found (and handled)
- YAML 1.1 parsed `2003_0_20210615` as an integer, which first produced false "UNEXPLAINED"
  results. Fixed (quoted, plus a type guard and a regression test).
- git "dirty" counted the audit's own output files. Fixed and tested.
- Sub-second timestamps would have been truncated 1 s early. Now rounded and flagged.
- Unparseable medication text was classed as an error. It is now a warning, with the raw text
  preserved.
- Data anomalies: see CURRENT_STATE "Known anomalies". All are flagged; none are deleted.

### Decisions Made
DEC-2026-10-18-A (owner approvals), ADR-016 to ADR-021. New proposals: P-C7 (sensor-restart
warm-up) and P-B5 (IV dextrose).

### Independent Self-Review (CLAUDE.md §46)
| Concern | Finding |
|---|---|
| Silent data loss | None. Every row is kept, and CGM-series exclusions are counted by reason. 112,475 rows in = 112,475 out |
| Identity | File name is authoritative, with a strict pattern. The sheet-name mismatch (2014_0) and file-name date mismatches are flagged; the two 2014 recordings differ by content hash. No overlapping recordings within a patient. Period index ≠ chronology for 2 patients, so downstream must order by timestamp |
| Timestamps / timezone | Exact integer conversion; rounding is tested; +08:00 is supported by meal-hour histograms |
| Non-determinism | None found: two full runs give an identical results hash, and the same holds before and after reformatting |
| Parser assumptions | Header variants are explicit; unitless headers were checked against the mg/dL range |
| Gate errors | Pure functions with boundary tests (0.99 inclusive). The G0.7 explanation requires that missing-CGM rows lie only in note-listed recordings |
| Weak tests | One sloppy assertion and one wrong expectation were found during writing and corrected to exact values |
| Contract divergence | None. Paths follow ADR-002/017 |

### Remaining Work
S2 onward (NEXT_STEPS.md). P-C7 awaits the owner.

### Next Task
S2: label builder (test-first) and event audit (G2, G3b).

---

## 2026-10-18 — S2: Label builder, eligibility, event audit, G2 / G3b

### Objective
Make the target event, prediction eligibility, patient-level event accounting and label validity
precise, tested and reproducible. No model work.

### Work Completed
- Startup check: HEAD `267046b`, clean tree, manifest and partition hashes confirmed.
- **Test-first**: 34 hand-labelled trace fixtures and 4 loader-path cases cover all 30 brief
  items. They were written against stubs; 74 tests failed before implementation.
- **Label package** (`src/hyposense/labels/`):
  - typed `LabelConfig`;
  - an explicit episode state machine (L1, L2, single-reading);
  - eligibility with first-failing reason codes;
  - future-onset labels; warnable onsets;
  - the recording-level builder;
  - CBG validity; annotations (nocturnal, first-24h, SA4, sensor-floor runs);
  - the P-C7 warm-up hook (off).
- **Verification beyond tests**:
  - Hypothesis differential tests against a verbatim transcription of the blueprint's
    executable spec: 800 random traces, identical.
  - 7/7 boundary mutants killed.
  - **All 48 blueprint event values reproduced exactly on figshare v1 and v2** (348 L1,
    107,041 prediction times, 1,188 positives, 154/30 E-treated, label-validity statistics,
    m_w).
- **Event audit on v5**, G2 and G3b gate JSON, and the CLI `hyposense audit events`.
- **Scientific sanity review**: diagnosed the long-episode and low-coverage outliers as sensor
  artefacts in two T-untreated recordings, and quantified their extent per partition
  (aggregate for E).
- **Documentation**: ANALYSIS_PLAN §0 (operational protocol); proposals P-C8 and P-B6.

### Files Changed
- New:
  - `src/hyposense/labels/{config,episodes,eligibility,build,validity,annotations}.py`;
  - `src/hyposense/audit/{events,event_run,legacy}.py`;
  - `configs/reference/blueprint_events.yaml`;
  - `tests/unit/{label_fixtures,test_labels,test_label_validity_and_events}.py`;
  - evidence `experiments/runs/ALL-AGG-audit-events-20261017T2212*/`,
    `artifacts/gates/G2.json`, `G3b.json`.
- Modified: `configs/default.yaml` (eligibility keys, G2/G3b criteria), `audit/gates.py`,
  `audit/reconcile.py` (public `equal_values`), `cli.py`, `pyproject.toml`,
  `tests/integration/test_real_data.py`, `tests/regression/test_protocol_constants.py`, docs.

### Tests Executed
- `uv run pytest -q` → **194 passed** (unit 165, leakage 12, regression 9, integration 8).
- `ruff check` / `ruff format` clean; `mypy --strict` clean (43 files).
- `hyposense audit events` ×2 at clean commit `32f3245` → identical results_sha256 `2f92a0c9…`.

### Results (MEASURED)
- Legacy (v1/v2): 48/48 exact.
- v5:
  - L1 348 in 61 patients; L2 96 in 26; single-reading 430 in 67;
  - duration median 60 min (IQR 30–120);
  - end reasons: 346 recovered, 2 record end, 0 gap;
  - nocturnal 115; prediction times 107,210; positives 1,188; warnable 306.
- **G2 PASS** (provisional): 154/30; half-width 0.113.
- **G3b TRIGGERED** (0.831 unconfirmed).

### Problems Found and Fixed
- A text-patch edit broke the per-level loop in `events.py`: end reasons, durations and nadirs
  became empty and legacy reproduction fell to 45/48. **Caught by the reconciliation**, fixed,
  and covered by a new unit test (`test_measure_events_populates_every_section`).
- mypy: one variable name reused for prediction labels and patient ids (renamed); an untyped
  comparison.
- Fixture count was overstated as "38 fixtures" in places; corrected to 34 + 4.

### Problems Found (open)
- **Sensor artefacts**: two T-untreated recordings hold 37 % of T's L1 episodes → P-C8, P-B6.
- Treated status is provisional until S3.

### Decisions Made
ADR-022, DEC-2026-10-18-B (operational protocol = executable spec), ADR-023. Proposals P-C8
(approval needed), P-B6.

### Independent Review (fresh eyes)
| Concern | Finding |
|---|---|
| Off-by-one / interval boundaries | Pinned by fixtures and killed mutants |
| Gap handling | 30 min exactly does not end an episode; > 30 does; refractory after a gap starts at the first post-gap reading (spec) |
| Refractory | [end, end + 60) |
| Cross-recording contamination | None; per-recording, order-independent; tested |
| Patient ids | Patient-level aggregates use `patient_id`; partition lookup has 0 missing |
| Timestamps | Integer epoch seconds from `cgm_series` |
| Leakage | Labels are offline-only (import guard). Labels use the future by design; they are never features |
| E policy | Only aggregate E statistics; trace inspection limited to T |
| Discrepancy masking | None. Expected differences are mechanical (pre-v5 reproduces exactly; diffs confined to note-listed files) |
| Conclusion | No outstanding defects |

### Remaining Work
S3 onward. P-C8 and P-C7 await the owner.

### Next Task
S3: medication normalisation and exposure engine (G3; production treated status; G2 re-check).

---

## 2026-10-18 — S3: Medication normalisation, dose parsing, exposure engine, G3

### Objective
Turn logged medication into a defensible, causal, time-resolved exposure signal (M3) and a raw
timing representation (M3r), with the production treated population, G3, and a G2 re-check. No
model training.

### Work Completed
- Startup check: HEAD `49e2849`, clean tree, hashes confirmed. P-C8 approval recorded.
- **Raw inventory first**: 178 distinct strings across 5 columns, inspected before any rule was
  written; artefact `medication_inventory.json`.
- **Dictionary and parser**:
  - versioned CSV; content-aware grammars per column; parse statuses and flags.
  - Explicit handling:
    - pump suspension → PUMP_SUSPEND;
    - misplaced acarbose → oral (MISPLACED_COLUMN);
    - i.v. bags split into fluids, glucose and insulin (RATE_UNKNOWN);
    - pasted header → NON_MEDICATION;
    - SciLin M30, glarigine, NBSP, the combination tablet, implausible units (kept and flagged);
    - gliclazide formulation rule (15 mg → MR, INFERRED).
- **Kernel parameter verification**: a background research agent read FDA SPL, EMA SmPC and
  national SmPCs; 15/16 items verified with quotes (`docs/medication/PARAMETER_SOURCES.md`).
  `pharma.yaml` v1.0.0 has per-parameter status and none are ILLUSTRATIVE.
  - Corrected illustrative values: NPH duration 15 h → 24 h; degludec 24 h → 42 h; gliclazide
    split into MR and IR kernels.
- **Exposure engine**:
  - causal; vectorised; exact summation;
  - family activities, IOB, projections, SU and glinide exposure;
  - CSII reconstruction with a 6-h cap; i.v. flag; per-class quality states.
- **M3r** raw timing. **Production treated status.** The **P-C8** causal sensor-fault flag.
- **Medication audit**: coverage, treated set, pump and i.v. investigations, G3, G2 re-check,
  representation QA on T only. CLI `hyposense audit medication`.
- Docs: FEATURE_DICTIONARY (M3r/M3 contracts), PHARMACIST_REVIEW packet, ANALYSIS_PLAN §0b/§0c.

### Tests Executed
- `uv run pytest -q` → **281 passed** (unit 249, leakage 12, regression 9, integration 11).
- ruff and format clean; `mypy --strict` clean (52 files).
- `hyposense audit medication` ×2 at clean commit `88cdeac` → identical results_sha256 `29148c8e…`.

### Results (MEASURED)
- Parsing: 0 unparseable/ambiguous of 4,653 cells; insulin 828/828; oral 2,171/2,171.
- Treated: 72 (legacy 73; 2078 explained).
- **G3 PASS. G2 PASS (unchanged).**
- i.v. glucose: FLAG ONLY.
- Representation: plausible ranges; varies in all treated T recordings; 0.24 ms per reading.

### Problems Found and Fixed (verify → diagnose → replan)
1. **Bitwise truncation failure** (≈1 ulp) caused by BLAS summation order → exact fsum (ADR-025).
   0/5,984 mismatches afterwards.
2. **Pump delivery would have been fabricated** by the literal "rate persists" rule (median 39.5 h,
   up to 168 h, in 21 recordings that switched to injections) → 6-h continuation cap, evidence-backed
   (ADR-026).
3. **Legacy treated misclassification** (2078) → the production definition; G2 unchanged.
4. **Uncapped minutes-since** in the engine (up to 11 days) → capped at 1440, as in the blueprint.
5. **Provenance defect from S1**: a leading porcelain space mangled the first path, giving false
   "dirty" flags only. Fixed and regression-tested; earlier evidence remains valid (ADR-029).
6. A parse-rate counting bug in the audit draft (the `and` of two counts) was fixed before any
   run was reported.
7. Two test expectations and one stale hard-coded peak time in tests were corrected.
8. Lint: escape sequences, Counter annotations.

### Decisions Made
DEC-2026-10-18-C (P-C8 approved), ADR-024 to ADR-029, DEC-2026-10-18-D (production treated
set). P-B3, P-B4 and P-B5 resolved. New proposals P-B7 and P-B8.

### Independent Review (fresh eyes)
| Concern | Finding |
|---|---|
| Drug mapping | Matches labels; composition assumptions flagged (Gansulin 40R, SciLin M30) |
| Units | IU, mg (g→mg) and IU/h correct |
| Duplicate dose events | None; exact-duplicate rows are skipped and counted, and there are 0 |
| Future leakage | None; bitwise tests (synthetic property test and real T) |
| Formulation / route | Gliclazide rule tested; liraglutide s.c. in the non-insulin column; misplaced acarbose → oral |
| i.v. glucose | Not insulin |
| Pump suspension | Not a dose |
| Timestamps | Charted row time (ASSUMPTION; R1 jitter planned) |
| Kernels | Integrals and peaks tested; Bateman tail truncated at 1 % |
| Tails | Degludec 42-h flat; IOB includes basal on-board (max 31 IU, plausible) |
| Pharmacological claims | None beyond label statements; not clinically validated |
| Conclusion | No outstanding defect |

### What Remains Uncertain
- Pharmacist review.
- Gliquidone t½.
- Basal lag and the flat shape.
- Protamine-aspart ≈ NPH.
- Whether dose times reflect administration.
- Whether exposure adds information beyond M3r (C2b in S6).

### What Should Be Tested in S6
- P-B1 (calibration), P-B2 (rounds), P-B6 (artefact recordings in T), P-B7 (combined
  secretagogue), P-B8 (compact M3; detemir duration).
- C2b (M3 vs M3r).
- SA6 kernel duration scaling.
- R1 dose-time jitter.

### Next Task
S4: patient state engine and causal feature builder.

## 2026-10-18 — S4: Patient State Engine, causal Feature Builder, feature specification

### Objective
Build the per-recording digital twin and ONE causal feature implementation shared by offline
training-table generation and replay / inference. Prove causality on real tuning data. No
model training.

### Work Completed
- Startup check: HEAD `9c305af`, clean tree. Blueprint App. D, Table 11.1, §10.2, §12.2, §25 and
  the S3 contracts were read before any feature was defined.
- The executable spec `audit2.py` (author's bundle) was read for the exact M0 rule:
  (t − 35 min, t], ≥ 3 readings, g(t) + H × LS slope. Recorded as ANALYSIS_PLAN §0d.
- **State engine** (`state/`):
  - typed events with canonical same-timestamp order;
  - persistent append-only histories;
  - CGM state with a causal L1 episode tracker;
  - data-quality state built on the authoritative `data.quality` functions (P-C8 flag; P-C7
    hook kept);
  - medication state over the S3 engines (no re-implementation);
  - static context (allow-list; '/' → NaN), meals, CBG, forecast state, outcome ledger;
  - `update()` strict and order-checked; `try_update()` → SYSTEM_ERROR;
  - one state per recording;
  - recording adapter (`stream.py`).
- **Features** (`features/`):
  - registry `spec.py`, one definition per feature, groups G1–G8 + G78;
  - level membership M1 38 / M2 72 / M3r 95 / M3 100;
  - missingness policy;
  - generated `artifacts/features/feature_spec.json`, locked;
  - group functions; `FeatureBuilder.union` / `snapshot`;
  - offline builder = event-by-event replay;
  - export with provenance;
  - T-only scope guard.
- **S4 audit** (`hyposense audit features`):
  - truncation equality at every eligible T time (raw record truncated, full pipeline re-run);
  - parity at every reading and level;
  - four future perturbations;
  - tracker vs labels;
  - distributions, redundancy, leakage smell test, event study, performance.
- **Independent review** (separate agent): no CRITICAL or HIGH findings, no leakage path. Fixed:
  - G7 indicator definition;
  - ledger finalize at recording end;
  - engine cache under `replace`;
  - a defence-in-depth sealed-partition guard in the adapter;
  - config / spec name consistency;
  - unrecognised regimen text flagged;
  - G5 audit privacy.

  Regimen temporal status was documented (MEASURED on T).
- Docs:
  - FEATURE_DICTIONARY (full rewrite);
  - ANALYSIS_PLAN v0.4 §0d;
  - ARCHITECTURE §4.5a;
  - DECISION_LOG ADR-030..035, DEC-2026-10-18-E;
  - PROPOSALS P-B8 evidence, new P-B9;
  - TRACEABILITY, EXPERIMENT_LOG, TEST_STRATEGY, IMPLEMENTATION_PLAN.

### Tests Executed
- `uv run pytest -q` → **362 passed** (unit 317, leakage 18, regression 10, integration 17).
- ruff clean; `mypy --strict src` clean (71 files).
- `hyposense audit features`: runs 2–3 on clean `dcb164f` and runs 4–5 on clean `df90031`,
  identical results_sha256 `db39f39a…`.
- Mutation checks: two tracker mutations and one adapter future-leak mutation were each caught by
  the tests.

### Results (MEASURED, T only)
- Truncation equality 31,292 / 0. Parity 133,856 / 0. Perturbation 1,200 / 0. Tracker 33,464 / 0.
- Determinism: two builds identical.
- REQUIRED violations 0; impossible values 0; smell-AUC 0.
- 21 constant and 8 near-constant columns on eligible T rows, all structurally explained.
- 41 |ρ| ≥ 0.95 pairs; 0 identical columns.
- Event study: insulin activity peaks at +60 min after s.c. boluses; no exposure before the dose.
- Live path 0.74 ms per reading (p99 1.79 ms). Exhaustive audit ~10 min.

### Problems Found and Fixed (verify → diagnose → replan)
- **Determinism false in run 1**: `frame_sha256` hashed object pointers of pandas `str` columns.
  The arrays were identical. Fixed with value-based hashing and a test.
- **Feature cost 3.3 ms per reading**: profiling showed `raw_timing` re-categorising every event at
  every reading. `RawTiming` is now cached per log length.
- **Audit runtime 16–19 min**: Windows E-core throttling of the background workers, not a hang
  (diagnosed live). Fixed with the throttling opt-out, single-thread BLAS and progress logging:
  10 min, identical results (ADR-035).
- **Audit bounds false positive**: `cgm_min_` prefix matched; fixed.
- **eGFR 257 rejected** by an over-tight validation bound; widened (keep-and-flag rule).
- **Lag test fixture wrong**: the code was right, the fixture used 8 min against a 7.5-min
  tolerance.

### Next Task
S5: evaluation harness and M0 (not started).

## 2026-10-18 — S5: Evaluation harness, metrics, patient-cluster bootstrap, M0

### Objective
Build the model-agnostic evaluation machinery every later model uses, prove it on hand-computed
cases and the blueprint's Table A.2, and measure M0 on the v5 tuning partition. No learned models.

### Work Completed
- `evaluation/`:
  - policy-replay accounting (§2);
  - exact operating curves (per-patient step functions; each resample on its own grid);
  - first-crossing sens@B, τA/τW, partial area;
  - operating points (lead, precision, warnable ceiling, abstention, per-patient);
  - window and calibration metrics (probabilities only);
  - paired patient-cluster bootstrap;
  - metric registry;
  - the `hyposense eval m0` runner, with provenance.
- `policy/decide.py`: gate (Table 14.1 + P-C1), classify (NaN → INSUFFICIENT DATA),
  should_notify.
- `models/m0.py`: M0 via `features.cgm`.
- Legacy loader: `load_legacy_tuning`.
- Reference: `configs/reference/blueprint_m0_table_a2.yaml`.
- Independent review (separate agent): no CRITICAL findings. Fixed:
  - resample grid under the strict comparator;
  - a stricter EXPECTED rule with the exact tie bound;
  - the pairing guard;
  - the k*=1 flag;
  - live NaN handling;
  - a stepwise-vs-vectorised test.
- Docs:
  - ANALYSIS_PLAN v0.5 (§5 DRAFT; §0d exactness);
  - ADR-036..038, DEC-2026-10-18-F;
  - EXPERIMENT_LOG, TRACEABILITY, TEST_STRATEGY, FEATURE_DICTIONARY (spec v1.0.1).

### Tests Executed
- `uv run pytest -q` → **410 passed** (unit 362, leakage 18, regression 10, integration 20).
- ruff clean; mypy --strict clean (78 files).
- `hyposense eval m0` ×2 on clean 671a7ca: identical results_sha256 `7864a0d0…`.
- `hyposense audit features` re-run on clean 3487373: 0 mismatches.

### Results (MEASURED; DEVELOPMENT only)
- **Table A.2:** 7/8 MATCH. θ = 45 EXPECTED DIFFERENCE (44 exact ties; reference bracketed;
  polyfit replay reproduces the treated row only).
- **v5 T M0:** sens@1FA 0.626 (0.491–0.837) treated, 0.610 (0.418–0.810) all; θA 54.0 / 52.2
  mg/dL; precision 0.12 / 0.16; median lead 45 / 30 min.

### Problems Found and Fixed (verify → diagnose → replan)
- **θ = 45 mismatch:** float noise at exact ties. Fixed with exact rational trend arithmetic
  (ADR-036); S4 re-verified.
- **Bootstrap grid deviation** under the strict comparator (review): each resample now uses its
  own grid exactly; Hypothesis-tested.
- **Over-permissive EXPECTED rule** (review): tightened; the polyfit evidence is recorded honestly.
- **CSV line endings:** a sed edit broke a string literal and was committed (0a346dd) because a
  `| tail` masked the lint exit code. Repaired in 3487373. Verification commands no longer mask
  exit codes.

### Next Task
S6: development experiments on T (not started).

## 2026-10-18 — S6: Learned-model development on T (tuning only)

### Objective
Tune M1, build the M1 / M2 / M3r / M3 ladder under one shared procedure, run the pre-registered
development experiments, and evaluate G4. E stays sealed.

### Work Completed
- **Pre-registered protocol first** (DEC-2026-10-18-G, committed 877e9bf before any fit).
- **Built:**
  - `models/lgbm.py`;
  - `calibration/methods.py` (isotonic, Platt, interpolated isotonic);
  - `evaluation/folds.py`, `devdata.py`, `s6_run.py`;
  - CLI `hyposense dev s6`.
- **Smoke run flagged a suspected leak.** M1 reached 0.91 vs M0 0.63. Diagnosed with no-learning
  rules: "CGM < 81" gives 0.911, so the endpoint is easy for a level rule. This is not proof of
  no leakage; that comes from the S4 audits and the S6 isolation checks. This
  became the post-hoc diagnostic and P-C9.
- **Two official runs** on clean fd34ecf: identical (`e81268ae…`). G4 PASS (G4.json).

### Results (DEVELOPMENT, treated T)
- **sens@1FA:**

  | M0 | M1 | M2 | M3r | M3 | M3_compact |
  |---|---|---|---|---|---|
  | 0.626 | 0.857 | 0.875 | 0.929 | 0.911 | 0.929 |

- **Comparisons:**
  - C0 +0.231 (0.094–0.437).
  - C1, C2a, C2b and M3−M2 all include 0; M3−M2 +0.036 (−0.042, 0.088).
- **Decisions:**
  - P-B1 → isotonic_interp;
  - P-B6 → adopted for training;
  - P-B8 → compact preferred (owner);
  - P-B9 adopted;
  - num_boost_round 113.

### Problems Found and Fixed
- **Read-only Arrow mask in the worker:** non-inplace ops.
- **The P-B1 decision was not driving the ladder calibrator:** reordered.
- **Evaluation and bootstrap take 11–14 min** (continuous scores). Accepted for an offline
  development run.

### Next Task
S7: policy, replay and API (not started). Owner decisions are pending before freeze.

### S6 independent review (2026-10-18)
- No leakage, contamination or unfairness found. Folds were re-derived exactly.
- Findings F1–F9 are in DEC-2026-10-18-I.
- **Fixed:**
  - F7: pure decision and mask functions, 6 fixture tests;
  - F8: inputs hash, smoke-run note;
  - doc overstatements: F2, F4, F5.
- **Opened:**
  - P-B10 (floored calibrator; P-B1 is fragile);
  - P-B11 (fit-variance repeat);
  - P-B6 status reset to PENDING implementation.
- **Verification run `T-AGG-dev-s6-20261018T153341Z`** on clean fce4c4b: results_sha256 `e81268ae…`, identical.

## 2026-10-18 — S7: Policy, replay and API

### Objective
Turn the validated research pipeline into a deterministic, safe, offline backend. E stays
sealed.

### Work Completed
- **Policy.** `policy.decide`: `decide`, `current` and fixed texts. One implementation shared
  with the offline evaluation (gate verbatim).
- **Artefacts.**
  - Strict loader `models/artifact.py`.
  - DEVELOPMENT M3 artefact on T: `hyposense dev artifact`.
- **Replay.** `replay/runner.py` and `replay/session.py`: recovery, circuit breaker,
  deterministic relative-clock merge, seek, JSONL logs.
- **API.** `api/` (FastAPI + SSE), started with `hyposense serve`.
- **Engineering evidence.** `hyposense dev s7`.
- **Independent review.** No CRITICAL or HIGH findings. Nine findings fixed (9b154bf); F7
  became P-C10.

### Results (engineering, T)
- **Parity:** 33,464 readings, 0 mismatches.
- **Determinism:** identical.
- **Error injection:** 0 later decisions changed.
- **Long run:** 13.94 days, flat memory.
- **Latency:** p99 4.5 ms per reading.
- **Runs:** `T-AGG-s7-engineering-20261018T163321Z` and `T-AGG-s7-engineering-20261018T163810Z` (`6d2517cd…`, identical).

### Problems Found and Fixed
- **Unknown model level leaked the wrong exception.**
- **The EVENT_REJECTED window started at a late event's old timestamp.** It now starts at the
  processing time.
- **Event-loop closure with threaded publishing.**
- **The benchmark's error-injection design tripped the circuit breaker.** The run is recorded
  as superseded.
- **Review F1–F10** (see DEC-2026-10-18-J).

### Next Task
S8: professional frontend (not started). Owner decisions are listed in CURRENT_STATE.

## 2026-10-19 — S8: Professional frontend

### Objective
A clinical, honest, deterministic frontend on the S7 API: Ward board, Patient review, Evidence.
T only.

### Work Completed
- **Design and stack:** short design-reference review (FRONTEND.md §5); design system as tokens;
  Next.js static export served by FastAPI, so it runs as one offline process.
- **Screens:** Ward board (attention summary, dense state-ordered table, freshness,
  notifications); Patient review (state header with a deterministic summary, glucose/model
  timeline with layer toggles, estimated exposure vs recorded doses, why, acknowledgement,
  data quality, forecast → outcome ledger); Evidence (DEVELOPMENT banner, task, limitations,
  ladder with CIs, operating curves, paired Δ, calibration, gates, safeguards, provenance).
- **Replay controller:** play, pause, step, +1 h, speed, seek, reset.
- **Backend additions:** display fields, typed evidence, curve artefact, P-C10 development
  switch, static-export mapping.
- **Tests:** Vitest 28; Python 495 including the browser E2E (replay → API → dashboard →
  acknowledge → acks.jsonl).
- **QA:** visual QA at 1440 / 1280 / 1024 px; accessibility audit; T walkthrough.
- **Independent 4-perspective review:** 10 findings (one HIGH), all fixed.

### Results
- **Accessibility:** 0 WCAG A/AA violations, keyboard skip link.
- **Load:** pages ready in < 0.5 s.
- **Determinism:** evidence curves identical across runs and equal to S6.
- **Walkthrough:** first ALERT at replay offset 3 h 08 min and first LOW NOW at 4 h 08 min, on
  the default ward. Moments were taken as they first occurred, not chosen.

### Problems Found and Fixed
- **Next 16 RSC segment 404s.**
- **Dependency advisories** (moved to patched releases).
- **Contrast failures:** 46 nodes; ink tokens darkened.
- **Interrupted-session hygiene:** stale server, dirty-tree runs regenerated.
- **Review F1–F10** (DEC-2026-10-19-K).

### Next Task
Pre-freeze Class B runs on T (P-B10, P-B11, P-B12). Owner decisions are listed in CURRENT_STATE.

## 2026-10-19 — Pre-freeze Class B (P-B10, P-B11, P-B12)

### Objective
Resolve three development uncertainties on T with rules written before the runs.

### Work Completed
- **Rules first**: rules and grid pre-specified and committed (6b1ad05).
- **Runner**: `hyposense dev prefreeze`, with the floored calibrator challenger and the S6 integrity gate.
- **Runs**: two official runs, identical. The superseded run is recorded.
- **Review**: independent review (no CRITICAL); Class A fixes.

### Results
- **P-B10 INCONCLUSIVE.** The current calibrator stays. It outputs exactly 0/1 in 11/15 configurations; the floored one is never materially worse.
- **P-B11.** M3 ≥ M2 on sens@1FA in 15/15 (12 better, 3 ties). Only M3−M2 partial area is "stable". M3_compact vs M3 is unstable on every metric.
- **P-B12 REMOVE TAG.** No candidate separates reliability; the true OOF firing rate is ~57 %.

### Problems Found and Fixed
- **Wrong P-B10 evaluation set**: corrected toward the written protocol.
- **Rounded hyperparameters**: the S7 artefact builder used rounded values; it now uses full precision.
- **Memory and disk exhaustion on C:**.
- **Review F1–F9.**

### Next Task
Owner decision resolution (CURRENT_STATE "Open Decisions"), then FREEZE.

## 2026-10-19 — Pre-freeze finalization (branch `prefreeze-finalization`)

### Work Completed
- **Owner decisions applied** (DEC-2026-10-19-M):
  - floored calibrator canonical (P-B10 verdict INCONCLUSIVE preserved);
  - LOW_CONFIDENCE removed;
  - full M3 canonical;
  - P-B6 sensitivity only;
  - P-C7 policy-only;
  - P-C9 post-hoc reference;
  - P-C10 option (b).
- **Analysis plan:** ANALYSIS_PLAN §5/§6 FINAL (17 items).
- **Pharmacist packet:** completed and marked PENDING.
- **Freeze candidate:** rebuilt with full-precision hyperparameters (artefact format 2). The
  candidate workflow ran twice, identical (`c0cbe721…`); the S7 bench ran on the candidate.
- **Freeze tooling:** `hyposense freeze` (fails closed).
- **Reviews and visual check:** final five-perspective review, with fixes; focused visual
  check of the Evidence and Ward pages.

### Results
- **T results:** sens@1FA and partial area identical to S6 for every model.
- **Calibration:** log-loss improves; ECE and slope shift (disclosed).
- **Replay:** identical.
- **P-C7:** no T effect (no gap > 120 min).

### Problems Found and Fixed
- **Stale Evidence calibration numbers:** the frontend build had not been rebuilt.
- **Candidate runs launched on a dirty tree:** stopped and relaunched.
- **Review F1–F8.**

### Next Task
COMPLETE PHARMACIST REVIEW (human), then `hyposense freeze`. S9 not started.

## 2026-10-19 — S9 runner + S10 presentation path built and rehearsed; freeze attempted

### Work Completed
- S9 confirmatory runner (`evaluation/confirm*.py`, `hyposense confirm`). Official mode only after
  `verify_freeze_record` and the E unlock; it runs once. A T-only rehearsal mode uses the same
  code.
- R4 tuning on T, frozen (`T-AGG-dev-r4-20261019T055800Z`).
- Held-out replay (`api/held_out.py`, `serve --held-out`). Read-only E access after the single
  official run (`freeze.verify_confirmation`, `data.dataset.unlock_for_presentation`).
- Confirmatory API and Evidence panel. `hyposense report`: RESULTS.md, MODEL_CARD.md and SVG
  figures.
- ANALYSIS_PLAN §5.7 items 31–33 and the R3 disclosure. P-C11 still awaiting.
- README rewrite. Traceability refresh: 44 rows, each test name verified to exist.

### Results
- Full rehearsal `T-AGG-rehearsal-20261019T070224Z` (clean `94a7246`, B 2000, 34 min):
  - equals S6 exactly;
  - held-out parity 0 / 31,416.
- Candidate pair on `57292dc`: identical (`c0cbe721…`).
- `hyposense freeze` on `7babc4f`: **ERROR — FREEZE ABORTED** on `pharmacist_review`,
  `class_c_resolved` (P-C11) and `analysis_plan_final` (P-C11). All 11 technical checks pass,
  including 546 Python tests and the frontend suite.

### Problems Found and Fixed
- Smoke rehearsal: a wrong config path for the SA5 tail parameter (fixed before the full run).
- Import-boundary guard:
  - the live API imported evaluation modules. `confirm_view` moved to `reporting/`, and
    held-out streams are now built with `state.stream`.
  - the partition was read outside `data/`. `data.dataset.partition_labels` was added.
- R3 low score diagnosed as a learner property, not a bug. It is disclosed, and the learner is
  unchanged.

### Next Task
Human gates: pharmacist review (or an explicit owner waiver) and P-C11 approval. Then freeze →
merge → S9 once → S10 (NEXT_STEPS).

## 2026-10-19 — Product-first: frontend inspection, new-data intake, Ask panel

### Work Completed
- Checkpoint A: the existing app was launched and inspected in Edge (0 console errors).
- The gap analysis found that no new patient or new data could be accepted.
- New-data intake:
  - `intake/`;
  - loader split into read + `parse_recording_frame`;
  - API endpoints;
  - Add patient page, session banner, Add observation, Remove session, NEW DATA ward tag;
  - "Ask about this patient" (fixed intents).
- P-C11 approval matrix: docs/protocol/P-C11_APPROVAL_MATRIX.md.

### Results
- Parity: a real T recording uploaded as CSV gives events, decisions and probabilities identical
  to the historical adapter. The incremental twin equals the full-file twin.
- Replay is unchanged (same ward states as before).
- Candidate pair on `28ac72f`: identical, `c0cbe721` (no number changed).
- `hyposense freeze`: aborted on the 3 human gates only. 570 Python and 37 Vitest tests pass.

### Problems Found and Fixed
- Questions were asked for empty pump and glucose columns; they are now asked only for fields
  with data.
- pandas silently renamed duplicate headers (`x` → `x.1`); these are now detected and refused.
- An out-of-order observation gave a misleading message; there is now an explicit append-only
  check.
- The live-path import guard now covers `intake`.
- "What is missing" showed raw codes; it now uses plain wording.
- The M1 interval "discrepancy" at Checkpoint A was a comparison against the discarded B=20
  smoke run. With B=2000, the rehearsal equals S6 exactly. No defect.

### Next Task
Human gates: pharmacist review (or explicit owner waiver) and P-C11 decision (see the matrix).

## 2026-10-19 — Judge-readiness UX redesign (DEC-2026-10-19-Q)

### Work Completed
- UX audit from real screenshots.
- Overview page; guided demo on the real replay.
- Ward, Patient, Add patient, Ask and Evidence made understandable, with technical detail on
  demand.
- docs/UX_REVIEW.md, including the expert-role heuristic review and the 5-minute demo script.

### Results
- axe: 0 violations on 6 pages.
- Tests: Vitest 42, Python 572, E2E 3.
- Edge walkthrough: 0 console errors.
- In the default replay, the first alert (2012, 14:48, 15 %) was not followed by a CGM low. The
  demo shows this false alert plainly.

### Problems Found and Fixed
- Demo step 7 referred to "the alert" while a later alert existed; it now names the alert time
  and reads its real outcome.
- The demo dock covered the history column; the page now gains bottom space and the dock can be
  minimised.
- Leftover jargon removed: "mapped", "τ", "Grouped TreeSHAP" (now behind a disclosure),
  "ledger", "Timing unknown".

### Next Task
Human gates: pharmacist review, and the P-C11 decision (docs/protocol/P-C11_APPROVAL_MATRIX.md).

## 2026-10-19/20 — P-C11 implementation audit, README, submission preview, owner design

### Work Completed
- Independent audit of §5.7 items 1–33 against the code: 6 defects found and fixed before
  freeze (DEC-2026-10-19-R). The rehearsal was re-run: primary result identical, fixes verified.
- README rewritten. Submission preview added in docs/submission: deck (PDF), demo guide, model
  card, honesty card, test report.
- Owner's new frontend design implemented on real data only (DEC-2026-10-20-S). Display-only
  backend fields were added for it.
- Performance measured (TEST_REPORT): building a twin from an upload takes ~6.5 ms per reading
  in the canonical engine. Not optimised; the UI shows progress.

### Problems Found and Fixed
- E2E tests failed for two harness reasons, not product defects: the file was set before the
  page had loaded its scripts (now waits for "Live"), and one locator was ambiguous.
- A 4.45:1 contrast on white-on-violet small text was fixed (axe now 0).
- A ward screenshot with replayed T patients was moved out of docs/ into the git-ignored
  artifacts/.

### Next Task
- Human gates: pharmacist review and the P-C11 decision.
- GitHub: no remote is configured; a repository URL is needed to push.

## 2026-10-20 — GitHub publication and README rewrite

### Work Completed
- Published to https://github.com/yug-birla/HypoSense-Twin at the owner's instruction. The
  branch was renamed `prefreeze-finalization` → `main`, then a normal push (no force).
- Root README restructured for judges, engineers, researchers and clinicians. Changes:
  - a hero section and a product tour;
  - a verified quick start;
  - the four worlds of the twin, prediction states, model ladder and evaluation design;
  - development results traced to `T-AGG-dev-s6-20261018T144427Z`;
  - limitations, citation and a documentation map.
- `scripts/ui_readme_showcase.py` captures the README screenshots from the running app. It
  uses SYNTHETIC new-data sessions only and no replay, so no T trace appears. Output:
  docs/screenshots/readme/.
- Quick start verified from a fresh clone of the GitHub repository:
  `uv sync` → `npm ci` / `npm run build` (0 vulnerabilities) → data fetch / extract / manifest
  (111 files verified) → `serve`. Health check: artifact verified; UI returns HTTP 200.

### Problems Found
- Without the dataset, `hyposense serve` stops with a `FileNotFoundError` traceback instead of
  a plain message. Documented in the README; not fixed, because `cli.py` is in the frozen code
  paths and the candidate pair would have to be rebuilt.
- DEMO_GUIDE referred to a README section number that no longer exists, and to the old
  "Overview" page name. Both fixed.

### Next Task
Human gates: the pharmacist review and the P-C11 decision.
