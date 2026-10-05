"""Explicit QA harness: real metadata discovery plus a no-inference task fixture.

Never launches live agent inference unless an operator separately selects a real
agent in the GUI. Use the clearly labelled QA fixture for submission checks.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sora.api import ApiServerConfig, SoraApiServer
from sora.contracts.models import ProviderCapabilities, ProviderRequest
from sora.providers.antigravity import AntigravityProvider
from sora.providers.base import ReasoningProvider
from sora.providers.codex import CodexAppServerProvider
from sora.providers.hermes import HermesACPProvider
from sora.providers.mock import DeterministicProvider
from sora.runtime.app_settings import AppSettings, AppSettingsController
from sora.runtime.service import RuntimeConfig, SoraRuntime


class CatalogueFixture(DeterministicProvider):
    def __init__(self, report: Path) -> None:
        super().__init__()
        self.report = report

    async def capabilities(self) -> ProviderCapabilities:
        return (await super().capabilities()).model_copy(
            update={
                "provider": "catalogue-fixture",
                "display_name": "QA fixture (no inference)",
            }
        )

    async def available_models(self) -> tuple[dict[str, Any], ...]:
        return (
            {
                "model": "fixture-small",
                "displayName": "QA small model fixture",
                "description": "Deterministic transport test only, not an LLM.",
                "defaultReasoningEffort": "low",
                "supportedReasoningEfforts": [{"reasoningEffort": "low"}],
            },
        )

    async def start(self, request: ProviderRequest) -> str:
        if request.model not in {None, "fixture-small"}:
            raise ValueError("Fixture model mismatch")
        self.report.write_text(
            json.dumps(
                {
                    "observed_at": datetime.now(UTC).isoformat(),
                    "task_id": request.task_id,
                    "run_id": request.run_id,
                    "model": request.model,
                    "effort": request.reasoning_effort,
                    "fixture": True,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return await super().start(request)


async def main(args: argparse.Namespace) -> None:
    root = Path(__file__).resolve().parents[1]
    state = Path(args.state).resolve()
    if state == root or root not in state.parents or ".local" not in state.parts:
        raise ValueError("QA state must be a dedicated directory beneath repository .local")
    state.mkdir(parents=True, exist_ok=True)
    fixture = CatalogueFixture(state / "selection-proof.json")
    providers: dict[str, ReasoningProvider] = {
        "fixture": fixture,
        "codex": CodexAppServerProvider(cwd=str(state)),
        "hermes": HermesACPProvider(cwd=str(state), skip_configured_mcp=True),
        "antigravity": AntigravityProvider(cwd=str(state)),
    }
    runtime = SoraRuntime(
        RuntimeConfig(root=state, identity_root=root / "identity"), providers=providers,
        app_settings=AppSettingsController(state, AppSettings()),
    )
    await runtime.start()
    server = SoraApiServer(
        runtime, ApiServerConfig(host="127.0.0.1", port=args.port, token_file=state / "api-token")
    )
    try:
        result = await runtime.agent_catalogue.refresh()
        (state / "catalogue-proof.json").write_text(
            json.dumps(result, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "providers": [
                        {
                            "provider": item["provider"],
                            "state": item["state"],
                            "count": len(item["models"]),
                            "error": item["error"],
                        }
                        for item in result["providers"]
                    ]
                }
            ),
            flush=True,
        )
        if args.serve:
            await server.start()
            print(f"QA Core ready on loopback port {server.actual_port}", flush=True)
            await asyncio.Event().wait()
    finally:
        await server.close()
        await runtime.close(drain=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=18793)
    asyncio.run(main(parser.parse_args()))
