"""Persistent append-only histories for immutable state snapshots.

A state at reading k sees exactly the first n items of its log. Successive states share one
buffer, so an update costs O(1) amortised rather than a copy of the whole history. A snapshot is
never affected by later appends, because it only ever reads its own prefix. Appending to an older
snapshot (a branch, e.g. "same past, different future" in tests) copies the prefix first, so
branches never interfere.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Generic, TypeVar

import numpy as np
import numpy.typing as npt

T = TypeVar("T")


class _ItemBuf(Generic[T]):
    __slots__ = ("items",)

    def __init__(self, items: list[T]) -> None:
        self.items = items


class AppendLog(Generic[T]):
    """Immutable view of the first `n` items of a shared append-only list."""

    __slots__ = ("_buf", "_n")

    def __init__(self, buf: _ItemBuf[T] | None = None, n: int = 0) -> None:
        self._buf: _ItemBuf[T] = buf if buf is not None else _ItemBuf([])
        self._n = n

    def append(self, item: T) -> AppendLog[T]:
        buf = self._buf
        if self._n != len(buf.items):  # branching from an older snapshot
            buf = _ItemBuf(buf.items[: self._n])
        buf.items.append(item)
        return AppendLog(buf, self._n + 1)

    def __len__(self) -> int:
        return self._n

    def __iter__(self) -> Iterator[T]:
        return iter(self._buf.items[: self._n])

    def last(self) -> T | None:
        return self._buf.items[self._n - 1] if self._n else None

    def items(self) -> tuple[T, ...]:
        return tuple(self._buf.items[: self._n])


class _SeriesBuf:
    __slots__ = ("ts", "used", "val")

    def __init__(self, capacity: int = 256) -> None:
        self.ts = np.zeros(capacity, dtype=np.int64)
        self.val = np.zeros(capacity, dtype=np.float64)
        self.used = 0


class SeriesLog:
    """Immutable view of the first `n` (ts, value) pairs of a shared numeric buffer."""

    __slots__ = ("_buf", "_n")

    def __init__(self, buf: _SeriesBuf | None = None, n: int = 0) -> None:
        self._buf = buf if buf is not None else _SeriesBuf()
        self._n = n

    def append(self, ts: int, value: float) -> SeriesLog:
        buf = self._buf
        if self._n != buf.used:  # branching from an older snapshot
            new = _SeriesBuf(max(256, 2 * self._n))
            new.ts[: self._n] = buf.ts[: self._n]
            new.val[: self._n] = buf.val[: self._n]
            new.used = self._n
            buf = new
        if buf.used == len(buf.ts):
            cap = 2 * len(buf.ts)
            ts_new = np.zeros(cap, dtype=np.int64)
            val_new = np.zeros(cap, dtype=np.float64)
            ts_new[: buf.used] = buf.ts[: buf.used]
            val_new[: buf.used] = buf.val[: buf.used]
            buf.ts, buf.val = ts_new, val_new
        buf.ts[buf.used] = ts
        buf.val[buf.used] = value
        buf.used += 1
        return SeriesLog(buf, self._n + 1)

    def __len__(self) -> int:
        return self._n

    @property
    def ts(self) -> npt.NDArray[np.int64]:
        v = self._buf.ts[: self._n]
        v.flags.writeable = False
        return v

    @property
    def values(self) -> npt.NDArray[np.float64]:
        v = self._buf.val[: self._n]
        v.flags.writeable = False
        return v
