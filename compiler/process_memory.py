"""Windows process working-set queries used only by explicit profiling."""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


def peak_working_set_bytes(process_handle: int) -> int | None:
    """Return a process handle's high-water working set, or None off Windows."""
    if sys.platform != "win32":
        return None
    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    query = psapi.GetProcessMemoryInfo
    query.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessMemoryCounters), wintypes.DWORD]
    query.restype = wintypes.BOOL
    raw_handle = process_handle.value if hasattr(process_handle, "value") else process_handle
    if not query(wintypes.HANDLE(raw_handle), ctypes.byref(counters), counters.cb):
        return None
    return int(counters.PeakWorkingSetSize)


def current_working_set_bytes(process_handle) -> int | None:
    """Return the current working set for an already-open process handle."""
    if sys.platform != "win32":
        return None
    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    query = psapi.GetProcessMemoryInfo
    query.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessMemoryCounters), wintypes.DWORD]
    query.restype = wintypes.BOOL
    raw_handle = process_handle.value if hasattr(process_handle, "value") else process_handle
    if not query(wintypes.HANDLE(raw_handle), ctypes.byref(counters), counters.cb):
        return None
    return int(counters.WorkingSetSize)


def current_process_peak_working_set_bytes() -> int | None:
    """Return this process's high-water working set on Windows."""
    if sys.platform != "win32":
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    return peak_working_set_bytes(kernel32.GetCurrentProcess())


class _ProcessEntry32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


def _process_tree_working_set_bytes(root_pid: int) -> int:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot == wintypes.HANDLE(-1).value:
        return 0
    try:
        entry = _ProcessEntry32W()
        entry.dwSize = ctypes.sizeof(entry)
        first = kernel32.Process32FirstW
        first.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry32W)]
        first.restype = wintypes.BOOL
        next_process = kernel32.Process32NextW
        next_process.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry32W)]
        next_process.restype = wintypes.BOOL
        parents: dict[int, int] = {}
        ok = first(snapshot, ctypes.byref(entry))
        while ok:
            parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            ok = next_process(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(wintypes.HANDLE(snapshot))

    pids = {root_pid}
    while True:
        new = {pid for pid, parent in parents.items() if parent in pids}
        if new <= pids:
            break
        pids.update(new)
    total = 0
    open_process = kernel32.OpenProcess
    open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_process.restype = wintypes.HANDLE
    for pid in pids:
        handle = open_process(0x0400, False, pid)  # PROCESS_QUERY_INFORMATION
        if not handle:
            continue
        try:
            total += current_working_set_bytes(handle) or 0
        finally:
            kernel32.CloseHandle(handle)
    return total


def sample_process_tree_peak_working_set_bytes(process, interval: float = 0.005) -> int | None:
    """Sample a running Windows process tree and return its peak combined set.

    The sampling is intentionally called only for explicit profile runs. A
    short-lived descendant between samples can be missed, so this is a sampled
    high-water estimate rather than a kernel-maintained job-object counter.
    """
    if sys.platform != "win32":
        return None
    peak = 0
    while process.poll() is None:
        peak = max(peak, _process_tree_working_set_bytes(process.pid))
        time.sleep(interval)
    peak = max(peak, _process_tree_working_set_bytes(process.pid))
    return peak or None
