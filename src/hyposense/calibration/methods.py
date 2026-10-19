"""Probability calibrators (Blueprint §11.1; P-B1). Each is fitted on DEVELOPMENT / inner
out-of-fold raw predictions only and serialises to plain JSON (no pickle, ADR-009).

- `isotonic` (canonical): sklearn IsotonicRegression, clipped to the fitted range. Constant within
  blocks; sklearn joins block edges linearly.
- `platt`: logistic regression of y on logit(p), unpenalised.
- `isotonic_interp` (P-B1 challenger): linear interpolation between the isotonic blocks'
  centroids (mean raw score, block value). Strictly monotone between distinct blocks, so it keeps
  score resolution.
- `isotonic_interp_floored` (P-B10 challenger): `isotonic_interp` clamped to [p_lo, 1 - p_lo],
  p_lo = (positives in the lowest isotonic block + 0.5) / (block size + 1), all on the fitting
  data (inner OOF). Never outputs exactly 0 or 1; monotone (non-decreasing).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

F64 = npt.NDArray[np.float64]
EPS = 1e-6
METHODS = ("isotonic", "platt", "isotonic_interp")
# P-B10 challenger (pre-specified, DEC-2026-10-19-L). Deliberately NOT in METHODS, so the S6
# workflow and its P-B1 decision are unchanged.
CHALLENGERS = ("isotonic_interp_floored",)


@dataclass(frozen=True)
class Calibrator:
    method: str
    params: dict[str, Any]

    def apply(self, p: F64) -> F64:
        p = np.asarray(p, dtype=np.float64)
        if self.method in ("isotonic", "isotonic_interp", "isotonic_interp_floored"):
            x = np.asarray(self.params["x"])
            y = np.asarray(self.params["y"])
            out: F64 = np.interp(np.clip(p, x[0], x[-1]), x, y)
            if self.method == "isotonic_interp_floored":
                lo = float(self.params["p_lo"])
                out = np.clip(out, lo, 1.0 - lo)
            return out
        if self.method == "platt":
            z = np.log(np.clip(p, EPS, 1 - EPS) / (1 - np.clip(p, EPS, 1 - EPS)))
            res: F64 = 1.0 / (1.0 + np.exp(-(self.params["a"] * z + self.params["b"])))
            return res
        raise ValueError(self.method)


def fit(method: str, p: F64, y: npt.NDArray[np.int64]) -> Calibrator:
    from sklearn.isotonic import IsotonicRegression  # type: ignore[import-untyped]
    from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]

    p = np.asarray(p, dtype=np.float64)
    if method == "platt":
        z = np.log(np.clip(p, EPS, 1 - EPS) / (1 - np.clip(p, EPS, 1 - EPS))).reshape(-1, 1)
        lr = LogisticRegression(C=np.inf, solver="lbfgs", max_iter=1000).fit(z, y)
        return Calibrator("platt", {"a": float(lr.coef_[0][0]), "b": float(lr.intercept_[0])})
    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(p, y)
    x, v = iso.X_thresholds_.astype(float), iso.y_thresholds_.astype(float)
    if method == "isotonic":
        return Calibrator("isotonic", {"x": x.tolist(), "y": v.tolist()})
    if method in ("isotonic_interp", "isotonic_interp_floored"):
        fitted = iso.predict(p)
        cx, cy = [], []
        for val in np.unique(fitted):
            m = fitted == val
            cx.append(float(p[m].mean()))
            cy.append(float(val))
        order = np.argsort(cx, kind="stable")
        cxs = np.array(cx)[order]
        cys = np.maximum.accumulate(np.array(cy)[order])
        params: dict[str, Any] = {"x": cxs.tolist(), "y": cys.tolist()}
        if method == "isotonic_interp":
            return Calibrator("isotonic_interp", params)
        low = fitted == fitted.min()  # the lowest isotonic block
        y_arr = np.asarray(y)
        params["p_lo"] = float((y_arr[low].sum() + 0.5) / (low.sum() + 1))
        params["lowest_block"] = {"size": int(low.sum()), "positives": int(y_arr[low].sum())}
        return Calibrator("isotonic_interp_floored", params)
    raise ValueError(method)
