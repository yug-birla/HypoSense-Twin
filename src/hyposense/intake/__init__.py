"""New-data intake (product extension, not research data).

Uploaded or manually entered observations are validated, clarified through deterministic
questions and passed through the SAME canonical modules as the historical data:
`data.loader.parse_recording_frame` → `state.stream.recording_stream` → Patient State Engine →
causal features → model → calibration → policy. Nothing here trains, calibrates, tunes or
selects. Intake data lives in server memory only, is never merged into the T / E partitions and
is never committed.
"""
