"""Recording-level label construction (OFFLINE only).

Raw data → CGM series → episodes (L1, L2, single-reading) → prediction eligibility and labels.
Each recording is labelled independently: episodes, refractory periods and warm-up never cross
recording boundaries, and the result does not depend on the order recordings are processed in.
"""

from __future__ import annotations

from dataclasses import dataclass

from hyposense.data.loader import cgm_series
from hyposense.data.records import CGMSeries, Recording
from hyposense.labels.config import LabelConfig
from hyposense.labels.eligibility import PredictionLabels, build_prediction_labels
from hyposense.labels.episodes import Episode, build_episodes


@dataclass(frozen=True)
class RecordingLabels:
    recording_key: str
    patient_key: str
    series: CGMSeries
    l1: tuple[Episode, ...]
    l2: tuple[Episode, ...]
    l1_single: tuple[Episode, ...]
    prediction: PredictionLabels


def episodes_for(series: CGMSeries, cfg: LabelConfig) -> dict[str, tuple[Episode, ...]]:
    common = {"max_step_s": cfg.max_step_s, "max_gap_s": cfg.max_gap_s}
    ts, g = series.ts, series.value
    return {
        "L1": build_episodes(
            ts, g, cfg.l1_threshold_mgdl, min_run=cfg.min_run, level="L1", **common
        ),
        "L2": build_episodes(
            ts, g, cfg.l2_threshold_mgdl, min_run=cfg.min_run, level="L2", **common
        ),
        "L1_single": build_episodes(
            ts, g, cfg.l1_threshold_mgdl, min_run=1, level="L1_single", **common
        ),
    }


def label_recording(rec: Recording, cfg: LabelConfig) -> RecordingLabels:
    series = cgm_series(rec)
    eps = episodes_for(series, cfg)
    return RecordingLabels(
        recording_key=rec.identity.recording_key,
        patient_key=rec.identity.patient_key,
        series=series,
        l1=eps["L1"],
        l2=eps["L2"],
        l1_single=eps["L1_single"],
        prediction=build_prediction_labels(series.ts, series.value, eps["L1"], cfg),
    )
