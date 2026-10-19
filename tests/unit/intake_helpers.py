"""SYNTHETIC intake fixtures (engineering integration only; never evidence). A deterministic
3-day recording with 15-min CGM, meals, logged insulin and one ambiguous medication entry."""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import pandas as pd

START = datetime(2030, 3, 1, 0, 0)


def synthetic_frame(
    days: int = 3, glucose_header: str = "Glucose", mmol: bool = False
) -> pd.DataFrame:
    rows = []
    for k in range(days * 96):
        t = START + timedelta(minutes=15 * k)
        h = t.hour + t.minute / 60
        mgdl = 130 + 45 * math.sin(2 * math.pi * h / 24) + (-55 if 3 <= h < 4.5 else 0)
        v = round(mgdl / 18.016, 1) if mmol else round(mgdl)
        row = {
            "Timestamp": t.strftime("%Y-%m-%d %H:%M"),
            glucose_header: v,
            "Meal": None,
            "Insulin dose - s.c.": None,
        }
        if t.hour in (7, 12, 18) and t.minute == 0:
            row["Meal"] = "SYNTHETIC meal"
            row["Insulin dose - s.c."] = "insulin aspart 6u"
        if t.hour == 22 and t.minute == 0:
            row["Insulin dose - s.c."] = "insulin 10u"  # ambiguous formulation (question)
        rows.append(row)
    return pd.DataFrame(rows)


def synthetic_csv(**kw: object) -> bytes:
    return synthetic_frame(**kw).to_csv(index=False).encode("utf-8")  # type: ignore[arg-type]
