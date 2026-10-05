"""Stop response races are scoped, fail closed and preserve canonical history."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

from sora.api import ApiServerConfig, SoraApiClient, SoraApiServer
from sora.api.protocol import HttpRequest
from sora.api.routes import RouteHandler
from sora.providers.dialogue import DialogueTimeoutError
from sora.providers.mock import DeterministicProvider
from sora.runtime.dialogue_turns import (
    DialogueCancelledError,
    DialogueRequestConflict,
    DialogueTurn,
    DialogueTurns,
)
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.security.local_policy import owner_local_scope
from tests.providers.test_direct_dialogue import RecordingDialogueProvider


@pytest.mark.asyncio
async def test_stop_before_start_and_nonce_reuse() -> None:
    turns = DialogueTurns()
    calls = 0

    async def respond(turn: DialogueTurn) -> str:
        nonlocal calls
        calls += 1
        return "ok"

    assert turns.cancel("early", local=True) == "cancelled-before-start"
    with pytest.raises(DialogueCancelledError):
        await turns.run(respond, request_id="early", local=True)
    assert calls == 0
    assert await turns.run(respond, request_id="early", local=False) == "ok"
    with pytest.raises(DialogueRequestConflict):
        await turns.run(respond, request_id="early", local=False)
    assert turns.count == 0


@pytest.mark.asyncio
async def test_cancelled_provider_cannot_publish_late_reply_or_cancel_another_turn() -> None:
    turns = DialogueTurns()
    entered = asyncio.Event()
    released = asyncio.Event()

    async def stubborn(turn: DialogueTurn) -> str:
        entered.set()
        try:
            await released.wait()
        except asyncio.CancelledError:
            return "late response"
        return "normal"

    task = asyncio.create_task(turns.run(stubborn, request_id="one", local=True))
    await entered.wait()
    with pytest.raises(DialogueRequestConflict):
        await turns.run(stubborn, request_id="one", local=True)
    assert turns.cancel("one", local=False) == "cancelled-before-start"
    assert not task.done()
    assert turns.cancel("one", local=True) == "cancelling"
    with pytest.raises(DialogueCancelledError):
        await task
    assert turns.count == 0
    released.set()
    assert await turns.run(stubborn, request_id="two", local=True) == "normal"


@pytest.mark.asyncio
async def test_commit_fence_does_not_claim_rollback() -> None:
    turns = DialogueTurns()
    entered = asyncio.Event()
    released = asyncio.Event()

    async def commit(turn: DialogueTurn) -> str:
        turn.begin_commit()
        entered.set()
        await released.wait()
        turn.phase = "committed"
        return "committed pair"

    task = asyncio.create_task(turns.run(commit, request_id="commit", local=True))
    await entered.wait()
    assert turns.cancel("commit", local=True) == "already-finishing"
    released.set()
    assert await task == "committed pair"
    assert turns.cancel("commit", local=True) == "completed"


@pytest.mark.asyncio
async def test_deadline_is_checked_even_when_provider_returns_late() -> None:
    turns = DialogueTurns()

    async def late(turn: DialogueTurn) -> str:
        turn.expires_at = time.monotonic() - 1
        return "too late"

    with pytest.raises(DialogueTimeoutError):
        await turns.run(late, request_id="late", local=True)
    assert turns.count == 0


@pytest.mark.asyncio
async def test_stop_before_child_first_instruction_cleans_registry() -> None:
    turns = DialogueTurns()
    entered = False

    async def respond(turn: DialogueTurn) -> str:
        nonlocal entered
        entered = True
        return "ok"

    task = asyncio.create_task(turns.run(respond, request_id="early-child", local=True))
    await asyncio.sleep(0)
    turns.cancel("early-child", local=True)
    with pytest.raises(DialogueCancelledError):
        await task
    assert not entered
    assert turns.count == 0


@pytest.mark.asyncio
async def test_shutdown_and_policy_invalidation_are_local_scoped() -> None:
    turns = DialogueTurns()
    entered = asyncio.Event()

    async def wait(turn: DialogueTurn) -> str:
        entered.set()
        await asyncio.Event().wait()
        return "unreachable"

    task = asyncio.create_task(turns.run(wait, request_id="shutdown", local=True))
    await entered.wait()
    await turns.close()
    with pytest.raises(DialogueCancelledError):
        await task
    assert turns.count == 0


class StoppableDialogue(RecordingDialogueProvider):
    def __init__(self) -> None:
        super().__init__()
        self.entered = asyncio.Event()

    async def respond(self, prompt: str, context: str, **kwargs: object) -> str:
        if prompt == "Slow response":
            self.entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                return "late private response"
        return "normal response"


@pytest.mark.asyncio
async def test_owner_stop_route_rejects_late_reply_and_next_request_works(tmp_path: Path) -> None:
    provider = StoppableDialogue()
    runtime = SoraRuntime(
        RuntimeConfig(
            root=tmp_path, identity_root=Path(__file__).resolve().parents[2] / "identity"
        ),
        provider=DeterministicProvider(),
        dialogue_provider=provider,
    )
    await runtime.start()
    route = RouteHandler(runtime)

    def request(path: str, data: object) -> HttpRequest:
        return HttpRequest("POST", path, {}, json.dumps(data).encode())

    try:
        with owner_local_scope():
            task = asyncio.create_task(
                route.handle_request(
                    request(
                        "/api/v1/dialogue",
                        {
                            "content": "Slow response",
                            "request_id": "stopped",
                        },
                    )
                )
            )
            await provider.entered.wait()
            assert (
                await route.handle_request(
                    request(
                        "/api/v1/dialogue/cancel",
                        {
                            "request_id": "stopped",
                        },
                    )
                )
            ).status_code == 200
            result = await task
            assert result.status_code == 409
            assert b"DIALOGUE_CANCELLED" in result.body
            assert not await runtime.repository.list_messages(runtime.config.conversation_id)
            assert runtime.dialogue_turns.count == 0
            assert (
                await route.handle_request(
                    request(
                        "/api/v1/dialogue",
                        {
                            "content": "Hello",
                            "request_id": "next",
                        },
                    )
                )
            ).status_code == 201
            assert len(await runtime.repository.list_messages(runtime.config.conversation_id)) == 2
            invalid_requests: list[object] = [{}, {"request_id": "bad id"}, {"request_id": 1}, []]
            for data in invalid_requests:
                assert (
                    await route.handle_request(request("/api/v1/dialogue/cancel", data))
                ).status_code == 400
            assert (
                await route.handle_request(
                    request(
                        "/api/v1/dialogue/cancel",
                        {
                            "request_id": "next",
                        },
                    ),
                    remote_scopes=frozenset({"conversation:write"}),
                )
            ).status_code == 403
        assert (
            await route.handle_request(
                request(
                    "/api/v1/dialogue/cancel",
                    {
                        "request_id": "not-owner",
                    },
                )
            )
        ).status_code == 403
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_authenticated_http_cancel_is_scoped_and_stale_response_never_commits(
    tmp_path: Path,
) -> None:
    provider = StoppableDialogue()
    runtime = SoraRuntime(
        RuntimeConfig(
            root=tmp_path, identity_root=Path(__file__).resolve().parents[2] / "identity"
        ),
        provider=DeterministicProvider(),
        dialogue_provider=provider,
    )
    await runtime.start()
    server = SoraApiServer(runtime, ApiServerConfig(port=0, auth_token="cancel-test-token-123456"))
    await server.start()
    client = SoraApiClient(
        f"http://127.0.0.1:{server.actual_port}", auth_token="cancel-test-token-123456"
    )
    anonymous = SoraApiClient(f"http://127.0.0.1:{server.actual_port}")
    try:
        pending = asyncio.create_task(
            client._request(
                "POST",
                "/api/v1/dialogue",
                {
                    "content": "Slow response",
                    "request_id": "http-turn",
                },
            )
        )
        await asyncio.wait_for(provider.entered.wait(), timeout=5)
        status, _ = await anonymous._request(
            "POST",
            "/api/v1/dialogue/cancel",
            {
                "request_id": "http-turn",
            },
        )
        assert status == 401
        assert not pending.done()
        status, data = await client._request(
            "POST",
            "/api/v1/dialogue/cancel",
            {
                "request_id": "http-turn",
            },
        )
        assert status == 200 and data["state"] == "cancelling"
        status, data = await asyncio.wait_for(pending, timeout=5)
        assert status == 409 and data["error"]["code"] == "DIALOGUE_CANCELLED"
        assert not await runtime.repository.list_messages(runtime.config.conversation_id)
        status, data = await client._request(
            "POST",
            "/api/v1/dialogue",
            {
                "content": "Hello",
                "request_id": "http-next",
            },
        )
        assert status == 201 and data["response"] == "normal response"
    finally:
        await server.close()
        await runtime.close()
