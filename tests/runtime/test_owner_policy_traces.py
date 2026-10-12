"""Owner-local permission checks are traced once per kind per minute, not once per call.

The avatar's embodiment calls are checked about 34 times a second; tracing every one grew the
owner's database to 934 MB by 2026-10-11.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from sora.contracts.models import CapabilityOperation
from sora.runtime import service
from sora.runtime.app_settings import AppSettings, AppSettingsController, SettingsEdit
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.security.local_policy import owner_local_scope
from tests.runtime.test_agent_catalogue import CatalogueProvider

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


async def owner_policy_traces(runtime: SoraRuntime) -> list[dict[str, object]]:
    rows = await runtime.repository.database.read(
        lambda database: tuple(
            str(row[0]) for row in database.execute(
                "SELECT fields_json FROM traces WHERE phase='operation.owner_policy' "
                "ORDER BY timestamp, rowid"
            )
        )
    )
    return [json.loads(row) for row in rows]


def runtime_for(tmp_path: Path, controller: AppSettingsController) -> SoraRuntime:
    return SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=IDENTITY_ROOT),
        providers={"codex": CatalogueProvider("codex-app-server")}, app_settings=controller,
    )


async def check(runtime: SoraRuntime, resource: str = "embodiment.command",
                operation: CapabilityOperation = CapabilityOperation.TOOL_INVOKE) -> None:
    with owner_local_scope():
        await runtime.authorize_operation(
            grant_id="owner-local", device_id="desktop", resource=resource, operation=operation,
        )


@pytest.mark.asyncio
async def test_identical_checks_share_one_trace_a_minute(tmp_path: Path) -> None:
    controller = AppSettingsController(tmp_path, AppSettings())
    runtime = runtime_for(tmp_path, controller)
    await runtime.start()
    try:
        for _ in range(50):
            await check(runtime)
        await check(runtime, "embodiment.topology")  # the same effect: avatar_control
        traces = await owner_policy_traces(runtime)
        assert len(traces) == 1
        assert traces[0]["effects"] == ["avatar_control"]
        assert traces[0]["identical_since_last"] == 0

        await check(runtime, "voice", CapabilityOperation.VOICE_SESSION)  # another kind
        traces = await owner_policy_traces(runtime)
        assert [trace["effects"] for trace in traces] == [["avatar_control"], ["voice"]]

        controller.save(SettingsEdit(  # a settings change is traced at once
            version=10, expected_revision=controller.saved.revision,
            changes={"local_companion.desktop_interact": False},
        ))
        await check(runtime)
        traces = await owner_policy_traces(runtime)
        assert len(traces) == 3
        assert traces[2]["settings_revision"] == controller.saved.revision
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_skipped_checks_are_counted_in_the_next_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = runtime_for(tmp_path, AppSettingsController(tmp_path, AppSettings()))
    await runtime.start()
    try:
        for _ in range(7):
            await check(runtime)
        monkeypatch.setattr(service, "OWNER_POLICY_TRACE_INTERVAL", timedelta(0))
        await check(runtime)  # the minute is up: one trace with the count it stood for
        traces = await owner_policy_traces(runtime)
        assert [trace["identical_since_last"] for trace in traces] == [0, 6]
    finally:
        await runtime.close()
