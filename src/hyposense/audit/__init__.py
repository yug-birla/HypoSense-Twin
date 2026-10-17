"""Offline data audit (structural measurements, blueprint reconciliation, evidence gates).

OFFLINE ONLY: never imported by the live path (enforced by tests/leakage/test_import_boundaries.py).
Outputs are aggregate-only (approved P-C5). The per-recording table is restricted to the
structural fields in `structural.PER_RECORDING_FIELDS`, so no glucose values, outcomes or
labels of individual (possibly sealed) patients ever appear.
"""
