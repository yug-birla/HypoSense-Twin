"""S6 development dataset (OFFLINE; TUNING partition only; DEC-2026-10-18-G).

Joins the v1.0.1 tuning feature table (one row per CGM reading) with:
- labels (S2): eligible, y = an L1 onset in (t, t + 60 min];
- the S5 evaluation inputs (policy gate, M0 scores, onsets);
- P-B6 training-exclusion masks (pre-registered):
  - (i) eligible rows whose label window (t, t + 60] overlaps a sensor-floor run;
  - (ii) all rows of recordings with >= 5 CGM < 70 readings paired to a CBG (+/- 8 min), all of
    those CBG >= 70.

  These masks change TRAINING only, never labels or evaluation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from hyposense.common.config import REPO_ROOT, load_config
from hyposense.data.dataset import AccessScope, load_dataset
from hyposense.data.loader import cgm_series
from hyposense.evaluation.data import EvalRecording
from hyposense.evaluation.m0_run import eval_recordings, treated_patient_keys
from hyposense.features.spec import UNION_NAMES, spec_sha256
from hyposense.labels.annotations import floor_runs
from hyposense.labels.validity import cbg_series, pair_cbg_cgm

FEATURES_DIR = REPO_ROOT / "data" / "processed" / "features"
CBG_PAIR_S = 8 * 60
CONTRADICTION_MIN_PAIRS = 5


@dataclass(frozen=True)
class DevData:
    table: pd.DataFrame  # ids, eligible, y, treated, pb6_exclude, then UNION features
    recs: list[EvalRecording]  # aligned with the table, sorted by recording_key
    offsets: dict[str, tuple[int, int]]  # recording_key -> [start, end) rows in the table
    strata: dict[str, int]  # patient -> treated * 2 + has_L1
    treated: set[str]
    provenance: dict[str, Any]
    pb6_summary: dict[str, Any]


def _y(ts: npt.NDArray[np.int64], onsets: npt.NDArray[np.int64], h: int) -> npt.NDArray[np.int8]:
    j = np.searchsorted(onsets, ts, side="right")
    ok = j < len(onsets)
    y = np.zeros(len(ts), dtype=np.int8)
    y[ok] = (onsets[j[ok]] <= ts[ok] + h).astype(np.int8)
    return y


def load_dev() -> DevData:
    cfg = load_config()
    spec = spec_sha256(cfg["features"])
    vdir = FEATURES_DIR / f"v{cfg['features']['spec_version']}"
    prov = json.loads((vdir / "tuning_features.provenance.json").read_text(encoding="utf-8"))
    if prov["feature_spec_sha256"] != spec:
        raise RuntimeError("tuning feature table was built with another feature spec; rebuild it")
    df = pd.read_parquet(vdir / "tuning_features.parquet")
    ds = load_dataset(AccessScope.TUNING_ONLY)
    recs = eval_recordings(ds.recordings, ds.summary)
    by_key = {r.identity.recording_key: r for r in ds.recordings}
    h = int(cfg["event"]["horizon_min"]) * 60
    treated = treated_patient_keys()
    parts = []
    offsets: dict[str, tuple[int, int]] = {}
    start = 0
    excl_window = excl_rec = 0
    contradicted: list[str] = []
    for r in recs:
        sub = df[df["recording_key"] == r.recording_key].sort_values("ts")
        if not np.array_equal(sub["ts"].to_numpy(np.int64), r.ts):
            raise AssertionError(f"{r.recording_key}: feature table and labels misaligned")
        y = _y(r.ts, r.onsets, h)
        s = cgm_series(by_key[r.recording_key])
        ex = np.zeros(len(r.ts), dtype=bool)
        for a, b in floor_runs(s.ts, s.value):
            lo, hi = int(s.ts[a]), int(s.ts[b - 1])
            ex |= r.eligible & (r.ts < hi) & (r.ts + h >= lo)  # (t, t+60] overlaps [lo, hi]
        excl_window += int(ex.sum())
        cb, cg = pair_cbg_cgm(cbg_series(by_key[r.recording_key]), s.ts, s.value, CBG_PAIR_S)
        low = cg < 70
        if int(low.sum()) >= CONTRADICTION_MIN_PAIRS and bool(np.all(cb[low] >= 70)):
            ex[:] = True
            excl_rec += 1
            contradicted.append(r.recording_key)
        sub = sub.assign(eligible=r.eligible, y=y, treated=r.patient_key in treated, pb6_exclude=ex)
        parts.append(sub)
        offsets[r.recording_key] = (start, start + len(sub))
        start += len(sub)
    table = pd.concat(parts, ignore_index=True)
    ids = ["patient_key", "recording_key", "ts", "eligible", "y", "treated", "pb6_exclude"]
    table = table[ids + list(UNION_NAMES)]
    has_l1 = {p: False for p in table["patient_key"].unique()}
    for r in recs:
        has_l1[r.patient_key] |= len(r.onsets) > 0
    strata = {p: int(p in treated) * 2 + int(v) for p, v in has_l1.items()}
    affected = sorted(set(table.loc[table["pb6_exclude"], "patient_key"]))
    return DevData(
        table,
        recs,
        offsets,
        strata,
        treated,
        prov,
        {
            "eligible_rows_excluded_floor_window": excl_window,
            "recordings_excluded_cbg_contradiction": excl_rec,
            "contradicted_recordings": len(contradicted),
            "affected_patients": len(affected),
            "affected_patient_keys_private": affected,
            "eligible_rows_excluded_total": int((table["pb6_exclude"] & table["eligible"]).sum()),
        },
    )


def save_inputs(dev: DevData, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dev.table.to_parquet(path, index=False)
