"""S5 integration tests on the official copy, TUNING partition only (aggregate assertions).

Pinned values are invariants of: the SHA-pinned data (v5; v2 reconciliation copy), the approved
protocol (ANALYSIS_PLAN §0, §0d, §2-3), and the code. They may change only through a
DECISION_LOG entry.
"""

from __future__ import annotations

import pytest

from hyposense.common.config import REPO_ROOT, load_config, load_yaml
from hyposense.data.dataset import AccessScope, load_dataset, load_legacy_tuning
from hyposense.evaluation.data import as_label_eligible_decisions
from hyposense.evaluation.m0_run import (
    MODEL,
    REFERENCE,
    compare,
    curve_rows,
    eval_recordings,
    exact_ties,
    table_rows,
    treated_patient_keys,
)
from hyposense.evaluation.metrics import EventRules

pytestmark = pytest.mark.requires_data
ER = EventRules.from_config(load_config())

LEGACY = REPO_ROOT / "data" / "raw" / "reconciliation" / "v2"


@pytest.fixture(scope="module")
def v5():  # type: ignore[no-untyped-def]
    ds = load_dataset(AccessScope.TUNING_ONLY)
    return eval_recordings(ds.recordings, ds.summary)


@pytest.mark.skipif(not LEGACY.is_dir(), reason="figshare v2 reconciliation copy not extracted")
def test_table_a2_reproduces_on_v2_tuning() -> None:
    lt = load_legacy_tuning(2)
    recs = as_label_eligible_decisions(eval_recordings(lt.recordings, lt.summary))
    ref = load_yaml(REFERENCE)
    thetas = sorted(int(t) for t in ref["rows"])
    treated = treated_patient_keys()
    rows = table_rows(recs, thetas, ER, treated)
    ties = {th: exact_ties(recs, th) for th in thetas}
    tie_rows = table_rows(recs, thetas, ER, treated, strict=False)
    status = {c["theta"]: c["status"] for c in compare(rows, ref, tie_rows, ties)}
    assert status == {
        40: "MATCH",
        45: "EXPECTED DIFFERENCE",
        50: "MATCH",
        55: "MATCH",
        60: "MATCH",
        65: "MATCH",
        70: "MATCH",
        80: "MATCH",
    }
    assert ties[45] == 44 and all(ties[t] == 0 for t in thetas if t != 45)


def test_m0_v5_tuning_development_invariants(v5) -> None:  # type: ignore[no-untyped-def]
    treated = treated_patient_keys()
    assert len(v5) == 34 and sum(len(r.ts) for r in v5) == 33464
    t = [r for r in v5 if r.patient_key in treated]
    s = curve_rows(t, ER)["summary"]
    assert s["theta_alert"] == 54.0 and s["non_monotone_fa_steps"] == 0
    assert round(s["sens_at_1fa"], 4) == 0.626 and not s["first_crossing"]["budget_not_reached"]
    a = curve_rows(v5, ER)["summary"]
    assert a["theta_alert"] == 52.2 and round(a["sens_at_1fa"], 4) == 0.6096


def test_policy_and_label_decision_sets_differ_only_slightly(v5) -> None:  # type: ignore[no-untyped-def]
    q = sum(int(r.queried.sum()) for r in v5)
    e = sum(int(r.eligible.sum()) for r in v5)
    both = sum(int((r.queried & r.eligible).sum()) for r in v5)
    assert (q, e, both) == (31416, 31292, 31288)
    assert all(MODEL in r.scores for r in v5)
