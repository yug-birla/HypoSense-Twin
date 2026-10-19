"""Pre-specified P-B10 / P-B11 / P-B12 decision rules (DEC-2026-10-19-L, commit 6b1ad05)."""

from __future__ import annotations

import math

import numpy as np

from hyposense.evaluation.prefreeze import (
    FOLD_SEEDS,
    MODEL_SEEDS,
    ll_unclipped,
    pb10_decision,
    pb10_outcome,
    pb12_decision,
    stability_label,
)


def m(ll: float, ece: float) -> dict[str, float]:
    return {"ll_u": ll, "ece": ece}


def test_grid_is_the_prespecified_one() -> None:
    assert FOLD_SEEDS == (2026, 2028, 2029)
    assert MODEL_SEEDS == (2026, 2028, 2029, 2030, 2031)


def test_unclipped_log_loss_is_infinite_on_a_certain_miss() -> None:
    y = np.array([0, 1, 0])
    assert math.isinf(ll_unclipped(y, np.array([0.1, 0.0, 0.2])))
    assert math.isinf(ll_unclipped(y, np.array([1.0, 0.5, 0.2])))
    assert ll_unclipped(np.array([0, 0]), np.array([0.0, 0.0])) == 0.0  # 0 on negatives is fine
    p = np.array([0.1, 0.6, 0.2])
    expect = -(np.log(0.9) + np.log(0.6) + np.log(0.8)) / 3
    assert math.isclose(ll_unclipped(y, p), expect)


def test_pb10_r1_current_inadmissible() -> None:
    cur = m(math.inf, 0.0010)
    assert pb10_outcome(cur, m(0.04, 0.0011), m(0.03, 0.0005)) == "ADOPT floored"
    assert (
        pb10_outcome(cur, m(0.04, 0.0012), m(0.04, 0.0009)) == "ADOPT platt"
    )  # floored ECE > 1.1x
    assert pb10_outcome(cur, m(math.inf, 0.001), m(0.04, 0.005)) == "INCONCLUSIVE"


def test_pb10_r2_current_admissible() -> None:
    cur = m(0.0400, 0.0010)
    assert pb10_outcome(cur, m(0.0395, 0.0009), m(0, 0)) == "ADOPT floored"  # >= 1 % and ECE ok
    assert pb10_outcome(cur, m(0.0399, 0.0010), m(0, 0)) == "NO MATERIAL DIFFERENCE"
    assert pb10_outcome(cur, m(0.0405, 0.0009), m(0, 0)) == "KEEP CURRENT"  # LL >= 1 % worse
    assert pb10_outcome(cur, m(0.0399, 0.0012), m(0, 0)) == "KEEP CURRENT"  # ECE > 1.1x


def test_pb10_decision_needs_integrity_and_r3() -> None:
    assert pb10_decision("ADOPT floored", True, ["ADOPT floored"] * 10 + ["X"] * 5) == "ADOPT"
    assert pb10_decision("ADOPT floored", True, ["ADOPT floored"] * 9 + ["X"] * 6) == "INCONCLUSIVE"
    assert pb10_decision("KEEP CURRENT", False, ["KEEP CURRENT"] * 15) == "INCONCLUSIVE"
    assert pb10_decision("NO MATERIAL DIFFERENCE", True, ["NO MATERIAL DIFFERENCE"] * 15) == (
        "NO MATERIAL DIFFERENCE"
    )


def test_stability_reading_thresholds() -> None:
    assert stability_label([1] * 13 + [-1] * 2) == "stable"
    assert stability_label([1] * 11 + [-1] * 4) == "unstable"
    assert stability_label([1] * 12 + [-1] * 3) == "leaning"
    assert stability_label([1] * 12 + [0] * 3) == "leaning"  # ties are not the same sign


def test_pb12_decision_rule() -> None:
    c = ("C0_current", "C1_key_inputs", "C2_wider_range")

    def d(
        useful: tuple[bool, ...],
        sep: tuple[bool, ...],
        st: tuple[bool, ...],
        s: tuple[float, ...] = (0.1, 0.1, 0.1),
    ) -> str:
        z = lambda v: dict(zip(c, v, strict=True))  # noqa: E731
        return pb12_decision(z(useful), z(sep), z(st), z(s))

    assert d((False, True, True), (True,) * 3, (True,) * 3, (0.1, 0.05, 0.2)).endswith(
        "C2_wider_range)"
    )
    assert d((False, True, True), (True,) * 3, (True,) * 3, (0.1, 0.2, 0.2)).endswith(
        "C1_key_inputs)"
    )
    assert d((False, False, False), (True, False, False), (True, False, False)) == "KEEP CURRENT"
    assert d((False,) * 3, (False,) * 3, (True,) * 3) == "REMOVE TAG"
    assert d((False,) * 3, (False, True, False), (False,) * 3) == "INCONCLUSIVE"
