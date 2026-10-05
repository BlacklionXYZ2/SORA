"""Cross-process input check, restricted to two explicitly launched fixture processes."""

from __future__ import annotations

import asyncio
import ctypes
import json
from ctypes import wintypes
from pathlib import Path


class Point(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("data", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("extra", ctypes.c_size_t),
    ]


class InputUnion(ctypes.Union):
    _fields_ = [("mouse", MouseInput)]


class Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("value", InputUnion)]


async def probe_input(
    player_pid: int, anchor_x: int, anchor_y: int, root: Path, evidence: Path
) -> tuple[int, int]:
    fixture = root / "clients/input_fixture/bin/Debug/net10.0-windows/input_fixture.exe"
    assert fixture.is_file(), "Build clients/input_fixture before packaged acceptance"
    state_path = evidence / "input-fixture.json"
    state_path.unlink(missing_ok=True)
    child = await asyncio.create_subprocess_exec(
        str(fixture), str(state_path), str(anchor_x - 600), str(anchor_y - 700)
    )
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.WindowFromPoint.argtypes = [Point]
    user.WindowFromPoint.restype = wintypes.HWND
    user.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    user.GetDC.argtypes = [wintypes.HWND]
    user.GetDC.restype = wintypes.HDC
    user.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    previous = Point()
    user.GetCursorPos(ctypes.byref(previous))
    awareness = user.SetThreadDpiAwarenessContext
    awareness.argtypes = [ctypes.c_void_p]
    awareness.restype = ctypes.c_void_p
    prior_awareness = awareness(ctypes.c_void_p(-4))
    last = Point(previous.x, previous.y)
    player_window = 0
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def window_owner(window: int) -> int:
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(ctypes.c_void_p(window), ctypes.byref(pid))
        return int(pid.value)

    def find(window: int, _: int) -> bool:
        nonlocal player_window
        if window_owner(window) == player_pid and user.IsWindowVisible(ctypes.c_void_p(window)):
            player_window = window
        return True

    async def fixture_state() -> dict[str, int]:
        for _ in range(100):
            try:
                value: dict[str, int] = json.loads(state_path.read_text(encoding="utf-8"))
                return value
            except (FileNotFoundError, json.JSONDecodeError):
                await asyncio.sleep(0.05)
        raise AssertionError("Input fixture did not report state")

    async def click(x: int, y: int, expected_pid: int) -> None:
        nonlocal last
        user.SetCursorPos(x, y)
        last = Point(x, y)
        await asyncio.sleep(0.2)  # Give the player's per-frame hit-test time to update.
        window = user.WindowFromPoint(last)
        assert window and window_owner(window) == expected_pid, (
            "Refuse input outside the expected fixture"
        )
        for flag in (0x0002, 0x0004):
            event = Input(0, InputUnion(MouseInput(0, 0, 0, flag, 0, 0)))
            assert user.SendInput(1, ctypes.byref(event), ctypes.sizeof(event)) == 1
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.2)

    async def drag_avatar(start_x: int, start_y: int, end_x: int, end_y: int) -> None:
        nonlocal last
        user.SetCursorPos(start_x, start_y)
        last = Point(start_x, start_y)
        await asyncio.sleep(0.2)
        window = user.WindowFromPoint(last)
        assert window and window_owner(window) == player_pid, (
            "Refuse drag beginning outside the launched Unity fixture"
        )
        down = Input(0, InputUnion(MouseInput(0, 0, 0, 0x0002, 0, 0)))
        assert user.SendInput(1, ctypes.byref(down), ctypes.sizeof(down)) == 1
        for step in range(1, 31):
            x = start_x + (end_x - start_x) * step // 30
            y = start_y + (end_y - start_y) * step // 30
            user.SetCursorPos(x, y)
            last = Point(x, y)
            await asyncio.sleep(0.02)
        up = Input(0, InputUnion(MouseInput(0, 0, 0, 0x0004, 0, 0)))
        assert user.SendInput(1, ctypes.byref(up), ctypes.sizeof(up)) == 1
        await asyncio.sleep(0.5)

    async def find_avatar_point() -> tuple[int, int]:
        candidates = [(anchor_x, anchor_y - 150)]
        candidates.extend(
            (anchor_x + dx, anchor_y - dy)
            for dy in range(60, 281, 20)
            for dx in range(-60, 61, 20)
        )
        for x, y in candidates:
            user.SetCursorPos(x, y)
            await asyncio.sleep(0.04)
            window = user.WindowFromPoint(Point(x, y))
            if window and window_owner(window) == player_pid:
                return x, y
        raise AssertionError("Packaged avatar collider never became an OS input target")

    async def find_fixture_point(state: dict[str, int]) -> tuple[int, int]:
        left = state["x"]
        top = state["y"]
        right = left + state["width"]
        bottom = top + state["height"]
        observed_owners: dict[int, int] = {}
        for y in range(top + 40, bottom - 39, 40):
            for x in range(left + 40, right - 39, 40):
                user.SetCursorPos(x, y)
                await asyncio.sleep(0.04)
                window = user.WindowFromPoint(Point(x, y))
                owner = window_owner(window) if window else 0
                observed_owners[owner] = observed_owners.get(owner, 0) + 1
                if owner == child.pid:
                    return x, y
        raise AssertionError(
            "No click-through point reached the launched input fixture; "
            f"observed window-owner counts={observed_owners}"
        )

    try:
        state = await fixture_state()
        wrapped = callback_type(find)
        user.EnumWindows(wrapped, 0)
        assert player_window
        user.SetWindowPos(player_window, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0013)
        blank_x, blank_y = await find_fixture_point(state)
        await click(blank_x, blank_y, child.pid)
        after_blank = await fixture_state()
        for _ in range(20):
            if after_blank["clicks"] == state["clicks"] + 1:
                break
            await asyncio.sleep(0.05)
            after_blank = await fixture_state()
        blank_click_received = after_blank["clicks"] == state["clicks"] + 1
        # A white fixture pixel is visible through the actual composed native overlay.
        dc = user.GetDC(None)
        gdi = ctypes.WinDLL("gdi32")
        gdi.GetPixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
        gdi.GetPixel.restype = wintypes.DWORD
        try:
            background = int(gdi.GetPixel(dc, blank_x, blank_y))
        finally:
            user.ReleaseDC(None, dc)
        channels = (
            background & 0xFF,
            (background >> 8) & 0xFF,
            (background >> 16) & 0xFF,
        )
        assert min(channels) >= 254, (
            f"Overlay background was not transparently near-white: {background:#x}"
        )
        avatar_x, avatar_y = await find_avatar_point()
        await click(avatar_x, avatar_y, player_pid)
        after_avatar = await fixture_state()
        assert after_avatar["clicks"] == after_blank["clicks"]
        drag_end = (avatar_x + 150, avatar_y - 160)
        await drag_avatar(avatar_x, avatar_y, *drag_end)
        after_drag = await fixture_state()
        assert after_drag["clicks"] == after_avatar["clicks"]
        style = user.GetWindowLongPtrW(player_window, -20)
        assert style & 0x8 and style & 0x80000 and style & 0x08000000
        (evidence / "native-input-acceptance.json").write_text(
            json.dumps(
                {
                    "blank_window_routed_to_fixture": True,
                    "blank_click_point": {"x": blank_x, "y": blank_y},
                    "blank_click_received_by_fixture": blank_click_received,
                    "avatar_click_routed_to_player": True,
                    "avatar_click_not_received_by_fixture": True,
                    "avatar_drag_injected_with_fixture_beneath": True,
                    "avatar_drag_start": {"x": avatar_x, "y": avatar_y},
                    "drag_end": {"x": drag_end[0], "y": drag_end[1]},
                    "vertical_lift_px": 160,
                    "composed_background_rgb": background,
                    "topmost_layered_noactivate": True,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return drag_end
    finally:
        current = Point()
        user.GetCursorPos(ctypes.byref(current))
        if current.x == last.x and current.y == last.y:
            user.SetCursorPos(previous.x, previous.y)
        awareness(prior_awareness)
        if child.returncode is None:
            child.terminate()
            await child.wait()
