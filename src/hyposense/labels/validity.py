"""Label validity: CGM vs capillary (CBG) agreement and CBG confirmation of CGM episodes.

OFFLINE. This module is deliberately separate from the target definition. CBG never changes an
episode. It only annotates episodes (G3b; sensitivity analysis SA5) and measures agreement.
The target stays a **CGM-detected** episode (Blueprint §8.4, N1).

Definitions (Blueprint §8.4; executable spec audit2.py):
- Pair: each CBG value is paired with the nearest CGM reading of the same recording by absolute
  time difference (ties → the earlier CGM reading), if that difference is <= 8 min.
- CBG "during" an episode: a CBG timestamp in [onset_ts, last_ts + 15 min]. The episode is
  CONFIRMED if any such CBG < 70 mg/dL, UNCONFIRMED if CBG values exist but none < 70, and has no
  status (None) if no CBG falls in the window.
- Legacy onset-window status (audit.py, reported for reconciliation only):
  CBG in [onset - 30 min, onset + 60 min].
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from hyposense.data.records import Recording
from hyposense.labels.episodes import Episode


@dataclass(frozen=True)
class CBGSeries:
    ts: npt.NDArray[np.int64]
    value: npt.NDArray[np.float64]


def cbg_series(rec: Recording) -> CBGSeries:
    f = rec.frame
    sel = f["cbg"].notna() & f["ts_valid"]
    return CBGSeries(
        ts=f.loc[sel, "ts"].to_numpy(np.int64), value=f.loc[sel, "cbg"].to_numpy(np.float64)
    )


def pair_cbg_cgm(
    cbg: CBGSeries,
    cgm_ts: npt.NDArray[np.int64],
    cgm_value: npt.NDArray[np.float64],
    window_s: int,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Return (cbg_values, cgm_values) of all pairs within window_s."""
    out_cbg: list[float] = []
    out_cgm: list[float] = []
    if len(cgm_ts) == 0:
        return np.zeros(0), np.zeros(0)
    for t, v in zip(cbg.ts.tolist(), cbg.value.tolist(), strict=True):
        right = int(np.searchsorted(cgm_ts, t, side="left"))
        candidates = [k for k in (right - 1, right) if 0 <= k < len(cgm_ts)]
        best = min(candidates, key=lambda k: (abs(int(cgm_ts[k]) - t), cgm_ts[k]))
        if abs(int(cgm_ts[best]) - t) <= window_s:
            out_cbg.append(v)
            out_cgm.append(float(cgm_value[best]))
    return np.array(out_cbg), np.array(out_cgm)


def episode_cbg_status(ep: Episode, cbg: CBGSeries, tail_s: int, threshold: float) -> bool | None:
    sel = (cbg.ts >= ep.onset_ts) & (cbg.ts <= ep.last_ts + tail_s)
    if not sel.any():
        return None
    return bool(np.any(cbg.value[sel] < threshold))


def episode_cbg_status_onset_window(ep: Episode, cbg: CBGSeries, threshold: float) -> bool | None:
    """Legacy audit.py definition (reconciliation only): CBG in [onset - 30, onset + 60] min."""
    if len(cbg.ts) == 0:
        return None
    sel = (cbg.ts >= ep.onset_ts - 1800) & (cbg.ts <= ep.onset_ts + 3600)
    if not sel.any():
        return None
    return bool(np.any(cbg.value[sel] < threshold))


def agreement_stats(
    cbg: npt.NDArray[np.float64], cgm: npt.NDArray[np.float64], low: float = 70.0
) -> dict[str, Any]:
    if len(cbg) == 0:
        return {"pairs": 0}
    diff = cgm - cbg
    lt100 = cbg < 100
    return {
        "pairs": len(cbg),
        "cgm_minus_cbg_mean": round(float(diff.mean()), 1),
        "cgm_minus_cbg_median": round(float(np.median(diff)), 1),
        "cgm_minus_cbg_sd": round(float(diff.std(ddof=1)), 1) if len(diff) > 1 else None,
        "mard_pct": round(float(np.mean(np.abs(diff) / cbg) * 100), 1),
        "pairs_cbg_lt100": int(lt100.sum()),
        "cgm_minus_cbg_mean_cbg_lt100": round(float(diff[lt100].mean()), 1)
        if lt100.any()
        else None,
        "pairs_cgm_lt70": int((cgm < low).sum()),
        "pairs_cgm_lt70_cbg_lt70": int(((cgm < low) & (cbg < low)).sum()),
        "pairs_cbg_lt70": int((cbg < low).sum()),
        "pairs_cbg_lt70_cgm_lt70": int(((cbg < low) & (cgm < low)).sum()),
    }
