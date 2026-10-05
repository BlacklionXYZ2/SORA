"""Unified small-model calls: constrained vocabulary and real Core admission boundaries."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from sora.api.protocol import HttpRequest
from sora.api.routes import RouteHandler
from sora.contracts.companion_call import CompanionCall, Delegate, ListAgents, call_schema
from sora.contracts.embodiment import EmbodimentVerb, MonitorDescriptor, ScreenRect
from sora.providers.dialogue import DeterministicDialogueProvider, OpenAICompatibleDialogueProvider
from sora.runtime.agent_catalogue import AgentCatalogue
from sora.runtime.agent_preferences import AgentPreferences
from sora.runtime.app_settings import AppSettings, AppSettingsController, SettingsEdit
from sora.runtime.delegation_catalogue import DelegationCatalogue
from sora.runtime.dialogue_turns import DialogueCancelledError, DialogueRequestConflict
from sora.runtime.read_tools import CompanionReadTools
from sora.runtime.read_turn import collect_reads
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.security.local_policy import owner_local_scope
from tests.providers.test_motion_dialogue import fake_session
from tests.runtime.test_agent_catalogue import CatalogueProvider

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


class Caller(DeterministicDialogueProvider):
    def __init__(self, *calls: dict[str, Any]):
        self.calls = iter(calls)
        self.observations: list[str] = []
        self.operations: list[frozenset[str]] = []

    async def choose_call(
        self,
        prompt: str,
        observations: str,
        operations: frozenset[str],
    ) -> CompanionCall:
        self.observations.append(observations)
        self.operations.append(operations)
        return CompanionCall.model_validate(next(self.calls, {"op": "finish"}))


def runtime_for(tmp_path: Path, caller: Caller) -> tuple[SoraRuntime, CatalogueProvider]:
    settings = AppSettingsController(tmp_path, AppSettings())
    settings.save(
        SettingsEdit(
            version=8,
            expected_revision=0,
            changes={
                "agents.codex.preferred_model": "opaque/provider:model",
                "agents.codex.model_purpose": "Small documentation tasks",
                "perception.desktop_context": False,
            },
        )
    )
    provider = CatalogueProvider("codex-app-server")
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=IDENTITY_ROOT),
        providers={"codex": provider},
        app_settings=settings,
    )
    settings.provider = caller
    return runtime, provider


@pytest.mark.parametrize(
    "value",
    [
        {"op": "shell", "command": "dir"},
        {"op": "pose", "name": "wave", "authorized_by": "owner"},
        {"op": "move", "target": "pointer", "x": 4},
        {"op": "move", "target": "window"},
        {"op": "delegate", "task": "x", "provider": "invented"},
        {"op": "delegate", "task": ""},
        {"op": "delegate", "task": "x", "permissions": ["write"]},
        {"op": "press", "target": "w1"},
    ],
)
def test_call_rejects_authority_coordinates_and_unimplemented_operations(value: Any) -> None:
    with pytest.raises(ValidationError):
        CompanionCall.model_validate(value)


def test_disabled_calls_are_structurally_absent_including_definitions() -> None:
    schema = call_schema({"list_windows", "read_file"})
    assert set(schema["discriminator"]["mapping"]) == {"finish", "list_windows", "read_file"}
    assert set(schema["$defs"]) == {"FinishRead", "ListWindows", "ReadFile"}
    assert "Delegate" not in json.dumps(schema)


@pytest.mark.asyncio
async def test_provider_requests_enabled_schema_and_validates_disabled_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OpenAICompatibleDialogueProvider(base_url="http://127.0.0.1:1234/v1", model="2b")
    post = AsyncMock(return_value={"content": '{"op":"pose","name":"wave"}'})
    monkeypatch.setattr(provider, "_post_message", post)
    assert (await provider.choose_call("Wave", "[]", frozenset({"pose"}))).root.op == "pose"
    body = post.call_args.args[0]
    assert body["max_tokens"] == 1024 and body["temperature"] == 0
    assert body["response_format"]["schema"] == call_schema({"pose"})
    from sora.providers.dialogue import DialogueProviderError

    with pytest.raises(DialogueProviderError):
        await provider.choose_call("Hello", "[]", frozenset({"finish"}))


@pytest.mark.asyncio
async def test_catalogue_uses_cache_known_exposed_refs_and_no_inference() -> None:
    provider = CatalogueProvider("codex-app-server")
    preferences = AgentPreferences.model_validate(
        {
            "codex": {
                "preferred_model": "configured-default",
                "model_purpose": "Cheap work",
            }
        }
    )
    catalogue = AgentCatalogue({"codex": provider}, preferences=lambda: preferences)
    await catalogue.refresh()
    calls = provider.calls
    refs = await DelegationCatalogue.create(catalogue)
    preview = refs.preview()
    default = preview["agents"][0]["models"][0]
    assert default["purpose"] == "Cheap work" and not default["execution_verified"]
    with pytest.raises(ValueError, match="Unknown"):
        refs.select(Delegate(op="delegate", task="x", model="m2"))  # Not yet exposed.
    page = refs.list_agents(ListAgents(op="list_agents", provider="codex"))
    selected = refs.select(Delegate(op="delegate", task="x", model=page["models"][1]["ref"]))
    assert selected.provider == "codex" and selected.model == "opaque/provider:model"
    assert provider.calls == calls and not provider.started_runs
    for fields in ({"model": "invented"}, {"project": "C:/owner"}, {"provider": "hermes"}):
        with pytest.raises(ValueError):
            refs.select(Delegate.model_validate({"op": "delegate", "task": "x", **fields}))
    with pytest.raises(ValueError, match="cursor"):
        refs.list_agents(ListAgents(op="list_agents", cursor="stale"))


@pytest.mark.asyncio
async def test_list_agents_has_core_versioned_result_and_one_terminal_effect() -> None:
    catalogue = await DelegationCatalogue.create(
        AgentCatalogue(
            {
                "codex": CatalogueProvider("codex-app-server"),
            }
        )
    )
    caller = Caller(
        {"op": "list_agents"}, {"op": "delegate", "task": "Explain", "provider": "codex"}
    )
    result = await collect_reads(
        "Ask Codex to explain",
        provider=caller,
        tools=CompanionReadTools(check=lambda _: None, observe=AsyncMock()),
        check_epoch=lambda: None,
        file_read=False,
        desktop_read=False,
        catalogue=catalogue,
        timeout=2,
        budget=6000,
        avatar_control=False,
    )
    rows = json.loads(result.observations)
    listing = next(row for row in rows if row.get("operation") == "list_agents")
    assert listing["version"] == 1 and listing["call_id"] and listing["observed_at"]
    assert listing["source"] == "core" and listing["status"] == "ok"
    assert isinstance(result.action, Delegate) and len(caller.operations) == 2
    assert "pose" not in caller.operations[0] and "read_file" not in caller.operations[0]


@pytest.mark.asyncio
async def test_chat_delegation_keeps_original_authority_not_brief_or_prior_desktop(
    tmp_path: Path,
) -> None:
    caller = Caller(
        {"op": "finish"},
        {
            "op": "delegate",
            "task": "MODEL BRIEF: create unrelated.txt",
            "provider": "codex",
            "model": "m1",
        },
    )
    runtime, specialist = runtime_for(tmp_path, caller)
    await runtime.start()
    assert runtime.app_settings is not None
    runtime.app_settings.provider = caller
    try:
        with owner_local_scope():
            await runtime.dialogue("PRIVATE_DESKTOP_HISTORY")
            answer = await runtime.dialogue(
                "Ask Codex to explain testing, no file edits.", request_id="delegation"
            )
            with pytest.raises(DialogueRequestConflict):
                await runtime.dialogue("Ask Codex again", request_id="delegation")
        tasks = await runtime.runtime_repository.list_tasks()
        assert len(tasks) == 1 and "queued" in answer and "not completed" in answer
        task = tasks[0]
        assert task.companion_brief == "MODEL BRIEF: create unrelated.txt"
        assert task.requested_model == "opaque/provider:model"
        await runtime.wait_for_task(task.task_id)
        request = specialist._requests[task.active_run_id or ""]
        assert request.intent == "Ask Codex to explain testing, no file edits."
        assert "PRIVATE_DESKTOP_HISTORY" not in request.context
        assert "create unrelated.txt" not in request.context
        assert request.working_directory is None
        handler = RouteHandler(runtime)
        evidence = await handler.handle_request(
            HttpRequest(
                "GET",
                f"/api/v1/tasks/{task.task_id}/evidence",
                {},
                b"",
            )
        )
        assert json.loads(evidence.body)["owner_request"] == request.intent
        remote = await handler.handle_request(
            HttpRequest(
                "GET",
                f"/api/v1/tasks/{task.task_id}",
                {},
                b"",
            ),
            remote_scopes=frozenset({"tasks:read"}),
        )
        assert "companion_brief" not in json.loads(remote.body)
        blocked = await handler.handle_request(
            HttpRequest(
                "GET",
                f"/api/v1/tasks/{task.task_id}/evidence",
                {},
                b"",
            ),
            remote_scopes=frozenset({"tasks:read"}),
        )
        assert blocked.status_code == 403
        messages = await runtime.repository.list_messages(runtime.config.conversation_id)
        assert sum(message.content == request.intent for message in messages) == 1
        assert sum(message.content == answer for message in messages) == 1
    finally:
        await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields",
    [
        {"provider": "hermes"},
        {"model": "invented"},
        {"project": "invented"},
    ],
)
async def test_bad_selection_does_not_queue_or_fall_back(tmp_path: Path, fields: Any) -> None:
    caller = Caller({"op": "delegate", "task": "Explain", **fields})
    runtime, specialist = runtime_for(tmp_path, caller)
    await runtime.start()
    assert runtime.app_settings is not None
    runtime.app_settings.provider = caller
    try:
        with owner_local_scope():
            answer = await runtime.dialogue("Ask Codex to explain testing")
        assert "not queued" in answer
        assert not await runtime.runtime_repository.list_tasks() and not specialist.started_runs
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_off_remote_and_stop_never_admit_delegation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caller = Caller({"op": "delegate", "task": "Explain", "provider": "codex"})
    runtime, specialist = runtime_for(tmp_path, caller)
    await runtime.start()
    assert runtime.app_settings is not None
    runtime.app_settings.provider = caller
    try:
        await runtime.dialogue("Ask Codex to explain testing", allow_desktop_view=False)
        assert not caller.operations  # Remote/non-owner never uses local chooser.
        runtime.app_settings.save(
            SettingsEdit(
                version=8,
                expected_revision=1,
                changes={
                    "local_companion.agent_delegation": False,
                },
            )
        )
        with owner_local_scope():
            await runtime.dialogue("Ask Codex to explain testing")
        assert all("delegate" not in operations for operations in caller.operations)
        assert not await runtime.runtime_repository.list_tasks()
        started = asyncio.Event()

        async def held(*args: Any) -> CompanionCall:
            started.set()
            await asyncio.Event().wait()
            return CompanionCall.model_validate(
                {"op": "delegate", "task": "Never", "provider": "codex"}
            )

        monkeypatch.setattr(caller, "choose_call", held)
        with owner_local_scope():
            pending = asyncio.create_task(runtime.dialogue("Explain", request_id="stop-delegate"))
            await asyncio.wait_for(started.wait(), 2)
            assert runtime.cancel_dialogue("stop-delegate") == "cancelling"
            with pytest.raises(DialogueCancelledError):
                await pending
        assert not await runtime.runtime_repository.list_tasks() and not specialist.started_runs
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_toggle_during_atomic_admission_never_queues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caller = Caller({"op": "delegate", "task": "Explain", "provider": "codex"})
    runtime, specialist = runtime_for(tmp_path, caller)
    await runtime.start()
    assert runtime.app_settings is not None
    runtime.app_settings.provider = caller
    original = runtime.runtime_repository.submit

    async def revoked(**kwargs: Any) -> Any:
        assert runtime.app_settings is not None
        for enabled in (False, True):
            runtime.app_settings.save(
                SettingsEdit(
                    version=8,
                    expected_revision=runtime.app_settings.saved.revision,
                    changes={"local_companion.agent_delegation": enabled},
                )
            )
        return await original(**kwargs)

    monkeypatch.setattr(runtime.runtime_repository, "submit", revoked)
    try:
        with owner_local_scope():
            answer = await runtime.dialogue("Ask Codex to explain testing")
        assert "not queued" in answer and "changed" in answer
        assert not await runtime.runtime_repository.list_tasks() and not specialist.started_runs
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_missing_write_project_asks_instead_of_authoring(tmp_path: Path) -> None:
    caller = Caller({"op": "delegate", "task": "Create file", "provider": "codex"})
    runtime, specialist = runtime_for(tmp_path, caller)
    await runtime.start()
    assert runtime.app_settings is not None
    runtime.app_settings.provider = caller
    try:
        with owner_local_scope():
            answer = await runtime.dialogue("Ask Codex to create a new Python module")
        assert "Which project" in answer and "not queued" in answer
        assert not await runtime.runtime_repository.list_tasks() and not specialist.started_runs
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_finish_never_falls_back_to_second_motion_selector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caller = Caller({"op": "finish"})
    fallback = AsyncMock(side_effect=AssertionError("No second decision after finish"))
    monkeypatch.setattr(caller, "choose_motion", fallback, raising=False)
    runtime, _ = runtime_for(tmp_path, caller)
    await runtime.start()
    assert runtime.app_settings is not None
    runtime.app_settings.provider = caller
    runtime.app_settings.save(
        SettingsEdit(
            version=8,
            expected_revision=1,
            changes={"local_companion.avatar_control": False},
        )
    )
    session = await fake_session(runtime, monkeypatch)
    queue = runtime.register_embodiment_queue()
    try:
        with owner_local_scope():
            await runtime.dialogue("Do not wave")
        assert "pose" not in caller.operations[0] and "move" not in caller.operations[0]
        fallback.assert_not_awaited()
        assert queue.empty()
    finally:
        await session.close()
        runtime.unregister_embodiment_queue(queue)
        await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action", [{"op": "pose", "name": "wave"}, {"op": "move", "target": "pointer"}]
)
async def test_unified_motion_uses_existing_dispatch_not_passive_image_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action: Any,
) -> None:
    caller = Caller(action)
    runtime, _ = runtime_for(tmp_path, caller)
    await runtime.start()
    assert runtime.app_settings is not None
    runtime.app_settings.provider = caller
    runtime.app_settings.save(
        SettingsEdit(
            version=8,
            expected_revision=1,
            changes={
                "perception.mode": "image-on-prompt",
            },
        )
    )
    session = await fake_session(runtime, monkeypatch)
    queue = runtime.register_embodiment_queue()
    runtime.update_embodiment_topology(
        (
            MonitorDescriptor(
                id="PRIMARY",
                primary=True,
                rect=ScreenRect(x=0, y=0, width=1920, height=1080),
            ),
        )
    )
    capture = AsyncMock(side_effect=AssertionError("Motion must not trigger passive capture"))
    monkeypatch.setattr("sora.runtime.service.capture_application", capture)
    try:
        with owner_local_scope():
            answer = await runtime.dialogue("Wave" if action["op"] == "pose" else "Come here")
        command = queue.get_nowait()
        if action["op"] == "pose":
            assert command.state is not None and command.state.value == "waving"
            assert "not that the animation has finished" in answer
        else:
            assert command.verb is EmbodimentVerb.MOVE_TO and command.target_point is not None
            assert "not arrival" in answer
        assert "sent" in answer and await runtime.validate_embodiment_delivery(command)
        capture.assert_not_awaited()
    finally:
        await session.close()
        runtime.unregister_embodiment_queue(queue)
        await runtime.close()
