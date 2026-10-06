"""Start agent CLIs so that stopping a run stops every process it started.

On Windows, npm shims (``claude.CMD``, ``codex.CMD``) and launchers start the real agent as a
child. Killing the direct child leaves that agent running, still spending usage and, in a
project folder, still writing after Core has released the folder. Each run therefore gets its
own kill-on-close Windows job. The process is created suspended, assigned to the job and only
then resumed, so every descendant is born inside the job.

A bootstrap child that waits for a go signal is not enough here: under Microsoft Store Python
(the owner's interpreter) the bootstrap runs in a Store job that lets its children silently
break away from every job, so nothing it starts would be contained. Elsewhere the process is
started directly.
"""

from __future__ import annotations

import asyncio
import ctypes
import os
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from sora.providers.windows_job import WindowsWriterJob, job_name, writer_job_empty

_PIPE = asyncio.subprocess.PIPE
_CREATE_SUSPENDED = 0x00000004
_PROCESS_SUSPEND_RESUME = 0x0800


def _resume(pid: int) -> None:
    """Resume a process created suspended (its only thread is the main one)."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    ntdll = ctypes.WinDLL("ntdll")
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    ntdll.NtResumeProcess.argtypes = (ctypes.c_void_p,)
    ntdll.NtResumeProcess.restype = ctypes.c_long
    handle = kernel.OpenProcess(_PROCESS_SUSPEND_RESUME, 0, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        status = ntdll.NtResumeProcess(handle)
        if status != 0:
            raise OSError(f"NtResumeProcess failed with status {status:#x}")
    finally:
        kernel.CloseHandle(handle)


class OwnedProcess:
    """One agent process tree owned by a single SORA run."""

    def __init__(self, process: asyncio.subprocess.Process, job: WindowsWriterJob | None):
        self.process = process
        self.job = job

    @classmethod
    async def start(
        cls,
        command: Sequence[str],
        *,
        run_id: str,
        cwd: str | None,
        stdin: Any = _PIPE,
        stdout: Any = _PIPE,
        stderr: Any = _PIPE,
        env: Mapping[str, str] | None = None,
        limit: int | None = None,
    ) -> OwnedProcess:
        """Start ``command`` (stdin piped by default). Raises OSError if it cannot start."""
        # Fail clearly and early when the agent is not installed.
        if not command or (shutil.which(command[0]) is None and not Path(command[0]).is_file()):
            raise FileNotFoundError(command[0] if command else "(empty command)")
        extra: dict[str, Any] = {} if limit is None else {"limit": limit}
        if env is not None:
            extra["env"] = dict(env)
        if os.name != "nt":
            process = await asyncio.create_subprocess_exec(
                *command, stdin=stdin, stdout=stdout, stderr=stderr, cwd=cwd, **extra
            )
            return cls(process, None)
        job = WindowsWriterJob(job_name(run_id))
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
                cwd=cwd,
                creationflags=_CREATE_SUSPENDED,
                **extra,
            )
        except BaseException:
            job.close()
            raise
        try:
            job.attach(process.pid)
            _resume(process.pid)
        except BaseException:
            if process.returncode is None:
                process.kill()
            await process.wait()
            job.close()
            raise
        return cls(process, job)

    def stopped(self) -> bool:
        """True only when no process of this run can still be running."""
        if self.job is not None:
            return writer_job_empty(self.job.name)
        return self.process.returncode is not None

    async def stop(self) -> bool:
        """Stop the whole tree and wait for it. Returns whether everything stopped."""
        if self.job is not None:
            stopped = await asyncio.to_thread(self.job.stop)
        else:
            if self.process.returncode is None:
                try:
                    self.process.kill()
                except ProcessLookupError:
                    pass
            stopped = True
        await self.process.wait()
        return stopped or self.stopped()

    def close(self) -> None:
        """Release the job and stdin. Kill-on-close ends any process that is somehow left."""
        # Close every pipe now. Otherwise an unread stdout/stdin pipe is only closed when the
        # event loop collects it, which surfaces as an "unclosed transport" ResourceWarning.
        # asyncio has no public API for this; Process._transport has been stable since 3.4.
        transport = getattr(self.process, "_transport", None)
        if transport is not None and not transport.is_closing():
            transport.close()
        elif self.process.stdin is not None and not self.process.stdin.is_closing():
            self.process.stdin.close()
        if self.job is not None:
            self.job.close()
