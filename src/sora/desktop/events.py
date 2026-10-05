"""Windows WinEvent subscription for content-free P13.1 desktop events."""

from __future__ import annotations

import os
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from sora.contracts.desktop_events import DesktopEvent, DesktopEventKind


class DesktopEventSource(Protocol):
    def start(
        self,
        callback: Callable[[DesktopEvent], None],
        *,
        device_id: str,
        topology_revision: Callable[[], int],
    ) -> None: ...

    def stop(self) -> None: ...


class WindowsDesktopEventSource:
    """Subscribe with WinEventHook; never reads titles, text, pixels, or UIA contents."""

    EVENT_SYSTEM_FOREGROUND = 0x0003
    EVENT_SYSTEM_DIALOGSTART = 0x0010
    EVENT_SYSTEM_DIALOGEND = 0x0011
    EVENT_OBJECT_CREATE = 0x8000
    EVENT_OBJECT_DESTROY = 0x8001
    OBJID_WINDOW = 0
    WINEVENT_OUTOFCONTEXT = 0x0000
    WINEVENT_SKIPOWNPROCESS = 0x0002
    WM_QUIT = 0x0012

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._ready = threading.Event()
        self._startup_error: BaseException | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(
        self,
        callback: Callable[[DesktopEvent], None],
        *,
        device_id: str,
        topology_revision: Callable[[], int],
    ) -> None:
        del device_id  # Scope is supplied by Core, never trusted from a native callback.
        if os.name != "nt":
            raise RuntimeError("Windows desktop events are available only on Windows")
        if self.running:
            raise RuntimeError("Windows desktop event subscription is already running")
        self._ready.clear()
        self._startup_error = None
        self._thread = threading.Thread(
            target=self._run,
            args=(callback, topology_revision),
            name="sora-windows-events",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout=5):
            raise RuntimeError("Windows desktop event subscription did not start")
        if self._startup_error is not None:
            error = self._startup_error
            self.stop()
            raise RuntimeError("Windows desktop event subscription failed") from error

    def stop(self) -> None:
        thread = self._thread
        thread_id = self._thread_id
        if thread is None:
            return
        if thread_id is not None and os.name == "nt":
            import ctypes

            ctypes.windll.user32.PostThreadMessageW(thread_id, self.WM_QUIT, 0, 0)
        thread.join(timeout=5)
        if thread.is_alive():
            raise RuntimeError("Windows desktop event subscription did not stop")
        self._thread = None
        self._thread_id = None

    def _run(
        self,
        callback: Callable[[DesktopEvent], None],
        topology_revision: Callable[[], int],
    ) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        callback_type = ctypes.WINFUNCTYPE(
            None,
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.HWND,
            wintypes.LONG,
            wintypes.LONG,
            wintypes.DWORD,
            wintypes.DWORD,
        )

        def receive(
            _hook: int,
            native_event: int,
            hwnd: int,
            object_id: int,
            child_id: int,
            _thread_id: int,
            _event_time: int,
        ) -> None:
            if native_event in {self.EVENT_OBJECT_CREATE, self.EVENT_OBJECT_DESTROY} and (
                object_id != self.OBJID_WINDOW or child_id != 0
            ):
                return
            revision = topology_revision()
            if revision < 1:
                return
            kind = {
                self.EVENT_SYSTEM_FOREGROUND: DesktopEventKind.FOREGROUND_CHANGED,
                self.EVENT_SYSTEM_DIALOGSTART: DesktopEventKind.DIALOG_OPENED,
                self.EVENT_SYSTEM_DIALOGEND: DesktopEventKind.DIALOG_CLOSED,
                self.EVENT_OBJECT_CREATE: DesktopEventKind.WINDOW_OPENED,
                self.EVENT_OBJECT_DESTROY: DesktopEventKind.WINDOW_CLOSED,
            }.get(native_event)
            if kind is None or (kind is not DesktopEventKind.FOREGROUND_CHANGED and not hwnd):
                return
            process_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
            callback(
                DesktopEvent(
                    event_id=f"desktop-event-{uuid.uuid4()}",
                    kind=kind,
                    occurred_at=datetime.now(UTC),
                    topology_revision=revision,
                    process_id=process_id.value or None,
                    window_handle=int(hwnd or 0),
                )
            )

        native_callback = callback_type(receive)
        hooks: list[int] = []
        flags = self.WINEVENT_OUTOFCONTEXT | self.WINEVENT_SKIPOWNPROCESS
        try:
            self._thread_id = int(kernel32.GetCurrentThreadId())
            for first, last in (
                (self.EVENT_SYSTEM_FOREGROUND, self.EVENT_SYSTEM_FOREGROUND),
                (self.EVENT_SYSTEM_DIALOGSTART, self.EVENT_SYSTEM_DIALOGEND),
                (self.EVENT_OBJECT_CREATE, self.EVENT_OBJECT_DESTROY),
            ):
                hook = user32.SetWinEventHook(first, last, 0, native_callback, 0, 0, flags)
                if not hook:
                    raise OSError(ctypes.get_last_error(), "SetWinEventHook failed")
                hooks.append(hook)
            self._ready.set()
            message = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(message), 0, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        except BaseException as exc:
            self._startup_error = exc
            self._ready.set()
        finally:
            for hook in hooks:
                user32.UnhookWinEvent(hook)
