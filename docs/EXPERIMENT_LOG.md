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
| T-M1-tune-001 | T | M1 | Optuna ≤30 trials, inner log-loss; num_boost_round rule (P-B2) | S6 | PENDING |
| T-calib-bench-001 | T | M1–M3 | calibration benchmark (P-B1) | S6 | PENDING |
| T-ladder-001 | T | M1–M3 | development ladder; Gate G4 | S6 | PENDING |
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
