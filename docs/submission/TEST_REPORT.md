# Final test and verification report

Date: 2026-10-20. Machine: Windows 11, Python 3.11.9, Node 24, Microsoft Edge (Playwright).
Status: **DEVELOPMENT / pre-freeze.** No confirmatory (sealed-partition) result exists.

## Automated tests

| Suite | Command | Result |
|---|---|---|
| Python: unit, leakage, regression, integration, reproducibility, E2E | `uv run pytest -q` | **578 passed** |
| Frontend unit / component (Vitest) | `cd frontend && npx vitest run` | **42 passed** |
| Browser E2E (Edge): replay → acknowledgement; upload → questions → twin → append; guided demo | `uv run pytest -q tests/e2e` | **3 passed** |
| Lint | `uv run ruff check src tests scripts` | clean |
| Types | `uv run mypy src` (strict) · `npx tsc --noEmit` | clean · clean |
| Accessibility (axe-core 4.13, WCAG 2 A/AA): 6 pages | `uv run python scripts/ui_audit.py` | **0 violations** (`T-AGG-s8-ui-audit-20261019T182505Z`) |
| npm dependency audit | `cd frontend && npm audit` | 0 vulnerabilities (last run 2026-10-19) |

## Scientific integrity checks (from committed run records)

| Check | Result |
|---|---|
| Causal features: truncation equality | 31,292 eligible T times, 0 mismatches |
| Offline = live features | 133,856 comparisons, 0 mismatches |
| Freeze candidate rebuilt twice per code change | identical results hash `c0cbe721…` on every pair (latest on `38d7aca`) |
| Confirmatory runner rehearsal on T (`T-AGG-rehearsal-20261019T172643Z`) | equals S6 exactly; held-out replay parity 0 / 31,416 |
| Upload adapter vs historical adapter (real T recording as CSV) | identical events, decisions and probabilities |
| `hyposense freeze` | passes every technical check; **aborts on the human gates** (pharmacist review; P-C11) |

## Performance (measured 2026-10-20, local CPU, one server)

| Measure | Value |
|---|---|
| Server start (artefact verification + T catalogue) | 10.9 s |
| Replay: 24 h of 8 recorded patients | 5.4 s (776 decisions, ~144 decisions/s) |
| `GET /api/ward` p50 / p95 | 18.5 / 38.1 ms |
| `GET /api/patients/{key}` p50 / p95 | 18.8 / 45.4 ms |
| Upload + validation of a 14-day CSV | 96 ms |
| Re-validation after answers | 475 ms |
| Building a 14-day twin from an upload | 8.8 s (canonical exposure and feature engine, ~6.5 ms per reading; the UI shows "Building the twin…") |
| Appending one observation | 269 ms p50 |
| Server memory (working set) | 204 MB |

## Visual verification

Edge at 1440, 1280 and 1024 px:
- pages checked: Welcome, Ward board, Replay studio, Patient review (all tabs), Evidence garden,
  Add patient, Guided demo;
- 0 console errors.

Screenshots:
- `artifacts/screenshots/redesign/`: shows tuning-partition traces, so it is git-ignored.
- `docs/screenshots/`: SYNTHETIC or aggregate only.
