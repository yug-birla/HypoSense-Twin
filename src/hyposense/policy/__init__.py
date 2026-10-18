"""Frozen deterministic decision policy: risk + state + data quality -> ALERT / WATCH / NO ALERT /
LOW NOW / INSUFFICIENT DATA / SYSTEM ERROR, cooldown. Blueprint Section 14, Table 14.1. Never
imports model code.

Status: core rules implemented in S5 (`decide.py`: gate, classify, should_notify), because the
evaluation's policy replay (ANALYSIS_PLAN §2) needs them. Tags, logging, acknowledgements and the
live service: S7.
"""
