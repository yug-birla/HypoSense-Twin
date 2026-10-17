# Blueprint v2.0 — Structured Digest

Source: [HypoSense_Twin_v2_Blueprint.docx](HypoSense_Twin_v2_Blueprint.docx) (authoritative),
sha256 `c052df9130ecb61cec120f575a740b3d474de1dac806ef70df6e46b8084a4bcb`.
Searchable text: [blueprint/HypoSense_Twin_v2_Blueprint.extracted.md](blueprint/HypoSense_Twin_v2_Blueprint.extracted.md).
Digest written 2026-10-18. Section references (§) are to the blueprint.

This digest only summarises the blueprint. Where the digest and the .docx disagree, the .docx
wins. Proposed deviations are in [PROPOSALS.md](PROPOSALS.md), not here.

Classification used below:
**REQUIRED** · **RECOMMENDED** · **OPTIONAL** (gated or time-permitting) · **EXPERIMENTAL** ·
**REJECTED** · **PENDING** (needs an action or evidence) · **ASSUMPTION**.

---

## 1. Objective and intended use

- **System**: a per-patient state engine (the "twin") that updates at every 15-min CGM reading.
  It carries an explicit time-resolved **medication exposure state** computed from logged
  doses with fixed population pharmacokinetic kernels. This state feeds a calibrated LightGBM
  risk model and a frozen, auditable alert policy (§1, §4.1).
- **Prediction task**: at each permitted reading t, P(a CGM-detected L1 episode begins in
  (t, t+60 min]), using only data timestamped ≤ t (§5.1).
- **Intended use**: a retrospective, **silent-mode**, inpatient-ward decision-support research
  prototype. The user is a ward nurse or diabetes educator. The decision supported is "whom to
  check with a capillary glucose in the next 15–30 min" (§5.3). **ASSUMPTION**: the setting is
  inpatient-like.
- **Never**: dose advice, insulin adjustment, diagnosis, patient-facing messages, automatic
  escalation, a "safe" label, medication what-if (§5.3, §16.3).

## 2. Research hypothesis (confirmatory, single) — §6.1

**H1**: in **treated** patients of the sealed evaluation partition **E**, episode sensitivity at
**1.0 false alert per patient-day** is higher for **M3** (M2 + exposure) than for **M2**. The
learner, hyperparameters, folds, seeds, calibration and threshold rule are all the same.
**Supported only if** the paired 95% patient-cluster bootstrap interval of Δ = sens(M3) − sens(M2)
excludes 0 (B = 2000, seed 2027). The estimate is reported whatever it is.
Detectable effect ≈ 10–20 percentage points (§8.6, Table 8.4). A null result means "no large
effect detected".

## 3. Definitions (§5.2, Table 5.1) — REQUIRED, Class C

| Term | Definition |
|---|---|
| L1 episode | Onset = first of ≥2 consecutive CGM <70 mg/dL with spacing ≤20 min. End = first of ≥2 consecutive ≥70, or a gap >30 min, or record end |
| L2 | Same rule at 54 mg/dL (secondary) |
| Single-reading episode | Any reading <70 outside an episode (SA1 only) |
| Prediction time t | CGM(t) ≥70; not in an episode; not within 60 min after an episode end; ≥7 of the last 8 readings; ≥60 min follow-up **or** onset within it |
| Positive | L1 onset in (t, t+60] |
| Hit | ≥1 prediction time with state ALERT in [onset−60, onset−15]. Lead = onset − earliest such ALERT |
| Notification | ALERT and no notification in the previous 60 min (cooldown). The ALERT state persists while p ≥ τA |
| False alert | A notification with no onset in (t, t+60] |
| FA/patient-day | false alerts / Σ recording durations |
| Primary operating point | sens at exactly 1.0 FA/day, by linear interpolation on the operating curve |
| Deployed point | τA = lowest threshold with development FA ≤1.0/day; frozen before E is opened |
| Treated patient | Logged insulin (any route) or SU or glinide in any recording. Defines the population only; **never a feature** |

Readings <80 mg/dL are **not** excluded (v1's rule removed the last warnable reading in 88% of episodes).

## 4. Data (§8) — ShanghaiT2DM, CC BY 4.0

Audit numbers are **VERIFIED on a GitHub mirror only**. Neither the audit scripts nor the
partition file are in this repository.
- 100 patients, 109 recordings (patient = file-name prefix), 112,287 CGM readings on the mirror
  vs 112,475 published (−188, Gate G0), 1168.8 patient-days, FreeStyle Libre H at 15-min sampling.
- L1: 348 episodes in 61 patients. 210 are in the 73 treated patients; 138 (40%) have no logged
  hypoglycaemic drug. L2: 96 in 26.
- 88% of episodes are warnable at H=60. Prediction times: 107,041, of which 1.11% are positive.
- Medication parse rates: insulin 99.8%, oral 100%. Entries sit on CGM rows (15-min
  resolution). SU appears in 15 recordings (14 patients), glinide in 3.
- Label validity (**G3b triggered**): CGM − CBG = −12.5 mg/dL. Only 11/65 episodes with a
  concurrent capillary value were confirmed <70. Hence the name "CGM-detected" and the
  capillary-check action.
- Never used: the summary field "Hypoglycemia (yes/no)" (§N2).
- Partition: T = 30 patients (22 treated, 56 treated episodes), E = 70 patients (51 treated;
  154 treated episodes in 30 patients). Seed 2026, stratified by treated × has-episode.
  Effective cluster size m_w = 9.23.
- Exploratory M0 on T: 0.64 sensitivity at 1.07 FA/day (θ = 55 mg/dL), median lead 45 min.

## 5. Architecture (§9, Fig. 9.1)

Live path: **Data Adapter & Validator** → **Patient State Engine** (CGM state, Medication
Exposure State, data-quality status, forecast–outcome ledger) → **Feature Builder** (causal
snapshot) → **Risk Model** (LightGBM + isotonic) → **Decision Policy** (frozen) →
**Explanation** (grouped TreeSHAP and an exposure timeline taken from the state) → **Ward
Board / Patient Review / Evidence view** → clinician acknowledgement.
Offline only: **Label Builder**, **Evaluation Harness**, frozen artefacts.

## 6. Model ladder (§11, §19) — REQUIRED

| Model | Inputs (App. D groups) | Role |
|---|---|---|
| M0 | Trend rule: 30-min slope projected to t+60, ALERT if < θ | Baseline (C0) |
| M1 | CGM groups 1–3 + time (4) | Baseline; **hyperparameters tuned here** |
| M2 | M1 + static context (5) + meal timing (6) | **Primary comparator** |
| M3r | M2 + raw dose timing (7) | Representation check (C2a/C2b) |
| M3 | M2 + exposure state (8) | **Proposed model** |
| M4 | M3 + physiology (9) | **OPTIONAL**, only if Gate G6 passes; exploratory |

Fairness: the same patients, folds, seeds and hyperparameters (chosen for M1) for every
learned model, with the same calibration and threshold procedure. No extra tuning trials.

Learner (§11.1): LightGBM binary log-loss, no class re-weighting, no monotone constraints in
the core. Optuna ≤30 trials on T with inner grouped CV, objective mean log-loss. Isotonic
calibration on inner out-of-fold predictions. Deterministic: seed 2026, one thread.

## 7. Medication exposure (§12, App. B–C) — REQUIRED

- Four distinct things: prescribed regimen (static → M2), recorded administration, estimated
  exposure (→ M3), observed effect (CGM; never assumed).
- Kernel classes: rapid analogue, regular human, premix analogue and premix human (weighted
  sums), NPH, basal analogue (flat after a 1 h lag over 24 h), CSII regular (basal rate as
  15-min micro-boluses), SU and glinide (Bateman, peak-normalised, dose / D_max). i.v. insulin
  is a flag only (last 4 h). Metformin, AGI, DPP-4, SGLT2, TZD and GLP-1 are presence flags only.
- Eq. 1–2: activity and on-board. Eq. 3–4: OpenAPS exponential curve (t_peak, t_dur). Eq. 5–6:
  Bateman. Projections to t+30 and t+60 use past doses only.
- Missing timing: regimen lists the class but there is no entry in 36 h → features **missing,
  not zero**, a "timing unknown" indicator and a UI badge. Logged-but-not-prescribed → use the
  logged entry and flag the conflict. Gliclazide formulation is inferred from the dose multiple
  (**ASSUMPTION**) and flagged.
- Parameters are fixed, population-level and taken from labels, with pharmacist review before
  freeze. **PENDING** (all values are currently ILLUSTRATIVE). SA6 scales durations ×0.75 and ×1.5.

## 8. Policy (§14, Table 14.1) — REQUIRED, deterministic, separate from the model

Rules in priority order:
1. SYSTEM ERROR (artefact hash mismatch or inference exception).
2. INSUFFICIENT DATA (no reading, gap >20 min, <7/8 readings, warm-up <2 h, reading ≤40 or
   |rate| >4 mg/dL/min).
3. LOW NOW (CGM <70, in an episode, or <60 min after one).
4. ALERT (p ≥ τA; notify on a 60-min cooldown).
5. WATCH (τW ≤ p < τA).
6. NO ALERT (never "safe").

LOW CONFIDENCE and timing-unknown tags never downgrade ALERT. τW = development
"notification-equivalent" rate ≤3.0/day. No k-of-n persistence in the core. JSONL decision and
acknowledgement logs. Four acknowledgement reason codes.

## 9. Evaluation (§15, §20) — REQUIRED, Class C

Design on T only, then freeze, then unseal E. E uses 5 grouped folds; training data =
T ∪ (E∖k); calibration and τ come from inner OOF predictions. OOF predictions are pooled for
the operating curves. The primary result is Δ at 1.0 FA/day on E-treated with a 2000-resample
paired patient bootstrap. Secondary analyses: S1–S7. Sensitivity analyses: SA1–SA8.
Robustness: R1–R4 (Table 20.3). Interpretation matrix: Table 20.4. Model-selection rule: §15.
Demo cases are replayed from E out-of-fold predictions. Gates G0–G7 (Table 21.1).

## 10. Interface (§17, §23)

Three screens: **Ward Board**, **Patient Review** and **Evidence view**. Badges carry text,
never colour alone. A provenance badge reads "replay of held-out record". Seeded TP/FN/FP case
selection uses seed 2026 and is recorded in demo/cases.json. The data honesty card is shown
first. Replay runs at ×120. Two runs must produce an identical decision-log hash (G7).

## 11. Classification of blueprint elements

| Status | Elements |
|---|---|
| **REQUIRED** | Official-data audit + gates G0–G5, G7; adapter; labels; drug dictionary; kernels; state engine; causal features; M0, M1, M2, M3r, M3; nested calibration + τ selection; evaluation harness with cluster bootstrap; frozen policy; replay + API; Ward Board, Patient Review, Evidence view (from results.json); README, model card, honesty card; architecture document; deck; ≥20-min video; truncation-equality test; freeze guard; decision/ack logs; deterministic replay (§27) |
| **RECOMMENDED** | Docker image for the demo; offline run; p95 latency <200 ms; per-patient forest plot; Indian clinician case review (future, §5.4) |
| **OPTIONAL** (gated) | E1/M4 (G6); risk bands instead of % (if calibration slope is outside 0.8–1.25); LR robustness R3 (time permitting); carbohydrate estimation E3; per-drug-class and bedtime analyses |
| **EXPERIMENTAL** | M4; any challenger (CLAUDE.md §6) |
| **REJECTED** | ODE + UKF on the predictive path; empirical-Bayes priors; nightly MAP refits; per-horizon residual heads; conformal bands; OOD Mahalanobis; ensembles; what-if (meal and medication) engine; LLM report writer; agents; drift monitor; six screens; patient-ID embeddings; RNN/transformers; per-patient fine-tuning; class re-weighting; k-of-n persistence in the core; monotone constraints in the core; exclusion of readings <80; the "Hypoglycemia (yes/no)" field; external-validation claims; FHIR/ABDM; patient-facing app; synthetic data in any metric; **Streamlit** (rejected by the project owner, 2026-10-18) |
| **PENDING** | Official copy + G0 reconciliation; production kernel values + pharmacist review; partition file; G4, G5, G7; competition rules and deadline confirmation; clarifications in PROPOSALS.md |
| **ASSUMPTION** | +08:00 timestamps; dose entries ≈ administration time (±15 min); inpatient/supervised setting; mirror ≈ official copy except 188 readings; gliclazide formulation from dose multiples; labs within ±6 months (SA8) |

## 12. Competition facts (all **REPORTED**, unverified)

Happiest Health Digital Twin Challenge 2026 (Unstop). Registration closes **18 Oct 2026,
19:00 IST**. The event ends 20 Nov 2026. The Phase-1 deadline and rubric are not public.
Deliverables: public repository, README, licence, architecture document, deck, video of
**≥20 min**, folder named `TeamName_CollegeName`.
