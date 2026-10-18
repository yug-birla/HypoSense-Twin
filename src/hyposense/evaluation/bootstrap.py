"""Paired patient-cluster bootstrap (Blueprint §15, Table 20.1, App. E; configs/default.yaml
`bootstrap`: B = 2,000, seed 2027, unit = patient, percentile 95 % interval).

- **Cluster unit.** The PATIENT is the unit: all recordings, episodes and prediction times of a
  drawn patient travel together. Readings, windows and episodes are never resampled on their own.
- **Multiplicity.** A patient drawn k times contributes k times: weights = draw counts, never
  de-duplicated.
- **Pairing.** One set of draws (fixed by the seed) is shared by every model, and the
  difference A - B is computed on each resample. Two separate intervals are never compared.
- **Every resample** re-applies the full rule: the first-crossing sens@B on the resample's own
  curve (exact, see `metrics` module docstring).
- **G5 diagnostics.** The number of resamples with no episodes (statistic undefined, NaN) is
  reported, never silently dropped.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from hyposense.evaluation.metrics import PatientCurves, curve, partial_area, sens_at_budget

F64 = npt.NDArray[np.float64]
Statistic = Callable[[F64], float]  # patient weights -> value


def draw_weights(n_patients: int, resamples: int, seed: int) -> npt.NDArray[np.int64]:
    """(resamples x patients) draw counts. Each row sums to n_patients."""
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n_patients, size=(resamples, n_patients))
    w = np.zeros((resamples, n_patients), dtype=np.int64)
    for b in range(resamples):
        w[b] = np.bincount(idx[b], minlength=n_patients)
    return w


@dataclass(frozen=True)
class BootstrapResult:
    point: dict[str, float]
    draws: dict[str, F64]
    ci95: dict[str, tuple[float, float]]
    undefined_resamples: dict[str, int]
    resamples: int
    seed: int
    patients: int


def paired_bootstrap(
    stats: Mapping[str, Statistic],
    n_patients: int,
    resamples: int = 2000,
    seed: int = 2027,
    differences: Mapping[str, tuple[str, str]] | None = None,
    patients: tuple[str, ...] | None = None,
) -> BootstrapResult:
    """`stats` map a name to a function of patient weights. `differences` adds
    name -> (A, B): A - B on the same draws. Statistics built from `PatientCurves` carry their
    patient tuple; all of them must index the SAME patients in the same order (pairing)."""
    keyed = {k: getattr(f, "patients", None) for k, f in stats.items()}
    tuples = {v for v in keyed.values() if v is not None} | ({patients} if patients else set())
    if len(tuples) > 1:
        raise ValueError(f"paired statistics index different patient sets: {sorted(keyed)}")
    if tuples and len(next(iter(tuples))) != n_patients:
        raise ValueError("n_patients does not match the statistics' patient set")
    w = draw_weights(n_patients, resamples, seed).astype(np.float64)
    ones = np.ones(n_patients)
    draws = {k: np.array([f(w[b]) for b in range(resamples)]) for k, f in stats.items()}
    point = {k: float(f(ones)) for k, f in stats.items()}
    for name, (a, b) in (differences or {}).items():
        draws[name] = draws[a] - draws[b]
        point[name] = point[a] - point[b]
    ci = {}
    undefined = {}
    for k, v in draws.items():
        ok = v[~np.isnan(v)]
        undefined[k] = int(np.sum(np.isnan(v)))
        ci[k] = (
            (float(np.percentile(ok, 2.5)), float(np.percentile(ok, 97.5)))
            if len(ok)
            else (float("nan"), float("nan"))
        )
    return BootstrapResult(point, draws, ci, undefined, resamples, seed, n_patients)


def sens_at_budget_stat(pc: PatientCurves, budget: float) -> Statistic:
    def f(w: F64) -> float:
        c = curve(pc, w)
        if not c.n_episodes > 0 or not c.days > 0:
            return float("nan")
        return sens_at_budget(c.fa_per_day, c.sensitivity, c.tau, budget).value

    f.patients = pc.patients  # type: ignore[attr-defined]
    return f


def partial_area_stat(pc: PatientCurves, lo: float = 0.5, hi: float = 2.0) -> Statistic:
    def f(w: F64) -> float:
        c = curve(pc, w)
        if not c.n_episodes > 0 or not c.days > 0:
            return float("nan")
        return partial_area(c.fa_per_day, c.sensitivity, lo, hi)[0]

    f.patients = pc.patients  # type: ignore[attr-defined]
    return f


def summary(r: BootstrapResult) -> dict[str, Any]:
    return {
        "method": "paired patient-cluster bootstrap, percentile 95% interval",
        "resamples": r.resamples,
        "seed": r.seed,
        "patients": r.patients,
        "point": r.point,
        "ci95": {k: list(v) for k, v in r.ci95.items()},
        "undefined_resamples": r.undefined_resamples,
    }
