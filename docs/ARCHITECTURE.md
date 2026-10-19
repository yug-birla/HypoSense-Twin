# HypoSense Twin v2 — Architecture

Status: **Data (S1), labels (S2), medication (S3), state engine and features (S4) IMPLEMENTED; models, policy, API, UI DESIGN** (updated
2026-10-18).
Baseline: Blueprint v2.0 §9–§18 and §24–§25 ([digest](BLUEPRINT_DIGEST.md)). Engineering
refinements are recorded as ADRs in [DECISION_LOG.md](DECISION_LOG.md). Open scientific
clarifications are in [PROPOSALS.md](PROPOSALS.md). Where this document is more specific than
the blueprint, the reason is given and cross-referenced.

---

## 1. System context

```
ShanghaiT2DM (official figshare copy, read-only, SHA-256 pinned)
        │
        ▼
┌──────────────────────────── LIVE PATH (same code in training and replay) ───────────────────────────┐
│ Data Adapter & Validator ──► Patient State Engine ("the twin") ──► Feature Builder ──► Risk Model    │
│   typed events + flags        CGMState                              causal snapshot     M0 | LightGBM │
│                               MedicationExposureState               z(t), level-gated   + calibrator  │
│                               DataQualityState                                              │        │
│                               ForecastState / OutcomeLedger                                 ▼        │
│                                         └──── sufficiency, CGM(t), timing flags ──► Decision Policy   │
│                                                                                   (frozen, no model   │
│                                                                                    imports)          │
└───────────────────────────────────────────────────────────────────────────────────────┬─────────────┘
                                                                                        ▼
                         Replay Service ──► FastAPI (REST + SSE) ──► Next.js UI: Ward Board · Patient Review · Evidence
                                                                         │
                                                                         ▼
                                                    Clinician acknowledgement (reason code) → JSONL log
┌──────────────────────────── OFFLINE ONLY (may see the future; never imported by the live path) ─────┐
│ Label Builder → Partition (T/E, guard) → Evaluation Harness (nested CV, calibration, τ, metrics,     │
│ cluster bootstrap) → Frozen artefacts (model, calibrator, policy.json, results.json, model card)     │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

The model and policy boundary is mandatory (CLAUDE.md §19):
**model: features → p(t)**; **policy: p(t) + state + history + quality → user-facing state**.
A static test enforces it ([tests/leakage/test_import_boundaries.py](../tests/leakage/test_import_boundaries.py)).

## 2. Repository layout (ADR-002)

```
configs/            default.yaml · dataset.yaml (pinned figshare source) · pharma.yaml ·
                    partition.csv + partition.provenance.json (immutable, ADR-016) ·
                    reference/blueprint_audit.yaml · drug_dictionary.csv (S3)
data/               raw/downloads/ (archives + provenance sidecars) · raw/ShanghaiT2DM/ (canonical
                    v5 extraction) · raw/reconciliation/v1|v2/ (never analysed) — all git-ignored ·
                    MANIFEST.json + MANIFEST.sha256 (committed) · processed/ (git-ignored)
src/hyposense/
  common/           hashing, config, provenance, timeconv (no scientific logic)
  data/             source (fetch/extract), manifest, columns, records, loader, summary,
                    quality flags, partition, dataset (scoped access)   → load_recording()
  audit/            structural audit, version + blueprint reconciliation, gates G0/G1 (OFFLINE)
  labels/           episodes, eligibility (OFFLINE)                  → build_episodes(), eligible_times()
  medication/       dictionary, parse_dose(), kernels, exposure_at()
  state/            PatientState + sub-states, update()
  features/         snapshot() per level M1/M2/M3r/M3
  models/           M0 trend rule, LightGBM wrapper, artefact I/O
  calibration/      isotonic (default) + challengers, calibration metrics
  policy/           decide(), cooldown, decision logging
  evaluation/       folds, nested fitting, metrics, operating curves, bootstrap, reports (OFFLINE)
  replay/           deterministic event-ordered replay, decision-log hashing
  api/              FastAPI app, routes, SSE stream, static UI mount
  cli.py            `hyposense audit | freeze | confirm | demo` (ADR-006)
frontend/           Next.js app (ADR-007)
tests/              unit · integration · leakage · regression · reproducibility · e2e
experiments/        runs/<run_id>/ manifests and results (ADR-010)
artifacts/          <model_version>/ frozen artefacts
scripts/            one-off tooling (blueprint extraction, data fetch)
docs/               project control documents + protocol/ANALYSIS_PLAN.md (pre-freeze)
```

## 3. Time, ordering and units

- Timestamps are parsed as local **+08:00 (ASSUMPTION)** and stored internally as **int64 epoch
  seconds**. Time-of-day features use the local clock.
- Windows are half-open: history **(t − Δ, t]**, label **(t, t + 3600]**.
- **Event ordering within one timestamp (deterministic):** `dose` → `meal` → `cgm` → `cbg`
  (display only). Ties then break by source row. A dose charted at row t counts as available at
  t (its timestamp ≤ t). Its kernel contribution at τ = 0 is 0 by construction, so only the
  "minutes since dose" and timing features change. Dose-time uncertainty is handled by
  robustness test R1, not by shifting data.
- Units: glucose mg/dL (float32), insulin IU, oral doses mg, basal rates IU/h, and dimensionless
  exposure fractions. Missing values are `NaN`/`None`, never 0. Every optional feature carries
  an `_missing` indicator.
- Keys: `patient_key = "shanghai_t2dm:<prefix>"`, `recording_key = "<prefix>_<period>_<date>"`.
  All grouping (folds, bootstrap, partition) uses `patient_key`, never `recording_key`
  (109 recordings ≠ 100 patients).

## 4. Components

### 4.1 Data Adapter & Validator (`data/`)
- `load_recording(path) → RecordingBundle`: maps the five column variants to canonical names
  (an unmapped column raises `UnknownColumnError`), converts units, sorts rows, removes exact
  duplicates and quarantines non-monotone timestamps.
- Per-reading quality flags: gap >20 min, ≤40 mg/dL (floor), |ΔG/Δt| >4 mg/dL/min, warm-up
  (first 2 h). **Flags never delete data.**
- `MANIFEST.sha256` verification happens before any read (`ChecksumError`).
- **Partition guard** (ADR-011): every record access goes through
  `DataAccess(scope=TUNING_ONLY | AGGREGATE_AUDIT | ALL_AFTER_FREEZE)`.
  `ALL_AFTER_FREEZE` requires a freeze manifest whose hashes match the current code and config.
  `AGGREGATE_AUDIT` returns only aggregate reports for E (scope pending approval, P-C5).

### 4.1a As implemented in S1 (2026-10-18)
- **Source** (`data/source.py`, `configs/dataset.yaml`): figshare article 21600933. v5 is
  canonical; v1/v2 serve reconciliation only (ADR-017). The download is checked against
  figshare's MD5 and the pinned SHA-256, and a provenance sidecar records URL, DOI, retrieval
  time, checksums and licence. Extraction is allow-listed (no `__MACOSX`, `.DS_Store` or T1DM)
  and handles the `diabetes datasets/` wrapper of v2–v4. It refuses to overwrite existing raw
  data.
- **Manifest** (`data/manifest.py`): per-file SHA-256 and size. `files_sha256` is the identity
  hash, independent of retrieval time. `load_dataset` verifies it on every call
  (`ChecksumError`).
- **Loader** (`data/loader.py`, `data/columns.py`, `data/records.py`):
  - strict file-name identity `<pid>_<period>_<YYYYMMDD>.xls[x]`;
  - an explicit table of the 5 observed header variants;
  - raw-cell parsing, per-row flags (`ts_valid`, `ts_non_monotone`, `dup_ts`, `exact_dup`) and
    typed `LoadIssue`s;
  - `raw_<col>` preservation for non-clean numeric cells;
  - +08:00 → int64 epoch seconds, with sub-second values rounded.

  `cgm_series()` returns strictly increasing readings plus an exclusion account (ADR-019).
- **Summary** (`data/summary.py`): one row per **recording** (33 columns, canonical names). The
  "Hypoglycemia (yes/no)" field is tagged `FORBIDDEN_FEATURE_COLUMNS`.
- **Quality flags** (`data/quality.py`): gap > 20 min, ≤ 40 floor, |rate| > 4 mg/dL/min,
  warm-up < 120 min. They annotate only.
- **Scoped access** (`data/dataset.py`, ADR-018): `TUNING_ONLY` | `AGGREGATE_AUDIT` |
  `ALL_AFTER_FREEZE`.
- **Audit** (`audit/`): `measure()` is deterministic. Its results hash is identical across runs.
  The per-recording table is restricted to `PER_RECORDING_FIELDS`. Version reconciliation and
  blueprint reconciliation are mechanical (MATCH / EXPECTED DIFFERENCE / UNEXPLAINED). The pure
  `evaluate_g0`/`evaluate_g1` write `artifacts/gates/G*.json`.
- **CLI**: `hyposense data fetch|extract|manifest|validate`, `partition verify`, `audit run`,
  `gates show`.

### 4.2 Label Builder (`labels/`, offline)
**IMPLEMENTED (S2).** Modules:
- `config` (`LabelConfig`, all constants in integer seconds);
- `episodes` (explicit state machine; `Episode` records onset, end and last-in-episode times,
  end reason, nadir and n);
- `eligibility` (reason code per reading; y ∈ {1, 0, −1}; seconds to next onset; warnable
  onsets; P-C7 warm-up hook);
- `build` (`label_recording` → `RecordingLabels`);
- `validity` (CBG pairing and confirmation; never alters episodes);
- `annotations` (nocturnal, first-24h, SA4 compression, sensor-floor run).

The operational protocol is ANALYSIS_PLAN §0. The event audit (`audit/events.py`,
`audit/event_run.py`) produces G2/G3b.

`build_episodes(obs, thr, min_run=2, max_step=1200, max_gap=1800)` and
`eligible_times(obs, episodes)` implement Table 5.1 exactly. Hand-labelled fixtures are written
**before** the code (test-first, CLAUDE.md §23). Labels come from CGM only.

### 4.3 Medication normalisation and exposure (`medication/`)
- `parse_dose(text, route, ts) → list[DoseEvent]` never raises. Unknown products get class
  `unknown`, are excluded from exposure and are counted. The parser runs a plausible-dose range
  check per drug (App. B data-quality findings).
- `configs/drug_dictionary.csv` (versioned) maps product → class, formulation rule, D_max.
- `exposure_at(doses, t, kernels) → ExposureState` implements Eq. 1–6 and **asserts that every
  dose ts ≤ t**. Projections to t+30 and t+60 use only past doses. The CSII basal-continuation
  question is open (P-B3).
- Kernels are pure, vectorised numpy functions with closed-form parameters. Parameter
  validation enforces t_peak < t_dur/2 (Eq. 3) and t_max solvability (Bateman).

### 4.3a As implemented in S3 (2026-10-18)
- `medication/events.py`: typed `MedicationEvent` and `EntryParse`, with parse statuses, event
  kinds and flags.
- `medication/dictionary.py`: the versioned CSV and normalisation.
- `medication/parse.py`: column grammars, content-aware.
- `medication/recording.py`: recording parse, production treated status, prescribed classes.
- `medication/kernels.py`: exponential, flat and Bateman kernels.
- `medication/exposure.py`: `ExposureEngine`. It is causal and vectorised, with exact fsum
  summation, CSII reconstruction with the 6-h cap, projections and `QualityState`.
- `medication/timing.py`: M3r raw timing.
- `data/quality.sensor_fault_suspected`: P-C8 causal flag.
- Audit: `audit/medication.py`, `audit/med_run.py` (`hyposense audit medication`).
- Contracts: docs/FEATURE_DICTIONARY.md. Parameters: configs/pharma.yaml and
  docs/medication/PARAMETER_SOURCES.md.

### 4.4 Patient State Engine (`state/`) — "the twin"
```
PatientState(patient_key, ts)
├── CGMState               24-h ring buffer; causal episode tracker (onset confirmed at the
│                          2nd reading; end confirmed at the 2nd recovery reading; refractory clock)
├── MedicationExposureState append-only dose log; ExposureState(t); CSII current rate; last i.v.;
│                          timing-unknown per class
├── DataQualityState       sufficiency (gap, 7/8 rule, warm-up, flags) + reasons; range flags
├── ForecastState          last Prediction, last PolicyDecision, last notification ts
└── OutcomeLedger          forecasts awaiting reconciliation at t+60 (display/audit only —
                           NEVER read by the feature builder)
```
- `update(event) → PatientState` is deterministic and timestamp-ordered. It returns a new
  immutable snapshot (a frozen dataclass), so a full state sequence can be inspected and
  replayed. On an internal failure the state carries a SYSTEM_ERROR tag; it never keeps a stale
  value as if it were current.
- **The causal episode tracker uses the same rule as the Label Builder, applied with
  confirmation lag.** The live policy's LOW NOW and refractory logic and the "prior L1 onsets"
  feature depend only on episodes confirmed by t. This keeps the twin from importing
  `labels/`.

### 4.5 Feature Builder (`features/`) — single causal implementation (ADR-004)
- `snapshot(view: CausalView, static, level) → FeatureSnapshot`. `CausalView` exposes only
  arrays truncated at t (built by `searchsorted`, so slicing is O(log n)).
- **Offline training snapshots come from the same functions** called over every reading,
  through the same `CausalView`. There is no separate vectorised "batch" implementation, so
  training and serving features cannot drift apart. Expected cost: about 112k snapshots × tens
  of µs, i.e. seconds to minutes (to be measured, CLAUDE.md §28).
- Feature groups are gated by level (App. D). Feature names and order are written to
  `feature_spec.json` and checked when an artefact loads (`FeatureSpecMismatch`).
- The "Hypoglycemia (yes/no)" summary field and patient identifiers are excluded by an
  allow-list, not a deny-list.

### 4.5a As implemented in S4 (2026-10-18)
- **Adapter** `state/stream.py`: `Recording` → `RecordingStream`, typed events in canonical order
  (ts, then dose → meal → CGM → CBG, then source row and column). Inputs:
  - CGM from `cgm_series`;
  - meals (same-timestamp rows merged; "not recorded" marker → content unknown);
  - CBG;
  - S3 medication events;
  - the recording's static context (`state/context.py`, allow-list).

  A patient's recordings are ordered by first timestamp, never by number.
- **State** `state/patient.py`: frozen `PatientState` with:
  - `context`;
  - `cgm` (`CGMState`: persistent append-only series + causal `EpisodeTracker` + last low);
  - `quality` (`DataQualityState`, from the authoritative `data.quality` functions applied to
    2- and 8-reading tails, plus the warm-up anchor with the P-C7 hook);
  - `medication` (`MedicationExposureState`: append-only S3 events; `ExposureEngine` and
    `RawTiming` built once per log length);
  - `meals`, `cbg`;
  - `forecast`, `ledger` (display/audit only).

  `update()`:
  - is strict, deterministic and order-checked (`OutOfOrderEventError`,
    `RecordingBoundaryError`, `MalformedEventError`);
  - has a live-path wrapper, `try_update()`, which returns the previous state tagged
    SYSTEM_ERROR; snapshots of a tagged state are refused.

  Histories are persistent (`state/history.py`): O(1) amortised appends, immutable prefixes,
  copy on branch.
- **One state per recording.** No state crosses a recording boundary (ANALYSIS_PLAN §0 item 10).
  Static context is per recording row.
- **Features**: `features/spec.py` holds the registry (one definition per feature, groups, levels,
  missingness); `artifacts/features/feature_spec.json` is its committed export.
  - Group functions: `features/cgm.py` (G1–G4), `features/context.py` (G5–G6) and
    `features/medication.py` (G7, G78, G8), the last being assembly only from the S3 engines.
  - `FeatureBuilder.union(FeatureInputs)` computes every feature at a CGM reading.
    `snapshot(state, level)` is a fixed selection of that union.
  - `FeatureInputs` exposes only context, CGM, meals and medication, never forecast or ledger.
- **Offline = replay**: `features/build.py` replays each recording through `update()` and calls the
  same `union()` after each CGM reading. There is no batch path (ADR-004, now implemented).
  T-only scope guard (`SealedPartitionError`). The table goes to `data/processed/features/`
  (git-ignored) with provenance: commit, data, config, spec, dictionary and pharma hashes.
- **Audit**: `audit/features.py`, run as `hyposense audit features`: truncation equality at every
  eligible T time (raw record truncated), replay parity, perturbation, tracker agreement,
  distributions, redundancy, performance. It is parallel (15 workers); `common/runtime.py` opts
  the processes out of Windows power throttling (ADR-035).

### 4.6 Risk models (`models/`) and calibration (`calibration/`)
- M0: least-squares 30-min slope projected to t+60. Its "score" is the projected glucose, with
  ALERT if projection < θ.
- M1–M3: LightGBM, one shared hyperparameter set tuned on M1 (T, inner grouped CV, ≤30 Optuna
  trials). The procedure for the number of boosting rounds is open (P-B2).
- Calibration defaults to isotonic, fitted on inner out-of-fold predictions. Challengers are
  benchmarked only on T (P-B1).
- **Artefacts (ADR-009)**: LightGBM native text model, calibrator as JSON
  (thresholds/values), `feature_spec.json`, `policy.json`, `manifest.json` with SHA-256 of each
  file plus data/config/code hashes. **No pickle.** The API refuses to start on a hash mismatch.

### 4.7 Decision Policy (`policy/`)
- `decide(p, state, policy_cfg) → PolicyDecision` is a pure function. It never raises: an
  exception maps to SYSTEM ERROR. Table 14.1 applies, with the priority question in P-C1.
- Cooldown is 60 min. The ALERT state persists during cooldown. Tags (timing unknown,
  recent input rejected) never downgrade an ALERT. LOW CONFIDENCE was removed (P-B12,
  DEC-2026-10-19-M).
- Logging appends to `logs/decisions.jsonl` (timestamp, patient key, model version, config
  hash, p, τA, τW, state, flags, input digest). Acknowledgements append to `logs/acks.jsonl`.
  Raw diet free text is never logged.

### 4.8 Evaluation Harness (`evaluation/`, offline)
- Folds come from `configs/partition.csv`. Five grouped folds over E. Training data =
  T ∪ (E∖k). Inner folds produce OOF predictions for calibration and τ.
- **The policy is evaluated by causal replay over every reading**, using the same `decide()`
  as the live system. Hits and false alerts are counted from that replay (exact counting
  semantics in P-C3; operating-curve and τ rules in P-C2).
- Metrics follow Table 20.2 and App. E. The paired patient-cluster bootstrap uses B = 2000 and
  seed 2027.
- Every run writes `experiments/runs/<run_id>/manifest.json` (ADR-010).

### 4.9 Explanation
Grouped TreeSHAP over the LightGBM raw margin, summed into the nine factor groups of §16.1,
with the top 3 groups and their direction. The UI states that the attribution is on the
pre-calibration score and that it shows "associations, not causes". The exposure timeline comes
from the state, never from the model.

### 4.10 Replay Service and API (`replay/`, `api/`)
- Replay merges all events of the selected patients into one stream, ordered by
  (ts, event-type order, patient_key, source row). That stream drives `state.update →
  features → model → policy`. Wall-clock speed (×120 by default) affects pacing only, never
  ordering. **Seek** recomputes from the recording start, so it stays deterministic.
- Before freeze, replay may use T patients only, with live M0/M1–M3 predictions labelled
  DEVELOPMENT. After S9, it uses E patients with their **out-of-fold** predictions (§15).
- API (FastAPI + Pydantic; ADR-008). **Contract as implemented in S7** (`api/app.py`,
  `api/schemas.py`; DEC-2026-10-18-J). Every view carries `model_status`.

| Method | Path | Returns |
|---|---|---|
| GET | `/api/health` | liveness; the service only exists with a verified artefact |
| GET | `/api/meta` | model version / status, manifest hash, compatibility hashes, provenance, thresholds, policy rules, source label, caveat |
| GET | `/api/evidence` | S6 development ladder + comparisons + provenance; status DEVELOPMENT; confirmatory PENDING |
| GET | `/api/replay/cases` | T recordings (key, patient, days, readings) |
| GET | `/api/replay/status` | session, recordings, playing, speed, offset, duration, finished |
| POST | `/api/replay/select` | 1–12 recording keys; new session and log segment |
| POST | `/api/replay/play` · `pause` · `reset` | clock control |
| POST | `/api/replay/speed` | 1–3600× |
| POST | `/api/replay/step` | 1–2000 events |
| POST | `/api/replay/advance` | 0–6 h of data time |
| POST | `/api/replay/seek` | offset; deterministic rebuild from the start |
| GET | `/api/ward` | `Ward`: beds sorted by state (SYSTEM_ERROR, LOW_NOW, ALERT, WATCH, INSUFFICIENT, NO_ALERT), then p, then key; badges; unacknowledged notifications |
| GET | `/api/patients/{recording_key}` | `PatientView`: current decision (+texts), last forecast with `is_current`, 24 h CGM / CBG / meals / doses, exposure (+ts), medication and data quality, factor groups (current forecast only), notifications, ledger counts, rejected events, halted |
| POST | `/api/acknowledgements` | `{decision_id, reason ∈ 4 codes, user_role}` → 201; 404 unknown; 409 not a notification / already acknowledged |
| GET | `/api/stream` | SSE v1: `session`, `tick`, `decision`, `notification`, `error`, `bed_state`, `acknowledgement` |

- Frontend TypeScript types are **generated from the OpenAPI schema** (openapi-typescript), so
  contracts are never duplicated by hand.

### 4.11 Frontend (`frontend/`, ADR-007) — implemented in S8; details in [FRONTEND.md](FRONTEND.md)
- Stack: Next.js (App Router, static export) + React + TypeScript + Tailwind CSS +
  shadcn/ui (Radix primitives) + Apache ECharts + TanStack Query. FastAPI serves the static
  build, so the demo is a single process and fully offline.
- Screens:
  - **Ward Board**: patients sorted by server rank (state, then risk). State badges combine
    text, icon and colour. Shows last reading time, data-quality and timing badges, and the
    provenance badge.
  - **Patient Review**: state and probability (or risk band), 6-h and 24-h CGM with dose and
    meal markers, an exposure panel with projections and the "assumes no further doses"
    caption, data quality, the top factor groups with their caveat, an event ledger and the
    acknowledgement panel.
  - **Evidence**: the headline operating curves with Δ and its CI, ladder chart, calibration,
    per-patient forest plot, lead times, failure cases, the data honesty card and the model
    card. Every number is read from `results.json` and carries a status label.
- Global elements: replay controls (play/pause/speed/seek/case selector), a model and config
  provenance strip, and the honesty card on first load. Explicit **loading**, **error (SYSTEM
  ERROR banner)**, **INSUFFICIENT DATA** and **connection-lost / stale** states. If the stream
  stalls, the UI greys out values and says so; it never shows an old state as current.
- No scientific logic lives in the frontend. Sorting, states, thresholds and metrics all come
  from the API.
- Synthetic examples, if any are ever needed (e.g. Storybook), carry a visible **SYNTHETIC**
  watermark and never ship in the demo build.

### 4.12 Deployment
`hyposense demo` starts uvicorn, which serves the API and the static UI on localhost with no
network calls. A Docker image is the RECOMMENDED backup. A recorded replay video and static
Evidence exports serve as the G7 fallback (ADR-013).

## 5. Leakage controls (Blueprint Fig. 10.1, CLAUDE.md §11)

| Risk | Control | Test |
|---|---|---|
| Future CGM in features | `CausalView` truncation; single feature path | `test_truncation_equality` (all levels, random t, Hypothesis) |
| Future doses in exposure | assertion in `exposure_at` | `test_exposure_causal` |
| Label code on live path | import boundary | `test_import_boundaries` (exists) |
| Ledger/outcomes feeding features | ledger not reachable from `features/` | `test_features_ignore_ledger` |
| Episode history feature using hindsight | causal tracker with confirmation lag | truncation equality at episode boundaries |
| Patient overlap across folds and T/E | grouping by `patient_key` | `test_group_by_patient` |
| Design iteration on E | partition guard + freeze manifest | `test_freeze_guard` |
| Calibration/τ on test fold | inner OOF only | `test_nested_fitting_isolation` |
| Labs post-dating CGM | patient-level context only; SA8 | SA8 |
| Normalisation/percentile references from test data | fitted inside training folds only | integration test on fold artefacts |

## 6. Provenance and reproducibility

- Seeds: partition/folds 2026, LightGBM 2026 (deterministic, one thread for confirmatory runs),
  bootstrap 2027, SA7 2028–2032.
- Every result carries: run id, UTC timestamp, git commit (a **dirty tree is refused for
  confirmatory runs**), dataset manifest hash, config hash, seeds, `uv.lock` hash and package
  versions, model/feature/dictionary/kernel versions, metrics and artefact hashes.
- Freeze manifest (`artifacts/freeze/FREEZE.json`): hashes of code tree, configs, partition,
  pharma.yaml, drug dictionary, `docs/protocol/ANALYSIS_PLAN.md` and `uv.lock`.

## 7. Deviations from the blueprint (summary)

| Blueprint | This architecture | Class | Ref |
|---|---|---|---|
| Flat `hyposense/` package, `config/`, `artefacts/` | `src/hyposense/<subpackages>`, `configs/`, `artifacts/` | A | ADR-002 |
| `make` targets | `hyposense` CLI (no `make` on the Windows dev machine) | A | ADR-006 |
| Separate audit.py/audit2.py | Audit built on production adapter, labels and parser (no duplicated scientific logic) | A | ADR-005 |
| (unspecified) batch vs live features | One causal implementation for both | A | ADR-004 |
| React (Vite) + Recharts; Streamlit fallback | Next.js + TS + Tailwind + shadcn/ui + ECharts, static export served by FastAPI; fallback = recorded video | A | ADR-007, ADR-013 |
| Polling once per second | SSE stream + REST | A | ADR-008 |
| (unspecified) artefact format | No pickle; LightGBM text + JSON | A | ADR-009 |
| Analysis plan = sections of the .docx | Also a standalone `docs/protocol/ANALYSIS_PLAN.md` hashed at freeze | A | ADR-012 |
| Policy priority 2 before 3 | LOW NOW for any current reading <70 | **C — APPROVED** | P-C1, ANALYSIS_PLAN §1 |
| Operating-curve threshold grid, τ rule | Exact first-crossing rule | **C — APPROVED** | P-C2, ANALYSIS_PLAN §3 |
| FA counting unspecified at recording ends | OUTCOME-UNKNOWN class, reported separately | **C — APPROVED** | P-C3, ANALYSIS_PLAN §2 |
| Mirror copy of the data | figshare v5 canonical, v1/v2 reconciliation | A | ADR-017 |
| `config/partition.csv` from the audit | Same file, verified and hash-locked | C (delegated) | ADR-016 |
