"""One request per child process bounds blocking native UI Automation calls."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from sora.contracts.desktop import DesktopObservation, DesktopObservationRequest


class WindowsObservationBridge:
    def __init__(self, executable: Path, *, timeout: float = 3.0) -> None:
        self.executable = executable.resolve()
        self.timeout = timeout
        self._busy = False

    async def observe(self, request: DesktopObservationRequest) -> DesktopObservation:
        if self._busy:
            return DesktopObservation(status="busy")
        self._busy = True
        process: asyncio.subprocess.Process | None = None
        try:
            async with asyncio.timeout(self.timeout):
                process = await asyncio.create_subprocess_exec(
                    str(self.executable), stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                    limit=512 * 1024,
                    creationflags=0x08000000 if os.name == "nt" else 0,
                    env={k: v for k, v in os.environ.items() if k.upper() in {
                        "SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "DOTNET_ROOT",
                    }},
                )
                assert process.stdin is not None and process.stdout is not None
                process.stdin.write(request.model_dump_json().encode() + b"\n")
                await process.stdin.drain()
                process.stdin.close()
                line = await process.stdout.readline()
                # Any extra output is a protocol violation; never buffer an unbounded stream.
                if await process.stdout.read(1):
                    return DesktopObservation(status="protocol_error")
                await process.wait()
                if process.returncode != 0:
                    return DesktopObservation(status="unavailable")
                result = DesktopObservation.model_validate_json(line)
                if len(result.nodes) > request.max_nodes or any(
                    request.operation != "inventory" and node.process_id != request.process_id
                    for node in result.nodes
                ):
                    return DesktopObservation(status="protocol_error")
                if sum(len(node.text) + len(node.selected_text) for node in result.nodes) > (
                    request.max_text_chars
                ):
                    return DesktopObservation(status="protocol_error")
                return result
        except TimeoutError:
            return DesktopObservation(status="timeout")
        except (ValueError, UnicodeError):
            return DesktopObservation(status="protocol_error")
        except OSError:
            return DesktopObservation(status="unavailable")
        finally:
            if process is not None and process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
            self._busy = False
