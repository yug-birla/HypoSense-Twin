# S4 feature audit — T-AGG-audit-features-20261018T133142Z

Scope: TUNING partition only (aggregate statistics; no row-level values).

- results_sha256: `a66c8bd18c2582fb6adada646ad17a4ce494ae6fd8f3b486561acc003d334e79`
- table_sha256: `acb1be1f3fbb53016cd3ac6d0b823cb2cb214bf6bdb0c427c957c79bc4e36004` (two builds identical: True)
- recordings 34, patients 30, readings 33464, label-eligible 31292 (positive 403), L1 episodes 117
- level sizes: {'M1': 38, 'M2': 72, 'M3r': 95, 'M3': 100}

## Causality
- truncation equality: 31292 comparisons, 0 mismatches
- offline vs replay parity: 133856 snapshot comparisons, 0 mismatches
- future perturbation: future_cgm 0/300, future_medication 0/300, future_meal 0/300, future_outcome 0/300
- causal tracker vs label builder: {'readings': 33464, 'mismatches': 0}

## Flags (label-eligible T rows)
- constant: ['cgm_slope60_missing', 'rx_glinide', 'rx_sglt2', 'age_y_missing', 'sex_male_missing', 'bmi_missing', 'weight_kg_missing', 'diabetes_duration_y_missing', 'rx_missing', 'su_last_dose', 'glinide_min_since_last', 'glinide_last_dose', 'glinide_dose_24h', 'glinide_n_24h', 'glinide_missing', 'act_glinide', 'glinide_p30', 'glinide_p60', 'min_since_glinide', 'quality_glinide', 'min_since_glinide_missing']
- near_constant: ['cgm_lag15_missing', 'cgm_lag30_missing', 'cgm_lag45_missing', 'cgm_lag60_missing', 'cgm_slope30_missing', 'rx_glp1', 'meal_none_logged', 'iv_insulin_recent']
- mostly_missing: ['glinide_min_since_last', 'glinide_last_dose', 'min_since_glinide']
- required_violation: []
- impossible_values: []
- no_within_patient_variation: ['age_y', 'sex_male', 'rx_short_rapid', 'rx_glp1', 'rx_tzd', 'hba1c_mmol_mol_missing', 'egfr_missing', 'c_peptide_fasting_nmol_l_missing']
- smell_auc: []

## Redundancy
- named pairs: {'insulin_p60~act_insulin_total': 0.987, 'insulin_p30~act_insulin_total': 0.993, 'su_p60~act_su': 0.999, 'act_insulin_total~insulin_bolus_dose_24h': 0.86, 'act_su~su_min_since_last': -0.606, 'cgm_m0_proj60~cgm_slope30': 0.557, 'act_insulin_total~act_insulin_total_per_kg': 0.996}
- |rho| >= 0.95 pairs: 41; identical columns: 0

## Performance
- workers: 15
- power_throttling_disabled: True
- phase_wall_seconds: {'build_a': 9.7, 'build_b': 5.4, 'parity': 41.8, 'truncation': 335.3, 'perturbation': 17.0, 'statistics': 3.2}
- total_wall_seconds: 424.1
- build_wall_seconds: 9.7
- truncation_wall_seconds: 335.3
- update_us_per_event: 116.0
- features_ms_per_reading: 1.421
- combined_ms_per_reading: 1.551
- events: 37570
- longest_recording_events: 1539
- replay_peak_traced_memory_mb: 0.11
- table_memory_mb: 32.7
