"""Deterministic multi-recording replay (ARCHITECTURE §4.10; Blueprint Table 18.1).

Ordering. Every selected recording is replayed on a shared RELATIVE clock: offset 0 is each
recording's first event (recordings come from different calendar dates, so absolute merging
would leave beds idle for months). The merged stream is ordered by
(offset, event-type rank, recording_key, position in the recording's canonical stream), which is
a total order fixed by the data alone. Wall-clock speed only decides how far the clock advances
per tick; it never changes the order.

Seek. `seek(offset)` rebuilds every runner from the recording start and replays up to the
target, so the state after a seek equals the state of an uninterrupted replay (no mutation of
existing state). Each reset starts a new log segment.

Logs. One directory per session segment under logs/replay/: decisions.jsonl (one line per
decision, deterministic content, Blueprint §14.3), acks.jsonl, rejected.jsonl and session.json
(wall-clock metadata only there). The decision-log SHA-256 is the determinism fingerprint
(`test_replay_determinism`).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hyposense.common.hashing import sha256_bytes
from hyposense.replay.runner import DecisionRecord, Pipeline, TwinRunner
from hyposense.state.events import rank
from hyposense.state.stream import RecordingStream

MAX_RECORDINGS = 12  # one ward


@dataclass(frozen=True)
class Emitted:
    """One processed event: which runner, its clock offset, and the decision it produced."""

    index: int  # runner index
    offset: int
    record: DecisionRecord | None


class DecisionLog:
    """Append-only JSONL writer for one session segment."""

    def __init__(self, directory: Path, header: dict[str, Any]) -> None:
        directory.mkdir(parents=True, exist_ok=False)
        self.directory = directory
        (directory / "session.json").write_text(json.dumps(header, indent=1) + "\n", "utf-8")
        self._files = {
            n: (directory / f"{n}.jsonl").open("a", encoding="utf-8", newline="\n")
            for n in ("decisions", "acks", "rejected")
        }

    def write(self, name: str, record: dict[str, Any]) -> None:
        f = self._files[name]
        f.write(json.dumps(record, sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n")
        f.flush()

    def close(self) -> None:
        for f in self._files.values():
            f.close()

    def sha256(self, name: str = "decisions") -> str:
        self._files[name].flush()
        return sha256_bytes((self.directory / f"{name}.jsonl").read_bytes())


class ReplaySession:
    def __init__(
        self, streams: Sequence[RecordingStream], pipe: Pipeline, log: DecisionLog | None = None
    ) -> None:
        if not 1 <= len(streams) <= MAX_RECORDINGS:
            raise ValueError(f"select 1..{MAX_RECORDINGS} recordings")
        keys = [s.identity.recording_key for s in streams]
        if len(set(keys)) != len(keys):
            raise ValueError("a recording may be selected once")
        self.streams = tuple(sorted(streams, key=lambda s: s.identity.recording_key))
        self.pipe = pipe
        self.log = log
        self.start_ts = [s.first_ts if s.first_ts is not None else 0 for s in self.streams]
        order = []
        for i, s in enumerate(self.streams):
            for j, e in enumerate(s.events):
                order.append(
                    (e.ts - self.start_ts[i], int(rank(e)), s.identity.recording_key, j, i)
                )
        order.sort()
        self.order = tuple((o, i, j) for o, _, _, j, i in order)
        self.duration = self.order[-1][0] if self.order else 0
        self._reset_runners()

    def _reset_runners(self) -> None:
        self.runners = [TwinRunner(s, self.pipe) for s in self.streams]
        self.pos = 0
        self.offset = 0

    # ------------------------------------------------------------------ clock
    @property
    def finished(self) -> bool:
        return self.pos >= len(self.order)

    def now(self, index: int) -> int:
        """Absolute data time of runner `index` at the current clock offset."""
        return self.start_ts[index] + self.offset

    def _process_next(self) -> Emitted:
        o, i, j = self.order[self.pos]
        self.pos += 1
        self.offset = max(self.offset, o)
        r = self.runners[i]
        before = len(r.rejected)
        rec = r.feed(j, r.stream.events[j])
        if self.log is not None:
            if rec is not None:
                self.log.write("decisions", rec.log(self.pipe.model))
            for x in r.rejected[before:]:
                self.log.write("rejected", {"recording_key": r.recording_key, **x})
        if self.finished:
            for rr in self.runners:
                rr.finish()
        return Emitted(i, o, rec)

    def step(self, n: int = 1) -> list[Emitted]:
        out = []
        while n > 0 and not self.finished:
            out.append(self._process_next())
            n -= 1
        return out

    def advance_to(self, offset: int) -> list[Emitted]:
        """Process every event with clock offset <= `offset`; the clock then reads `offset`."""
        out = []
        while not self.finished and self.order[self.pos][0] <= offset:
            out.append(self._process_next())
        self.offset = max(self.offset, min(offset, self.duration))
        return out

    def seek(self, offset: int, log: DecisionLog | None) -> None:
        """Deterministic seek: rebuild from the recording start, then replay to `offset` into a
        NEW log segment `log` (the previous segment stays as written)."""
        if not 0 <= offset <= self.duration:
            raise ValueError(f"seek offset must be within [0, {self.duration}]")
        if self.log is not None:
            self.log.close()
        self.log = log
        self._reset_runners()
        self.advance_to(offset)
