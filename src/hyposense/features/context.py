"""Static context (G5) and meal timing (G6) features (App. D). No carbohydrate estimation and no
nutrition parsing: only meal timing and whether content was recorded (deferred E3)."""

from __future__ import annotations

import math
from collections.abc import Sequence

from hyposense.state.context import REGIMEN_FLAGS, STATIC_FIELDS, PatientContext
from hyposense.state.events import MealEvent


def static_features(ctx: PatientContext) -> dict[str, float]:
    out: dict[str, float] = {}
    for name in STATIC_FIELDS:
        out[name] = ctx.values[name]
    for name in REGIMEN_FLAGS:
        out[name] = ctx.regimen[name]
    for name in STATIC_FIELDS:
        out[f"{name}_missing"] = float(math.isnan(ctx.values[name]))
    out["rx_missing"] = float(any(math.isnan(v) for v in ctx.regimen.values()))
    return out


def meal_features(
    meals: Sequence[MealEvent], t: int, cap_min: float, recent_s: int, utc_offset_s: int
) -> dict[str, float]:
    """`meals` are this recording's meals with ts <= t, in time order."""
    if not meals:
        return {
            "meal_min_since": math.nan,
            "meal_last_3h": 0.0,
            "meals_today": 0.0,
            "meal_last_content_unknown": math.nan,
            "meal_none_logged": 1.0,
        }
    last = meals[-1]
    if last.ts > t:
        raise AssertionError(f"meal at {last.ts} is after t={t}")
    day = (t + utc_offset_s) // 86400
    return {
        "meal_min_since": min((t - last.ts) / 60.0, cap_min),
        "meal_last_3h": float(last.ts > t - recent_s),
        "meals_today": float(sum(1 for m in meals if (m.ts + utc_offset_s) // 86400 == day)),
        "meal_last_content_unknown": float(not last.content_known),
        "meal_none_logged": 0.0,
    }
