"""Native/file tool contracts and owner-local conversation integration."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from sora.contracts.companion_read import CompanionReadCall
from sora.contracts.desktop import DesktopNode, DesktopObservation, DesktopObservationRequest
from sora.providers.dialogue import (
    DialogueProviderError,
    DialogueTimeoutError,
    OpenAICompatibleDialogueProvider,
)
from sora.providers.mock import DeterministicProvider
from sora.runtime.app_settings import AppSettings, AppSettingsController, SettingsEdit
from sora.runtime.read_tools import CompanionReadTools
from sora.runtime.read_turn import bounded_observations, collect_reads
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.security.local_policy import owner_local_scope
from sora.security.operations import OperationAuthorizationError
from tests.providers.test_direct_dialogue import RecordingDialogueProvider

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


def call(op: str, **fields: Any) -> CompanionReadCall:
    return CompanionReadCall.model_validate({"op": op, **fields})


def window() -> DesktopNode:
    return DesktopNode(
        node_id="w1",
        process_id=42,
        window_handle=17,
        name="Fixture",
        automation_id="",
        control_type="Window",
        rect=None,
        focused=True,
        enabled=True,
        offscreen=False,
        password=False,
        process_started_at=datetime(2026, 10, 1, tzinfo=UTC),
    )


class Reader(RecordingDialogueProvider):
    def __init__(self, calls: list[CompanionReadCall]) -> None:
        super().__init__()
        self.reads = iter(calls)
        self.observations: list[str] = []
        self.screen = AsyncMock(side_effect=AssertionError("No screenshot classifier"))

    async def choose_read(self, prompt: str, observations: str) -> CompanionReadCall:
        self.observations.append(observations)
        return next(self.reads, call("finish"))

    async def choose_screen_view(self, prompt: str) -> Any:
        return await self.screen(prompt)


@pytest.mark.parametrize(
    "payload",
    [
        {"op": "read_file"},
        {"op": "read_file", "path": "x", "target": "f1"},
        {"op": "list_windows", "authorized_by": "owner"},
        {"op": "shell", "cmd": "dir"},
        {"op": "read_file", "path": "x", "offset": -1},
        {"op": "inspect_window", "target": "w1", "view": "click"},
    ],
)
def test_read_schema_rejects_authority_effects_and_bad_locations(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        CompanionReadCall.model_validate(payload)


@pytest.mark.asyncio
async def test_files_outside_project_paging_cursors_and_stale_refs(tmp_path: Path) -> None:
    for index in range(45):
        (tmp_path / f"item-{index:02}.txt").write_text("needle " + "x" * 9000)
    tools = CompanionReadTools(check=lambda _: None, observe=AsyncMock())
    listing = await tools.execute(call("list_files", path=str(tmp_path)))
    assert listing.status == "partial" and listing.continuation
    entries: Any = listing.data["entries"]
    read = await tools.execute(call("read_file", target=entries[0]["target"]))
    assert read.status == "partial" and len(str(read.data["text"])) == 8192
    tail = await tools.execute(call("read_file", path=entries[0]["path"], offset=8192))
    assert tail.status == "ok" and tail.data["next_offset"] is None
    second = await tools.execute(
        call("list_files", path=str(tmp_path), cursor=listing.continuation)
    )
    assert second.status == "ok" and len(second.data["entries"]) == 5  # type: ignore[arg-type]
    wrong = await tools.execute(
        call("search_files", path=str(tmp_path), query="item", cursor=listing.continuation)
    )
    assert wrong.status == "stale"
    Path(entries[0]["path"]).write_text("changed")
    assert (await tools.execute(call("read_file", target=entries[0]["target"]))).status == "stale"
    assert (await tools.execute(call("read_file", path="relative.txt"))).status == "unsupported"
    assert (
        await tools.execute(call("read_file", path=str(tmp_path / "missing")))
    ).status == "not_found"


@pytest.mark.asyncio
async def test_literal_text_search_reports_format_gaps_and_prefix_limit(tmp_path: Path) -> None:
    (tmp_path / "match.txt").write_text("literal [needle] " + "x" * 70000)
    (tmp_path / "paper.pdf").write_text("[needle]")
    (tmp_path / "picture.png").write_bytes(b"not pixels")
    tools = CompanionReadTools(check=lambda _: None, observe=AsyncMock())
    result = await tools.execute(
        call("search_files", path=str(tmp_path), query="[needle]", mode="text")
    )
    assert result.status == "partial" and result.data["skipped"] == 2
    assert len(result.data["entries"]) == 1  # type: ignore[arg-type]
    assert (
        await tools.execute(call("read_file", path=str(tmp_path / "paper.pdf")))
    ).status == "unsupported"
    # Last page of a bounded prefix remains partial, not a claim that the whole file was read.
    last = await tools.execute(call("read_file", path=str(tmp_path / "match.txt"), offset=65536))
    assert last.status == "partial" and last.truncated


@pytest.mark.asyncio
async def test_windows_selection_identity_and_policy_rechecks() -> None:
    node = window()
    observe = AsyncMock(
        side_effect=[
            DesktopObservation(status="ok", nodes=(node,)),
            DesktopObservation(
                status="ok",
                nodes=(node.model_copy(update={"selected_text": "chosen"}),),
                process_started_at=node.process_started_at,
            ),
            DesktopObservation(status="ok", nodes=(node,), process_started_at=datetime.now(UTC)),
        ]
    )
    tools = CompanionReadTools(check=lambda _: None, observe=observe)
    assert (
        await tools.execute(call("inspect_window", target="guess", view="text"))
    ).status == "stale"
    await tools.execute(call("list_windows"))
    selection = await tools.execute(call("inspect_window", target="w1", view="selection"))
    assert selection.status == "ok" and "chosen" in json.dumps(selection.data)
    assert observe.call_args.args[0].operation == "selection"
    assert (await tools.execute(call("inspect_window", target="w1", view="text"))).status == "stale"
    count = 0

    def check(_: str) -> None:
        nonlocal count
        count += 1
        if count == 2:
            raise OperationAuthorizationError("Changed while reading")

    denied = CompanionReadTools(
        check=check, observe=AsyncMock(return_value=DesktopObservation(status="ok", nodes=(node,)))
    )
    result = await denied.execute(call("list_windows"))
    assert result.status == "disabled" and not denied.windows and "Fixture" not in str(result.data)


def test_observation_budget_preserves_valid_json_and_reports_clipping() -> None:
    records = [{"source": "filesystem", "status": "ok", "data": {"text": "x" * 8000}}]
    encoded = bounded_observations(records, 1000)
    assert len(encoded) <= 1000
    assert json.loads(encoded)[0]["context_clipped"]
    assert len(records[0]["data"]["text"]) == 8000  # type: ignore[index]


def test_fresh_selection_survives_large_older_inventory() -> None:
    records = [
        {"operation": "list_windows", "data": {"windows": [{"title": "x" * 1000}] * 30}},
        {
            "operation": "inspect_window",
            "data": {"view": "selection", "selected_text": "bef", "nodes": [{"name": "fixture"}]},
        },
    ]
    encoded = bounded_observations(records, 900)
    assert len(encoded) <= 900
    assert json.loads(encoded)[-1]["data"]["selected_text"] == "bef"
    with pytest.raises(ValidationError):
        call("inspect_window", target="w1")


@pytest.mark.asyncio
async def test_loop_repeat_invalid_and_deadline_are_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sora.runtime.read_turn.desktop_directories", lambda: [])
    tools = CompanionReadTools(
        check=lambda _: None,
        observe=AsyncMock(return_value=DesktopObservation(status="not_configured")),
    )
    # The first repeat ends the reading; the earlier result stays in the observations.
    reader = Reader([call("list_windows"), call("list_windows"), call("list_windows")])
    result = await collect_reads(
        "windows",
        provider=reader,
        tools=tools,
        check_epoch=lambda: None,
        file_read=False,
        desktop_read=True,
        timeout=1,
        budget=3000,
    )
    assert len(result.sources) == 1
    assert "Repeated read stopped" in result.observations
    assert result.chosen == ("list_windows",) * 2
    reader.choose_read = AsyncMock(side_effect=DialogueProviderError("invalid"))  # type: ignore[method-assign]
    result = await collect_reads(
        "windows",
        provider=reader,
        tools=tools,
        check_epoch=lambda: None,
        file_read=False,
        desktop_read=True,
        timeout=1,
        budget=3000,
    )
    assert reader.choose_read.await_count == 2
    assert result.attempted and "Invalid read call" in result.observations

    async def slow(*args: Any) -> CompanionReadCall:
        await asyncio.sleep(10)
        return call("finish")

    monkeypatch.setattr(reader, "choose_read", slow)
    result = await collect_reads(
        "windows",
        provider=reader,
        tools=tools,
        check_epoch=lambda: None,
        file_read=False,
        desktop_read=True,
        timeout=0.01,
        budget=3000,
    )
    assert "deadline reached" in result.observations

    failed = AsyncMock(side_effect=DialogueTimeoutError("provider timed out"))
    monkeypatch.setattr(reader, "choose_read", failed)
    with pytest.raises(DialogueTimeoutError):
        await collect_reads(
            "windows", provider=reader, tools=tools, check_epoch=lambda: None,
            file_read=False, desktop_read=True, timeout=1, budget=3000,
        )
    assert failed.await_count == 1


@pytest.mark.asyncio
async def test_local_dialogue_reads_with_capture_off_remote_cannot_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sora.runtime.read_turn.desktop_directories", lambda: [])
    settings = AppSettingsController(tmp_path, AppSettings())
    settings.save(
        SettingsEdit(
            version=3,
            expected_revision=0,
            changes={
                "local_companion.desktop_capture": False,
                "local_companion.avatar_control": False,
            },
        )
    )
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(),
        app_settings=settings,
    )
    await runtime.start()
    reader = Reader([call("list_windows"), call("finish")])
    settings.provider = reader
    runtime.windows_bridge = AsyncMock()
    runtime.windows_bridge.observe.return_value = DesktopObservation(status="ok", nodes=(window(),))
    try:
        await runtime.dialogue("STALE_HISTORY_MARKER", allow_desktop_view=False)
        reader.calls.clear()
        with owner_local_scope():
            answer = await runtime.dialogue("Which windows are open?")
        assert "Read evidence:" in answer and "windows.win32, ok" in answer
        assert "Fixture" in reader.calls[0][1]
        assert "STALE_HISTORY_MARKER" not in reader.calls[0][1]
        assert 'desktop_observe": true' in reader.observations[0]
        reader.screen.assert_not_awaited()
        runtime.windows_bridge.observe.assert_awaited_once()
        previous = len(reader.observations)
        await runtime.dialogue(
            "Which windows are open?", allow_desktop_view=False, allow_local_files=False
        )
        assert len(reader.observations) == previous
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_policy_off_on_during_selection_never_executes_or_sends_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sora.runtime.read_turn.desktop_directories", lambda: [])
    settings = AppSettingsController(tmp_path, AppSettings())
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(),
        app_settings=settings,
    )
    await runtime.start()
    reader = Reader([])

    async def toggle(*args: Any) -> CompanionReadCall:
        for enabled in (False, True):
            settings.save(
                SettingsEdit(
                    version=3,
                    expected_revision=settings.saved.revision,
                    changes={"local_companion.file_read": enabled},
                )
            )
        return call("list_windows")

    monkeypatch.setattr(reader, "choose_read", toggle)
    settings.provider = reader
    try:
        from sora.runtime.dialogue_turns import DialogueCancelledError

        with owner_local_scope(), pytest.raises(DialogueCancelledError):
            await runtime.dialogue("Look for my notes")
        assert not reader.calls and runtime.dialogue_in_progress == 0
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_external_dialogue_never_receives_default_desktop_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    desktop = AsyncMock(side_effect=AssertionError("No local evidence to external model"))
    monkeypatch.setattr("sora.runtime.service.collect_reads", desktop)
    settings = AppSettingsController(tmp_path, AppSettings())
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(),
        app_settings=settings,
    )
    await runtime.start()
    provider = OpenAICompatibleDialogueProvider(base_url="https://example.invalid/v1", model="test")
    monkeypatch.setattr(provider, "respond", AsyncMock(return_value="No local reads"))
    settings.provider = provider
    try:
        with owner_local_scope():
            await runtime.dialogue("Hello", allow_motion_actions=False, allow_desktop_view=False)
        desktop.assert_not_awaited()
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_read_schema_request_has_space_for_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatibleDialogueProvider(base_url="http://127.0.0.1:1234/v1", model="2b")
    post = AsyncMock(return_value={"content": '{"op":"read_file","path":"C:/notes/a.txt"}'})
    monkeypatch.setattr(provider, "_post_message", post)
    chosen = await provider.choose_read("read a note", "[]")
    assert chosen.root.op == "read_file"
    body = post.call_args.args[0]
    assert body["max_tokens"] == 1024
    assert body["response_format"]["schema"] == CompanionReadCall.model_json_schema()


@pytest.mark.asyncio
async def test_default_desktop_seed_is_metadata_only_and_loop_has_six_steps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for index in range(15):
        (tmp_path / f"note-{index}.txt").write_text("BODY MUST NOT BE SEEDED")
    monkeypatch.setattr("sora.runtime.read_turn.desktop_directories", lambda: [str(tmp_path)])
    tools = CompanionReadTools(check=lambda _: None, observe=AsyncMock())
    reader = Reader([call("read_file", path=str(tmp_path / f"note-{i}.txt")) for i in range(7)])
    result = await collect_reads(
        "Read notes",
        provider=reader,
        tools=tools,
        check_epoch=lambda: None,
        file_read=True,
        desktop_read=True,
        timeout=5,
        budget=4000,
    )
    assert "BODY MUST NOT BE SEEDED" not in reader.observations[0]
    assert len(reader.observations) == 6
    assert "Six-step limit reached" in result.observations


def test_normal_launcher_wires_native_observation() -> None:
    script = (IDENTITY_ROOT.parent / "scripts/start-manual-test.ps1").read_text()
    assert '"--windows-bridge", $observationHelper' in script
    # Root Start-SORA delegates here: all native helpers must be built (a failed helper build
    # stops the start) and passed to Core.
    [helper_builds] = [line for line in script.splitlines()
                       if "foreach ($project in @($captureProject" in line]
    for name in ("observation", "action", "type"):
        assert f"${name}Project" in helper_builds
    for name in ("action", "type"):
        assert f'"--windows-{name}", ${name}Helper' in script
    root = (IDENTITY_ROOT.parent / "Start-SORA.ps1").read_text()
    assert '"scripts/start-manual-test.ps1"' in root
    assert "[switch]$NoClient" in root
    assert "[switch]$HiddenCore" in root


def test_inventory_text_contracts_redact_passwords() -> None:
    assert DesktopObservationRequest(operation="inventory").resource == "desktop.observe:inventory"
    with pytest.raises(ValidationError):
        DesktopObservationRequest(operation="inventory", process_id=42)
    with pytest.raises(ValidationError):
        DesktopObservation(
            status="ok",
            nodes=(
                window().model_copy(
                    update={
                        "password": True,
                        "name": "",
                        "text": "secret",
                    }
                ),
            ),
        )


def test_trimming_keeps_the_window_inventory_over_background_context() -> None:
    """Seen live 2026-10-08: the inventory was trimmed first, so E4B could not point at a control.

    Desktop previews, the agent list and memory previews go before the window inventory.
    """
    import json

    from sora.runtime.read_turn import bounded_observations

    records = [
        {"operation": "memory_context", "status": "ok", "data": {"items": ["m" * 300] * 5}},
        {"operation": "agent_defaults", "status": "ok", "data": {"agents": ["a" * 300] * 5}},
        {"operation": "list_windows", "status": "ok",
         "data": {"windows": [{"target": "w1", "title": "Antigravity"}]}},
        {"operation": "desktop_metadata", "status": "ok", "data": {"entries": ["d" * 300] * 5}},
        {"operation": "inspect_window", "status": "ok", "data": {"nodes": []}},
    ]
    kept = {row["operation"]: row for row in json.loads(bounded_observations(records, 1200))}
    assert kept["list_windows"]["data"]["windows"] == [{"target": "w1", "title": "Antigravity"}]
    assert kept["desktop_metadata"]["data"] == {}
    assert kept["desktop_metadata"]["context_clipped"]


def test_a_repeated_window_list_names_the_window_the_owner_asked_about() -> None:
    from sora.runtime.read_turn import named_windows

    tools = CompanionReadTools(check=lambda _: None, observe=AsyncMock())
    node = window()
    tools.windows["w5"] = (node.model_copy(update={"name": "Antigravity - SORA"}), 0.0)
    tools.windows["w6"] = (node.model_copy(update={"name": "Spotify"}), 0.0)
    hint = named_windows("Look at the Close button on the Antigravity window.", tools)
    assert "w5 (Antigravity - SORA)" in hint and "w6" not in hint
    assert named_windows("What's the weather?", tools) == ""


@pytest.mark.asyncio
async def test_a_listed_window_turn_cannot_relist_and_names_the_requested_window() -> None:
    """Seen live 2026-10-09 (spoken turns): E4B re-called list_windows after the seeded list,
    hit the repeat stop and never moved. Once listed, list_windows is no longer offered, and the
    window the owner named is pointed out up front."""
    from sora.contracts.companion_call import CompanionCall
    from sora.contracts.companion_read import CompanionReadResult

    class Tools(CompanionReadTools):
        async def execute(self, read: CompanionReadCall) -> CompanionReadResult:
            node = window().model_copy(update={"name": "Claude"})
            self.windows["w1"] = (node, 0.0)
            return CompanionReadResult(
                call_id="c1", status="ok", source="fixture", observed_at=datetime.now(UTC),
                data={"windows": [{"target": "w1", "title": "Claude"}]})

    class Chooser:
        def __init__(self) -> None:
            self.offered: list[frozenset[str]] = []
            self.seen: list[str] = []

        async def choose_call(
            self, prompt: str, observations: str, operations: frozenset[str],
        ) -> CompanionCall:
            self.offered.append(operations)
            self.seen.append(observations)
            return CompanionCall.model_validate({"op": "finish"})

    chooser = Chooser()
    turn = await collect_reads(
        "Could you walk to the Claude window?", provider=chooser,
        tools=Tools(check=lambda _: None, observe=AsyncMock()), check_epoch=lambda: None,
        file_read=False, desktop_read=True, timeout=5, budget=4000, seed_windows=True,
        avatar_control=True)
    assert "list_windows" not in chooser.offered[0] and "move" in chooser.offered[0]
    assert "list_windows" in turn.offered  # the trace still shows what the turn offered
    assert "w1 (Claude)" in chooser.seen[0]


def test_her_abilities_are_described_from_what_the_turn_offered() -> None:
    from sora.runtime.read_turn import abilities

    line = abilities(("delegate", "finish", "move", "pose"))
    assert "walk or run my avatar" in line and "agent colleagues" in line
    assert "finish" not in line and abilities(("finish",)) == ""
