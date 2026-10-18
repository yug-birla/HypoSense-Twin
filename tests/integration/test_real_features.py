"""S4 integration tests on the official copy, TUNING partition only (aggregate assertions).

Fast subset of `hyposense audit features`: three T recordings chosen by structure (the most
medication events, the most sulfonylurea events, the most L1 episodes). The audit run covers
EVERY T recording and EVERY label-eligible time.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from hyposense.common.config import load_config
from hyposense.data.dataset import AccessScope, SealedPartitionError, load_dataset
from hyposense.features.build import build_recording, tuning_streams
from hyposense.features.snapshot import LEVEL_INDEX, FeatureBuilder
from hyposense.features.spec import BY_NAME, LEVELS, UNION_NAMES, Missing
from hyposense.labels.build import label_recording
from hyposense.labels.config import LabelConfig
from hyposense.medication.dictionary import load_dictionary
from hyposense.medication.events import MedicationEvent
from hyposense.state.events import CGMReading
from hyposense.state.patient import EngineConfig, PatientState

pytestmark = pytest.mark.requires_data

CFG, PHARMA = load_config(), load_config("pharma.yaml")
PLAUS = {k: (float(v[0]), float(v[1])) for k, v in CFG["features"]["static_plausible"].items()}


@pytest.fixture(scope="module")
def t_data():  # type: ignore[no-untyped-def]
    ds = load_dataset(AccessScope.TUNING_ONLY)
    streams = tuning_streams(ds, load_dictionary(), PHARMA["formulation_rules"], PLAUS)
    recs = {r.identity.recording_key: r for r in ds.recordings}
    lc = LabelConfig.from_config(CFG)
    labels = {k: label_recording(r, lc) for k, r in recs.items()}

    def n_med(s, drug_class=None):  # type: ignore[no-untyped-def]
        return sum(
            isinstance(e, MedicationEvent)
            and e.is_target_administration
            and (drug_class is None or e.drug_class == drug_class)
            for e in s.events
        )

    chosen = {
        max(streams, key=n_med).identity.recording_key,
        max(streams, key=lambda s: n_med(s, "sulfonylurea")).identity.recording_key,
        max(streams, key=lambda s: len(labels[s.identity.recording_key].l1)).identity.recording_key,
    }
    by_key = {s.identity.recording_key: s for s in streams}
    return ds, streams, recs, labels, sorted(chosen), by_key


ENGINE = EngineConfig.from_config(CFG, PHARMA)
BUILDER = FeatureBuilder(CFG)


def test_feature_generation_refuses_sealed_scope() -> None:
    ds = load_dataset(AccessScope.TUNING_ONLY)
    from dataclasses import replace

    fake = replace(ds, scope=AccessScope.ALL_AFTER_FREEZE)
    with pytest.raises(SealedPartitionError):
        tuning_streams(fake, load_dictionary(), PHARMA["formulation_rules"], PLAUS)


def test_streams_cover_all_tuning_recordings_in_time_order(t_data) -> None:  # type: ignore[no-untyped-def]
    ds, streams, *_ = t_data
    assert len(streams) == len(ds.recordings) == 34
    assert {s.identity.patient_key for s in streams} == {
        r.identity.patient_key for r in ds.recordings
    }
    for s in streams:
        ts = [e.ts for e in s.events]
        assert ts == sorted(ts)


def test_truncation_parity_tracker_and_required_on_real_tuning_recordings(t_data) -> None:  # type: ignore[no-untyped-def]
    ds, _streams, recs, labels, chosen, by_key = t_data
    from hyposense.audit.features import features_at, truncate_recording
    from hyposense.state.stream import recording_stream

    rng = np.random.default_rng(2026)
    k_onsets = UNION_NAMES.index("cgm_prior_l1_onsets")
    required = [i for i, n in enumerate(UNION_NAMES) if BY_NAME[n].missing is Missing.REQUIRED]
    for key in chosen:
        rf = build_recording(by_key[key], ENGINE, BUILDER)
        lab = labels[key]
        assert np.array_equal(rf.ts, lab.series.ts)
        el = np.flatnonzero(lab.prediction.eligible)
        # REQUIRED features are finite at every label-eligible time
        assert np.isfinite(rf.X[np.ix_(el, required)]).all()
        # causal tracker == offline label builder (onset confirmed one reading later)
        onset_idx = np.array([e.onset_index for e in lab.l1])
        for k in range(len(rf.ts)):
            assert rf.X[k, k_onsets] == float(np.sum(onset_idx + 1 <= k))
        # truncation equality at sampled eligible times incl. medication times and episode ends
        dose_ts = [e.ts for e in by_key[key].events if isinstance(e, MedicationEvent)]
        near_dose = np.unique(np.clip(np.searchsorted(rf.ts, dose_ts), 0, len(rf.ts) - 1))
        ends = [e.end_index for e in lab.l1 if e.end_ts is not None]
        special = [i for i in (*near_dose.tolist(), *ends) if lab.prediction.eligible[i]]
        sample = sorted(set(special[:15]) | set(rng.choice(el, min(15, len(el)), replace=False)))
        assert len(sample) >= 15 and len(rf.ts) > 500
        for i in sample:
            row = {str(c): v for c, v in ds.summary.frame.loc[key].items()}
            cut = recording_stream(
                truncate_recording(recs[key], int(rf.ts[i])),
                load_dictionary(),
                PHARMA["formulation_rules"],
                row,
                PLAUS,
            )
            got = features_at(cut, ENGINE, BUILDER)
            assert got.tobytes() == rf.X[i].tobytes(), (key, i)
        # offline vs replay parity on the first 300 readings, every level
        s = PatientState.start(by_key[key].context, ENGINE)
        k = 0
        for e in by_key[key].events:
            s = s.try_update(e)
            assert s.error is None
            if isinstance(e, CGMReading):
                for lvl in LEVELS:
                    snap = BUILDER.snapshot(s, lvl)
                    assert snap.values.tobytes() == rf.X[k, LEVEL_INDEX[lvl]].tobytes()
                k += 1
                if k >= 300:
                    break


def test_static_context_on_tuning(t_data) -> None:  # type: ignore[no-untyped-def]
    _ds, streams, *_ = t_data
    for s in streams:
        assert not math.isnan(s.context.values["age_y"])
        assert all(not math.isnan(v) for v in s.context.regimen.values())
    issues = sorted({i for s in streams for i in s.context.issues})
    assert issues == [
        "c_peptide_fasting_nmol_l: missing",
        "egfr: missing",
        "hba1c_mmol_mol: missing",
    ]


def test_adapter_refuses_sealed_patients_before_freeze(make_workbook, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Defence in depth: even a SYNTHETIC record carrying an E patient's id is refused."""
    from datetime import datetime

    from hyposense.data.loader import load_recording
    from hyposense.data.partition import load_partition
    from hyposense.state.stream import recording_stream
    from tests.conftest import row

    e_pid = sorted(p for p, part in load_partition().items() if part == "E")[0]
    path = make_workbook(
        f"{e_pid}_0_20210301.xlsx",
        [row(datetime(2021, 3, 1, 6, 0), 100.0)],
        sheet_name=f"{e_pid}_0_20210301",
        directory=tmp_path,
    )
    with pytest.raises(SealedPartitionError):
        recording_stream(
            load_recording(path), load_dictionary(), PHARMA["formulation_rules"], None, PLAUS
        )
