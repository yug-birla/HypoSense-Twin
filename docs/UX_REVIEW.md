# Judge-readiness UX review (2026-10-19)

Scope: presentation only. No endpoint, label, feature, model, calibration, threshold, policy
rule, kernel or evaluation definition was changed. The UI remains a rendering layer over
backend-decided states. The two backend additions are display-only:
- `POST /api/replay/advance-until-notification`, which advances the real replay in its fixed
  order;
- extra fixed "Ask" intents.

## 1. Problems found (real screenshots, newcomer walkthrough)

1. **No answer to "what is this?"** The app opened on a 36-checkbox case picker labelled with
   dataset terms ("tuning partition", "R0").
2. **Jargon:** τ thresholds, "Grouped TreeSHAP", "record clock", "ledger",
   "Pending (window open)", "Timing unknown: sulfonylurea".
3. **Observed and predicted looked alike.** CGM and risk % sat in identical boxes.
4. **Ward:** 9 equally weighted columns; "<1%" without meaning; two different "now" times.
5. **Chart:** toggle chips, dashed thresholds and the risk subplot were unexplained.
6. **Medication chart:** recorded doses and model-estimated activity were distinguished only by a
   caption.
7. **Replay:** looked like a debug control ("1 d 6 h", "+1 h", "×120"), with no story.
8. **Evidence:** opened with the model ladder, curves and calibration, with no plain summary.
9. **Add patient:** no progress indicator; questions did not say what happens if unanswered.
10. **Ask panel:** terse labels; missing "are readings current?", "why no forecast?" and
    "what happened after the alert?".

## 2. What changed

| Area | Change |
|---|---|
| Information architecture | Overview (`/`), Guided demo, Ward board (`/ward/`), Patient twin, Add patient, Evidence |
| Overview | What HypoSense is (one paragraph), prototype status, three ways in, a 5-step "How the twin works" strip (matches the implemented pipeline), the states grouped as *Observed now* / *Prediction* / *No forecast* |
| States | Every status pill can show its plain meaning on hover or keyboard focus (`STATE_MEANING`, verified against `policy/decide.py`). LOW NOW = observed; ALERT = prediction, "glucose is not necessarily low now"; NO ALERT = "not a guarantee" |
| Ward | Columns: Patient · Status · Glucose now (value + direction) · Risk 60 min · Why · Last reading · Alerts. Help tips on headers. Quality warnings under the reason. "not current" made explicit. One-click "Start replay of 8 recorded patients", with other recordings in a disclosure. Replay bar labelled "Replay of recorded data", with speed in plain units |
| Patient | Organised as four questions: **What is happening now?** (state + meaning; *Observed now* solid tile vs *Predicted · next 60 min* dashed tile marked DEVELOPMENT, not clinically validated, or "No forecast" with the reason) · **How did we get here?** (glucose chart + "How to read this chart"; medicine chart split *Recorded* vs *Estimated*) · **Why is HypoSense showing this?** (one sentence → associated information in plain group names → *Technical detail* disclosure with probability, thresholds, reason codes and method) · **What happened after each forecast?** (plain outcomes) |
| Guided demo | 8 steps driving the real replay through the normal API. The alert shown is the first notification in replay order; step 7 reads that alert's real outcome from the backend history, including a false alert |
| Add patient | 5-step stepper. Every question shows *Why we ask* and *If you can't answer*. Plain section names ("What we found", "Your file, as we read it") |
| Ask | 9 fixed questions in natural language, answered only from recorded state. New: why (no) forecast, are readings current, after the last alert |
| Evidence | "Understand the evidence" (6 plain questions using the canonical numbers + a metric glossary) above "Technical evidence" (unchanged: ladder, curves, CIs, comparisons, calibration, gates, safeguards, provenance) |

## 3. Expert-role heuristic review

This is **not a user study**. It is a structured self-review against the real interface, using
three personas. No independent testers were available.

| Persona | Question | Where answered | Clicks from open |
|---|---|---|---|
| Non-technical judge | What does HypoSense do? | Overview, first paragraph | 0 |
| | How do I start a demo? | Overview primary card "Guided demo (5 min)" | 1 |
| | What does an ALERT mean? | Overview "What the states mean"; hover on any pill; patient header sentence | 0–1 |
| | How do I add patient data? | Overview card / nav "Add patient", with stepper | 1 |
| Clinician / researcher | Observed vs predicted? | Patient header: solid *Observed now* vs dashed *Predicted* tile; LOW NOW grouped as observed | 0 on patient |
| | Data quality? | Patient "Can the data be trusted right now?"; Ask "Are readings current?" | 0–1 |
| | Medication exposure assumptions? | Medicine chart caption (recorded vs estimated; not a blood level); Evidence limitations | 0 |
| | Why this state? | "Why is HypoSense showing this?" sentence + associated information | 0 |
| | Clinical limitations? | Overview "Not a medical device…"; Evidence "What are the limitations?" | 0–1 |
| ML / technical judge | Architecture? | Overview strip; Technical detail on patient; docs/ARCHITECTURE.md | 1 |
| | Model ladder, protocol? | Evidence "What is being compared?" → Technical evidence | 1 |
| | Reproducibility? | Evidence "Reproducibility and provenance" (hashes, runs) | 1 |
| | Development vs confirmatory? | Evidence plain card "Is the final evaluation complete? No — PENDING" + Confirmatory panel | 1 |

Residual weaknesses, found and not fixed:
- Fixed after review: the ward "Why" column now reads, for example, "Elevated risk; most
  associated with glucose level and recent glucose history" (plain group names live in the
  backend, `policy/messages.py`).
- The guided-demo dock covers part of the right column. It can be minimised, and the page gains
  bottom space while the demo runs.
- The patient page is long; sections are ordered by the four questions.

## 4. Verification

- Microsoft Edge, 1440 / 1280 / 1024 px. Screenshots are in `artifacts/screenshots/judge/` (T
  traces, git-ignored) and `docs/screenshots/intake/` (SYNTHETIC).
- Guided demo driven end to end through the UI (`scripts/ui_judge_qa.py`); 0 console errors.
- axe-core WCAG 2 A/AA: 0 violations on Overview, Demo, Ward, Patient, Evidence and Add patient
  (`T-AGG-s8-ui-audit-20261019T130249Z`).
- Tests:
  - Vitest 42;
  - Python 572;
  - browser E2E 3: replay + acknowledgement, intake, guided demo.

## 5. Five-minute judge demonstration script

1. **(0:00) Overview.** "HypoSense estimates whether a CGM-detected low will begin within the
   next hour, so staff can check earlier. It is a research prototype; it never suggests doses."
   Point to the 5-step strip and the three state groups.
2. **(0:40) Guided demo → Start the replay.** Eight recorded patients from the development
   data, chosen by catalogue order rather than by result.
3. **(1:10) Advance 2 hours.** The board orders patients by status. Hover a status to show its
   meaning.
4. **(1:40) Fast-forward to the first alert.** The patient opens. Show the solid *Observed now*
   tile (e.g. 81 mg/dL) against the dashed *Predicted* tile (e.g. 15 %, DEVELOPMENT): "an alert
   is a forecast, not a low".
5. **(2:20) Why is HypoSense showing this?** The sentence, then the associated information
   (glucose level, history, estimated medicine activity), described as "associations, not
   causes". Open *Technical detail* for the probability and thresholds.
6. **(3:00) Medicines.** Bars are recorded doses; curves are estimated activity, not a blood
   level. This is the project's differentiator: the scientific question is whether this
   information helps.
7. **(3:30) Advance 75 minutes → history.** Show whatever really happened. In the default replay
   the first alert (2012, 14:48) was **not** followed by a CGM low, so it was a false alert, and
   the system shows it plainly.
8. **(4:00) Evidence.** "M2 87.5 %, M3 91.1 % at one false alert per patient-day on development
   data; the difference's interval includes zero. The sealed evaluation has not been run, so
   there is no claim yet."
9. **(4:30) Add patient (optional).** Upload `docs/screenshots/intake/SYNTHETIC_recording.csv`.
   Show that the questions explain why they are asked, then create the twin.
