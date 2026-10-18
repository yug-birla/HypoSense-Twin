"""Raw medication-timing representation for M3r (Blueprint Table 11.1, App. D group 7). CAUSAL.

M3r gives the learner the same logged medication information as M3, but without any
pharmacological kernel. It is the representation check C2b (M3 vs M3r). Categories:

- insulin_bolus: rapid, regular and premixed insulin injections and CSII boluses (meal-linked)
- insulin_basal: basal analogue and NPH injections
- su: sulfonylurea administrations
- glinide: glinide administrations

Per category, at time t (events with ts <= t only):
- min_since_last  minutes since the latest administration, capped at 1440. NaN if none ever.
- last_dose       dose of the latest administration (IU or mg). NaN if none or unknown.
- dose_24h        total dose in (t - 24 h, t]. NaN if any dose in the window is unknown (no fake
                  precision).
- n_24h           number of administrations in (t - 24 h, t].

CSII and i.v. state (`csii_active`, `csii_rate_iu_h`, `iv_insulin_recent`) are shared with M3
and come from the exposure engine. A category whose class has QualityState TIMING_UNKNOWN is set
to NaN by the feature builder (S4), using the engine's quality output.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import numpy.typing as npt

from hyposense.medication.events import EventKind, Flag, MedicationEvent, ParseStatus

CATEGORIES = ("insulin_bolus", "insulin_basal", "su", "glinide")
MIN_SINCE_CAP = 1440.0
WINDOW_S = 24 * 3600
_BOLUS_FAMILIES = {"insulin_rapid", "insulin_regular", "insulin_premix"}
_BASAL_FAMILIES = {"insulin_basal", "insulin_intermediate"}


def category(e: MedicationEvent) -> str | None:
    if e.kind is not EventKind.ADMINISTRATION or Flag.ZERO_DOSE in e.flags:
        return None
    if e.parse_status not in (ParseStatus.PARSED, ParseStatus.PARSED_WITH_WARNING) or not e.target:
        return None
    if e.drug_class == "insulin" and e.route in ("sc", "csii"):
        if e.exposure_family in _BOLUS_FAMILIES:
            return "insulin_bolus"
        if e.exposure_family in _BASAL_FAMILIES:
            return "insulin_basal"
    if e.drug_class == "sulfonylurea":
        return "su"
    if e.drug_class == "glinide":
        return "glinide"
    return None


def raw_timing(
    events: Sequence[MedicationEvent], times: npt.NDArray[np.int64]
) -> dict[str, npt.NDArray[np.float64]]:
    times = np.asarray(times, dtype=np.int64)
    out: dict[str, npt.NDArray[np.float64]] = {}
    for cat in CATEGORIES:
        evs = sorted((e for e in events if category(e) == cat), key=lambda e: (e.ts, e.source_row))
        ts = np.array([e.ts for e in evs], dtype=np.int64)
        dose = np.array([np.nan if e.dose is None else e.dose for e in evs], dtype=np.float64)
        last = np.searchsorted(ts, times, side="right") - 1  # index of latest event with ts <= t
        first_in_window = np.searchsorted(ts, times - WINDOW_S, side="right")
        has = last >= 0
        li = np.clip(last, 0, None)
        out[f"{cat}_min_since_last"] = np.where(
            has, np.minimum((times - ts[li]) / 60.0 if len(ts) else 0.0, MIN_SINCE_CAP), np.nan
        )
        out[f"{cat}_last_dose"] = np.where(has, dose[li] if len(ts) else np.nan, np.nan)
        n24 = (last + 1) - first_in_window
        out[f"{cat}_n_24h"] = n24.astype(np.float64)
        csum = np.concatenate([[0.0], np.cumsum(np.nan_to_num(dose))])
        nan_c = np.concatenate([[0], np.cumsum(np.isnan(dose))])
        tot = csum[last + 1] - csum[first_in_window]
        any_nan = (nan_c[last + 1] - nan_c[first_in_window]) > 0
        out[f"{cat}_dose_24h"] = np.where(any_nan, np.nan, tot)
    return out
