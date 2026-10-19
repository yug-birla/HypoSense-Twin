# P-C11 approval matrix (ANALYSIS_PLAN §5.7, items 1–33)

Status: **AWAITING OWNER DECISION.** This matrix is a review aid. It approves nothing.

Every item was written before E was opened. None changes the target event, horizon, warning
window, primary endpoint, population, H1, bootstrap method or false-alert budget; each makes
blueprint wording executable. All items are implemented in `evaluation/confirm*.py` and were
exercised by the T rehearsal (`T-AGG-rehearsal-20261019T070224Z`, which reproduces S6 exactly).

Classification:
- **SPEC:** restates an already approved rule (ANALYSIS_PLAN §2–§6, Blueprint §15) for the E
  run.
- **OPDEF:** an operational definition the blueprint leaves open. It is a Class C choice, since
  it fixes how a pre-specified analysis is computed.
- **ENG:** an engineering or governance rule with no effect on any number.

| # | Rule (short) | Source | Class | Recommendation | Approval needed |
|---|---|---|---|---|---|
| 1 | 5 grouped E folds, strata treated × has-L1, seed 2026 | Blueprint §15; S6 fold code | SPEC | Approve | Confirm |
| 2 | Train on T ∪ (E∖k) eligible rows, frozen hyperparameters, 113 rounds, no P-B6 exclusion | §15; DEC-2026-10-19-M | SPEC | Approve | Confirm |
| 3 | 4 inner folds; calibrator on inner-OOF eligible rows; τA/τW from calibrated inner OOF | §15; ANALYSIS_PLAN §3.4–3.6 | SPEC | Approve | Confirm |
| 4 | Fold model scores held-out E through its fold calibrator | §15 | SPEC | Approve | Confirm |
| 5 | Pooled OOF curves; no threshold carried across folds | §3 | SPEC | Approve | Confirm |
| 6 | Deployed operating point: each patient at its own fold τA | §15 "deployed operating point" | OPDEF | Approve | **Yes** |
| 7 | Primary rule, H1 iff lower bound > 0; G5 = no undefined resample, else inconclusive | §5.1; Table 21.1 | SPEC | Approve | Confirm |
| 8 | S1: lead ≥ 30 min | Table 20.3 | OPDEF | Approve | **Yes** |
| 9 | S2: FA at M2's sens@1FA, first-crossing linear interpolation, s* re-estimated per resample | Table 20.3 | OPDEF | Approve | **Yes** |
| 10 | S3: window log-loss Δ, patient-weighted ratio estimator | §5.3 item 7 | SPEC | Approve | Confirm |
| 11 | S4: C0/C1/C2a/C2b on sens@1FA, area, log-loss | Table 20.3; S6 | SPEC | Approve | Confirm |
| 12 | S5: L2 episodes (< 54 mg/dL), other rules unchanged | Table 20.3 | OPDEF | Approve | **Yes** |
| 13 | S6: all E patients | Table 20.3 | SPEC | Approve | Confirm |
| 14 | S7: per-patient sensitivity and FA/day at τA; patient-weighted sensitivity | Table 20.3 | OPDEF | Approve | **Yes** |
| 15 | SA1: single-reading episodes | Table 20.3 | OPDEF | Approve | **Yes** |
| 16 | SA2: drop the first 24 h of each recording | Table 20.3 | OPDEF | Approve | **Yes** |
| 17 | SA3: drop recordings with CSII or i.v. insulin | Table 20.3 | OPDEF | Approve | **Yes** |
| 18 | SA4/SA5/SA9-i: excluded episodes leave the denominator; notifications still classified against all onsets | Table 20.3; P-C8c | OPDEF | Approve | **Yes** |
| 19 | SA9-ii: notifications overlapping a sensor-floor run removed from FA, counted separately | P-C8c | OPDEF | Approve | **Yes** |
| 20 | SA6: insulin t_dur and secretagogue t_half × 0.75 / × 1.5; features rebuilt; M3 refitted | Table 20.3 | OPDEF | Approve | **Yes** |
| 21 | SA7: fold seeds 2028–2032 | Table 20.3; config | SPEC | Approve | Confirm |
| 22 | SA8: no laboratory features | Table 20.3; context.LAB_FIELDS | SPEC | Approve | Confirm |
| 23 | P-B6 training-exclusion sensitivity | DEC-2026-10-19-M | SPEC | Approve | Confirm |
| 24 | R1: dose times jittered ±30 / ±60 min in held-out folds only | Table 20.3 | OPDEF | Approve | **Yes** |
| 25 | R2: 10 / 20 % CGM removed, random or in blocks; labels from the full record | Table 20.3 | OPDEF | Approve | **Yes** |
| 26 | R3: L2-penalised logistic regression (C = 1). T rehearsal property disclosed: overfits `rx_*`, sens 0.30 | Table 20.3 | OPDEF | Approve as written. Changing the learner after seeing T output would be result-driven | **Yes** |
| 27 | R4: per-model hyperparameters tuned on T before freeze (`T-AGG-dev-r4-20261019T055800Z`) | Table 20.3 | OPDEF | Approve | **Yes** |
| 28 | §6 selection applied mechanically to frozen point estimates | §6 (approved DEC-2026-10-19-N) | SPEC | Approve | Confirm |
| 29 | Final model: selected level retrained on all patients with the S7 procedure | §15 | SPEC | Approve | Confirm |
| 30 | Demo cases: TP/FN/FP from M3 pooled E-treated OOF at fold τA; eligibility windows; seed 2026; no substitute if a category is empty | Blueprint §23.1 | OPDEF | Approve | **Yes** |
| 31 | "≈" in Table 20.4 = CI includes 0; "S3 favours M3" = point log-loss Δ < 0 | Table 20.4 | OPDEF | Approve | **Yes** |
| 32 | Run once; a second execution is only a bitwise reproduction check | CLAUDE.md §12; brief | ENG | Approve | Confirm |
| 33 | Read-only E access after the single official run, for held-out replay and the report | DEC-2026-10-19-O | ENG | Approve | Confirm |

**Summary:**
- 14 items restate approved rules (SPEC).
- 17 items are operational definitions that need an explicit decision (OPDEF): 6, 8, 9, 12,
  14–20, 24–27, 30 and 31.
- 2 items are engineering or governance rules (ENG).

One decision ("approve P-C11 as written", or a per-item amendment) unblocks the
`class_c_resolved` and `analysis_plan_final` freeze checks.

**How to record approval:**
1. Change the §5.7 status line in ANALYSIS_PLAN and the P-C11 status in PROPOSALS to APPROVED,
   with the date.
2. Add a DECISION_LOG entry.

Both edits are documentation; neither changes code. An amendment that changes code requires the
rehearsal and the candidate pair to be rerun before freeze.
