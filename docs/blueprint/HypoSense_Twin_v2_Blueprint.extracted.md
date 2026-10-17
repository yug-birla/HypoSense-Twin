<!-- MACHINE EXTRACTION of the blueprint .docx. The .docx is authoritative. -->
<!-- source: docs/HypoSense_Twin_v2_Blueprint.docx  sha256: c052df9130ecb61cec120f575a740b3d474de1dac806ef70df6e46b8084a4bcb -->
<!-- regenerate: python -I scripts/extract_blueprint.py <docx> <md> -->

HAPPIEST HEALTH DIGITAL TWIN CHALLENGE 2026
HypoSense Twin
Redesigned Solution Architecture, Research Blueprint, and Competition Demonstration Plan
Version:  2.0 (supersedes Blueprint v1.0)
Date:  17 October 2026
Prepared for:  The HypoSense Twin team
Document status:  Redesign blueprint. Feasibility audit executed on real records (mirror copy of ShanghaiT2DM). No predictive model trained; no performance or clinical benefit is claimed.
Intended use of the system:  Research and decision-support prototype for retrospective, silent-mode evaluation. Not a medical device. Never recommends doses.
Data: ShanghaiT2DM (Zhao et al., Scientific Data 2023; CC BY 4.0). No identifiable patient data appear in this document; interface mock-ups use synthetic values and are labelled.
How to read this document
Part I (Sections 1–4) is a self-contained competition summary: problem, recommendation, what changed and why, and the decision record. Part II gives the scientific basis and the data audit. Part III specifies the system. Part IV specifies the experiments, gates and result templates. Part V is the delivery plan. Appendices hold implementation detail, the source and assumption register, and references.
Every important statement carries one of these tags:
Table 0.1. Status legend.

| Tag | Meaning |
|  VERIFIED  | Checked in this review against a primary source, or computed from the data by the audit script |
|  REPORTED  | Stated in a cited source (often the v1.0 blueprint) but not independently re-checked here |
|  INFERRED  | Reasoned from verified facts; no direct measurement |
|  ASSUMPTION  | Taken as true for design purposes; listed in Appendix I with the check that would confirm it |
|  HYPOTHESIS  | A claim the experiments will test; not yet supported |
|  PENDING  | Requires an action or experiment that has not been done; result fields are empty |
|  ILLUSTRATIVE  | Example values or synthetic graphics for explanation only — never results |


| Key numbers from the audit (ShanghaiT2DM mirror copy) / 100 patients · 109 recordings · 112,287 CGM readings · 1168.8 patient-days  VERIFIED  / 348 CGM-detected L1 episodes in 61 patients; 210 in 73 treated patients  VERIFIED  / Sealed evaluation partition: 154 treated-patient episodes in 30 patients  VERIFIED  / Dose entries parse to drug + amount: 99.8% (insulin), 100% (oral)  VERIFIED  / CGM − capillary glucose: mean -12.5 mg/dL; 11/65 episodes with a capillary value confirmed <70  VERIFIED  |

Document control
Table 0.2. Version history.

| Version | Date | Change |
| 1.0 | 17 Oct 2026 | Original blueprint: hybrid ODE + UKF + LightGBM twin, six screens |
| 2.0 | 17 Oct 2026 | Redesign after evaluation: data audit executed; physiology removed from predictive path; exposure-state twin; rebuilt evaluation protocol, gates and scope |

Contents
PART I · EXECUTIVE AND COMPETITION STRATEGY

# 1. Executive Summary

| Competition summary — readable on its own / Problem. Adults with type 2 diabetes (T2D) treated with insulin or insulin secretagogues (sulfonylureas, glinides) have frequent low-glucose episodes, many of which are not noticed. On a ward, capillary checks follow a timetable rather than individual risk. / Recommendation. Build HypoSense Twin v2: a per-patient state engine (“the twin”) that updates at every CGM reading, carries an explicit, time-resolved medication exposure state computed from logged doses with fixed pharmacokinetic kernels, and feeds a calibrated gradient-boosted risk model and a frozen, auditable alert policy. It forecasts whether a CGM-detected Level 1 hypoglycaemia episode will begin within the next 60 minutes and prompts a human to check — it never recommends doses. / Central claim to test (one, pre-specified). In medication-treated patients, adding time-resolved exposure (M3) to a strong CGM-plus-context model (M2) increases the share of episodes warned at least 15 minutes ahead at a budget of 1.0 false alert per patient-day. Supported only if the paired 95% patient-cluster bootstrap interval excludes zero.  HYPOTHESIS  / Evidence status. A data feasibility audit has been run on real records (a GitHub mirror of ShanghaiT2DM that matches the published file count): 348 CGM-detected Level 1 episodes in 61 of 100 patients; 210 of them in the 73 patients with logged insulin or secretagogue doses; dose entries parse to drug and amount in 99.8–100% of cases.  VERIFIED  No predictive model has been trained; no performance claim is made. / Biggest honest caveat. The CGM reads on average 12.5 mg/dL below capillary glucose, agreement around 70 mg/dL is poor, and only 11 of 65 CGM episodes with a capillary value taken during the episode were confirmed below 70 mg/dL. The target is therefore named a CGM-detected low, and the clinical action is a capillary confirmation, not treatment.  VERIFIED  |


## 1.1 Problem
HypoSense Twin set out to forecast hypoglycaemia in insulin- and sulfonylurea-treated T2D before it occurs, using a medication-aware virtual patient. The supplied evaluation found the idea clinically meaningful but the original design (v1.0) unproven on five fronts at once: whether dose-timed medication data exist, whether enough events exist, whether medication information adds anything beyond a CGM trend, whether the physiological model and Kalman filter add anything at all, and whether the evaluation rules were internally consistent. This document is the response: a redesigned, narrower and testable solution, with the feasibility questions answered from data wherever the data could be reached during this review.

## 1.2 Recommended solution in one paragraph
HypoSense Twin v2 replaces the eight-state physiological model and unscented Kalman filter on the predictive path with a smaller, more defensible twin. The twin keeps four explicit, inspectable state blocks per patient — the CGM state, the Medication Exposure State, the data-quality status, and a forecast–outcome ledger — and updates them at every 15-minute reading. The exposure state is mechanistic where the science is population-level and stable (how long a given insulin formulation or sulfonylurea acts after a recorded dose) and does not attempt to estimate patient-specific physiology that 15-minute CGM alone cannot identify. A single LightGBM classifier with isotonic calibration produces the risk; a deterministic policy with frozen thresholds turns risk into ALERT, WATCH, NO ALERT, LOW NOW or INSUFFICIENT DATA; and a clinician acknowledges every alert with a reason code.
Figure 1.1. Problem, limitation, insight and value. Solid boxes are established facts or design elements; dashed boxes are hypotheses or evidence still to be produced. The human action sits outside the system.

## 1.3 Central innovation and expected value
The innovation is not a new algorithm. It is the combination of (i) an explicit, time-resolved medication exposure state inside a patient twin, (ii) a pre-registered ablation that isolates its value against a strong CGM-plus-context baseline using the same learner, folds and threshold rule, and (iii) an evaluation built around what a ward can act on — episodes warned at a fixed false-alert budget, with lead time. If the hypothesis holds, the expected value is more warnings with time to act, at no extra alert burden, specifically in the patients whose lows are drug-driven. If it does not hold, the project still delivers a validated, honest warning system built on the best baseline, plus a quantified negative result that answers a question the field cares about.

## 1.4 What is and is not claimed
Table 1.1. Claim boundaries. Status tags follow the legend on page 2.

| Statement | Status |
| ShanghaiT2DM contains enough CGM-detected episodes and dose-resolved medication records to run the primary test | Verified on a mirror copy; to be re-run on the official copy  VERIFIED  |
| A simple trend rule warns roughly two-thirds of episodes at about one false alert per patient-day (tuning partition only) | Exploratory measurement: 64% at 1.07 FA/day  VERIFIED  |
| Time-resolved medication exposure improves warning beyond CGM + context | Primary hypothesis  HYPOTHESIS  |
| A physiological model adds value beyond exposure features | Not expected; optional gated extension  HYPOTHESIS  |
| The system reduces hypoglycaemia, admissions or harm | Not claimed; would need prospective studies  PENDING  |
| The system works in Indian patients | Not claimed; no Indian data used  PENDING  |


# 2. Competition Positioning

## 2.1 What the competition asks for
The official listing could not be rendered during this review, so the requirements below are carried over from the original blueprint (which cites the Unstop listing) and must be re-checked against the organiser’s rules before submission.
Table 2.1. Competition requirements and how the redesign meets them.

| Requirement (as reported) | How v2 satisfies it | Status |
| One chronic or lifestyle condition prevalent in India | T2D treated with insulin and/or secretagogues |  REPORTED  |
| Fuse static/historical and dynamic data | Static record + dose log + meal log + CGM stream, fused in a causal feature snapshot |  REPORTED  |
| Maintain a virtual patient state that updates as data arrive | Patient State Engine with four explicit state blocks, updated every reading |  REPORTED  |
| Forecast an adverse event before it occurs | Onset of a CGM-detected L1 episode within 60 minutes, warned ≥15 minutes ahead |  REPORTED  |
| Clinician-facing interface | Ward Board, Patient Review and Evidence view |  REPORTED  |
| Anonymised, open or synthetic data only | ShanghaiT2DM (CC BY 4.0); no synthetic data in any reported metric |  REPORTED  |
| Public repository, README, licence, architecture document, deck, video of at least 20 minutes, folder named TeamName_CollegeName | Section 27 deliverables matrix |  REPORTED  |
| Registration before 18 Oct 2026, 19:00 IST; event ends 20 Nov 2026; Phase-1 deadline and rubric weights not public | Treat registration as urgent; ship a submittable version early (Section 26) |  REPORTED  |


## 2.2 The most defensible differentiation
v1.0 argued differentiation from a survey of other teams’ repositories. That argument is weak — repositories change daily and judges rarely reward claims about competitors. v2 differentiates on things that can be shown on the day:
- A real, acute adverse event with a published consensus-style definition, applied consistently and reproducibly from CGM alone.
- Feasibility measured, not assumed. Event counts, dose-record usability and label validity come from an executable audit of the actual dataset, with the script in the repository.
- One pre-registered question, answered against a strong baseline. The model ladder isolates exactly one change — time-resolved exposure — with everything else held fixed.
- Evaluation a reviewer would accept. Patient-level separation, a sealed evaluation partition, episode-level sensitivity at a false-alert budget, paired patient-cluster bootstrap intervals.
- Honesty about the sensor. The label-validity finding is presented, not hidden, and shapes the clinical action.

## 2.3 What judges must be able to see
- One headline figure: operating curves (episode sensitivity vs false alerts per patient-day) for M0–M3 on held-out treated patients, with the M3 − M2 difference at 1.0 false alert per patient-day and its confidence interval.
- The model ladder (Figure 19.1) so that the comparison is obviously fair.
- A live replay of real held-out records showing a correct warning, a miss and a false alert, chosen by a seeded rule rather than by hand.
- The data honesty card: what is real, what is replayed, what is derived, and the label-validity caveat.
- The twin’s state changing as readings and doses arrive — the exposure curve rising after a logged dose before glucose falls.

# 3. Original vs Redesigned Solution

## 3.1 What is preserved, changed, removed and added
Table 3.1. Disposition of every major v1.0 element.

| Element | v1.0 | v2 decision | Reason |
| Target event | CGM onset <70 mg/dL ≥15 min within 60 min | Preserved, renamed “CGM-detected L1 episode”; one definition set | Clinically meaningful; label validity issue requires honest naming |
| Population | Insulin/SU-treated T2D; headline on subgroup | Preserved as primary population (“treated”: insulin or SU or glinide logged) | 40% of episodes occur without logged hypoglycaemic drugs |
| Patient-level splits, leakage controls | GroupKFold by patient | Preserved and strengthened: sealed evaluation partition, protocol hash | Removes researcher-iteration leakage |
| Event-level metrics, false-alert budget | Yes, with inconsistent windows | Preserved, made consistent (Section 5.2) | Conflicting definitions in v1.0 |
| Mechanistic core | 8-state extended minimal model + UKF + empirical-Bayes priors + nightly MAP refits | Removed from the predictive path; replaced by fixed pharmacokinetic exposure kernels; reduced physiology only as optional E1 | Unidentifiable, no counter-regulation, unproven value |
| Learner | LightGBM event head + per-horizon residual heads | Changed: one LightGBM event model, isotonic calibration | Residual heads only served the removed ODE |
| Uncertainty | UKF covariance, conformal bands, OOD Mahalanobis, ensembles | Simplified: input sufficiency, calibration reliability, out-of-range flags | Each retained check maps to a user-visible state |
| Baselines | B0–B7 + P2; no arm isolates medication information | Rebuilt as ladder M0–M3 (+M3r, optional M4) | Isolates one change per step |
| Comparison method | Non-overlapping bootstrap CIs | Replaced by paired patient-cluster bootstrap of differences | Overlap test is invalid and underpowered |
| What-if scenario engine | Meal-timing scenarios, validation A/B | Removed | Not needed for the central claim; risk of causal over-reading |
| LLM report writer | Optional P2 | Removed | No contribution to the claim |
| Drift monitor, nightly refits | Yes | Removed | Retrospective replay has no deployment drift to monitor |
| Screens | Six screens + model card | Reduced to Ward Board, Patient Review, Evidence view | Effort moved to validation |
| Clinical use case | Educator monitoring 8–20 patients, remote or ward | Narrowed: retrospective, silent-mode inpatient ward prototype; action = capillary check | Matches data and a plausible workflow |
| Feasibility gate | Event count only (≥60 in ≥20 patients) | Expanded to gates G0–G7 incl. medication usability and label validity, with fallbacks | Data-first design |
| Data audit | Planned | Executed on a mirror copy; script included | Removes guesswork |


## 3.2 Issue register
The supplied evaluation report was not provided as a separate file; its findings were provided as the issue list in the redesign brief. Each issue was checked against the v1.0 blueprint (cited by section, “v1 §x”) and, where possible, against the data. Status: Verified (the problem exists as stated), Partially supported (exists but differs in nature or size), Unresolved (cannot be settled without an experiment), Potentially incorrect (evidence contradicts it). Issues N1–N11 were not raised by the evaluation.
Table 3.2. Issue register. Counts are from the audit of the mirror copy (Section 8).

| ID · area | Reported issue → source | Assessment and evidence | Effect → resolution in v2 |
| I1 · Data feasibility | Dose-resolved insulin/SU records may not exist or be usable → v1 §9.1, §9.3 (gate checked events only) | Partially supported → largely resolved. Audit: 825/827 insulin entries and 2166/2166 oral entries parse to product/drug and dose; entries sit on the 15-min CGM grid; logged on a median 97% of calendar days in treated recordings. Unresolved: charting vs administration time; gliclazide formulation; i.v. infusion rates absent. | Gate G3 with fallback; dose-time jitter robustness test; formulation rule (App. B) |
| I2 · Event feasibility | Too few episodes; uneven across folds → v1 §9.3, §6.2 | Concern verified; size resolved. 348 L1 episodes in 61 patients; 154 in 30 treated patients of the evaluation partition; but concentrated (top 5 patients hold 27%; effective cluster size m_w ≈ 9.23). | Gate G2 on CI precision, not raw count; patient-cluster bootstrap; per-patient reporting |
| I3 · Core hypothesis | No evidence that medication features help → v1 §7, §12.1 | Verified. Also found: no v1 arm isolates medication information — B3 → B5 changes physiology, filtering, priors and features at once, and B7 removes medication states only inside the full hybrid (v1 §12.1). | Ladder M2 → M3 isolates exposure; M3r tests representation |
| I4 · Model necessity | ODE + UKF may add nothing beyond GBM → v1 §10–11 | Verified as unjustified. No experiment; small-data benchmark evidence favours simple models (GlucoBench, as reported in v1 [R8]). | Removed from predictive path; optional E1 behind Gate G6 |
| I5 · Physiological validity | No counter-regulation; unreliable near low glucose → v1 §10.2 | Verified by inspection. The equations contain no glucagon/adrenaline response; the only restoring term is linear glucose effectiveness, so projected lows are likely too deep and too long. | Section 13; any counter-regulation term must pass an explicit low-range test |
| I6 · Identifiability | Too many states/parameters for the observations → v1 §10.3, §30.2 | Verified (structural argument). 8 states and 7 personal parameters observed through one 15-min CGM channel, without insulin measurements or reliable carbohydrate inputs. | No patient-specific pharmacodynamic parameters; fixed population kernels |
| I7 · Input quality | Medication, meal, activity reliability → v1 §9.5 | Partially supported. v1 planned a Chinese food-name carbohydrate lookup (v1 §9.5), but an English column with weighed items also exists; 742 of 3802 diet entries read “data not available”; the activity input of the v1 model has no data in ShanghaiT2DM. | Meal timing only in core; carbohydrate estimation deferred (E3) |
| I8 · Statistical power | Wide CIs; subgroup conclusions unreliable → v1 §8.2 | Verified and quantified. Minimum detectable paired difference ≈ 0.10–0.21 in sensitivity (Table 8.4). | Estimation framing; pre-set decision rule; log-loss as powered secondary; subgroups exploratory |
| I9 · Evaluation consistency | Conflicting warning definitions; inadequate comparison → v1 §8.2, §10.4, §15.3, §21.3 | Verified. “≥10 min before onset” (v1 §8.2) vs “[onset − 60, onset − 5]” (v1 §21.3); exclusion of readings <80 mg/dL from evaluation (v1 §10.4) while the alert policy breaks its cooldown when “G <80 and falling” (v1 §15.3). Audit: the reading just before onset was <80 mg/dL in 307 of 348 episodes, so the exclusion removes the last chance to warn for most episodes. | One definition set (Section 5.2, Figure 5.1); paired cluster bootstrap |
| I10 · Clinical workflow | Unclear recipient, action, response time → v1 §8.1 | Verified. | Inpatient silent-mode use case; capillary check; acknowledgement reason codes |
| I11 · Generalisability | Chinese/US data vs Indian context → v1 §23 | Verified (v1 acknowledged it). | Section 5.4 evidence separation; Indian clinician review as next step |
| I12 · Demo integrity | Constructed patients; cherry-picking → v1 §13, §28 | Partially supported. v1 labelled mock-ups, but the storyboard is built around a “scripted moment” and a scripted two-patient contrast. | Seeded case selection from held-out predictions; TP, FN and FP shown |
| I13 · Scope | Too many features → v1 §26 | Verified. | Deliverables matrix; removed scenario engine, LLM, drift, conformal |
| I14 · Documentation | Long internal blueprint, no concise narrative → v1 (60 pp.) | Verified. | Part I is self-contained; detail moved to appendices |
| I15 · Differentiation | No evidence the core innovation works → v1 §7, §30.4 | Verified. | Differentiation rests on the experiment and its rigour; narrative survives a null result |
| N1 · Label validity | Not raised | New, verified. CGM − capillary mean -12.5 mg/dL (MARD 12.9%); poor agreement at 70 mg/dL in both directions; 11/65 episodes with a capillary value during the episode confirmed <70. Consistent with published FreeStyle Libre Pro data in hospitalised T2D [6]. | Gate G3b; “CGM-detected” naming; capillary check as action; discordance sensitivity analysis |
| N2 · Dataset label field | Not raised | New, verified. The summary field “Hypoglycemia (yes/no)” is “no” for 54 recordings that contain CGM episodes. | Never used as label or feature |
| N3 · Recording ≠ patient | Not raised | New, verified. 109 recordings from 100 patients. | Group by patient prefix; unit test |
| N4 · Untreated episodes | Not raised | New, verified. 138 of 348 episodes occur with no logged insulin or secretagogue. | Primary population = treated; all-patient analysis secondary |
| N5 · Uninformative absolute targets | Not raised | New, verified (exploratory). v1 target “≥70% warned at ≤1 FA/day” is close to what the trend rule alone achieves on the tuning partition. | Relative, paired endpoints only |
| N6 · Prescribed vs logged conflicts | Not raised | New, verified. SU prescribed but not logged in 4 recordings; logged but not prescribed in 4. | Logged administration wins; “timing unknown” flag |
| N7 · Time resolution / zone | Not raised | New, partially supported. Dose times are aligned to 15-min CGM rows; time zone unstated. | Kernels with peaks ≥ 60 min tolerate this; jitter test; +08:00 assumed |
| N8 · Mirror vs official copy | Not raised | New, verified. Mirror: 112,287 CGM values vs 112,475 published (−188). | Gate G0 before unsealing |
| N9 · Competition facts | Not raised | Unresolved. Deadlines and rubric not verifiable here. | Confirm with organisers; ship early |
| N10 · Post-dated laboratory values | Not raised | New, partially supported. The descriptor states labs were taken within 6 months before or after CGM [1]. | Patient-level context only; SA8 removes labs |
| N11 · Sensor floor | Not raised | New, verified. 329 readings at ≤40 mg/dL (device floor). | L2 depth is truncated; floor readings flagged |


# 4. Final Recommendation and Decision Record

## 4.1 Selected architecture
HypoSense Twin v2 — an exposure-aware risk twin. Primary system to build: Data Adapter & Validator → Patient State Engine (CGM state, Medication Exposure State, data-quality status, forecast–outcome ledger) → causal Feature Builder → Risk Model M3 (LightGBM + isotonic calibration) → frozen Decision Policy → Ward Board and Patient Review, with an offline Label Builder and Evaluation Harness. Minimum viable research prototype: the same chain with M2 and M3 trained and evaluated on the protocol in Section 20, and a replay of held-out records. Fallback architecture: the identical system running M2 (or M1) if the medication branch fails its gate or the primary hypothesis is not supported.

## 4.2 Alternatives considered
Table 4.1. Comparison of the alternatives required by the brief. D is A and C plus an exposure state, without the unidentifiable physiology of B.

| Criterion | A · Strong simple predictor | B · Medication-aware hybrid (ODE/UKF) | C · Risk- and uncertainty-aware warning system | D · Selected: C + exposure state (B-lite) |
| Problem–solution fit | Good; ignores the drug mechanism | Good in principle | Good; strongest on safe operation | Good; mechanism enters as data, not unidentifiable physiology |
| Originality / defensibility | Low / high | Medium / low (identifiability) | Low–medium / high | Medium / high |
| Minimum data | CGM only | CGM, exact doses, reliable carbs | CGM | CGM + timed doses (verified present) |
| Complexity | Low | High (8 states, filter, priors, refits) | Low–medium | Low–medium |
| Statistical / build risk | Low / low | High / high | Low / low | Medium / low |
| Evaluation burden | Low | High (filter stability, recovery) | Medium | Medium |
| Explainability, uncertainty | Feature attributions | Mechanistic story, but untrustworthy near low glucose | Explicit states, abstention | Exposure timeline + attributions + explicit states |
| Demo quality | Plain | Impressive but fragile | Clear | Clear, with a visible drug mechanism |
| Time / compute | Hours / CPU | Weeks / CPU | Days / CPU | Days / CPU |
| Rejected if… | Chosen as fallback, not primary: no differentiation | Rejected now: fails identifiability and validity checks | Absorbed into D | Medication gate fails → becomes A + C |


## 4.3 Decision record
Table 4.2. Architecture decision record (ADR-001).

| Field | Content |
| Decision | Build D (exposure-aware risk twin). M3 is the proposed model; M2 is the primary comparator; M0 and M1 are reported baselines. |
| Rejected | B as primary (unidentifiable, no counter-regulation, unproven value, high build risk); A as primary (no test of the central idea); multi-architecture blueprint (avoids commitment). |
| Evidence supporting the choice | Audit: events and dose logs suffice (Gates G1–G3 pass provisionally); structural identifiability argument (Section 13); the trend-only baseline is strong, so effort must go into a fair test, not into model sophistication. |
| Key trade-offs | Gives up patient-specific physiology and what-if simulation in exchange for a test that can actually succeed or fail cleanly; accepts a less “impressive” twin diagram. |
| Major unverified assumptions | Dose timestamps approximate administration (R4); kernel parameters are adequate at population level (R5); CGM-detected episodes are clinically meaningful despite sensor bias (R1). |
| Gates that reverse the decision | G3 fail → context-only branch; G4 fail → M0 as operational baseline; G6 pass → M4 added as exploratory, never primary. |
| Fallback if the innovation fails | Ship M2 (or the best of M1/M2 by the pre-specified rule) in the same twin, policy and UI; report the null result with its interval. |
| Decisions final now | Event definition, population, primary endpoint, ladder, partition, policy structure, removed components. |
| Decisions conditional on data | Thresholds τA/τW (development data); whether E1 is attempted (time and G6); whether kernels or raw timing are deployed (C2b result); the final deployed model (interpretation matrix, Table 20.4). |


## 4.4 Open evidence gates
Gates G0 (official-copy reconciliation), G4 (baseline feasibility), G5 (statistical interpretability) and G7 (demo readiness) are open; G1, G2 and G3 pass provisionally on the mirror copy; G3b has triggered and its consequences are already built into the design (Section 21).
PART II · PROBLEM AND SCIENTIFIC BASIS

# 5. Problem Definition and Intended Use

## 5.1 The prediction task
At every CGM reading time t at which a forecast is permitted (Section 5.2), estimate the probability that a CGM-detected Level 1 hypoglycaemia episode begins in the half-open window (t, t + 60 min], using only information timestamped at or before t. Turn that probability into one of five user-facing states with a frozen policy (Section 14). The system forecasts what the CGM will report, not true blood glucose; the clinical response is a capillary check.

## 5.2 One set of definitions used everywhere
v1.0 used three different warning windows and an exclusion rule that contradicted its own alert policy. v2 uses the definitions below in every section, figure, script and table. They are implemented once, in labels.py and metrics.py, and unit-tested against hand-labelled fixtures.
Table 5.1. Definitions. Readings below 80 mg/dL are not excluded — v1.0’s rule would have removed the last pre-onset reading in 88% of episodes.

| Term | Definition (ShanghaiT2DM, 15-min sampling) |
| L1 episode (primary label) | Onset at the first of ≥2 consecutive CGM readings <70 mg/dL whose spacing is ≤20 min. Ends at the first of ≥2 consecutive readings ≥70 mg/dL, or at a gap >30 min, or at the end of the record. With 15-min sampling, “≥2 consecutive readings” is the closest available operationalisation of the consensus ≥15-minute rule [3][5]. |
| L2 episode (secondary label) | Same rule with 54 mg/dL. |
| Single-reading episode (sensitivity analysis only) | Onset at any single reading <70 mg/dL outside an existing episode. |
| Prediction time t | A CGM reading at which: CGM(t) ≥70 mg/dL; t is not inside an L1 episode; t is not within 60 min after an episode ended (refractory); ≥7 of the last 8 readings (120 min) are present; and either ≥60 min of follow-up exists or an onset occurs within it. |
| Positive window | An L1 onset falls in (t, t + 60 min]. |
| Correct warning (episode hit) | At least one prediction time with state ALERT in [onset − 60, onset − 15] min. Lead time = onset minus the earliest such ALERT time. The 15-min minimum makes every hit a forecast at least one sampling interval ahead, not a detection. |
| Notification | Issued when the state is ALERT and no notification was issued for the same patient in the preceding 60 min (cooldown). The ALERT state itself persists while p(t) ≥ τA. |
| False alert | A notification at time t with no L1 onset in (t, t + 60 min]. |
| False alerts per patient-day | Number of false alerts divided by the total monitored days (sum of recording durations) of the patients evaluated. |
| Primary operating point | Episode sensitivity at exactly 1.0 false alert per patient-day, read from each model’s operating curve by linear interpolation between adjacent thresholds. |
| Deployed operating point | τA = the lowest threshold whose development (inner out-of-fold) false-alert rate is ≤1.0 per patient-day; frozen before the evaluation partition is opened. |
| Treated patient | A patient with at least one logged insulin entry (s.c., CSII or i.v.) or a logged sulfonylurea or glinide in any recording. This defines the analysis population only; it is never a model input. |

Figure 5.1. The time definitions on one synthetic trace. Features use only data up to the prediction time; the label looks 60 minutes ahead; a warning counts only if it occurs 15–60 minutes before onset; readings inside an episode and in the 60-minute refractory period are not prediction times. The dose arrow shows that a logged dose enters the exposure state at its own timestamp.

## 5.3 Clinical use case (initial setting)
Retrospective, silent-mode decision-support research prototype for an inpatient diabetes ward. This setting is chosen over live remote triage because it matches the data: the ShanghaiT2DM records include short-term insulin-pump (CSII) therapy in 35 recordings, intravenous insulin infusions in 6, roughly three capillary glucose checks per day, and weighed meals — features consistent with hospital-supervised care, although the data descriptor does not state the setting [1].  ASSUMPTION 
Table 5.2. Intended use. Prediction capability can be demonstrated retrospectively; clinical benefit cannot.

| Aspect | Definition |
| Person represented by the data | Adult with T2D wearing a professional CGM (FreeStyle Libre H, 15-min readings [1]) and receiving logged insulin and/or secretagogue doses. |
| Intended user | Ward nurse or diabetes educator reviewing a ward board; endocrinology resident for escalation. |
| Decision supported | “Which patients should have a capillary glucose check and a meal/medication review in the next 15–30 minutes?” — a prioritisation of attention, not a treatment decision. |
| When forecasts are generated | At every new CGM reading (every 15 minutes in this dataset). |
| What the user sees | State (ALERT / WATCH / NO ALERT / LOW NOW / INSUFFICIENT DATA), current CGM and 6-hour trace, logged doses and the exposure curve, data-quality status, the top contributing factor groups, and the acknowledgement panel. |
| Missing or unreliable data | INSUFFICIENT DATA (no probability) when CGM is missing or flagged; a “medication timing unavailable” badge when doses are expected but not logged (Section 14.4). |
| What it explicitly does not do | No dose advice, no insulin adjustment, no diagnosis, no patient-facing messages, no automatic escalation, no “safe” label. |
| Human role | A trained professional reviews every ALERT, acknowledges it with a reason code and acts according to local protocol and judgement. |
| How utility would be evaluated | Stepwise (Section 5.5): retrospective silent evaluation (this project) → clinician case review → prospective silent-mode pilot → only then an interventional study. |


## 5.4 Indian relevance — separated by type of evidence
Table 5.3. Indian relevance without over-claiming.

| Evidence type | What it says | What it does not say |
| From the dataset  VERIFIED  | Premixed human and analogue insulins (33 recordings), basal analogues (22), gliclazide/glimepiride/gliquidone and repaglinide appear with doses and times — regimen types that are also used in Indian practice. | Nothing about Indian patients, diets, sensors or ward workflows. |
| External research  REPORTED  | India has a very large T2D population (ICMR-INDIAB [18]); sulfonylurea-related hypoglycaemia is a recognised problem in Indian practice (as reported in v1 [19]). | Disease burden does not show that this workflow or model would work in India. |
| Expert-informed assumption  ASSUMPTION  | Ward capillary checks on a fixed timetable are common; a risk-ranked board could help prioritise them. | Needs confirmation by Indian clinicians. |
| Proposed validation  PENDING  | Smallest credible step: two or three Indian diabetologists review 30 seeded alert cases (TP/FN/FP mix) for plausibility and actionability, and confirm kernel parameters for commonly used Indian products. Next: a silent-mode pilot on an Indian ward with professional CGM and routine capillary checks, under ethics approval and DPDP-compliant consent [21]. | — |


## 5.5 Future clinical validation path
- Intended-use statement reviewed by a clinician: population, user, decision, setting, exclusions.
- Clinician case review (30 seeded cases): is the alert plausible, would you act, what is missing? Record agreement and reasons.
- Prospective silent-mode study on a ward: system runs on live CGM without showing alerts; outcomes are compared after the fact; measures sensitivity, false alerts, lead time and capillary-confirmed rates.
- Usability and workload study: alert burden, acknowledgement time, reasons recorded.
- Interventional study only after the above, with a regulatory pathway. Under India’s draft guidance on medical device software (October 2025), software for prediction or monitoring is treated as a medical device with risk-based classes [20]; a product version would need classification, clinical evidence and post-market surveillance.

# 6. Research Hypothesis and Contributions

## 6.1 Primary hypothesis

| H1 (pre-specified primary claim) / In treated patients of the evaluation partition, the episode sensitivity of M3 (CGM + static context + meal timing + time-resolved medication exposure) at 1.0 false alert per patient-day is higher than that of M2 (the same without exposure), for CGM-detected L1 episodes with a 60-minute horizon and ≥15-minute lead. / Baseline: M2 — same learner, hyperparameters, folds, seeds, calibration and threshold rule. Metric: paired difference Δ = sens(M3) − sens(M2) at 1.0 FA/patient-day. Evidence required: the 95% patient-cluster bootstrap interval of Δ excludes 0. The estimate and interval are reported whatever they are. |


## 6.2 The eight testable questions
Table 6.1. Questions, the evidence that answers each, and their status.

| # | Question (from the brief) | How it is answered | Status |
| Q1 | Enough eligible events for credible evaluation? | Audit: 154 treated L1 episodes in 30 patients of E; precision table |  VERIFIED  provisionally (G2) |
| Q2 | Medication timestamps, doses, routes, classes reliable enough? | Audit of parse rates, coverage, conflicts; jitter robustness test |  VERIFIED  parse/coverage; timing truth  PENDING  |
| Q3 | Do medication records add information beyond CGM and context? | Primary comparison M3 vs M2 (and M3r vs M2) |  HYPOTHESIS  |
| Q4 | Does an explicit exposure model add value beyond raw medication features? | C2b: M3 vs M3r |  HYPOTHESIS  |
| Q5 | Does a physiological model add value beyond data-driven features? | C3: M4 vs M3, only if Gate G6 passes |  HYPOTHESIS  |
| Q6 | Meaningful sensitivity vs false-alert trade-off at 60 min? | Operating curves for M0–M3; deployed operating-point check |  PENDING  |
| Q7 | Warnings explainable without overstating certainty? | Grouped attributions, exposure timeline, explicit states, calibration report | Design  PENDING  evaluation |
| Q8 | Most valuable system buildable in the time? | Scope matrix and staged plan (Sections 26–27) | Decided |


## 6.3 Contributions the work can support
- C1 · Verified feasibility audit of ShanghaiT2DM for medication-aware hypoglycaemia forecasting, with an executable script, event counts by patient and treatment, dose-record usability and a CGM–capillary label-validity analysis.
- C2 · A pre-registered, leakage-safe test of whether time-resolved medication exposure improves episode warning over a strong CGM-plus-context model — publishable whether positive or negative.
- C3 · A transparent twin whose exposure state is mechanistic and inspectable, with a frozen policy that abstains rather than guesses.
- C4 · An evaluation template for alerting systems on small clustered data: episode sensitivity at a false-alert budget, paired cluster bootstrap, seeded case selection.
Not claimed: novelty of LightGBM, kernels or bootstrap; clinical benefit; performance on true (capillary-confirmed) hypoglycaemia; performance in India; superiority over any commercial product.

# 7. Related Approaches and Competitive Differentiation
Table 7.1. Related approaches. v2 does not claim to outperform any of them.

| Approach | What it does | Relevance and limitation for this task | Source status |
| Trend extrapolation of CGM (our M0) | Projects recent CGM slope forward; alerts if the projection crosses a threshold | Strong at short horizons; blind to drug action; essential baseline | Measured here on T  VERIFIED  |
| Short-horizon ML on CGM history | Random forests, LSTMs etc. predicting lows at 30 min with high AUROC | High AUROC at short horizons is common and does not show episode-level usefulness or false-alert burden | As reported in v1 [R12–R14]  REPORTED  |
| Inpatient EHR-based hypoglycaemia prediction | Gradient boosting on EHR variables predicting glucose ≤70 mg/dL within 24 hours after each measurement (Johns Hopkins, ~55,000 admissions) [7] | Shows inpatient demand for hypoglycaemia risk tools; 24-h horizon and point-of-care glucose, no CGM |  VERIFIED  (secondary summary) |
| Inpatient CGM guidance | Endocrine Society 2022 guideline supports considering CGM with point-of-care confirmation for hospitalised patients at high risk of hypoglycaemia [8] | Supports the capillary-confirmation action |  VERIFIED  (press release) |
| Physiological simulators (UVA/Padova and minimal models) | Compartment models; later versions add glucagon and counter-regulation [9] | Need rich, identifiable inputs; T1D-focused; not used on the predictive path here |  REPORTED  |
| Insulin-on-board curves (open-source closed loops) | Parametric activity curves by peak time and duration of insulin action [15] | Engineering precedent for the exposure kernels |  VERIFIED  |
| CGM foundation models | Large pre-trained sequence models of CGM | Mostly trained on non-diabetic CGM; not suited to 15-min, ~100-patient data | As reported in v1  REPORTED  |

Differentiation of the final design. Compared with CGM-only prediction, v2 asks a specific, falsifiable question about medication timing. Compared with EHR-based inpatient models, it works on a 60-minute horizon with CGM and dose-time data. Compared with simulators, it keeps mechanism only where parameters can be set from labels rather than estimated per patient. Compared with typical hackathon entries, its evaluation is designed to survive a methodological review.

# 8. Data and Feasibility Assessment
All numbers in this section come from an executable audit (scripts/audit.py, scripts/audit2.py, Appendix A) run during this review on a public GitHub mirror of ShanghaiT2DM [2] whose 109 recording files match the published count [1]. The mirror is a third-party copy; Gate G0 requires re-running the audit on the official figshare copy before any confirmatory analysis.  VERIFIED 

## 8.1 Dataset facts
Table 8.1. ShanghaiT2DM as audited.

| Item | Value | Status |
| Patients / recordings | 100 / 109 (patient = file-name prefix) |  VERIFIED  |
| CGM device and sampling | FreeStyle Libre H, one reading every 15 min [1] |  REPORTED  |
| CGM readings | 112,287 (published 112,475; difference −188, 0.17%) |  VERIFIED  |
| Monitored time | 1168.8 patient-days; recording length 2.56–13.94 days (median 12.68) |  VERIFIED  |
| Sampling gaps | 112,168 of 112,178 intervals ≤16 min; 7 intervals 16–30 min; 3 intervals 30–60 min |  VERIFIED  |
| Sensor floor | 329 readings ≤40 mg/dL; minimum 39.6 mg/dL |  VERIFIED  |
| Time-series fields | Date, CGM, CBG, blood ketone, dietary intake (English + Chinese), insulin s.c., non-insulin agents, CSII bolus, CSII basal, insulin i.v.; five column-name variants across files |  VERIFIED  |
| Static fields | 33 summary columns incl. age, BMI, duration, HbA1c, eGFR, C-peptide, insulin, prescribed agents, complications, “Hypoglycemia (yes/no)” |  VERIFIED  |
| Setting | Not stated in the descriptor; recruited at two Shanghai hospitals (2019–2021) [1]; CSII, i.v. insulin and frequent CBG suggest supervised/inpatient care |  ASSUMPTION  |
| Licence | CC BY 4.0 [1][2] |  REPORTED  |


## 8.2 Hypoglycaemia events
Table 8.2. Event audit with the Section 5.2 definitions  VERIFIED .

| Measure | Value |
| L1 episodes (primary rule) | 348 in 61 patients |
| L2 episodes | 96 in 26 patients |
| Single-reading rule (sensitivity analysis) | 430 in 67 patients |
| Episodes per affected patient | median 3 (IQR 2–8), max 28; top 5 patients hold 27% |
| Episode duration / nadir (median) | 60 min / 60.3 mg/dL |
| Nocturnal onsets (00:00–05:59) | 115 (33%) |
| Onsets within first 24 h of a recording | 69 (20%) |
| In recordings with logged insulin or secretagogue | 210 (insulin 121; secretagogue 94; overlap counted in both) |
| In recordings with neither | 138 (40%) |
| Episodes warnable at H = 60 (an eligible prediction time in [onset − 60, onset − 15]) | 306 (88%) — the ceiling on episode sensitivity |
| Reading immediately before onset <80 mg/dL | 307 (88%) |
| Prediction times at H = 60 (all patients) | 107,041, of which 1,188 positive (1.11%) |
| Dataset field “Hypoglycemia (yes/no)” | “yes” in 10 recordings; “no” in 54 recordings that contain CGM episodes — a different construct; never used |

Figure 8.1. Audit findings on real records. (a) Episodes are concentrated in a few patients (blue: treated; orange: no insulin or secretagogue logged). (b) One third of onsets are nocturnal, in treated and untreated patients alike (33% each); some nocturnal lows may be sensor compression artefacts (sensitivity analysis SA4). (c) The CGM reads below capillary glucose on average; of 64 paired CGM values <70 mg/dL, 8 had a capillary value <70.

## 8.3 Medication-data usability
Table 8.3. Fraction of records supporting each intended feature  VERIFIED .

| Intended feature | Records supporting it | Verdict |
| Insulin product and dose (s.c.) | 825/827 entries (99.8%) in 54 recordings parse to product + IU | Usable |
| Insulin class (rapid / short / premix / basal) | Product names map to class for all parsed entries (premix analogue in 20 recordings, premix human 13, basal analogue 22, short human 8, rapid analogue 2) | Usable |
| CSII bolus and basal rate | 35 recordings; regular insulin; basal as IU/h | Usable (rate persists until changed) |
| i.v. insulin | 6 recordings, 10 entries; amount in infusion bag, no rate | Flag only |
| Oral agent class and dose | 2166/2166 entries (100%) in 92 recordings | Usable |
| Sulfonylurea / glinide exposure | SU logged in 15 recordings (14 patients); glinide in 3 (3 patients); SU entries cluster at 05:00–09:00 and 16:00–18:00 | Usable; small subgroup |
| Administration timestamp | All entries sit on CGM rows (15-min resolution); a median 97% of calendar days in treated recordings have ≥1 entry, consistent with daily administration logging | Usable at 15-min resolution [ASSUMPTION: charted near administration] |
| Prescribed vs administered | SU prescribed but never logged in 4 recordings; logged but not prescribed in 4 | Logged wins; flag conflicts |
| Formulation (e.g., gliclazide IR vs MR) | Not recorded; inferable from dose multiples (30/60/120 mg → MR; 40/80 mg → IR) | Rule + flag  ASSUMPTION  |
| Meal timing | 3802 entries; 742 (20%) read “data not available” (time known, content not) | Timing usable; carbs deferred |
| Physical activity | Not present | Not used |


## 8.4 Label validity
In hospitalised T2D on basal-bolus insulin, the FreeStyle Libre Pro read 12.8 mg/dL below point-of-care glucose on average, its MARD was 28% in the 51–69 mg/dL range, and it flagged far more patients with readings <70 mg/dL than point-of-care testing did [6]. The audit finds the same overall bias and poor agreement at the threshold: across 3,262 paired values the mean CGM − CBG difference is -12.5 mg/dL (MARD 12.9%), although it is close to zero (+1.9 mg/dL) when capillary glucose is below 100 mg/dL; of 64 CGM values <70 mg/dL only 8 had a paired capillary value <70, and of 18 capillary values <70 only 8 had a CGM value <70 — disagreement runs in both directions; and of 65 L1 episodes with a capillary value during the episode, 11 were confirmed. Capillary checks were not taken at random times, so this does not prove that most CGM episodes are false — but it rules out calling them “hypoglycaemia” without qualification.  VERIFIED 
Consequences built into v2: the target is named CGM-detected L1 episode; L2 is reported as a secondary endpoint; a sensitivity analysis removes the 54 CGM episodes contradicted by a capillary value and the episodes flagged by a nocturnal compression heuristic; the clinical action is a capillary check; and Gate G3b records the issue.

## 8.5 How hard is the task? An exploratory baseline
To calibrate expectations without touching the evaluation partition, the trend rule M0 (no fitted parameters) was run on the tuning partition only. Its operating curve (Figure 8.2) shows that trend extrapolation alone warns about two-thirds of treated-patient episodes at roughly one false alert per patient-day, with a median lead of 45 minutes. Any model must beat this, and the headroom to the warnable ceiling (~0.9–0.95) is about 25–30 percentage points.  VERIFIED  (exploratory)
Figure 8.2. Exploratory operating curve of the trend rule M0 on the tuning partition (θ = projected-glucose threshold in mg/dL). Not a confirmatory result; the evaluation partition has not been touched.

## 8.6 Partition and statistical precision
Patients were split once (seed 2026, stratified by treated × has-episode) into a tuning partition T (30 patients, 22 treated, 56 treated-patient episodes) and an evaluation partition E (70 patients, 51 treated, 154 treated-patient episodes in 30 patients). Episodes within a patient are correlated; the effective cluster size m_w = Σm²/Σm is 9.23 in E-treated. With an intra-patient correlation (ICC) of the warned/missed outcome between 0.05 and 0.30, the design effect is 1 + (m_w − 1)·ICC.
Table 8.4. Precision the data can support. Discordance = share of episodes warned by exactly one of the two compared models. Normal approximation; the confirmatory analysis uses the patient-cluster bootstrap.

| Population (E) | Episodes | ICC | Design effect | Effective n | 95% CI half-width of sensitivity (p = 0.65) | Minimum detectable Δ (80% power), discordance 15% / 25% |
| Treated (primary) | 154 | 0.05 | 1.41 | 109 | ±0.090 | 0.10 / 0.13 |
|  |  | 0.15 | 2.24 | 69 | ±0.113 | 0.13 / 0.17 |
|  |  | 0.30 | 3.47 | 44 | ±0.140 | 0.16 / 0.21 |
| All patients (secondary) | 231 | 0.05 | 1.43 | 161 | ±0.074 | 0.09 / 0.11 |
|  |  | 0.15 | 2.29 | 101 | ±0.093 | 0.11 / 0.14 |
|  |  | 0.30 | 3.59 | 64 | ±0.117 | 0.14 / 0.18 |

Reading. The primary test can detect a paired improvement of roughly 10–20 percentage points in sensitivity, not small gains. A non-significant result therefore means “no large effect detected”, and the document must say so. The window-level log-loss difference (secondary S3) uses all prediction times and is the more sensitive check of whether exposure carries any information at all.

## 8.7 Other datasets
AI-READI (controlled access) [4] and CGMacros (open) were proposed in v1.0 for external validation. Neither is used in the core: whether AI-READI records time-resolved sulfonylurea and insulin administration was not verifiable during this review, and CGMacros contains few insulin- or secretagogue-treated participants (as reported in v1). The study is therefore internal validation only; no external-validation claim is made. An external dataset with dose-timed records is listed as future work.  PENDING 

## 8.8 Unresolved data assumptions
- Dose entries reflect administration time within one sampling interval (tested indirectly by the dose-time jitter experiment R1, Section 20.3).  ASSUMPTION 
- Timestamps are local China Standard Time (+08:00) and consistent across files.  ASSUMPTION 
- The official figshare copy equals the mirror apart from the 188-reading difference, which must be explained (Gate G0).  PENDING 
- The care setting is predominantly supervised/inpatient (to confirm with the dataset authors).  ASSUMPTION 
PART III · ARCHITECTURE AND TECHNICAL DESIGN

# 9. End-to-End Architecture
Figure 9.1 (next page, landscape) shows the selected design and nothing else. Colours mark boundaries the brief asks to make explicit: blue = measured records; green = computed state and features; purple = model outputs; red = policy and safety guardrails; amber = human decisions; grey = offline evaluation. Dashed boxes are optional and enter only through a gate.

## 9.1 Modules
Table 9.1. Responsibilities of retained modules. Removed modules are listed in Table 3.1.

| Module | Responsibility | Inputs → outputs | Live path? |
| Data Adapter & Validator | Map the five column variants to one schema; parse doses; convert units; enforce monotone timestamps; flag gaps, floor readings and implausible rates | raw recording + summary → Observation, DoseEvent, MealEvent, PatientStatic, flags | Yes |
| Patient State Engine (“twin”) | Hold and update, per patient, the CGM state, Medication Exposure State, data-quality status and forecast–outcome ledger at every reading | validated events → PatientState(t) | Yes |
| Medication Exposure State | Convert logged doses into time-resolved insulin activity, insulin on board and secretagogue exposure using fixed kernels; project exposure 30 and 60 min ahead from past doses only | DoseEvent ≤ t → ExposureState(t) | Yes |
| Feature Builder | Assemble the causal snapshot z(t) for the configured model level (M1, M2, M3r or M3) | PatientState(t), PatientStatic → FeatureSnapshot | Yes |
| Risk Model M3 | LightGBM binary classifier + isotonic calibrator | FeatureSnapshot → p(t) | Yes |
| Decision Policy | Deterministic, frozen thresholds and cooldown; abstention; logging | p(t), sufficiency, CGM(t), last notification → PolicyDecision | Yes |
| Explanation | Grouped TreeSHAP contributions; exposure timeline from the state (not from the model) | model, snapshot → top factor groups | Yes (cached) |
| Ward Board / Patient Review / Evidence view | Show states, traces, doses, data quality, reasons; collect acknowledgements; show frozen results | API → screens; user → Acknowledgement | Yes |
| Replay Service & API | Deterministic, chronological replay of held-out records; REST endpoints; JSONL audit log | stored records → timed events | Yes (demo) |
| Label Builder | Episodes and prediction-time eligibility from CGM only | Observation → EpisodeLabel, eligibility | No |
| Evaluation Harness | Folds, training, calibration, τ selection, operating curves, bootstrap, reports | snapshots + labels → results.json, model card, artefacts | No |


## 9.2 Why this counts as a digital twin — and what it is not
The twin is a persistent, per-patient state that is updated as each observation arrives, carries a mechanistic component (drug exposure from recorded doses), produces forecasts, and reconciles each forecast with what then happened. Every state element can be displayed and tested (tests in Appendix H, Table H.2). It is not a validated physiological simulator: it does not estimate a patient’s insulin sensitivity or simulate meals, and the interface never presents a filtered glucose trajectory as a mechanistic prediction.
Figure 9.1. End-to-end architecture of HypoSense Twin v2 (selected design only). Blue: measured records; green: computed state and features; purple: model outputs; red: policy and safety guardrails; amber: human decisions; grey: offline evaluation, never on the live path; dashed: optional, gated.

# 10. Data and Feature Pipeline
Figure 10.1. Data pipeline with the six places where leakage could enter (red notes) and how each is prevented.

## 10.1 Ingestion and validation
- Integrity: raw files are read-only, pinned by SHA-256 in data/MANIFEST.sha256; the loader refuses to run on a mismatch.
- Schema harmonisation: five column-name variants (e.g., “CGM (mg / dl)”, “CGM ”, “胰岛素泵基础量 (Novolin R, IU / H)”) map to canonical names; any unmapped column is an error.
- Units: CGM and CBG in mg/dL; insulin in IU; oral doses converted to mg (“0.5 g” → 500 mg); CSII basal in IU/h.
- Timestamps: stored as timezone-aware ISO-8601 with +08:00 (assumed); internal arithmetic in integer epoch seconds; rows sorted; exact duplicates removed; non-monotone timestamps quarantined.
- Quality flags per reading: gap since previous reading >20 min; value ≤40 mg/dL (sensor floor); |ΔG/Δt| >4 mg/dL/min; first 2 hours of a recording (warm-up). Flags never delete data.

## 10.2 Leakage-safe feature construction
Every feature at time t is computed by a function that receives only the records with timestamp ≤ t. This is enforced by construction (the snapshot builder takes a truncated history object) and by a test: for random t, the snapshot computed from the full record must equal the snapshot computed from the record truncated at t. Exposure projected to t + 30 and t + 60 min is allowed because it depends only on doses already given — it assumes no further doses, which is stated in the UI. One residual risk is accepted and tested: laboratory values in the summary sheet may have been measured up to six months after the CGM period [1]; they are patient-level context, not time-stamped events, and sensitivity analysis SA8 removes them.

## 10.3 Splits
Patient-level partition (T 30% / E 70%, seed 2026, stratified) is fixed before any model is fitted and stored in config/partition.csv. All recordings of a patient stay together. Within E, five grouped folds; training data for fold k = T ∪ (E minus fold k). Calibrators, thresholds, scalers and percentile references are fitted inside training data only (Section 15).

## 10.4 Inference-time input requirements
Table 10.1. Minimum inputs at inference time.

| Input | Required for a forecast? | If absent |
| CGM reading at t (no gap >20 min before it, not flagged) | Yes | INSUFFICIENT DATA |
| ≥7 of the last 8 readings (120 min) | Yes | INSUFFICIENT DATA |
| Static record (age, BMI, duration, eGFR, HbA1c, regimen) | No (M2/M3 use missing indicators) | Forecast with missing-indicator features |
| Dose log for a patient whose regimen lists insulin/secretagogue | No | Exposure features missing + “medication timing unavailable” badge |
| Meal log | No | Meal features missing; no badge (meal logging is incomplete by nature) |


# 11. Model Architecture
All learned models share one learner, one hyperparameter set and one calibration and threshold procedure, so that comparisons isolate information, not tuning effort.
Table 11.1. Model ladder contracts. Feature lists are in Appendix D.

| Model | Inputs | Output contract | Rationale | Role |
| M0 trend rule | Last 30 min of CGM (≥3 readings) | Projected CGM at t + 60 min; ALERT if projection < θ | Transparent, no fitting; strong at short horizons | Baseline (C0) |
| M1 CGM-only | CGM features (App. D, group 1–3) + time of day | p(t) ∈ [0, 1], calibrated | Strong data-driven sensor baseline | Baseline |
| M2 CGM + context | M1 + static record, prescribed regimen flags, meal timing | same | Ordinary contextual information | Primary comparator |
| M3r raw dose timing | M2 + time since last dose, last dose, 24-h totals by class; CSII / i.v. flags | same | Medication information without a pharmacological model | Representation check (C2) |
| M3 exposure | M2 + exposure state at t, t + 30, t + 60; time since last dose by class; CSII / i.v. flags | same | Drug action as a time-varying state | Proposed model |
| M4 (optional) | M3 + reduced physiological model features | same | Only if Gate G6 passes | Exploratory (C3) |


## 11.1 Learner and training choices
- LightGBM, binary log-loss, no class re-weighting (re-weighting distorts calibration; the threshold handles imbalance). Monotone constraints are not imposed in the core (they would encode untested assumptions); they are a listed robustness variant.
- One shared hyperparameter set, chosen for M1 on the tuning partition by inner grouped cross-validation (≤30 Optuna trials, objective: mean log-loss), then reused unchanged for M2, M3r, M3 and M4. Tuning on the baseline favours the comparator, which makes a positive M3 result more credible. A sensitivity analysis re-tunes each model separately.
- Search space: learning rate 0.02–0.1; num_leaves 7–31; min_data_in_leaf 100–800; feature_fraction 0.6–1.0; bagging_fraction 0.7–1.0; lambda_l2 0–10; 2,000 rounds with early stopping on inner grouped log-loss.
- Isotonic calibration fitted on inner out-of-fold predictions of the training patients; Brier score, expected calibration error and a reliability diagram reported. If calibration is poor on development data (pre-set rule: calibration slope outside 0.8–1.25), the UI shows risk bands instead of percentages — decided before E is opened.
- Determinism: seed=2026, deterministic=true, num_threads=1 for the confirmatory run.

## 11.2 Alternatives not chosen
Logistic regression (kept as a robustness variant for M2 vs M3 — if the effect appears only with trees, it is reported as such); recurrent or transformer sequence models (insufficient patients at 15-minute resolution); patient-ID or embedding features (memorise identity and leak in grouped validation); per-patient fine-tuning (too few events per patient).

# 12. Medication Representation
The exposure state distinguishes four things the brief requires to keep separate: the prescribed regimen (static summary field — used as context in M2), the recorded administration (a timestamped dose entry), the estimated exposure (kernel-weighted function of recorded administrations — the M3 state) and the observed physiological effect (the CGM — never assumed from exposure).

## 12.1 Normalisation
Each dose text (e.g., “insulin aspart 70/30, 14 IU”, “metformin 500 mg, gliclazide 30 mg”) is split into components, matched against a versioned dictionary (Appendix B) and mapped to (class, product, amount, unit, route). Classes with kernels: rapid analogue, short human (regular), premix analogue, premix human, intermediate (NPH), basal analogue, CSII regular (bolus and basal rate), sulfonylurea, glinide. Classes kept as presence flags only (low intrinsic hypoglycaemia risk): metformin, α-glucosidase inhibitors, DPP-4 inhibitors, SGLT2 inhibitors, thiazolidinediones, GLP-1 receptor agonists. Unknown products become class “unknown”, are excluded from exposure, and are logged for dictionary review.

## 12.2 Exposure equations
For each kernel class c, let D(c, t) be the recorded doses (tj, dj) of that class with tj ≤ t; ac(τ) is the kernel activity (fraction of dose per minute) and Ac(τ) the cumulative absorbed fraction:
Activityc(t) = Σj ∈ D(c,t) dj · ac(t − tj)        [IU/min, or dose fraction/min]	(1)
OnBoardc(t) = Σj ∈ D(c,t) dj · [1 − Ac(t − tj)]        [IU, or dose fraction]	(2)
Insulin kernels use the parametric exponential activity curve used in open-source insulin-on-board calculations [15], defined by peak time tp and duration of action td (minutes):
τ = tp(1 − tp/td) / (1 − 2tp/td),   a = 2τ/td,   S = 1 / [1 − a + (1 + a)·exp(−td/τ)]	(3)
a(t) = (S/τ2) · t · (1 − t/td) · exp(−t/τ)   for 0 ≤ t ≤ td;   a(t) = 0 otherwise	(4)
Premixed insulins are the dose-weighted sum of their components (for example 0.3 × rapid + 0.7 × intermediate for a 30/70 analogue). Basal analogues use a flat kernel after a 1-hour lag over 24 hours. A CSII basal rate r (IU/h) is treated as a sequence of 15-minute micro-boluses of r/4 IU passed through the short-human kernel until the next rate entry. Intravenous insulin is represented only by a flag “i.v. insulin entry in the last 4 h” because infusion rates are not recorded.
Secretagogue exposure uses a normalised one-compartment absorption–elimination (Bateman) kernel κ with elimination half-life t½ and time to peak tmax, and doses expressed as a fraction of the maximum labelled daily dose Dmax of that drug and formulation, so that different sulfonylureas share one scale:
ESU(t) = Σj ∈ D(SU,t) (dj / Dmax) · κ(t − tj)        [dimensionless]	(5)
κ(τ) = [exp(−keτ) − exp(−kaτ)] / maxτ[exp(−keτ) − exp(−kaτ)],   ke = ln 2 / t½	(6)
The absorption rate ka is set so that the kernel peaks at tmax. Projected exposure at t + 30 and t + 60 min is computed from the same past doses (no assumed future doses). Features also include insulin activity per kg body weight when weight is known.
Figure 12.1. Kernel shapes with illustrative parameter values. Production values come from product labels and are confirmed by a clinical pharmacist before the protocol is frozen (Appendix C).

## 12.3 Parameters, uncertainty and sensitivity analysis
- Fixed, population-level parameters. No patient-specific pharmacodynamic parameter is estimated; the data cannot identify them (Section 13). Values per product/class are set from labels before E is opened and recorded in config/pharma.yaml with source and date.  PENDING 
- Uncertainty is handled by sensitivity analysis, not by pretending precision: all durations scaled by ×0.75 and ×1.5 (SA6); kernel family swapped (exponential ↔ gamma) as a robustness variant; renal impairment (eGFR <45) does not alter kernels in the core — eGFR is a context feature and an interaction the trees may learn.
- Representation check: M3r gives the learner the same medication information without kernels; if M3r ≈ M3, the simpler representation is deployed and the claim becomes “medication timing helps”, not “the exposure model helps”.

## 12.4 Missing or conflicting administration information
Table 12.1. Missing-information rules.

| Situation | Handling |
| Regimen lists insulin/secretagogue; no entry of that class in the last 36 h | Exposure features for that class set to missing (not zero); indicator “timing unknown” = 1; UI badge; subgroup reported |
| Entry logged but not in prescribed regimen | Logged administration is used (it is the event record); conflict flag stored |
| Formulation ambiguous (e.g., gliclazide IR vs MR) | Inferred from dose multiple (App. B); flag; SA with the alternative formulation |
| Unparseable entry | Kept as text; class “unknown”; excluded from exposure; counted in the data-quality report |
| Fallback branch (Gate G3 fails) | No exposure features at all; medication information limited to static regimen flags (M2); claim narrows to the value of context |


# 13. Physiological Model and State Estimation
Decision: removed from the primary predictive pathway. The section documents why, and what would be required to bring a reduced version back as the optional extension E1 (model M4).

## 13.1 Assessment of the v1.0 model
Table 13.1. Why the mechanistic core does not stay on the predictive path.

| Question from the brief | Finding |
| Scientific assumptions | Extended Bergman minimal model: linear glucose effectiveness toward a basal level, remote insulin action, two-compartment subcutaneous insulin and gut absorption, sulfonylurea-driven secretion proportional to plasma exposure (v1 §10.2). The minimal model was built for intravenous glucose tolerance tests with frequent plasma sampling [10]. |
| Appropriate for population and observations? | Partly. Observations are one 15-minute interstitial channel (with sensor bias at low glucose), unmeasured insulin, and meals as free text with 19.5% missing content. |
| Counter-regulation | Absent. No glucagon or adrenaline response and no increase in endogenous glucose production below a threshold; later simulator versions added these explicitly [9]. Without them, projected lows are too deep and too long — biased exactly where the forecast matters. |
| Validity near 70 mg/dL | Not established; and the CGM itself is least accurate there (Section 8.4). |
| States and free parameters vs data | 8 states, 7 personal parameters + drug constants, observed through one noisy channel. Products such as SI × φSU, and SG versus Gb, trade off; minimal-model parameters are known to have numerical non-identifiability regions even with richer data [11]. |
| Practical predictive value of state estimates | Unknown; no experiment. A strong CGM trend baseline already captures much of the short-term signal (Figure 8.2). |
| Stability with gaps and irregular sampling | Unmodelled or mis-estimated meals produce large innovations; v1 already planned NIS monitoring, resets to the prior on divergence and nightly MAP refits (v1 §10.5, §29) — added fragility. |
| Independent validation possible? | Not with this dataset: no insulin, C-peptide time series or tracer data during CGM. |


## 13.2 Optional extension E1 (only if time allows and Gate G6 passes)
If attempted, E1 is a reduced model used only as a feature generator for M4 — never as a displayed trajectory. Units: G in mg/dL, time in minutes.
dG/dt = −SG·(G − Gb) − γ·X·G + cr·max(0, Gr − G) + m·M(t)	(7)
dX/dt = −p2·X + p2·[Activityins(t) + φ·ESU(t)]	(8)
SG, p2, φ, cr, Gr and m are fixed at group level (strata: insulin-treated vs secretagogue-only; diabetes duration above/below 10 years), estimated once on the tuning partition; M(t) is a meal-logged indicator with a fixed absorption profile (no carbohydrate amount). Only the gain γ is tracked per patient by a one-dimensional filter. The counter-regulation term cr·max(0, Gr − G) is included only if it passes the low-range test below; its justification is the known rise in endogenous glucose production as glucose falls, which may be blunted in long-standing insulin-treated diabetes — hence group-level, not personal, values.

### Gate G6 tests for E1
- Parameter recovery on synthetic patients generated by a structurally different model (different absorption and elimination forms, Libre-like negative bias and noise, 15-minute sampling): γ recovered within ±25% in ≥80% of simulated patients.
- Filter stability on all tuning-partition records: no divergence (normalised innovation within its 99% χ² band for ≥99% of readings).
- Low-range behaviour: on tuning-partition readings between 70 and 100 mg/dL followed by a fall, the 30-minute forecast bias with the counter-regulation term is smaller than without it, by a pre-set margin (absolute bias reduction ≥3 mg/dL) — otherwise the term is dropped.
- Incremental value on T: M4 improves inner-CV log-loss over M3 on the tuning partition. If any test fails, E1 is dropped; the core is unaffected.

# 14. Risk Estimation and Decision Policy
Figure 14.1. From a new reading to a human decision. Every path ends either in an explicit non-forecast state or in a clinician acknowledgement; the action itself is taken by staff outside the system.

## 14.1 Inputs and outputs
Inputs at each reading: calibrated p(t) from the deployed model; sufficiency flags; CGM(t); medication-timing status; out-of-range flags; time of the last notification for the patient. Output: one PolicyDecision with state, probability (or none), reasons, flags and a log record.

## 14.2 Rules
Table 14.1. Deterministic policy, evaluated top to bottom.

| Priority | Condition | State | Shown to user |
| 1 | Model artefact hash mismatch or inference exception | SYSTEM ERROR | Error banner; no stale states |
| 2 | No reading at t, gap >20 min, <7 of last 8 readings, warm-up (<2 h of record), or reading flagged (≤40 mg/dL, rate >4 mg/dL/min) | INSUFFICIENT DATA | No probability; reason |
| 3 | Current or recent low: CGM(t) <70 mg/dL, or t inside an episode, or <60 min after an episode ended | LOW NOW | Reading, episode duration or time since recovery; no forecast |
| 4 | p(t) ≥ τA | ALERT | Probability, reasons; notification if none in previous 60 min |
| 5 | τW ≤ p(t) < τA | WATCH | Probability, reasons; no notification |
| 6 | otherwise | NO ALERT | Probability; never the word “safe” |
| — | Any input outside the development range (0.5th–99.5th percentile) or medication timing unknown | tag on states 4–6 | LOW CONFIDENCE / timing badge; tags never downgrade ALERT |


## 14.3 Thresholds, persistence, suppression and logging
- τA = lowest threshold with development false-alert rate ≤1.0 per patient-day; τW = lowest threshold with development notification-equivalent rate ≤3.0 per patient-day. Both are chosen on inner out-of-fold predictions of training patients and frozen in artefacts/policy.json with the config hash before E is opened.
- Persistence: no k-of-n rule in the core — at 15-minute sampling, requiring two consecutive exceedances costs 15 minutes of lead. A 2-of-2 variant is a listed robustness analysis.
- Duplicate suppression: one notification per patient per 60 minutes; the ALERT state remains visible during cooldown.
- Logging: every decision is appended to logs/decisions.jsonl with timestamp, patient key, model version, config hash, p(t), τA, τW, state, flags and input digest; acknowledgements with reason codes are appended to logs/acks.jsonl.
- Uncertainty principle: uncertainty may qualify reassurance (NO ALERT with LOW CONFIDENCE) but never suppresses a warning.

## 14.4 State transitions and safe degradation
Figure 14.2. Policy state transitions.
Figure 14.3. Failure modes and the explicit response to each. No failure produces a confident number.
Risk categories are operational states for prioritising attention. They are not validated clinical actions and the UI says so.

# 15. Evaluation and Model-Selection Pipeline
The evaluation is designed so that the evaluation partition E influences nothing except the final numbers.
- Design on T. Feature engineering, hyperparameter selection (for M1), calibration settings, kernel parameter checks, policy rules and demo design use only T (with inner grouped CV).
- Freeze. Code, configuration, partition file, kernel parameters, analysis plan (this document, Sections 19–20) and seeds are committed; the commit hash is recorded in the README and in results.json.
- Unseal E. Five grouped folds over E. For each fold: train each model on T ∪ (E minus fold) with the frozen hyperparameters; produce inner out-of-fold predictions on that training set; fit the isotonic calibrator and choose τA/τW on them; predict the held-out fold.
- Pool out-of-fold predictions for all E patients; compute operating curves and metrics per model.
- Primary comparison: Δ at 1.0 FA/patient-day, M3 − M2, on E-treated patients; 2,000 patient-cluster bootstrap resamples (patients drawn with replacement, both models evaluated on the same resample; percentile interval) [13].
- Deployed operating point: with fold-frozen τA, report the achieved false-alert rate and sensitivity — this checks whether the threshold rule transfers.
- Model for the demo and repository: retrained on all patients with the frozen procedure; its threshold from all-patient out-of-fold predictions. The demo replays E patients using their out-of-fold predictions, so no demo case is scored by a model that saw it.
Model selection rule (pre-specified): deploy M3 if H1 is supported; otherwise deploy whichever of M2 and M3 has the higher point estimate at 1.0 FA/patient-day only if its log-loss is not worse; ties go to the simpler model (M2). M0 is deployed only if no learned model beats it.

# 16. Explanation, Safety and Human Oversight

## 16.1 What can be explained
Table 16.1. Explanations and the caveat attached to each.

| Output | Explanation method | Caveat shown |
| Risk p(t) | TreeSHAP values [17] summed into factor groups: CGM level, CGM trend, CGM variability, personal history, time of day, static context, meal timing, insulin exposure, secretagogue exposure; top 3 groups with direction | “Associations learned from retrospective data — not causes” |
| Exposure state | Directly displayed curves from logged doses (no model) | “Estimated from recorded doses with standard kernels; assumes no further doses” |
| State | Policy rule that fired (Table 14.1) | Thresholds and their freeze date |
| Model reliability | Evidence view: operating curves, calibration, per-patient spread, known failure cases | “Internal validation on Chinese data; not clinically validated” |


## 16.2 Uncertainties that must be exposed
- Data sufficiency (INSUFFICIENT DATA, no number).
- Medication timing unknown (badge).
- Inputs outside development range (LOW CONFIDENCE).
- Label uncertainty: every forecast refers to a CGM-detected low; capillary confirmation recommended by local protocol.
- Calibration quality (percentages or risk bands, decided before testing).

## 16.3 Prohibited actions
The system must not: recommend, adjust or simulate insulin or other medication doses; offer medication what-if scenarios; label a patient “safe”; diagnose; send messages to patients; escalate automatically; or hide the label caveat. These are enforced in code by the absence of such functions and checked in a review of UI strings.

## 16.4 Human oversight
Every ALERT notification requires acknowledgement with one of four reason codes (capillary glucose checked; known/already managed; sensor issue suspected; not clinically relevant). The codes feed the alert-burden analysis and, in a future pilot, the measurement of how alerts are used.

# 17. Interface and Demonstration
Figure 17.1. Ward Board and Patient Review wireframe. Illustrative layout with synthetic values; the demo uses replayed held-out records with alias names.
Table 17.1. The three retained screens.

| Screen | Purpose | Must show |
| Ward Board | Who needs attention now? | Patients sorted by state then risk; state badge with text (never colour alone); time of last reading; provenance badge “replay of held-out record” |
| Patient Review | Why, and can I trust it? | State and probability; 6-h CGM with dose markers; exposure curves; data-quality and medication-timing status; top factor groups; acknowledgement panel |
| Evidence view | Does it work, and where does it fail? | Headline operating curves with interval; ladder table; calibration; per-patient spread; known failure cases; data honesty card; model card |

Technology: FastAPI back end serving REST endpoints and a replay clock; a single-page React (Vite, Recharts) front end polling once per second. A team with no front-end capacity may use Streamlit instead; the scientific result is unaffected. The end-to-end demonstration is specified in Section 23.

# 18. Reliability and Reproducibility
Table 18.1. Reliability requirements.

| Concern | Specification |
| Determinism | Seeds: partition 2026, folds 2026, LightGBM 2026 with deterministic mode and one thread for confirmatory runs; bootstrap seed 2027; replay is clock-scaled but event order is fixed. Test: two replays produce identical decision-log hashes. |
| Provenance | Every artefact carries data hash, code commit, config hash and creation time; results.json records all three plus library versions. |
| Environment | Python 3.11, pinned lockfile; Docker image for the demo; runs offline on a CPU laptop; no network calls on the demo path. |
| Error handling | Loader refuses mismatched data; API refuses to start on artefact hash mismatch; inference exceptions produce SYSTEM ERROR, never a stale state. |
| Logging | Append-only JSONL for decisions and acknowledgements; rotation per run; logs never contain raw free-text diet entries. |
| Versioning | Semantic versions for data dictionary (pharma.yaml, drug_dictionary.csv), models and policy; the Evidence view shows them. |
| Latency | Target <200 ms per reading on a laptop CPU (feature build + LightGBM + policy) — to be measured. |

PART IV · EXPERIMENTATION AND EVIDENCE

# 19. Baseline and Ablation Design
Figure 19.1. The model ladder. Each arrow changes one block of information; the red arrow is the single primary comparison. No results are shown because none exist yet.
Table 19.1. Comparisons, kept to six; only one is confirmatory.

| Comparison | Models | Question | Type |
| Primary | M3 vs M2 | Does time-resolved medication exposure improve warning beyond CGM + context? | Confirmatory |
| C0 | M1 vs M0 | Is a learned model needed beyond trend extrapolation? | Secondary |
| C1 | M2 vs M1 | Does static context (incl. prescribed regimen) and meal timing help? | Secondary |
| C2a | M3r vs M2 | Does raw medication timing help? | Secondary |
| C2b | M3 vs M3r | Does the kernel representation matter? | Secondary |
| C3 | M4 vs M3 | Does a reduced physiological model add anything? (only if G6 passes) | Exploratory |

Fairness rules: same patients, folds, seeds, hyperparameters (chosen for M1), calibration and threshold procedure for all learned models; M0 uses the same notification and cooldown logic with its projection threshold θ chosen by the same false-alert rule. No model receives extra tuning trials.

# 20. Evaluation Protocol
Figure 20.1. Evaluation protocol. Grey: development metrics on the tuning partition, used only for design. Purple and red: confirmatory metrics computed once, on the evaluation partition, after the protocol freeze.

## 20.1 Summary of the protocol
Table 20.1. Evaluation protocol at a glance.

| Element | Specification |
| Primary hypothesis | H1 (Section 6.1) |
| Primary endpoint | Δ episode sensitivity (M3 − M2) at 1.0 false alert per patient-day, E-treated patients, L1, H = 60 min, lead ≥15 min |
| Labels and windows | Section 5.2 (single definition set) |
| Unit of independence | Patient. Recordings, episodes and prediction times within a patient are not independent and are never resampled on their own |
| Partitions | T (30 patients) for design; E (70 patients) sealed until freeze; 5 grouped folds within E; training = T ∪ E∖k |
| Calibration and thresholds | Inner grouped out-of-fold predictions of training patients only |
| Model selection | Pre-specified rule (Section 15); one shared hyperparameter set chosen for M1 on T |
| Uncertainty | 2,000 patient-cluster bootstrap resamples; percentile 95% intervals; paired for differences |
| Decision rule | H1 supported if the lower bound of the 95% interval of Δ > 0 |
| Seeds | Partition and folds 2026; LightGBM 2026; bootstrap 2027; sensitivity analysis SA7 repeats folds with seeds 2028–2032 |
| Validation type | Internal (patient-held-out) validation only. No external validation is available for the M3 feature set |


## 20.2 Metrics
Table 20.2. Metrics. Accuracy and AUROC alone are not reported as evidence of usefulness.

| Metric | Definition | Role |
| Episode sensitivity at 1.0 FA/day | Share of episodes with a correct warning (Section 5.2) at the threshold giving 1.0 false alert per patient-day | Primary |
| Operating curve (FROC-style) | Episode sensitivity vs false alerts per patient-day across thresholds | Headline figure |
| Partial area 0.5–2.0 FA/day | Normalised area under the operating curve between 0.5 and 2.0 FA/patient-day | Secondary |
| Lead time | Median and IQR of onset minus earliest correct ALERT; share with lead ≥30 min | Secondary |
| False alerts per patient-day; alert precision | Section 5.2; precision = true notifications / all notifications | Secondary |
| Missed-episode rate | 1 − sensitivity; reported with the warnable ceiling | Secondary |
| Per-patient distribution | Sensitivity and FA/day per patient (forest plot) | Secondary |
| Window-level log-loss, Brier, AUPRC | Over all prediction times; differences with patient-cluster bootstrap | Secondary (S3) |
| Calibration | Reliability diagram, calibration slope and intercept, ECE | Secondary |
| Abstention coverage | Share of readings in INSUFFICIENT DATA; episodes whose warning window fell in abstention | Secondary |
| Latency, reliability | p50/p95 inference time; replay determinism; crash-free 14-day replay | Engineering |


## 20.3 Pre-specified secondary and sensitivity analyses
Table 20.3. Secondary (S), sensitivity (SA) and robustness (R) analyses. None can overturn the primary decision rule; all are reported.

| ID | Analysis | Purpose |
| S1 | Primary comparison restricted to warnings with lead ≥30 min | Medication should matter most for early warning |
| S2 | Δ false alerts per patient-day at M2’s sensitivity at 1.0 FA/day | Same catches, fewer alarms? |
| S3 | Δ window-level log-loss (M3 − M2) | Higher-powered check of information content |
| S4 | C0–C2 comparisons | Locate where value comes from |
| S5 | L2 episodes | Clinically more significant, less noisy label |
| S6 | All E patients (treated + untreated) | Generality; untreated contribute many CGM lows |
| S7 | Per-patient forest plot; patient-weighted sensitivity | Avoid domination by a few patients |
| SA1 | Single-reading episode rule | Definition dependence |
| SA2 | Exclude first 24 h of each recording | Sensor day-1 inaccuracy |
| SA3 | Exclude recordings with CSII or i.v. insulin | Intensive inpatient regimens |
| SA4 | Exclude nocturnal compression-artefact candidates (onset 00–06 h, ≤45 min, fall or rise ≥1.5 mg/dL/min) | Label noise (9 episodes flagged in audit) |
| SA5 | Exclude episodes contradicted by a capillary value during the episode | Label validity (54 episodes) |
| SA6 | Kernel durations ×0.75 and ×1.5 | Parameter uncertainty |
| SA7 | Five alternative fold seeds | Partition sensitivity |
| SA8 | M2 and M3 without laboratory values (HbA1c, C-peptide, eGFR, lipids) | Labs may post-date the CGM period |
| R1 | Dose times jittered ±30 and ±60 min (uniform) in test folds | Dependence on precise timing (charting-time risk) |
| R2 | Random removal of 10% and 20% of CGM readings; 60–120-min blocks | Robustness and abstention behaviour |
| R3 | Logistic regression in place of LightGBM for M2 and M3 | Learner dependence |
| R4 | Per-model hyperparameter tuning | Tuning-fairness check |


## 20.4 Interpretation matrix
Table 20.4. Every outcome yields a defensible conclusion and a selected configuration. Nothing guarantees that the more complex model wins.

| Outcome | Legitimate conclusion | Architecture selected |
| Δ CI > 0; S2/S3 agree | Time-resolved medication exposure improves CGM-detected low warnings in treated patients in this internal validation | M3 in the twin; claim as stated |
| Δ CI > 0, but M3 ≈ M3r | Medication timing helps; the kernel representation adds nothing measurable | Deploy the simpler of M3/M3r by rule; claim “timing helps” |
| Δ point estimate > 0, CI includes 0; S3 favours M3 | Exposure carries information but no large improvement in warning was detected | M2 (simpler) or M3 by rule; report as inconclusive for H1 |
| Δ ≈ 0; S3 ≈ 0 | No detectable value of exposure beyond CGM + context in these data | M2; report the negative result |
| M2 ≈ M1 | Static context and meal timing add nothing | Simplest of M1/M2 |
| M4 adds nothing (if run) | Physiology adds no detectable value | E1 dropped |
| Gains only in one data-quality subgroup (e.g., SA5) | Effect may depend on label quality; not a general claim | As per primary; subgroup reported as exploratory |
| Learned models ≤ M0 | At 15-min sampling and this sample size, trend extrapolation is as good as ML | M0 in the twin; report candidly |
| Gate failure before E (G0–G4) | Primary hypothesis not testable as designed | Fallback branch per Section 21 |


## 20.5 Statistical limitations
- Thirty treated patients with episodes in E; precision supports only large effects (Table 8.4).
- Prediction times overlap and are autocorrelated; window-level metrics are never treated as independent evidence — all intervals resample patients.
- Subgroup analyses (by drug class, nocturnal, renal function) have very few patients and are exploratory.
- Internal validation on one Chinese dataset; no external validation.

# 21. Decision Gates and Fallback Branches
Figure 21.1. Research decision gates with current status from the audit and the predefined fallback for every failure.
Table 21.1. Gate specifications. Thresholds are justified by precision and usability, not copied from the evaluation.

| Gate | Measurement | Acceptance criterion and justification | If passed | If failed | Status |
| G0 Source integrity | Official copy downloaded; SHA-256; file and reading counts vs descriptor | 109 files; CGM count reconciled to 112,475 or difference explained — confirmatory claims must rest on the citable copy | Unseal allowed | Re-run audit on official copy; block E | PARTIAL |
| G1 Dataset usability | Parse rate, timestamp monotonicity, interval distribution | ≥99% of readings parse; ≥99% of intervals ≤20 min — needed for 15-min features without imputation | Proceed | Stop: change dataset | PASS |
| G2 Event sufficiency | L1 episodes and patients with episodes in E-treated; projected CI half-width | ≥100 episodes in ≥20 patients and half-width ≤0.15 at ICC 0.15 — below this, only differences >0.2 are detectable, which is not a useful test | Treated primary population | All patients as primary; else descriptive claim only | PASS (154 / 30; ±0.11) |
| G3 Medication usability | Parse rate; share of treated recording-days with entries; timing resolution; patients with exposure variation | ≥90% parse; ≥80% days; ≤15-min resolution; ≥20 treated E patients — exposure needs timed, dosed entries for most days | Exposure branch (M3) | Context-only branch (M2 vs M1) | PASS (99.8–100%; 97%; 15 min; 51) |
| G3b Label validity | CGM vs capillary agreement at low glucose | If >50% of episodes with a concurrent capillary value are unconfirmed, the label must be renamed and SA5 run | No change | Rename, SA5, capillary action | TRIGGERED → applied |
| G4 Baseline feasibility | Pipeline end-to-end on T; leakage tests; M1 vs M0 on T inner CV | All tests pass; M1 operating curve computed — a broken baseline makes every comparison meaningless | Freeze protocol | M0 operational baseline; fix pipeline | PENDING |
| G5 Statistical interpretability | Bootstrap distribution after the confirmatory run | Every resample contains episodes for both models; interval reported as planned | Report decision per rule | Report as inconclusive; no superiority claim | PENDING |
| G6 Physiology (optional) | Recovery, stability, low-range bias, gain on T | Section 13.2 | M4 as exploratory | Drop E1 | NOT STARTED |
| G7 Demo readiness | Replay determinism; seeded cases; offline run on a clean machine; all states exercised | Identical decision-log hash in two runs; TP/FN/FP cases exist | Live demo | Recorded replay video + static evidence | PENDING |


# 22. Results Reporting Template

| Status of this section / All result cells below are empty placeholders to be filled automatically from results.json after the confirmatory run. Targets are not results. The only measured performance numbers in this document are the exploratory M0 values on the tuning partition (Figure 8.2). |

Table 22.1. Primary results table (E-treated patients, L1, H = 60, lead ≥15 min).

| Model | Sensitivity at 1.0 FA/day (95% CI) | Δ vs M2 (95% CI) | Median lead (IQR) | Partial area 0.5–2.0 | Log-loss | Status |
| M0 trend rule | [  ] | [  ] | [  ] | [  ] | n/a |  PENDING  |
| M1 CGM-only | [  ] | [  ] | [  ] | [  ] | [  ] |  PENDING  |
| M2 CGM + context | [  ] | reference | [  ] | [  ] | [  ] |  PENDING  |
| M3r raw dose timing | [  ] | [  ] | [  ] | [  ] | [  ] |  PENDING  |
| M3 exposure (primary) | [  ] | [  ]  ← primary | [  ] | [  ] | [  ] |  PENDING  |
| M4 (if run) | [  ] | [  ] | [  ] | [  ] | [  ] |  PENDING  |

Table 22.2. Secondary and sensitivity analyses template.

| Analysis | Δ M3 − M2 (95% CI) | Notes | Status |
| S1 lead ≥30 min | [  ] |  |  PENDING  |
| S2 Δ FA/day at matched sensitivity | [  ] |  |  PENDING  |
| S3 Δ log-loss | [  ] |  |  PENDING  |
| S5 L2 episodes | [  ] |  |  PENDING  |
| S6 all E patients | [  ] |  |  PENDING  |
| SA1–SA8 | [  ] | one row each |  PENDING  |
| R1 dose-time jitter ±30 / ±60 | [  ] |  |  PENDING  |

Table 22.3. Operating-point and engineering template.

| Deployed operating point (fold-frozen τA) | Value | Status |
| Achieved false alerts per patient-day (target 1.0) | [  ] |  PENDING  |
| Achieved episode sensitivity | [  ] |  PENDING  |
| Alert precision | [  ] |  PENDING  |
| Calibration slope / intercept / ECE | [  ] |  PENDING  |
| Readings in INSUFFICIENT DATA | [  ] |  PENDING  |
| p95 latency per reading | [  ] |  PENDING  |


## 22.1 Figures to generate (templates)
- R-F1 Headline: operating curves M0–M3 on E-treated; vertical line at 1.0 FA/day; inset: bootstrap distribution of Δ with the interval.
- R-F2 Ladder chart: Δ with CI for C0, C1, C2a, C2b (and C3) as a dot-and-interval chart around zero.
- R-F3 Calibration: reliability diagram with confidence bands, M2 and M3.
- R-F4 Per-patient forest plot of sensitivity and FA/day.
- R-F5 Lead-time distribution of correct warnings, M2 vs M3.

# 23. Demonstration and Reproducibility Protocol
Figure 23.1. Demonstration flow. The headline result is a placeholder until the confirmatory run exists.

## 23.1 Case selection without cherry-picking
- After the confirmatory run, take the out-of-fold predictions of E-treated patients for M3 and M2 at their fold-frozen thresholds.
- Classify episodes and notifications: TP (episode warned by M3), FN (episode missed by M3), FP (M3 false alert).
- Eligibility for display: ≥24 h of record before the event and complete data quality in the 6 h around it (so the replay is legible). The eligibility rule is fixed now and does not use model outputs.
- Shuffle each category with seed 2026 and take the first eligible case of each. Record the seed, the case IDs and the hash of the selection script in demo/cases.json.
- If M3 has no FN or FP in E-treated, say so on screen; never substitute a case from training data.
- Show M2 side by side for the same timestamps and thresholds, with both models’ states.

## 23.2 Data honesty card (shown at the start of the demo)
Table 23.1. Data honesty card.

| Element | What the audience is told |
| Real | CGM values, doses, meal times and static fields from ShanghaiT2DM held-out patients (CC BY 4.0) |
| Replayed | Timing of delivery is simulated at ×120 speed; order is the recorded order |
| Derived | Exposure curves, features, risk, states — computed by the frozen pipeline |
| Aliased | Display names only (“Mr A.”); record IDs available in the Evidence view |
| Synthetic | None in the demo or in any metric; wireframes in documents are illustrative |
| Caveat | Targets are CGM-detected lows; Chinese data; not clinically validated |


## 23.2 Reproducibility
make audit && make freeze && make confirm && make demo reproduces the audit, the frozen protocol, the confirmatory results and the demo from the official data copy. Two consecutive make demo runs must produce the same decision-log hash (Gate G7). A recorded video of the replay and static exports of the Evidence view are kept as a backup.
PART V · IMPLEMENTATION AND DELIVERY

# 24. Repository and Module Structure
TeamName_CollegeName/
├── README.md              problem, claim, how to run, results (auto-filled), limits, licence
├── LICENSE                MIT (code); DATA_LICENSES.md (CC BY 4.0 attribution)
├── Makefile               setup · fetch · audit · freeze · confirm · demo · test
├── config/
│   ├── default.yaml       event, horizon, policy budgets, seeds, paths
│   ├── partition.csv      patient → T/E (seed 2026)          [frozen]
│   ├── pharma.yaml        kernel parameters with sources       [frozen]
│   └── drug_dictionary.csv  product/drug → class, unit, formulation rule
├── data/                  (git-ignored) raw/  MANIFEST.sha256  processed/
├── scripts/  fetch_official · audit · audit2 · freeze · select_demo_cases (.py)
├── hyposense/
│   ├── schema.py          pydantic models (Section 25)
│   ├── adapter.py         load + harmonise + validate one recording
│   ├── meds.py            dose parsing and normalisation
│   ├── exposure.py        kernels, Activity / OnBoard / E_SU, projections
│   ├── labels.py          episodes, eligibility (Section 5.2)
│   ├── state.py           PatientState and its update()
│   ├── features.py        causal snapshot per model level
│   ├── model.py           LightGBM wrapper + isotonic calibrator
│   ├── policy.py          deterministic states, cooldown, logging
│   ├── explain.py         grouped TreeSHAP
│   └── metrics.py         episode metrics, operating curves, cluster bootstrap
├── evaluation/  tune_T.py · run_confirmatory.py · sensitivity.py · report.py
├── api/  main.py (FastAPI) · replay.py · store.py (JSONL logs)
├── web/   React (Vite) — WardBoard, PatientReview, Evidence
├── artefacts/<version>/  model, calibrator, policy.json, results.json, model card
├── demo/   cases.json · honesty_card.md · backup_video_link.md
├── tests/  unit/ · leakage/ · twin/ · e2e/
└── docs/   blueprint.docx · architecture.pdf · deck.pdf · figures/ (.dot/.svg)
Compared with v1.0, the repository loses the ODE, UKF, prior builder, what-if engine, LLM tools and drift monitor, and gains exposure.py, meds.py, an audit, a freeze script and a seeded demo-case selector.

# 25. Implementation Contracts

## 25.1 Conventions
- Time: stored as timezone-aware ISO-8601 (ShanghaiT2DM: +08:00 assumed); internal int64 epoch seconds; windows are half-open: history (t − Δ, t], label (t, t + 3600].
- Units: glucose mg/dL (float32); insulin IU; oral doses mg; rates IU/h; exposure fractions dimensionless.
- Keys: patient_key = "shanghai_t2dm:<prefix>"; recording_key = "<prefix>_<period>_<date>". Grouping always uses patient_key.
- Missing values: None/NaN, never 0; every optional feature has a _missing indicator.

## 25.2 Data schemas
Table 25.1. Core schemas (pydantic models in schema.py).

| Schema | Fields (type) | Invariants |
| Observation | patient_key (str), recording_key (str), ts (int64), kind {cgm, cbg} , value (float32), flags (set[str]) | ts strictly increasing per recording for cgm; value in [20, 600] |
| DoseEvent | patient_key, ts, route {sc, csii_bolus, csii_basal, iv, oral}, product (str), cls (enum), amount (float), unit {IU, mg, IU/h}, formulation (str\|None), raw_text (str), conflict (bool) | cls ∈ dictionary or "unknown"; amount > 0 |
| MealEvent | patient_key, ts, content_known (bool), raw_text (str) | — |
| PatientStatic | patient_key, age, sex, bmi, weight_kg, duration_y, hba1c, egfr, c_peptide_f, regimen_flags (dict[str,bool]) | missing allowed; never the summary hypoglycaemia field |
| ExposureState | ts, activity_by_class (dict), onboard_by_class (dict), e_su, e_glinide, projected_30, projected_60, timing_unknown_by_class (dict) | computed from DoseEvent with ts ≤ t only |
| PatientState | patient_key, ts, cgm_buffer (24 h), exposure (ExposureState), quality (QualityStatus), last_notification_ts, ledger_ref | updated once per Observation |
| FeatureSnapshot | patient_key, ts, level {M1, M2, M3r, M3}, values (float32[n]), names (list), digest (sha1) | names match artefact feature_spec |
| Prediction | patient_key, ts, model_version, p (float\|None), config_hash | p ∈ [0,1] or None |
| PolicyDecision | patient_key, ts, state {ALERT, WATCH, NO_ALERT, LOW_NOW, INSUFFICIENT_DATA, SYSTEM_ERROR}, p, tags, reasons, notify (bool) | notify ⇒ state = ALERT and no notification in previous 3600 s |
| Acknowledgement | decision_id, ts, user_role, reason {checked_glucose, known, sensor_issue, not_relevant}, note | one per notification |
| EpisodeLabel | patient_key, onset_ts, end_ts, end_reason, level {L1, L2}, nadir | from CGM only; offline |


## 25.3 Function contracts
Table 25.2. Function contracts.

| Function | Responsibility | Errors |
| load_recording(path) → RecordingBundle | Read one file, harmonise columns, return typed events + flags | UnknownColumnError; ChecksumError |
| parse_dose(text, route, ts) → list[DoseEvent] | Split components; dictionary lookup; unit conversion; formulation rule | never raises; unknown → cls "unknown" |
| build_episodes(obs, thr, min_run=2, max_step=1200, max_gap=1800) → list[EpisodeLabel] | Section 5.2 rule | ValueError on unsorted input |
| eligible_times(obs, episodes) → array[int64] | Prediction-time eligibility | — |
| exposure_at(doses, t, kernels) → ExposureState | Equations 1–6 with doses ≤ t | AssertionError if any dose ts > t |
| PatientState.update(obs, new_doses) → PatientState | Advance state; recompute quality and exposure | returns state with SYSTEM_ERROR tag on failure |
| snapshot(state, static, level) → FeatureSnapshot | Causal features for one model level | FeatureSpecMismatch |
| RiskModel.predict(snapshot) → float | LightGBM + calibrator | ArtefactHashMismatch at load |
| decide(p, state, policy) → PolicyDecision | Table 14.1 rules | never raises |
| episode_metrics(decisions, episodes, days) → Metrics | Sensitivity, FA/day, lead time, precision | — |
| cluster_bootstrap(fn, patients, B=2000, seed=2027) → CI | Paired patient resampling | — |


# 26. Staged Build and Verification Plan
Figure 26.1. Build dependencies. The protocol freeze separates everything that may use the tuning partition from the single confirmatory run.
Table 26.1. Stages with completion criteria, tests and stop conditions.

| Stage | Work | Completion criterion | Tests | Stop condition |
| S0 | Register team; download official ShanghaiT2DM; repo skeleton; licences | Registration confirmed; MANIFEST written | — | Registration missed → ask organisers |
| S1 | Run audit on official copy; gates G0–G3b | Audit report matches Section 8 or differences explained | audit determinism | G1 fails → stop |
| S2 | Adapter, schema, label builder | All 109 recordings load; episode counts reproduce the audit | golden-file labels; hand-labelled fixtures | Counts differ unexplained |
| S3 | Drug dictionary, parser, kernels (pharma.yaml sourced and reviewed) | ≥99% entries parse; kernels integrate to 1; clinician/pharmacist sign-off | kernel unit tests; dictionary coverage test | G3 fails → context-only branch |
| S4 | State engine, feature builder | Snapshots for M1–M3 on T | truncation-equality leakage test; twin tests (App. H) | Leakage test fails → fix before S6 |
| S5 | Evaluation harness + M0 | Operating curves on T reproduce Figure 8.2 | metric unit tests on fixtures | — |
| S6 | M1 tuning on T; M2, M3r, M3 on T inner CV; Gate G4 | All models run; G4 passed | reproducibility (same hash twice) | G4 fails → M0 operational |
| S7 | Policy, replay, API | Deterministic replay of one T patient | policy table tests; replay hash test | — |
| S8 | Ward Board, Patient Review, Evidence (placeholders) | All six states visible on T replay | E2E (Playwright) script | Slip → Streamlit fallback |
| Freeze | Commit code, config, partition, kernels, analysis plan | Hash recorded in README | freeze script verifies no E access before | — |
| S9 | Confirmatory run on E; results.json; model card | Tables 22.1–22.3 filled automatically | bootstrap seed test; G5 | G5 fails → report inconclusive |
| S10 | Seeded demo cases; video; deck; Gate G7 | Two identical demo runs; video ≥20 min | G7 checklist | G7 fails → recorded video |
| E1 | Optional physiology (Gate G6) | G6 passed before freeze | recovery, stability, low-range tests | Any G6 failure → drop |

Calendar. The event reportedly ends on 20 November 2026 and the Phase-1 deadline is unknown. No duration is promised: the stage order is fixed, and the team should aim to have S0–S5 plus a minimal S7–S8 as a submittable version as early as possible, then S6 → freeze → S9 → S10. With two or more people, S7–S8 run in parallel with S3–S6. No new features after the freeze.

# 27. Scope and Deliverables
Table 27.1. Deliverables matrix.

| Category | Items |
| Must build | Official-data audit and gates; adapter, labels, drug dictionary, kernels; state engine and causal features; M0–M3 incl. M3r; evaluation harness with cluster bootstrap; frozen policy; replay + API; Ward Board and Patient Review; Evidence view from results.json; README, model card, honesty card; repository, architecture document, deck, ≥20-min video |
| Build only if a gate passes | E1 reduced physiological model and M4 (Gate G6); risk bands instead of percentages (if calibration check fails); logistic-regression robustness run (time permitting after S9) |
| Nice to have | Carbohydrate estimation from the English diet text (E3); per-drug-class exploratory analysis; Streamlit-free polish; bedtime-specific analysis |
| Explicitly out of scope | Dose or insulin recommendations; medication what-if scenarios; meal what-if engine; LLM report writer; agents or orchestration frameworks; drift monitors and nightly refits; patient-specific physiological parameters; patient-facing app; external integrations (FHIR/ABDM); external-validation claims; synthetic data in any metric |


# 28. Risks and Mitigations
Figure 28.1. Risk heatmap. Likelihood and impact refer to the credibility of the competition claim.
Table 28.1. Risk register.

| ID | Risk | Type | Mitigation |
| R1 | CGM-detected episodes are partly sensor artefacts (Libre bias at low glucose) | Scientific | CGM-detected naming; L2 secondary; SA4/SA5; capillary-check action |
| R2 | True effect smaller than detectable (MDD 0.10–0.21) | Statistical | Estimation framing; S3 log-loss; honest “inconclusive” category |
| R3 | A few patients dominate episodes | Statistical | Patient-cluster bootstrap; per-patient forest plot; patient-weighted sensitivity |
| R4 | Dose timestamps are charting, not administration, times | Data | Jitter test R1; kernels with peaks ≥60 min; ask dataset authors |
| R5 | Kernel parameters wrong for products or formulations | Scientific | Label-sourced values with pharmacist review; SA6; M3r comparison |
| R6 | Inpatient-like data vs intended setting | Clinical | Use case restricted to ward; no outpatient claims |
| R7 | No Indian data; regimens, diets and sensors differ | Clinical | Section 5.4; clinician review; future silent pilot |
| R8 | Leakage via design iterations on evaluation patients | Engineering | Sealed E; freeze hash; scripts refuse E access before freeze |
| R9 | Official copy differs from mirror | Data | Gate G0 before unsealing |
| R10 | Deadline earlier than assumed; limited capacity | Delivery | Submittable version early; strict scope; stop conditions |
| R11 | Demo failure on the day | Demonstration | Offline Docker image; recorded replay; static exports |
| R12 | Jury sees “not a real twin” without an ODE | Positioning | Explain the state engine; show exposure state updating; present G6 as principled restraint |
| R13 | States misread as clinical instructions | Clinical | Wording reviewed; acknowledgement codes; no “safe” label |
| R14 | Licence attribution missed | Legal | DATA_LICENSES.md; citation in README and deck |


# 29. Competition Pitch and Jury Questions

## 29.1 Seven-step narrative
Table 29.1. Pitch narrative — credible whichever way the primary test goes.

| Step | What is said | What is shown |
| 1 Problem | Treated T2D patients have frequent lows that are easy to miss; ward checks follow a timetable. | One slide; no burden statistics used as proof |
| 2 Insight | Insulin and sulfonylureas keep acting after they are given — the twin tracks that exposure explicitly. | Exposure curve rising after a logged dose |
| 3 What is different | One pre-registered question, a fair ladder, a sealed test set, and honesty about the sensor. | Ladder figure; honesty card |
| 4 The experiment | Does exposure increase episodes warned at one false alert per patient-day over CGM + context? | Protocol figure |
| 5 The real result | [from results.json — whatever it is] | Headline operating curves + Δ with CI |
| 6 Why it matters | If positive: warnings with time to act at no extra alarm cost. If null: a quantified answer and a validated baseline twin. | TP / FN / FP replay |
| 7 Limits and next step | CGM-detected label; Chinese data; internal validation. Next: Indian clinician review and a silent pilot. | Validation path |


## 29.2 Difficult jury questions
Table 29.2. Anticipated questions.

| Question | Answer |
| Is this a twin or a classifier? | A persistent per-patient state updated at every reading, with a mechanistic exposure block and a forecast–outcome ledger; the classifier is one component. We chose not to estimate physiology the data cannot identify. |
| Why drop the physiological model? | Eight states and seven personal parameters from one 15-minute sensor channel are not identifiable, and the model had no counter-regulation. We specify exactly what it would take to bring a reduced version back (Gate G6). |
| Your labels come from a sensor that disagrees with capillary glucose. | Yes — we measured it: mean −12.5 mg/dL overall, and poor agreement around 70 mg/dL in both directions. We call the target CGM-detected, report L2, run a capillary-discordance sensitivity analysis, and make the action a capillary check. |
| How do you know you didn’t tune on the test patients? | The evaluation patients were sealed by a seeded split before modelling; the protocol hash was recorded before they were opened. |
| Why not report AUROC? | It is reported as secondary, but it says little about alarms a ward can tolerate. We lead with episodes warned at a fixed false-alert budget, with lead time. |
| What if exposure doesn’t help? | Then we report that, with its interval, and the twin runs M2. The interpretation matrix was written before the run. |
| With 30 patients, can you detect anything? | Only large effects (≈10–20 points). We say so, and add a higher-powered log-loss comparison. |
| Are dose times real administration times? | Unknown; they are logged daily at 15-minute resolution. The jitter experiment shows how much performance depends on exact timing. |
| Will it work in India? | Not shown. The regimens are similar, but patients, diets and sensors differ. The next step is Indian clinician review and a silent pilot. |
| Does it tell staff what to do? | No. It prioritises who to check; staff decide, and acknowledge every alert. |
| Why ShanghaiT2DM and not AI-READI? | It is open and links CGM with timed doses; whether AI-READI has dose-timed secretagogue data could not be verified, so no external-validation claim is made. |
| What about the 40% of lows in untreated patients? | They are reported (S6). Their causes are unknown — sensor error, fasting or unlogged medication are all possible; the primary claim concerns treated patients, where drug exposure is a plausible mechanism. |


# 30. Final Technical Verdict and Open Decisions

## 30.1 Strongest claims supported now
- ShanghaiT2DM supports the primary test: 348 CGM-detected L1 episodes (154 in 30 treated patients of the sealed partition) and usable, timed, dosed medication records.  VERIFIED 
- The original physiological core is not identifiable from these observations and lacks counter-regulation; removing it from the predictive path is justified.  INFERRED 
- The CGM reads below capillary glucose (mean -12.5 mg/dL), so labels must be named CGM-detected.  VERIFIED 
- A trend rule is a strong baseline on the tuning partition; the bar for any model is real.  VERIFIED  (exploratory)

## 30.2 Unresolved assumptions
- Dose times approximate administration (R4).
- Kernel parameters from labels are adequate (R5).
- The setting is predominantly supervised/inpatient (R6).
- The mirror equals the official copy apart from 188 readings (R9).

## 30.3 Expected evidence after the confirmatory run
Δ sensitivity (M3 − M2) at 1.0 FA/patient-day with a 95% patient-cluster interval; C0–C2 comparisons; calibration; deployed operating point; sensitivity analyses; three seeded replay cases.

## 30.4 Decisions that must wait for experiments
Table 30.1. Open decisions and the rules that settle them.

| Decision | Depends on | Rule |
| Deploy M3, M3r or M2 | Primary and C2b results | Section 15 selection rule |
| Attempt E1 / M4 | Time after S6; Gate G6 | Only if G6 passes before freeze |
| Percentages or risk bands | Development calibration | Calibration slope outside 0.8–1.25 → bands |
| Claim wording | Interpretation matrix row | Table 20.4 |

Verdict. The redesign is narrower than v1.0 and more likely to produce a result that survives scrutiny. Its competitive strength rests on one fair experiment, executed on verified data, presented with its limits — not on architectural sophistication.
APPENDICES

# Appendix A. Feasibility Audit: Results and Reproduction
Source: two identical public GitHub mirrors of the ShanghaiT2DM folder (109 recording files + summary; MD5-identical to each other), converted from .xls to .xlsx with LibreOffice. Scripts: scripts/audit.py (events, medication usability, folds) and scripts/audit2.py (CGM–CBG agreement, artefact heuristic, partition, exploratory M0 on T). Both are deterministic and read files only from a path argument. Status of every number:  VERIFIED  on the mirror; to be re-run on the official copy (Gate G0).
Table A.1. Audit outputs not already shown in Section 8.

| Quantity | Value |
| Recordings / patients / CGM readings | 109 / 100 / 112287 |
| Monitored days | 1168.8 |
| L1 / L2 / single-reading episodes | 348 / 96 / 430 |
| Patients with L1 / L2 | 61 / 26 |
| Patients with logged insulin / SU / glinide / any of these | 60 / 14 / 3 / 73 |
| Treated patients with ≥1 L1 | 43 |
| L1 end reason | recovered 346; record end 2 |
| CBG values / recordings with CBG | 3262 / 94 |
| CGM–CBG pairs (±8 min); mean, median CGM − CBG | 3262; -12.5, -9 mg/dL |
| Mean CGM − CBG when CBG <100 (n pairs) | 1.9 mg/dL (321) |
| CBG <70 pairs with CGM <70 | 8 of 18 |
| Nocturnal compression-artefact candidates (heuristic) | 9 |
| Balanced 5-fold simulation (all patients): episodes per fold | 70, 70, 70, 69, 69; patients with episodes per fold 11, 13, 13, 12, 12 |
| Partition T / E: patients; treated; treated episodes | 30 / 70; 22 / 51; 56 / 154 |
| Insulin s.c. entry hours (most frequent) | 6:00 (149), 7:00 (98), 11:00 (44), 16:00 (73), 17:00 (103), 18:00 (54), 20:00 (63), 21:00 (61) |

Table A.2. Exploratory M0 operating points on the tuning partition (56 treated / 117 total episodes; 255 / 348 patient-days).  VERIFIED  exploratory only.

| θ (mg/dL) | Sensitivity (treated T) | FA / patient-day | Median lead (min) | Sensitivity (all T) | FA / patient-day (all T) |
| 40 | 0.43 | 0.60 | 30 | 0.50 | 0.65 |
| 45 | 0.48 | 0.73 | 30 | 0.54 | 0.79 |
| 50 | 0.55 | 0.85 | 30 | 0.58 | 0.92 |
| 55 | 0.64 | 1.07 | 45 | 0.66 | 1.15 |
| 60 | 0.77 | 1.37 | 45 | 0.77 | 1.46 |
| 65 | 0.86 | 1.84 | 45 | 0.85 | 1.93 |
| 70 | 0.91 | 2.22 | 45 | 0.88 | 2.31 |
| 80 | 0.95 | 3.65 | 60 | 0.90 | 3.73 |


## A.1 Audit procedure (outline)
for recording in sorted(files):                       # read-only; path passed as argument
    x = harmonise(read_excel(recording))              # 5 column variants -> canonical names
    cgm = x[x.cgm.notna()].sort_values("ts")
    L1 = episodes(cgm, thr=70, min_run=2, max_step=20min, max_gap=30min)
    L2 = episodes(cgm, thr=54, ...); L1s = episodes(cgm, thr=70, min_run=1)
    doses = [parse(t) for t in x.ins_sc] + [parse(t) for t in x.oral] + csii + iv
    eligible = [t for t in cgm.ts if cgm(t) >= 70 and not in_episode(t) and not refractory(t)
                and history_ok(t, 120min, >=7) and follow_up_ok(t, 60min)]
    positives = [t for t in eligible if onset in (t, t + 60min]]
    record counts, parse rates, coverage, prescribed-vs-logged conflicts, CBG pairs
partition = stratified_split(patients, strata=(treated, has_L1), frac_T=0.30, seed=2026)
M0 on T only: slope of last 30 min -> projection at t+60; ALERT if < theta; 60-min cooldown

# Appendix B. Medication Normalisation Dictionary
Table B.1. Dictionary rules (to be reviewed by a clinical pharmacist before freeze).

| Text pattern (case-insensitive) | Class | Kernel | Notes |
| insulin aspart 70/30; aspart 50/50 | premix analogue | 30% (or 50%) rapid + 70% (50%) intermediate | NovoMix-type |
| Novolin 30R; Humulin 70/30; Gansulin 40R | premix human | 30% (40%) regular + 70% (60%) NPH | Proportions from product name |
| Novolin R; Gansulin R; Humulin R | short human (regular) | regular | s.c. only; CSII uses the same kernel |
| insulin aspart; glulisine; lispro | rapid analogue | rapid | — |
| glargine (incl. misspelling “glarigine”); detemir; degludec | basal analogue | flat 24 h after 1 h lag | Typos handled by fuzzy match |
| Novolin N; Humulin N; NPH | intermediate | NPH | Not observed in audit; rule kept |
| CSII bolus (IU) / basal (IU/h) | CSII regular | regular; basal as 15-min micro-boluses | Rate persists until next entry |
| “… IU Novolin R …” in infusion text | i.v. insulin | none (flag 4 h) | Infusion rate not recorded |
| gliclazide | sulfonylurea | Bateman | Formulation: dose multiple of 30/60/120 → MR; 40/80/160 → IR; else flag |
| glimepiride; glibenclamide/glyburide; glipizide; gliquidone | sulfonylurea | Bateman | Per-drug t½, t_max, D_max (App. C) |
| repaglinide; nateglinide | glinide | Bateman (short) | — |
| metformin; acarbose; voglibose; gliptin; gliflozin; pioglitazone; liraglutide etc. | flags | none | Presence and daily count only |

Data-quality findings from the oral-agent text:  VERIFIED  several entries carry implausible units, e.g., “voglibose 0.2 g” (usual unit: mg), “empagliflozin 10 g”, “metformin 50 mg”, “linagliptin 0.1 g”. They affect only flag classes, so exposure is unaffected; the parser checks each drug against a plausible-dose range and flags out-of-range entries. Secretagogue doses observed (gliclazide 15–120 mg, glimepiride 2 mg, repaglinide 0.5–3 mg) were within plausible ranges.

# Appendix C. Exposure Kernel Parameters

| Status / The values below are illustrative (they generate Figure 12.1). Production values must be taken from current product labels, entered in config/pharma.yaml with source and date, and reviewed by a clinical pharmacist before the protocol freeze.  PENDING  |

Table C.1. Kernel parameter template.

| Kernel | Parameters (illustrative) | Production source | Status |
| Rapid analogue | t_p 75 min, t_d 300 min | Product label (aspart, glulisine, lispro) |  ILLUSTRATIVE  |
| Regular human | t_p 150 min, t_d 480 min | Product label (Novolin R, Gansulin R, Humulin R) |  ILLUSTRATIVE  |
| Intermediate (NPH) | t_p 360 min, t_d 900 min | Product label |  ILLUSTRATIVE  |
| Basal analogue | flat, 1 h lag, 24 h | Product labels (glargine, detemir, degludec) |  ILLUSTRATIVE  |
| Sulfonylurea (per drug and formulation) | t½ 12 h, t_max 4 h; D_max from label | Product labels |  ILLUSTRATIVE  |
| Glinide | t½ 1 h, t_max 1 h; D_max from label | Product labels |  ILLUSTRATIVE  |


# Appendix D. Feature Dictionary
Table D.1. Features by group. The summary field “Hypoglycemia (yes/no)” and any patient identifier are excluded.

| Group | Features (all computed from data ≤ t) | Models |
| 1 CGM level | g(t); g at t − 15, − 30, − 45, − 60; M0 projection at t + 30 and t + 60 | M1–M4 |
| 2 CGM trend | least-squares slope over 30, 60, 120 min; acceleration (slope 30 − slope 60); number of consecutive falling readings | M1–M4 |
| 3 CGM variability and personal history | min, mean, SD over 2 h, 6 h, 24 h; CV 24 h; minutes <80 mg/dL in past 24 h; prior L1 onsets in the recording before t (from CGM ≤ t); minutes since last reading <70; percentile of g(t) within own history (≥24 h, else missing); sensor day | M1–M4 |
| 4 Time | hour-of-day sine and cosine; night flag (00:00–05:59) | M1–M4 |
| 5 Static context | age, sex, BMI, weight, diabetes duration, HbA1c, eGFR, fasting C-peptide; prescribed-regimen flags (insulin, premix, basal, short/rapid, SU, glinide, metformin, AGI, DPP-4, SGLT2, GLP-1, TZD); missing indicators | M2–M4 |
| 6 Meal timing | minutes since last logged meal (cap 720); meal logged in last 3 h; meals logged today; last meal content unknown | M2–M4 |
| 7 Raw dose timing | per class: minutes since last dose (cap 1440), last dose amount, 24-h total, doses in 24 h; CSII active; i.v. flag | M3r |
| 8 Exposure state | insulin activity and on-board (short/rapid, intermediate, basal components; total; per kg); E_SU, E_glinide; projections to t + 30, t + 60; Δexposure next 60 min; minutes since last insulin / secretagogue dose; timing-unknown indicators; CSII active; i.v. flag | M3, M4 |
| 9 Physiology (optional) | E1 one-step and 30/60-min glucose forecasts; tracked gain γ | M4 |


# Appendix E. Metric Definitions and Notation
Table E.1. Definitions used by metrics.py.

| Symbol / metric | Definition |
| t, H | Prediction time; horizon = 60 min |
| y(t) | 1 if an L1 onset occurs in (t, t + H], else 0 (defined only at eligible t) |
| p(t) | Calibrated model probability that y(t) = 1 |
| S(t) ∈ {ALERT, WATCH, NO ALERT, LOW NOW, INSUFFICIENT DATA, SYSTEM ERROR} | Policy state |
| Hit(e) | 1 if ∃ eligible t ∈ [onset_e − 60, onset_e − 15] with S(t) = ALERT |
| Sensitivity | Σ_e Hit(e) / number of episodes |
| Lead(e) | onset_e − min{t ∈ window : S(t) = ALERT}, for hits |
| Notification n at t_n | S(t_n) = ALERT and no notification in (t_n − 60 min, t_n) |
| False alert | notification with no onset in (t_n, t_n + 60] |
| FA rate | false alerts / Σ monitored days |
| sens@1FA | Linear interpolation of the (FA rate, sensitivity) operating curve at FA rate = 1.0 |
| Δ | sens@1FA(M3) − sens@1FA(M2) on the same patients |
| Patient-cluster bootstrap | Draw patients with replacement (B = 2,000, seed 2027); recompute both models’ curves and Δ on each resample; 95% percentile interval |
| m_w | Σ m_i² / Σ m_i, m_i = episodes of patient i (effective cluster size) |
| Design effect | 1 + (m_w − 1)·ICC |
| ECE | Σ_bins (n_b/N)·\|mean p − mean y\| over 10 equal-count bins |


# Appendix F. Configuration Template
# config/default.yaml (frozen at protocol freeze; hash recorded in results.json)
event:
  {threshold_mgdl: 70, l2_threshold_mgdl: 54, min_run: 2, max_step_min: 20,
   max_gap_min: 30, horizon_min: 60, min_lead_min: 15, refractory_min: 60}
eligibility: {history_min: 120, min_readings_in_history: 7, follow_up_min: 60}
population: {primary: treated, treated_def: [insulin_any, sulfonylurea, glinide]}
partition: {file: config/partition.csv, seed: 2026, frac_T: 0.30}
cv: {folds: 5, seed: 2026, inner_folds: 4}
model:
  {learner: lightgbm, objective: binary, deterministic: true, num_threads: 1,
   seed: 2026, tuned_on: M1, optuna_trials: 30}
calibration: {method: isotonic, band_rule: {slope_min: 0.8, slope_max: 1.25}}
policy:
  {fa_budget_alert: 1.0, fa_budget_watch: 3.0, cooldown_min: 60, max_gap_min: 20,
   floor_mgdl: 40, max_rate_mgdl_per_min: 4, warmup_min: 120,
   range_pct: [0.5, 99.5]}
exposure:
  {pharma: config/pharma.yaml, dictionary: config/drug_dictionary.csv,
   timing_unknown_after_h: 36, iv_flag_h: 4, projections_min: [30, 60]}
bootstrap: {resamples: 2000, seed: 2027, unit: patient}
replay: {speed: 120, source: E_out_of_fold, cases: demo/cases.json}

# Appendix G. Data-Quality Report Template
Table G.1. Generated automatically by scripts/audit.py --report.

| Section | Fields |
| Provenance | source URL/DOI, download date, SHA-256 per file, licence, mirror vs official differences |
| Structure | files, patients, recordings per patient, column variants found, unmapped columns |
| CGM | readings, interval histogram, gaps >20/30/60 min, floor readings, rate flags, warm-up readings |
| Events | L1, L2, single-reading counts; per patient distribution; nocturnal; first 24 h; warnable share |
| Medication | entries by route; parse rate; unknown products; implausible units; coverage of days; prescribed-vs-logged conflicts; formulation inferences |
| Meals | entries; content not available; timing gaps |
| Label validity | CGM–CBG pairs, bias overall and <100 mg/dL, episodes with CBG during, confirmed share |
| Partition | T/E counts by stratum; treated episodes; m_w |
| Gate decisions | G0–G3b outcome, evidence, date, reviewer |


# Appendix H. Experiment Tracking and Test Checklist
Table H.1. Experiment tracking table.

| Run ID | Partition | Model | Config hash | Code commit | Data hash | Primary metric | Notes |
| T-M0-001 | T | M0 | [ ] | [ ] | [ ] | exploratory | Figure 8.2 |
| T-M1-tune | T | M1 | [ ] | [ ] | [ ] | inner log-loss | ≤30 trials |
| T-ladder | T | M1–M3 | [ ] | [ ] | [ ] | development only | Gate G4 |
| E-confirm | E | M0–M3 | [ ] | [ ] | [ ] | Δ sens@1FA | once, after freeze |

Table H.2. Twin, leakage and policy tests (CI).

| Test | Pass condition |
| test_no_future_leak | Snapshot from full record equals snapshot from record truncated at t (random t, all levels) |
| test_group_by_patient | No patient_key appears in both training and test of any fold; T and E disjoint |
| test_labels_fixtures | Episode builder reproduces 20 hand-labelled fixtures incl. gaps and floor values |
| test_exposure_causal | Exposure at t unchanged by adding doses after t |
| test_kernel_integrals | Each insulin kernel integrates to 1 ± 0.01 over its duration |
| test_state_updates | Each reading changes the state timestamp and appends to the ledger |
| test_dose_raises_exposure | Adding a secretagogue dose increases E_SU at later times and not before |
| test_missing_abstains | A 45-min gap yields INSUFFICIENT DATA and no probability |
| test_uncertainty_never_silences | LOW CONFIDENCE tag never changes ALERT to another state |
| test_cooldown | No two notifications for a patient within 60 min |
| test_policy_table | All rows of Table 14.1 produce the specified state |
| test_replay_determinism | Two replays produce identical decision-log hashes |
| test_freeze_guard | Confirmatory script refuses to run without a recorded freeze hash; tuning scripts refuse E patients |
| test_long_run | 14-day replay at ×600 without exceptions or memory growth |


# Appendix I. Source and Assumption Register
Table I.1. Source and assumption register.

| Claim | Source | Status | Check still needed |
| Event, medication and partition counts | Audit of GitHub mirror (this review) |  VERIFIED  | Re-run on official copy (G0) |
| ShanghaiT2DM: 100 T2D patients, 109 files, 15-min FreeStyle Libre H, two Shanghai hospitals, CC BY 4.0 | Data descriptor [1], via Nature page |  VERIFIED  | — |
| 112,475 CGM readings published | Data descriptor table [1]; Glucose-ML [23] |  VERIFIED  | Explain −188 difference |
| Care setting predominantly supervised/inpatient | Inferred from CSII, i.v. insulin, CBG frequency |  ASSUMPTION  | Ask dataset authors |
| Dose entries approximate administration time | Inferred from daily logging pattern |  ASSUMPTION  | Jitter test R1; authors |
| Libre Pro reads below POC glucose on average and flags more lows than POC in hospitalised T2D | Galindo et al. 2020 [6] |  VERIFIED  | — |
| Episode definition (≥15 min, end after ≥15 min ≥70) | Consensus as summarised in [5]; Battelino 2023 [3] |  VERIFIED  (secondary) | Read [3] full text for end rule wording |
| Endocrine Society supports considering CGM with POC confirmation in hospital | Press release for [8] |  VERIFIED  (secondary) | Read guideline text for grading |
| Inpatient ML hypoglycaemia model, 24-h horizon, ~55,000 admissions | Endocrine News summary of [7] |  VERIFIED  (secondary) | Read paper for metrics |
| Simulators added glucagon/counter-regulation | [9] |  REPORTED  | Read full text |
| Minimal-model numerical non-identifiability | [11] |  REPORTED  | Read full text |
| Small-data benchmarks favour simple models | GlucoBench [12] as cited in v1 |  REPORTED  | Read paper |
| ICMR-INDIAB burden; SU hypoglycaemia in Indian practice | [18], [19] as cited in v1 |  REPORTED  | Not used as evidence of model performance |
| CDSCO draft guidance on medical device software (Oct 2025) | Secondary legal summary [20] |  VERIFIED  (secondary) | Official CDSCO text |
| Competition requirements, dates, rubric | v1 blueprint citing the listing [22] |  REPORTED  | Organiser confirmation |
| Kernel parameter values | Illustrative |  ILLUSTRATIVE  | Product labels + pharmacist |
| M3 improves on M2 | — |  HYPOTHESIS  | Confirmatory run |
| Evaluation report content | Issue list in the redesign brief (report itself not supplied) |  REPORTED  | Obtain full report if available |


# Appendix J. References
[1] Zhao Q, Zhu J, Shen X, Lin C, Zhang Y, Liang Y, Cao B, Li J, Liu X, Rao W, Wang C. Chinese diabetes datasets for data-driven machine learning. Scientific Data. 2023;10. doi:10.1038/s41597-023-01940-7.
[2] Diabetes Datasets — ShanghaiT1DM and ShanghaiT2DM. figshare collection. doi:10.6084/m9.figshare.c.6310860 (CC BY 4.0). Mirror used for the audit: github.com/Kartikey-Bartwal/Shanghai-Diabetes-Dataset-to-detect-if-the-person-has-type-1-or-type-2-diabetes (accessed 17 Oct 2026).
[3] Battelino T, et al. Continuous glucose monitoring and metrics for clinical trials: an international consensus statement. Lancet Diabetes Endocrinol. 2023. PMID 36493795.
[4] AI-READI Consortium. Flagship dataset of type 2 diabetes (Bridge2AI), FAIRhub (as cited in v1; access conditions not re-verified).
[5] Koutroukas V, Thomas J, Martine-Edith G, et al. Exploring the impact of different definitions of level 1 and level 2 sensor-detected hypoglycaemia upon frequency of hypoglycaemia and time below range: the Hypo-METRICS study. Diabetes Obes Metab. 2025;28(1):775–778. doi:10.1111/dom.70238.
[6] Galindo RJ, Migdal AL, Davis GM, et al. Comparison of the FreeStyle Libre Pro flash continuous glucose monitoring (CGM) system and point-of-care capillary glucose testing in hospitalized patients with type 2 diabetes treated with basal-bolus insulin regimen. Diabetes Care. 2020;43(11):2730–2735. doi:10.2337/dc19-2073.
[7] Mathioudakis NN, et al. Development and validation of a machine learning model to predict near-term risk of iatrogenic hypoglycemia in hospitalized patients. JAMA Netw Open. 2021.
[8] Korytkowski MT, et al. Management of hyperglycemia in hospitalized adult patients in non-critical care settings: an Endocrine Society clinical practice guideline. J Clin Endocrinol Metab. 2022.
[9] Dalla Man C, Micheletto F, Lv D, Breton M, Kovatchev B, Cobelli C. The UVA/PADOVA type 1 diabetes simulator: new features. J Diabetes Sci Technol. 2014;8(1):26–34.
[10] Bergman RN, Ider YZ, Bowden CR, Cobelli C. Quantitative estimation of insulin sensitivity. Am J Physiol. 1979;236(6):E667–E677.
[11] Pillonetto G, Sparacino G, Cobelli C. Numerical non-identifiability regions of the minimal model of glucose kinetics: superiority of Bayesian estimation. Math Biosci. 2003;184(1):53–67.
[12] Sergazinov R, et al. GlucoBench: curated list of continuous glucose monitoring datasets with prediction benchmarks. ICLR 2024.
[13] Field CA, Welsh AH. Bootstrapping clustered data. J R Stat Soc Series B. 2007;69(3):369–390.
[14] Chakraborty DP. Observer Performance Methods for Diagnostic Imaging (free-response ROC methodology). CRC Press; 2017.
[15] OpenAPS documentation. Understanding insulin on board (IOB) calculations. openaps.readthedocs.io (accessed 17 Oct 2026).
[16] Ke G, et al. LightGBM: a highly efficient gradient boosting decision tree. NeurIPS 2017.
[17] Lundberg SM, et al. From local explanations to global understanding with explainable AI for trees. Nat Mach Intell. 2020;2:56–67.
[18] Anjana RM, et al. Metabolic non-communicable disease health report of India: the ICMR-INDIAB national cross-sectional study. Lancet Diabetes Endocrinol. 2023.
[19] Kalra S, et al. OBSTACLE hypoglycemia study (sulfonylurea users in India). Diabetes Technol Ther. 2013 (as cited in v1).
[20] India Briefing. CDSCO moves to regulate medical device software in India: key takeaways (draft guidance dated 21 Oct 2025). Published 12 Nov 2025.
[21] Digital Personal Data Protection Act 2023 and DPDP Rules 2025, Government of India (as cited in v1; verify against the official gazette).
[22] Happiest Health / Unstop. Digital Twin Challenge 2026 listing (as cited in v1; not renderable during this review).
[23] Glucose-ML: a collection of longitudinal diabetes datasets for development of robust AI solutions. arXiv:2507.14077 (preprint).
[24] HypoSense Twin — Research & Engineering Blueprint v1.0 (internal, 17 Oct 2026).
References marked  REPORTED  in Appendix I were not re-read in full during this review; their use is limited to context, never to support a performance claim.

# Appendix K. Glossary
Table K.1. Glossary.

| Term | Meaning |
| CGM | Continuous glucose monitoring (here a professional flash sensor, 15-min readings) |
| CBG / POC | Capillary blood glucose / point-of-care meter reading |
| L1 / L2 episode | CGM-detected episode below 70 / 54 mg/dL (Section 5.2) |
| Treated patient | Logged insulin or sulfonylurea or glinide |
| SU, glinide | Insulin secretagogues: sulfonylureas and meglitinides |
| CSII | Continuous subcutaneous insulin infusion (insulin pump) |
| Exposure state | Time-resolved insulin activity / on-board and secretagogue exposure computed from logged doses |
| M0–M4, M3r | Model ladder (Section 19) |
| T / E | Tuning partition / sealed evaluation partition |
| FA/day | False alerts per patient-day |
| Operating curve (FROC-style) | Episode sensitivity against false alerts per patient-day |
| m_w, ICC, design effect | Clustering statistics for episodes within patients |
| Gate | A pre-defined measurable check that decides whether the work proceeds, narrows or falls back |
| Freeze | Commit of code, configuration and analysis plan before the evaluation partition is opened |

