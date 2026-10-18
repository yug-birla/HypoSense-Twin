"""S6 rule and mask logic on SYNTHETIC fixtures: labels, P-B6 masks, P-B1/B6/B8 decisions, and
out-of-fold score assembly (independent review F7)."""

from __future__ import annotations

import numpy as np

from hyposense.evaluation.devdata import _y, cbg_contradicted, pb6_window_mask
from hyposense.evaluation.s6_run import pb1_decide, pb6_decide, pb8_decide

H = 3600


def test_label_is_onset_in_half_open_horizon() -> None:
    ts = np.array([0, 300, 3600, 3900, 4000, 9000], dtype=np.int64)
    onsets = np.array([3900], dtype=np.int64)
    # (t, t+h]: t=300 -> 3900 inside (boundary inclusive); t=0 -> 3900 > 3600; t=3900 -> excluded
    assert _y(ts, onsets, H).tolist() == [0, 1, 1, 0, 0, 0]
    assert _y(ts, np.array([], dtype=np.int64), H).tolist() == [0] * 6


def test_pb6_window_mask_overlap_and_eligibility() -> None:
    ts = np.arange(0, 20001, 1000, dtype=np.int64)
    elig = np.ones(len(ts), dtype=bool)
    elig[ts == 8000] = False
    m = pb6_window_mask(ts, elig, [(10000, 12000)], H)
    # (t, t+3600] overlaps [10000, 12000]  <=>  t < 12000 and t + 3600 >= 10000
    expected = (ts < 12000) & (ts + H >= 10000) & elig
    assert m.tolist() == expected.tolist()
    assert not m[ts == 8000].any() and m[ts == 7000].all() and not m[ts == 6000].any()
    assert not pb6_window_mask(ts, elig, [], H).any()


def test_cbg_contradiction_rule() -> None:
    cg = np.array([60.0, 62, 65, 68, 69, 120])
    assert cbg_contradicted(np.array([80.0, 90, 75, 70, 85, 60]), cg)  # 5 lows, all CBG >= 70
    assert not cbg_contradicted(np.array([80.0, 90, 75, 69, 85, 120]), cg)  # one CBG confirms
    assert not cbg_contradicted(np.array([80.0, 90, 75, 70]), cg[:4])  # only 4 pairs
    assert not cbg_contradicted(np.array([], dtype=float), np.array([], dtype=float))


def _pb1(iso: float, iso_ece: float, platt: float, p_ece: float, interp: float, i_ece: float):  # type: ignore[no-untyped-def]
    return {
        "isotonic": {"log_loss": iso, "ece": iso_ece},
        "platt": {"log_loss": platt, "ece": p_ece},
        "isotonic_interp": {"log_loss": interp, "ece": i_ece},
    }


def test_pb1_decision_rule() -> None:
    assert pb1_decide(_pb1(1.0, 0.01, 0.995, 0.005, 0.999, 0.001)) == "isotonic"  # < 1 %
    assert pb1_decide(_pb1(1.0, 0.01, 0.98, 0.02, 1.0, 0.01)) == "isotonic"  # ECE higher
    assert pb1_decide(_pb1(1.0, 0.01, 0.99, 0.01, 1.0, 0.01)) == "platt"  # exactly 1 %, ECE tie
    assert pb1_decide(_pb1(1.0, 0.01, 0.98, 0.005, 0.97, 0.009)) == "isotonic_interp"  # best LL


def test_pb6_and_pb8_decision_rules() -> None:
    assert pb6_decide(1.0, 0.99) == "ADOPT for training"
    assert pb6_decide(1.0, 0.995) == "KEEP canonical training"
    assert pb8_decide(1.0, 0.98, 0.9, 0.9).startswith("candidate preferred")
    assert pb8_decide(1.0, 0.98, 0.9, 0.89) == "M3_baseline retained"
    assert pb8_decide(1.0, 0.995, 0.9, 0.95) == "M3_baseline retained"


def test_assemble_places_each_fold_score_at_its_rows() -> None:
    from types import SimpleNamespace

    from hyposense.evaluation.s6_run import _assemble

    dev = SimpleNamespace(table=np.zeros(6))
    outs = [
        {
            "idx": np.array([0, 2, 4]),
            "raw": np.array([0.0, 0.2, 0.4]),
            "cal": {"m": np.array([1.0, 1.2, 1.4])},
        },
        {"idx": np.array([1, 3]), "raw": np.array([0.1, 0.3]), "cal": {"m": np.array([1.1, 1.3])}},
    ]
    raw = _assemble(dev, outs, "raw")  # type: ignore[arg-type]
    assert raw[:5].tolist() == [0.0, 0.1, 0.2, 0.3, 0.4] and np.isnan(raw[5])
    assert _assemble(dev, outs, "m")[:5].tolist() == [1.0, 1.1, 1.2, 1.3, 1.4]  # type: ignore[arg-type]
