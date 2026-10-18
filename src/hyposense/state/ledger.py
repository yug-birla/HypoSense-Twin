"""Forecast state and forecast-outcome ledger (Blueprint §9.2: the twin "reconciles each forecast
with what then happened").

DISPLAY / AUDIT ONLY. The feature builder never reads these blocks: `features/` may not import
this module (static test), and two states differing only here give identical snapshots
(`test_features_ignore_ledger`).

A forecast made at t_f is reconciled causally, from the state's own episode tracker:
- outcome 1 as soon as an L1 onset with onset time in (t_f, t_f + H] is confirmed;
- outcome 0 at the first reading after t_f + H if none was confirmed. Any later onset starts
  after t_f + H, so the outcome can no longer change;
- forecasts still pending when the recording ends are OUTCOME-UNKNOWN (ANALYSIS_PLAN §2 item 4).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from hyposense.state.history import AppendLog


@dataclass(frozen=True)
class Forecast:
    ts: int
    level: str  # M0 | M1 | M2 | M3r | M3
    model_version: str
    p: float | None  # None: no probability (INSUFFICIENT DATA, LOW NOW, SYSTEM ERROR)


@dataclass(frozen=True)
class LedgerEntry:
    forecast: Forecast
    outcome: int  # 1: onset in (ts, ts + H]; 0: none
    resolved_ts: int  # reading time at which the outcome became known


@dataclass(frozen=True)
class ForecastState:
    last_forecast: Forecast | None = None
    last_notification_ts: int | None = None  # set by the policy (S7)


@dataclass(frozen=True)
class OutcomeLedger:
    horizon_s: int = 3600
    pending: tuple[Forecast, ...] = ()
    resolved: AppendLog[LedgerEntry] = field(default_factory=AppendLog)

    def add(self, f: Forecast) -> OutcomeLedger:
        return replace(self, pending=(*self.pending, f))

    def reconcile(self, reading_ts: int, new_onset_ts: int | None) -> OutcomeLedger:
        """Called after each CGM reading. `new_onset_ts` is the onset confirmed at this
        reading, if any."""
        if not self.pending:
            return self
        still: list[Forecast] = []
        resolved = self.resolved
        for f in self.pending:
            if new_onset_ts is not None and f.ts < new_onset_ts <= f.ts + self.horizon_s:
                resolved = resolved.append(LedgerEntry(f, 1, reading_ts))
            elif reading_ts > f.ts + self.horizon_s:
                resolved = resolved.append(LedgerEntry(f, 0, reading_ts))
            else:
                still.append(f)
        return replace(self, pending=tuple(still), resolved=resolved)

    def finalize(self, last_reading_ts: int) -> tuple[OutcomeLedger, tuple[Forecast, ...]]:
        """At recording end (ANALYSIS_PLAN §2 item 4). A pending forecast whose window is fully
        observed (last reading >= t_f + H) had no confirmed onset: its outcome is 0. An onset at
        the very last reading cannot be confirmed (it needs the next reading), the same rule as
        the labels. Forecasts whose window is not fully observed come back as OUTCOME-UNKNOWN."""
        resolved = self.resolved
        unknown: list[Forecast] = []
        for f in self.pending:
            if last_reading_ts >= f.ts + self.horizon_s:
                resolved = resolved.append(LedgerEntry(f, 0, last_reading_ts))
            else:
                unknown.append(f)
        return replace(self, pending=(), resolved=resolved), tuple(unknown)
