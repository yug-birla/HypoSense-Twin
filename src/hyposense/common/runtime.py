"""Process-level runtime settings for long CPU-bound offline jobs (audits).

Windows 11 power throttling ("EcoQoS") may schedule console-less background processes on the
efficiency cores only. MEASURED in S4: an audit's 15 workers were confined to the 4 E-cores
(logical CPUs 12-15 at 100 %, the 12 P-core threads idle), so the run took > 2x longer.
`disable_power_throttling()` opts the current process out (SetProcessInformation with
ProcessPowerThrottling, EXECUTION_SPEED control, state off = always high QoS). It is a no-op on
other platforms and never raises; results do not depend on it (scheduling only).
"""

from __future__ import annotations

import ctypes
import os
import sys

_PROCESS_POWER_THROTTLING = 4  # PROCESS_INFORMATION_CLASS.ProcessPowerThrottling
_EXECUTION_SPEED = 0x1


class _ThrottlingState(ctypes.Structure):
    _fields_ = [
        ("Version", ctypes.c_ulong),
        ("ControlMask", ctypes.c_ulong),
        ("StateMask", ctypes.c_ulong),
    ]


def disable_power_throttling() -> bool:
    """Opt this process out of execution-speed throttling. True if the OS accepted it."""
    if sys.platform != "win32":
        return False
    try:
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetCurrentProcess.restype = wintypes.HANDLE  # 64-bit pseudo-handle, not a C int
        k32.SetProcessInformation.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        k32.SetProcessInformation.restype = wintypes.BOOL
        state = _ThrottlingState(1, _EXECUTION_SPEED, 0)
        ok = k32.SetProcessInformation(
            k32.GetCurrentProcess(),
            _PROCESS_POWER_THROTTLING,
            ctypes.byref(state),
            ctypes.sizeof(state),
        )
        return bool(ok)
    except (AttributeError, OSError):
        return False


SINGLE_THREAD_ENV = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
}


def single_threaded_math_env() -> None:
    """Child processes inherit these (read by numpy's BLAS at import): no thread
    oversubscription when many worker processes run side by side."""
    for k, v in SINGLE_THREAD_ENV.items():
        os.environ.setdefault(k, v)
