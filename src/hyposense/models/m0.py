"""M0 trend rule (Blueprint Table 11.1; ANALYSIS_PLAN §0d and §3.1). No fitted parameters.

projection(t + H) = g(t) + H x slope, where slope is the least-squares slope over (t - 35 min, t]
with >= 3 readings (the executable spec, audit2.py). It is computed by the SAME function as the
`cgm_slope30` / `cgm_m0_proj60` features (`features.cgm.trend_slope`), so M0 and the features
cannot diverge.

Score orientation (§3.1): score = -projection(t + 60). M0 alerts iff projection < theta, i.e.
score > -theta: the comparator is STRICT. An undefined projection (< 3 readings) gives score NaN,
which never alerts.
"""

from __future__ import annotations

import math

from hyposense.features.cgm import CGMFeatureConfig, trend_projection
from hyposense.state.patient import PatientState

M0_HORIZON_MIN = 60
M0_STRICT = True  # ALERT iff score > tau (projection < theta)


def projection(s: PatientState, cfg: CGMFeatureConfig, horizon_min: int = M0_HORIZON_MIN) -> float:
    """The same function as the cgm_m0_proj features (exact arithmetic, rounded once)."""
    return trend_projection(s.cgm.series.ts, s.cgm.series.values, horizon_min, cfg)


class M0Scorer:
    model_id = "M0"
    version = "1.0.0"
    strict = M0_STRICT

    def __init__(self, cfg: CGMFeatureConfig) -> None:
        self.cfg = cfg

    def __call__(self, s: PatientState) -> float:
        p = projection(s, self.cfg)
        return -p if math.isfinite(p) else math.nan


def theta_to_tau(theta_mgdl: float) -> float:
    return -theta_mgdl


def tau_to_theta(tau: float) -> float:
    return -tau
