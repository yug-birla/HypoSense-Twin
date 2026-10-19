# Frontend (S8): architecture and design system

Status: implemented 2026-10-19 (DEC-2026-10-19-K). Stack per ADR-007/008. Audience: engineers
and reviewers of the demo.

## 1. Run it

```
cd frontend && npm ci && npm run build      # static export -> frontend/out/
uv run hyposense serve                       # API + UI on http://127.0.0.1:8000 (offline)
```

P-C10 is final (DEC-2026-10-19-M): a rejected non-CGM input keeps the clinical state and shows an
INPUT REJECTED badge. There is no runtime switch.

Regenerate the contract types after a backend schema change:
`uv run python scripts/export_openapi.py && cd frontend && npm run gen:types`.

## 2. Architecture

| Layer | Where | Rule |
|---|---|---|
| Contract | `frontend/openapi.json` → `src/lib/openapi.d.ts` (generated) | No hand-written API types |
| REST client | `src/lib/api.ts` | Typed; errors become `ApiError` (no stack traces) |
| Snapshots | `src/lib/queries.ts` (TanStack Query) | Server state only; no global store |
| Stream | `src/lib/stream.tsx` | SSE v1; messages only trigger refetches (coalesced over 400 ms); unknown versions ignored; reconnect with backoff 1/2/5/10 s, then "offline"; full resync on reconnect |
| Presentation maps | `src/lib/states.ts`, `src/lib/format.ts` | Labels, icons, number/time formatting only |
| Pages | `src/app/{page,patient/page,evidence/page}.tsx` | Ward board, Patient review (`?key=`), Evidence |
| Components | `src/components/{shell,ward,patient,evidence,replay,ui}` | Tokens only; no per-component palettes |

**No scientific logic in the browser.** Risk, policy state, staleness (`policy.current`),
thresholds, trend category, the one-line reason, the deterministic summary, factor groups,
exposure, ledger outcomes and every evidence number come from the backend. The browser formats
and scales them. A state string the UI does not know renders as SYSTEM ERROR, never as a
reassuring state.

Backend additions for the UI (S8, all derived from canonical modules):

- Bed: `cgm_mgdl`, `trend` (canonical `cgm_slope30` + display category), `data_age_s`,
  `summary`, `reason`, `badges` (critical), `info_tags` (informational).
- PatientView: 24-h `timeline` (per reading: CGM, state, p, notify, causal `in_episode`, sensor
  fault, exposure), `ledger_entries` (forecast → LOW_FOLLOWED / NO_LOW / PENDING /
  OUTCOME_UNKNOWN, from the twin's OutcomeLedger), `input_rejected`, `exposure_units`.
- `/api/evidence`: typed view of S6 results, aggregate operating curves
  (`hyposense dev evidence`; reproduces S6 sens@1FA exactly), gates, S7 engineering run, leakage
  safeguards quoted from the S4 audit, model provenance.
- Static export mount (`ExportFiles`): maps Next's `__next.<seg>.__PAGE__.txt` requests onto the
  exported files; anything else is served or refused by Starlette unchanged.

## 3. Design system

Principles: clinical first · calm · glanceable · progressive disclosure · honest labels · state is
never colour alone (text + icon + colour).

| Token group | Values (`src/app/globals.css`) |
|---|---|
| Type | Inter Variable; display 22, title 17, section/body 13, small 12, label 11 caps, metric 28; tabular numbers everywhere a number is compared; JetBrains Mono for hashes |
| Radius | 3 / 4 / 6 / 8 px (restrained) |
| Surfaces | canvas `#f5f6f8`, surface white, sunken `#f0f2f5`, 1 px lines |
| Text | ink / ink-2 / ink-3 / ink-4; ink-3 and ink-4 meet WCAG AA on every surface |
| Accent | teal `#0e6e6a`: navigation, links, focus. Never a state |
| States | LOW NOW solid red; ALERT orange tint; WATCH amber tint; SYSTEM ERROR violet tint; INSUFFICIENT dashed grey; NO ALERT neutral |
| Badges | Tier 1 = state pill; tier 2 = critical quality (sensor fault, input rejected, halted); tier 3 = quiet grey info tags (timing unknown, recent input rejected). LOW_CONFIDENCE was removed (P-B12: ~57 % firing on held-out forecasts, no reliability separation; DEC-2026-10-19-M) |
| Charts | ECharts (SVG renderer, tree-shaken): CGM ink line, 70–180 range band, 70/54 reference lines, risk on its own panel with τ lines (a forecast never shares the glucose axis), doses/meals on an event lane, episodes and sensor-fault regions as shaded areas, gaps > 20 min never joined; exposure on a separate "ESTIMATED" chart |
| Motion | one 1.2 s background fade on a state change; disabled under `prefers-reduced-motion` |

## 4. Screens

- **Ward board**: attention count, beds per state, quality issues, unacknowledged notifications;
  dense table in server rank order (state, then risk): patient, state, CGM, trend, risk, reason,
  quality, freshness (amber after 20 min), notifications. Under 1280 px the sidebar collapses to
  icons and quality badges move under the reason.
- **Patient review**: header (state, deterministic summary, observed CGM + trend, risk or "no
  forecast in this state", freshness); glucose/model timeline with layer toggles; medication
  context (estimated exposure vs recorded doses); why (policy texts + top-3 factor groups,
  "associated, not causes"); notifications with acknowledgement dialog (4 reason codes, explicit
  confirm, no free text); data quality; forecast → outcome ledger.
- **Evidence**: DEVELOPMENT banner (E sealed, not clinically validated); task; limitations; model
  ladder with CIs; operating curves; paired Δ with CIs; calibration; gates (G3b TRIGGERED shown);
  leakage safeguards; reproducibility/provenance.

### Confirmatory panel (S10, built before freeze)
`components/evidence/Confirmatory.tsx` reads `GET /api/confirmatory`.
- **PENDING:** shown while E is sealed. No numbers appear.
- **CONFIRMATORY:** shown for the single verified official run, with the primary Δ and CI, the
  H1 verdict, §6 selection, Table 20.4 rows, the ladder, the deployed operating point and all
  S/SA/R analyses.
- **INTEGRITY FAILURE:** shown if verification fails.
- A rehearsal is never served. Tests: `src/test/confirmatory.test.tsx`.

### Add patient and new-data sessions (DEC-2026-10-19-P)
- **`app/intake/page.tsx` + `components/intake/Intake.tsx`:**
  - pseudonymous label;
  - upload or empty patient;
  - server questions (required first; suggestions marked, never preselected);
  - validation findings by severity;
  - file preview with mapping;
  - optional context;
  - "Create patient twin", enabled only when the draft is READY.
- **`components/intake/SessionPanels.tsx`:** the NEW DATA SESSION banner (DEVELOPMENT, not
  clinically validated, not research data), Add observation (CGM, capillary glucose, meal,
  medication) and Remove session.
- **`components/patient/AskPanel.tsx`:** fixed questions answered by the backend.
- **Ward:** new-data beds carry a NEW DATA tag and are listed with replay beds, but are never
  counted in evidence.
- **Tests:** `src/test/intake.test.tsx`; browser E2E
  `tests/e2e/test_ui_e2e.py::test_new_patient_upload_questions_twin_and_append`.
- **Screenshots:** `docs/screenshots/intake/` (SYNTHETIC only, safe to commit).

## 5. Design research (principles extracted; nothing copied)

| Reference | Pattern | Adopt? | HypoSense mapping |
|---|---|---|---|
| Dexcom Clarity | One-page overview → drill-down; AGP target band | Yes | Ward overview → patient drill-down; 70–180 band, 70/54 lines |
| GE HealthCare Command Center | Tiles answering "what is happening now"; flag stale data | Partly | Attention summary + freshness column; no wall of tiles (one ward fits a table) |
| Biofourmis | Notification triage + clinician review queue | Yes | Unacknowledged-notification counts; acknowledgement on the patient page |
| Linear | Not every element earns equal weight; low noise at high density | Yes | Three-tier badge hierarchy; quiet NO ALERT rows |
| Vercel dashboard | Collapsible sidebar, consistent navigation | Yes | Sidebar collapses to icons < 1280 px |

Sources: dexcom.com Clarity reports FAQ; businesswire.com (GE Hospital Pulse Tile, 2024);
healthcareitnews.com (Tampa General command center); biofourmis.com/platform;
linear.app/blog (design refresh); vercel.com/changelog (dashboard navigation, 2026).

## 6. Accessibility and performance (measured)

`scripts/ui_audit.py` (axe-core 4.13, WCAG 2.0/2.1 A+AA, Edge, 1440×900):
0 violations on all three pages; first Tab reaches "Skip to content"; pages ready in
0.25–0.55 s; ~0.7–0.8 MB JS per page (1.4 MB total static JS). Runs:
`T-AGG-s8-ui-audit-20261018T184552Z` / `T184600Z` (identical).

## 7. Tests

- Vitest (`frontend/src/test/ui.test.tsx`, 25): every state has text + icon; unknown state →
  SYSTEM ERROR; ward rows (LOW NOW + sensor fault, ALERT + unacknowledged, stale, no forecast,
  SYSTEM ERROR + input rejected); header; acknowledgement (4 reasons, disabled until chosen, no
  textbox); evidence banner; stream version/invalidation; CGM gaps; prohibited wording scan.
- Python: `tests/unit/test_s8_presentation.py`, S8 integration cases, browser E2E
  `tests/e2e/test_ui_e2e.py` (replay → API → dashboard → acknowledge → `acks.jsonl`).
- Visual QA: `scripts/ui_snapshots.py`, `scripts/ui_walkthrough.py` → `artifacts/screenshots/`
  (git-ignored: they show T patient traces).

## 8. Known limitations

- Mobile widths are not designed for (desktop/laptop/tablet ≥ 1024 px only).
- The ledger table shows at most 25 rows (backend sends ≤ 50).
- Data times are shown on the record's local clock (UTC+8), not the viewer's clock.
- P-C10 display semantics PENDING (switch exists; default is the current specification).
