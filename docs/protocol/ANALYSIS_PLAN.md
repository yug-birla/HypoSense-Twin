# HypoSense Twin v2 — Statistical Analysis Plan (pre-registration)

**Status: DRAFT v0.5 — §0 ADOPTED (= executable spec, S2); §0b ADOPTED (S3); §0c APPROVED (P-C8);
§0d ADOPTED (= executable spec, S4; exact arithmetic S5); §5 DRAFT (S5, awaiting owner approval);
§1–4 APPROVED by the project owner (2026-10-18); §5–6 pending (S5).** This file is hashed into the freeze manifest (ADR-012). After freeze it may not
change. Before freeze, a change to an APPROVED section requires a new owner approval recorded
in [../DECISION_LOG.md](../DECISION_LOG.md).

Baseline definitions (episode, prediction time, hit, notification, false alert, treated) are
those of Blueprint v2.0 Table 5.1 and are not restated here. This plan fixes the operational
details the blueprint left open.

---

## 0. Label protocol, operational form (S2, 2026-10-18)

Status: **ADOPTED. Identical to the blueprint's executable specification** (audit.py /
audit2.py, which produced every number in Blueprint §8). The production label builder reproduces
all 48 blueprint event values exactly on the mirror-equivalent figshare v1/v2 data (EXPERIMENT_LOG
S2). The items below only make Table 5.1's wording precise; they change no number.
Implementation: `src/hyposense/labels/`. Fixtures: `tests/unit/label_fixtures.py`.

1. **Low**: value < threshold (70 for L1, 54 for L2). A value equal to the threshold is not low.
   All values lie on the 1.8 mg/dL grid (§1 note).
2. **Onset**: the first reading i with low(i) and low(i+1), where t(i+1) − t(i) ≤ 20 min.
3. **End** (scan j = i+1, …; the first rule that applies wins):
   - (a) **GAP** if t(j) − t(j−1) > 30 min. A gap of exactly 30 min does not end an episode.
   - (b) **RECOVERED** if ¬low(j), ¬low(j+1) and t(j+1) − t(j) ≤ 20 min. "Consecutive" recovery
     readings therefore obey the same 20-min spacing as onset readings.
   - (c) **RECORD_END** otherwise. A final lone ≥ 70 reading cannot confirm recovery.

   The episode covers readings [onset, end) by index. Its end time is the time of the reading
   at the end index: the first recovery reading, or the first reading after the gap.
4. **Refractory**: readings with t ∈ [end time, end time + 60 min). For GAP endings, the
   refractory period therefore starts at the first post-gap reading.
5. **History** (prediction time t):
   - **t − recording start ≥ 120 min.** This equals the policy's warm-up rule (Table 14.1,
     priority 2), so no label-eligible time can fall in a period where the policy cannot alert.
   - **≥ 7 readings in the half-open window (t − 120 min, t].**
   - The warm-up anchor can be re-set after long gaps through
     `eligibility.warmup_restart_after_gap_min`. This is the P-C7 hook, currently `null`
     (PENDING).
6. **Follow-up**: last reading − t ≥ 60 min, OR an L1 onset in (t, t + 60 min].
7. **Label**: y(t) = 1 iff an L1 onset lies in (t, t + 60 min]. y is undefined (−1) at
   non-eligible readings. Every reading carries the first failing eligibility rule, in the
   order LOW_CGM, IN_EPISODE, REFRACTORY, INSUFFICIENT_HISTORY, INSUFFICIENT_FOLLOW_UP.
8. **Warnable episode** (the ceiling on sensitivity): some label-eligible t lies in
   [onset − 60, onset − 15] min, closed at both ends. The executable spec's variant (first onset
   after an eligible positive t, with no 15-min lead check) gives the same count on this data
   (306). The production definition is the Table 5.1 one.
9. **Single-reading rule** (SA1): as rules 2–3 with min_run = 1.
10. **Recording independence**: episodes, refractory periods, warm-up and labels are computed
    per recording and never cross recording boundaries. Recording order is irrelevant.
11. **Label validity** (G3b, SA5): a CBG is paired with the nearest CGM reading within ± 8 min,
    with ties going to the earlier reading. A CBG falls "during" an episode if it lies in
    [onset, last in-episode reading + 15 min]. The episode is confirmed if any such CBG < 70.
    CBG never changes an episode.

**Two distinct time concepts.** **Policy decision time** is every CGM reading; the live policy
is causal (§2). **Label-eligible time** is the subset defined above, used for training rows and
for counting hits. Labels may use the future; the policy and features may not.

## 0b. Treated population and medication exposure (S3, 2026-10-18)

**Treated patient (operational form of Table 5.1).** A patient is treated if any of their
recordings contains ≥ 1 parsed (PARSED or PARSED_WITH_WARNING) logged administration of:
- insulin by any route: s.c. injection, CSII bolus > 0 IU, CSII basal rate > 0 IU/h, or an i.v.
  insulin bag; or
- a sulfonylurea; or
- a glinide.

Classification follows the parsed CONTENT of a cell, never its source column. A zero-dose CSII
bolus, a pump-suspension text and a pasted column header are not administrations. Status:
ADOPTED, being the production form of the blueprint definition.

Result (MEASURED): 72 treated patients (T 22, E 50). The legacy audit rule gave 73. The single
difference is patient 2078 (E), whose only "insulin" under the legacy rule was a misplaced
"acarbose 50 mg" cell in the CSII bolus column. G2 is unchanged (154 E-treated L1 episodes in 30
patients). Artefact: `artifacts/population/treated_patients.csv` (sha256 recorded in the
medication audit).

**Medication exposure conventions.** These are frozen with the code at freeze:
- An administration charted at row time t is known at t.
- Exposure at t uses only administrations with ts ≤ t.
- Projections assume no future injections or tablets. They do continue the currently programmed
  CSII basal rate (P-B3, a-priori).
- A programmed basal rate lasts at most 6 h after its entry.
- Summation is exact (math.fsum), so truncated and full records give identical values.

Kernel parameters and their provenance: configs/pharma.yaml and
docs/medication/PARAMETER_SOURCES.md.

## 0c. Sensor-failure handling (approved P-C8, 2026-10-18)

- **P-C8a: definition.** A *sensor-floor run* is ≥ 8 consecutive CGM readings ≤ 40 mg/dL, each
  ≤ 20 min after its predecessor (≈ ≥ 2 h at the floor). It is a measurement-quality annotation
  and **never alters the canonical labels**.
- **P-C8b: live behaviour (policy, S7).**
  - A causal flag (`data.quality.sensor_fault_suspected`) becomes true at the 8th consecutive floor
    reading, using data up to t only.
  - While it is true, the state stays **LOW NOW** (P-C1), with the prominent data-quality warning
    "SENSOR FAULT SUSPECTED — verify sensor and obtain capillary glucose."
  - The state is never converted to NO ALERT, the observed low is never hidden, and no treatment
    advice is given.
- **P-C8c: sensitivity analysis SA9.** It repeats the primary comparison (Δ sens@1FA, M3 − M2,
  E-treated) with two exclusions:
  - (i) every L1 episode whose readings [onset, end) overlap a sensor-floor run (identified in
    hindsight; offline annotation `labels.annotations.floor_runs`) is removed from the
    sensitivity denominator;
  - (ii) notifications issued at times t whose label window (t, t + 60 min] overlaps a
    sensor-floor run are removed from FA accounting and reported separately.

  Everything else is as in the primary analysis (bootstrap, rules, thresholds).
  - SA9 is a sensitivity analysis only; the canonical primary analysis is unchanged.
  - MEASURED on v5: 0 E episodes overlap a sensor-floor run, so SA9 equals the primary
    analysis unless the data change.

## 0d. M0 trend rule and feature-time conventions (S4, 2026-10-18)

Status: **ADOPTED. Identical to the blueprint's executable specification** (audit2.py, which
produced Table A.2). This makes Table 11.1's "last 30 min of CGM (≥ 3 readings)" precise; it
changes no number.

1. **M0 projection.** At reading t, take the readings with ts in (t − 35 min, t]. With fewer than
   3, there is no projection (NaN). Otherwise slope = the least-squares slope of g on time
   (mg/dL per min), and the projection to t + H is g(t) + H × slope. The fit's intercept is not
   used: the line is anchored at the current reading. The M0 score is −projection(t + 60)
   (§3.1).
2. The same projection (H = 30, 60) and slope are App. D group-1 and group-2 features
   (`cgm_m0_proj30/60`, `cgm_slope30`). One implementation, `features.cgm`, serves both M0 and the
   features. Since S5 (ADR-036) the slope and projection are computed in exact rational arithmetic on the 0.1 mg/dL data grid and rounded once. A projection exactly equal to θ is exactly θ and does not alert (strict rule). This agrees with numpy.polyfit to 1e-9 (`test_ls_slope_matches_numpy_polyfit`).
3. **Feature time.** Features at t use only events with ts ≤ t, ordered dose → meal → CGM within
   one timestamp. Static summary values (including laboratory values that may post-date the CGM
   period) are recording-level context available at every t. This is Blueprint §10.2's accepted
   residual risk, removed in SA8. Full definitions: docs/FEATURE_DICTIONARY.md and
   artifacts/features/feature_spec.json.

## 1. Decision policy: current lows (approved P-C1)

1. If a CGM reading exists at t and CGM(t) < 70 mg/dL, the state is **LOW NOW**, whatever the
   data-sufficiency flags (gap, warm-up, ≤40 floor, rapid change).
2. Any sufficiency flag that applies is attached as a tag (`SENSOR_FLOOR`, `RAPID_CHANGE`,
   `AFTER_GAP`, `WARM_UP`), together with the text "verify with capillary glucose".
3. INSUFFICIENT DATA applies only when no reading exists at t, or when the reading is
   ≥ 70 mg/dL and fails sufficiency.
4. The rule changes no prediction time, label or hit (prediction times require CGM(t) ≥ 70), so
   the primary endpoint is unaffected.

Note (S1, VERIFIED): every CGM value lies on the 1.8 mg/dL grid (0.1 mmol/L × 18). "< 70 mg/dL"
therefore means "≤ 68.4 mg/dL" (≤ 3.8 mmol/L), which matches the consensus "< 3.9 mmol/L". No
reading equals 70 exactly, so the comparison has no tie ambiguity. Likewise "< 54" means
"≤ 52.2 mg/dL" (< 3.0 mmol/L).

## 2. Evaluation semantics (approved P-C3)

1. **Policy replay.** For each model, the frozen decision policy is replayed causally over each
   recording in timestamp order, using the same `decide()` function as the live system. The
   policy is evaluated at every CGM reading, which is every reading at which the live system
   would issue a decision. The model is queried wherever the policy needs a probability
   (sufficient data, CGM ≥ 70, not LOW NOW). The 60-min notification cooldown runs
   continuously over the replay, including across readings where no forecast is made.
   *Interpretation note:* the owner's approval says "at every eligible reading". It is read here
   as "every reading at which the policy issues a decision". Hits are still counted only at
   label-eligible prediction times (item 3).
2. **Training rows.** Models are trained on label-eligible prediction times only (Table 5.1).
3. **Hits.** An episode is warned if at least one **label-eligible** prediction time in
   [onset − 60, onset − 15] min has state ALERT. Lead time is onset minus the earliest such
   time. The window is closed at both ends.
4. **Notification outcome classes.** Every notification issued at time t_n gets exactly one
   class:
   - **TRUE**: an L1 onset in (t_n, t_n + 60 min].
   - **FALSE**: no onset in (t_n, t_n + 60 min], and the recording's last CGM reading is at or
     after t_n + 60 min.
   - **OUTCOME-UNKNOWN**: no onset in (t_n, t_n + 60 min], and the recording ends before
     t_n + 60 min. These are excluded from both the TRUE and FALSE counts and reported
     separately, per model and per analysis. They are never silently counted as either.
5. **FA rate.** FA/patient-day = FALSE notifications / Σ monitored days of the evaluated
   patients. A recording's monitored days run from its first to its last CGM reading
   (structural audit definition, `dataset.monitored_days`).
6. **Alert precision** = TRUE / (TRUE + FALSE). OUTCOME-UNKNOWN is excluded and reported.

## 3. Operating curve, sens@budget and threshold selection (approved P-C2)

### 3.1 Score orientation
For every model, higher score means higher risk. Learned models (M1–M3, M3r) use the calibrated
probability p(t). M0 uses score(t) = −(projected CGM at t + 60 min), so the M0 rule "ALERT if
projection < θ" is the same as "score > −θ". The M0 alert condition is strict (projection < θ),
so for M0 "score ≥ τ" is replaced by "score > τ". Every other model uses `score ≥ τ`
(inclusive).

### 3.2 Threshold grid
The grid is the set of **all distinct values** of the model's score among the pooled
policy-queried readings of the evaluated population, ordered from strictest (highest) to most
lenient. A sentinel τ₀ = +∞ comes first (no alerts: FA = 0, sensitivity = 0). Only exact
computation is permitted. An implementation may use any acceleration (e.g. an event-driven
sweep) only if it gives exactly the same curve values. Approximate grids (quantile binning) are
**not** allowed.

### 3.3 Curve points
For each grid threshold τ_k, the policy replay under §2 gives a point (F_k, S_k). F_k is
FA/patient-day and S_k is episode sensitivity. S_k is non-decreasing as τ decreases, because
the ALERT state does not depend on cooldown. F_k need not be monotone (cooldown). The count of
grid steps where F decreases is reported with every curve.

### 3.4 Sensitivity at budget B (B = 1.0 for the primary endpoint)
Scan from the strict end, k = 0, 1, 2, …
- Let k* be the **first** index with F_{k*} > B.
- Let a = k* − 1, the last point before the first crossing. F_a ≤ B by construction.
- **sens@B** = S_a + (B − F_a) · (S_{k*} − S_a) / (F_{k*} − F_a). If F_a = B exactly, sens@B = S_a.
- **Edge cases:**
  - If no grid point has F > B (the budget is never reached even at the most lenient
    threshold), sens@B = S at the most lenient point. The result carries the flag
    `budget_not_reached`.
  - If k* = 1 (the strictest real threshold already exceeds B), interpolate from the sentinel
    (0, 0).
  - Later points where F dips back below B are ignored. First crossing only is a deliberately
    conservative rule.
  - Ties: all readings with equal score switch together (the grid contains distinct values only).
- The same rule applies to every model and to every bootstrap resample. In each resample the
  grid is the set of distinct scores within that resample.

### 3.5 Deployed alert threshold τA
τA = τ_a from §3.4 with B = 1.0. It is computed on **development** inner out-of-fold predictions
of the training patients only, frozen before the held-out fold (and E as a whole) is scored.
If the budget is never reached, τA is the most lenient grid threshold and is flagged.

### 3.6 WATCH threshold τW (approved P-C6)
τW is chosen with the same first-crossing rule (§3.4, B = 3.0) applied to the **total
notification rate**. That rate counts TRUE + FALSE + OUTCOME-UNKNOWN notifications per
patient-day, computed with the same 60-min cooldown **as if τW were the alert threshold**, on
the same development predictions. Then τW := min(τW, τA). If τW = τA, the WATCH band is empty;
this is reported, not adjusted. WATCH has no role in any endpoint.

### 3.7 Secondary curve summaries
- Partial area over 0.5–2.0 FA/day: the trapezoidal area under S(F), using the first-crossing
  path. Points after the first crossing of 2.0 are excluded, and the curve is linearly
  interpolated at exactly 0.5 and 2.0. The area is normalised by 1.5.
- Curves for display are computed until F first exceeds 4.0 FA/day.

## 4. Freeze requirement
Sections 1–3 are frozen together with the code that implements them. Implementation tests (S5)
must include fixtures for:
- non-monotone FA under cooldown;
- `budget_not_reached`;
- k* = 1;
- an exact hit at F_a = B;
- tie handling;
- the M0 strict inequality;
- OUTCOME-UNKNOWN classification at recording ends.

## 5. Primary analysis, bootstrap, secondary and sensitivity analyses

Status: **DRAFT (S5), awaiting owner approval. Required before freeze; not blocking S6
development work.** Implementation: `src/hyposense/evaluation/`. Metric definitions:
`artifacts/evaluation/metric_registry.json`, generated from `evaluation/registry.py`.

### 5.1 Primary analysis (Blueprint §15, Table 20.1; unchanged)
- **Endpoint:** Δ = sens@1FA(M3) − sens@1FA(M2), for E-treated patients, on pooled
  out-of-fold predictions.
- **Rules:** the §2 policy-replay semantics and the §3.4 first-crossing rule.
- **H1 is supported iff** the lower bound of the 95 % paired patient-cluster bootstrap interval
  of Δ is greater than 0.

### 5.2 Bootstrap (Blueprint Table 20.1, App. E; `configs/default.yaml` `bootstrap`)
- **Settings:** B = 2,000 resamples, seed 2027, percentile 95 % interval.
- **Unit:** the patient. All of a drawn patient's recordings, episodes and prediction times
  travel together. Readings, windows and episodes are never resampled on their own.
- **Multiplicity:** a patient drawn k times counts k times (weights = draw counts).
- **Pairing:** one set of draws, shared by both models. Δ is computed on each resample;
  separate intervals are never compared.
- **Each resample** re-applies the full §3.4 rule on its own curve. The implementation evaluates
  per-patient step functions on the pooled grid. A grid value that is not a resampled patient's
  score repeats an adjacent point of the resample's own curve, so first-crossing values and
  areas are exactly those of the resample's own grid.
- **G5 (Table 21.1):** the number of resamples in which a statistic is undefined (no episodes)
  is reported. G5 requires it to be 0 for both models.

### 5.3 Implementation clarifications of §2–3 (S5)
None of these changes a number on the current tuning data. Each is tested.
1. **Cooldown scope.** The 60-min cooldown runs within a recording; each recording is one state
   (§0 item 10). The recordings of a patient do not overlap in time (MEASURED on T).
2. **Ties are exact.** M0 projections and CGM slopes are computed in exact rational arithmetic on
   the 0.1 mg/dL data grid and rounded once (ADR-036). Mathematically equal scores are therefore
   bitwise equal and switch together (§3.4). A projection exactly equal to θ does not alert,
   because the rule is strict.
3. **Partial area (§3.7).** Each segment of the first-crossing path is clipped to [0.5, 2.0]
   FA/day and integrated with its sign, so a non-monotone stretch counts as the path runs. For a
   monotone curve this is the ordinary trapezoidal area. The M0 curves on T have 0 non-monotone
   steps.
4. **Window-level metrics** (log-loss, Brier, AUPRC, calibration) are defined only for
   probabilities. M0 has none, so they are reported as not applicable, never forced.
5. **Abstention coverage (Table 20.2).** The share of CGM readings in INSUFFICIENT DATA, plus the
   number of warnable episodes with no forecast at any label-eligible reading of their warning
   window.

### 5.4 Secondary, sensitivity and robustness analyses
Blueprint Table 20.3 (S1–S7, SA1–SA8, R1–R4) and §0c SA9 apply unchanged. Each reuses §2–3
and §5.2 exactly. Development (T) results are labelled DEVELOPMENT and are never pooled with
confirmatory results.

## 6. Interpretation matrix and model-selection rule
PENDING (S5). Blueprint §15 and Table 20.4 apply unchanged.
