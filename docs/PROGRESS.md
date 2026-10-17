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
