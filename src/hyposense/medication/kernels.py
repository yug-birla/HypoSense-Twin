"""Population-level exposure kernels (Blueprint §12.2, Eq. 1-6). All times in minutes.

Every kernel is zero before administration (tau < 0), causal, deterministic and vectorised.
- `ExponentialKernel` (insulin; OpenAPS-style activity curve, Eq. 3-4): activity a(tau) in
  fraction-of-dose per minute integrates to 1 over [0, t_dur]. On-board is the closed-form
  remaining fraction (1 at tau = 0, 0 at tau >= t_dur).
- `FlatKernel` (basal analogues): constant activity 1/t_dur on [lag, lag + t_dur), 0 elsewhere.
  On-board is 1 until the lag, then decreases linearly to 0.
- `BatemanKernel` (sulfonylureas, glinides; Eq. 6): one-compartment absorption-elimination shape,
  normalised so its peak (at t_max) equals 1. Truncated to 0 once it falls below `trunc` (1 % of
  peak) after the peak; this bounds the tail and the lookback window.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

Arr = npt.NDArray[np.float64]


@dataclass(frozen=True)
class ExponentialKernel:
    t_peak: float
    t_dur: float
    _tau: float = field(init=False)
    _a: float = field(init=False)
    _s: float = field(init=False)

    def __post_init__(self) -> None:
        if not 0 < self.t_peak < self.t_dur / 2:
            raise ValueError("exponential kernel needs 0 < t_peak < t_dur / 2 (Eq. 3)")
        tau = self.t_peak * (1 - self.t_peak / self.t_dur) / (1 - 2 * self.t_peak / self.t_dur)
        a = 2 * tau / self.t_dur
        s = 1 / (1 - a + (1 + a) * math.exp(-self.t_dur / tau))
        object.__setattr__(self, "_tau", tau)
        object.__setattr__(self, "_a", a)
        object.__setattr__(self, "_s", s)

    @property
    def support(self) -> float:
        return self.t_dur

    def activity(self, t: Arr) -> Arr:
        t = np.asarray(t, dtype=np.float64)
        inside = (t >= 0) & (t <= self.t_dur)
        tc = np.where(inside, t, 0.0)
        val = (self._s / self._tau**2) * tc * (1 - tc / self.t_dur) * np.exp(-tc / self._tau)
        return np.where(inside, np.maximum(val, 0.0), 0.0)

    def on_board(self, t: Arr) -> Arr:
        t = np.asarray(t, dtype=np.float64)
        inside = (t >= 0) & (t < self.t_dur)
        tc = np.where(inside, t, 0.0)
        tau, a, s = self._tau, self._a, self._s
        iob = 1 - s * (1 - a) * (
            (tc**2 / (tau * self.t_dur * (1 - a)) - tc / tau - 1) * np.exp(-tc / tau) + 1
        )
        return np.where(inside, np.clip(iob, 0.0, 1.0), 0.0)


@dataclass(frozen=True)
class FlatKernel:
    lag: float
    t_dur: float

    @property
    def support(self) -> float:
        return self.lag + self.t_dur

    def activity(self, t: Arr) -> Arr:
        t = np.asarray(t, dtype=np.float64)
        return np.where((t >= self.lag) & (t < self.lag + self.t_dur), 1.0 / self.t_dur, 0.0)

    def on_board(self, t: Arr) -> Arr:
        t = np.asarray(t, dtype=np.float64)
        frac = np.clip(1 - (t - self.lag) / self.t_dur, 0.0, 1.0)
        return np.where(t < 0, 0.0, np.where(t < self.lag, 1.0, frac))


@dataclass(frozen=True)
class BatemanKernel:
    t_half: float
    t_max: float
    trunc: float = 0.01
    _ke: float = field(init=False)
    _ka: float = field(init=False)
    _peak: float = field(init=False)
    _support: float = field(init=False)

    def __post_init__(self) -> None:
        ke = math.log(2) / self.t_half
        if not 0 < self.t_max < 1 / ke:
            raise ValueError("Bateman kernel needs 0 < t_max < t_half / ln 2 (k_a > k_e solvable)")
        ka = _solve_ka(ke, self.t_max)
        peak = math.exp(-ke * self.t_max) - math.exp(-ka * self.t_max)
        object.__setattr__(self, "_ke", ke)
        object.__setattr__(self, "_ka", ka)
        object.__setattr__(self, "_peak", peak)
        # first time after the peak at which the normalised curve falls to `trunc`
        lo, hi = self.t_max, self.t_max + 200 * self.t_half
        for _ in range(200):
            mid = (lo + hi) / 2
            if self._raw(mid) / peak > self.trunc:
                lo = mid
            else:
                hi = mid
        object.__setattr__(self, "_support", hi)

    def _raw(self, t: float) -> float:
        return math.exp(-self._ke * t) - math.exp(-self._ka * t)

    @property
    def ka(self) -> float:
        return self._ka

    @property
    def support(self) -> float:
        return self._support

    def activity(self, t: Arr) -> Arr:
        """Normalised exposure (peak = 1); named 'activity' for a uniform kernel interface."""
        t = np.asarray(t, dtype=np.float64)
        inside = (t >= 0) & (t < self._support)
        tc = np.where(inside, t, 0.0)
        val = (np.exp(-self._ke * tc) - np.exp(-self._ka * tc)) / self._peak
        return np.where(inside, np.maximum(val, 0.0), 0.0)


def _solve_ka(ke: float, t_max: float) -> float:
    """k_a > k_e such that ln(k_a/k_e) / (k_a - k_e) = t_max (monotone decreasing in k_a)."""

    def tm(ka: float) -> float:
        return math.log(ka / ke) / (ka - ke)

    lo, hi = ke * (1 + 1e-9), ke * 2.0
    while tm(hi) > t_max:
        hi *= 2.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if tm(mid) > t_max:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


Kernel = ExponentialKernel | FlatKernel | BatemanKernel
