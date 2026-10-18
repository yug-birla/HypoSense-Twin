"""Leakage-safe feature builder: causal FeatureSnapshot per model level (M1, M2, M3r, M3) at a CGM
reading, from the patient state (history <= t). Blueprint 10.2, Appendix D. Single
implementation shared by offline training-table generation and live replay (ADR-004).
Specification: features/spec.py -> artifacts/features/feature_spec.json. Implemented in S4.
"""
