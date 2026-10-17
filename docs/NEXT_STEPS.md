# Next Steps

Ordered execution queue. Updated: 2026-10-18 (end of S0 planning run).
Each item lists: objective · dependency · acceptance criteria · difficulty · parallel? ·
approval needed?

## P0 — Blocking

1. **Competition registration (HUMAN, URGENT)**
   - Objective: confirm the team is registered. The reported deadline is **18 Oct 2026,
     19:00 IST** (REPORTED, unverified). Also confirm the Phase-1 deadline, rubric, team name
     and college name.
   - Dependency: none · Acceptance: registration confirmation recorded in CURRENT_STATE.md ·
     Difficulty: trivial · Parallel: yes · Approval: owner action.

2. **Decide the Class C items P-C1 … P-C6 (HUMAN)**
   - Objective: approve, reject or amend each item in [PROPOSALS.md](PROPOSALS.md). P-C4
     (partition provenance) and P-C5 (outcome-blind E access) block S1/S2. P-C2, P-C3 and P-C6
     block S5. P-C1 blocks S7.
   - Dependency: none · Acceptance: each decision recorded in DECISION_LOG.md · Difficulty:
     review · Parallel: yes · Approval: **yes**.

3. **Request the blueprint's original `partition.csv`, `audit.py`, `audit2.py` (HUMAN)**
   - Objective: P-C4 option A. · Dependency: none · Acceptance: files placed in the repo, or a
     statement that they are unavailable · Difficulty: trivial · Parallel: yes · Approval: owner.

4. **S1 — Acquire the official ShanghaiT2DM copy and run the structural audit (G0, G1)**  ← *next engineering task*
   - Objective: `scripts/fetch_official.py`, `data/MANIFEST.sha256`, checksum verification,
     adapter v0 (column-variant discovery and mapping, timestamp parsing), and
     `hyposense audit --structural`.
   - Dependency: P-C5 approval before the audit reads E files (fetching and checksumming are
     outcome-blind and may proceed).
   - Acceptance: 109 files pinned; every column variant mapped (an unmapped one is an error);
     reading count reconciled to 112,475 or the difference explained; G1 measured; the audit
     runs twice with an identical report hash; tests pass.
   - Difficulty: medium · Parallel: no (critical path) · Approval: P-C5.

5. **S2 — Schemas, label builder (test-first), event audit, partition + guard**
   - Dependency: S1, P-C4 · Acceptance: ≥20 label fixtures pass; episode counts reconciled
     with the blueprint or differences explained; `configs/partition.csv` frozen; partition
     guard and `test_group_by_patient` pass · Difficulty: medium–high · Parallel: no ·
     Approval: P-C4.

## P1 — Core

1. **S3 — Drug dictionary, parser, kernels, exposure; source kernel parameters**
   - Dependency: S2 · Acceptance: ≥99% dictionary coverage; all kernel tests pass; pharma.yaml
     has no ILLUSTRATIVE kernels (or a documented reviewer gap); G3 measured · Difficulty: high ·
     Parallel: partly (kernel maths needs no data) · Approval: pharmacist review (human
     resource), P-B3/P-B4 a-priori decisions.
2. **S4 — State engine + causal features; truncation-equality test**
   - Dependency: S3 · Acceptance: leakage suite green; throughput measured · Difficulty: high ·
     Parallel: no.
3. **S5 — Evaluation harness, metrics, bootstrap, M0, ANALYSIS_PLAN.md**
   - Dependency: S4, P-C2/P-C3/P-C6 · Acceptance: metric fixtures pass; M0 curve on T ·
     Difficulty: high · Parallel: metric code can start after S2.
4. **S6 — M1 tuning, ladder on T, calibration benchmark, Gate G4**
   - Dependency: S5 · Acceptance: G4 passed; determinism tests pass · Difficulty: medium ·
     Parallel: no.
5. **S7 — Policy, replay, FastAPI + SSE**
   - Dependency: S4 schemas (works with M0 before S6) · Acceptance: Table 14.1 tests;
     replay-hash determinism · Difficulty: medium · Parallel: **yes**.

## P2 — Product / Demo

1. **S8 — Next.js frontend: Ward Board, Patient Review, Evidence view**
   - Dependency: S7 API contract · Acceptance: all six states visible on a T replay;
     Playwright E2E; offline static build · Difficulty: high · Parallel: **yes**.
2. **Early submittable version** (S0–S5 + minimal S7–S8 with M0 on T replay)
   - Dependency: S5, minimal S7/S8 · Acceptance: runs end-to-end and is honestly labelled
     DEVELOPMENT · Difficulty: medium · Parallel: —.
3. **FREEZE → S9 → S10** as in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).
4. **Remote repository + CI workflow; LICENSE + DATA_LICENSES.md** · Difficulty: low ·
   Parallel: yes · Approval: owner (repo visibility, licence holder).

## P3 — Enhancements (only after P0–P2 are healthy)

1. Docker image for the demo (REC).
2. Logistic-regression robustness run R3 (OPT, after S9).
3. Carbohydrate estimation E3 from the English diet text (OPT).
4. E1/M4 reduced physiology — **not planned** (ADR-015).
