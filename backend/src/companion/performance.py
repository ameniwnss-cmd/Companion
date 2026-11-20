import ctypes
import logging
import sys

logger = logging.getLogger(__name__)

PROCESS_POWER_THROTTLING = 4
POWER_THROTTLING_VERSION = 1
THROTTLE_EXECUTION_SPEED = 0x1


def disable_power_throttling() -> bool:
    """Keep Windows from moving this background server onto efficiency cores (EcoQoS).

    Without this, speech synthesis on hybrid Intel CPUs slowed down unpredictably by up to 8x.
    """
    if sys.platform != "win32":
        return False

    from ctypes import wintypes

    class PowerThrottlingState(ctypes.Structure):
        _fields_ = [
            ("Version", wintypes.ULONG),
            ("ControlMask", wintypes.ULONG),
            ("StateMask", wintypes.ULONG),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.SetProcessInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.SetProcessInformation.restype = wintypes.BOOL

    state = PowerThrottlingState(POWER_THROTTLING_VERSION, THROTTLE_EXECUTION_SPEED, 0)
    disabled = bool(
        kernel32.SetProcessInformation(
            kernel32.GetCurrentProcess(),
            PROCESS_POWER_THROTTLING,
            ctypes.byref(state),
            ctypes.sizeof(state),
        )
    )
    if not disabled:
        logger.warning("Could not disable power throttling (error %d)", ctypes.get_last_error())
    return disabled
