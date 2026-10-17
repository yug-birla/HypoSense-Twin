# Implementation Plan

Status: **APPROVED FOR S0–S1 EXECUTION; later stages are subject to review** (2026-10-18).
Baseline: Blueprint §26 (Table 26.1). The stage contents are refined here, mainly by ADR-005,
which moves the audit onto production modules. Live progress is tracked in
[CURRENT_STATE.md](CURRENT_STATE.md) and [NEXT_STEPS.md](NEXT_STEPS.md).

## 0. Critical path and parallelism

```
S0 ─► S1 ─► S2 ─► S3 ─► S4 ─► S5 ─► S6 ─► FREEZE ─► S9 ─► S10
                        │      │
                        │      └──► S7 (policy, replay, API; usable with M0 first)
                        │                 └──► S8 (frontend on real T-patient replay)
                        └──── S7/S8 contracts can be drafted once S4 schemas exist
```

- **Critical path**: S1 → S2 → S3 → S4 → S5 → S6 → Freeze → S9.
- **Parallel track** (with a second person): S7 → S8, starting once the S4 schemas are stable.
  It is developed against **real T-patient replay using M0**, so no fabricated values are
  needed.
- **Early submittable version** (blueprint §26 advice): S0–S5 + a minimal S7–S8 (M0 twin on
  T replay, Evidence view clearly labelled DEVELOPMENT / PENDING).
- **No new features after freeze.**

## 1. Indicative calendar (PLAN, not a commitment — team capacity is unknown)

The event reportedly ends **20 Nov 2026**. The Phase-1 deadline is unknown.

| Window | Stage(s) |
|---|---|
| 18 Oct | S0 (done except registration and remote/CI); start S1 |
| 18–20 Oct | S1 |
| 19–22 Oct | S2 (labels test-first; partition) |
| 21–25 Oct | S3 (dictionary, parser, kernels; pharma sources) |
| 23–28 Oct | S4 (state engine, features, truncation test) |
| 26–29 Oct | S5 (harness, metrics, M0, ANALYSIS_PLAN.md) → early submittable version |
| 28 Oct–4 Nov | S6 (M1 tuning, ladder on T, calibration benchmark, G4) |
| 27 Oct–5 Nov | S7 (parallel) |
| 29 Oct–12 Nov | S8 (parallel) |
| ~5–6 Nov | **FREEZE** |
| 6–8 Nov | S9 confirmatory run + sensitivity analyses |
| 8–18 Nov | S10 demo cases, evidence, video, deck, packaging; buffer to 20 Nov |

---

## S0 · Repository and environment
- **Objective**: a reproducible, documented, testable baseline.
- **Deliverables**: git repo; `src/` package skeleton; `pyproject.toml` + `uv.lock`;
  `configs/default.yaml` (DRAFT), `configs/pharma.yaml` (ILLUSTRATIVE); project control docs;
  protocol-constant and import-boundary tests; README; data README.
- **Remaining**: competition registration (human, **deadline reportedly 18 Oct 19:00 IST**);
  remote repository and CI workflow (pytest + ruff + mypy) once a remote exists; LICENSE and
  DATA_LICENSES.md (when the team name and holder are known).
- **Acceptance**: `uv sync && uv run pytest` passes on a clean checkout. **Status: MET** (16 tests). **S0 COMPLETE** (remote/CI deferred).

## S1 · Data acquisition and structural audit (Gates G0, G1)
**Status: COMPLETE (2026-10-18)** — G0 PASS, G1 PASS; official figshare v5; v1/v2 reconciliation reproduces every structural blueprint number; original partition imported and locked (ADR-016/017). Delivered via the `hyposense` CLI (not `scripts/fetch_official.py`). Evidence: `artifacts/gates/`, `experiments/runs/ALL-AGG-audit-structural-20261017T2135*`.

- **Objective**: the official ShanghaiT2DM copy, pinned and structurally validated.
- **Work**:
  1. `scripts/fetch_official.py`: download the ShanghaiT2DM files from figshare
     (doi:10.6084/m9.figshare.c.6310860) into `data/raw/`. Record source URLs and the date.
     If automated download fails, document the manual steps.
  2. `data/MANIFEST.sha256` + `common/hashing.py` checksum verification.
  3. `data/adapter.py` v0: read .xls/.xlsx, discover and map the column variants (an unmapped
     column is an error), parse timestamps (+08:00), sort, deduplicate, quarantine
     non-monotone rows.
  4. `hyposense audit --structural`: files, recordings, patient prefixes, column variants, CGM
     reading count vs the published 112,475 and the mirror's 112,287, interval histogram, gaps,
     floor readings, CBG count, summary-sheet fields. Output to
     `experiments/runs/<id>/audit_structural.json` + Markdown.
- **Tests**: column-mapping unit tests (synthetic fixtures labelled SYNTHETIC); timestamp
  parsing; checksum refusal; audit determinism (two runs → identical report hash).
- **Gate G0**: 109 files, with the reading count reconciled to 112,475 or the difference
  explained. **G1**: ≥99% of readings parse and ≥99% of intervals ≤20 min.
- **Stop**: G1 fails → stop (change dataset). The G0 discrepancy is unexplained → block the
  unsealing of E (not development).
- **Approval needed**: P-C5 (outcome-blind access) should be approved before running the
  audit over E files.

## S2 · Schemas, adapter completion, label builder, partition (Gates G2, G3b)
**Status: COMPLETE (2026-10-18).** Labels implemented test-first. 48/48 blueprint event values reproduced exactly on figshare v1/v2. G2 PASS (provisional treated definition), G3b TRIGGERED. Strata re-check passed. Evidence: `experiments/runs/ALL-AGG-audit-events-20261017T2212*`, `artifacts/gates/G2.json`, `G3b.json`. Open: P-C8 (sensor failure).

- **Objective**: typed events for all recordings, verified labels and the frozen partition.
- **Work**:
  1. `common/schema.py` → Pydantic/dataclass contracts (Blueprint Table 25.1): Observation,
     DoseEvent (raw text preserved), MealEvent, PatientStatic, EpisodeLabel, plus
     `RecordingBundle`.
  2. **Test-first** `labels/`: ≥20 hand-labelled fixtures (gaps of 16/20/25/30/31 min, floor
     values, single-reading dips, recovery with one reading ≥70, record end, overlapping L1/L2,
     refractory edges, the 7-of-8 rule, the follow-up rule). Write the tests, confirm they
     fail, then implement `build_episodes` and `eligible_times`.
  3. Event audit (aggregate): L1/L2/single counts, per-patient distribution, nocturnal share,
     warnable share, prediction-time count, CGM–CBG agreement (G3b).
  4. Partition: adopt the original file (P-C4 option A) or generate one (option B). Write
     `configs/partition.csv` + hash, then implement the **partition guard** (ADR-011).
- **Tests**: `test_labels_fixtures`; `test_group_by_patient`; episode-count regression
  (golden numbers once established); `test_summary_hypo_field_never_used`.
- **Gates**: G2 (≥100 treated episodes in ≥20 E patients; half-width ≤0.15 at ICC 0.15); G3b
  re-confirmed.
- **Stop**: counts differ unexplained from the audit → investigate before proceeding.
- **Approval needed**: P-C4 decision.

## S3 · Medication normalisation and exposure engine (Gate G3)
**Status: NEXT.** It also delivers the production treated status and a G2 re-check (ADR-023).

- **Work**: `configs/drug_dictionary.csv` (versioned); `parse_dose` (multi-component text,
  units, plausible ranges, gliclazide formulation rule, unknown → class `unknown`); CSII
  bolus/basal and the i.v. flag; prescribed-vs-logged conflict flags; kernels (Eq. 1–6);
  `exposure_at`; `pharma.yaml` production values with label sources (P-B3, P-B4); meal-event
  parsing (timing + content-known flag).
- **Tests**: zero exposure before administration; onset; peak at t_peak/t_max; decay to 0 at
  t_dur; integral = 1 ± 0.01; overlapping and repeated doses are additive; missing doses lead
  to timing-unknown (not zero); malformed records → `unknown`, never raise; boundary
  timestamps (τ = 0, τ = t_dur); `test_exposure_causal`; dictionary coverage ≥99%; property
  tests (Hypothesis) for linearity and causality.
- **Gate G3**: ≥90% parse; ≥80% of treated recording-days have entries; ≤15-min resolution;
  ≥20 treated E patients.
- **Stop**: G3 fails → context-only branch (M2 vs M1).
- **Human dependency**: a clinical-pharmacist review of kernel parameters (§12.3). If no
  pharmacist is available, use label-sourced values marked "not pharmacist-reviewed" in the
  model card.

## S4 · Patient State Engine and causal Feature Builder
- **Work**: `state/` (sub-states, deterministic `update`, causal episode tracker, ledger);
  `features/` (App. D groups 1–8, level gating, `feature_spec.json`); offline snapshot
  generation for **T patients only** → Parquet; profile throughput (ADR-004).
- **Tests**: **truncation equality** (all levels, random t, Hypothesis, including episode
  boundaries and dose times); `test_state_updates`; replay determinism of the state sequence;
  `test_features_ignore_ledger`; missing-indicator behaviour; static allow-list.
- **Stop**: any truncation inequality → **STOP model development** (CLAUDE.md §11).

## S5 · Evaluation harness, metrics and M0
- **Work**: write `docs/protocol/ANALYSIS_PLAN.md` (after P-C2/P-C3/P-C6 approvals);
  `evaluation/metrics.py` (episode hits, lead time, notifications with cooldown, FA/day,
  operating curve with the first-crossing rule, partial area, per-patient metrics, log-loss,
  Brier, AUPRC, ECE, calibration slope/intercept); `cluster_bootstrap` (paired, B=2000,
  seed 2027); run manifests (ADR-010); M0 on T.
- **Tests**: metric fixtures computed by hand (tiny synthetic traces); bootstrap seed
  determinism; non-monotone FA fixture (P-C2); follow-up exclusion fixture (P-C3).
- **Acceptance**: the M0 operating curve on T qualitatively reproduces Table A.2. Exact numbers
  are expected to differ if the partition changed (P-C4).

## S6 · M1 / M2 / M3r / M3 development on T (Gate G4)
- **Work**: LightGBM wrapper and artefacts (ADR-009); Optuna tuning of M1 on T (≤30 trials,
  inner grouped CV, mean log-loss) and the `num_boost_round` rule (P-B2); M2/M3r/M3 with
  frozen hyperparameters; nested calibration; calibration benchmark (P-B1); the risk-band
  decision (slope rule on held-out inner data); τA/τW procedure; grouped TreeSHAP;
  development-only operating curves (labelled DEVELOPMENT).
- **Tests**: training determinism (same hash twice); nested-fitting isolation; artefact hash
  check; feature-spec mismatch error.
- **Gate G4**: all tests pass, the pipeline runs end-to-end on T, and the M1 operating curve is
  computed. On failure → M0 becomes the operational baseline; fix the pipeline.

## S7 · Policy engine, replay and backend API (parallel track)
- **Work**: `policy.decide` (Table 14.1 + approved P-C1); cooldown; tags; JSONL logs; replay
  service (ordering, speed, seek, case selection); FastAPI routes + SSE (ADR-008);
  acknowledgement store; artefact hash check at start-up; SYSTEM ERROR path.
- **Tests**: every Table 14.1 row; threshold boundaries (p = τA exactly); WATCH → ALERT;
  cooldown; persistent risk; current low; insufficient data; missing medication badge;
  recovery; repeated alerts; malformed inference response → SYSTEM ERROR; tags never
  downgrade ALERT; `test_replay_determinism` (identical decision-log hash); `test_long_run`
  (14-day replay at ×600); API contract tests.

## S8 · Professional frontend (parallel track)
- **Work**: Next.js app (ADR-007): Ward Board, Patient Review, Evidence view; replay controls;
  event timeline/ledger; provenance strip; data-quality and timing badges; acknowledgement
  panel; loading, error, insufficient-data and stale states; honesty card. Types are generated
  from OpenAPI.
- **Tests**: component tests for state badges (text present, not colour alone); Playwright E2E:
  replay a T patient → all six states visible → acknowledge an alert → log entry exists; a UI
  string review for prohibited wording ("safe", dose advice).
- **Acceptance**: all six states visible on a T replay; runs offline from the FastAPI-served
  static build.

## FREEZE · Protocol, code, configuration and artefact freeze
- **Preconditions (checklist)**: G0 passed or explained; G1–G4 passed; all P-C items
  resolved; `pharma.yaml` has no ILLUSTRATIVE kernels; ANALYSIS_PLAN.md complete; calibration
  method and band decision recorded; τ procedure fixed; seeds fixed; full test suite green;
  clean git tree.
- **Work**: `hyposense freeze` writes `artifacts/freeze/FREEZE.json` with hashes (code tree,
  configs, partition, dictionary, pharma, analysis plan, uv.lock) and a tagged commit
  `protocol-freeze-v1`. The README records the hash.
- **Tests**: `test_freeze_guard` (the confirmatory command refuses to run without a matching
  freeze record; tuning commands refuse E patients).

## S9 · Confirmatory evaluation (run once)
- **Work**: `hyposense confirm`: 5 grouped folds over E with training data T ∪ (E∖k); nested
  calibration and τ; OOF pooling; primary Δ with the paired cluster bootstrap; S1–S7, SA1–SA8,
  R1–R4 as planned; the deployed operating point; `results.json`; model card; tables 22.1–22.3
  filled automatically. Apply the model-selection rule (§15) and interpretation matrix
  (Table 20.4) mechanically.
- **Gate G5**: every resample contains episodes for both models. On failure → report as
  inconclusive.
- **Rule**: **no optimisation after seeing the results.**

## S10 · Demo, documentation and submission assets (Gate G7)
- **Work**: seeded TP/FN/FP case selection (`demo/cases.json`, seed 2026, eligibility rule
  fixed in advance); Evidence view from `results.json`; honesty card; model card; deck;
  ≥20-min video; architecture document export; the `TeamName_CollegeName` packaging;
  Docker image; offline clean-machine run.
- **Gate G7**: two demo runs produce an identical decision-log hash; TP/FN/FP cases exist (or
  their absence is stated on screen); all states exercised; offline run verified.

## E1 · Optional reduced physiology (Gate G6) — **not planned** (ADR-015)
