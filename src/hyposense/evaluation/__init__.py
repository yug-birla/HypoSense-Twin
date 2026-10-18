"""Evaluation harness (OFFLINE): model-agnostic policy-replay accounting, episode and window
metrics, exact operating curves, first-crossing sens@B, threshold selection, paired
patient-cluster bootstrap, metric registry, provenance-stamped results. Blueprint Sections 15,
19-20, App. E; ANALYSIS_PLAN §2-3.

Status: S5 IMPLEMENTED (data, metrics, bootstrap, registry, m0_run). Folds, nested calibration
and the confirmatory runner: S6 / S9.
"""
