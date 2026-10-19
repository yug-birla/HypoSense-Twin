# Demo guide (6–8 minutes)

**Setup** (once):
1. `uv sync`.
2. `cd frontend && npm ci && npm run build && cd ..`.
3. Fetch the data ([README → Quick start](../../README.md#quick-start)).
4. Start the server: `uv run hyposense serve --port 8765`.
5. Open http://127.0.0.1:8765.

The demo uses **development data** (tuning partition T). Everything shown is real replay output;
nothing is staged. Say "development" whenever a number appears.

| Time | Screen | What to do | What to say |
|---|---|---|---|
| 0:00 | Welcome | Read the first paragraph aloud | "HypoSense estimates whether a CGM-detected low will begin in the next hour, so staff can check earlier. Research prototype; never suggests doses." |
| 0:30 | Welcome, *the four worlds* and *Observe · Forecast · Review* | Point to the four worlds, then the status meanings | "LOW NOW is observed. ALERT, WATCH and NO ALERT are predictions. No forecast is never shown as low risk." |
| 1:00 | Guided demo | *Start the guided demo* → *Start the replay* | "Eight real recorded patients, in catalogue order, not chosen for good results." |
| 1:30 | Ward board | *Advance 2 hours*; hover a status | "The board orders patients by status, then risk. The rules run on the server." |
| 2:00 | Patient (first alert) | *Fast-forward to the first alert* | "The first alert in time order: patient 2012 at 14:48, estimated risk 15 %. The solid tile is the observed glucose (81 mg/dL); the dashed tile is the prediction. An alert is a forecast, not a low." |
| 2:45 | *Why is HypoSense showing this?* | Read the sentence; open *Technical detail* | "The information most associated with the estimate. These are associations, not causes. The thresholds are frozen in the model." |
| 3:30 | *Medicines* | Point to bars vs curves | "Bars are recorded doses. Curves are the estimated activity, not a measured level. This is our differentiator, and the scientific question is whether it helps." |
| 4:15 | History | *Advance 75 minutes* | "The 14:48 alert was **not** followed by a CGM low: a false alert. We show it plainly; the evaluation measures exactly this trade-off between lows warned and false alerts." |
| 5:00 | Ask panel | *After the last alert?* · *Are readings current?* | "Fixed questions, answered from recorded data. No chatbot and no advice." |
| 5:30 | Add patient | Upload `docs/screenshots/intake/SYNTHETIC_recording.csv`; answer the questions; *Create patient twin*; add a reading | "New data go through the same parser and twin. It asks only what it must, and guesses nothing. These sessions are never training data." |
| 6:45 | Evidence | *Understand the evidence* | "Development: M2 87.5 %, M3 91.1 % at one false alert per day; the difference's interval includes zero. The sealed evaluation has not been run: no claim yet." |
| 7:30 | Close | — | "Limitations: one centre, CGM-detected labels, kernels pending pharmacist review. Next: freeze, then the single confirmatory run." |

If something differs (for example, a different first alert after you change the recordings), say
what you see. The demo never edits events.
