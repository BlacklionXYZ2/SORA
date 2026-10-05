"""Owned local voice GUI QA profile; stop by creating its state-root/stop file."""

import asyncio
from pathlib import Path

from sora.api import ApiServerConfig, SoraApiServer
from sora.providers.mock import DeterministicProvider
from sora.runtime.app_settings import AppSettings, AppSettingsController
from sora.runtime.service import RuntimeConfig, SoraRuntime

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / ".local/voice-gui-qa-20261003"


async def main() -> None:
    settings = AppSettingsController(
        STATE,
        AppSettings.model_validate(
            {
                "perception": {"paused": True},
                "local_companion": {
                    "desktop_observe": False,
                    "desktop_capture": False,
                    "avatar_control": False,
                    "file_read": False,
                    "agent_delegation": False,
                },
            }
        ),
    )
    runtime = SoraRuntime(
        RuntimeConfig(root=STATE, identity_root=ROOT / "identity"),
        provider=DeterministicProvider(),
        app_settings=settings,
    )
    server = SoraApiServer(
        runtime,
        ApiServerConfig(
            port=18788, token_file=STATE / "token", auth_token="voice-gui-qa-token-123456"
        ),
    )
    try:
        await runtime.start()
        await server.start()
        print("Owned voice GUI QA Core listening on 18788", flush=True)
        while not (STATE / "stop").exists():
            await asyncio.sleep(0.5)
    finally:
        await server.close()
        await runtime.close()


asyncio.run(main())
