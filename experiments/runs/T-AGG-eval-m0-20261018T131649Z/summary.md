# M0 evaluation (S5) — EXPLORATORY / DEVELOPMENT (tuning partition only; not confirmatory)

## Legacy Table A.2 reproduction (v2, label-eligible decision times)

| θ | status | warned T-treated ref/meas | FA/day treated ref/meas | lead ref/meas | warned all ref/meas | FA/day all ref/meas |
|---|---|---|---|---|---|---|
| 40 | MATCH | 24/24 | 0.6/0.6 | 30/30.0 | 58/58 | 0.65/0.65 |
| 45 | UNEXPLAINED DIFFERENCE | 27/27 | 0.73/0.71 | 30/30.0 | 63/62 | 0.79/0.77 |
| 50 | MATCH | 31/31 | 0.85/0.85 | 30/30.0 | 68/68 | 0.92/0.92 |
| 55 | MATCH | 36/36 | 1.07/1.07 | 45/45.0 | 77/77 | 1.15/1.15 |
| 60 | MATCH | 43/43 | 1.37/1.37 | 45/45.0 | 90/90 | 1.46/1.46 |
| 65 | MATCH | 48/48 | 1.84/1.84 | 45/45.0 | 100/100 | 1.93/1.93 |
| 70 | MATCH | 51/51 | 2.22/2.22 | 45/45.0 | 103/103 | 2.31/2.31 |
| 80 | MATCH | 53/53 | 3.65/3.65 | 60/60.0 | 105/105 | 3.73/3.73 |

## Official v5 TUNING, protocol semantics (DEVELOPMENT; not confirmatory)

| θ | sens treated | FA/day treated | precision treated | unknown | sens all | FA/day all |
|---|---|---|---|---|---|---|
| 40 | 0.428571 | 0.59603 | 0.136364 | 1 | 0.495726 | 0.648862 |
| 45 | 0.482143 | 0.713667 | 0.129187 | 2 | 0.529915 | 0.766576 |
| 50 | 0.553571 | 0.850911 | 0.125 | 2 | 0.581197 | 0.918743 |
| 55 | 0.642857 | 1.070501 | 0.116505 | 2 | 0.65812 | 1.148428 |
| 60 | 0.767857 | 1.372437 | 0.107143 | 3 | 0.769231 | 1.464246 |
| 65 | 0.857143 | 1.835144 | 0.085938 | 3 | 0.854701 | 1.926489 |
| 70 | 0.910714 | 2.219427 | 0.078176 | 3 | 0.880342 | 2.308341 |
| 80 | 0.946429 | 3.654603 | 0.052846 | 5 | 0.897436 | 3.732392 |

## sens@1FA (first crossing) with patient-cluster bootstrap

- treated: sens@1FA 0.625959 (95% CI [0.490867, 0.836835]), θA 54.0 mg/dL, partial area 0.69141 (CI [0.558065, 0.836504]), non-monotone FA steps 0
- all: sens@1FA 0.609552 (95% CI [0.418486, 0.810461]), θA 52.2 mg/dL, partial area 0.680917 (CI [0.491415, 0.830259]), non-monotone FA steps 0
