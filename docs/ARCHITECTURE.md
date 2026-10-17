# HypoSense Twin v2 — Architecture

Status: **DESIGN — reviewed, not yet implemented** (2026-10-18).
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
configs/            default.yaml · pharma.yaml · drug_dictionary.csv (S3) · partition.csv (S2)
data/               raw/ (git-ignored) · processed/ (git-ignored) · MANIFEST.sha256 (committed)
src/hyposense/
  common/           time, hashing, provenance, config loading (no scientific logic)
  data/             adapter, validators, partition guard            → load_recording()
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

### 4.2 Label Builder (`labels/`, offline)
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
- Cooldown is 60 min. The ALERT state persists during cooldown. Tags (LOW CONFIDENCE, timing
  unknown) never downgrade an ALERT.
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
- API (FastAPI + Pydantic; ADR-008). This is a draft contract to be fixed in S7:

| Method | Path | Returns |
|---|---|---|
| GET | `/api/health` | liveness + artefact hash check |
| GET | `/api/meta` | model version, config hash, protocol/freeze status, data provenance, replay source label |
| GET | `/api/ward` | `WardBoard` — patients with state, p, last reading time, badges, server-computed sort rank |
| GET | `/api/patients/{key}` | `PatientView` — state, CGM trace, doses, exposure curves (+projections), quality, factor groups, ledger |
| POST | `/api/acknowledgements` | stores `Acknowledgement` (reason code ∈ 4) |
| GET | `/api/evidence` | `results.json` content + provenance + status (DEVELOPMENT / CONFIRMATORY / PENDING) |
| GET/POST | `/api/replay/*` | status · play · pause · speed · seek · select case |
| GET | `/api/stream` | server-sent events: `tick`, `decision`, `notification`, `error` |

- Frontend TypeScript types are **generated from the OpenAPI schema** (openapi-typescript), so
  contracts are never duplicated by hand.

### 4.11 Frontend (`frontend/`, ADR-007)
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
| Policy priority 2 before 3 | LOW NOW for any current reading <70 | **C — pending approval** | P-C1 |
| Operating-curve threshold grid, τ rule | Explicit first-crossing rule | **C — pending approval** | P-C2 |
