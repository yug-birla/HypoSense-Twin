"""LightGBM wrapper (Blueprint §11.1; ADR-009 no pickle; DEC-2026-10-18-G).

Fixed, shared settings: binary objective, binary_logloss, no class weighting, seed 2026,
deterministic, num_threads 1, bagging_freq 1 (so that bagging_fraction acts), force_row_wise.
Tuned: learning_rate, num_leaves, min_data_in_leaf, feature_fraction, bagging_fraction,
lambda_l2 (search space `configs/default.yaml model.search_space`), and num_boost_round (P-B2).
The model text (LightGBM's own format) is the artefact; its SHA-256 identifies the model.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from hyposense.common.hashing import sha256_bytes

F64 = npt.NDArray[np.float64]


def base_params(cfg: dict[str, Any]) -> dict[str, Any]:
    m = cfg["model"]
    if m.get("class_weighting", "none") != "none":
        raise ValueError("class re-weighting is excluded by the protocol (§11.1)")
    return {
        "objective": m["objective"],
        "metric": "binary_logloss",
        "seed": int(m["seed"]),
        "deterministic": bool(m["deterministic"]),
        "num_threads": int(m["num_threads"]),
        "force_row_wise": True,
        "bagging_freq": 1,
        "verbosity": -1,
    }


@dataclass(frozen=True)
class TrainedModel:
    model_text: str
    features: tuple[str, ...]
    num_boost_round: int
    params: dict[str, Any]
    categorical: tuple[str, ...] = ()
    history: dict[str, Any] = field(default_factory=dict)

    @property
    def sha256(self) -> str:
        return sha256_bytes(self.model_text.encode("utf-8"))

    def booster(self) -> Any:
        import lightgbm as lgb

        return lgb.Booster(model_str=self.model_text)

    def predict(self, X: pd.DataFrame) -> F64:
        if tuple(X.columns) != self.features:
            from hyposense.features.spec import FeatureSpecMismatch

            raise FeatureSpecMismatch("input columns differ from the model's feature list")
        out: F64 = np.asarray(self.booster().predict(X.to_numpy(np.float64)), dtype=np.float64)
        return out


def train(
    X: pd.DataFrame,
    y: npt.NDArray[np.int64],
    params: dict[str, Any],
    num_boost_round: int,
    categorical: Sequence[str] = (),
    valid: tuple[pd.DataFrame, npt.NDArray[np.int64]] | None = None,
    early_stopping_rounds: int | None = None,
) -> TrainedModel:
    import lightgbm as lgb

    feats = tuple(X.columns)
    cat = [c for c in categorical if c in feats]
    dtrain = lgb.Dataset(
        X.to_numpy(np.float64),
        label=y,
        feature_name=list(feats),
        categorical_feature=cat or "auto",
        free_raw_data=False,
    )
    record: dict[str, Any] = {}
    callbacks = [lgb.record_evaluation(record)]
    valid_sets = [dtrain]
    names = ["train"]
    if valid is not None:
        dvalid = lgb.Dataset(
            valid[0].to_numpy(np.float64),
            label=valid[1],
            reference=dtrain,
            feature_name=list(feats),
            categorical_feature=cat or "auto",
        )
        valid_sets.append(dvalid)
        names.append("valid")
        if early_stopping_rounds:
            callbacks.append(lgb.early_stopping(early_stopping_rounds, verbose=False))
    b = lgb.train(
        dict(params),
        dtrain,
        num_boost_round=num_boost_round,
        valid_sets=valid_sets,
        valid_names=names,
        callbacks=callbacks,
    )
    best = int(b.best_iteration) if valid is not None and early_stopping_rounds else num_boost_round
    hist = {
        "best_iteration": best,
        "train_logloss": float(record["train"]["binary_logloss"][best - 1]),
        "valid_logloss": (
            float(record["valid"]["binary_logloss"][best - 1]) if valid is not None else None
        ),
    }
    text = b.model_to_string(num_iteration=best)
    return TrainedModel(text, feats, best, dict(params), tuple(cat), hist)
