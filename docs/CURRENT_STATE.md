# HypoSense Twin — Current Project State

_Last updated: 2026-10-18 (end of S2). This is the canonical snapshot. Read it first, then
[NEXT_STEPS.md](NEXT_STEPS.md) and [PROGRESS.md](PROGRESS.md)._

## Current Phase
**S2 — complete and reviewed.** Next: **S3** (medication normalisation and exposure engine; G3).
S3 has **not** been started, per the owner's instruction.

## Overall Status
**IMPLEMENTATION.** The data and label foundations are verified. No model work has started.

## Completed Components
| Component | Status | Files | Tests |
|---|---|---|---|
| S0 baseline | DONE | — | constant lock, import guard |
| S1 data foundation (source, manifest, loader, structural audit, partition) | DONE; G0 PASS, G1 PASS | `src/hyposense/data/`, `audit/{structural,versions,reconcile,run}.py` | see TEST_STRATEGY |
| **Label builder** (L1, L2, single-reading; eligibility; labels; warnable) | **DONE** | `src/hyposense/labels/{config,episodes,eligibility,build}.py` | 34 trace + 4 loader-path fixtures; invariants; differential vs executable spec; 7/7 mutants killed |
| **Label validity + annotations** | **DONE** | `labels/{validity,annotations}.py` | unit tests; v2 exact |
| **Event audit + legacy reproduction** | **DONE** | `audit/{events,event_run,legacy}.py`; CLI `hyposense audit events` | integration (v5 counts, determinism, v2 48/48) |
| **G2 / G3b** | **G2 PASS (provisional treated def.) / G3b TRIGGERED** | `artifacts/gates/G2.json`, `G3b.json` | `test_g2`, `test_g3b`, Table 8.4 reproduction |
| Analysis plan §0 (operational label protocol) | ADOPTED (= executable spec) | `docs/protocol/ANALYSIS_PLAN.md` | — |

## In Progress
None. S2 ended at a clean boundary.

## Pending Components (dependency order)
1. **S3**: drug dictionary, dose parser, kernels, exposure; G3. It also brings the production
   treated status, which replaces the legacy definition, and a G2 re-check.
2. S4: state engine, causal features, truncation-equality test.
3. S5: evaluation harness (ANALYSIS_PLAN §2–3), M0 on T.
4. S6: M1 tuning, ladder on T, calibration benchmark, P-B6, G4.
5. S7/S8 in parallel; FREEZE → S9 → S10.

## Scientific Status
| Item | Status |
|---|---|
| Dataset | figshare v5, verified (G0, G1 PASS) |
| Labels | **Implemented and verified.** All 48 blueprint event values reproduced exactly on figshare v1/v2. v5: 46 MATCH + 2 EXPECTED (documented v5 rows), 0 UNEXPLAINED |
| Event counts (v5, MEASURED) | L1 348 in 61 patients; L2 96 in 26; single-reading 430 in 67; prediction times 107,210 (95.3 % of readings), 1,188 positive (1.11 %); warnable 306 (87.9 %) |
| G2 | **PASS** (provisional): 154 E-treated L1 episodes in 30 patients; m_w 9.23; 95 % CI half-width 0.113 at ICC 0.15 (MDD 0.13–0.17) |
| G3b | **TRIGGERED**: 54/65 episodes with a concurrent CBG unconfirmed (0.831). Consequences already in the design (CGM-detected naming, SA5, capillary action, L2 secondary) |
| Partition | v1.0.0 immutable. Strata re-verified on v5 (9/18/30/43; T 3/5/9/13); the 2003/2029 check passes |
| Sensor artefacts | Two T-untreated recordings (2075 stuck at floor 33.5 h; 2077 systematic negative bias) hold 37 % of T's L1 episodes. **0 floor-run artefacts in E** → P-C8 (approval), P-B6 (S6 experiment) |
| Models / calibration / evaluation | not implemented |
| Sealed evaluation (E) | **SEALED.** Aggregate-only access (P-C5). No E trace inspected; the trace review was limited to T |

## Current Models
None implemented (M0–M3 pending S5/S6; M4 not planned).

## Data Status
- Dataset: available (git-ignored), manifest `5f9d65b4…`, partition `ccdcbce0…`.
- Audits:
  - structural: `ALL-AGG-audit-structural-20261017T2135*`;
  - events: `ALL-AGG-audit-events-20261017T2212*` (results_sha256 `2f92a0c9…`, identical across
    2 runs, commit `32f3245`, clean).
- Known label-relevant anomalies:
  - sensor artefacts in T (above);
  - 11 L1 onsets fall within the first 2 h (unwarnable by design);
  - 22 onsets occur within 60 min of the previous episode's end;
  - L2 is concentrated (one patient = 35 % overall, 69 % within T; 19 % within E).

## Testing Status
| Category | Status |
|---|---|
| Unit | 165/165 |
| Leakage / static guards | 12/12 (truncation equality pending S4) |
| Regression | 9/9 (now also locks label eligibility keys, G2, G3b) |
| Integration (real data, aggregate) | 8/8 (incl. v2 48/48 reproduction, v5 event counts, determinism) |
| Reproducibility | structural and event audits deterministic (identical hashes) |
| E2E | none yet |
| Lint / format / types | ruff + format clean; mypy --strict clean (43 files) |

Last full run: `uv run pytest -q` → **194 passed** (2026-10-18).

## UI Status
Not started (S7/S8).

## Open Issues
| Issue | Severity | Proposed solution |
|---|---|---|
| Sensor-failure artefacts in T distort development metrics; a stuck sensor would show LOW NOW for 33 h | HIGH for S6 dev / MEDIUM safety | P-C8 (rule + policy tag + SA9) for approval; P-B6 (S6 controlled comparison) |
| Treated status is still the legacy regex definition | MEDIUM | S3 production parser; re-evaluate G2 |
| L2 secondary analysis concentrated in few patients | LOW (secondary) | Report patient-weighted L2 results (S7 forest plot) |
| i.v. column holds IV fluids incl. 5 % glucose | MEDIUM (S3) | P-B5 a-priori decision |
| Misplaced medication entries, pump-suspension text, "scilin m30" | MEDIUM (S3) | S3 parser |
| Sensor replacement warm-up (2029_0) | LOW | P-C7 (hook implemented, off) |

## Open Decisions
| Decision | Recommendation | Approval required? | Blocking? |
|---|---|---|---|
| P-C8 sensor-failure flag + policy tag + SA9 | Approve | **Yes** | Not for S3; needed before S6/S7 |
| P-C7 warm-up restart after gap > 120 min | Approve (tiny impact) | Yes | Before S7 |
| Operational label protocol (ANALYSIS_PLAN §0) | Adopted; equals the executable spec | Owner may object | No |
| P-B1/P-B2/P-B3/P-B5/P-B6 | as in PROPOSALS | No (Class B) | — |

## Last Verified Commit
- Code: `32f3245` (S2 implementation; the official event audits reference it).
- Documentation and evidence commit: see `git log -1`.
- Date: 2026-10-18.

## Next Recommended Task
**S3 — Medication normalisation and exposure engine:**
- the versioned drug dictionary and `parse_dose`, covering every S1 finding;
- exposure kernels (Eq. 1–6) with label-sourced parameters;
- `exposure_at` with causality tests;
- the medication audit (G3);
- the production treated status, then a G2 re-evaluation against the provisional result.
