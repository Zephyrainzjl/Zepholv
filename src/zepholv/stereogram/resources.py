"""Bounded CPU use. No GPU compute or concurrent Blender jobs are launched."""

from contextlib import contextmanager
import os

from threadpoolctl import threadpool_limits


@contextmanager
def low_impact(threads=2):
    """Temporarily limit numerical thread pools and lower Windows process priority."""
    if not isinstance(threads, int) or threads < 1:
        raise ValueError("threads must be a positive integer")
    previous = None
    kernel = None
    process = None
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.GetPriorityClass.argtypes = [wintypes.HANDLE]
        kernel.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        process = kernel.GetCurrentProcess()
        previous = kernel.GetPriorityClass(process)
        kernel.SetPriorityClass(process, 0x00004000)  # BELOW_NORMAL_PRIORITY_CLASS
    try:
        with threadpool_limits(limits=threads):
            yield
    finally:
        if kernel is not None and previous:
            kernel.SetPriorityClass(process, previous)
