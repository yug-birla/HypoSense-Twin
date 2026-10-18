"""Patient-grouped, stratified, deterministic folds (Blueprint §10.3, §15; DEC-2026-10-18-G).

Patients are grouped (all of a patient's recordings in one fold). Within each stratum the
patients are shuffled with a seeded generator and dealt round-robin, continuing the deal across
strata, so fold sizes differ by at most one and every stratum is spread over the folds.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np


def grouped_folds(
    patients: Sequence[str], strata: Mapping[str, int], k: int, seed: int
) -> dict[str, int]:
    if k < 2 or k > len(set(patients)):
        raise ValueError(f"need 2 <= k <= number of patients (k={k}, n={len(set(patients))})")
    rng = np.random.default_rng(seed)
    out: dict[str, int] = {}
    deal = 0
    for s in sorted({strata[p] for p in patients}):
        ids = sorted({p for p in patients if strata[p] == s})
        order = rng.permutation(len(ids))
        for i in order.tolist():
            out[ids[i]] = deal % k
            deal += 1
    return out
