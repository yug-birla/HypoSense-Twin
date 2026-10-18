# Improvement Proposals and Clarification Requests

This file holds every proposal that deviates from, or makes more specific, the blueprint.

Status values: **AWAITING APPROVAL** · **APPROVED** · **REJECTED** · **EXPERIMENT PLANNED** ·
**IMPLEMENTED**.

- **Class C** (scientific protocol / safety): nothing is implemented until a human approves it.
  The approval is then recorded in [DECISION_LOG.md](DECISION_LOG.md).
- **Class B** (model and research engineering): resolved by a controlled experiment on
  development data (T) or by an a-priori decision recorded before freeze.
- **Class A** (engineering): implemented directly. The full list is in DECISION_LOG.md and is
  only summarised here.

---

## Class C — require human approval

### P-C1 · LOW NOW must take precedence over sensor-flag INSUFFICIENT DATA for a current low reading
**Status: APPROVED 2026-10-18** (owner) → [protocol/ANALYSIS_PLAN.md §1](protocol/ANALYSIS_PLAN.md); implementation S7 · raised 2026-10-18

1. **Current specification.** Table 14.1 evaluates priority 2 (INSUFFICIENT DATA: gap >20 min,
   <7/8 readings, warm-up <2 h, reading ≤40 mg/dL, |rate| >4 mg/dL/min) **before** priority 3
   (LOW NOW: CGM <70, in an episode, or <60 min after one). Fig. 14.2 adds: "any state →
   INSUFFICIENT DATA when a gap or artefact occurs".
2. **Problem.** A current reading at the sensor floor (≤40 mg/dL) is shown as **INSUFFICIENT
   DATA**, not LOW NOW. These are the deepest CGM lows in the data. The same happens to a
   reading <70 that arrives after a gap, during warm-up, or with a fast rate of change. Hiding a
   current low behind "insufficient data" conflicts with the safety principle that low risk,
   insufficient information and a current low are distinct states (CLAUDE.md §17).
3. **Evidence.** The audit found 329 readings ≤40 mg/dL (§8.1). Table 14.1 rule order. Fig. 14.2
   caption.
4. **Proposed modification.** If a CGM reading exists at t and CGM(t) <70 mg/dL, return
   **LOW NOW** whatever the sufficiency flags. Add tags (SENSOR_FLOOR, RAPID_CHANGE, AFTER_GAP,
   WARM_UP) and the text "verify with capillary glucose". INSUFFICIENT DATA keeps every other
   case: no reading at t, or a reading ≥70 that fails sufficiency.
5. **Scientific consequences.** None for the primary endpoint. Prediction times require
   CGM(t) ≥70, so LOW NOW times produce no forecast under either order. Hits are ALERT states
   at eligible times, and notifications come only from ALERT. The secondary "abstention
   coverage" metric falls slightly; both versions can be reported.
6. **Effect on comparability.** None. The same policy applies to all models.
7. **Risk of bias or leakage.** None. The rule uses only the current reading.
8. **Recommendation.** Approve.

### P-C2 · Exact operationalisation of the operating curve, sens@1FA and τ selection
**Status: APPROVED 2026-10-18** (owner) → [protocol/ANALYSIS_PLAN.md §3](protocol/ANALYSIS_PLAN.md) (exact algorithm + edge cases); implementation S5 · raised 2026-10-18

1. **Current specification.** "Episode sensitivity at exactly 1.0 FA/patient-day, read from
   each model's operating curve by linear interpolation between adjacent thresholds" (Table
   5.1). "τA = the lowest threshold whose development false-alert rate is ≤1.0 per patient-day".
2. **Problem.** The primary endpoint cannot be computed reproducibly from this wording.
   (a) **FA/day is not guaranteed monotone in the threshold.** Because of the 60-min cooldown,
   a lower threshold can start a notification earlier, and the cooldown can then absorb
   notifications that a higher threshold would have produced separately. The curve can
   therefore cross 1.0 FA/day more than once. "Adjacent thresholds" and "lowest threshold with
   FA ≤1.0" then pick different points. Sensitivity *is* monotone, because the ALERT state does
   not depend on cooldown.
   (b) **The threshold grid is unspecified.** Isotonic calibration outputs a step function
   with many tied values, so a curve over calibrated probabilities is coarse and the
   interpolated value depends on the grid.
   (c) For M0, the score is projected glucose (alert if *below* θ), so the sweep runs the other
   way.
3. **Evidence.** (a) and (c) follow from the definitions. (b) is a mathematical property of
   isotonic regression. The size of both effects will be **measured on T** in S5–S6: the count
   of unique calibrated values and the number of non-monotone FA steps.
4. **Proposed modification.** Fix the following rule *before any model is run*:
   - **Grid**: all unique pooled scores of the model (plus a sentinel above the maximum),
     ordered from strictest to most lenient. M0 sweeps θ ascending in 0.5 mg/dL steps over
     [30, 120].
   - **Curve**: at each grid point, (FA/day, sensitivity) from the causal policy replay (P-C3).
   - **sens@1FA**: scan from the strict end. At the **first** grid step where FA/day passes
     1.0, interpolate sensitivity linearly in FA between the two points that bracket the
     crossing.
   - **τA**: the most lenient grid threshold *before* the first crossing of the budget, on
     development (inner OOF) predictions. **τW** uses the same rule with its own budget (P-C6).
   - Report the number of non-monotone steps alongside each curve.
5. **Scientific consequences.** The pre-specified intent (sensitivity at a 1.0 FA/day budget)
   is unchanged; the rule only removes the ambiguity. Taking the first crossing is
   conservative: it never benefits from a later dip in FA.
6. **Effect on comparability.** The same rule applies to every model and every bootstrap
   resample.
7. **Risk of bias or leakage.** Low, provided the rule is fixed before results exist, which is
   the case now. The calibration method's effect on resolution is handled separately in P-B1.
8. **Recommendation.** Approve, and record the rule in `docs/protocol/ANALYSIS_PLAN.md`.

### P-C3 · Evaluation semantics: causal policy replay and false-alert accounting
**Status: APPROVED 2026-10-18** (owner; OUTCOME-UNKNOWN class reported separately) → [protocol/ANALYSIS_PLAN.md §2](protocol/ANALYSIS_PLAN.md); implementation S5 · raised 2026-10-18

1. **Current specification.** Prediction-time eligibility (Table 5.1) uses hindsight:
   episode membership, refractory period and ≥60 min of follow-up. Hits are ALERT states at
   eligible times. A false alert is a notification with no onset in (t, t+60].
2. **Problem.** Three things are not specified:
   (i) at which readings the policy runs during evaluation (only eligible times, or every
   reading);
   (ii) how a notification at a time *without* 60 min of follow-up is counted (for example at
   the end of a recording, where its truth is unknowable);
   (iii) whether the cooldown clock runs across ineligible readings.
   Different reasonable answers give different FA/day values, and so a different sens@1FA.
3. **Evidence.** The definitions in Table 5.1 and Appendix E. Analysis shows that the runtime
   LOW NOW/refractory logic, applied causally with one-reading confirmation lag, agrees with the
   hindsight eligibility at every reading. Every boundary case either has CGM <70 or falls
   inside the refractory period in both views. The **follow-up condition** is the only real
   hindsight element. Fixture tests in S2/S7 will verify this.
4. **Proposed modification.**
   - The policy runs causally at **every CGM reading** with the live `decide()`. The cooldown
     clock runs continuously.
   - The model is queried wherever the policy requests a probability (sufficient data,
     CGM ≥70, not LOW NOW). The model is **trained** on label-eligible times only, as in the
     blueprint.
   - **Hits** follow the blueprint exactly.
   - **False alerts** are notifications at times with ≥60 min follow-up (or an onset within it)
     and no onset in (t, t+60]. Notifications without determinable follow-up are excluded from
     the FA count and **reported separately**.
5. **Scientific consequences.** This makes the endpoint computable and makes the evaluated
   system identical to the deployed one. The blueprint's intent is unchanged.
6. **Effect on comparability.** The same semantics apply to every model, including M0.
7. **Risk of bias or leakage.** Excluding unknowable-outcome notifications removes a handful
   of events at recording ends. They are reported, so nothing is hidden.
8. **Recommendation.** Approve, and record the semantics in `docs/protocol/ANALYSIS_PLAN.md`.

### P-C4 · Partition provenance: the original `partition.csv` and audit scripts are not in the repository
**Status: RESOLVED 2026-10-18 — Option A.** Originals were found in the blueprint author's source bundle (`HypoSense_v2_sources.zip`). The documented algorithm (seed 2026) reproduces the original assignment exactly (0/100 mismatches). It was imported as `configs/partition.csv` v1.0.0, SHA-256 pinned and immutable (ADR-016) · raised 2026-10-18

1. **Current specification.** The patient-level partition T/E (seed 2026, stratified by
   treated × has-L1, frac_T 0.30) was created by the blueprint audit (`scripts/audit2.py`) and
   stored in `config/partition.csv`. T/E counts: 30/70 patients; 22/51 treated; 56/154 treated
   episodes.
2. **Problem.** Neither the partition file nor `audit.py`/`audit2.py` exists in this
   repository. A re-implemented stratified split with seed 2026 will almost certainly **not**
   reproduce the same patient assignment, because the RNG call sequence and algorithm differ.
   The sealed partition is a Class C element.
3. **Evidence.** A repository inventory on 2026-10-18 shows only `CLAUDE.md` and the blueprint
   .docx.
4. **Proposed modification.**
   - **Option A (preferred):** obtain the original `partition.csv`, `audit.py` and
     `audit2.py` from the blueprint author and adopt the partition verbatim, after checking
     that its patient keys and stratum counts reproduce on the official copy.
   - **Option B:** if A is unavailable within ~1 day, regenerate the partition with a
     documented deterministic algorithm and seed 2026 **before any modelling**. Record it as
     partition v1 and mark the blueprint's E counts as superseded. The has-L1 stratum needs L1
     labels for all patients. That is a single, automated, aggregate-only use of E labels
     (covered by P-C5), with no human inspection of per-patient output.
5. **Scientific consequences.** A: none. B: the T/E numbers change. The blueprint author's
   exploratory M0 run on the *old* T influenced no frozen design parameter (horizon, budgets,
   definitions and ladder were all fixed on a-priori grounds), so re-partitioning before any
   modelling does not bias H1.
6. **Effect on comparability.** None within this project. Blueprint numbers are not
   comparable under B.
7. **Risk of bias or leakage.** B risks nothing, provided the partition is generated before
   any feature, model or threshold work.
8. **Recommendation.** Ask for the originals today. Fall back to B at the start of S2.

### P-C5 · Permitted outcome-blind access to the sealed partition E before freeze
**Status: APPROVED 2026-10-18** (owner); safeguards implemented in S1 (ADR-018) · raised 2026-10-18

1. **Current specification.** E "influences nothing except the final numbers" (§15;
   CLAUDE.md §12). Yet the blueprint's own stage criteria need all files: "All 109 recordings
   load; episode counts reproduce the audit" (S2) and "≥99% entries parse" (S3). The audit
   itself reports aggregate counts over all 100 patients.
2. **Problem.** The boundary between data engineering on all files and E influencing design is
   undefined. Without a rule, either the adapter and parser cannot be validated, or E is
   touched informally.
3. **Evidence.** Blueprint §26 completion criteria, §8 aggregates, and Gate G0/G1 definitions.
4. **Proposed modification.** Before freeze, the following are permitted on E, **only through
   automated scripts behind the partition guard that emit aggregate reports**:
   (i) structural validation (checksums, column variants, timestamp monotonicity, interval
   distribution, parse success, unit sanity);
   (ii) medication and meal **text vocabulary** for dictionary coverage, which is outcome-blind;
   (iii) aggregate label counts for gates G0–G3b and the episode-count regression test;
   (iv) the partition stratum indicator (P-C4).
   **Forbidden** on E before freeze: viewing CGM traces, per-patient episode or label listings,
   computing any feature or model output, any tuning, kernel or threshold choice, and any demo
   or UI case selection.
5. **Scientific consequences.** This writes down how the blueprint was already designed to
   work.
6. **Effect on comparability.** None.
7. **Risk of bias or leakage.** Minimal. Item (ii) lets E's drug vocabulary shape the
   dictionary, but that is outcome-blind normalisation, the same as a pharmacist reading a
   product list.
8. **Recommendation.** Approve.

### P-C6 · Definition of τW ("notification-equivalent rate ≤3.0 per patient-day")
**Status: APPROVED 2026-10-18** (owner) → [protocol/ANALYSIS_PLAN.md §3.6](protocol/ANALYSIS_PLAN.md) · raised 2026-10-18

1. **Current.** §14.3: τW is the lowest threshold whose development "notification-equivalent"
   rate is ≤3.0 per patient-day.
2. **Problem.** It is ambiguous whether the rate counts all notifications or only false ones,
   and whether cooldown applies.
3. **Evidence.** The wording of §14.3.
4. **Proposed.** τW is chosen with the P-C2 first-crossing rule, applied to the **total**
   notification rate (true + false). That rate is computed with the same 60-min cooldown, as if
   τW were the alert threshold, on inner OOF development predictions.
5. **Consequences.** It affects only the WATCH display state. It has no effect on the primary
   or secondary endpoints.
6. **Comparability.** Not applicable.
7. **Bias.** None.
8. **Recommendation.** Approve.

### P-C7 · Sensor replacement within a recording should restart the warm-up period
**Status: AWAITING APPROVAL (low impact, not blocking S2)** · raised 2026-10-18 (S1 audit)

1. **Current specification.** Warm-up = "first 2 hours of a recording" (§10.1; policy priority 2).
2. **Problem.** Recording 2029_0_20210526 contains a documented CGM device replacement (the
   publisher's v5 note): a 212-min gap, then readings from a new sensor starting 2021-06-03
   12:46. Under the current rule, the new sensor's first readings are not flagged as warm-up,
   although sensor day-1 inaccuracy applies to them as well (SA2 exists for exactly this reason).
3. **Evidence.** S1 audit: 1 gap > 60 min in the whole dataset, at the device change (the only
   one). Publisher note.txt.
4. **Proposed modification.** Warm-up = the first 2 h after the recording start **or** after any
   CGM gap > 120 min (a gap that long implies a sensor restart or replacement in this data). SA2
   ("exclude first 24 h") should likewise restart after such a gap.
5. **Scientific consequences.** Very small. The 7-of-8-readings rule already blocks prediction
   times for 105 min after the gap, so at most a few readings change state. It affects one
   recording.
6. **Comparability.** Identical for all models.
7. **Bias/leakage.** None; the rule is causal (the gap is known at t).
8. **Recommendation.** Approve before S7 (policy). It may also be left as is, since the impact
   is negligible.

### P-C8 · Sensor-failure handling: a rule-based flag, a policy tag and sensitivity analysis SA9
**Status: APPROVED 2026-10-18** (owner; all three parts) → ANALYSIS_PLAN §0c; causal flag implemented (S3); policy and UI handling in S7/S8 · raised 2026-10-18 (S2)

1. **Current specification.** Labels come from CGM only. Sensor floor readings (≤ 40 mg/dL) are
   valid lows. Under P-C1 a current reading < 70 is LOW NOW. SA4 (compression) and SA5
   (CBG-contradicted episodes) are the only artefact-oriented analyses.
2. **Problem (MEASURED, S2).** Two tuning-partition recordings carry gross sensor artefacts:
   - **2075_0**: the CGM is stuck at the 39.6 mg/dL floor for the final 33.5 h. All 5 CBG values
     paired with CGM < 70 are normal (97–155 mg/dL).
   - **2077_0**: systematic negative bias. Median CGM is 56 mg/dL on 10 of 11 days, 67 % of
     readings are < 70, and 18/18 CBG values paired with CGM < 70 are ≥ 75 mg/dL.

   Together they hold **43 of the 117 T L1 episodes (37 %)** and most of T's L2 episodes (one
   patient = 69 % of T's L2). The live system would show LOW NOW for 33 h on a failed sensor.
   **None of this reaches the confirmatory population.** Both patients are untreated and in T.
   The floor-run rule flags **0 episodes and 0 recordings in E**.
3. **Evidence.** Event audit `ALL-AGG-audit-events-*`: `sensor_floor_runs`,
   `by_partition.*.L1_overlapping_sensor_floor_run`, and the T-only trace review (permitted).
4. **Proposed modification.**
   - (a) A CGM-only rule, defined on T and applied uniformly: a **sensor-floor run** is ≥ 8
     consecutive readings ≤ 40 mg/dL (≥ 2 h).
   - (b) Policy: during such a run the state stays LOW NOW (P-C1) and gains the tag
     **SENSOR FAULT SUSPECTED — check sensor and capillary glucose**.
   - (c) A new sensitivity analysis **SA9**: the primary comparison excluding episodes that
     overlap a sensor-floor run.
   - (d) The primary endpoint, labels and population are **unchanged**.
5. **Scientific consequences.** None for H1 as specified, because E has no flagged episodes and
   SA9 = primary on current data. The demo becomes safer and more realistic.
6. **Comparability.** Identical for all models.
7. **Bias/leakage.** The rule was designed after inspecting T only. It uses CGM at or before t,
   so it is causal for the policy. Not tuned on E.
8. **Recommendation.** Approve (a)–(c). The systematic-bias case (2077) is not catchable by a
   CGM-only rule; it is handled by P-B6 and by SA5.

---

## Class B — experiments or a-priori decisions on development data (T) before freeze

### P-B1 · Calibration method benchmark (isotonic vs Platt vs smoothed isotonic)
**Status: EXPERIMENT PLANNED (S6)**
- **Current approach**: isotonic regression on inner OOF predictions (§11.1).
- **Problem**: isotonic output is piecewise constant. The resulting ties coarsen the operating
  curve (P-C2), and the fit can be unstable with few positives per fold (~1.1% prevalence). The
  band rule (calibration slope outside 0.8–1.25) is trivially ≈1 if computed on the data used
  to fit the calibrator.
- **Alternatives**: Platt (logistic) scaling; isotonic with linear interpolation between knots
  (strictly monotone, so it keeps resolution).
- **Protocol**: T only, inner grouped CV. Calibrators are fitted on inner-train OOF predictions
  and evaluated on inner-held-out patients: log-loss, Brier, ECE, calibration slope and
  intercept, and the number of unique values. A **decision rule is written before running**:
  keep isotonic unless a challenger improves held-out log-loss without worsening ECE. Ties go to
  the blueprint default. One method then applies to all models.
- **Classification**: B · **Action**: EXPERIMENT.

### P-B2 · Number of boosting rounds in nested and confirmatory training
**Status: A-PRIORI DECISION PROPOSED**
- **Current**: "2,000 rounds with early stopping on inner grouped log-loss" (§11.1).
- **Problem**: early stopping in the confirmatory run needs a validation split carved from
  T ∪ (E∖k). The blueprint leaves this undefined, and different choices change the models.
- **Proposed**: treat `num_boost_round` as a tuned hyperparameter. During M1 tuning on T,
  record the best iteration of each inner fold for the winning trial and freeze
  `num_boost_round` = their median. Every nested and confirmatory fit then uses that fixed
  count with **no** early stopping. This keeps the fits deterministic and removes the need for
  a validation split.
- **Classification**: B (hyperparameter procedure) · **Action**: decide before S6 tuning;
  record in DECISION_LOG.

### P-B3 · CSII basal infusion in exposure projections
**Status: RESOLVED (S3, a priori): option (b) — continue the current programmed rate (ADR-026)**
- **Current**: projections to t+30 and t+60 "assume no further doses" (§10.2, §12.2). The
  basal rate is modelled as 15-min micro-boluses "until the next rate entry".
- **Problem**: a running CSII basal rate is a known, ongoing administration at t. Projecting
  zero future micro-boluses understates future exposure for 35 pump recordings.
- **Options**: (a) the literal blueprint; (b) continue the current basal rate through the
  projection horizon, because the rate is known at t and so stays causal.
- **Recommendation**: choose (b) **a priori on mechanistic grounds, not by metric**, and adjust
  the UI caption to "assumes no further boluses; current pump basal rate continues". This needs
  confirmation of how basal entries appear in the data (S3).
- **Classification**: B · **Action**: a-priori decision at S3, before any M3 result exists.

### P-B4 · Kernel specification details to pin with the pharmacist
**Status: RESOLVED for engineering (ADR-027): flat window [lag, lag + duration); D_max per drug from labels; pharmacist review still pending**
- Basal-analogue flat window: does "flat after a 1-h lag over 24 h" mean active on [60, 1440)
  or on [60, 1500) min? Normalisation must integrate to 1 either way.
- Bateman D_max per drug and formulation (gliclazide IR vs MR, glimepiride, gliquidone,
  repaglinide).
- **Recommendation**: settle each with product-label sources before any M3 development result
  exists, and record them in `pharma.yaml`.

### P-B5 · Intravenous column carries IV fluids, including 5% glucose (S1 finding)
**Status: RESOLVED (S3): FLAG ONLY (ADR-028)**. 3 events, E only, rate unknown
- **Finding (MEASURED, S1 vocabulary)**: the "Insulin dose - i.v." column contains Novolin R
  infusions (9 components), **5% glucose** (2), 5% glucose + sodium chloride (1), 10% potassium
  chloride (9), 0.9% sodium chloride (6), and one misplaced CSII-basal entry. These come from 10
  entries in 6 recordings.
- **Problem**: the blueprint treats this column as "i.v. insulin flag only". Glucose infusions
  raise glucose and are a plausible confounder (or a treatment response). They must not be
  counted as insulin.
- **Options**: (a) i.v. insulin flag only, with dextrose ignored; (b) add a separate "i.v.
  dextrose in last 4 h" flag to M3/M3r context (and to M2 if it is regarded as context, not
  medication exposure).
- **Recommendation**: decide a priori in S3 before any model result. Because only 3 entries are
  dextrose, prefer (a) plus a data-quality flag, to keep M2 vs M3 clean.
- **Classification**: B.

### P-B6 · Development-stage handling of sensor-artefact recordings in T (S6)
**Status: EXPERIMENT PLANNED (S6; decision rule to be written before any model is run)**
- **Problem**: T development metrics (M1 tuning objective, ladder on T, the M0 Table A.2
  reproduction) are dominated by two artefact recordings: 37 % of T's L1 episodes, with T's
  largest single-patient share 24 % for L1 and 69 % for L2.
- **Options**:
  - (a) Keep everything (the blueprint);
  - (b) also report patient-weighted development metrics (Blueprint S7 already does this for
    E);
  - (c) in addition, run a pre-specified training/tuning variant that excludes episodes and
    windows overlapping sensor-floor runs (P-C8a) and recordings meeting an objective
    CBG-contradiction rule. The rule must be written before running, e.g. ≥ 5 CGM < 70 readings
    paired with CBG, all with CBG ≥ 70.
- **Constraint**: the confirmatory evaluation population and labels never change. This
  concerns only what the learner sees in training and which development summary steers
  tuning.
- **Recommendation**: (b) always. (c) as a controlled comparison; adopt for training only if it
  improves development held-out log-loss on the unaffected T patients by a pre-set margin.
- **Classification**: B.

### P-B7 · Secretagogue representation: separate SU and glinide vs combined (S6)
**Status: EXPERIMENT PLANNED (S6)**
- **Evidence (MEASURED, S3)**: there are 0 glinide patients in T and 3 in E, so `act_glinide` is 100 %
  zero in T. A separate glinide channel cannot be learned on development data and adds
  near-empty dimensions.
- **Candidate**: `M3_candidate_secretagogue` combines SU and glinide into one
  dose/D_max-normalised exposure (the shared scale already exists by design), against
  `M3_baseline` (separate, as in the blueprint).
- **Rule**: decide on T inner-CV log-loss with a pre-written margin. M3_baseline stays the
  confirmatory definition unless the owner approves a change before freeze.
- **Classification**: B.

### P-B8 · Compact M3 (redundancy) and product-specific basal durations (S6)
**Status: EXPERIMENT PLANNED (S6)**
- **Evidence (MEASURED, S3; T only)**:
  - Spearman ρ(insulin_p60, act_insulin_total) = 0.974, so the projections are nearly redundant
    with current activity; only the Δ carries information.
  - ρ(act_insulin_total, insulin_bolus_dose_24h) = 0.80 and ρ(act_su, su_min_since_last) = −0.69,
    so M3 and M3r overlap substantially. C2b may well find M3 ≈ M3r.
- **Candidates**:
  - (a) compact M3: family activities, total IOB, Δ60 insulin, SU exposure, Δ60 SU, minutes-since,
    flags (≈ 12 variables instead of ≈ 21);
  - (b) detemir duration shortened to the dose-dependent ~14–20 h, a kernel sensitivity variant
    within SA6.
- **Rule**: T inner CV only, with a pre-written decision margin. M3_baseline is preserved.
- **Classification**: B.

---

## Class A — engineering (implemented or scheduled; see DECISION_LOG)

| ID | Summary | Status |
|---|---|---|
| ADR-002 | `src/` layout, `configs/`, `artifacts/` | IMPLEMENTED |
| ADR-003 | uv + lockfile, Python 3.11 | IMPLEMENTED |
| ADR-004 | Single causal feature implementation for training and replay | SCHEDULED S4 |
| ADR-005 | Audit built on production modules; audit split across S1–S3 | IMPLEMENTED for S1 (structural); S2/S3 parts pending |
| ADR-006 | `hyposense` CLI instead of Makefile | IMPLEMENTED (data/partition/audit/gates) |
| ADR-007 | Next.js + TS + Tailwind + shadcn/ui + ECharts; static export served by FastAPI | SCHEDULED S8 |
| ADR-008 | REST + SSE; TS types generated from OpenAPI | SCHEDULED S7 |
| ADR-009 | No pickle in artefacts | SCHEDULED S6 |
| ADR-010 | File-based run manifests (no MLflow) | IMPLEMENTED (audit runs) |
| ADR-011 | Partition guard + freeze manifest | PARTIAL: scoped access implemented (ADR-018); freeze manifest at Freeze |
| ADR-012 | Standalone `docs/protocol/ANALYSIS_PLAN.md` hashed at freeze | SCHEDULED S5 |
| ADR-013 | Demo fallback = recorded video + static exports (no Streamlit) | ACCEPTED |
| ADR-014 | Protocol-constant lock + import-boundary tests | IMPLEMENTED |
| ADR-016 | Original partition imported, verified, hash-locked | IMPLEMENTED |
| ADR-017 | Canonical data = figshare v5; v1/v2 for reconciliation only | IMPLEMENTED |
| ADR-018 | Scoped dataset access (sealed-partition safeguard) | IMPLEMENTED |
| ADR-019 | Loader conventions (raw cells, flags not deletion, rounding, severities) | IMPLEMENTED |
| ADR-020 | Aggregate-only audit evidence committed to git | IMPLEMENTED |
| ADR-021 | `ruff format` adopted repository-wide | IMPLEMENTED |
| ADR-022 | Label package: explicit state machine, typed outputs, differential tests vs executable spec | IMPLEMENTED |
| ADR-023 | Legacy treated definition isolated in `audit/legacy.py` (reproduction + provisional G2 only) | IMPLEMENTED; superseded for science by DEC-2026-10-18-D |
| ADR-024 | Content-aware medication parsing | IMPLEMENTED |
| ADR-025 | Exact summation (bitwise causality) | IMPLEMENTED |
| ADR-029 | Provenance porcelain parsing fix | IMPLEMENTED |

---

## Housekeeping (low severity, owner decision)

- **H-1** · CLAUDE.md §2 gives the blueprint path as `docs/blueprint/HypoSense_Twin_v2_Blueprint.docx`.
  The file is at `docs/HypoSense_Twin_v2_Blueprint.docx`. Proposal: update CLAUDE.md §2. This
  was left unedited because CLAUDE.md is the owner's instruction file.
