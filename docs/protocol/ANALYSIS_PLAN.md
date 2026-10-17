# HypoSense Twin v2 — Statistical Analysis Plan (pre-registration)

**Status: DRAFT v0.1 — sections 1–4 APPROVED by the project owner (2026-10-18); sections 5–6
pending (S5).** This file is hashed into the freeze manifest (ADR-012). After freeze it may not
change. Before freeze, a change to an APPROVED section requires a new owner approval recorded
in [../DECISION_LOG.md](../DECISION_LOG.md).

Baseline definitions (episode, prediction time, hit, notification, false alert, treated) are
those of Blueprint v2.0 Table 5.1 and are not restated here. This plan fixes the operational
details the blueprint left open.

---

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
PENDING (S5). Blueprint §20 (Tables 20.1–20.4) applies unchanged until this section is written.

## 6. Interpretation matrix and model-selection rule
PENDING (S5). Blueprint §15 and Table 20.4 apply unchanged.
