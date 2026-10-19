"""P-B10 floored calibrator (SYNTHETIC data)."""

from __future__ import annotations

import numpy as np
import pytest

from hyposense.calibration.methods import fit


def test_floored_interp_never_reaches_0_or_1_and_keeps_order() -> None:
    """P-B10: p_lo from the lowest isotonic block; clamp only; monotone; METHODS unchanged."""
    from hyposense.calibration.methods import CHALLENGERS, METHODS

    rng = np.random.default_rng(3)
    p = rng.uniform(0, 1, 4000)
    y = (rng.uniform(0, 1, 4000) < p**4).astype(np.int64)
    f = fit("isotonic_interp_floored", p, y)
    base = fit("isotonic_interp", p, y)
    blk = f.params["lowest_block"]
    assert f.params["p_lo"] == pytest.approx((blk["positives"] + 0.5) / (blk["size"] + 1))
    grid = np.linspace(-0.5, 1.5, 2001)
    out = f.apply(grid)
    assert out.min() >= f.params["p_lo"] > 0 and out.max() <= 1 - f.params["p_lo"] < 1
    assert np.all(np.diff(out) >= 0)
    assert np.array_equal(out, np.clip(base.apply(grid), f.params["p_lo"], 1 - f.params["p_lo"]))
    assert "isotonic_interp_floored" not in METHODS and CHALLENGERS == ("isotonic_interp_floored",)
