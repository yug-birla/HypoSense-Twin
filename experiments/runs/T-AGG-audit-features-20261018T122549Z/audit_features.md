# S4 feature audit — T-AGG-audit-features-20261018T122549Z

Scope: TUNING partition only (aggregate statistics; no row-level values).

- results_sha256: `db39f39a28cc93a09a0621e05f5f7626f912369bae56605c466a416e08fdcde4`
- table_sha256: `a5b6ac939c8b956ed161b37fa54aa833046b9d29e16fff8128731c25f5ce806b` (two builds identical: True)
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
- phase_wall_seconds: {'build_a': 22.7, 'build_b': 10.9, 'parity': 49.5, 'truncation': 483.0, 'perturbation': 23.5, 'statistics': 3.5}
- total_wall_seconds: 604.2
- build_wall_seconds: 22.7
- truncation_wall_seconds: 483.0
- update_us_per_event: 406.1
- features_ms_per_reading: 3.792
- combined_ms_per_reading: 4.248
- events: 37570
- longest_recording_events: 1539
- replay_peak_traced_memory_mb: 0.1
- table_memory_mb: 32.7
