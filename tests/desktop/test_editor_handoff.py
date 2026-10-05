"""P10.4 exact cooperating-editor context and finding presentation."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from tests.authorization_helpers import persist_operation_grant

from sora.api.protocol import HttpRequest
from sora.api.routes import RouteHandler
from sora.contracts.desktop import (
    DesktopNode,
    DesktopObservation,
    DesktopObservationRequest,
    DesktopTarget,
    DesktopTargetRequest,
)
from sora.contracts.editor import (
    EditorContextRequest,
    EditorFinding,
    EditorFindingPresentationRequest,
    EditorPosition,
    EditorSelection,
)
from sora.contracts.embodiment import EmbodimentVerb, ScreenRect
from sora.contracts.models import (
    CapabilityOperation,
    NormalizedResult,
    ProviderOutcome,
    ProviderRequest,
)
from sora.desktop import WindowsObservationBridge
from sora.editor import EditorContextError
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime

ROOT = Path(__file__).resolve().parents[2]


class SequenceBridge(WindowsObservationBridge):
    def __init__(self, *results: DesktopObservation) -> None:
        super().__init__(Path("unused"))
        self.results = list(results)

    async def observe(self, request: DesktopObservationRequest) -> DesktopObservation:
        del request
        assert self.results
        return self.results.pop(0)


class EditorFindingProvider(DeterministicProvider):
    async def _produce(self, request: ProviderRequest) -> NormalizedResult:
        await asyncio.sleep(0.05)
        fields = dict(line.split("=", 1) for line in request.context.splitlines() if "=" in line)
        return NormalizedResult(
            result_id=f"result-{request.run_id}",
            task_id=request.task_id,
            run_id=request.run_id,
            base_revision=0,
            outcome=ProviderOutcome.COMPLETED,
            summary="The selected fixture contains a verified finding.",
            conclusion="The gamma line is the verified finding.",
            editor_findings=(
                EditorFinding(
                    finding_id="finding-gamma",
                    context_id=fields["context_id"],
                    selection_sha256=fields["selection_sha256"],
                    start_line=3,
                    end_line=3,
                    summary="The verified finding is on gamma.",
                ),
            ),
        )


def editor_node(*, y: int = 100) -> DesktopNode:
    return DesktopNode(
        node_id="selection-node",
        process_id=321,
        window_handle=654,
        name="Selected editor text",
        automation_id="fixture-selection",
        control_type="ControlType.Text",
        runtime_id=(42, 654),
        rect=ScreenRect(x=100, y=y, width=300, height=60),
        focused=True,
        enabled=True,
        offscreen=False,
        password=False,
    )


def observation(*, y: int = 100) -> DesktopObservation:
    return DesktopObservation(
        status="ok",
        nodes=(editor_node(y=y),),
        process_started_at=datetime(2026, 9, 10, 8, 0, tzinfo=UTC),
    )


@pytest_asyncio.fixture
async def editor_runtime(tmp_path: Path) -> AsyncIterator[tuple[SoraRuntime, Path, bytes]]:
    repository = tmp_path / "repository"
    repository.mkdir()
    document = b"alpha\nbeta\ngamma\ndelta\n"
    (repository / "sample.py").write_bytes(document)
    provider = EditorFindingProvider()
    runtime = SoraRuntime(
        RuntimeConfig(
            root=tmp_path / "runtime",
            identity_root=ROOT / "identity",
            editor_repository_roots=(repository,),
        ),
        provider=provider,
    )
    await runtime.start()
    try:
        yield runtime, repository, document
    finally:
        await runtime.close()


async def acquire_selection_target(runtime: SoraRuntime) -> DesktopTarget:
    request = DesktopTargetRequest(
        process_id=321,
        window_handle=999,
        automation_id="fixture-selection",
        control_type="ControlType.Text",
    )
    runtime.windows_bridge = SequenceBridge(observation())
    await persist_operation_grant(
        runtime,
        request.observation_request.resource,
        grant_id="grant-editor-observe",
        operation=CapabilityOperation.DESKTOP_OBSERVE,
    )
    return await runtime.acquire_desktop_target(
        request,
        grant_id="grant-editor-observe",
        device_id="device-local",
    )


def context_request(repository: Path, document: bytes, target_id: str) -> EditorContextRequest:
    return EditorContextRequest(
        editor_name="fixture-editor",
        repository_root=str(repository.resolve()),
        relative_file_path="sample.py",
        document_sha256=hashlib.sha256(document).hexdigest(),
        selection=EditorSelection(
            start=EditorPosition(line=2, column=1),
            end=EditorPosition(line=4, column=1),
        ),
        selected_text="beta\ngamma\n",
        desktop_target_id=target_id,
        captured_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_exact_selection_reaches_task_and_finding_points_at_verified_line(
    editor_runtime: tuple[SoraRuntime, Path, bytes],
) -> None:
    runtime, repository, document = editor_runtime
    target = await acquire_selection_target(runtime)
    file_path = repository / "sample.py"
    await persist_operation_grant(
        runtime,
        str(file_path.resolve()),
        grant_id="grant-editor-read",
        operation=CapabilityOperation.PATH_READ,
    )
    receipt = await runtime.submit_editor_task(
        "Explain the problem in this exact selection",
        context_request(repository, document, target.target_id),
        grant_id="grant-editor-read",
        device_id="device-local",
        idempotency_key="editor-task-exact-selection",
    )
    context = receipt.task.editor_context
    assert context is not None
    assert context.relative_file_path == "sample.py"
    assert context.selected_text == "beta\ngamma\n"
    assert context.selection_sha256 == hashlib.sha256(b"beta\ngamma\n").hexdigest()

    provider = runtime.provider
    assert isinstance(provider, DeterministicProvider)
    async with asyncio.timeout(2):
        while receipt.run.run_id not in provider._requests:
            await asyncio.sleep(0.005)
    provider_request = provider._requests[receipt.run.run_id]
    assert "EDITOR_CONTEXT_V1" in provider_request.context
    assert 'relative_file_path_json="sample.py"' in provider_request.context
    assert 'selection_text_json="beta\\ngamma\\n"' in provider_request.context

    report = await runtime.wait_for_task(receipt.task.task_id, timeout=2)
    assert report.completed and report.result is not None

    queue = runtime.register_embodiment_queue()
    runtime.windows_bridge = SequenceBridge(observation(y=120))
    await persist_operation_grant(
        runtime,
        f"desktop.present:{target.target_id}",
        grant_id="grant-editor-present",
        operation=CapabilityOperation.DESKTOP_PRESENT,
    )
    with pytest.raises(EditorContextError) as unverified:
        await runtime.present_editor_finding(
            receipt.task.task_id,
            EditorFindingPresentationRequest(
                context_id=context.context_id,
                result_id=report.result.result_id,
                finding_id="invented-finding",
            ),
            grant_id="grant-editor-present",
            device_id="device-local",
        )
    assert unverified.value.code == "finding_unverified"
    assert queue.empty()

    command = await runtime.present_editor_finding(
        receipt.task.task_id,
        EditorFindingPresentationRequest(
            context_id=context.context_id,
            result_id=report.result.result_id,
            finding_id="finding-gamma",
        ),
        grant_id="grant-editor-present",
        device_id="device-local",
    )
    assert command.verb is EmbodimentVerb.SHOW_MARKER
    assert command.target_id == context.context_id
    assert command.target_rect == ScreenRect(x=100, y=150, width=300, height=30)
    assert queue.get_nowait() == command


@pytest.mark.asyncio
async def test_missing_changed_or_out_of_root_metadata_is_never_guessed(
    editor_runtime: tuple[SoraRuntime, Path, bytes], tmp_path: Path
) -> None:
    runtime, repository, document = editor_runtime
    target = await acquire_selection_target(runtime)
    original = context_request(repository, document, target.target_id)

    for grant_id, request, expected in (
        (
            "grant-editor-changed",
            original.model_copy(update={"document_sha256": "0" * 64}),
            "document_changed",
        ),
        (
            "grant-editor-selection",
            original.model_copy(update={"selected_text": "guessed"}),
            "selection_mismatch",
        ),
    ):
        await persist_operation_grant(
            runtime,
            str((repository / "sample.py").resolve()),
            grant_id=grant_id,
            operation=CapabilityOperation.PATH_READ,
        )
        with pytest.raises(EditorContextError) as failure:
            await runtime.capture_editor_context(
                request,
                grant_id=grant_id,
                device_id="device-local",
            )
        assert failure.value.code == expected

    outside = tmp_path / "outside"
    outside.mkdir()
    outside_file = outside / "other.py"
    outside_file.write_text("private\n", encoding="utf-8")
    outside_request = original.model_copy(
        update={
            "repository_root": str(outside),
            "relative_file_path": "other.py",
            "document_sha256": hashlib.sha256(b"private\n").hexdigest(),
            "selected_text": "private",
            "selection": EditorSelection(
                start=EditorPosition(line=1, column=1),
                end=EditorPosition(line=1, column=8),
            ),
        }
    )
    with pytest.raises(EditorContextError) as disallowed:
        await runtime.capture_editor_context(
            outside_request,
            grant_id="not-consulted",
            device_id="device-local",
        )
    assert disallowed.value.code == "repository_not_allowed"


@pytest.mark.asyncio
async def test_editor_task_and_finding_api_are_typed(
    editor_runtime: tuple[SoraRuntime, Path, bytes],
) -> None:
    runtime, repository, document = editor_runtime
    target = await acquire_selection_target(runtime)
    request = context_request(repository, document, target.target_id)
    handler = RouteHandler(runtime)
    await persist_operation_grant(
        runtime,
        str((repository / "sample.py").resolve()),
        grant_id="grant-editor-api-read",
        operation=CapabilityOperation.PATH_READ,
    )
    response = await handler.handle_request(
        HttpRequest(
            "POST",
            "/api/v1/editor/tasks",
            headers={
                "x-sora-grant-id": "grant-editor-api-read",
                "x-sora-device-id": "device-local",
            },
            body=(
                "{"
                '"intent":"Inspect this exact selection",'
                f'"editor_context":{request.model_dump_json()}'
                "}"
            ).encode(),
        )
    )
    assert response.status_code == 201
    payload = response.parse_json()
    task_id = payload["task_id"]
    context_id = payload["editor_context_id"]
    report = await runtime.wait_for_task(task_id, timeout=2)
    assert report.result is not None

    queue = runtime.register_embodiment_queue()
    runtime.windows_bridge = SequenceBridge(observation())
    await persist_operation_grant(
        runtime,
        f"desktop.present:{target.target_id}",
        grant_id="grant-editor-api-present",
        operation=CapabilityOperation.DESKTOP_PRESENT,
    )
    finding = await handler.handle_request(
        HttpRequest(
            "POST",
            f"/api/v1/tasks/{task_id}/editor-finding",
            headers={
                "x-sora-grant-id": "grant-editor-api-present",
                "x-sora-device-id": "device-local",
            },
            body=(
                "{"
                f'"context_id":"{context_id}",'
                f'"result_id":"{report.result.result_id}",'
                '"finding_id":"finding-gamma"'
                "}"
            ).encode(),
        )
    )
    assert finding.status_code == 200
    assert finding.parse_json()["command"]["target_id"] == context_id
    assert queue.get_nowait().verb is EmbodimentVerb.SHOW_MARKER

    invalid = await handler.handle_request(
        HttpRequest(
            "POST",
            "/api/v1/editor/tasks",
            headers={"x-sora-device-id": "device-local"},
            body=b'{"intent":"Guess it","editor_context":{"editor_name":"fixture"}}',
        )
    )
    assert invalid.status_code == 400
    assert invalid.parse_json()["error"]["code"] == "INVALID_REQUEST"
