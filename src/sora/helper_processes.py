"""Which helper processes this SORA started, so the desktop host can close them all on Quit.

Core, the llama.cpp server, Laya, the avatar and the voice worker each leave one file,
``<state root>/private/helpers/<name>.pid``, holding their process ID. The desktop host reads
these at Quit and stops whichever are still running (checking the program name and start time,
so a reused process ID is never touched). The process tree alone can't find them: Store Python
and the llama.cpp worker break away from their parents on Windows.

Recording is on only when serving for the desktop host (``SORA_STATE_ROOT`` is set), and child
processes inherit it, so the llama.cpp worker records its own server. Recording never fails a
start.
"""

from __future__ import annotations

import os
from pathlib import Path

STATE_ROOT_ENV = "SORA_STATE_ROOT"


def enable(root: Path) -> None:
    """Turn recording on for this process and every child it starts."""
    os.environ[STATE_ROOT_ENV] = str(root.resolve())
    record("core", os.getpid())


def record(name: str, pid: int | None) -> None:
    """``pid`` may be None (a test double without one); nothing is recorded then."""
    root = os.environ.get(STATE_ROOT_ENV)
    if not root or pid is None:
        return
    folder = Path(root) / "private" / "helpers"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{name}.pid").write_text(str(pid), encoding="ascii")
    except OSError:
        pass
