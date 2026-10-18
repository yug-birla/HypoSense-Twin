"""CGM state: the recording's reading history and a CAUSAL L1 episode tracker.

The tracker applies the label protocol's episode rule (ANALYSIS_PLAN §0 items 1-4) incrementally,
with confirmation lag, so it never needs a future reading. The live path must not import
`hyposense.labels` (an import-boundary test enforces this), so the rule is restated here and tied
to the offline builder by a differential test (tests/unit/test_state.py).

- An onset at reading i is CONFIRMED when reading i+1 arrives: both < threshold and at most
  `max_step_s` apart.
- An episode ends RECOVERED at reading j (the first of two non-low readings at most `max_step_s`
  apart), confirmed when reading j+1 arrives. Its end time is t(j).
- An episode ends by GAP at reading j if t(j) - t(j-1) > `max_gap_s`. This is known at j.
- RECORD_END episodes never end inside the recording.

At reading k, the number of confirmed onsets equals the number of offline episodes with
onset_index + 1 <= k, and every confirmed end equals the offline end (same end time and
reason).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from hyposense.state.history import SeriesLog


@dataclass(frozen=True)
class EpisodeRule:
    threshold_mgdl: float = 70.0
    max_step_s: int = 1200
    max_gap_s: int = 1800

    def __post_init__(self) -> None:
        # Recovery and gap ends are mutually exclusive at one reading only if max_step < max_gap.
        if not self.max_step_s < self.max_gap_s:
            raise ValueError("episode rule requires max_step_s < max_gap_s")


@dataclass(frozen=True)
class EpisodeTracker:
    rule: EpisodeRule
    n_onsets: int = 0  # onsets confirmed so far in this recording
    in_episode: bool = False  # an episode is confirmed and not yet ended
    onset_ts: int | None = None  # onset time of the current or most recent episode
    last_end_ts: int | None = None  # end time of the most recently ended episode
    last_end_reason: str | None = None  # "recovered" | "gap"
    prev_ts: int | None = None
    prev_low: bool = False

    def step(self, ts: int, value: float) -> EpisodeTracker:
        r = self.rule
        low = value < r.threshold_mgdl
        if self.prev_ts is None:
            return replace(self, prev_ts=ts, prev_low=low)
        dt = ts - self.prev_ts
        state = self
        if self.in_episode:
            # Recovery confirmed at j = k-1 (only checked from the reading after confirmation;
            # the confirmation reading itself is low, so j = onset + 1 never recovers).
            if not self.prev_low and not low and dt <= r.max_step_s:
                state = replace(
                    state,
                    in_episode=False,
                    last_end_ts=self.prev_ts,
                    last_end_reason="recovered",
                )
            elif dt > r.max_gap_s:
                state = replace(state, in_episode=False, last_end_ts=ts, last_end_reason="gap")
        elif self.prev_low and low and dt <= r.max_step_s:
            state = replace(
                state, in_episode=True, onset_ts=self.prev_ts, n_onsets=self.n_onsets + 1
            )
        # (an end and an onset never happen at the same reading: the onset branch is skipped)
        return replace(state, prev_ts=ts, prev_low=low)


@dataclass(frozen=True)
class CGMState:
    """Readings of the current recording (ts strictly increasing) plus causal episode state."""

    series: SeriesLog
    tracker: EpisodeTracker
    last_low_ts: int | None = None  # latest reading < the L1 threshold

    @classmethod
    def empty(cls, rule: EpisodeRule) -> CGMState:
        return cls(SeriesLog(), EpisodeTracker(rule))

    def add(self, ts: int, value: float) -> CGMState:
        low = value < self.tracker.rule.threshold_mgdl
        return CGMState(
            series=self.series.append(ts, value),
            tracker=self.tracker.step(ts, value),
            last_low_ts=ts if low else self.last_low_ts,
        )

    @property
    def n(self) -> int:
        return len(self.series)
