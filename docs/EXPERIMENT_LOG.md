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
| ALL-AGG-audit-meds-001 | ALL-AGG | — | G3 medication audit | S3 | PENDING |
| T-M0-001 | T | M0 | exploratory operating curve (compare Table A.2) | S5 | PENDING |
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
