# Pre-freeze Class B (DEVELOPMENT, T) — T-AGG-dev-s6-20261018T144427Z

## P-B10 calibration (M1, canonical)

| Calibrator | LL_u | LL | Brier | ECE | slope | exact 0 | sens@1FA | area |
|---|---|---|---|---|---|---|---|---|
| raw | 0.03043 | 0.03043 | 0.00736 | 0.00144 | 0.989 | 0 | 0.8929 | 0.8917 |
| isotonic | 0.03089 | 0.03089 | 0.00751 | 0.00218 | 0.964 | 6718 | 0.8718 | 0.8888 |
| platt | 0.03079 | 0.03079 | 0.00741 | 0.00197 | 1.009 | 0 | 0.8571 | 0.8882 |
| isotonic_interp | 0.03073 | 0.03073 | 0.00746 | 0.00248 | 0.954 | 4700 | 0.8571 | 0.8921 |
| isotonic_interp_floored | 0.03074 | 0.03074 | 0.00746 | 0.00250 | 0.959 | 0 | 0.8571 | 0.8921 |

R0 integrity: True · canonical outcome: NO MATERIAL DIFFERENCE · R3 agreement 11/15 · **decision: NO MATERIAL DIFFERENCE**

## P-B11 stability (isotonic_interp, treated)

| Model | sens@1FA mean ± SD [min, max] | area mean ± SD | log-loss mean ± SD |
|---|---|---|---|
| M1 | 0.864 ± 0.039 [0.804, 0.911] | 0.886 ± 0.013 | 0.0321 ± 0.0030 |
| M2 | 0.873 ± 0.034 [0.804, 0.929] | 0.887 ± 0.017 | 0.0310 ± 0.0008 |
| M3r | 0.879 ± 0.042 [0.804, 0.929] | 0.886 ± 0.022 | 0.0310 ± 0.0007 |
| M3 | 0.907 ± 0.018 [0.875, 0.929] | 0.901 ± 0.011 | 0.0305 ± 0.0009 |
| M3_compact | 0.907 ± 0.025 [0.857, 0.929] | 0.903 ± 0.012 | 0.0304 ± 0.0006 |

| Contrast | first better / second better / ties (of 15) | median Δ | range | reading |
|---|---|---|---|---|
| M2-M1:sens_at_1fa | 7 / 3 / 5 | +0.0000 | [-0.0357, +0.0357] | leaning |
| M2-M1:partial_area | 7 / 8 / 0 | -0.0035 | [-0.0173, +0.0270] | unstable |
| M2-M1:log_loss | 8 / 7 / 0 | -0.0002 | [-0.0090, +0.0030] | unstable |
| M3r-M2:sens_at_1fa | 7 / 3 / 5 | +0.0000 | [-0.0357, +0.0536] | leaning |
| M3r-M2:partial_area | 8 / 7 / 0 | +0.0003 | [-0.0218, +0.0149] | unstable |
| M3r-M2:log_loss | 6 / 9 / 0 | +0.0004 | [-0.0026, +0.0016] | unstable |
| M3-M3r:sens_at_1fa | 11 / 2 / 2 | +0.0357 | [-0.0179, +0.0714] | leaning |
| M3-M3r:partial_area | 10 / 5 / 0 | +0.0150 | [-0.0064, +0.0468] | unstable |
| M3-M3r:log_loss | 11 / 4 / 0 | -0.0006 | [-0.0023, +0.0021] | unstable |
| M3-M2:sens_at_1fa | 12 / 0 / 3 | +0.0357 | [+0.0000, +0.0893] | leaning |
| M3-M2:partial_area | 13 / 2 / 0 | +0.0127 | [-0.0061, +0.0383] | stable |
| M3-M2:log_loss | 10 / 5 / 0 | -0.0004 | [-0.0029, +0.0013] | unstable |
| M3_compact-M3:sens_at_1fa | 5 / 3 / 7 | +0.0000 | [-0.0536, +0.0179] | leaning |
| M3_compact-M3:partial_area | 8 / 7 / 0 | +0.0045 | [-0.0104, +0.0271] | unstable |
| M3_compact-M3:log_loss | 9 / 6 / 0 | -0.0001 | [-0.0018, +0.0011] | unstable |

Rank frequency (sens@1FA, rank 1 = best): {"M1": {"4": 6, "2": 5, "3": 3, "1": 1}, "M2": {"3": 6, "1": 2, "2": 3, "4": 4}, "M3r": {"1": 3, "2": 4, "3": 3, "4": 5}, "M3": {"2": 3, "1": 9, "3": 3}}

## P-B11 stability (isotonic_interp_floored, treated)

| Model | sens@1FA mean ± SD [min, max] | area mean ± SD | log-loss mean ± SD |
|---|---|---|---|
| M1 | 0.864 ± 0.039 [0.804, 0.911] | 0.886 ± 0.013 | 0.0311 ± 0.0012 |
| M2 | 0.873 ± 0.034 [0.804, 0.929] | 0.887 ± 0.017 | 0.0307 ± 0.0003 |
| M3r | 0.879 ± 0.042 [0.804, 0.929] | 0.886 ± 0.022 | 0.0308 ± 0.0004 |
| M3 | 0.907 ± 0.018 [0.875, 0.929] | 0.901 ± 0.011 | 0.0302 ± 0.0004 |
| M3_compact | 0.907 ± 0.025 [0.857, 0.929] | 0.903 ± 0.012 | 0.0301 ± 0.0003 |

| Contrast | first better / second better / ties (of 15) | median Δ | range | reading |
|---|---|---|---|---|
| M2-M1:sens_at_1fa | 7 / 3 / 5 | +0.0000 | [-0.0357, +0.0357] | leaning |
| M2-M1:partial_area | 7 / 8 / 0 | -0.0035 | [-0.0173, +0.0270] | unstable |
| M2-M1:log_loss | 8 / 7 / 0 | -0.0002 | [-0.0028, +0.0011] | unstable |
| M3r-M2:sens_at_1fa | 7 / 3 / 5 | +0.0000 | [-0.0357, +0.0536] | leaning |
| M3r-M2:partial_area | 8 / 7 / 0 | +0.0003 | [-0.0218, +0.0149] | unstable |
| M3r-M2:log_loss | 6 / 9 / 0 | +0.0003 | [-0.0010, +0.0007] | unstable |
| M3-M3r:sens_at_1fa | 11 / 2 / 2 | +0.0357 | [-0.0179, +0.0714] | leaning |
| M3-M3r:partial_area | 10 / 5 / 0 | +0.0150 | [-0.0064, +0.0468] | unstable |
| M3-M3r:log_loss | 12 / 3 / 0 | -0.0006 | [-0.0013, +0.0001] | leaning |
| M3-M2:sens_at_1fa | 12 / 0 / 3 | +0.0357 | [+0.0000, +0.0893] | leaning |
| M3-M2:partial_area | 13 / 2 / 0 | +0.0127 | [-0.0061, +0.0383] | stable |
| M3-M2:log_loss | 13 / 2 / 0 | -0.0005 | [-0.0010, +0.0003] | stable |
| M3_compact-M3:sens_at_1fa | 5 / 3 / 7 | +0.0000 | [-0.0536, +0.0179] | leaning |
| M3_compact-M3:partial_area | 8 / 7 / 0 | +0.0045 | [-0.0104, +0.0271] | unstable |
| M3_compact-M3:log_loss | 10 / 5 / 0 | -0.0001 | [-0.0006, +0.0005] | unstable |

Rank frequency (sens@1FA, rank 1 = best): {"M1": {"4": 6, "2": 5, "3": 3, "1": 1}, "M2": {"3": 6, "1": 2, "2": 3, "4": 4}, "M3r": {"1": 3, "2": 4, "3": 3, "4": 5}, "M3": {"2": 3, "1": 9, "3": 3}}

## P-B12 LOW_CONFIDENCE (M3, isotonic_interp)

| Candidate | rate | patients | BSS tagged | BSS untagged | separation [95% CI] | +configs | criteria |
|---|---|---|---|---|---|---|---|
| C0_current | 57.411% | 100% | 0.201 | 0.105 | -0.097 [-0.198, +0.042] | 0/15 | {'a_rate': False, 'b_separation': False, 'c_stability': False} |
| C1_key_inputs | 26.569% | 100% | 0.285 | 0.111 | -0.175 [-0.274, -0.079] | 0/15 | {'a_rate': False, 'b_separation': False, 'c_stability': False} |
| C2_wider_range | 45.075% | 100% | 0.181 | 0.173 | -0.008 [-0.108, +0.145] | 5/15 | {'a_rate': False, 'b_separation': False, 'c_stability': False} |

**Decision: REMOVE TAG**

