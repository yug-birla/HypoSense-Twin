# Requirements Traceability Matrix

_Last updated: 2026-10-19 (pre-freeze; S9/S10 built, not run)_

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
| D-01 | Official figshare copy, SHA-256 manifest; loader refuses on mismatch | REQ | §10.1, G0 | `data/source.py`, `data/manifest.py`, `data/MANIFEST.json` | `test_manifest_detects_tampering`, `test_verify_archive_rejects_mismatch`; G0.3/G0.4 | **PASS** |
| D-02 | Reconcile CGM count to 112,475 or explain | REQ | G0, N8 | `audit/gates.py`, `audit/versions.py` | G0.7 PASS (rows = 112,475; 13 documented no-CGM rows) | **PASS** |
| D-03 | Map 5 column variants; unmapped column = error | REQ | §10.1 | `data/columns.py` | `test_all_observed_header_variants_map`, `test_schema_errors` | **PASS** |
| D-04 | Units: mg/dL, IU, mg (g → mg), IU/h | REQ | §10.1, §25.1 | `data/columns.py` (glucose units; unitless headers verified in mg/dL range), `medication/parse.py` (`_TO_MG`: g/mcg → mg; IU doses) | audit `schema.unitless_header_cgm_in_mgdl_range`; `test_oral_column_parses` ("metformin 0.5 g" → 500 mg), `test_insulin_sc_parses`, `test_implausible_units_are_kept_and_flagged` | **PASS** |
| D-05 | tz-aware +08:00, epoch seconds, sort, dedupe, quarantine non-monotone | REQ | §10.1, §25.1 | `data/loader.py`, `common/timeconv.py` | `test_clean_recording_contract_and_epoch`, `test_non_monotone_*`, `test_duplicate_timestamps`, `test_subsecond_*` | **PASS** (flags, no deletion; ADR-019) |
| D-06 | Quality flags (gap >20, ≤40, rate >4, warm-up); flags never delete | REQ | §10.1 | `data/quality.py` | `test_cgm_quality_flags` | **PASS** |
| D-07 | Patient = file prefix; group by patient_key | REQ | N3, §25.1 | `data/records.py` (identity); `evaluation/folds.py` (`grouped_folds`) | `test_parse_recording_name`, `test_multiple_recordings_share_patient_key`; `test_grouped_folds_are_deterministic_balanced_and_stratified` | **PASS** |
| D-08 | Never use "Hypoglycemia (yes/no)" field | REQ | N2, App. D | `data/summary.py` FORBIDDEN_FEATURE_COLUMNS; `state/context.py` allow-list (import-time assert) | `test_static_context_parsing` (field supplied, never read); `test_spec_records_are_complete_and_safe` | **PASS** |
| D-09 | G1: ≥99% readings parse, ≥99% intervals ≤20 min | REQ | Table 21.1 | `audit/gates.py` | `test_g1_thresholds_*`; artifacts/gates/G1.json (1.0 / 0.999902) | **PASS** |
| D-10 | Data-quality report (App. G sections) | REQ | App. G | `hyposense audit run` / `audit events` / `audit medication` (`audit/run.py`, `audit/event_run.py`, `audit/med_run.py`) | `test_audit_is_deterministic`, `test_event_audit_is_deterministic`, `test_measure_events_populates_every_section`, `test_measure_medication_on_synthetic_recordings` | **PASS** (provenance, structure, CGM, events, medication parse, partition) |
| D-11 | Logs never contain raw diet free text | REQ | Table 18.1 | by construction: `state/events.MealEvent` carries no text (only `content_known`); `api/schemas.py` acknowledgement payload refuses extra/free-text fields | `test_api_contract_and_acknowledgement` (free-text `note` → 422) | PARTIAL (no test scanning decisions.jsonl / acks.jsonl for diet text) |

## Labels and partition

| ID | Requirement | Kind | Source | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| L-01 | L1 episode rule (2 consecutive <70, spacing ≤20; end 2 ≥70 / gap >30 / record end) | C | Table 5.1, ANALYSIS_PLAN §0 | `labels/episodes.py` | 34 trace + 4 loader-path fixtures (`test_labels.py`), differential test vs executable spec, mutants, v2 48/48 | **PASS** |
| L-02 | L2 (54 mg/dL) secondary label | C | Table 5.1 | `labels/episodes.py`, `labels/build.py` | F02, F14, F15; differential test; v2 96/26 exact | **PASS** |
| L-03 | Single-reading rule (SA1 only) | REQ | Table 5.1 | `labels/episodes.py` (min_run=1) | F01, F04, F05, F09, F13a; v2 430/67 exact | **PASS** |
| L-04 | Prediction-time eligibility (≥70, not in episode, refractory 60, 7/8, follow-up) | C | Table 5.1, ANALYSIS_PLAN §0 | `labels/eligibility.py` | E01–E11 fixtures (incl. half-open window, +60 boundary, refractory edges); differential test; v2 107,041/1,188 exact | **PASS** |
| L-05 | Readings <80 not excluded | C | Table 5.1 | `labels/eligibility.py` (no such rule) | `prior_reading_lt80` 307 episodes retained (v2/v5) | **PASS** |
| L-06 | Treated definition = population only, never a feature | C | Table 5.1, ANALYSIS_PLAN §0b | `medication/recording.treatment_status`; artifacts/population/treated_patients.csv | `test_treatment_status`, `test_production_treated_population` (72; 2078 untreated) | **PASS** |
| L-07 | Patient-level partition T 30% / E 70%, seed 2026, stratified | C | §8.6, §10.3 | `configs/partition.csv` (ADR-016), `data/partition.py` | `test_official_partition_is_pinned_and_immutable`, `test_split_*`, `partition verify` | **PASS** (stratum re-checks S2/S3 pending) |
| L-08 | 5 grouped folds within E; training = T ∪ E∖k | C | §15 | `evaluation/folds.py` (`grouped_folds`), `evaluation/confirm.py` (train = always_train ∪ E∖k), `evaluation/confirm_fit.py` (fold-isolation assert) | `test_grouped_folds_are_deterministic_balanced_and_stratified`, `test_each_patient_is_scored_by_its_own_fold_model` | IMPLEMENTED, NOT RUN (S9 pending freeze) |
| L-09 | E sealed until freeze; scripts refuse E access | C | §15, R8 | `data/dataset.py` scopes (ADR-018) and `unlock_for_presentation`, `freeze.verify_freeze_record` | `test_tuning_scope_never_opens_sealed_patients`, `test_all_scope_is_refused_before_freeze`, `test_aggregate_audit_scope_is_confined`, `test_confirmatory_access_still_refused_before_s9`, `test_e_unlock_refuses_anything_but_a_verified_freeze`, `test_presentation_access_refused_without_an_official_run` | **PASS** |
| L-10 | G2 event sufficiency; G3b label validity | REQ | Table 21.1 | `audit/gates.py`, `audit/event_run.py` | `test_g2`, `test_g3b`, `test_precision_table_reproduces_blueprint_table_8_4`; artifacts/gates/G2.json (PASS, provisional), G3b.json (TRIGGERED) | **PASS** (G2 re-check in S3) |

## Medication exposure

| ID | Requirement | Kind | Source | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| M-01 | Versioned drug dictionary; raw text preserved | REQ | §12.1, App. B | `configs/drug_dictionary.csv`, `medication/dictionary.py`, `events.py` (raw_text, component_text, source_column) | `test_medication_parse.py`; real-data: 4,653/4,653 recognised | **PASS** |
| M-02 | parse_dose never raises; unknown → class `unknown`, excluded, counted | REQ | §25.3 | `medication/parse.py` (UNPARSEABLE status) | `test_unknown_product_is_unparseable`; real data 0 unparseable | **PASS** |
| M-03 | Plausible-dose range check per drug | REQ | App. B | dictionary plausible_min/max → DOSE_IMPLAUSIBLE | `test_implausible_units_are_kept_and_flagged` | **PASS** |
| M-04 | Gliclazide formulation rule + flag | REQ (ASSUMPTION) | App. B | `pharma.yaml formulation_rules`; `parse.apply_formulation_rule` | `test_gliclazide_formulation_rule` (15 → INFERRED) | **PASS** |
| M-05 | Insulin exponential kernel Eq. 3–4; ∫ = 1 ± 0.01 | REQ | §12.2 | `medication/kernels.py` | `test_exponential_kernel_shape` | **PASS** |
| M-06 | Premix = weighted sum; basal flat after lag; CSII micro-boluses; i.v. flag 4 h | REQ | §12.2 | `exposure.py` | `test_premix_split_and_basal_group`, `test_csii_basal_reconstruction_suspend_and_cap`, `test_iv_insulin_flag_only` | **PASS** (6-h cap: ADR-026) |
| M-07 | Bateman SU/glinide, dose / D_max | REQ | Eq. 5–6 | `kernels.BatemanKernel`, `exposure.py` | `test_bateman_kernel`, `test_secretagogue_scaled_by_dmax` | **PASS** |
| M-08 | Exposure uses only doses ≤ t; projections t+30/60 from past doses | REQ | §10.2, §25.3 | `exposure.py`, `timing.py` | `test_truncation_equality` (Hypothesis), `test_future_dose_does_not_change_the_past`, real-data bitwise truncation | **PASS** |
| M-09 | Missing timing → NaN + timing-unknown indicator (not zero); UI badge | REQ | Table 12.1 | `exposure.QualityState` | `test_quality_states` | **PASS** (UI badge S8) |
| M-10 | Logged-not-prescribed → logged used + conflict flag | REQ | Table 12.1 | `audit/medication.py` (prescribed_vs_logged) | real data: insulin 8, SU 4/4 | **PASS** |
| M-11 | Kernel parameters label-sourced, pharmacist-reviewed before freeze | REQ | §12.3, App. C | `configs/pharma.yaml` v1.0.0, PARAMETER_SOURCES.md; `freeze.pharmacist_status` | `test_pharma_parameters_have_provenance_and_none_is_illustrative`, `test_pharmacist_review_is_mandatory_unless_reviewed_or_waived` | PARTIAL (sourced; pharmacist review PENDING — see FZ-08 BLOCKED) |
| M-12 | G3 medication usability | REQ | Table 21.1 | `audit/gates.evaluate_g3`, `med_run.py` | `test_g3_thresholds`; artifacts/gates/G3.json | **PASS** |
| M-13 | Never fabricate administration times | REQ | CLAUDE.md §15 | untimed rows skipped and counted; 6-h pump cap | `parse_recording` skip counter; ADR-026 | **PASS** |

## State engine and features

| ID | Requirement | Kind | Source | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| S-01 | PatientState with CGM, exposure, quality, forecast, ledger blocks | REQ | §9.1, Table 25.1 | `state/patient.py` (+ `cgm`, `quality`, `medication`, `ledger`, `context`, `history`, `stream`) | `test_start_and_update_advance_time_and_counts`, `test_ledger_*`, `test_quality_state_equals_authoritative_flag_functions` | **PASS** |
| S-02 | Deterministic, ordered, replayable updates | REQ | CLAUDE.md §16 | `state/patient.update` (order-checked), `try_update` (SYSTEM_ERROR) | `test_replay_is_deterministic`, `test_same_past_different_future_gives_identical_current_state`, `test_same_timestamp_order_is_dose_meal_cgm_cbg`, `test_malformed_input_and_safe_degradation` | **PASS** (replay service S7) |
| F-01 | **Truncation equality** at all levels | REQ | §10.2, CLAUDE.md §11 | `features/` (offline = replay) | `test_truncation_equality_every_cgm_time` (Hypothesis), `test_truncation_equality_through_the_loader`; real T: 31,292 eligible times, 0 mismatches (audit runs 2–5) | **PASS** |
| F-02 | Feature groups 1–8 per App. D; level gating | REQ | App. D, Table 11.1 | `features/spec.py` (M1 38 / M2 72 / M3r 95 / M3 100), `features/{cgm,context,medication}.py` | `test_level_membership`, per-group unit tests | **PASS** |
| F-03 | Missing values NaN + `_missing` indicators | REQ | §25.1 | `features/spec.py` Missing policy (ADR-033) | `test_every_indicator_is_in_the_same_level_as_its_features`, missingness unit tests; audit REQUIRED violations 0 | **PASS** |
| F-04 | Feature spec stored with artefacts; mismatch error | REQ | Table 25.2 | `artifacts/features/feature_spec.json` (sha256 `82fc54e9…`), `FeatureSpecMismatch` | `test_committed_feature_spec_matches_the_registry`, `test_feature_spec_is_locked`, `test_feature_spec_mismatch_is_raised` | **PASS** (model-artefact check S6) |
| F-05 | Live path never imports labels/evaluation | REQ | CLAUDE.md §11 | package boundaries | `test_import_boundaries` | **PASS** |

## Models and calibration

| ID | Requirement | Kind | Source | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| R-01 | M0 trend rule (30-min slope → t+60, θ) | REQ | Table 11.1 | `models/m0.py` | `test_m0_flat_falling_rising`, `test_m0_minimum_history_and_strict_threshold`, `test_exact_tie_at_theta_on_the_data_grid_never_alerts`, `test_m0_projection_is_the_executable_spec` | **PASS** |
| R-02 | M1, M2, M3r, M3 LightGBM, one shared hyperparameter set tuned on M1 (T) | REQ | §11.1 | `models/lgbm.py`, `evaluation/s6_run.tune_m1`, `evaluation/s7_artifact.frozen_params` | `test_lgbm_training_is_deterministic_and_checks_features`, `test_frozen_params_are_full_precision_s6_values`; trials.csv (D6-02) | **PASS** |
| R-03 | No class re-weighting; no monotone constraints in core | REQ | §11.1 | `models/lgbm.py`, `configs/default.yaml` | `test_early_stopping_records_best_iteration_and_class_weighting_is_refused` | **PASS** (class weighting refused by test; monotone constraints absent by inspection, no dedicated test) |
| R-04 | Deterministic: seed 2026, one thread for confirmatory | REQ | §11.1, Table 18.1 | `models/lgbm.py` (seed, deterministic, num_threads from `configs/default.yaml`), `common/runtime.py` | `test_lgbm_training_is_deterministic_and_checks_features`, `test_single_threaded_math_env_does_not_override_explicit_settings`, `test_population_partition_cv_bootstrap` | **PASS** |
| R-05 | Isotonic calibration on inner OOF; Brier, ECE, reliability | REQ | §11.1 | `calibration/methods.py` (canonical floored isotonic, FZ-01), `evaluation/metrics.window_metrics` / `calibration`, `s6_run.task_outer`, `confirm_fit.task_fit` | `test_calibrators_are_monotone_bounded_and_serialisable`, `test_floored_interp_never_reaches_0_or_1_and_keeps_order`, `test_floored_calibrator_bounds_monotone_deterministic`, `test_calibration_of_a_perfectly_calibrated_model`, `test_window_metrics_by_hand_and_probability_guard` | **PASS** (nested isolation: runtime asserts only, see E-07) |
| R-06 | Risk-band rule decided before E (slope 0.8–1.25) | REQ | §11.1 | `evaluation/s6_run.py` (`ui`: percentages if 0.8 ≤ slope ≤ 1.25, else risk bands) | dev report (ANALYSIS_PLAN: slope 0.97 → 1.08 / 1.07, inside the band → percentages) | PARTIAL (rule applied on T before E; no unit test of the band rule) |
| R-07 | Grouped TreeSHAP factor groups + caveat | REQ | §16.1 | `models/artifact.py` (`contributions`, raw-margin pred_contrib), `s6_run.task_outer` (grouped mean abs SHAP); caveat/group labels in `policy/messages.py` | `test_reason_line_names_associations_never_causes` (caveat and group labels) | PARTIAL (no unit test of grouped contribution values; `models/explain.py` does not exist) |
| R-08 | Artefacts hashed; API refuses mismatch | REQ | Table 18.1 | `models/artifact.py`, `api/service.py` | `test_tampered_file_is_refused`, `test_missing_file_is_refused`, `test_corrupted_content_with_consistent_hash_is_refused`, `test_service_refuses_to_start_on_tampered_artifact`, `test_tampered_fold_bundle_is_refused` | **PASS** |
| R-09 | M4 only if G6 passes | OPT | §13.2 | — | — | N/A (ADR-015) |

## Policy

| ID | Requirement | Kind | Source | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| P-01 | Table 14.1 states and priority (+ approved P-C1) | C | Table 14.1, ANALYSIS_PLAN §1 | `policy/decide.py` | `test_policy_table` | **PASS** (S7: `decide`; P-C1, P-C8b; `test_policy_decide`, S5 gate tests) |
| P-02 | τA rule (dev FA ≤1.0), τW rule (≤3.0) | C | §14.3, ANALYSIS_PLAN §3.5–3.6 | `evaluation/metrics.select_threshold` | `test_threshold_selection_tau_a_and_tau_w`, `test_policy_budgets` | **PASS** |
| P-03 | 60-min cooldown; ALERT persists | C | Table 5.1 | `policy/` | `test_cooldown` | **PASS** (S7: `test_cooldown_and_alert_persistence`) |
| P-04 | Uncertainty / timing tags never downgrade ALERT (LOW CONFIDENCE removed, P-B12) | REQ | §14.3 | `policy/` | `test_uncertainty_never_silences` | **PASS** (S7: property test `test_tags_never_change_state_or_notification`) |
| P-05 | Gap → INSUFFICIENT DATA, no probability | REQ | §10.4 | `policy/` | `test_missing_abstains` | **PASS** (S7: gate + `current()` staleness; API stale-bed test) |
| P-06 | SYSTEM ERROR on exception/hash mismatch; never stale | REQ | §14.2, §18 | `policy/`, `api/` | unit + API tests | **PASS** (S7: artefact refusal tests; inference / malformed → SYSTEM_ERROR; no stale reuse) |
| P-07 | JSONL decision and ack logs with listed fields | REQ | §14.3 | `policy/`, `api/` | log schema test | **PASS** (S7: decisions.jsonl / acks.jsonl; deterministic log hash) |
| P-08 | 4 acknowledgement reason codes | REQ | §16.4 | `api/`, frontend | API + E2E | **PASS** (API: enum of 4; frontend S8) |
| P-09 | Never the word "safe"; no dose advice | REQ | §16.3 | policy, UI | UI string scan | **PASS** (backend texts scanned; UI strings S8) |

## Evaluation and statistics

| ID | Requirement | Kind | Source | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| E-01 | Primary endpoint Δ sens@1FA (M3 − M2), E-treated | C | §6.1, Table 20.1, ANALYSIS_PLAN §2–3 | `evaluation/confirm.py`, `evaluation/metrics.sens_at_budget`, `evaluation/bootstrap.py` | `test_sens_at_budget_*` fixtures (ANALYSIS_PLAN §4), `test_paired_difference_uses_the_same_draws` | IMPLEMENTED, NOT RUN (S9 pending freeze) |
| E-02 | Paired patient-cluster bootstrap, B=2000, seed 2027, percentile | C | Table 20.1 | `evaluation/bootstrap.py` | `test_bootstrap_draws_are_deterministic_and_keep_multiplicity`, `test_paired_difference_uses_the_same_draws`, `test_bootstrap_percentile_interval_on_a_known_case`, `test_population_partition_cv_bootstrap`, `test_official_run_refuses_bootstrap_override` | **PASS** |
| E-03 | Decision rule: lower bound > 0 | C | Table 20.1 | `evaluation/confirm.h1_supported` | `test_h1_requires_lower_bound_above_zero` | **PASS** (rule; application to E NOT RUN) |
| E-04 | Secondary metrics (Table 20.2) | REQ | §20.2 | `evaluation/metrics.py` (window, calibration, partial area, operating point), `evaluation/confirm.py` | `test_window_metrics_by_hand_and_probability_guard`, `test_calibration_of_a_perfectly_calibrated_model`, `test_partial_area_monotone_curve_by_hand`, `test_fa_at_sensitivity_interpolates_first_crossing` | IMPLEMENTED, NOT RUN (S9 pending freeze) (Table 20.2 completeness not re-audited row by row) |
| E-05 | S1–S7, SA1–SA8, R1–R4 | REQ | Table 20.3 | `evaluation/confirm.py` (S1–S7, SA1–SA9, R1–R4), `evaluation/confirm_data.py` (perturbations) | `test_perturbations_are_deterministic_and_bounded`, `test_fa_at_sensitivity_interpolates_first_crossing` | IMPLEMENTED, NOT RUN (S9 pending freeze) (most analyses have no dedicated unit test) |
| E-06 | Model-selection rule; interpretation matrix | C | §15, Table 20.4 | `evaluation/confirm.py` | `test_selection_h1_supported_deploys_m3`, `test_selection_point_estimate_and_logloss_rule`, `test_selection_m0_fallback_only_if_no_learned_model_beats_it`, `test_contrast_reading`, `test_interpretation_rows_are_mechanical` | **PASS** (rules; application to E NOT RUN) |
| E-07 | Calibration/τ only from inner OOF of training patients | C | §15 | `evaluation/confirm_fit.task_fit` (inner OOF; `fold isolation violated` assert), `evaluation/s6_run.py` | runtime isolation asserts only (`test_nested_fitting_isolation` does not exist) | PARTIAL (implemented; no named test; confirmatory use NOT RUN) |
| E-08 | Deployed operating point reported | REQ | §15 | `evaluation/confirm.py` (`deployed`), `evaluation/metrics.operating_point`, `reporting/confirm_view.py` | `test_confirmatory_view_only_selects_frozen_numbers`, `test_rehearsal_report_is_stamped_and_copies_numbers` (synthetic documents) | IMPLEMENTED, NOT RUN (S9 pending freeze) |
| E-09 | G4 baseline feasibility; G5 statistical interpretability | REQ | Table 21.1 | `artifacts/gates/G4.json` (D6-08); G5 in `evaluation/confirm.py` | G4: D6-08; G5: no named test | PARTIAL (G4 PASS; G5 IMPLEMENTED, NOT RUN (S9 pending freeze)) |
| E-10 | Results tables filled automatically from results.json | REQ | §22 | `reporting/confirm_report.py` (`hyposense report`) | `test_rehearsal_report_is_stamped_and_copies_numbers`, `test_official_report_banner` | IMPLEMENTED, NOT RUN (S9 pending freeze) |

## Reproducibility and engineering

| ID | Requirement | Kind | Source | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| X-01 | Provenance on every artefact/result | REQ | Table 18.1, CLAUDE.md §13 | `common/provenance.py` (used by audit, gates, features export, m0/s6/prefreeze/r4/candidate/s7/s8 runs, artefact, confirm, freeze) | audit/gate JSON provenance blocks; `test_git_dirty_ignores_generated_outputs_only` | PARTIAL (writers implemented; no test asserting provenance on every output) |
| X-02 | Python 3.11, pinned lockfile | REQ | Table 18.1 | `pyproject.toml`, `uv.lock` | `uv sync` | **PASS** |
| X-03 | Seeds as specified | C | Table 18.1, App. F | `configs/default.yaml` | `test_protocol_constants` | **PASS** (config level) |
| X-04 | Freeze: hashes recorded; confirmatory refuses without | REQ | §15, H.2 | `freeze.py` (`hyposense freeze`, `verify_freeze_record`), `evaluation/confirm.run_confirm` | `test_plan_must_be_final`, `test_awaiting_class_c_is_detected`, `test_pharmacist_review_is_mandatory_unless_reviewed_or_waived`, `test_any_failed_invariant_aborts_and_writes_nothing`, `test_confirmatory_access_still_refused_before_s9`, `test_e_unlock_refuses_anything_but_a_verified_freeze` | PARTIAL (guard PASS; freeze record not produced — BLOCKED by FZ-08 and P-C11) |
| X-05 | Offline CPU laptop; no network on demo path | REQ | Table 18.1 | `api/app.py` serving the static frontend export (ADR-007) | `test_replay_dashboard_acknowledge_audit` (in-process server, static build) | **PASS** (as D8-09; no explicit network-isolation test) |
| X-06 | Latency p95 <200 ms per reading | REC | Table 18.1 | `evaluation/s7_bench.py` (`hyposense dev s7`) | benchmark (D7-06: p99 4.5 ms) | **PASS** (MEASURED; benchmark, not a unit test) |
| X-07 | Docker image for demo | REC | Table 18.1 | `Dockerfile` | build test | PENDING |
| X-08 | Centralised scientific constants | REQ | CLAUDE.md §42 | `configs/` | constant lock | **PASS** (initial) |
| X-09 | Reproduce audit → freeze → confirm → demo by command | REQ | §23.2 | `hyposense` CLI (`cli.py`) | per-stage determinism tests (e.g. `test_audit_is_deterministic`, `test_event_audit_is_deterministic`) | PARTIAL (`data`, `partition verify`, `audit *`, `features spec`, `eval m0/registry`, `dev *`, `serve`, `freeze`, `confirm`, `report` exist; freeze/confirm/report not yet executed; no E2E reproduction test) |

## Interface and demo

| ID | Requirement | Kind | Source | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| U-01 | Ward Board (state then risk; text badges; provenance) | REQ | Table 17.1 | `frontend/src/app/page.tsx`, `frontend/src/components/ward/*`, `frontend/src/lib/states.ts` | `test_replay_dashboard_acknowledge_audit` (E2E); Vitest `ui.test.tsx` ("shows bed states while connected", "quality badges and info tags use readable text") | **PASS** |
| U-02 | Patient Review (state, p, 6-h CGM + doses, exposure, quality, factors, ack) | REQ | Table 17.1 | `frontend/src/app/patient/*`, `frontend/src/components/patient/*` | `test_replay_dashboard_acknowledge_audit` (E2E), `test_s8_ward_and_patient_fields`; Vitest ("acknowledgement offers exactly four reasons and needs an explicit choice", "breaks the CGM line at gaps > 20 min and never interpolates") | **PASS** |
| U-03 | Evidence view from results.json (curves, ladder, calibration, forest, failures, honesty, model card) | REQ | Table 17.1 | `frontend/src/app/evidence/page.tsx`, `evaluation/s8_evidence.py`, `reporting/confirm_view.py` | `test_evidence_view_from_real_artifacts`, `test_confirmatory_view_is_pending_without_an_official_run`; Vitest `confirmatory.test.tsx` | **PASS** (development evidence); confirmatory panel IMPLEMENTED, NOT RUN (S9 pending freeze) |
| U-04 | Replay deterministic, ×120, ordered | REQ | §23, G7 | `replay/session.py`, `replay/runner.py` (speed 1–3600 via `api/schemas.SpeedRequest`) | `test_replay_determinism_identical_decision_log_hash`, `test_session_log_is_deterministic_and_seek_equals_fresh_replay`, `test_same_timestamp_order_is_dose_meal_cgm_cbg` | **PASS** |
| U-05 | Seeded TP/FN/FP case selection from E OOF; cases.json | REQ | §23.1 | `evaluation/confirm._demo_cases` (results.json `demo_cases`), `api/held_out.py`, `reporting/confirm_view.py` (`scripts/select_demo_cases.py` does not exist) | `test_each_patient_is_scored_by_its_own_fold_model`, `test_presentation_access_refused_without_an_official_run` | IMPLEMENTED, NOT RUN (S9 pending freeze) (no unit test of the selection itself) |
| U-06 | Data honesty card shown first | REQ | Table 23.1 | Evidence banner + Limitations panel (`frontend/src/app/evidence/page.tsx`) | Vitest "development evidence is labelled and the sealed partition is stated" | PARTIAL (banner/limitations exist; a honesty card shown first is not verified) |
| U-07 | Synthetic content labelled SYNTHETIC; never fabricated results | REQ | CLAUDE.md §24, §31 | all (UI shows T data labelled DEVELOPMENT; evidence refused rather than invented) | `test_s8_ward_and_patient_fields` (evidence 404 for a synthetic artefact), `test_confirmatory_view_is_pending_without_an_official_run`; Vitest "shows PENDING and no numbers while E is sealed", "labels a rehearsal document as not evidence" | **PASS** |
| U-08 | Loading / error / insufficient / stale states | REQ | owner brief, CLAUDE.md §17 | `frontend/src/lib/states.ts`, `frontend/src/lib/stream.tsx`, components | Vitest `lost.test.tsx` ("hides bed states and risk when the connection is lost"), `ui.test.tsx` ("an unknown state renders as SYSTEM ERROR, never as a reassuring state", "renders backend order, states, sensor fault, stale data and no-forecast states"); `test_stale_bed_becomes_insufficient_and_is_streamed` | **PASS** (loading state not separately tested) |

## Deliverables

| ID | Requirement | Kind | Source | Status |
|---|---|---|---|---|
| V-01 | Public repo, README, licence (MIT + CC BY attribution) | REQ | §2.1, §24 | PARTIAL (README.md present; no LICENSE file in repo) |
| V-02 | Architecture document | REQ | §27 | PARTIAL (docs/ARCHITECTURE.md) |
| V-03 | Model card | REQ | §27 | IMPLEMENTED, NOT RUN (S9 pending freeze) (`reporting/confirm_report.model_card_md`; `test_rehearsal_report_is_stamped_and_copies_numbers`) |
| V-04 | Deck; video ≥20 min | REQ | §2.1 | PENDING |
| V-05 | Folder named TeamName_CollegeName | REQ | §2.1 | PENDING (names unknown) |
| V-06 | Competition registration | REQ | §2.1 | **UNKNOWN — urgent** |

## S1 additions

| ID | Requirement | Kind | Source | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| D-12 | Mirror-vs-official reconciliation of blueprint numbers | REQ | G0, README of source bundle | `audit/reconcile.py`, `audit/versions.py` | `test_reconcile_*`; 11 MATCH / 8 EXPECTED / 0 UNEXPLAINED | **PASS** |
| D-13 | No silent row deletion; explicit exclusion accounting | REQ | CLAUDE.md §10, owner S1.2 | `data/loader.py` | loader tests | **PASS** |
| D-14 | Aggregate-only outputs for E before freeze | C (P-C5) | owner S1, P-C5 | `audit/structural.py` PER_RECORDING_FIELDS | `test_per_recording_output_is_structural_only` | **PASS** |
| D-15 | Published count source verified | REQ | G0 | `configs/dataset.yaml` published block | nature.com table (VERIFIED 2026-10-18) | **PASS** |

## S2 additions

| ID | Requirement | Kind | Source | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| L-11 | Policy decision time vs label-eligible time kept distinct | C (P-C3) | ANALYSIS_PLAN §0, §2 | `labels/eligibility.py` docstring; policy S7 | design review | **PASS** (labels side) |
| L-12 | Current low (LOW NOW, incl. floor) never a forecasting target | C (P-C1) | owner S2.10 | `labels/eligibility.py` LOW_CGM rule | E06 fixture; `test_label_invariants` | **PASS** |
| L-13 | Legacy blueprint event numbers reproduced on pre-v5 content | REQ | owner S2.6 | `audit/event_run.py` | `test_legacy_blueprint_event_numbers_reproduce_exactly_on_v2` (48/48) | **PASS** |
| L-14 | P-C7 warm-up restart hook without rewriting labels | REQ | owner S2.11 | `LabelConfig.warmup_restart_after_gap_s` | E10/E10b fixtures | **PASS** (hook off) |
| L-15 | Episode annotations for SA2/SA4/SA5 (+ SA9 candidate) | REQ | Table 20.3 | `labels/annotations.py`, `labels/validity.py` | unit tests; v2 counts exact (115/69/9/65/11) | **PASS** |
| L-16 | Event audit reproducible | REQ | owner S2.12 | `hyposense audit events` | two runs identical results_sha256; `test_event_audit_is_deterministic` | **PASS** |

## S3 additions

| ID | Requirement | Kind | Source | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| M-14 | Complete raw medication inventory (machine-readable) | REQ | owner S3.1 | `audit/medication.inventory` → medication_inventory.json | real-data run | **PASS** |
| M-15 | Content-aware i.v. column (fluids ≠ insulin) | REQ | owner S3.5C | `parse._parse_iv` | `test_iv_column_is_content_aware` | **PASS** |
| M-16 | Pump suspension and misplaced entries classified by content | REQ | owner S3.5A/B | `parse.parse_text` | `test_csii_cells` | **PASS** |
| M-17 | i.v. glucose investigation and decision | REQ | owner S3.6 | `audit/medication` iv_glucose | ADR-028 (FLAG ONLY) | **PASS** |
| M-18 | M3r and M3 representation contracts | REQ | owner S3.12 | `timing.raw_timing`, `ExposureEngine.compute`; docs/FEATURE_DICTIONARY.md | unit tests; representation QA (T); assembled by the S4 feature builder (G7/G8) | **PASS** |
| M-19 | G2 re-check with the production treated definition | REQ | owner S3.7 | `med_run.py` | artifacts/gates/G2.json (PASS, unchanged 154/30) | **PASS** |
| S-03 | P-C8a sensor-failure flag (never alters labels) | C (approved) | ANALYSIS_PLAN §0c | `data.quality.sensor_fault_suspected`; `labels.annotations.floor_runs` | `test_sensor_fault_suspected_is_causal_and_needs_8_readings`, `test_floor_runs_require_8_consecutive_readings` | **PASS** |
| S-04 | P-C8b keep LOW NOW + SENSOR FAULT warning | C (approved) | ANALYSIS_PLAN §0c | `policy/decide.py` | `test_low_now_with_sensor_fault_is_distinguishable_p_c8b` | **PASS** |
| S-05 | P-C8c SA9 sensitivity analysis | C (approved) | ANALYSIS_PLAN §0c | `evaluation/confirm.py` (SA9_sensor_floor via `labels.annotations` floor runs) | `test_floor_runs_require_8_consecutive_readings` (annotation only) | IMPLEMENTED, NOT RUN (S9 pending freeze) |

## S4 additions

| ID | Requirement | Kind | Source | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| S-06 | Recording boundaries: state never crosses recordings; order by time, not number | REQ | ANALYSIS_PLAN §0.10; owner S4.4 | `state/patient.py` RecordingBoundaryError; `stream.order_recordings` | `test_recording_boundary_is_enforced`, `test_meal_unknown_markers_and_recording_order` | **PASS** |
| S-07 | Causal episode tracker = label rule with confirmation lag | REQ | ARCHITECTURE §4.4 | `state/cgm.EpisodeTracker` | differential tests (400 Hypothesis + 22 fixtures); real T 33,464 readings, 0 mismatches | **PASS** |
| S-08 | P-C8a flag and sufficiency in state; P-C7 policy-only warm-up restart (> 120 min) | C (approved) | ANALYSIS_PLAN §0c; P-C7 | `state/quality.py` (authoritative `data.quality` functions) | `test_quality_state_equals_authoritative_flag_functions` | **PASS** (P-C7 approved: `test_prefreeze_final` boundary/restart/LOW NOW/parity tests) |
| F-06 | Future perturbation leaves features at t unchanged | REQ | owner S4.15 | — | `test_future_perturbation_never_changes_the_present`; real T 1,200 checks, 0 mismatches | **PASS** |
| F-07 | Offline vs replay parity (one implementation) | REQ | ADR-004; owner S4.16 | `features/build.py` = replay of `PatientState.update` + `FeatureBuilder.union` | `test_offline_table_equals_event_by_event_replay_snapshots`; real T 133,856, 0 mismatches | **PASS** |
| F-08 | Features ignore forecast state and ledger | REQ | Table H.2 | `features/snapshot.FeatureInputs` | `test_features_ignore_forecast_state_and_ledger`, `test_feature_package_cannot_reach_the_ledger_or_labels` | **PASS** |
| F-09 | No E features before freeze | C (P-C5) | ADR-011 | `features/build.tuning_streams` scope guard; `data.dataset.assert_not_sealed` in the adapter | `test_feature_generation_refuses_sealed_scope`, `test_adapter_refuses_sealed_patients_before_freeze` | **PASS** |
| F-10 | Feature provenance: data, spec, config, dictionary, kernel hashes + commit | REQ | CLAUDE.md §13; owner S4.12 | `features/export.provenance` | audit run provenance blocks | **PASS** |
| F-11 | Tuning-set feature audit (distributions, redundancy, sanity) | REQ | owner S4.17–19 | `audit/features.py` | runs T-AGG-audit-features-20261018T1215*/T1225* | **PASS** |
| F-12 | M0 trend rule = executable spec | C-clarification | ANALYSIS_PLAN §0d | `features/cgm.ls_slope`, `trend_slope` | `test_m0_projection_is_the_executable_spec`, `test_ls_slope_matches_numpy_polyfit` | **PASS** (M0 model S5) |

## S5 additions

| ID | Requirement | Kind | Source | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| E5-01 | Model-agnostic evaluation input; M0 through the same harness | REQ | owner S5.1 | `evaluation/data.py` (EvalRecording) | unit + integration tests | **PASS** |
| E5-02 | Policy-replay notifications, cooldown, TRUE/FALSE/OUTCOME-UNKNOWN | C (P-C3) | ANALYSIS_PLAN §2 | `evaluation/metrics.py`, `policy/decide.py` | hand fixtures; stepwise-vs-vectorised Hypothesis test | **PASS** |
| E5-03 | Exact operating curve; first-crossing sens@B; τA/τW; partial area | C (P-C2, P-C6) | ANALYSIS_PLAN §3–4 | `evaluation/metrics.py` | §4 fixtures (non-monotone, budget_not_reached, k*=1, F_a=B, ties, strict); curve = direct replay (Hypothesis) | **PASS** |
| E5-04 | Paired patient-cluster bootstrap (B 2000, seed 2027, multiplicity, pairing) | REQ | Blueprint §15, Table 20.1 | `evaluation/bootstrap.py` | determinism, duplicated patient, paired difference, known CI, own-grid equivalence, mis-pairing guard | **PASS** |
| E5-05 | Canonical metric registry | REQ | owner S5 rule | `evaluation/registry.py` → `artifacts/evaluation/metric_registry.json` | drift test | **PASS** |
| E5-06 | Table A.2 reproduction (hard check) | REQ | owner S5.5/S5.24 | `evaluation/m0_run.py` | 7 MATCH + 1 EXPECTED (θ = 45, exact ties); integration test | **PASS** (θ = 45 residual partly HYPOTHESIS) |
| E5-07 | Official v5 T M0 development result with provenance | REQ | owner S5.6/S5.20 | `hyposense eval m0` | runs T-AGG-eval-m0-20261018T1406*/1407* identical | **PASS** |
| E5-08 | Window-level and calibration metrics for probabilistic models only | REQ | Table 20.2 | `metrics.window_metrics`, `calibration` | hand fixtures; probability guard | **PASS** (first use S6) |
| E5-09 | G4 baseline feasibility | Gate | Table 21.1 | `artifacts/gates/G4.json` | see D6-08 | **PASS** (evaluated in S6) |
| E5-10 | Exact ties in trend scores | REQ | ANALYSIS_PLAN §3.4, §0d | `features/cgm.ls_slope_exact` (ADR-036) | exact-tie tests; S4 audit re-run 0 mismatches | **PASS** |

## S6 additions

| ID | Requirement | Kind | Source | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| D6-01 | LightGBM, binary log-loss, no re-weighting, deterministic, shared hyperparameters | B | §11.1 | `models/lgbm.py` | determinism and class-weighting tests | **PASS** |
| D6-02 | M1 tuning: ≤ 30 Optuna trials, inner grouped CV, log-loss; P-B2 rounds | B | §11.1; P-B2 | `evaluation/s6_run.tune_m1` | trials.csv (30 trials kept) | **PASS** |
| D6-03 | Nested calibration on inner OOF; P-B1 benchmark | B | §11.1; P-B1 | `calibration/methods.py`, `s6_run.task_outer` | isolation asserts; calibrator tests | **PASS** (isotonic_interp) |
| D6-04 | Patient-grouped folds; no fold leakage | C | §10.3 | `evaluation/folds.py` | fold tests; fail-fast isolation asserts | **PASS** |
| D6-05 | Development ladder M0–M3 through the S5 harness, paired bootstrap | REQ | §15, §19 | `s6_run.evaluate` | runs T-AGG-dev-s6-20261018T1444*/1500* identical | **PASS** |
| D6-06 | Pre-registered experiments P-B1/B6/B8/B9 (P-B7 justified not run) | B | DEC-2026-10-18-G | `s6_run` | DEC-2026-10-18-H | **PASS** |
| D6-07 | Grouped TreeSHAP (descriptive) | REQ | §16.1 | `s6_run.task_outer` (pred_contrib) | results.json | **PASS** |
| D6-08 | Gate G4 | Gate | Table 21.1 | `artifacts/gates/G4.json` | 415 tests; pipeline; M1 curve | **PASS** |

## S7 additions

| ID | Requirement | Kind | Source | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| D7-01 | One policy implementation for live and offline | REQ | CLAUDE.md §19; ANALYSIS_PLAN §2 | `policy/decide.py` | parity 33,464 readings, 0 mismatches | **PASS** |
| D7-02 | Strict artefact loader; refuse on mismatch | REQ | §18 Table 18.1; ADR-009 | `models/artifact.py` | `test_artifact` (hash, missing, compatibility, corrupt, level, thresholds, pin) | **PASS** |
| D7-03 | Deterministic replay; identical decision-log hash | REQ | Table 18.1 | `replay/session.py` | `test_replay_determinism…`; bench | **PASS** |
| D7-04 | Error recovery without state poisoning; no stale prediction | REQ | §14.2; CLAUDE.md §29 | `replay/runner.py` | unit injections; bench 30 injections, 0 changed | **PASS** |
| D7-05 | 14-day replay at ×600 without exceptions or memory growth | REQ | App. test_long_run | integration + bench | 13.94 days | **PASS** |
| D7-06 | Latency < 200 ms per reading on a laptop CPU | REQ | Table 18.1 | — | p99 4.5 ms | **PASS** |
| D7-07 | API contract, bounded inputs, no stack traces, offline | REQ | §17, ADR-008 | `api/` | `test_replay_api` | **PASS** |
| D7-08 | E sealed in S7 (T catalogue only) | C | §12 | `tuning_streams`, `assert_not_sealed` | catalogue test | **PASS** |

## S8 additions

| ID | Requirement | Kind | Source | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| D8-01 | Ward board, Patient review, Evidence view | REQ | §17; CLAUDE.md §24 | `frontend/src/app/*` | screenshots; E2E | **PASS** |
| D8-02 | State never colour alone | REQ | §16.2 | `lib/states.ts`, `StatePill` | Vitest (every state) | **PASS** |
| D8-03 | No scientific logic in the browser | REQ | CLAUDE.md §26 | backend display fields | review F5 (fixed); code review | **PASS** |
| D8-04 | Never show a stale prediction as current | REQ | CLAUDE.md §29 | `policy.current`; lost-connection hiding | Vitest `lost.test.tsx`; integration stale-bed test | **PASS** |
| D8-05 | Acknowledgement: 4 codes, deliberate, audited | REQ | §16.4 | `AckPanel` | Vitest; E2E → acks.jsonl | **PASS** |
| D8-06 | DEVELOPMENT vs confirmatory honesty | REQ | CLAUDE.md §31 | Evidence banner, shell status | Vitest; review | **PASS** |
| D8-07 | Prohibited wording (no "safe", no dose advice) | REQ | §16.3 | UI strings | Vitest scan (with controls) | **PASS** |
| D8-08 | Accessibility baseline (WCAG AA) | REQ | S8 brief | tokens, roles, skip link | axe audit, 0 violations | **PASS** |
| D8-09 | Offline single-process demo | REQ | ADR-007 | static export served by FastAPI | walkthrough; E2E | **PASS** |
| D8-10 | All six states visible on a T replay | Accept | IMPLEMENTATION_PLAN S8 | — | 5 of 6 occur naturally; SYSTEM ERROR only under injected faults (S7) | **PASS (qualified)** |

## Pre-freeze Class B additions

| ID | Requirement | Kind | Source | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| PF-01 | Decision rules written before results | Protocol | CLAUDE.md §35; brief | PROPOSALS (6b1ad05) | git order; review | **PASS** |
| PF-02 | Calibrators compared on identical OOF/folds/models | REQ | brief | `prefreeze.task_fit` | review; R0 | **PASS** |
| PF-03 | Canonical config reproduces S6 bitwise | REQ | CLAUDE.md §14 | integrity gate | `T-AGG-dev-prefreeze-20261019T032309Z` | **PASS** |
| PF-04 | Fixed seed grid, no cherry-picking | REQ | brief | `FOLD_SEEDS`, `MODEL_SEEDS` | unit test; review | **PASS** |
| PF-05 | LOW_CONFIDENCE evaluated out-of-fold, no leakage | REQ | CLAUDE.md §11 | `prefreeze._tags` | review | **PASS** |
| PF-06 | E sealed | C | §12 | `load_dev` (TUNING_ONLY) | review | **PASS** |

## Pre-freeze resolution and freeze

| ID | Requirement | Kind | Source | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| FZ-01 | Canonical floored calibrator enforced | C (approved) | ANALYSIS_PLAN §5.4 item 12 | `models/artifact.py` loader check | `test_non_canonical_calibrator_is_refused` | **PASS** |
| FZ-02 | Full-precision hyperparameters | REQ | CLAUDE.md §13 | `s7_artifact.frozen_params` | integrity gate (S6 OOF bitwise) | **PASS** |
| FZ-03 | P-C7 policy-only warm-up restart | C (approved) | §5.4 item 16 | `state/patient.py`, `state/quality.py` | 6 tests incl. offline/live parity | **PASS** |
| FZ-04 | P-C10 keep state + INPUT REJECTED | C (approved) | §5.4 item 17 | `replay/runner.py`, `api/service.py` | 7 tests incl. circuit breaker | **PASS** |
| FZ-05 | LOW_CONFIDENCE removed from the live product | B (approved) | DEC-2026-10-19-M | runner, API, UI | API/UI checks; tests | **PASS** |
| FZ-06 | Reproducible freeze candidate | REQ | CLAUDE.md §14 | `hyposense dev candidate` | `T-AGG-candidate-20261019T045108Z` = `T-AGG-candidate-20261019T045338Z` | **PASS** |
| FZ-07 | Freeze fails closed | REQ | brief | `hyposense freeze` | `test_freeze_guard` | **PASS** |
| FZ-08 | Pharmacist review before freeze | C | Blueprint §12.3 | packet | human review | **BLOCKED (PENDING)** |
