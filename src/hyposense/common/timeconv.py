"""Time conversion. Internal time is int64 epoch seconds (UTC); source clocks are local.

ShanghaiT2DM timestamps are naive local times. They are interpreted with a fixed UTC offset
(ASSUMPTION, configs/default.yaml `time.assumed_utc_offset`, default +08:00). China observes no
daylight saving time, so a fixed offset is exact if the assumption (local clock) holds.
"""

from __future__ import annotations

import re

import numpy as np
import numpy.typing as npt

_OFFSET_RE = re.compile(r"^([+-])(\d{2}):(\d{2})$")


def parse_utc_offset(offset: str) -> int:
    """'+08:00' -> 28800 seconds."""
    m = _OFFSET_RE.match(offset)
    if not m:
        raise ValueError(f"invalid UTC offset {offset!r}; expected like '+08:00'")
    sign = 1 if m.group(1) == "+" else -1
    return sign * (int(m.group(2)) * 3600 + int(m.group(3)) * 60)


def local_naive_to_epoch_s(
    local: npt.NDArray[np.datetime64], offset_s: int
) -> npt.NDArray[np.int64]:
    """Naive local datetime64 array -> UTC epoch seconds (exact, no float rounding).

    NaT entries are not allowed here; callers must filter them first.
    """
    secs = local.astype("datetime64[s]").astype(np.int64)
    return secs - np.int64(offset_s)
