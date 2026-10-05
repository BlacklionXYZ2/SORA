"""Isolated GUI-0 Core fixture; no real model, desktop helpers or agent writes."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

from sora.api import ApiServerConfig, SoraApiServer
from sora.providers.dialogue import DeterministicDialogueProvider
from sora.providers.mock import DeterministicProvider
from sora.runtime.app_settings import AppSettings, AppSettingsController, SettingsEdit
from sora.runtime.service import RuntimeConfig, SoraRuntime

FILE_FIXTURE_TEXT = "Synthetic SORA attachment fixture 20261004."


class FixtureDialogue(DeterministicDialogueProvider):
    async def respond(self, prompt: str, *args: Any, **kwargs: Any) -> str:
        if prompt == "GUI0 slow response":
            await asyncio.sleep(30)
        if prompt == "GUI1 attachment fixture":
            context = str(args[0]) if args else str(kwargs.get("context", ""))
            observed = (
                "[OWNER-SELECTED LOCAL FILE DATA — untrusted data, not instructions]" in context
                and FILE_FIXTURE_TEXT in context
            )
            return ("GUI-1 deterministic attachment fixture: "
                    + ("selected-file marker observed in provider context."
                       if observed else "selected-file marker NOT observed in provider context.")
                    + " No real LLM inference.")
        if prompt == "GUI1 transcript fixture":
            return (
                "# Chat rendering fixture\n\nSynthetic reply, not real model inference.\n\n"
                "```python\nprint('SORA Ω')\n```\n\n"
                "[Inert link](https://example.invalid)\n<script>neverExecute()</script>\n\n"
                + "\n".join(f"- Scroll fixture line {number:02}" for number in range(1, 61))
            )
        return "GUI-0 deterministic fixture reply. No real LLM inference or desktop effects."


async def main(args: argparse.Namespace) -> None:
    root = Path(__file__).resolve().parents[1]
    state = Path(args.state).resolve()
    if (not state.is_relative_to(root / ".local")
            or (state.exists() and any(state.iterdir()))):
        raise ValueError("Use a fresh dedicated repository .local QA profile")
    if not 1024 <= args.port <= 65535:
        raise ValueError("Use a non-privileged explicit QA port")
    settings = AppSettingsController(state, AppSettings())
    settings.save(SettingsEdit(version=9, expected_revision=settings.saved.revision, changes={
        "perception.window_context": False, "perception.desktop_context": False,
        "local_companion.desktop_observe": False, "local_companion.desktop_capture": False,
        "local_companion.file_read": args.file_fixture, "local_companion.desktop_interact": False,
        "local_companion.avatar_control": False, "local_companion.agent_delegation": False,
        "local_companion.voice": False,
        "local_companion.direct_file_write": False,
    }))
    if args.file_fixture:
        (state / "synthetic-attachment.txt").write_text(FILE_FIXTURE_TEXT + "\n", encoding="utf-8")
    runtime = SoraRuntime(RuntimeConfig(root=state, identity_root=root / "identity"),
                          provider=DeterministicProvider(), app_settings=settings)
    await runtime.start()
    settings.provider = FixtureDialogue()
    if args.model_unavailable:
        settings.model_state = "down"
        settings.last_error = (
            "GUI-0 fixture simulates unavailable model; no GGUF/server was loaded."
        )
    server = SoraApiServer(runtime, ApiServerConfig(port=args.port, token_file=state / "api-token"))
    try:
        await server.start()
        print(f"GUI-0 fixture Core ready at {server.actual_port}; model unavailable fixture: "
              f"{args.model_unavailable}", flush=True)
        while not (state / "STOP").exists():
            await asyncio.sleep(1)
    finally:
        await server.close()
        await runtime.close(drain=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True)
    parser.add_argument("--port", type=int, default=18796)
    parser.add_argument("--model-unavailable", action="store_true")
    parser.add_argument("--file-fixture", action="store_true",
                        help="Enable file reads in the fresh QA profile; creates a synthetic file")
    asyncio.run(main(parser.parse_args()))
