"""S6 development dataset on the official copy (TUNING only; aggregate assertions)."""

from __future__ import annotations

import numpy as np
import pytest

from hyposense.evaluation.devdata import load_dev
from hyposense.evaluation.folds import grouped_folds

pytestmark = pytest.mark.requires_data


def test_dev_dataset_alignment_and_pre_registered_pb6_masks() -> None:
    dev = load_dev()
    t = dev.table
    assert len(t) == 33464 and int(t["eligible"].sum()) == 31292
    assert int((t["y"].astype(int) * t["eligible"]).sum()) == 403  # positives (S4 audit)
    assert len(dev.strata) == 30 and len(dev.treated & set(dev.strata)) == 22
    s = dev.pb6_summary
    assert s["eligible_rows_excluded_floor_window"] == 1
    assert s["recordings_excluded_cbg_contradiction"] == 2 and s["affected_patients"] == 2
    folds = grouped_folds(sorted(dev.strata), dev.strata, 5, 2026)
    assert np.bincount(list(folds.values())).tolist() == [6, 6, 6, 6, 6]
