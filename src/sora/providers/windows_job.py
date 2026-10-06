"""Named kill-on-close Windows job for one owned delegated writer tree.

The name is persisted before launch. Restart reconciliation queries the kernel job,
not a PID, wall-clock lease or provider's claim that it stopped.
"""

from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from typing import Any


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_int64),
        ("job_time", ctypes.c_int64),
        ("flags", wintypes.DWORD),
        ("minimum", ctypes.c_size_t),
        ("maximum", ctypes.c_size_t),
        ("process_limit", wintypes.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority", wintypes.DWORD),
        ("scheduling", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_uint64)
        for name in (
            "read_ops",
            "write_ops",
            "other_ops",
            "read_bytes",
            "write_bytes",
            "other_bytes",
        )
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", _BasicLimits),
        ("io", _IoCounters),
        ("process_memory", ctypes.c_size_t),
        ("job_memory", ctypes.c_size_t),
        ("peak_process", ctypes.c_size_t),
        ("peak_job", ctypes.c_size_t),
    ]


class _Accounting(ctypes.Structure):
    _fields_ = [
        ("user", ctypes.c_int64),
        ("kernel", ctypes.c_int64),
        ("period_user", ctypes.c_int64),
        ("period_kernel", ctypes.c_int64),
        ("faults", wintypes.DWORD),
        ("total", wintypes.DWORD),
        ("active", wintypes.DWORD),
        ("terminated", wintypes.DWORD),
    ]


def job_name(run_id: str) -> str:
    return "Local\\SORAWriter_" + run_id


def _kernel() -> Any:
    if os.name != "nt":
        raise OSError("Owned writer-tree containment requires Windows")
    library = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "CreateJobObjectW": ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
        "OpenJobObjectW": ([wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
        "OpenProcess": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        "SetInformationJobObject": (
            [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD],
            wintypes.BOOL,
        ),
        "QueryInformationJobObject": (
            [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p],
            wintypes.BOOL,
        ),
        "AssignProcessToJobObject": ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
        "TerminateJobObject": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
        "IsProcessInJob": (
            [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)], wintypes.BOOL,
        ),
        "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
        "WaitForSingleObject": ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
    }
    for name, (args, result) in signatures.items():
        method = getattr(library, name)
        method.argtypes, method.restype = args, result
    return library


def process_may_be_alive(pid: int) -> bool:
    kernel = _kernel()
    handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE, never terminate.
    if not handle:
        return ctypes.get_last_error() != 87  # Unknown/access denied is conservatively live.
    try:
        return bool(kernel.WaitForSingleObject(handle, 0) != 0)
    finally:
        kernel.CloseHandle(handle)


def job_active_processes(name: str) -> int | None:
    """Number of live processes in the named job, 0 if it is gone, None if it cannot be read."""
    kernel = _kernel()
    handle = kernel.OpenJobObjectW(4, False, name)  # JOB_OBJECT_QUERY
    if not handle:
        return 0 if ctypes.get_last_error() == 2 else None
    try:
        accounting = _Accounting()
        if not kernel.QueryInformationJobObject(
            handle, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None
        ):
            return None
        return int(accounting.active)
    finally:
        kernel.CloseHandle(handle)


def writer_job_empty(name: str) -> bool:
    """True only for a missing/empty kernel job; access/query failure stays uncertain."""
    kernel = _kernel()
    handle = kernel.OpenJobObjectW(4, False, name)  # JOB_OBJECT_QUERY
    if not handle:
        if ctypes.get_last_error() == 2:  # ERROR_FILE_NOT_FOUND
            return True
        return False
    try:
        accounting = _Accounting()
        if not kernel.QueryInformationJobObject(
            handle,
            1,
            ctypes.byref(accounting),
            ctypes.sizeof(accounting),
            None,
        ):
            return False
        return bool(accounting.active == 0)
    finally:
        kernel.CloseHandle(handle)


class WindowsWriterJob:
    def __init__(self, name: str):
        self.name = name
        self.kernel = _kernel()
        self.handle = self.kernel.CreateJobObjectW(None, name)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == 183:  # Never take over an existing live job.
            self.kernel.CloseHandle(self.handle)
            self.handle = None
            raise OSError("Writer job already exists")
        limits = _ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway.
        if not self.kernel.SetInformationJobObject(
            self.handle,
            9,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            error = ctypes.get_last_error()
            self.close()
            raise ctypes.WinError(error)

    def attach(self, pid: int) -> None:
        process = self.kernel.OpenProcess(0x0101, False, pid)  # SET_QUOTA | TERMINATE
        if not process:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not self.kernel.AssignProcessToJobObject(self.handle, process):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            self.kernel.CloseHandle(process)

    def close(self) -> None:
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None

    def contains(self, pid: int) -> bool:
        process = self.kernel.OpenProcess(0x1000, False, pid)
        if not process:
            return False
        try:
            member = wintypes.BOOL()
            return bool(self.kernel.IsProcessInJob(process, self.handle, ctypes.byref(member))
                        and member.value)
        finally:
            self.kernel.CloseHandle(process)

    def wait_empty(self, timeout: float = 5) -> bool:
        deadline = time.monotonic() + timeout
        while not writer_job_empty(self.name):
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.02)
        return True

    def stop(self) -> bool:
        """Keep the handle open until the kernel accounts for zero active processes."""
        if not self.handle or not self.kernel.TerminateJobObject(self.handle, 125):
            return False
        return self.wait_empty()
