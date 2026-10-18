# Kernel Parameter Sources (S3, verified 2026-10-18)

Every value in `configs/pharma.yaml` traces to this file. Values were read directly from the
retrieved document text, not from search snippets:
- US labels came from FDA SPL text via the openFDA API (`api.fda.gov/drug/label.json?search=set_id:<id>`).
  The equivalent human-readable page is `dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=<id>`.
- EU SmPCs came from EMA EPAR product-information PDFs. Their revision dates were not captured.
- Other national SmPCs are listed with their URLs.

**These are population-level label statements used to set modelling kernels. They are not clinical
validation, and the kernels are not patient-specific.**

## Insulins (time-action; subcutaneous)

| Product | Statement (quoted) | Source | Type |
|---|---|---|---|
| Insulin aspart (NovoLog) | "maximum glucose-lowering effect … between 1 and 3 hours"; "duration of action … 3 to 5 hours"; tmax 40–50 min; t½ 81 min | FDA SPL set 3a1e73a2-3009-40d0-876c-b4cb2be56fc5, v34, eff. 2023-02-28 | REGULATORY_LABEL |
| Insulin aspart (NovoRapid) | "onset … within 10 to 20 minutes … maximum effect … between 1 and 3 hours … duration of action is 3 to 5 hours"; T2D tmax 60 min | EMA SmPC novorapid | REGULATORY_LABEL |
| Insulin glulisine (Apidra) | tmax "60 minutes (range 40 to 120 minutes)"; t½ 42 min; EU onset "within 10-20 minutes" | FDA SPL set e7af6a7a-8046-4fb4-9979-4ec4230b23aa, v28, eff. 2025-11-25; EMA SmPC apidra | REGULATORY_LABEL |
| Regular human (Humulin R U-100) | effect begins ~30 min (10–75); "maximal at approximately 3 hours (range: 20 minutes to 7 hours) and terminates after approximately 8 hours (range: 3 to 14 hours)" | FDA SPL set b519bd83-038c-4ec5-a231-a51ec5cc291f, v35, eff. 2026-06-16 | REGULATORY_LABEL |
| Regular human (Novolin R) | "begins approximately 30 minutes … maximal between 1.5 and 3.5 hours … terminates approximately 8 hours post-dose" | FDA SPL set aee7f1f3-612c-4027-8ce9-4fd1f41eed71, v19, eff. 2022-11-23 | REGULATORY_LABEL |
| Soluble human (Actrapid) | onset ½ h; maximum 1.5–3.5 h; duration ~7–8 h | EMA SmPC actrapid | REGULATORY_LABEL |
| NPH (Humulin N) | "median maximum effect occurred at 6.5 hours (range: 2.8 to 13 hours)"; tmax ~4 h; t½ ~4.4 h | FDA SPL set f6edd793-440b-40c2-96b5-c16133b7a921, v50, eff. 2025-12-19 | REGULATORY_LABEL |
| NPH (Novolin N) | "duration of action of up to 24 hours"; onset 1–2 h | FDA SPL set 69dffec8-6ea9-441b-b795-042dcc26843d, v3, eff. 2026-07-08 | REGULATORY_LABEL |
| NPH (Insulatard) | onset within 1½ h; maximum 4–12 h; duration "approximately 24 hours" | EMA SmPC insulatard | REGULATORY_LABEL |
| Biphasic aspart 30 (NovoLog Mix 70/30) | "70% insulin aspart protamine crystals and 30% soluble insulin aspart"; onset 10–20 min; peak 2.7 ± 0.9 h; "duration … as long as 24 hours" | FDA SPL set 19888a44-b330-462a-864d-338c5893dd63 (repackager copy of the Novo text), v32, eff. 2026-01-29 | REGULATORY_LABEL |
| Biphasic aspart 30 (NovoMix 30) | 30 % soluble / 70 % protamine-crystallised; maximum 1–4 h; duration up to 24 h | EMA SmPC novomix | REGULATORY_LABEL |
| Human premix 70/30 (Humulin 70/30) | 70 % NPH / 30 % regular; effect begins ~50 min; maximal ~3.5 h (1.5–6.5); duration ~23 h (18–24) | FDA SPL set e245e0c5-b2d6-418b-baa4-1c3324292885, v50, eff. 2026-06-17 | REGULATORY_LABEL |
| Human premix 70/30 (Novolin 70/30 = "30R") | 70 % isophane / 30 % human; "up to 24 hours duration of action" | FDA SPL set 508a2763-3cb7-4be5-9e53-544e84cd9b1f, v18, eff. 2022-11-23 | REGULATORY_LABEL |
| Mixtard 30 | 30 % soluble / 70 % isophane; maximum 2–8 h; up to 24 h | EMA SmPC mixtard | REGULATORY_LABEL |
| Glargine (Lantus) | "no pronounced peak"; duration "24 hours (range: 10.8 to >24 hours)" (observation ended at 24 h) | FDA SPL set d5e07a0c-7e14-4756-9152-9fea485d654a, v35, eff. 2025-06-02 | REGULATORY_LABEL |
| Detemir (Levemir) | "up to a 24-hour duration of action"; end of effect 7.6 to >24 h; dose-dependent | FDA SPL set 82192527-99aa-4b53-8ce9-9173668d309c (repackager), v24, eff. 2024-10-09; EMA SmPC levemir | REGULATORY_LABEL |
| Degludec (Tresiba) | t½ ~25 h; "lasted at least 42 hours"; "median onset of appearance was around one hour" | FDA SPL set 456c5e87-3dfd-46fa-8ac0-c6128d4c97c6, v14, eff. 2022-07-01; EMA SmPC tresiba | REGULATORY_LABEL |
| Gansulin 40R | "prémix 40/60" (which fraction is 40 % is **not stated**) | Adocia press release, 2018-06-01, echanges.dila.gouv.fr/OPENDATA/AMF/BWR/2018/06/FCBWR110088_20180601.pdf | OTHER |
| Gensulin M30 (stand-in for SciLin M30) | "30% insuliny rozpuszczalnej i 70% insuliny izofanowej" | Polish ChPL rejestrymedyczne.ezdrowie.gov.pl/api/rpl/medicinal-products/9950/characteristic | REGULATORY_LABEL (for Gensulin, not SciLin) |

## Oral secretagogues

| Product | tmax | t½ | Max daily dose | Source | Type |
|---|---|---|---|---|---|
| Gliclazide MR (Diamicron 30 mg MR) | rises for 6 h, then a plateau 6–12 h | "between 12 and 20 hours" | "120 mg" | UK eMC SmPC 1321 (rev 02/2020); Dutch CBG SmPC h102828 identical | REGULATORY_LABEL |
| Gliclazide IR (Diamicron 80 mg) | "between 2 and 6 hours" | "between 10 and 12 hours" | 320 mg (single dose ≤ 160 mg) | UK eMC SmPC 1150 (rev 02/2020) | REGULATORY_LABEL |
| Glimepiride (Amaryl) | "approx. 2.5 hours" (US: 2–3 h) | "about 5 to 8 hours" (US: 5.3 ± 4.1 h) | US 8 mg; EU (2010) 6 mg | FDA SPL set 222b630b-7e09-43b4-9894-3d87f10add91, v19, eff. 2023-06-21; HPRA SPC PPA1500-063-001 (2010) | REGULATORY_LABEL |
| Gliquidone (Glurenorm) | Cmax "after 2–3 hours"; effect begins at 60–90 min, maximum at 2–3 h, lasts 8–10 h | **terminal t½ not stated** ("halved within 1.2 hours") | 120 mg | Polish ChPL register 2726 | REGULATORY_LABEL |
| Repaglinide (Prandin / NovoNorm) | "within 1 hour" | "approximately 1 hour" | 16 mg (single ≤ 4 mg) | FDA SPL set 4c1c212f-71a5-4dd3-81b2-cd9e2148774c, v11, eff. 2019-02-06; EMA SmPC novonorm | REGULATORY_LABEL |

## Community documentation

- OpenAPS "Understanding insulin on board (IOB) calculations". The rapid-acting exponential curve
  uses "peak activity set at 75 minutes and dia set at 300 minutes (5 hours)", and "dia must be
  greater than 300 minutes". URL:
  openaps.readthedocs.io/en/latest/docs/While%20You%20Wait%20For%20Gear/understanding-insulin-on-board-calculations.html.
  The oref0 source code was not checked. Type: OTHER.

## Not verified (recorded as ASSUMPTION in pharma.yaml)

- **SciLin M30** composition. There is no official source; Gensulin M30 is assumed to be the same
  product.
- **Gansulin 40R**: that the 40 % fraction is the regular insulin. No time-action data for either
  product.
- **Gliquidone** terminal half-life. Secondary sites cite about 8 h; no primary paper was found.
- **Basal-analogue lag** of 1 h for glargine and detemir. The labels give no numeric onset.
- **Protamine-aspart modelled with the NPH kernel.**

## Conflicts noted

- Glimepiride maximum dose: 8 mg (US) vs 6 mg (2010 EU SPC). The Chinese label was not checked.
- Gliclazide: MR and IR differ in both tmax and t½, hence separate kernels.
- Regular insulin: duration lengthens at high doses in obesity (Humulin R, about 18 h).
- NPH: peak effect 6.5 h (Humulin N) vs 4–12 h (Insulatard); duration about 24 h in all sources.
- OpenAPS uses a 5 h minimum DIA for rapid analogues; the aspart label gives 3–5 h.
