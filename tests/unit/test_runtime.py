"""Process runtime helpers (Class A; scheduling only, never results)."""

from __future__ import annotations

import os
import sys

from hyposense.common.runtime import (
    SINGLE_THREAD_ENV,
    disable_power_throttling,
    single_threaded_math_env,
)


def test_disable_power_throttling_never_raises_and_is_accepted_on_windows() -> None:
    result = disable_power_throttling()
    assert isinstance(result, bool)
    if sys.platform == "win32":
        assert result  # SetProcessInformation(ProcessPowerThrottling) accepted
    else:
        assert not result


def test_single_threaded_math_env_does_not_override_explicit_settings(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    for k in SINGLE_THREAD_ENV:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("OMP_NUM_THREADS", "4")
    single_threaded_math_env()
    assert os.environ["OMP_NUM_THREADS"] == "4" and os.environ["OPENBLAS_NUM_THREADS"] == "1"
