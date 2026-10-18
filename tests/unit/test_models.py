"""S6 model-side tests: grouped folds, calibrators, LightGBM wrapper. All data SYNTHETIC."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hyposense.calibration.methods import METHODS, Calibrator, fit
from hyposense.common.config import load_config
from hyposense.evaluation.folds import grouped_folds
from hyposense.features.spec import FeatureSpecMismatch
from hyposense.models.lgbm import base_params, train

CFG = load_config()


def test_grouped_folds_are_deterministic_balanced_and_stratified() -> None:
    pats = [f"p{i}" for i in range(30)]
    strata = {p: i % 4 for i, p in enumerate(pats)}
    a = grouped_folds(pats, strata, 5, 2026)
    assert a == grouped_folds(pats, strata, 5, 2026)
    assert set(a) == set(pats)
    sizes = np.bincount(list(a.values()))
    assert sizes.max() - sizes.min() <= 1
    for s in range(4):
        fs = [a[p] for p in pats if strata[p] == s]
        assert len(set(fs)) >= min(5, len(fs)) - 1  # each stratum spread over folds
    assert a != grouped_folds(pats, strata, 5, 2027)
    with pytest.raises(ValueError):
        grouped_folds(pats[:3], strata, 5, 2026)


def test_calibrators_are_monotone_bounded_and_serialisable() -> None:
    rng = np.random.default_rng(0)
    p = rng.uniform(0, 0.3, 5000)
    y = (rng.uniform(size=5000) < np.sqrt(p)).astype(int)  # miscalibrated on purpose
    grid = np.linspace(0, 0.3, 200)
    for m in METHODS:
        c = fit(m, p, y)
        out = c.apply(grid)
        assert np.all(np.diff(out) >= -1e-12) and out.min() >= 0 and out.max() <= 1
        again = Calibrator(c.method, {k: v for k, v in c.params.items()})
        assert np.array_equal(again.apply(grid), out)
    iso = fit("isotonic", p, y).apply(p)
    interp = fit("isotonic_interp", p, y).apply(p)
    assert len(np.unique(interp)) > len(np.unique(iso))  # keeps resolution (P-B1)


def _data(n: int = 3000, seed: int = 1) -> tuple[pd.DataFrame, np.ndarray]:
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(
        {"a": rng.normal(size=n), "b": rng.normal(size=n), "q": rng.integers(0, 6, n).astype(float)}
    )
    y = (rng.uniform(size=n) < 1 / (1 + np.exp(-(X["a"] * 2 - 3)))).astype(int)
    return X, y


def test_lgbm_training_is_deterministic_and_checks_features() -> None:
    X, y = _data()
    p = {
        **base_params(CFG),
        "learning_rate": 0.05,
        "num_leaves": 7,
        "min_data_in_leaf": 50,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "lambda_l2": 1.0,
    }
    m1 = train(X, y, p, 60, categorical=("q",))
    m2 = train(X, y, p, 60, categorical=("q",))
    assert m1.sha256 == m2.sha256 and m1.categorical == ("q",)
    assert np.array_equal(m1.predict(X), m2.predict(X))
    with pytest.raises(FeatureSpecMismatch):
        m1.predict(X[["b", "a", "q"]])


def test_early_stopping_records_best_iteration_and_class_weighting_is_refused() -> None:
    X, y = _data()
    Xv, yv = _data(seed=2)
    p = {
        **base_params(CFG),
        "learning_rate": 0.1,
        "num_leaves": 31,
        "min_data_in_leaf": 20,
        "feature_fraction": 1.0,
        "bagging_fraction": 1.0,
        "lambda_l2": 0.0,
    }
    m = train(X, y, p, 2000, valid=(Xv, yv), early_stopping_rounds=20)
    assert (
        1 <= m.history["best_iteration"] < 2000 and m.num_boost_round == m.history["best_iteration"]
    )
    bad = {**CFG, "model": {**CFG["model"], "class_weighting": "balanced"}}
    with pytest.raises(ValueError):
        base_params(bad)
