# Experiment Log

Append-only index of experiment runs. The full provenance of each run is in
`experiments/runs/<run_id>/manifest.json` (ADR-010). **A result without provenance is not a
valid project result** (CLAUDE.md §13).

Run-ID convention: `<partition>-<model|task>-<seq>`, e.g. `T-M0-001`, `T-M1-tune-001`,
`E-confirm-001`. Partition is `T` (tuning), `E` (sealed; only after freeze), `ALL-AGG`
(aggregate audit, P-C5) or `NONE` (no data).

## Runs executed in this repository

## ALL-AGG-audit-structural-20261017T213548Z and -20261017T213615Z — S1 structural audit (official v5)
- Date (UTC): 2026-10-17 21:35–21:36 (two identical runs; determinism evidence)
- Partition / patients: ALL-AGG (approved P-C5 aggregate-only scope) / 100 patients, 109 recordings
- Git commit (clean?): `f68f98a12349d4ba26e35155abdf12ea5b867074` (clean: dirty=False)
- Dataset manifest hash (files_sha256): `5f9d65b4e9233d4ecdd05438e80bb94314290cd5e2d9fdd21e353487cd3cc4ab`
- Archive: figshare 21600933 v5, sha256 `59b5f5c4053a32bb6b7827844a0191597dc82228fe88ce332a189fdfc659c4cb`
- Config hash: recorded in each report's provenance block
- Seeds: none used (deterministic, no sampling)
- Model / feature / dictionary / kernel versions: n/a (no model)
- Package lock hash: recorded in provenance (`uv_lock_sha256`)
- Purpose: Gates G0/G1, structural audit, reconciliation against the blueprint's mirror numbers
- Pre-specified decision rule: Blueprint Table 21.1 (G0: 109 files, count reconciled or explained;
  G1: >= 99 % parse, >= 99 % intervals <= 20 min); reconciliation statuses by the mechanical rule in
  `audit/reconcile.py` (written before the comparison was run on v5)
- Result (MEASURED): **G0 PASS, G1 PASS**; results_sha256 `09e780bdfd5ada0d360a45a3da6dbee0ccf483dc483921a3e92dc64fcc568cd3`
  in both runs. 109 recordings / 100 patients; 112,475 rows; 112,462 CGM readings; CGM parse rate
  1.0; intervals <= 20 min 0.999902; 1170.6 monitored days; reconciliation 11 MATCH, 8 EXPECTED
  DIFFERENCE, 0 UNEXPLAINED.
- Interpretation: the official v5 copy is structurally sound; every difference from the blueprint's
  mirror numbers is attributable to the publisher's documented v5 update (2003_0, 2029_0).
- Decision: proceed to S2 (labels) on v5.
- Artefacts: `experiments/runs/ALL-AGG-audit-structural-20261017T2135*/audit_structural.{json,md}`,
  `artifacts/gates/G0.json`, `artifacts/gates/G1.json`

## ALL-AGG-audit-events-20261017T221208Z and -20261017T221232Z — S2 labels and event audit
- Date (UTC): 2026-10-17 22:12 (two identical runs; determinism evidence)
- Partition / patients: ALL-AGG (P-C5) / 100 patients; plus legacy reproduction on figshare v1, v2
- Git commit (clean?): `32f3245780` (dirty=False)
- Dataset manifest hash: `5f9d65b4…`; partition `ccdcbce0…`; label_config_sha256 is in provenance
- Seeds: none (deterministic)
- Purpose: build canonical labels; reproduce blueprint event numbers; G2, G3b
- Pre-specified decision rules: Blueprint Table 21.1 (G2: ≥100 E-treated L1 episodes in ≥20
  patients and CI half-width ≤0.15 at ICC 0.15, p 0.65; G3b: unconfirmed share >0.5 → TRIGGERED).
  Mechanical reconciliation rule (`audit/reconcile.py`).
- Result (MEASURED): results_sha256 `2f92a0c993224cb24b59bce6f09e1b9e414f89406c8327ca567558e3d091c7ee`
  in both runs.
  - **Legacy reproduction 48/48 exact on v2 and on v1**.
  - v5: 46 MATCH, 2 EXPECTED DIFFERENCE (eligible 107,210 vs 107,041; CBG pairs 3,269 vs
    3,262; both from the documented v5 rows), 0 UNEXPLAINED.
  - v5 L1 348 / L2 96 / single 430; prediction times 107,210 (positive 1,188, prevalence
    1.11 %).
  - **G2 PASS** (provisional treated definition): 154 E-treated L1 episodes in 30 patients;
    m_w 9.23; half-width 0.113 at ICC 0.15.
  - **G3b TRIGGERED**: 54/65 episodes with a concurrent CBG were unconfirmed (0.831).
- Diagnosis: sensor artefacts in two T-untreated recordings (2075 floor-stuck 33.5 h; 2077
  systematic negative bias) hold 37 % of T's L1 episodes. Zero floor-run artefacts in E.
  → P-C8, P-B6.
- Decision: labels accepted as protocol-exact; S3 may proceed; P-C8 awaits approval.
- Artefacts: `experiments/runs/ALL-AGG-audit-events-20261017T2212*/`,
  `artifacts/gates/G2.json`, `artifacts/gates/G3b.json`

## ALL-AGG-audit-medication-20261018T095210Z and -20261018T095243Z — S3 medication audit
- Date (UTC): 2026-10-18 09:52 (two identical runs)
- Partition / patients: ALL-AGG (P-C5) for parsing, coverage and gates; TUNING only for representation QA
- Git commit (clean?): `88cdeac114` (dirty=False in both)
- Hashes: manifest `5f9d65b4…`; partition `ccdcbce0…`; drug dictionary and pharma hashes in provenance;
  treated_patients.csv `2016d3e3025b66081889e4fe64c3359c280f2be79534b57fb82e31db4050c5ef`
- Purpose: parser coverage, production treated set, G3, G2 re-check, i.v. glucose and pump
  investigations, representation QA
- Pre-specified rules: Blueprint Table 21.1 (G3: ≥ 90 % parse; ≥ 80 % treated recording-days;
  ≤ 15-min resolution; ≥ 20 treated E patients with exposure variation); G2 as in S2
- Result (MEASURED): results_sha256 `29148c8eeba8f0dfbb1f58825a1611dbe21087c2fbbc5f927f211ab001e3ac91` (both runs).
  - Parsing: 4,653 cells, 0 unparseable / ambiguous; insulin s.c. 828/828; oral 2,171/2,171.
  - Treated: 72 patients (T 22 / E 50); legacy 73, the difference being 2078 (misplaced acarbose).
  - **G3 PASS**: parse 1.0; median day coverage 1.0 (q1 0.93; 4/79 recordings < 0.8); 99.93 %
    of administrations on CGM timestamps; 50 E-treated patients with variation.
  - **G2 PASS** (unchanged: 154 / 30 / m_w 9.23).
  - i.v. glucose: 3 events (E only), rate unknown → FLAG ONLY.
  - CSII: 34 recordings; 4/1,055 pump intervals > 6 h; 21/21 early pump ends followed by s.c.
    insulin.
  - Representation QA (T, 23,651 eligible readings): insulin activity p99 3.1 IU/h, max 4.4;
    IOB max 31 IU; all 22 treated T recordings vary.
  - Redundancy: ρ(p60, current) 0.974; ρ(activity, bolus dose 24 h) 0.80.
  - Glinide channel 100 % zero in T. Cost 0.24 ms per reading.
- Decision: representation accepted for S4; P-B7/P-B8 experiments planned for S6
- Artefacts: `experiments/runs/ALL-AGG-audit-medication-20261018T0952*/` (audit_medication.json/.md,
  medication_inventory.json), `artifacts/gates/G3.json`, `artifacts/gates/G2.json` (superseding
  S2's provisional result), `artifacts/population/treated_patients.csv`

## T-AGG-audit-features (runs 1–5) — S4 state engine and feature audit (TUNING partition only)
- Date (UTC): 2026-10-18
- Partition / patients: TUNING only (34 recordings, 30 patients). The evaluation partition was not
  accessed; feature generation refuses any scope other than TUNING_ONLY, and the adapter refuses E
  patients.
- Command: `hyposense audit features --workers 15`
- Hashes: feature spec `82fc54e9…` (v1.0.0); table sha256 `a5b6ac93…`; dataset, config,
  dictionary and pharma hashes are in each run's provenance block.
- Purpose:
  - truncation equality at every label-eligible T time;
  - offline vs replay parity;
  - future perturbation;
  - causal tracker vs label builder;
  - distributions, redundancy and the medication event study;
  - performance.
- Pre-specified rules:
  - 0 mismatches required in every causality / parity check (CLAUDE.md §11);
  - REQUIRED features finite at every eligible row;
  - univariate AUC ≥ 0.95 (or ≤ 0.05) treated as a leakage smell.

| Run | Commit (clean?) | Wall-clock | results_sha256 | Note |
|---|---|---|---|---|
| …20261018T110633Z (run 1) | bd813d1 (**dirty**: docs edited during the run) | 7.1 min | `919eb8ee…` | **SUPERSEDED**: determinism false from the frame-hash defect (ADR-034); spec `0e87630c…` |
| …20261018T113718Z (run 2) | dcb164f (clean) | 16.1 min | `db39f39a…` | official; slow due to E-core throttling (ADR-035) |
| …20261018T115636Z (run 3) | dcb164f (clean) | 19.3 min | `db39f39a…` | official reproduction |
| …20261018T121521Z (run 4) | df90031 (clean) | 10.0 min | `db39f39a…` | after the runtime fix; phases: build 14.6 s, parity 36 s, truncation 497 s, perturbation 25 s |
| …20261018T122549Z (run 5) | df90031 (clean) | 10.1 min | `db39f39a…` | reproduction |

- **Result (MEASURED; identical in runs 2–5)**:
  - **Size**: 33,464 readings; 31,292 label-eligible rows (403 positive); 117 L1 episodes.
  - **Truncation equality**: 31,292 comparisons, 0 mismatches. The raw record is truncated and
    the full pipeline re-run.
  - **Parity**: 133,856 snapshot comparisons (4 levels × 33,464 readings), 0 mismatches.
  - **Future perturbation**: CGM, medication, meal and outcome, 300 each, 0 mismatches.
  - **Causal tracker vs label builder**: 33,464 readings, 0 mismatches.
  - **Determinism**: two builds identical.
  - **Flags**: REQUIRED violations 0; impossible values 0; smell-AUC 0 (strongest:
    `cgm_m0_proj60` 0.067, i.e. the expected trend signal).
  - **Constant on eligible T rows (21)**:
    - the glinide channel (0 glinide patients in T);
    - `rx_glinide`, `rx_sglt2`;
    - static `_missing` indicators for fields complete in T;
    - `cgm_slope60_missing`;
    - `su_last_dose`: every T SU dose is 30 mg (4 patients).
  - **Near-constant (8)**: lag/slope30 indicators (~0.01 %), `rx_glp1`, `meal_none_logged`,
    `iv_insulin_recent`.
  - **Redundancy**:
    - 41 pairs with |ρ| ≥ 0.95, 0 identical columns;
    - insulin_p30 / p60 vs current activity ρ 0.993 / 0.987; su_p60 vs act_su 0.999;
      per-kg vs total activity 0.996;
    - M3 vs M3r: act_basal ~ basal dose_24h 0.986, act_su ~ su_dose_24h 0.96, min_since_su ≡
      su_min_since_last (1.0);
    - the Δ60 terms are the least redundant: best M3r match 0.49 (insulin), 0.58 (SU).
  - **Event study** (227 s.c. boluses): insulin activity median 0.45 → 0.41 IU/h at the dose
    time (τ = 0 contributes 0), then 1.83 / 2.39 / 2.15 / 0.95 at +30 / +60 / +120 / +240 min.
    IOB rises from 2.49 to 9.99 IU at the dose. SU (75 doses): act_su rises slowly (MR tmax 9 h).
  - **Data-quality metadata**: sensor-fault-suspected rows 146. 1 eligible row has a label
    window that overlaps a sensor-floor run (SA9 / P-B6 mask).
- **Performance**:
  - live path (separate serial benchmark): 0.74 ms per reading (p99 1.79 ms);
  - audit replay peak traced memory 0.11 MB; table 32.7 MB.
- Decision: S4 causality and parity requirements met; feature set accepted as the canonical
  baseline. Redundancy findings go to P-B8 / P-B9 (S6).
- Artefacts:
  - `experiments/runs/T-AGG-audit-features-20261018T*/` (aggregate JSON and Markdown, committed);
  - `data/processed/features/v1.0.0/tuning_features.parquet` + provenance (row-level,
    git-ignored).

## T-AGG-eval-m0 (S5) — M0 through the shared evaluation harness

### Run IDs
| Run | Commit (clean?) | results_sha256 | Status |
|---|---|---|---|
| T-AGG-eval-m0-20261018T130913Z | 5c7deca + uncommitted S5 code (**dirty**) | `8d6eb3b7…` | DIAGNOSTIC, superseded: θ = 45 UNEXPLAINED before ADR-036 |
| T-AGG-eval-m0-20261018T131649Z | dirty | — | DIAGNOSTIC, superseded: after exact arithmetic, before tie classification |
| T-AGG-eval-m0-20261018T131830Z | dirty | — | DIAGNOSTIC, superseded: first tie-bracket rule (tightened after review) |
| **T-AGG-eval-m0-20261018T140638Z** | **671a7ca (clean)** | **`7864a0d0…`** | **OFFICIAL** |
| **T-AGG-eval-m0-20261018T140729Z** | **671a7ca (clean)** | **`7864a0d0…`** | **OFFICIAL reproduction (identical)** |

### Purpose
Prove the evaluation harness by reproducing Blueprint Table A.2, then measure M0 on the
official v5 TUNING partition under the approved protocol.

### Data / population
- **Legacy reproduction:** figshare v2 (mirror-equivalent), TUNING, 34 recordings / 30 patients,
  treated 22.
- **Official:** v5 TUNING, 34 recordings, 30 patients (22 treated), 33,464 readings, 31,292
  label-eligible times, 31,416 policy-queried readings.
- The T recordings are bitwise identical in v2 and v5, so there is no data-version effect on T.
- E was not accessed.

### Model / baseline
M0, no fitted parameters (ANALYSIS_PLAN §0d; strict comparator; score = −projection(t + 60)).

### Metrics
Definitions are in `artifacts/evaluation/metric_registry.json` (sha256 `cf01baeb…`):
- event L1, H = 60 min, warning window [onset − 60, onset − 15];
- cooldown 60 min, per recording;
- FA = FALSE notifications / monitored days;
- OUTCOME-UNKNOWN reported separately;
- sens@1FA by first crossing (§3.4).

### Results — legacy reproduction (label-eligible decision times)
- **θ = 40, 50, 55, 60, 65, 70, 80: MATCH.** Warned, episodes, sensitivity, FA/day and median
  lead equal the reference.
- **θ = 45: EXPECTED DIFFERENCE** (exact-tie resolution; ADR-036, DEC-2026-10-18-F).

| Quantity | Reference | Measured | Tie-inclusive |
|---|---|---|---|
| Treated warned | 27 | 27 | 28 |
| Treated FA/day | 0.73 | 0.71 | 0.76 |
| All warned | 63 | 62 | 64 |
| All FA/day | 0.79 | 0.77 | 0.81 |

- 44 exact ties.
- The polyfit replay reproduces the treated row (27, 0.73) but not the all-patients row
  (62 / 0.78). The mechanism is partly demonstrated; the residual is a HYPOTHESIS.

### Results — official v5 TUNING (DEVELOPMENT / EXPLORATORY; not confirmatory)
| Population | sens@1FA (95 % CI) | θA | Partial area 0.5–2 (CI) | Lead median (IQR) | Precision | Warnable ceiling |
|---|---|---|---|---|---|---|
| Treated (22 pts, 56 episodes) | **0.626** (0.491–0.837) | 54.0 mg/dL | 0.691 (0.558–0.837) | 45 (22.5–60) min | 0.121 | 0.946 |
| All (30 pts, 117 episodes) | **0.610** (0.418–0.810) | 52.2 mg/dL | 0.681 (0.491–0.830) | 30 (30–45) min | 0.160 | 0.906 |

### Confidence intervals
- 2,000 paired patient-cluster resamples, seed 2027, percentile 95 %, 0 undefined resamples.
- Curves have 280 / 283 grid points and 0 non-monotone FA steps.
- τW (θW) = 73.8 / 72.0 mg/dL.
- 2 OUTCOME-UNKNOWN notifications at θA; INSUFFICIENT DATA in 0.8 % of readings.
- At the Table A.2 θ the protocol values equal the label-eligible values, except for 1–5
  OUTCOME-UNKNOWN notifications at the end of a record.

### Interpretation
- The harness reproduces the blueprint's exploratory M0 exactly wherever the reference is
  determinate. The trend rule warns about ~62 % of treated-T episodes at 1 FA/day, with a median
  lead of 45 min.
- The intervals are wide (13 treated T patients have episodes).
- Precision is ~12 %: about 1 in 8 notifications is followed by an onset. This is the C0 bar
  learned models must beat.

### Limitations
- Development data (T) only.
- M0 has no probabilities, so window-level and calibration metrics are N/A, not forced.
- The θ = 45 residual is not bit-reproducible against the author's numerics.

### Comparison with previous runs
- The diagnostic runs differed only at θ = 45 (before ADR-036).
- Official runs 1 and 2 are identical.

### Provenance
Each `results.json` records:
- commit and clean flag; environment;
- config, partition, label-config, analysis-plan, metric-registry, feature-spec, reference and
  treated-population hashes;
- v5 manifest and v2 T file hashes;
- bootstrap settings.

Artefacts: `experiments/runs/T-AGG-eval-m0-20261018T1406*/{results.json, summary.md,
m0_v5_curve_*.csv}`. The per-patient table is under `data/processed/evaluation/` (git-ignored).

### Decision / next action
Harness accepted for S6. G4 is NOT YET EVALUABLE: it requires M1 on T inner CV (Table 21.1).

## T-AGG-dev-s6 (S6) — learned-model development ladder on T

### Run IDs
| Run | Commit (clean?) | results_sha256 | Status |
|---|---|---|---|
| T-AGG-dev-s6-20261018T142512Z | 877e9bf + uncommitted S6 code (**dirty**) | — | SMOKE (2 trials, 50 resamples). Raised the "too good?" check (M1 0.91 vs M0 0.63) |
| T-AGG-dev-s6-20261018T143013Z | dirty | — | SMOKE after the calibrator-order fix. Before the fix, ladder scores used canonical isotonic regardless of the P-B1 winner. After it, the P-B1 winner drives every model (M1 0.911 → 0.893 in smoke; P-B1 metrics unchanged) |
| **T-AGG-dev-s6-20261018T144427Z** | **fd34ecf (clean)** | **`e81268ae…`** | **OFFICIAL** |
| **T-AGG-dev-s6-20261018T150030Z** | **fd34ecf (clean)** | **`e81268ae…`** | **OFFICIAL reproduction (identical)** |
| T-AGG-dev-s6-20261018T153341Z | fce4c4b (clean; review F7/F8 refactor) | `e81268ae…` | VERIFICATION: refactor leaves results unchanged; adds s6_inputs sha256 |

### Purpose
Pre-registered S6 development (DEC-2026-10-18-G):
- M1 tuning;
- the M1 / M2 / M3r / M3 ladder;
- P-B1, P-B6, P-B8 and P-B9;
- G4.

### Data / population
v5 TUNING only: 30 patients (22 treated), 33,464 readings, 31,292 eligible rows (403 positive),
117 L1 episodes (56 treated). E was not accessed.

### Models
- LightGBM, binary, no class weighting, seed 2026, deterministic, 1 thread.
- Shared hyperparameters (best trial #20); num_boost_round 113.
- Calibrator: isotonic_interp (P-B1).
- Nested 5 × 4 patient-grouped folds (seed 2026).

### Results (treated T; DEVELOPMENT ONLY — not confirmatory)
| Model | sens@1FA (95 % CI) | Partial area | Log-loss | AUPRC | ECE | Slope |
|---|---|---|---|---|---|---|
| M0 | 0.626 (0.491–0.837) | 0.691 | n/a | n/a | n/a | n/a |
| M1 | 0.857 (0.719–1.000) | 0.892 | 0.0307 | 0.247 | 0.0025 | 0.95 |
| M2 | 0.875 (0.781–1.000) | 0.898 | 0.0313 | 0.233 | 0.0013 | 0.97 |
| M3r | 0.929 (0.804–1.000) | 0.911 | 0.0301 | 0.249 | 0.0015 | 1.01 |
| M3 | 0.911 (0.788–1.000) | 0.907 | 0.0309 | 0.236 | 0.0013 | 1.00 |
| M3_compact | 0.929 (0.817–1.000) | 0.918 | 0.0297 | 0.236 | 0.0011 | 1.03 |
| M1_pb6 | 0.929 (0.786–1.000) | 0.910 | 0.0303 | 0.227 | 0.0033 | 0.98 |

Patient-weighted sensitivity (treated): M0 0.61, M1 0.87, M2 0.90, M3r 0.95, M3 0.94. The
all-T table and every interval are in `ladder.md` and `results.json`.

### Paired differences (treated T, sens@1FA; 2,000 patient-cluster resamples, seed 2027)
| Comparison | Difference | 95 % CI |
|---|---|---|
| C0 M1−M0 | +0.231 | 0.094 to 0.437 |
| C1 M2−M1 | +0.018 | −0.064 to 0.089 |
| C2a M3r−M2 | +0.054 | −0.054 to 0.107 |
| C2b M3−M3r | −0.018 | −0.086 to 0.057 |
| Preview M3−M2 (NOT H1) | +0.036 | −0.042 to 0.088 |

Log-loss differences are all within ±0.0012, and every CI includes 0.

### Diagnostics
- **Tuning:** the 30 trials span CV log-loss 0.0463–0.0503; fold log-loss ranges 0.017–0.083.
  Fold composition dominates hyperparameters.
- **Overfitting:** train log-loss 0.018–0.030 vs held-out 0.013–0.083 per fold. This is patient
  heterogeneity, not a systematic train/held-out gap.
- **Grouped TreeSHAP (M3):** CGM level 0.82 > CGM history 0.76 > exposure 0.26 ≈ static 0.25 >
  trend 0.16 > time 0.10 > meal 0.04. Descriptive only.
- **Post-hoc simple rules:** "CGM < 81" gives sens@1FA 0.911 treated / 0.856 all → P-C9.
- **Runtime:**
  - tuning 40–50 s;
  - 210 ladder fits 38–40 s;
  - evaluation and bootstrap 11–14 min (~19k distinct calibrated scores per model);
  - full-T M3 fit 3.9 s;
  - single-reading prediction 0.16 ms p50 / 0.39 ms p99.

### Interpretation
- Learned models clearly beat M0 on T. But M0 is a weak reference under this endpoint, and a
  level rule matches the learned models.
- On T the M2 / M3r / M3 differences are within 1–3 episodes, against a warnable ceiling of
  0.946. The headroom for H1 on the primary endpoint is small. The window-level secondary
  (S3: log-loss) shows no separation either.
- This is development evidence only. It neither supports nor refutes H1.
- *Review (DEC-2026-10-18-I)*: model-fit variance is as large as the M2 / M3r / M3 /
  M3_compact / M1_pb6 differences, so their ordering on T is uninformative.
- The P-B1 win of isotonic_interp rests on 3 positives at a calibrated 0. Raw scores already
  match its log-loss.
- P-B6 was decided on M1 only and is not yet applied to the canonical ladder.

### Limitations
- Hyperparameters were tuned on all of T and reused in T's outer CV, so learned-model results
  are optimistic vs M0.
- 22 treated patients.
- Two artefact recordings.
- The level-rule check was post hoc.

### Decision / next action
- DEC-2026-10-18-H: tuned set and 113 rounds frozen; isotonic_interp; P-B6 adopted for training;
  P-B9 adopted; M3_compact = candidate (owner); G4 PASS.
- Owner decisions: P-C9, P-B8 compact, ANALYSIS_PLAN §5, P-C7.

## T-AGG-s7-engineering (S7) — live pipeline engineering evidence on T

| Run | Commit (clean?) | results_sha256 | Status |
|---|---|---|---|
| T-AGG-s7-engineering-20261018T161559Z | 457b770 (clean) | — | SUPERSEDED: its error-injection design tripped the circuit breaker (5 back-to-back bad events). Other sections are unchanged in the official runs |
| **T-AGG-s7-engineering-20261018T163321Z** | **9b154bf (clean)** | **`6d2517cd…`** | **OFFICIAL** |
| **T-AGG-s7-engineering-20261018T163810Z** | **9b154bf (clean)** | **`6d2517cd…`** | **OFFICIAL reproduction (identical)** |

- **Model:** `M3-development-9590a582b0c1` (DEVELOPMENT, fitted on all of T). Rebuild bitwise identical.
- **Parity:** offline vs live on 34 recordings / 33,464 readings:
  all mismatch counts 0 (probabilities bitwise).
- **Determinism:** decision-log hashes identical across replays.
- **Error injection:** 30 injected / 30 rejected / 0 later
  decisions changed.
- **Long run:** 13.94 days, retained memory flat.
- **Latency:** per reading p50 1.5 / p99 4.5 ms; API ward p50
  3.2 ms; throughput 629 events/s.
- **In-sample (not evidence):**
  - states {'ALERT': 1006, 'INSUFFICIENT_DATA': 263, 'LOW_NOW': 1785, 'NO_ALERT': 28684, 'WATCH': 1726};
  - 1.186 notifications / patient-day;
  - LOW_CONFIDENCE 16.1% of forecasts (P-B12).

## S8 — Evidence-view curves and UI audit (T, DEVELOPMENT)

| Run | Commit (clean) | results_sha256 | Status |
|---|---|---|---|
| T-AGG-dev-evidence-20261018T184314Z / 20261018T184413Z | 7b66be1 | `18cb4d0e…` (identical) | OFFICIAL: aggregate operating curves from the S6 OOF (hash-verified); sens@1FA reproduces S6 for 10/10 model × population |
| T-AGG-s8-ui-audit-20261018T184552Z / 20261018T184600Z | 9f457b5 | — | SUPERSEDED by the post-review audit |
| **T-AGG-s8-ui-audit-20261018T190216Z / 20261018T190224Z** | **25c2d88** | **`d6b44323…` (identical)** | **OFFICIAL**: axe-core 4.13 WCAG 2.0/2.1 A+AA, 0 violations on Ward / Patient / Evidence; first Tab = skip link; ready 0.24–0.45 s |

Deleted, not evidence: two runs on an uncommitted tree, and two audits against a stale server.

## Pre-freeze Class B (P-B10/P-B11/P-B12) — T, DEVELOPMENT

| Run | Commit (clean) | results_sha256 | Status |
|---|---|---|---|
| T-AGG-dev-prefreeze-20261019T023957Z | 913864e | f80c07eb… | SUPERSEDED: P-B10 metrics on treated rows instead of the P-B1 set (P-B10 NO MATERIAL DIFFERENCE, R3 11/15; P-B12 REMOVE TAG) |
| **T-AGG-dev-prefreeze-20261019T032309Z** | **e0931cf** | **`432869dc…`** | **OFFICIAL** |
| **T-AGG-dev-prefreeze-20261019T034056Z** | **e0931cf** | **`432869dc…` (identical)** | **OFFICIAL reproduction** |

- **Runs**:
  - **Official**: `T-AGG-dev-prefreeze-20261019T032309Z` and `T-AGG-dev-prefreeze-20261019T034056Z`, both on clean e0931cf. `results_sha256` `432869dc…` is identical across the two.
  - **Integrity gate**: the canonical configuration reproduces the S6 `oof_sha256` bitwise, using the full-precision hyperparameters.
  - **Superseded**: `T-AGG-dev-prefreeze-20261019T023957Z` (913864e) computed P-B10 LL_u/ECE on treated rows. The pre-specified set is the P-B1 set (all patients' pooled held-out rows, as in S6 P-B1). It was fixed in e0931cf; the protocol itself is ambiguous, since "primary population: treated" sits next to "(the P-B1 set)" (review F1).
    - In the superseded run, P-B10 was NO MATERIAL DIFFERENCE with R3 11/15.
    - With the corrected set, R3 is 4/15, so the outcome becomes INCONCLUSIVE.
    - In both runs nothing is adopted.
  - **No other runs**: no runs preceded the rule commit 6b1ad05.
- **P-B10 → INCONCLUSIVE** (pre-specified rule; current `isotonic_interp` stays).
  - **M1, canonical, P-B1 set:**
    - LL_u: current 0.04017, floored 0.04019, Platt 0.04037, raw 0.04025.
    - ECE: current 0.00060, floored 0.00060.
    - Exact 0 outputs: current 6947, floored 0.
    - sens@1FA and partial area are identical (R0 holds for all grid models).
  - **Canonical outcome**: NO MATERIAL DIFFERENCE.
  - **Across the 15 configurations**: {'NO MATERIAL DIFFERENCE': 4, 'ADOPT floored': 11}, so R3 is 4/15 → INCONCLUSIVE.
  - **Why the configurations disagree**: in 11/15 configurations the current calibrator outputs **exactly 1.0** on some held-out rows (up to 27 on M1), negatives included, and in one configuration exactly 0 on 2 positives. Its unclipped log-loss is then infinite (R1), while the floored version never reaches 0 or 1 and costs at most ~0.05 % log-loss.
  - **Weakness of R3** (review F2): R3 compares against the canonical *label*, and the canonical seed happens to be one of only 4 where the current calibrator is admissible.
  - **Rule kept**: the rule is applied as written, and the floored-calibrator question is raised for the owner.
  - **P-B6 SENSITIVITY** (M1_pb6, canonical): NO MATERIAL DIFFERENCE.
- **P-B11 (descriptive; isotonic_interp; treated; 15 configurations; only 3 independent fold partitions)**:
  - **sens@1FA, mean ± SD:**
    - M1 0.864 ± 0.039
    - M2 0.873 ± 0.034
    - M3r 0.879 ± 0.042
    - M3 0.907 ± 0.018
    - M3_compact 0.907 ± 0.025
  - **Contrasts** (first better / second better / ties):
    - M3−M2: sens 12/0/3 (median +0.0357, leaning); area 13/2/0 (median +0.0127, stable); log-loss 10/5/0 (median -0.0004, unstable).
    - M2−M1: sens 7/3/5 (median +0.0000, leaning).
    - M3r−M2: sens 7/3/5 (median +0.0000, leaning).
    - M3−M3r: sens 11/2/2 (median +0.0357, leaning).
    - M3_compact−M3: sens 5/3/7 (median +0.0000, leaning); area 8/7/0 (median +0.0045, unstable); log-loss 9/6/0 (median -0.0001, unstable).
  - **Ranking**: M3 ranked first on sens@1FA in 9/15 configurations. The calibrator choice changed the M1–M3 ranking in 0/15.
  - **Reading**: 45 readings (5 contrasts × 3 metrics) under the current calibrator; only M3−M2 partial area reaches "stable" (13/2). M3 never ranked below M2 on sens@1FA (12 better, 3 ties), but the median gain is one episode-step (+0.036).
- **P-B12 → REMOVE TAG** (pre-specified rule; M3, current calibrator, OOF ranges from training folds only):
  - C0 current: 57.4% tagged; separation -0.097 [-0.198, +0.042], 0/15 configs positive.
  - C1 key inputs: 26.6% tagged; separation -0.175 [-0.274, -0.079], 0/15 configs positive.
  - C2 0.1–99.9 %: 45.1% tagged; separation -0.008 [-0.108, +0.145], 5/15 configs positive.
  - **No candidate separates reliability**: tagged forecasts are, if anything, *more* informative (higher BSS).
  - **The S7 figure was in-sample**: "16.1 %" was measured in-sample. On held-out patients the current tag fires on ~57 %, driven by per-patient static context (BMI/age/weight) and medication exposure falling outside other patients' ranges (review F3).

Two earlier launches died without output (MemoryError, then disk full on C:); no artefacts.
Decision tables: `experiments/runs/T-AGG-dev-prefreeze-20261019T032309Z/prefreeze.md`.

## Freeze candidate (DEC-2026-10-19-M) — T, DEVELOPMENT

| Run | Commit (clean) | results_sha256 | Status |
|---|---|---|---|
| T-AGG-candidate-20261019T043127Z / 20261019T043435Z | a35085f | `c0cbe721…` (identical) | superseded only because code changed after the final review (fixes F1/F2/F7/F8); same results |
| **T-AGG-candidate-20261019T045108Z** | **a7efa25** | **`c0cbe721…`** | **OFFICIAL freeze candidate** |
| **T-AGG-candidate-20261019T045338Z** | **a7efa25** | **`c0cbe721…` (identical)** | **OFFICIAL reproduction** |
| **T-AGG-s7-engineering-20261019T050448Z** | **a7efa25** | `3a1de768…` | S7 bench on the candidate |

- **Integrity gate:** the canonical S6 configuration reproduces S6's `oof_sha256` bitwise with the
  full-precision hyperparameters.
- **Canonical model:** M3 (full; 100 features), calibrator `isotonic_interp_floored`,
  113 rounds, seed 2026.
- **Candidate artefact:** `M3-development-3271a3206765`, format 2.0.0.
  - τA 0.1230; τW 0.0251; p_lo 5.46e-05.
  - Model, calibrator and policy files are byte-identical across the four runs; the manifests
    differ only in `created_utc`.
- **Canonical T evaluation vs S6** (same fits; only the calibrator differs):

| Population | Model | sens@1FA S6 → candidate | partial area | log-loss | ECE | slope (cand.) |
|---|---|---|---|---|---|---|
| treated | M1 | 0.8571 → 0.8571 | 0.8921 → 0.8921 | 0.03073 → 0.03074 | 0.00248 → 0.00250 | 0.959 |
| treated | M2 | 0.8750 → 0.8750 | 0.8983 → 0.8983 | 0.03128 → 0.03107 | 0.00129 → 0.00222 | 1.081 |
| treated | M3r | 0.9286 → 0.9286 | 0.9109 → 0.9109 | 0.03005 → 0.03008 | 0.00155 → 0.00154 | 1.005 |
| treated | M3 | 0.9107 → 0.9107 | 0.9072 → 0.9072 | 0.03095 → 0.03022 | 0.00125 → 0.00167 | 1.071 |
| all | M1 | 0.8291 → 0.8291 | 0.8424 → 0.8424 | 0.04017 → 0.04019 | 0.00060 → 0.00060 | 0.974 |
| all | M2 | 0.8376 → 0.8376 | 0.8521 → 0.8521 | 0.04065 → 0.04046 | 0.00085 → 0.00154 | 1.043 |
| all | M3r | 0.8632 → 0.8632 | 0.8567 → 0.8567 | 0.04048 → 0.04050 | 0.00100 → 0.00100 | 0.975 |
| all | M3 | 0.8547 → 0.8547 | 0.8546 → 0.8546 | 0.04392 → 0.04087 | 0.00064 → 0.00087 | 0.979 |

- **Explained differences.**
  - **sens@1FA and partial area:** identical (monotone calibrator).
  - **Log-loss improves:** S6's unfloored calibrator gave exactly 0 to one positive for M2 and M3
    (penalised through the 1e-15 clip).
  - **ECE and slope:** the floor in outer fold 4 is 0.47 % (M2) / 0.26 % (M3), because that
    fold's lowest isotonic block is small, and it clamps ≈ 70 % of that fold's held-out rows
    (ANALYSIS_PLAN §5.4 item 12 disclosure).
  - **Δ M3−M2 (T-treated):** +0.0357 (S6 +0.0357).
- **Replay of all T** through the candidate:
  - states {'ALERT': 1006, 'INSUFFICIENT_DATA': 263, 'LOW_NOW': 1785, 'NO_ALERT': 28684, 'WATCH': 1726}, identical to S7;
  - tags {'MED_TIMING_UNKNOWN': 1197}, with no LOW_CONFIDENCE.
  - **P-C7:** 0 T gaps > 120 min, so no T decision changed.
- **S7 bench** (T-AGG-s7-engineering-20261019T050448Z):
  - offline/live parity 33,464 readings, 0 mismatches;
  - decision logs identical;
  - artefact rebuild identical and equal to the deployed bundle;
  - 30 injected bad inputs, 0 later decisions changed;
  - latency p99 4.8 ms.

## T-AGG-dev-r4-20261019T055800Z — R4 per-model tuning (T, frozen before E)
- Commit f154e63 (clean); 177 s. S6 procedure (Optuna TPE, seed 2026, same space and trials) per level.
- Result (MEASURED): M2 trial 29 / 39 rounds / inner LL 0.04674; M3r trial 0 / 131 / 0.04739;
  M3 trial 28 / 76 / 0.04659. Used only by robustness analysis R4 (ANALYSIS_PLAN §5.7 item 27).

## T-AGG-rehearsal-20261019T060915Z — S9 smoke rehearsal (DISCARDED scratch)
- Uncommitted code, bootstrap B = 20 (debug override, rehearsal only); 681 s.
- Purpose: exercise the confirmatory runner end to end. Found and fixed one bug (a wrong config
  path for the SA5 tail parameter) and diagnosed R3 (learner property, ANALYSIS_PLAN item 26).
- Not evidence and not committed (dirty code); superseded by the run below.

## T-AGG-rehearsal-20261019T070224Z — S9 full rehearsal on T (REHEARSAL, never evidence)
- Date: 2026-10-19 · commit 94a7246 (clean) · B = 2000 · 4 workers · 2,050 s (bootstrap 1,644 s).
- Purpose: run the identical confirmatory code on T before freeze (ANALYSIS_PLAN §5.7).
- Integrity checks (MEASURED):
  - T rows of the S9 table equal the S4/S6 development table.
  - The primary M2 / M3 sens@1FA (0.875 / 0.911) and all checked paired CIs equal the
    independent S6 run exactly (M3−M2 −0.0417 to 0.0877; C0 0.0944 to 0.4373;
    C2a −0.0541 to 0.1072).
  - SA7 seeds 2028/2029 equal the pre-freeze fit-variance grid.
  - The final model equals candidate 3271a320.
  - Held-out replay of every T recording with its fold model reproduces the pooled OOF
    probabilities bitwise (31,416 decisions, 0 mismatches).
- Rehearsal outputs: H1 not supported on T, and the §6 rule selects M3. These are development
  numbers and not an answer to H1.
- Report: experiments/runs/T-AGG-rehearsal-20261019T070224Z/report/ (stamped REHEARSAL).
  Row-level outputs are private in data/processed/confirm/.

## T-AGG-candidate-20261019T085805Z / T090035Z — candidate pair on intake code (T, DEVELOPMENT)
- Commit 28ac72f (clean; includes the `parse_recording_frame` loader split).
- Results `c0cbe721…` in both runs, identical to every earlier pair. The refactor changed no
  feature, model or threshold.

## Evidence inherited from the blueprint (not reproduced here)

| Item | Source | Status in this repo |
|---|---|---|
| Audit counts (Section 8, App. A) | Blueprint author's `audit.py`/`audit2.py` on a GitHub mirror (scripts found in the source bundle, ADR-016) | **Structural (S1) and all 48 event / label-validity / partition numbers (S2) REPRODUCED exactly on figshare v1/v2**; v5 differences explained. Medication-parse numbers: S3 |
| Exploratory M0 on T (Table A.2: 0.64 sens at 1.07 FA/day, θ=55) | `audit2.py` on mirror, original partition | **NOT YET REPRODUCED** — S5 target. The original partition is kept (ADR-016), and both v5-changed recordings (2003_0, 2029_0) belong to E patients, so all T data are identical to the mirror. Table A.2 should therefore reproduce **exactly** if S5's definitions match; any difference must be explained |

## Planned runs (Blueprint App. H, Table H.1)

| Run ID | Partition | Model | Purpose | Stage | Status |
|---|---|---|---|---|---|
| ALL-AGG-audit-structural-20261017T2135* | ALL-AGG | — | G0/G1 structural audit | S1 | **DONE** (G0 PASS, G1 PASS) |
| ALL-AGG-audit-events-20261017T2212* | ALL-AGG | — | G2/G3b event audit + legacy reproduction | S2 | **DONE** (G2 PASS provisional, G3b TRIGGERED, 48/48) |
| ALL-AGG-audit-medication-20261018T0952* | ALL-AGG (+T for QA) | — | G3 medication audit + G2 re-check | S3 | **DONE** (G3 PASS, G2 PASS) |
| T-AGG-audit-features-20261018T1215* / T1225* | T (+aggregate) | — | S4 state + feature audit (truncation, parity, perturbation) | S4 | **DONE** (0 mismatches; runs 2–5 identical) |
| T-AGG-audit-features-20261018T133142Z | T | — | S4 re-verification after ADR-036 | S5 | **DONE** (0 mismatches) |
| T-AGG-eval-m0-20261018T1406* / T1407* | T (+v2 T) | M0 | Table A.2 reproduction + v5 development M0 | S5 | **DONE** (7 MATCH + 1 EXPECTED; runs identical) |
| T-M1-tune-001 | T | M1 | Optuna ≤30 trials, inner log-loss; num_boost_round rule (P-B2) | S6 | **DONE** within T-AGG-dev-s6-20261018T1444* |
| T-calib-bench-001 | T | M1–M3 | calibration benchmark (P-B1) | S6 | **DONE** within T-AGG-dev-s6-20261018T1444* |
| T-ladder-001 | T | M1–M3 | development ladder; Gate G4 | S6 | **DONE** within T-AGG-dev-s6-20261018T1444* |
| T-AGG-dev-s6-20261018T1444* / T1500* | T | M1–M3 (+variants) | S6 development ladder, P-B1/6/8/9, G4 | S6 | **DONE** (identical; G4 PASS) |
| E-confirm-001 | E | M0–M3 | **confirmatory, once, after freeze** | S9 | PENDING |

## Entry template

```
## <run_id> — <title>
- Date (UTC):
- Partition / patients:
- Git commit (clean?):
- Dataset manifest hash:
- Config hash:
- Seeds:
- Model / feature / dictionary / kernel versions:
- Package lock hash:
- Hypothesis or purpose:
- Pre-specified decision rule (written BEFORE running):
- Result (MEASURED):
- Interpretation:
- Decision:
- Artefacts:
```
