"""Canonical metric registry: ONE definition per metric used by the project.

Sources: ANALYSIS_PLAN §2-3 (approved P-C2/P-C3/P-C6), Blueprint Table 20.2, App. E,
Table 21.1 (G5). Exported to artifacts/evaluation/metric_registry.json (generated, committed,
drift-tested). Each entry names its single implementation. Results artifacts cite the registry
hash, so a definition change is visible.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from hyposense.common.hashing import sha256_json

REGISTRY_VERSION = "1.0.0"


@dataclass(frozen=True)
class MetricDef:
    name: str
    definition: str
    unit: str
    role: str  # primary | headline | secondary | engineering | diagnostic
    applies_to: str  # all models | probabilistic models only
    source: str
    implementation: str
    status: str = "IMPLEMENTED"


EVENT = "L1 episode (ANALYSIS_PLAN §0); H = 60 min; correct warning window [onset-60, onset-15]"

METRICS: tuple[MetricDef, ...] = (
    MetricDef(
        "episode_sensitivity",
        "hit episodes / episodes; an episode is hit iff a label-eligible, policy-queried "
        f"reading in its warning window has state ALERT. {EVENT}",
        "fraction",
        "secondary",
        "all models",
        "ANALYSIS_PLAN §2.3; Table 20.2",
        "evaluation.metrics.operating_point / curve",
    ),
    MetricDef(
        "fa_per_patient_day",
        "FALSE notifications / sum of monitored days (first to last CGM reading per "
        "recording). Notification = ALERT with no notification in the previous 60 min; "
        "FALSE = no onset in (t, t+60] and the record continues >= 60 min",
        "1/day",
        "secondary",
        "all models",
        "ANALYSIS_PLAN §2.4-2.5",
        "evaluation.metrics.operating_point / curve",
    ),
    MetricDef(
        "outcome_unknown_notifications",
        "notifications with no onset in (t, t+60] whose recording ends before t+60; "
        "excluded from TRUE and FALSE, reported separately",
        "count",
        "diagnostic",
        "all models",
        "ANALYSIS_PLAN §2.4",
        "evaluation.metrics.classify_notifications",
    ),
    MetricDef(
        "alert_precision",
        "TRUE / (TRUE + FALSE); OUTCOME-UNKNOWN excluded",
        "fraction",
        "secondary",
        "all models",
        "ANALYSIS_PLAN §2.6",
        "evaluation.metrics.operating_point",
    ),
    MetricDef(
        "operating_curve",
        "(FA/day, sensitivity) at every distinct queried score, strictest first, sentinel "
        "+inf; exact policy replay; non-monotone FA steps counted",
        "curve",
        "headline",
        "all models",
        "ANALYSIS_PLAN §3.2-3.3",
        "evaluation.metrics.patient_curves / curve",
    ),
    MetricDef(
        "sens_at_1fa",
        "first-crossing interpolation at B = 1.0 FA/patient-day (flags budget_not_reached, "
        "k_star_is_1)",
        "fraction",
        "primary",
        "all models",
        "ANALYSIS_PLAN §3.4",
        "evaluation.metrics.sens_at_budget",
    ),
    MetricDef(
        "delta_sens_at_1fa",
        "sens@1FA(A) - sens@1FA(B) on the same patients; paired patient-cluster bootstrap "
        "(B = 2,000, seed 2027, percentile 95 %)",
        "fraction",
        "primary",
        "all models",
        "Blueprint §15, Table 20.1, App. E",
        "evaluation.bootstrap.paired_bootstrap",
    ),
    MetricDef(
        "tau_alert",
        "τA = threshold at the last point before the first crossing of "
        "1.0 FA/day on DEVELOPMENT predictions",
        "score",
        "secondary",
        "all models",
        "ANALYSIS_PLAN §3.5",
        "evaluation.metrics.select_threshold",
    ),
    MetricDef(
        "tau_watch",
        "τW = same rule on the total notification rate (TRUE+FALSE+UNKNOWN) "
        "with B = 3.0; τW := min(τW, τA)",
        "score",
        "secondary",
        "all models",
        "ANALYSIS_PLAN §3.6",
        "evaluation.metrics.select_threshold",
    ),
    MetricDef(
        "partial_area_0.5_2.0",
        "trapezoidal area under S(F) along the first-crossing path, clipped to "
        "[0.5, 2.0] FA/day (signed over non-monotone stretches), normalised by 1.5",
        "fraction",
        "secondary",
        "all models",
        "ANALYSIS_PLAN §3.7",
        "evaluation.metrics.partial_area",
    ),
    MetricDef(
        "lead_time",
        "onset - earliest ALERT in the warning window (hit episodes): median, IQR, share >= 30 min",
        "min",
        "secondary",
        "all models",
        "Table 20.2; §2.3",
        "evaluation.metrics.operating_point",
    ),
    MetricDef(
        "missed_episode_rate",
        "1 - episode sensitivity; reported with the warnable ceiling",
        "fraction",
        "secondary",
        "all models",
        "Table 20.2",
        "evaluation.metrics.operating_point",
    ),
    MetricDef(
        "warnable_ceiling",
        "share of episodes with a label-eligible time in "
        "[onset-60, onset-15] (S2 definition, labels.eligibility.warnable_onsets)",
        "fraction",
        "secondary",
        "all models",
        "ANALYSIS_PLAN §0.8",
        "labels.eligibility.warnable_onsets",
    ),
    MetricDef(
        "per_patient_distribution",
        "per-patient sensitivity and FA/day (quartiles; forest "
        "plot input). Development data only before freeze",
        "fraction, 1/day",
        "secondary",
        "all models",
        "Table 20.2",
        "evaluation.metrics.operating_point",
    ),
    MetricDef(
        "abstention_coverage",
        "share of CGM readings in INSUFFICIENT DATA; warnable "
        "episodes with no forecast at any label-eligible window reading",
        "fraction, count",
        "secondary",
        "all models",
        "Table 20.2 (operationalised)",
        "evaluation.metrics.operating_point",
    ),
    MetricDef(
        "log_loss",
        "mean -[y log p + (1-y) log(1-p)] over label-eligible times (p clipped 1e-15)",
        "nats",
        "secondary",
        "probabilistic models only",
        "Table 20.2 (S3)",
        "evaluation.metrics.window_metrics",
    ),
    MetricDef(
        "brier",
        "mean (p - y)^2 over label-eligible times",
        "-",
        "secondary",
        "probabilistic models only",
        "Table 20.2",
        "evaluation.metrics.window_metrics",
    ),
    MetricDef(
        "auprc",
        "average precision over label-eligible times",
        "-",
        "secondary",
        "probabilistic models only",
        "Table 20.2",
        "evaluation.metrics.window_metrics",
    ),
    MetricDef(
        "ece",
        "sum over 10 equal-count bins of n_b/N |mean p - mean y|",
        "-",
        "secondary",
        "probabilistic models only",
        "App. E",
        "evaluation.metrics.calibration",
    ),
    MetricDef(
        "calibration_slope_intercept",
        "logistic regression of y on logit(p), unpenalised",
        "-",
        "secondary",
        "probabilistic models only",
        "Table 20.2; §11.1",
        "evaluation.metrics.calibration",
    ),
    MetricDef(
        "bootstrap_undefined_resamples",
        "resamples in which a statistic is undefined "
        "(no episodes); G5 requires episodes in every resample",
        "count",
        "diagnostic",
        "all models",
        "Table 21.1 G5",
        "evaluation.bootstrap.paired_bootstrap",
    ),
)


def registry_document() -> dict[str, Any]:
    return {"version": REGISTRY_VERSION, "metrics": [asdict(m) for m in METRICS]}


def registry_sha256() -> str:
    return sha256_json(registry_document())
