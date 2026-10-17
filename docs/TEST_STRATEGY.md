# Test Strategy

Principles (CLAUDE.md §22–23):
- Critical research logic is **test-first**: labels, metrics, kernels, policy, partitioning and
  feature timing.
- **Never claim a test passed without running it.** Every PROGRESS entry lists the exact
  command and its outcome.
- Fixtures built from invented numbers are named `synthetic_*` and their docstrings say
  **SYNTHETIC**. They are never used in a reported metric.
- Tests that need the real dataset are marked `@pytest.mark.requires_data` and skip cleanly
  when `data/raw` is absent. No real patient values are committed; golden real-data
  expectations are **aggregate numbers** only.
- No test may read sealed-partition (E) records before freeze, except aggregate audit tests
  allowed by P-C5.

Tooling: pytest, Hypothesis (property-based), ruff, mypy (strict), Playwright (E2E),
Vitest/Testing Library (frontend components).

Commands:
```bash
uv run pytest                       # everything that can run
uv run pytest -m "not slow"         # fast loop
uv run pytest tests/leakage         # leakage suite (must be green before any model run)
uv run ruff check src tests scripts && uv run mypy src
```

---

## 1. Unit tests (`tests/unit/`)

| Area | Tests | Stage |
|---|---|---|
| Adapter | each column variant maps; unknown column raises; units (`0.5 g` → 500 mg); +08:00 parsing; duplicate removal; non-monotone quarantine; quality flags (gap >20, ≤40, rate >4, warm-up); flags never delete rows | S1–S2 |
| Labels | ≥20 hand-labelled fixtures: onset at the 1st of 2 <70; spacing ≤20 vs 21 min; gap >30 ends the episode; end at the 1st of 2 ≥70; single ≥70 inside an episode does not end it; record end; L2 nested in L1; single-reading rule (SA1); eligibility: CGM ≥70, in-episode, refractory 60 min, 7/8 readings in (t−120, t], follow-up ≥60 or onset; unsorted input raises `ValueError` | S2 |
| Medication parsing | multi-component text; dictionary lookup incl. typos ("glarigine"); premix proportions from product name; gliclazide formulation rule (30/60/120 → MR, 40/80/160 → IR, else flag); implausible units flagged; unparseable → `unknown`, raw text kept, never raises; CSII basal persists until the next entry; i.v. → flag only | S3 |
| Kernels | zero before administration; zero at τ=0; peak at t_peak (insulin) / t_max (Bateman); decays to 0 at t_dur; ∫ = 1 ± 0.01 (insulin); premix = weighted sum; flat basal normalised; parameter validation (t_peak < t_dur/2; Bateman solvable); SA6 scaling preserves the integral | S3 |
| Exposure | overlapping and repeated doses add linearly; missing class in 36 h → NaN + timing-unknown (not 0); logged-not-prescribed → used + conflict flag; projections use only past doses; boundary timestamps | S3 |
| State | each reading advances ts and appends to the ledger; causal episode tracker matches label builder events once confirmed; immutable snapshots; SYSTEM_ERROR tag on internal failure | S4 |
| Features | each App. D feature on hand-computed traces; level gating (M1 ⊂ M2 ⊂ M3/M3r); feature-spec order; static allow-list excludes "Hypoglycemia (yes/no)" and IDs; `_missing` indicators | S4 |
| Models | M0 projection on linear traces; LightGBM wrapper determinism; artefact hash mismatch → error; feature-spec mismatch → error | S5–S6 |
| Calibration | isotonic monotone; JSON round-trip equality; ECE / slope / intercept on fixtures | S6 |
| Policy | every Table 14.1 row; p = τA boundary; WATCH → ALERT; cooldown (no two notifications in 60 min, ALERT persists); persistent risk; current low; insufficient data; missing medication badge; recovery; repeated alerts; malformed/NaN p → SYSTEM ERROR; tags never downgrade ALERT; never the word "safe" | S7 |
| Metrics | hit window [onset−60, onset−15] inclusive edges; lead time; FA counting; follow-up exclusion (P-C3); FA/day denominator; first-crossing interpolation incl. non-monotone FA fixture (P-C2); M0 θ sweep direction; partial area; bootstrap determinism (seed 2027) and pairing | S5 |

## 2. Integration tests (`tests/integration/`)

| Path | Test |
|---|---|
| data → state | a synthetic recording file → adapter → state sequence matches the expected flags and exposure |
| state → features | the same events processed by replay vs offline snapshot generation → identical matrices (ADR-004) |
| features → model | feature spec round-trip; prediction for a known artefact is stable to 1e-12 |
| model → calibration | calibrator fitted only on inner-OOF rows of training patients (`test_nested_fitting_isolation`) |
| calibration → policy | τ chosen on development predictions; policy states over a replay match the expected counts |
| backend → frontend | OpenAPI schema snapshot; generated TS types compile; API contract tests with the FastAPI TestClient |

## 3. Leakage tests (`tests/leakage/`) — must be green before any model run

| Test | Pass condition |
|---|---|
| `test_import_boundaries` | **exists** — live path never imports labels/evaluation; policy never imports models |
| `test_truncation_equality` | for random t (Hypothesis) at every level: snapshot(full record) == snapshot(record truncated at t), bit-for-bit; includes t at dose times, episode boundaries and gaps |
| `test_exposure_causal` | adding doses after t leaves exposure at t unchanged |
| `test_features_ignore_ledger` | mutating the ledger/outcomes leaves snapshots unchanged |
| `test_group_by_patient` | no patient_key in both train and test of any fold; T ∩ E = ∅; recordings of one patient stay together |
| `test_freeze_guard` | confirmatory command refuses without a matching freeze record; tuning commands refuse E |
| `test_fold_fitted_references` | percentiles/ranges used for LOW CONFIDENCE come from training patients only |

## 4. Reproducibility tests (`tests/reproducibility/`)

- Audit determinism: two runs → identical report hash.
- Training determinism: same data, config and seed → identical model file hash (one thread,
  deterministic mode).
- Replay determinism: two replays → identical decision-log hash (G7).
- Bootstrap determinism: same seed → identical interval.
- Provenance completeness: every run manifest has all CLAUDE.md §13 fields.

## 5. Regression tests (`tests/regression/`)

- **exists** `test_protocol_constants`: Class C constants pinned (ADR-014).
- Episode counts on the official copy (aggregate golden values, set in S2).
- Medication parse rates and dictionary coverage (set in S3).
- Known fixture outputs for kernels and policy.

## 6. End-to-end tests (`tests/e2e/`, Playwright)

- Start `hyposense demo` (offline) → Ward Board loads → replay a T patient → all six states
  observed → open Patient Review → acknowledge an ALERT with a reason code → entry in
  `logs/acks.jsonl`.
- Stale-stream simulation: kill the stream → the UI shows connection lost and no current
  state.
- Prohibited-wording scan over the built UI strings ("safe", dose/insulin advice).

## 7. Continuous integration

Once a remote exists, a GitHub Actions workflow runs on every push: `uv sync --frozen`, ruff,
mypy, pytest (no data, so `requires_data` tests skip), the frontend lint and build, and the
E2E tests on the main branch.

## 8. Current status (2026-10-18)

| Category | Implemented | Passing |
|---|---|---|
| Unit | 0 | — |
| Integration | 0 | — |
| Leakage | import boundaries (10 parametrised cases) | 10/10 |
| Reproducibility | 0 | — |
| Regression | protocol constants (6) | 6/6 |
| E2E | 0 | — |
