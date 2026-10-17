# Event audit — ALL-AGG-audit-events-20261017T221208Z

- results_sha256: `2f92a0c993224cb24b59bce6f09e1b9e414f89406c8327ca567558e3d091c7ee`
- git: `32f3245780f5fee9461b37ddbd805819d65efff9` (dirty: False)
- label_config_sha256: `92e24a777897ab727c410433f5c218bf45b9819d322d940678084918e7284f7f`
- manifest files_sha256: `5f9d65b4e9233d4ecdd05438e80bb94314290cd5e2d9fdd21e353487cd3cc4ab`
- access scope: aggregate_audit (aggregate-only)

## Episodes (figshare v5)

| Level | Episodes | Patients with | Per affected patient q1/med/q3/max | Top-5 share | Duration q1/med/q3 (min) | End reasons |
|---|---|---|---|---|---|---|
| L1 | 348 | 61 | [2.0, 3.0, 8.0, 28] | 0.273 | [30.0, 60.0, 120.0] | {'record_end': 2, 'recovered': 346} |
| L2 | 96 | 26 | [1.0, 2.0, 3.0, 34] | 0.635 | [30.0, 75.0, 120.0] | {'record_end': 2, 'recovered': 94} |
| L1 single-reading | 430 | 67 | [1.5, 4.0, 9.5, 28] | 0.26 | [30.0, 45.0, 90.0] | {'record_end': 2, 'recovered': 428} |

## Prediction times

- readings 112462; eligible 107210 (0.9533); positive 1188 (prevalence 0.0111)
- ineligibility reasons: {'ELIGIBLE': 107210, 'INSUFFICIENT_FOLLOW_UP': 424, 'INSUFFICIENT_HISTORY': 837, 'IN_EPISODE': 20, 'LOW_CGM': 2635, 'REFRACTORY': 1336}
- per-recording eligible share min/median/max: [0.21, 0.98, 0.99]
- warnable L1 episodes: {'blueprint_definition': 306, 'legacy_definition': 306, 'warnable_share': 0.879}

## Partitions (aggregate)

{"T": {"patients": 30, "patients_with_L1": 18, "L1": 117, "treated_patients": 22, "treated_L1": 56, "treated_with_L1": 13, "treated_m_w": 6.79, "L1_concentration": {"top5_share": 0.658, "top1_share": 0.239, "m_w": 13.46}, "L2": {"episodes": 49, "patients_with": 8, "top5_share": 0.918, "top1_share": 0.694, "m_w": 24.39}, "L1_overlapping_sensor_floor_run": 6, "treated_L1_overlapping_sensor_floor_run": 1}, "E": {"patients": 70, "patients_with_L1": 43, "L1": 231, "treated_patients": 51, "treated_L1": 154, "treated_with_L1": 30, "treated_m_w": 9.23, "L1_concentration": {"top5_share": 0.346, "top1_share": 0.078, "m_w": 9.63}, "L2": {"episodes": 47, "patients_with": 18, "top5_share": 0.638, "top1_share": 0.191, "m_w": 4.83}, "L1_overlapping_sensor_floor_run": 0, "treated_L1_overlapping_sensor_floor_run": 0}}

## Label validity

{"pairs": 3269, "cgm_minus_cbg_mean": -12.5, "cgm_minus_cbg_median": -9.0, "cgm_minus_cbg_sd": 40.9, "mard_pct": 12.9, "pairs_cbg_lt100": 321, "cgm_minus_cbg_mean_cbg_lt100": 1.9, "pairs_cgm_lt70": 64, "pairs_cgm_lt70_cbg_lt70": 8, "pairs_cbg_lt70": 18, "pairs_cbg_lt70_cgm_lt70": 8, "L1_with_cbg_during": 65, "L1_cbg_during_confirmed": 11, "L1_cbg_during_contradicted": 54, "unconfirmed_share": 0.831, "legacy_onset_window": {"confirmed": 13, "no_cbg": 284, "unconfirmed": 51}}

## Annotations and sensor-floor runs

- L1 annotations: {'compression_candidates': 9, 'nocturnal_00_06': 115, 'prior_reading_lt80': 307, 'sensor_floor_run': 6, 'within_first_24h': 69}
- sensor-floor runs: {'recordings_with_run': 3, 'recordings_with_run_E': 0, 'recordings_with_run_T': 3}

## Legacy reproduction: exact matches {'v2': '48/48', 'v1': '48/48'}

| Metric | Blueprint | Measured (v5) | Status |
|---|---|---|---|
| L1_episodes | 348 | 348 | MATCH |
| L2_episodes | 96 | 96 | MATCH |
| L1_single_reading | 430 | 430 | MATCH |
| patients_with_L1 | 61 | 61 | MATCH |
| patients_with_L2 | 26 | 26 | MATCH |
| patients_with_L1_single | 67 | 67 | MATCH |
| L1_top5_counts | [28, 18, 17, 17, 15] | [28, 18, 17, 17, 15] | MATCH |
| L1_top5_patients_share | 0.273 | 0.273 | MATCH |
| L1_end_reason | {'recovered': 346, 'record_end': 2} | {'record_end': 2, 'recovered': 346} | MATCH |
| L1_duration_min_median | 60.0 | 60.0 | MATCH |
| L1_nadir_median | 60.3 | 60.3 | MATCH |
| L1_nocturnal_00_06 | 115 | 115 | MATCH |
| L1_within_first_24h | 69 | 69 | MATCH |
| L1_prior_reading_lt80 | 307 | 307 | MATCH |
| L1_warnable_h60 | 306 | 306 | MATCH |
| episodes_suspect_artefact | 9 | 9 | MATCH |
| eligible_points_h60 | 107041 | 107210 | EXPECTED DIFFERENCE |
| positive_points_h60 | 1188 | 1188 | MATCH |
| patients_insulin_or_secretagogue | 73 | 73 | MATCH |
| L1_in_insulin_or_secretagogue_recordings | 210 | 210 | MATCH |
| L1_in_insulin_recordings | 121 | 121 | MATCH |
| L1_in_secretagogue_recordings | 94 | 94 | MATCH |
| L1_in_neither | 138 | 138 | MATCH |
| T_treated | 22 | 22 | MATCH |
| E_treated | 51 | 51 | MATCH |
| T_L1 | 117 | 117 | MATCH |
| T_L1_treated | 56 | 56 | MATCH |
| T_treated_with_L1 | 13 | 13 | MATCH |
| T_treated_m_w | 6.79 | 6.79 | MATCH |
| E_L1 | 231 | 231 | MATCH |
| E_L1_treated | 154 | 154 | MATCH |
| E_treated_with_L1 | 30 | 30 | MATCH |
| E_treated_m_w | 9.23 | 9.23 | MATCH |
| treated_m_w_all | 8.58 | 8.58 | MATCH |
| cbg_cgm_pairs | 3262 | 3269 | EXPECTED DIFFERENCE |
| cgm_minus_cbg_mean | -12.5 | -12.5 | MATCH |
| cgm_minus_cbg_median | -9.0 | -9.0 | MATCH |
| mard_pct | 12.9 | 12.9 | MATCH |
| pairs_cbg_lt100 | 321 | 321 | MATCH |
| cgm_minus_cbg_mean_cbg_lt100 | 1.9 | 1.9 | MATCH |
| pairs_cgm_lt70 | 64 | 64 | MATCH |
| pairs_cgm_lt70_cbg_lt70 | 8 | 8 | MATCH |
| pairs_cbg_lt70 | 18 | 18 | MATCH |
| episodes_with_cbg_during | 65 | 65 | MATCH |
| episodes_cbg_during_lt70 | 11 | 11 | MATCH |
| L1_cbg_confirmed | 13 | 13 | MATCH |
| L1_cbg_unconfirmed | 51 | 51 | MATCH |
| L1_no_cbg_nearby | 284 | 284 | MATCH |
