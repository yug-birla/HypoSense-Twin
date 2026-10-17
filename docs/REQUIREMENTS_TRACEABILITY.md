# Requirements Traceability Matrix

Purpose: no blueprint requirement may disappear during implementation.

Columns:
- **Kind**: REQ = required · REC = recommended · OPT = optional/gated · C = Class C protocol
  constant.
- **Status**: PENDING (not implemented) · PARTIAL · PASS (implemented and verified by the
  named test) · FAIL · BLOCKED · N/A.

Update this file whenever a requirement's status changes. Module paths are relative to
`src/hyposense/`.

## Data and audit

| ID | Requirement | Kind | Source | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| D-01 | Official figshare copy, SHA-256 manifest; loader refuses on mismatch | REQ | §10.1, G0 | `data/`, `data/MANIFEST.sha256` | `test_checksum_refusal` | PENDING |
| D-02 | Reconcile CGM count to 112,475 or explain | REQ | G0, N8 | `hyposense audit --structural` | audit report | PENDING |
| D-03 | Map 5 column variants; unmapped column = error | REQ | §10.1 | `data/adapter.py` | `test_column_variants` | PENDING |
| D-04 | Units: mg/dL, IU, mg (g → mg), IU/h | REQ | §10.1, §25.1 | `data/adapter.py`, `medication/` | unit tests | PENDING |
| D-05 | tz-aware +08:00, epoch seconds, sort, dedupe, quarantine non-monotone | REQ | §10.1, §25.1 | `data/adapter.py`, `common/time.py` | unit tests | PENDING |
| D-06 | Quality flags (gap >20, ≤40, rate >4, warm-up); flags never delete | REQ | §10.1 | `data/validators.py` | unit tests | PENDING |
| D-07 | Patient = file prefix; group by patient_key | REQ | N3, §25.1 | `data/`, `evaluation/folds.py` | `test_group_by_patient` | PENDING |
| D-08 | Never use "Hypoglycemia (yes/no)" field | REQ | N2, App. D | `features/` allow-list | `test_summary_hypo_field_never_used` | PENDING |
| D-09 | G1: ≥99% readings parse, ≥99% intervals ≤20 min | REQ | Table 21.1 | audit | audit report | PENDING |
| D-10 | Data-quality report (App. G sections) | REQ | App. G | `hyposense audit --report` | audit determinism | PENDING |
| D-11 | Logs never contain raw diet free text | REQ | Table 18.1 | `policy/`, `api/` | log content test | PENDING |

## Labels and partition

| ID | Requirement | Kind | Source | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| L-01 | L1 episode rule (2 consecutive <70, spacing ≤20; end 2 ≥70 / gap >30 / record end) | C | Table 5.1 | `labels/episodes.py` | `test_labels_fixtures` (≥20) | PENDING |
| L-02 | L2 (54 mg/dL) secondary label | C | Table 5.1 | `labels/episodes.py` | fixtures | PENDING |
| L-03 | Single-reading rule (SA1 only) | REQ | Table 5.1 | `labels/episodes.py` | fixtures | PENDING |
| L-04 | Prediction-time eligibility (≥70, not in episode, refractory 60, 7/8, follow-up) | C | Table 5.1 | `labels/eligibility.py` | fixtures | PENDING |
| L-05 | Readings <80 not excluded | C | Table 5.1 | `labels/` | fixture | PENDING |
| L-06 | Treated definition = population only, never a feature | C | Table 5.1 | `evaluation/population.py` | feature-spec test | PENDING |
| L-07 | Patient-level partition T 30% / E 70%, seed 2026, stratified | C | §8.6, §10.3 | `configs/partition.csv` | `test_group_by_patient`; constant lock | PARTIAL (constants locked; file pending P-C4) |
| L-08 | 5 grouped folds within E; training = T ∪ E∖k | C | §15 | `evaluation/folds.py` | fold tests | PENDING |
| L-09 | E sealed until freeze; scripts refuse E access | C | §15, R8 | `data/access.py` (guard) | `test_freeze_guard` | PENDING |
| L-10 | G2 event sufficiency; G3b label validity | REQ | Table 21.1 | event audit | audit report | PENDING |

## Medication exposure

| ID | Requirement | Kind | Source | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| M-01 | Versioned drug dictionary; raw text preserved | REQ | §12.1, App. B | `configs/drug_dictionary.csv`, `medication/dictionary.py` | coverage ≥99% | PENDING |
| M-02 | parse_dose never raises; unknown → class `unknown`, excluded, counted | REQ | §25.3 | `medication/parse.py` | unit tests | PENDING |
| M-03 | Plausible-dose range check per drug | REQ | App. B | `medication/parse.py` | unit tests | PENDING |
| M-04 | Gliclazide formulation rule + flag | REQ (ASSUMPTION) | App. B | `medication/parse.py` | unit tests | PENDING |
| M-05 | Insulin exponential kernel Eq. 3–4; ∫ = 1 ± 0.01 | REQ | §12.2 | `medication/kernels.py` | `test_kernel_integrals` | PARTIAL (shape constraint on config tested) |
| M-06 | Premix = weighted sum; basal flat after lag; CSII micro-boluses; i.v. flag 4 h | REQ | §12.2 | `medication/kernels.py`, `exposure.py` | unit tests | PENDING |
| M-07 | Bateman SU/glinide, dose / D_max | REQ | Eq. 5–6 | `medication/kernels.py` | unit tests | PENDING |
| M-08 | Exposure uses only doses ≤ t; projections t+30/60 from past doses | REQ | §10.2, §25.3 | `medication/exposure.py` | `test_exposure_causal` | PENDING |
| M-09 | Missing timing → NaN + timing-unknown indicator (not zero); UI badge | REQ | Table 12.1 | `medication/`, `state/` | unit tests | PENDING |
| M-10 | Logged-not-prescribed → logged used + conflict flag | REQ | Table 12.1 | `medication/` | unit tests | PENDING |
| M-11 | Kernel parameters label-sourced, pharmacist-reviewed before freeze | REQ | §12.3, App. C | `configs/pharma.yaml` | freeze precondition test | PENDING (all ILLUSTRATIVE) |
| M-12 | G3 medication usability | REQ | Table 21.1 | medication audit | audit report | PENDING |
| M-13 | Never fabricate administration times | REQ | CLAUDE.md §15 | `medication/` | code review + tests | PENDING |

## State engine and features

| ID | Requirement | Kind | Source | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| S-01 | PatientState with CGM, exposure, quality, forecast, ledger blocks | REQ | §9.1, Table 25.1 | `state/` | `test_state_updates` | PENDING |
| S-02 | Deterministic, ordered, replayable updates | REQ | CLAUDE.md §16 | `state/`, `replay/` | state-sequence determinism | PENDING |
| F-01 | **Truncation equality** at all levels | REQ | §10.2, CLAUDE.md §11 | `features/` | `test_truncation_equality` | PENDING |
| F-02 | Feature groups 1–8 per App. D; level gating | REQ | App. D, Table 11.1 | `features/` | unit tests | PENDING |
| F-03 | Missing values NaN + `_missing` indicators | REQ | §25.1 | `features/` | unit tests | PENDING |
| F-04 | Feature spec stored with artefacts; mismatch error | REQ | Table 25.2 | `features/`, `models/` | unit test | PENDING |
| F-05 | Live path never imports labels/evaluation | REQ | CLAUDE.md §11 | package boundaries | `test_import_boundaries` | **PASS** |

## Models and calibration

| ID | Requirement | Kind | Source | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| R-01 | M0 trend rule (30-min slope → t+60, θ) | REQ | Table 11.1 | `models/m0.py` | unit tests | PENDING |
| R-02 | M1, M2, M3r, M3 LightGBM, one shared hyperparameter set tuned on M1 (T) | REQ | §11.1 | `models/`, `evaluation/tune.py` | determinism test | PENDING |
| R-03 | No class re-weighting; no monotone constraints in core | REQ | §11.1 | `configs/default.yaml` | config test | PENDING |
| R-04 | Deterministic: seed 2026, one thread for confirmatory | REQ | §11.1, Table 18.1 | `models/` | training determinism | PENDING |
| R-05 | Isotonic calibration on inner OOF; Brier, ECE, reliability | REQ | §11.1 | `calibration/` | nested isolation test | PENDING |
| R-06 | Risk-band rule decided before E (slope 0.8–1.25) | REQ | §11.1 | `calibration/` | dev report | PENDING |
| R-07 | Grouped TreeSHAP factor groups + caveat | REQ | §16.1 | `models/explain.py` | unit test | PENDING |
| R-08 | Artefacts hashed; API refuses mismatch | REQ | Table 18.1 | `models/artifacts.py`, `api/` | unit test | PENDING |
| R-09 | M4 only if G6 passes | OPT | §13.2 | — | — | N/A (ADR-015) |

## Policy

| ID | Requirement | Kind | Source | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| P-01 | Table 14.1 states and priority | C | Table 14.1 | `policy/decide.py` | `test_policy_table` | PENDING (P-C1 open) |
| P-02 | τA rule (dev FA ≤1.0), τW rule (≤3.0) | C | §14.3 | `evaluation/thresholds.py` | unit tests | PENDING (P-C2, P-C6) |
| P-03 | 60-min cooldown; ALERT persists | C | Table 5.1 | `policy/` | `test_cooldown` | PENDING |
| P-04 | LOW CONFIDENCE / timing tags never downgrade ALERT | REQ | §14.3 | `policy/` | `test_uncertainty_never_silences` | PENDING |
| P-05 | Gap → INSUFFICIENT DATA, no probability | REQ | §10.4 | `policy/` | `test_missing_abstains` | PENDING |
| P-06 | SYSTEM ERROR on exception/hash mismatch; never stale | REQ | §14.2, §18 | `policy/`, `api/` | unit + API tests | PENDING |
| P-07 | JSONL decision and ack logs with listed fields | REQ | §14.3 | `policy/`, `api/` | log schema test | PENDING |
| P-08 | 4 acknowledgement reason codes | REQ | §16.4 | `api/`, frontend | API + E2E | PENDING |
| P-09 | Never the word "safe"; no dose advice | REQ | §16.3 | policy, UI | UI string scan | PENDING |

## Evaluation and statistics

| ID | Requirement | Kind | Source | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| E-01 | Primary endpoint Δ sens@1FA (M3 − M2), E-treated | C | §6.1, Table 20.1 | `evaluation/` | metric fixtures | PENDING (P-C2, P-C3) |
| E-02 | Paired patient-cluster bootstrap, B=2000, seed 2027, percentile | C | Table 20.1 | `evaluation/bootstrap.py` | determinism test | PARTIAL (constants locked) |
| E-03 | Decision rule: lower bound > 0 | C | Table 20.1 | `evaluation/report.py` | unit test | PENDING |
| E-04 | Secondary metrics (Table 20.2) | REQ | §20.2 | `evaluation/metrics.py` | fixtures | PENDING |
| E-05 | S1–S7, SA1–SA8, R1–R4 | REQ | Table 20.3 | `evaluation/sensitivity.py` | run manifests | PENDING |
| E-06 | Model-selection rule; interpretation matrix | C | §15, Table 20.4 | `evaluation/report.py` | unit test | PENDING |
| E-07 | Calibration/τ only from inner OOF of training patients | C | §15 | `evaluation/` | `test_nested_fitting_isolation` | PENDING |
| E-08 | Deployed operating point reported | REQ | §15 | `evaluation/` | report | PENDING |
| E-09 | G4 baseline feasibility; G5 statistical interpretability | REQ | Table 21.1 | `evaluation/` | gate reports | PENDING |
| E-10 | Results tables filled automatically from results.json | REQ | §22 | `evaluation/report.py` | report test | PENDING |

## Reproducibility and engineering

| ID | Requirement | Kind | Source | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| X-01 | Provenance on every artefact/result | REQ | Table 18.1, CLAUDE.md §13 | `common/provenance.py` | manifest completeness test | PENDING |
| X-02 | Python 3.11, pinned lockfile | REQ | Table 18.1 | `pyproject.toml`, `uv.lock` | `uv sync` | **PASS** |
| X-03 | Seeds as specified | C | Table 18.1, App. F | `configs/default.yaml` | `test_protocol_constants` | **PASS** (config level) |
| X-04 | Freeze: hashes recorded; confirmatory refuses without | REQ | §15, H.2 | `hyposense freeze` | `test_freeze_guard` | PENDING |
| X-05 | Offline CPU laptop; no network on demo path | REQ | Table 18.1 | `api/`, frontend static export | E2E offline run | PENDING |
| X-06 | Latency p95 <200 ms per reading | REC | Table 18.1 | — | benchmark | PENDING |
| X-07 | Docker image for demo | REC | Table 18.1 | `Dockerfile` | build test | PENDING |
| X-08 | Centralised scientific constants | REQ | CLAUDE.md §42 | `configs/` | constant lock | **PASS** (initial) |
| X-09 | Reproduce audit → freeze → confirm → demo by command | REQ | §23.2 | `hyposense` CLI | E2E | PENDING (stub) |

## Interface and demo

| ID | Requirement | Kind | Source | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| U-01 | Ward Board (state then risk; text badges; provenance) | REQ | Table 17.1 | `frontend/` | E2E | PENDING |
| U-02 | Patient Review (state, p, 6-h CGM + doses, exposure, quality, factors, ack) | REQ | Table 17.1 | `frontend/` | E2E | PENDING |
| U-03 | Evidence view from results.json (curves, ladder, calibration, forest, failures, honesty, model card) | REQ | Table 17.1 | `frontend/` | E2E | PENDING |
| U-04 | Replay deterministic, ×120, ordered | REQ | §23, G7 | `replay/` | `test_replay_determinism` | PENDING |
| U-05 | Seeded TP/FN/FP case selection from E OOF; cases.json | REQ | §23.1 | `scripts/select_demo_cases.py` | hash recorded | PENDING |
| U-06 | Data honesty card shown first | REQ | Table 23.1 | `frontend/` | E2E | PENDING |
| U-07 | Synthetic content labelled SYNTHETIC; never fabricated results | REQ | CLAUDE.md §24, §31 | all | review | PENDING |
| U-08 | Loading / error / insufficient / stale states | REQ | owner brief, CLAUDE.md §17 | `frontend/` | E2E | PENDING |

## Deliverables

| ID | Requirement | Kind | Source | Status |
|---|---|---|---|---|
| V-01 | Public repo, README, licence (MIT + CC BY attribution) | REQ | §2.1, §24 | PARTIAL (README) |
| V-02 | Architecture document | REQ | §27 | PARTIAL (docs/ARCHITECTURE.md) |
| V-03 | Model card | REQ | §27 | PENDING |
| V-04 | Deck; video ≥20 min | REQ | §2.1 | PENDING |
| V-05 | Folder named TeamName_CollegeName | REQ | §2.1 | PENDING (names unknown) |
| V-06 | Competition registration | REQ | §2.1 | **UNKNOWN — urgent** |
