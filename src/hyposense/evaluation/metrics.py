"""Canonical evaluation metrics (OFFLINE). ANALYSIS_PLAN §2 (policy replay semantics) and §3
(operating curve, sens@B, thresholds); Blueprint Table 20.2 and App. E. Every definition lives in
`evaluation/registry.py`; this module implements them once, for every model.

Policy-replay accounting at a threshold tau (one recording; the cooldown never crosses recordings):
- ALERT at reading i  iff  queried[i] and score[i] passes tau (>= tau; > tau if strict, M0).
- Notifications: greedy in time. An ALERT notifies iff t - (last notification) >= 60 min.
- Outcome of a notification at t_n (§2.4): TRUE if an L1 onset lies in (t_n, t_n + 60 min];
  otherwise FALSE if the recording's last reading is >= t_n + 60 min; otherwise OUTCOME-UNKNOWN.
- An episode is hit iff some label-eligible AND queried reading in [onset - 60, onset - 15] min
  (closed) has ALERT. Lead = onset - the earliest such reading.

Exact operating curve (§3.2-3.3). Each recording's counts are a step function of its own distinct
queried scores, computed exactly (one greedy pass per step). The global grid is every distinct
queried score, with the sentinel +inf first. Per-patient arrays on that grid (`PatientCurves`)
serve the full sample (weights 1) and every bootstrap resample (weights = multiplicity). At a
grid value that is not a resampled patient's score, the point duplicates an adjacent point of the
resample's own grid, so first-crossing values and areas are exactly those of the resample's own
grid (§3.4 "the grid is the set of distinct scores within that resample").
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt

from hyposense.evaluation.data import EvalRecording

TRUE, FALSE, UNKNOWN = 0, 1, 2
EXCLUDED = 3  # SA9-ii only: removed from every notification class
F64 = npt.NDArray[np.float64]
I64 = npt.NDArray[np.int64]


@dataclass(frozen=True)
class EventRules:
    horizon_s: int = 3600
    min_lead_s: int = 900
    cooldown_s: int = 3600

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> EventRules:
        return cls(
            horizon_s=int(cfg["event"]["horizon_min"]) * 60,
            min_lead_s=int(cfg["event"]["min_lead_min"]) * 60,
            cooldown_s=int(cfg["policy"]["cooldown_min"]) * 60,
        )


# ---------------------------------------------------------------- primitives
def passes(score: F64, tau: float, strict: bool) -> npt.NDArray[np.bool_]:
    """Vectorised comparator; NaN never passes (ANALYSIS_PLAN §3.1)."""
    with np.errstate(invalid="ignore"):
        out: npt.NDArray[np.bool_] = (score > tau) if strict else (score >= tau)
    return out & ~np.isnan(score)


def notification_indices(ts: I64, alert: npt.NDArray[np.bool_], cooldown_s: int) -> I64:
    """Greedy cooldown: the first ALERT notifies; the next notification is the first ALERT at
    >= last + cooldown. Exact."""
    idx = np.flatnonzero(alert)
    if not len(idx):
        return idx.astype(np.int64)
    ta = ts[idx]
    out = []
    k = 0
    while k < len(ta):
        out.append(idx[k])
        k = int(np.searchsorted(ta, ta[k] + cooldown_s, side="left"))
    return np.array(out, dtype=np.int64)


def classify_notifications(t_n: I64, onsets: I64, last_ts: int, horizon_s: int) -> I64:
    """TRUE / FALSE / UNKNOWN per notification (§2.4)."""
    out = np.full(len(t_n), FALSE, dtype=np.int64)
    if len(onsets):
        j = np.searchsorted(onsets, t_n, side="right")  # first onset strictly after t_n
        has = j < len(onsets)
        hit = np.zeros(len(t_n), dtype=bool)
        hit[has] = onsets[j[has]] <= t_n[has] + horizon_s
        out[hit] = TRUE
    else:
        hit = np.zeros(len(t_n), dtype=bool)
    unknown = ~hit & (t_n + horizon_s > last_ts)
    out[unknown] = UNKNOWN
    return out


def _classify(r: EvalRecording, n: I64, rules: EventRules) -> I64:
    """Notification classes for a recording. Canonical unless a §5.7 variant field is set:
    `notif_onsets` replaces the onsets used for classification; `notif_exclude` removes
    notifications whose (t, t + H] window overlaps an excluded interval."""
    onsets = r.notif_onsets if r.notif_onsets is not None else r.onsets
    t_n = r.ts[n]
    c = classify_notifications(t_n, onsets, r.last_ts, rules.horizon_s)
    if r.notif_exclude:
        keep = np.ones(len(t_n), dtype=bool)
        for a, b in r.notif_exclude:
            keep &= ~((a < t_n + rules.horizon_s) & (b > t_n))
        c = np.where(keep, c, EXCLUDED)
    return c


def episode_window_readings(r: EvalRecording, onset: int, rules: EventRules) -> I64:
    """Indices of label-eligible, queried readings in [onset - H, onset - min_lead] (closed)."""
    lo = int(np.searchsorted(r.ts, onset - rules.horizon_s, side="left"))
    hi = int(np.searchsorted(r.ts, onset - rules.min_lead_s, side="right"))
    i = np.arange(lo, hi)
    out: I64 = i[r.eligible[lo:hi] & r.queried[lo:hi]]
    return out


def hit_scores(r: EvalRecording, model: str, rules: EventRules) -> F64:
    """Per onset, the best (maximum) score in its warning window; NaN if the window holds no
    usable reading. An episode is hit at tau iff its hit score passes tau."""
    s = r.scores[model]
    out = np.full(len(r.onsets), np.nan)
    for k, o in enumerate(r.onsets.tolist()):
        w = episode_window_readings(r, o, rules)
        v = s[w]
        v = v[~np.isnan(v)]
        if len(v):
            out[k] = float(v.max())
    return out


# ---------------------------------------------------------------- per-recording step functions
@dataclass(frozen=True)
class RecordingSteps:
    """Counts at alert level j = 0..m (j = number of the recording's distinct queried scores,
    from the top, that alert)."""

    distinct_desc: F64  # the recording's distinct finite queried scores, descending
    true: I64
    false: I64
    unknown: I64


def recording_steps(r: EvalRecording, model: str, rules: EventRules) -> RecordingSteps:
    s = r.scores[model]
    q = r.queried & ~np.isnan(s)
    d = np.unique(s[q])[::-1]
    m = len(d)
    t_arr = np.zeros(m + 1, dtype=np.int64)
    f_arr = np.zeros(m + 1, dtype=np.int64)
    u_arr = np.zeros(m + 1, dtype=np.int64)
    for j in range(1, m + 1):
        alert = q & (s >= d[j - 1])  # level j = alert set {score >= d_j} (no NaN by q)
        n = notification_indices(r.ts, alert, rules.cooldown_s)
        c = _classify(r, n, rules)
        t_arr[j] = int(np.sum(c == TRUE))
        f_arr[j] = int(np.sum(c == FALSE))
        u_arr[j] = int(np.sum(c == UNKNOWN))
    return RecordingSteps(d, t_arr, f_arr, u_arr)


def level(distinct_desc: F64, tau: F64, strict: bool) -> I64:
    """Alert level j(tau) = number of distinct scores passing tau (vectorised over tau)."""
    asc = distinct_desc[::-1]
    pos = np.searchsorted(asc, tau, side="right") if strict else np.searchsorted(asc, tau)
    out: I64 = (len(asc) - pos).astype(np.int64)
    return out


# ---------------------------------------------------------------- per-patient curves on a grid
@dataclass(frozen=True)
class PatientCurves:
    """Per-patient counts on the global grid (row = patient, column = grid point)."""

    model: str
    strict: bool
    patients: tuple[str, ...]
    tau: F64  # grid, index 0 = +inf sentinel, then distinct scores descending
    fa: I64
    true: I64
    unknown: I64
    hits: I64
    days: F64
    n_episodes: I64
    n_warnable: I64
    present: npt.NDArray[np.bool_]  # [patient, k]: tau_k is one of the patient's scores
    meta: dict[str, Any] = field(default_factory=dict)


def patient_curves(
    recs: Sequence[EvalRecording], model: str, strict: bool, rules: EventRules
) -> PatientCurves:
    steps = {r.recording_key: recording_steps(r, model, rules) for r in recs}
    scores_all = [st.distinct_desc for st in steps.values() if len(st.distinct_desc)]
    grid = np.unique(np.concatenate(scores_all))[::-1] if scores_all else np.zeros(0)
    tau = np.concatenate([[np.inf], grid])
    patients = tuple(sorted({r.patient_key for r in recs}))
    pidx = {p: i for i, p in enumerate(patients)}
    P, K = len(patients), len(tau)
    fa = np.zeros((P, K), dtype=np.int64)
    tr = np.zeros((P, K), dtype=np.int64)
    un = np.zeros((P, K), dtype=np.int64)
    hits = np.zeros((P, K), dtype=np.int64)
    days = np.zeros(P)
    n_ep = np.zeros(P, dtype=np.int64)
    n_warn = np.zeros(P, dtype=np.int64)
    present = np.zeros((P, K), dtype=bool)
    present[:, 0] = True  # sentinel
    for r in recs:
        i = pidx[r.patient_key]
        st = steps[r.recording_key]
        j = level(st.distinct_desc, tau, strict)
        fa[i] += st.false[j]
        tr[i] += st.true[j]
        un[i] += st.unknown[j]
        hs = hit_scores(r, model, rules)
        for h in hs[~np.isnan(hs)]:
            hits[i] += _passes_tau(float(h), tau, strict)
        days[i] += r.days
        n_ep[i] += len(r.onsets)
        n_warn[i] += int(r.warnable.sum())
        present[i, 1:] |= np.isin(tau[1:], st.distinct_desc)
    return PatientCurves(
        model, strict, patients, tau, fa, tr, un, hits, days, n_ep, n_warn, present
    )


def _columns(pc: PatientCurves, keep: npt.NDArray[np.bool_]) -> PatientCurves:
    return PatientCurves(
        pc.model,
        pc.strict,
        pc.patients,
        pc.tau[keep],
        pc.fa[:, keep],
        pc.true[:, keep],
        pc.unknown[:, keep],
        pc.hits[:, keep],
        pc.days,
        pc.n_episodes,
        pc.n_warnable,
        pc.present[:, keep],
        pc.meta,
    )


def _passes_tau(h: float, tau: F64, strict: bool) -> npt.NDArray[np.bool_]:
    out: npt.NDArray[np.bool_] = (h > tau) if strict else (h >= tau)
    return out


# ---------------------------------------------------------------- curve, sens@B, area, tau
@dataclass(frozen=True)
class Curve:
    tau: F64
    fa_per_day: F64
    sensitivity: F64
    notif_per_day: F64  # TRUE + FALSE + UNKNOWN per day (WATCH rule, §3.6)
    days: float
    n_episodes: float

    @property
    def non_monotone_steps(self) -> int:
        """Grid steps at which FA/day decreases (reported with every curve, §3.3)."""
        return int(np.sum(np.diff(self.fa_per_day) < 0))


def curve(pc: PatientCurves, weights: F64 | None = None) -> Curve:
    """The curve of the (weighted) sample on ITS OWN grid (§3.4): the sentinel plus the distinct
    scores of the patients with weight > 0. Pooled-grid columns that are no drawn patient's score
    are dropped, so first-crossing values, thresholds, flags and areas equal those of the
    resample's own grid exactly, for both comparators (Hypothesis test against an explicit
    resample). S5 review finding: without this, a strict-comparator resample gained a lenient
    point its own grid lacks."""
    w = np.ones(len(pc.patients)) if weights is None else np.asarray(weights, dtype=np.float64)
    keep: npt.NDArray[np.bool_] = np.asarray(pc.present[w > 0].any(axis=0), dtype=bool)
    if not keep.all():
        pc = _columns(pc, keep)
    days = float(w @ pc.days)
    n_ep = float(w @ pc.n_episodes)
    fa = (w @ pc.fa) / days if days > 0 else np.full(len(pc.tau), np.nan)
    tot = (w @ (pc.fa + pc.true + pc.unknown)) / days if days > 0 else np.full(len(pc.tau), np.nan)
    sens = (w @ pc.hits) / n_ep if n_ep > 0 else np.full(len(pc.tau), np.nan)
    return Curve(pc.tau, fa, sens, tot, days, n_ep)


@dataclass(frozen=True)
class BudgetPoint:
    budget: float
    value: float  # sens@B (§3.4)
    a: int  # last grid index before the first crossing
    k_star: int | None  # first index with F > B (None: budget not reached)
    tau_a: float  # threshold at index a (+inf = no alerts)
    f_a: float
    s_a: float
    budget_not_reached: bool
    k_star_is_1: bool


def sens_at_budget(F: F64, S: F64, tau: F64, budget: float) -> BudgetPoint:
    """First-crossing rule (ANALYSIS_PLAN §3.4), exactly as written."""
    over = np.flatnonzero(budget < F)
    if not len(over):
        a = len(F) - 1
        return BudgetPoint(
            budget, float(S[a]), a, None, float(tau[a]), float(F[a]), float(S[a]), True, False
        )
    k = int(over[0])
    if k == 0:  # the sentinel has F = 0 <= B by construction
        raise AssertionError("sentinel point exceeds the budget")
    a = k - 1
    fa, sa = float(F[a]), float(S[a])
    val = sa if fa == budget else sa + (budget - fa) * (float(S[k]) - sa) / (float(F[k]) - fa)
    # 'k* = 1' (§3.4): the strictest ALERTING threshold already exceeds B, i.e. the crossing
    # starts from the no-alert point (0, 0). Comparator-independent (strict grids begin with a
    # (0, 0) point at the top score as well as the sentinel).
    return BudgetPoint(budget, val, a, k, float(tau[a]), fa, sa, False, fa == 0.0 and sa == 0.0)


def partial_area(F: F64, S: F64, lo: float = 0.5, hi: float = 2.0) -> tuple[float, bool]:
    """§3.7: trapezoidal area under S(F) along the first-crossing path, between F = lo and hi,
    normalised by (hi - lo). The path is points 0 .. k* (first F > hi), with the last segment
    cut at F = hi. Segments are clipped to [lo, hi] and integrated with their sign, so a
    non-monotone stretch (cooldown) counts as the path actually runs. For a monotone curve
    this is the ordinary trapezoidal area. Returns (area, hi_reached)."""
    over = np.flatnonzero(hi < F)
    end = int(over[0]) if len(over) else len(F) - 1
    area = 0.0
    for k in range(end):
        f0, f1, s0, s1 = float(F[k]), float(F[k + 1]), float(S[k]), float(S[k + 1])
        if f1 == f0:
            continue
        a_, b_ = max(min(f0, f1), lo), min(max(f0, f1), hi)
        if b_ <= a_:
            continue
        sa = s0 + (a_ - f0) * (s1 - s0) / (f1 - f0)
        sb = s0 + (b_ - f0) * (s1 - s0) / (f1 - f0)
        seg = (b_ - a_) * (sa + sb) / 2.0
        area += seg if f1 > f0 else -seg
    return area / (hi - lo), bool(len(over))


def select_threshold(c: Curve, budget: float, rate: str = "fa") -> BudgetPoint:
    """τA (§3.5): rate 'fa', B = 1.0. τW (§3.6): rate 'notifications', B = 3.0, then
    τW := min(τW, τA) by the caller. Must be applied to DEVELOPMENT predictions only."""
    F = c.fa_per_day if rate == "fa" else c.notif_per_day
    return sens_at_budget(F, c.sensitivity, c.tau, budget)


# ---------------------------------------------------------------- operating point detail
def operating_point(
    recs: Sequence[EvalRecording], model: str, tau: float, strict: bool, rules: EventRules
) -> dict[str, Any]:
    """All Table 20.2 event-level metrics at one threshold, plus per-patient values."""
    n_true = n_false = n_unknown = 0
    leads: list[float] = []
    hits = n_ep = n_warn = 0
    days = 0.0
    readings = insufficient = 0
    abstained = 0
    per_patient: dict[str, dict[str, float]] = {}
    for r in recs:
        s = r.scores[model]
        alert = r.queried & passes(s, tau, strict)
        n = notification_indices(r.ts, alert, rules.cooldown_s)
        c = _classify(r, n, rules)
        rt, rf, ru = int(np.sum(c == TRUE)), int(np.sum(c == FALSE)), int(np.sum(c == UNKNOWN))
        rh = 0
        for k, o in enumerate(r.onsets.tolist()):
            w = episode_window_readings(r, o, rules)
            aw = w[alert[w]]
            if len(aw):
                rh += 1
                leads.append((o - int(r.ts[aw.min()])) / 60.0)
            elif r.warnable[k] and not len(w):
                # warnable (a label-eligible reading exists in the window) but the policy made no
                # forecast at any of them (INSUFFICIENT DATA or causal LOW NOW)
                abstained += 1
        n_true, n_false, n_unknown = n_true + rt, n_false + rf, n_unknown + ru
        hits += rh
        n_ep += len(r.onsets)
        n_warn += int(r.warnable.sum())
        days += r.days
        readings += len(r.ts)
        insufficient += int(np.sum(r.gate_code == 2))
        pp = per_patient.setdefault(
            r.patient_key, {"hits": 0, "episodes": 0, "false": 0, "days": 0.0}
        )
        pp["hits"] += rh
        pp["episodes"] += len(r.onsets)
        pp["false"] += rf
        pp["days"] += r.days
    lead = np.array(leads)
    sens_pp = [v["hits"] / v["episodes"] for v in per_patient.values() if v["episodes"]]
    fa_pp = [v["false"] / v["days"] for v in per_patient.values() if v["days"] > 0]
    return {
        "tau": tau,
        "strict": strict,
        "episodes": n_ep,
        "hits": hits,
        "sensitivity": hits / n_ep if n_ep else math.nan,
        "missed_episode_rate": 1 - hits / n_ep if n_ep else math.nan,
        "warnable_episodes": n_warn,
        "warnable_ceiling": n_warn / n_ep if n_ep else math.nan,
        "notifications": {"true": n_true, "false": n_false, "outcome_unknown": n_unknown},
        "monitored_days": days,
        "fa_per_day": n_false / days if days else math.nan,
        "alert_precision": n_true / (n_true + n_false) if (n_true + n_false) else math.nan,
        "lead_min": {
            "median": float(np.median(lead)) if len(lead) else math.nan,
            "q25": float(np.percentile(lead, 25)) if len(lead) else math.nan,
            "q75": float(np.percentile(lead, 75)) if len(lead) else math.nan,
            "share_ge_30": float(np.mean(lead >= 30)) if len(lead) else math.nan,
        },
        "abstention": {
            "readings": readings,
            "insufficient_data_share": insufficient / readings if readings else math.nan,
            "warnable_episodes_without_forecast_in_window": abstained,
        },
        "per_patient_distribution": {
            "patients": len(per_patient),
            "patients_with_episodes": len(sens_pp),
            "sensitivity_q25_q50_q75": [float(x) for x in np.percentile(sens_pp, [25, 50, 75])]
            if sens_pp
            else None,
            "fa_per_day_q25_q50_q75": [float(x) for x in np.percentile(fa_pp, [25, 50, 75])]
            if fa_pp
            else None,
        },
        "per_patient": per_patient,
    }


# ---------------------------------------------------------------- window-level metrics
def window_metrics(
    y: npt.NDArray[np.int64], p: F64, weights: F64 | None = None
) -> dict[str, float]:
    """Log-loss, Brier and AUPRC over label-eligible prediction times (Table 20.2 S3). Only for
    PROBABILITIES; an uncalibrated score such as M0's must not be passed here."""
    from sklearn.metrics import average_precision_score  # type: ignore[import-untyped]

    if np.any((p < 0) | (p > 1)) or np.any(np.isnan(p)):
        raise ValueError("window metrics need probabilities in [0, 1]")
    w = np.ones(len(y)) if weights is None else np.asarray(weights, dtype=np.float64)
    pc = np.clip(p, 1e-15, 1 - 1e-15)
    ll = -(y * np.log(pc) + (1 - y) * np.log(1 - pc))
    return {
        "log_loss": float(np.sum(w * ll) / np.sum(w)),
        "brier": float(np.sum(w * (p - y) ** 2) / np.sum(w)),
        "auprc": float(average_precision_score(y, p, sample_weight=w)),
        "base_rate": float(np.sum(w * y) / np.sum(w)),
    }


def calibration(y: npt.NDArray[np.int64], p: F64, bins: int = 10) -> dict[str, Any]:
    """Reliability (equal-count bins), ECE (App. E), calibration slope and intercept (logistic
    regression of y on logit p, unpenalised)."""
    from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]

    order = np.argsort(p, kind="stable")
    parts = np.array_split(order, bins)
    rel = [
        {"n": len(b), "mean_p": float(p[b].mean()), "mean_y": float(y[b].mean())}
        for b in parts
        if len(b)
    ]
    ece = sum(r["n"] / len(p) * abs(r["mean_p"] - r["mean_y"]) for r in rel)
    pc = np.clip(p, 1e-6, 1 - 1e-6)
    logit = np.log(pc / (1 - pc)).reshape(-1, 1)
    lr = LogisticRegression(C=np.inf, solver="lbfgs", max_iter=1000).fit(logit, y)  # unpenalised
    return {
        "ece": float(ece),
        "slope": float(lr.coef_[0][0]),
        "intercept": float(lr.intercept_[0]),
        "reliability": rel,
    }
