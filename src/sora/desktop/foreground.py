"""Volatile last-application context, independent of renderer, screenshots and inference."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import PureWindowsPath
from typing import Protocol

# SORA's own windows are never "the application the owner was using". SoraShell.exe hosts the
# native app's Chat and Settings (the default client since 2026-10-06); missing it here made
# image-on-prompt capture SORA's own Chat instead of the owner's window.
COMPANION_PROCESSES = frozenset({"soradesktop.exe", "sorawidget.exe", "sora.exe", "sorashell.exe"})


@dataclass(frozen=True)
class ForegroundIdentity:
    process_id: int
    window_handle: int
    process_started_at: datetime
    process_name: str
    observed_at: datetime


class ForegroundMemory:
    """An observation hint only: never an action target or an authorization."""

    def __init__(self) -> None:
        self.current: ForegroundIdentity | None = None
        self.previous: ForegroundIdentity | None = None

    def clear(self) -> None:
        self.current = self.previous = None

    def accept(self, identity: ForegroundIdentity | None) -> None:
        if identity is None or identity.process_name.casefold() in {"lockapp.exe", "logonui.exe"}:
            self.clear()
            return
        if self.current and identity.observed_at < self.current.observed_at:
            return
        if identity.process_name.casefold() in COMPANION_PROCESSES:
            # The prior application remained foreground until this focus transition.
            if self.current is not None and self.current == self.previous:
                self.previous = replace(self.previous, observed_at=identity.observed_at)
        else:
            self.previous = identity
        self.current = identity

    def recent(self, *, now: datetime | None = None) -> ForegroundIdentity | None:
        value = self.previous
        if value is None:
            return None
        age = ((now or datetime.now(UTC)) - value.observed_at).total_seconds()
        return value if -5 <= age <= 300 else None


class ForegroundSource(Protocol):
    @property
    def running(self) -> bool: ...

    def start(self, callback: Callable[[ForegroundIdentity | None], None]) -> None: ...
    def stop(self) -> None: ...


class WindowsForegroundSource:
    """WinEvent foreground/desktop-switch hooks; no UIA/content capture or effects."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._stopping = threading.Event()
        self._error: BaseException | None = None

    @property
    def running(self) -> bool:
        return (
            self._thread is not None
            and self._thread.is_alive()
            and self._error is None
            and not self._stopping.is_set()
        )

    def start(self, callback: Callable[[ForegroundIdentity | None], None]) -> None:
        if os.name != "nt":
            raise RuntimeError("Foreground context requires Windows")
        if self._thread is not None:
            raise RuntimeError("Foreground watcher already started")
        self._ready.clear()
        self._stopping.clear()
        self._error = None
        self._thread = threading.Thread(
            target=self._run, args=(callback,), daemon=True, name="sora-foreground"
        )
        self._thread.start()
        if not self._ready.wait(5) or self._error is not None:
            self.stop()
            raise RuntimeError("Foreground watcher could not start") from self._error

    def stop(self) -> None:
        self._stopping.set()
        if self._thread is None:
            return
        if self._thread_id and os.name == "nt":
            import ctypes

            ctypes.windll.user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)
        self._thread.join(5)
        if self._thread.is_alive():
            raise RuntimeError("Foreground watcher did not stop")
        self._thread = None
        self._thread_id = 0

    def _run(self, callback: Callable[[ForegroundIdentity | None], None]) -> None:
        import ctypes
        from ctypes import wintypes as w

        user = ctypes.WinDLL("user32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        event_callback = ctypes.WINFUNCTYPE(
            None, w.HANDLE, w.DWORD, w.HWND, w.LONG, w.LONG, w.DWORD, w.DWORD
        )
        user.SetWinEventHook.argtypes = [
            w.DWORD,
            w.DWORD,
            w.HMODULE,
            event_callback,
            w.DWORD,
            w.DWORD,
            w.DWORD,
        ]
        user.SetWinEventHook.restype = w.HANDLE
        user.UnhookWinEvent.argtypes = [w.HANDLE]
        user.GetForegroundWindow.restype = w.HWND
        user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
        user.GetMessageW.argtypes = [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT]
        user.PeekMessageW.argtypes = [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT, w.UINT]
        kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        kernel.OpenProcess.restype = w.HANDLE
        kernel.CloseHandle.argtypes = [w.HANDLE]
        kernel.QueryFullProcessImageNameW.argtypes = [
            w.HANDLE,
            w.DWORD,
            w.LPWSTR,
            ctypes.POINTER(w.DWORD),
        ]
        kernel.GetProcessTimes.argtypes = [w.HANDLE] + [ctypes.POINTER(w.FILETIME)] * 4

        def identity(hwnd: int) -> ForegroundIdentity | None:
            pid = w.DWORD()
            if not hwnd or not user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)):
                return None
            process = kernel.OpenProcess(0x1000, False, pid.value)
            if not process:
                return None
            try:
                name = ctypes.create_unicode_buffer(32768)
                size = w.DWORD(len(name))
                created, exited, system, cpu = (w.FILETIME() for _ in range(4))
                if not kernel.QueryFullProcessImageNameW(process, 0, name, ctypes.byref(size)):
                    return None
                if not kernel.GetProcessTimes(
                    process,
                    ctypes.byref(created),
                    ctypes.byref(exited),
                    ctypes.byref(system),
                    ctypes.byref(cpu),
                ):
                    return None
                ticks = (created.dwHighDateTime << 32) | created.dwLowDateTime
                started = datetime(1601, 1, 1, tzinfo=UTC) + timedelta(microseconds=ticks // 10)
                return ForegroundIdentity(
                    pid.value,
                    int(hwnd),
                    started,
                    PureWindowsPath(name.value).name,
                    datetime.now(UTC),
                )
            finally:
                kernel.CloseHandle(process)

        def receive(
            _hook: int, event: int, hwnd: int, _object: int, _child: int, _thread: int, _time: int
        ) -> None:
            if self._stopping.is_set():
                return
            try:
                # A desktop switch invalidates context even if the secure desktop is unreadable.
                callback(None if event == 0x0020 else identity(hwnd))
            except (OSError, ValueError, OverflowError):
                callback(None)

        handler = event_callback(receive)
        hooks: list[int] = []
        try:
            self._thread_id = kernel.GetCurrentThreadId()
            message = w.MSG()
            user.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)  # Create message queue.
            for event in (0x0003, 0x0020):
                hook = user.SetWinEventHook(event, event, None, handler, 0, 0, 0)
                if not hook:
                    raise OSError(ctypes.get_last_error(), "SetWinEventHook failed")
                hooks.append(hook)
            callback(identity(user.GetForegroundWindow()))
            self._ready.set()
            while (
                not self._stopping.is_set()
                and user.GetMessageW(ctypes.byref(message), None, 0, 0) > 0
            ):
                user.TranslateMessage(ctypes.byref(message))
                user.DispatchMessageW(ctypes.byref(message))
        except BaseException as exc:
            self._error = exc
            self._ready.set()
            callback(None)
        finally:
            for hook in hooks:
                user.UnhookWinEvent(hook)
            callback(None)
