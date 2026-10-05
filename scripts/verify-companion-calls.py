"""Isolated, clearly labelled offline GUI fixture; no model inference or file authoring.

Only the exact QA request below delegates. Existing owner Core/settings are never touched.
Close gracefully by creating STOP beneath the explicitly selected dedicated .local state.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

from sora.api import ApiServerConfig, SoraApiServer
from sora.contracts.companion_call import CompanionCall
from sora.contracts.models import ProviderCapabilities
from sora.providers.dialogue import DeterministicDialogueProvider
from sora.providers.mock import DeterministicProvider
from sora.runtime.app_settings import AppSettings, AppSettingsController, SettingsEdit
from sora.runtime.service import RuntimeConfig, SoraRuntime

QA_PROMPT = "Ask Codex to explain this offline GUI test. Do not edit files."


class QASpecialist(DeterministicProvider):
    async def capabilities(self) -> ProviderCapabilities:
        return (await super().capabilities()).model_copy(
            update={
                "provider": "codex-app-server",
                "display_name": "QA Codex fixture (no inference)",
            }
        )

    async def available_models(self) -> tuple[dict[str, Any], ...]:
        return (
            {
                "model": "fixture-small",
                "displayName": "Offline QA fixture, NOT an LLM",
                "description": "Deterministic admission/UI test only.",
            },
        )


class QADialogue(DeterministicDialogueProvider):
    async def choose_call(
        self,
        prompt: str,
        observations: str,
        operations: frozenset[str],
    ) -> CompanionCall:
        if prompt == QA_PROMPT and "delegate" in operations:
            return CompanionCall.model_validate(
                {
                    "op": "delegate",
                    "provider": "codex",
                    "model": "m1",
                    "task": "OFFLINE QA BRIEF: explain the fixture; do not edit files.",
                }
            )
        return CompanionCall.model_validate({"op": "finish"})

    async def respond(self, *args: Any, **kwargs: Any) -> str:
        return "OFFLINE GUI QA ONLY. No LLM inference. Exact test prompt: " + QA_PROMPT


async def main(args: argparse.Namespace) -> None:
    root = Path(__file__).resolve().parents[1]
    state = Path(args.state).resolve()
    if root not in state.parents or ".local" not in state.parts:
        raise ValueError("Use a dedicated .local QA directory, never owner state")
    state.mkdir(parents=True, exist_ok=True)
    if (state / "STOP").exists():
        raise ValueError("Use a fresh QA directory; existing STOP belongs to its previous run")
    settings = AppSettingsController(state, AppSettings())
    settings.save(
        SettingsEdit(
            version=8,
            expected_revision=settings.saved.revision,
            changes={
                "agents.codex.preferred_model": "fixture-small",
                "agents.codex.model_purpose": "OFFLINE deterministic GUI verification, not an LLM",
                "perception.desktop_context": False,
                "perception.window_context": False,
                "perception.mode": "native-only",
            },
        )
    )
    runtime = SoraRuntime(
        RuntimeConfig(root=state, identity_root=root / "identity"),
        providers={"codex": QASpecialist()},
        app_settings=settings,
    )
    await runtime.start()
    settings.provider = QADialogue()
    server = SoraApiServer(
        runtime,
        ApiServerConfig(
            host="127.0.0.1",
            port=args.port,
            token_file=state / "api-token",
        ),
    )
    try:
        await runtime.agent_catalogue.refresh()
        await server.start()
        print(f"OFFLINE QA Core ready: {server.actual_port}; prompt: {QA_PROMPT}", flush=True)
        while not (state / "STOP").exists():
            await asyncio.sleep(1)
    finally:
        await server.close()
        await runtime.close(drain=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True)
    parser.add_argument("--port", type=int, default=18793)
    asyncio.run(main(parser.parse_args()))
