"""Medication Exposure State (Blueprint §12; the M3 representation). CAUSAL.

At time t only events with ts <= t contribute (a dose charted at t is known at t, but every kernel
is 0 or full-on-board at tau = 0 by construction). Exposure of insulin family g (Eq. 1-2):

    activity_g(t) = sum_j dose_j * w_jg * a_k(t - t_j)          [IU/h]
    on_board(t)   = sum_j dose_j * w_jk * (1 - A_k(t - t_j))     [IU]

Premixes split by component weights (dictionary). Secretagogues use (dose_j / D_max) x
peak-normalised Bateman kernels (dimensionless). CSII basal rates become r/4-IU micro-boluses every
15 min from the programmed entry. A rate continues until the next pump entry or suspension, at most
`max_continuation_min` after its entry; beyond that, pump delivery is UNKNOWN (never fabricated).

Projections to t+30 / t+60 use past doses only, plus continuation of the currently programmed CSII
basal rate (P-B3 a-priori decision). They never assume future injections or tablets.

Uncertainty is never turned into fake precision. Per class (insulin / sulfonylurea / glinide) a
`QualityState` is reported, and exposure values of a class whose timing is unknown are NaN.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import numpy as np
import numpy.typing as npt

from hyposense.medication.events import EventKind, Flag, MedicationEvent, ParseStatus
from hyposense.medication.kernels import BatemanKernel, ExponentialKernel, FlatKernel, Kernel

Arr = npt.NDArray[np.float64]
INSULIN_GROUP = {
    "rapid_analogue": "prandial",
    "regular_human": "prandial",
    "intermediate_nph": "intermediate",
    "basal_glargine": "basal",
    "basal_detemir": "basal",
    "basal_degludec": "basal",
}
GROUPS = ("prandial", "intermediate", "basal", "su", "glinide")
CLASSES = ("insulin", "sulfonylurea", "glinide")
PROJECTIONS_MIN = (30, 60)
MIN_SINCE_CAP_MIN = 1440.0


class QualityState(StrEnum):
    KNOWN = "KNOWN"
    PARTIAL = "PARTIAL"  # inferred formulation, unknown pump delivery, or i.v. rate unknown
    TIMING_UNKNOWN = "TIMING_UNKNOWN"  # prescribed, but nothing logged within the lookback window
    DOSE_UNKNOWN = "DOSE_UNKNOWN"
    FORMULATION_UNKNOWN = "FORMULATION_UNKNOWN"
    NO_LOGGED_MEDICATION = "NO_LOGGED_MEDICATION"


@dataclass(frozen=True)
class KernelSet:
    kernels: dict[str, Kernel]
    d_max_mg: dict[str, float]
    microbolus_s: int
    max_continuation_s: int
    project_pump: bool
    iv_window_s: int
    timing_unknown_s: int
    statuses: dict[str, dict[str, str]]  # kernel -> parameter -> status


def _v(spec: Any) -> float:
    return float(spec["value"] if isinstance(spec, dict) else spec)


def load_kernel_set(pharma: dict[str, Any], timing_unknown_h: float) -> KernelSet:
    kernels: dict[str, Kernel] = {}
    d_max: dict[str, float] = {}
    statuses: dict[str, dict[str, str]] = {}
    for group in ("insulin", "secretagogue"):
        for name, k in pharma[group].items():
            statuses[name] = {p: v.get("status", "?") for p, v in k.items() if isinstance(v, dict)}
            if k["family"] == "exponential":
                kernels[name] = ExponentialKernel(_v(k["t_peak_min"]), _v(k["t_dur_min"]))
            elif k["family"] == "flat":
                kernels[name] = FlatKernel(_v(k["lag_min"]), _v(k["t_dur_min"]))
            elif k["family"] == "bateman":
                kernels[name] = BatemanKernel(_v(k["t_half_min"]), _v(k["t_max_min"]))
                d_max[name] = _v(k["d_max_mg"])
            else:
                raise ValueError(f"unknown kernel family {k['family']!r}")
    c = pharma["csii"]
    return KernelSet(
        kernels=kernels,
        d_max_mg=d_max,
        microbolus_s=int(c["basal_microbolus_min"]) * 60,
        max_continuation_s=int(c["max_continuation_min"]) * 60,
        project_pump=bool(c["projection_continues_current_rate"]),
        iv_window_s=int(pharma["iv_insulin"]["flag_window_min"]) * 60,
        timing_unknown_s=int(timing_unknown_h * 3600),
        statuses=statuses,
    )


@dataclass(frozen=True)
class Component:
    ts: int
    amount: float  # IU (insulin) or dose / D_max (secretagogues)
    kernel: str
    group: str


@dataclass(frozen=True)
class PumpSegment:
    start: int
    end: int  # exclusive: next pump entry, or start + max continuation
    rate_iu_h: float
    cap_end: int  # start + max continuation (known at `start`)


@dataclass(frozen=True)
class Uncertain:
    ts: int
    drug_class: str
    state: QualityState
    horizon_s: int  # how long the uncertainty affects exposure


def _exact_dot(m: Arr, w: Arr) -> Arr:
    """Row-wise sum of m * w with math.fsum: correctly rounded and independent of term order and of
    zero (future) terms, so results are bitwise identical for full and truncated records."""
    prod = m * w[None, :]
    return np.array([math.fsum(row) for row in prod.tolist()], dtype=np.float64)


def _parse_kernel_components(spec: str) -> list[tuple[str, float]]:
    out = []
    for part in spec.split(";"):
        name, w = part.split(":")
        out.append((name, float(w)))
    return out


class ExposureEngine:
    """Built from one recording's parsed events. `compute(times)` is causal and vectorised."""

    def __init__(
        self,
        events: Sequence[MedicationEvent],
        ks: KernelSet,
        prescribed: frozenset[str] = frozenset(),
    ) -> None:
        self.ks = ks
        self.prescribed = prescribed
        comps: list[Component] = []
        uncertain: list[Uncertain] = []
        logged: dict[str, list[int]] = {c: [] for c in CLASSES}
        iv_ts: list[int] = []
        pump: list[tuple[int, float | None]] = []  # (ts, rate) ; rate None = suspend
        for e in sorted(events, key=lambda x: (x.ts, x.source_row)):
            ok = e.parse_status in (ParseStatus.PARSED, ParseStatus.PARSED_WITH_WARNING)
            if not (ok and e.target and e.drug_class in CLASSES):
                continue
            if e.kind is EventKind.PUMP_BASAL_RATE:
                pump.append((e.ts, float(e.dose or 0.0)))
                logged["insulin"].append(e.ts)
                continue
            if e.kind is EventKind.PUMP_SUSPEND:
                pump.append((e.ts, None))
                continue
            if e.kind is not EventKind.ADMINISTRATION or Flag.ZERO_DOSE in e.flags:
                continue
            cls = str(e.drug_class)
            logged[cls].append(e.ts)
            if e.route == "iv":
                iv_ts.append(e.ts)
                continue
            if e.dose is None:
                uncertain.append(Uncertain(e.ts, cls, QualityState.DOSE_UNKNOWN, self._support(e)))
                continue
            spec = e.kernel_components or ""
            if spec.startswith("bateman:"):
                name = spec.split(":", 1)[1]
                if name not in ks.kernels:
                    uncertain.append(
                        Uncertain(e.ts, cls, QualityState.FORMULATION_UNKNOWN, self._max_support())
                    )
                    continue
                group = "su" if cls == "sulfonylurea" else "glinide"
                comps.append(Component(e.ts, e.dose / ks.d_max_mg[name], name, group))
                if Flag.FORMULATION_INFERRED in e.flags:
                    uncertain.append(
                        Uncertain(
                            e.ts, cls, QualityState.PARTIAL, int(ks.kernels[name].support * 60)
                        )
                    )
                continue
            for name, w in _parse_kernel_components(spec):
                comps.append(Component(e.ts, e.dose * w, name, INSULIN_GROUP[name]))
        self.components = tuple(comps)
        self.uncertain = tuple(uncertain)
        self.logged = {c: np.array(sorted(v), dtype=np.int64) for c, v in logged.items()}
        self.iv_ts = np.array(sorted(iv_ts), dtype=np.int64)
        self.segments = self._segments(pump)

    def _support(self, e: MedicationEvent) -> int:
        spec = e.kernel_components or ""
        names = (
            [spec.split(":", 1)[1]]
            if spec.startswith("bateman:")
            else [n for n, _ in _parse_kernel_components(spec)]
            if spec
            else []
        )
        sup = [self.ks.kernels[n].support for n in names if n in self.ks.kernels]
        return int(max(sup) * 60) if sup else self._max_support()

    def _max_support(self) -> int:
        return int(max(k.support for k in self.ks.kernels.values()) * 60)

    def _segments(self, pump: list[tuple[int, float | None]]) -> tuple[PumpSegment, ...]:
        segs = []
        for k, (ts, rate) in enumerate(pump):
            if rate is None:
                continue
            cap_end = ts + self.ks.max_continuation_s
            nxt = pump[k + 1][0] if k + 1 < len(pump) else None
            end = min(cap_end, nxt) if nxt is not None else cap_end
            segs.append(PumpSegment(ts, end, rate, cap_end))
        return tuple(segs)

    # ------------------------------------------------------------------ evaluation
    def _pump_components(self, t_max: int) -> list[Component]:
        """Micro-boluses with ts <= t_max (later ones are evaluated as zero by causality)."""
        out = []
        step = self.ks.microbolus_s
        for s in self.segments:
            if s.rate_iu_h <= 0:
                continue
            m = s.start
            while m < s.end and m <= t_max:
                out.append(Component(m, s.rate_iu_h * step / 3600, "regular_human", "prandial"))
                m += step
        return out

    def compute(self, times: npt.NDArray[np.int64]) -> dict[str, Arr]:
        """Exposure features at each t in `times` (any order). Uses only events with ts <= t."""
        times = np.asarray(times, dtype=np.int64)
        n = len(times)
        out: dict[str, Arr] = {}
        comps = list(self.components) + self._pump_components(int(times.max()) if n else 0)
        c_ts = np.array([c.ts for c in comps], dtype=np.int64)
        for g in GROUPS:
            out[f"act_{g}"] = np.zeros(n)
        out["iob_insulin"] = np.zeros(n)
        for h in PROJECTIONS_MIN:
            for g in ("insulin", "su", "glinide"):
                out[f"{g}_p{h}"] = np.zeros(n)
        by_kernel: dict[tuple[str, str], list[int]] = {}
        for idx, c in enumerate(comps):
            by_kernel.setdefault((c.kernel, c.group), []).append(idx)
        for (kname, group), idxs in by_kernel.items():
            kern = self.ks.kernels[kname]
            ts_k = c_ts[idxs]
            amt = np.array([comps[i].amount for i in idxs])
            tau = (times[:, None] - ts_k[None, :]) / 60.0  # minutes; tau < 0 -> future -> 0
            known = tau >= 0
            act = _exact_dot(kern.activity(np.where(known, tau, -1.0)) * known, amt)
            if group in ("su", "glinide"):
                out[f"act_{group}"] += act
            else:
                out[f"act_{group}"] += act * 60.0  # IU/min -> IU/h
                if not isinstance(kern, BatemanKernel):
                    out["iob_insulin"] += _exact_dot(
                        kern.on_board(np.where(known, tau, -1.0)) * known, amt
                    )
            for h in PROJECTIONS_MIN:
                pa = _exact_dot(kern.activity(np.where(known, tau + h, -1.0)) * known, amt)
                key = "insulin" if group not in ("su", "glinide") else group
                out[f"{key}_p{h}"] += pa if key != "insulin" else pa * 60.0
        if self.ks.project_pump:
            self._add_pump_projection(times, out)
        out["act_insulin_total"] = out["act_prandial"] + out["act_intermediate"] + out["act_basal"]
        out.update(self._timing_and_flags(times))
        self._apply_quality(times, out)
        return out

    def _current_segment(self, t: int) -> PumpSegment | None:
        cur = None
        for s in self.segments:
            if s.start <= t:
                cur = s
        if cur is None or t >= cur.cap_end:
            return None
        # a suspension (or newer entry) at or before t ends the segment
        if cur.end <= t:
            return None
        return cur

    def _add_pump_projection(self, times: npt.NDArray[np.int64], out: dict[str, Arr]) -> None:
        kern = self.ks.kernels["regular_human"]
        step = self.ks.microbolus_s
        for i, t in enumerate(times.tolist()):
            seg = self._current_segment(t)
            if seg is None or seg.rate_iu_h <= 0:
                continue
            # next grid point strictly after t
            k0 = (t - seg.start) // step + 1
            for h in PROJECTIONS_MIN:
                horizon = t + h * 60
                m = seg.start + k0 * step
                total = 0.0
                while m <= horizon and m < seg.cap_end:
                    total += float(kern.activity(np.array([(horizon - m) / 60.0]))[0])
                    m += step
                out[f"insulin_p{h}"][i] += total * seg.rate_iu_h * step / 3600 * 60.0

    def _timing_and_flags(self, times: npt.NDArray[np.int64]) -> dict[str, Arr]:
        res: dict[str, Arr] = {}
        for cls, key in (
            ("insulin", "min_since_insulin"),
            ("sulfonylurea", "min_since_su"),
            ("glinide", "min_since_glinide"),
        ):
            arr = self.logged[cls]
            idx = np.searchsorted(arr, times, side="right") - 1
            # capped at 1440 min like Blueprint App. D group 7 (NaN = never logged before t)
            res[key] = (
                np.where(
                    idx >= 0,
                    np.minimum((times - arr[np.clip(idx, 0, None)]) / 60.0, MIN_SINCE_CAP_MIN),
                    np.nan,
                )
                if len(arr)
                else np.full(len(times), np.nan)
            )
        res["csii_active"] = np.array(
            [float(self._current_segment(t) is not None) for t in times.tolist()]
        )
        res["csii_rate_iu_h"] = np.array(
            [(s.rate_iu_h if (s := self._current_segment(t)) else 0.0) for t in times.tolist()]
        )
        iv = self.iv_ts
        res["iv_insulin_recent"] = np.array(
            [
                float(bool(len(iv)) and bool(np.any((iv <= t) & (iv > t - self.ks.iv_window_s))))
                for t in times.tolist()
            ]
        )
        return res

    def quality(self, times: npt.NDArray[np.int64]) -> dict[str, list[QualityState]]:
        out: dict[str, list[QualityState]] = {c: [] for c in CLASSES}
        rank = [QualityState.DOSE_UNKNOWN, QualityState.FORMULATION_UNKNOWN, QualityState.PARTIAL]
        for t in np.asarray(times, dtype=np.int64).tolist():
            for cls in CLASSES:
                arr = self.logged[cls]
                recent = bool(np.any((arr <= t) & (arr > t - self.ks.timing_unknown_s)))
                active_seg = cls == "insulin" and self._current_segment(t) is not None
                if not recent and not active_seg:
                    out[cls].append(
                        QualityState.TIMING_UNKNOWN
                        if cls in self.prescribed
                        else QualityState.NO_LOGGED_MEDICATION
                    )
                    continue
                states = {
                    u.state
                    for u in self.uncertain
                    if u.drug_class == cls and u.ts <= t < u.ts + u.horizon_s
                }
                if cls == "insulin":
                    if len(self.iv_ts) and np.any(
                        (self.iv_ts <= t) & (self.iv_ts > t - self.ks.iv_window_s)
                    ):
                        states.add(QualityState.PARTIAL)
                    last = [s for s in self.segments if s.start <= t]
                    if (
                        last
                        and t >= last[-1].cap_end
                        and t < last[-1].cap_end + 86400
                        and last[-1].end == last[-1].cap_end
                    ):
                        states.add(QualityState.PARTIAL)  # pump delivery after the cap: unknown
                out[cls].append(next((s for s in rank if s in states), QualityState.KNOWN))
        return out

    def _apply_quality(self, times: npt.NDArray[np.int64], out: dict[str, Arr]) -> None:
        q = self.quality(times)
        cols = {
            "insulin": [
                "act_prandial",
                "act_intermediate",
                "act_basal",
                "iob_insulin",
                "insulin_p30",
                "insulin_p60",
            ],
            "sulfonylurea": ["act_su", "su_p30", "su_p60"],
            "glinide": ["act_glinide", "glinide_p30", "glinide_p60"],
        }
        for cls, keys in cols.items():
            unknown = np.array(
                [
                    s
                    in (
                        QualityState.TIMING_UNKNOWN,
                        QualityState.DOSE_UNKNOWN,
                        QualityState.FORMULATION_UNKNOWN,
                    )
                    for s in q[cls]
                ]
            )
            for k in keys:
                out[k] = np.where(unknown, np.nan, out[k])
            out[f"quality_{cls}"] = np.array(
                [list(QualityState).index(s) for s in q[cls]], dtype=np.float64
            )
        out["act_insulin_total"] = out["act_prandial"] + out["act_intermediate"] + out["act_basal"]


__all__ = ["ExposureEngine", "KernelSet", "QualityState", "load_kernel_set"]
