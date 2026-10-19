# New patient / new data (intake)

Status: **DEVELOPMENT feature of a research prototype.** New data run through the same
digital-twin pipeline as the research replay. They are never research data, never training data
and never evidence.

## What it does

`Add patient` (Ward / Patient / Evidence navigation) offers two ways in:

1. **Upload a recording** (CSV in UTF-8, or XLSX with one worksheet; header row; ≤ 5 MB,
   ≤ 100,000 rows, ≤ 40 columns).
2. **New patient without a file.** Observations are then added one at a time.

The server validates the data and asks only the questions the data require. When every required
question is answered, **Create patient twin** builds a live twin. Patient review then shows the
twin, with a NEW DATA SESSION banner and an **Add observation** panel (CGM reading, capillary
glucose, meal, medication given).

## Pipeline (no second ML pipeline)

```
file / entry → intake.upload (safe read) → intake.draft (mapping, questions, unit/clock
normalisation) → data.loader.parse_recording_frame  (the SAME parser as the dataset loader)
→ state.stream.recording_stream → TwinRunner (Patient State Engine → causal features → model →
calibration → policy) → API → frontend
```

An appended observation adds one row to the session's canonical frame. The whole frame is
re-parsed by the same modules. The new event stream must extend the old one exactly, and only
the new events are fed to the twin.

**Verified by tests** (`tests/integration/test_intake.py`):
- **Parity:** a real tuning-partition recording uploaded as CSV gives events, decisions and
  probabilities identical to the historical adapter.
- **Causality:** a twin built reading by reading equals a twin built from the whole file.

## Columns

Recognised headers (the dataset format) are mapped automatically: `Date`, `CGM (mg / dl)`,
`CBG (mg / dl)`, `Dietary intake`, `Insulin dose - s.c.`, `Non-insulin hypoglycemic agents`,
`Insulin dose - i.v.`, `CSII - bolus/basal insulin …`, `Blood Ketone (mmol / L)`.

Any other header becomes a question: "What does the column … contain?". A suggestion may be
shown from the header words, but it is never applied without the user choosing it. A date/time
column and a CGM column are required.

## Questions (deterministic, triggered by findings)

| Question | Asked when | Required |
|---|---|---|
| Column meaning | header not recognised | yes |
| Glucose unit (mg/dL or mmol/L) | glucose column has data and its header states no unit | yes |
| Clock (patient local or UTC) | timestamps carry no time zone | yes |
| Patient UTC offset | timestamps are UTC | yes |
| Pump insulin type | pump columns contain data (only regular human insulin is modelled) | yes |
| Medication entry clarification | the canonical parser reports UNPARSEABLE, AMBIGUOUS, DOSE_UNKNOWN, FORMULATION_UNKNOWN or UNIT_MISSING | no |

**Nothing is guessed:**
- Units are never inferred from magnitudes.
- If the median CGM after the stated unit lies outside 40–400 mg/dL, the data are refused.
- Mixed time zones are refused.
- A medication replacement must be accepted by the canonical parser. Otherwise it is refused
  and the entry can be kept as recorded, with the existing unknown semantics.

Context (age, sex, BMI, weight, diabetes duration, HbA1c, eGFR, C-peptide, prescribed agents) is
**optional**. These are exactly the fields the model reads. Missing values stay missing (never
zero), and implausible values become missing with a warning.

## Time

The model's time-of-day features use one reference clock: `time.assumed_utc_offset`, +08:00,
the dataset's clock. New data are stored as the **patient's local wall-clock time** encoded at
that reference offset, so the features see the patient's own local hour. UTC exports are
converted to local time with the stated offset. Every displayed time is the patient's local
clock.

Limitation: a daylight-saving jump inside a recording appears as a 1-hour gap or as
out-of-order rows, and is flagged.

## Forecasts on new data

- A forecast appears only when the canonical policy gates allow it: sufficient recent CGM,
  plausible rate of change, no sensor-fault condition. Otherwise the state is INSUFFICIENT DATA
  (or LOW NOW for an observed low).
- The forecast uses the DEVELOPMENT model. It was not trained or evaluated on the new data, so
  **no accuracy claim applies** to them.
- Pending forecasts stay "Pending (window open)" until 60 minutes of later CGM exist. Nothing is
  filled in.
- No dose, medication change or treatment is ever suggested.

## Ask about this patient

Fixed questions are answered only from the twin's recorded state (`GET
/api/patients/{key}/ask?intent=`):
- why this state;
- what is missing;
- what changed;
- medication entries;
- data-quality notes;
- supporting evidence.

Free text is not accepted.

## Privacy and retention

- Identifiers are pseudonymous (`N0001`) and assigned by the server. The optional display label
  is limited to 24 letters, digits, spaces, `-` and `_`. Do not enter names or record numbers.
- The uploaded file is held **in server memory only** and never written to disk.
- Each session writes a decision log (decisions and acknowledgements; no file content) under
  `logs/replay/intake/`, which is git-ignored.
- **Remove session** on Patient review deletes the session from memory and deletes its log.
  Stopping the server discards all sessions.
- No external network call is made; everything runs offline on the local machine.
- New data are never merged into the research partitions (T / E). Patient keys use the
  `intake:` prefix, so they cannot collide with a dataset patient. Nothing is retrained,
  recalibrated or re-thresholded.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/intake/upload` | `{file_name, content_base64, label?}` → draft |
| POST | `/api/intake/new` | `{label?}` → empty draft |
| GET | `/api/intake/drafts/{id}` | draft |
| POST | `/api/intake/drafts/{id}/answers` | `{answers: {question_id: value}, context: {field: value}}` |
| POST | `/api/intake/drafts/{id}/commit` | create the twin (only when READY) |
| DELETE | `/api/intake/drafts/{id}` | discard |
| GET | `/api/sessions` | new-data sessions |
| POST | `/api/sessions/{key}/observations` | `{kind: cgm\|cbg\|meal\|medication, local_time, value?, unit?, text?, column?}` |
| DELETE | `/api/sessions/{key}` | delete session and its log |
| GET | `/api/patients/{key}/ask?intent=` | fixed questions |
