# HypoSense Twin — Current Project State

_Last updated: 2026-10-18 (end of S1). This is the canonical snapshot. Read it first, then
[NEXT_STEPS.md](NEXT_STEPS.md) and [PROGRESS.md](PROGRESS.md)._

## Current Phase
**S1 — complete and reviewed.** Next: **S2** (schemas, label builder, event audit; G2/G3b). Per
the owner's instruction, S2 has **not** been started.

## Overall Status
**IMPLEMENTATION** — data foundation verified. No model work has started.

## Completed Components
| Component | Status | Files | Tests |
|---|---|---|---|
| S0 baseline (env, skeleton, control docs) | DONE | see PROGRESS 2026-10-18 (S0) | constant lock, import guard |
| Official data acquisition (figshare v5; v1/v2 for reconciliation) | DONE | `src/hyposense/data/source.py`, `configs/dataset.yaml` | `test_allowed_member_*`, `test_wrapper_*`, `test_verify_archive_*` |
| Manifest (111 files) | DONE | `data/MANIFEST.json`, `data/MANIFEST.sha256`, `data/manifest.py` | `test_manifest_*` |
| Production loader + summary loader | DONE | `data/loader.py`, `columns.py`, `records.py`, `summary.py` | 16 loader + 15 identity/schema tests |
| CGM quality flags | DONE | `data/quality.py` | `test_cgm_quality_flags` |
| Scoped dataset access (sealed-partition safeguard) | DONE | `data/dataset.py` | integration + static confinement tests |
| Official T/E partition (original, verified, hash-locked) | DONE | `configs/partition.csv`, `partition.provenance.json`, `data/partition.py` | `test_partition.py` (6) |
| Structural audit + version/blueprint reconciliation | DONE | `src/hyposense/audit/` | `test_audit_structural.py`, `test_gates_and_reconcile.py`, integration |
| Gates G0 / G1 | **PASS / PASS** | `artifacts/gates/G0.json`, `G1.json` | `test_g0_*`, `test_g1_*` |
| CLI | DONE (S1 scope) | `src/hyposense/cli.py` | exercised end-to-end |
| Analysis plan §1–3 (approved P-C1, P-C2, P-C3, P-C6) | DOCUMENTED (implementation S5/S7) | `docs/protocol/ANALYSIS_PLAN.md` | fixtures listed in §4 |

## In Progress
None. S1 ended at a clean boundary.

## Pending Components (dependency order)
1. **S2**: typed event schemas; label builder (test-first, ≥20 hand-labelled fixtures); event
   audit (G2, G3b); re-check of the 2003/2029 has-L1 strata; blueprint event-count
   reconciliation (episodes, prediction times)
2. S3: drug dictionary, dose parser (incl. S1 findings), kernels, exposure; G3; treated-flag
   re-check
3. S4: state engine, causal features, truncation-equality test
4. S5: evaluation harness implementing ANALYSIS_PLAN §2–3; M0 on T (expect exact Table A.2)
5. S6: M1 tuning, M2/M3r/M3 on T, calibration benchmark, G4
6. S7 (policy, replay, API) and S8 (frontend) in parallel
7. FREEZE → S9 → S10

## Scientific Status
| Item | Status |
|---|---|
| Dataset | **Official figshare v5 acquired and verified** (MD5 = figshare; SHA-256 `59b5f5c4…`); manifest `5f9d65b4…` |
| Published count | 112,475 **VERIFIED** on nature.com = v5 timepoint rows; 112,462 non-empty CGM; 13 documented device-change rows |
| Blueprint numbers | Structural: 11 MATCH, 8 EXPECTED DIFFERENCE (documented v5 update), 0 UNEXPLAINED. The mirror = figshare v1–v4 (MEASURED) |
| Labels | not implemented (S2) |
| Partition | **v1.0.0 official, immutable**: the blueprint's original, reproduced exactly by its algorithm (100/100); T 30 / E 70 |
| Models / calibration / evaluation | not implemented |
| Sealed evaluation (E) | **SEALED.** Only aggregate structural checks (approved P-C5); no labels, traces or outputs of E examined |
| Timezone | +08:00 local: ASSUMPTION, now strongly supported (meal entries peak 07/11/17 local; INFERRED) |

## Current Models
| Model | Implemented | Trained | Validated | Artefact | Result |
|---|---|---|---|---|---|
| M0 | no | n/a | no | no | none |
| M1 | no | no | no | no | none |
| M2 | no | no | no | no | none |
| M3r | no | no | no | no | none |
| M3 | no | no | no | no | none |
| M4 | not planned (ADR-015) | — | — | — | — |

## Data Status
- Dataset available: **yes** (local, git-ignored), `data/raw/ShanghaiT2DM/` (v5).
- Official copy verified: **yes** (G0 PASS).
- Hashes:
  - archive v5 sha256 `59b5f5c4053a32bb6b7827844a0191597dc82228fe88ce332a189fdfc659c4cb`
  - manifest files_sha256 `5f9d65b4e9233d4ecdd05438e80bb94314290cd5e2d9fdd21e353487cd3cc4ab`
  - partition sha256 `ccdcbce02b049992b0ca09bd99a2a5b8c49bcf49940f3a68ed6ca69cd2449578`
- Structural audit: **completed**. Runs `ALL-AGG-audit-structural-20261017T213548Z` and
  `…213615Z` gave an identical results_sha256 `09e780bd…`.
- Key numbers (MEASURED, v5):
  - 109 recordings / 100 patients (92 × 1, 7 × 2, 1 × 3 recordings);
  - 112,475 rows; 112,462 CGM readings; 1170.6 monitored days;
  - CGM parse 100%; intervals ≤20 min 99.99%; 1 gap >60 min (212 min, device change);
  - 329 floor readings; all values on the 1.8 mg/dL grid;
  - doses: 828 insulin s.c. entries (54 recordings), 2,171 oral entries (92), CSII in 35, i.v.
    in 6; 99.94% of medication entries sit on CGM rows;
  - 3,808 diet entries (745 "data not available").
- Known anomalies (all flagged, none deleted):
  - sheet-name mismatch in 2014_0;
  - 3 file-name dates that don't match the data (2017_0, 2094_0 [year typo], 2098_0);
  - 2 patients whose period index is not chronological;
  - 13 sub-second timestamps and 10 empty rows (2029_0 device change);
  - pump-suspension text ×2 and a misplaced "acarbose 50 mg" in CSII columns;
  - the i.v. column contains IV fluids (incl. 5% glucose) and one misplaced CSII basal entry.

## Testing Status
| Category | Status |
|---|---|
| Unit | 67/67 pass |
| Integration (real data, aggregate) | 5/5 pass |
| Leakage / static guards | 12/12 pass (truncation equality pending S4) |
| Reproducibility | audit determinism verified (identical results hash, 2 runs) |
| Regression | 9/9 pass |
| E2E | none yet |
| Lint / format / types | ruff check + format clean; mypy --strict clean (34 files) |

Last full run: `uv run pytest -q` → **93 passed** (2026-10-18).

## UI Status
Ward Board / Patient Review / Evidence View / Replay: not started (S7/S8).

## Open Issues
| Issue | Severity | Proposed solution |
|---|---|---|
| Sensor replacement inside 2029_0 not treated as warm-up | LOW | P-C7 (awaiting approval; not blocking S2) |
| i.v. column contains IV glucose and other fluids | MEDIUM (S3) | P-B5: a-priori decision in S3 |
| Misplaced medication entries in CSII and i.v. columns; pump-suspension text | MEDIUM (S3) | S3 parser recovers them from `raw_*` columns (never fabricates times) |
| "scilin m30" (premix human) missing from the blueprint regex; explains its 825/827 | LOW (S3) | Add to the drug dictionary |
| Partition strata were computed on pre-v5 data (2003, 2029 are E patients) | LOW | Re-check has-L1 in S2; report, never re-split |
| Kernel parameters ILLUSTRATIVE; pharmacist availability unknown | MEDIUM (S3) | Label-sourced values; record review status |

## Open Decisions
| Decision | Options | Recommendation | Approval required? |
|---|---|---|---|
| P-C7 sensor-restart warm-up | keep / restart warm-up after gap >120 min | restart (tiny impact) | Yes (not blocking until S7) |
| P-B1 calibration method | isotonic / Platt / interpolated isotonic | benchmark on T, pre-written rule | No |
| P-B2 boosting rounds | fixed tuned count | fixed count | No |
| P-B3 CSII basal continuation in projections | literal / continue | continue (a priori, S3) | No |
| P-B5 i.v. dextrose | ignore + flag / separate feature | ignore + flag (a priori, S3) | No |

## Last Verified Commit
- Code: `f68f98a` (S1 implementation + provenance fix; official audit runs reference it).
- Documentation and evidence commit: see `git log -1` (S1 docs + audit outputs).
- Date: 2026-10-18.

## Next Recommended Task
**S2 — Label builder (test-first) and event audit:** write ≥20 hand-labelled SYNTHETIC
fixtures for the Table 5.1 episode and eligibility rules, then implement `build_episodes` and
`eligible_times` on `cgm_series()`. Run the aggregate event audit (G2, G3b) and reconcile
episode, prediction-time and warnable counts against the blueprint. v1/v2 provide the exact
mirror baseline, as in S1.
