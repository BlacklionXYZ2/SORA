from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sora.api.protocol import HttpRequest
from sora.api.routes import RouteHandler
from sora.contracts.models import TaskStatus
from sora.providers.mock import DeterministicProvider
from sora.runtime.agent_catalogue import AgentCatalogue, validate_selection
from tests.runtime.test_multi_provider_routing import MockSpecialistProvider, make_runtime


class CatalogueProvider(MockSpecialistProvider):
    def __init__(self, name: str, *, fail: bool = False) -> None:
        super().__init__(name)
        self.calls = 0
        self.fail = fail

    async def available_models(self) -> tuple[dict[str, object], ...]:
        self.calls += 1
        await asyncio.sleep(0.01)
        if self.fail:
            raise ValueError("SECRET=do-not-echo")
        return (
            {
                "model": "opaque/provider:model",
                "displayName": "Small specialist",
                "description": "Purpose from provider",
                "supportedReasoningEfforts": [
                    {"reasoningEffort": "low"},
                    {"reasoningEffort": "high"},
                ],
            },
        )


@pytest.mark.asyncio
async def test_cached_listing_singleflight_dedup_and_errors() -> None:
    provider = CatalogueProvider("codex-app-server")
    failing = CatalogueProvider("hermes-acp", fail=True)
    catalogue = AgentCatalogue(
        {
            "codex": provider,
            "codex-app-server": provider,
            "hermes": failing,
            "fixture": DeterministicProvider(),
        }
    )
    before = await catalogue.snapshot()
    assert provider.calls == 0
    assert len(before["providers"]) == 3
    assert before["providers"][0]["state"] == "not_checked"
    results = await asyncio.gather(catalogue.refresh(), catalogue.refresh())
    assert provider.calls == failing.calls == 1
    assert results[0] == results[1]
    first, failed, fixture = results[0]["providers"]
    assert first["models"][0]["id"] == "opaque/provider:model"
    assert first["models"][0]["efforts"] == ["low", "high"]
    assert not first["models"][0]["execution_verified"]
    assert failed["state"] == "unavailable"
    assert "SECRET" not in json.dumps(failed)
    assert fixture["state"] == "not_supported"
    results[0]["providers"][0]["models"].clear()
    assert (await catalogue.snapshot())["providers"][0]["models"]
    assert not provider.started_runs


@pytest.mark.parametrize(
    "provider,model,effort",
    [
        (None, "model", None),
        ("auto", "model", "low"),
        ("codex", "two words", None),
        ("codex", "model\n", None),
        ("codex", "m" * 257, None),
        ("codex", "m", "nonsense"),
    ],
)
def test_invalid_overrides_are_not_auto_routed(provider: str, model: str, effort: str) -> None:
    with pytest.raises(ValueError):
        validate_selection(provider, model, effort)


@pytest.mark.asyncio
async def test_selection_survives_persistence_execution_and_retry(tmp_path: Path) -> None:
    provider = CatalogueProvider("codex-app-server")
    runtime = make_runtime(tmp_path, {"codex": provider})
    await runtime.start()
    try:
        receipt = await runtime.submit_task(
            "Inspect only",
            explicit_provider="codex",
            explicit_model="opaque/provider:model",
            explicit_effort="low",
            idempotency_key="selected-task",
        )
        report = await runtime.wait_for_task(receipt.task.task_id)
        assert report.status is TaskStatus.COMPLETED
        request = provider._requests[receipt.run.run_id]
        assert request.model == "opaque/provider:model"
        assert request.reasoning_effort == "low"
        duplicate = await runtime.submit_task(
            "Inspect only",
            explicit_provider="codex",
            explicit_model="opaque/provider:model",
            explicit_effort="low",
            idempotency_key="selected-task",
        )
        assert not duplicate.created
        with pytest.raises(ValueError, match="different agent/model"):
            await runtime.submit_task(
                "Inspect only",
                explicit_provider="codex",
                explicit_model="different",
                idempotency_key="selected-task",
            )
    finally:
        await runtime.close()
    restarted = make_runtime(tmp_path, {"codex": provider})
    await restarted.start()
    try:
        task = await restarted.runtime_repository.get_task(receipt.task.task_id)
        assert task is not None
        assert task.requested_model == "opaque/provider:model"
        assert task.requested_effort == "low"
    finally:
        await restarted.close()


@pytest.mark.asyncio
async def test_explicit_model_unavailability_never_falls_back(tmp_path: Path) -> None:
    failing = MockSpecialistProvider("codex", fail_unavailable=True)
    alternate = CatalogueProvider("hermes")
    runtime = make_runtime(tmp_path, {"codex": failing, "hermes": alternate})
    await runtime.start()
    try:
        receipt = await runtime.submit_task(
            "Inspect", explicit_provider="codex", explicit_model="m"
        )
        assert (await runtime.wait_for_task(receipt.task.task_id)).status is TaskStatus.FAILED
        assert not alternate.started_runs
        with pytest.raises(ValueError):
            await runtime.submit_task("Inspect", explicit_model="m")
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_persisted_run_missing_adapter_does_not_use_default(tmp_path: Path) -> None:
    default = DeterministicProvider()
    runtime = make_runtime(tmp_path, {"default": default})
    await runtime.start()
    try:
        receipt = await runtime.runtime_repository.submit(
            owner_id=runtime.config.owner_id,
            project_id=runtime.config.project_id,
            conversation_id=runtime.config.conversation_id,
            intent="Persisted selection",
            idempotency_key="missing-agent",
            now=datetime.now(UTC),
            provider="removed-agent",
            requested_backend="removed-agent",
            requested_model="pinned-model",
        )
        await runtime._execute(receipt.run.run_id, "worker-test")
        task = await runtime.runtime_repository.get_task(receipt.task.task_id)
        assert task is not None and task.status is TaskStatus.FAILED
        assert default.start_count == 0
        assert await runtime.runtime_repository.lease_count() == 0
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_catalogue_owner_only_and_selection_api_validation(tmp_path: Path) -> None:
    provider = CatalogueProvider("codex-app-server")
    runtime = make_runtime(tmp_path, {"codex": provider})
    await runtime.start()
    try:
        routes = RouteHandler(runtime)
        for method, path in (
            ("GET", "/api/v1/agents/catalogue"),
            ("POST", "/api/v1/agents/catalogue/refresh"),
        ):
            response = await routes.handle_request(
                HttpRequest(method, path, {}, b""), remote_scopes=frozenset({"tasks:read"})
            )
            assert response.status_code == 403
        assert provider.calls == 0
        response = await routes.handle_request(
            HttpRequest("GET", "/api/v1/agents/catalogue", {}, b"")
        )
        assert response.status_code == 200
        assert provider.calls == 0
        for body in (
            {"intent": "Inspect", "explicit_model": "m"},
            {"intent": "Inspect", "explicit_provider": "codex", "explicit_model": 2},
        ):
            response = await routes.handle_request(
                HttpRequest("POST", "/api/v1/tasks", {}, json.dumps(body).encode())
            )
            assert response.status_code == 400
    finally:
        await runtime.close()
