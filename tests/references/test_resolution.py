"""P10.6 conversational reference reuse, ambiguity, expiry, pinning and revalidation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from tests.authorization_helpers import persist_operation_grant

from sora.api.protocol import HttpRequest
from sora.api.routes import RouteHandler
from sora.contracts.content import (
    ContentReference,
    ReferenceCandidate,
    ReferenceKind,
    ReferencePinRequest,
    ReferenceResolutionStatus,
    ReferenceResolveRequest,
)
from sora.contracts.desktop import (
    DesktopNode,
    DesktopObservation,
    DesktopObservationRequest,
    DesktopTargetRequest,
)
from sora.contracts.embodiment import ScreenRect
from sora.contracts.models import AttentionTarget, CapabilityOperation
from sora.desktop import WindowsObservationBridge
from sora.providers.mock import DeterministicProvider
from sora.references import ReferenceResolver
from sora.runtime.service import RuntimeConfig, SoraRuntime

ROOT = Path(__file__).resolve().parents[2]


class SequenceBridge(WindowsObservationBridge):
    def __init__(self, *results: DesktopObservation) -> None:
        super().__init__(Path("unused"))
        self.results = list(results)

    async def observe(self, request: DesktopObservationRequest) -> DesktopObservation:
        assert self.results
        return self.results.pop(0)


def observation(x: int) -> DesktopObservation:
    return DesktopObservation(
        status="ok",
        nodes=(
            DesktopNode(
                node_id="node-reference",
                process_id=123,
                window_handle=456,
                name="Reference fixture",
                automation_id="reference-fixture",
                control_type="ControlType.Button",
                runtime_id=(42, 8),
                rect=ScreenRect(x=x, y=100, width=120, height=40),
                focused=False,
                enabled=True,
                offscreen=False,
                password=False,
            ),
        ),
        process_started_at=datetime(2026, 9, 14, 20, 0, tzinfo=UTC),
    )


@pytest_asyncio.fixture
async def runtime(tmp_path: Path) -> AsyncIterator[SoraRuntime]:
    instance = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=ROOT / "identity"),
        provider=DeterministicProvider(),
    )
    await instance.start()
    try:
        yield instance
    finally:
        await instance.close()


def test_candidate_kinds_ambiguity_expiry_and_pinned_spatial_staleness(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 9, 14, 20, 0, tzinfo=UTC)
    resolver = ReferenceResolver()
    resolver.remember_content(
        ContentReference(
            reference_id="content:project:sora",
            kind="repository",
            label="SORA project",
            owner_id="owner-local",
            device_id="device-local",
            project_id="project-sora",
            path=tmp_path.resolve(),
            root=tmp_path.resolve(),
            created_at=now,
        )
    )
    resolver.remember_content(
        ContentReference(
            reference_id="content:document:status",
            kind="document",
            label="status report",
            owner_id="owner-local",
            device_id="device-local",
            project_id="project-sora",
            path=(tmp_path / "status.pdf").resolve(),
            root=tmp_path.resolve(),
            created_at=now,
        )
    )
    for index, name in enumerate(("alpha.py", "beta.py")):
        path = (tmp_path / name).resolve()
        resolver.remember_content(
            ContentReference(
                reference_id=f"content:file:{index}",
                kind="file",
                label=name,
                owner_id="owner-local",
                device_id="device-local",
                project_id="project-sora",
                path=path,
                root=tmp_path.resolve(),
                created_at=now,
            )
        )
    resolver.remember_task(
        "task-fixture",
        label="Fix the parser",
        owner_id="owner-local",
        device_id="device-local",
        project_id="project-sora",
        created_at=now,
    )
    resolver.remember_object(
        "obj-board",
        label="Kanban board",
        owner_id="owner-local",
        device_id="device-local",
        project_id="project-sora",
        created_at=now,
    )

    ambiguous = resolver.resolve(
        ReferenceResolveRequest(utterance="Open this file"),
        owner_id="owner-local",
        device_id="device-local",
        project_id="project-sora",
        now=now,
    )
    assert ambiguous.status is ReferenceResolutionStatus.CLARIFICATION_REQUIRED
    assert {item.kind for item in ambiguous.alternatives} == {ReferenceKind.FILE}

    task = resolver.resolve(
        ReferenceResolveRequest(utterance="Show the parser task"),
        owner_id="owner-local",
        device_id="device-local",
        project_id="project-sora",
        now=now,
    )
    assert task.status is ReferenceResolutionStatus.RESOLVED
    assert task.candidate is not None and task.candidate.task_id == "task-fixture"
    board = resolver.resolve(
        ReferenceResolveRequest(utterance="Where is the Kanban board?"),
        owner_id="owner-local",
        device_id="device-local",
        project_id="project-sora",
        now=now,
    )
    assert board.status is ReferenceResolutionStatus.RESOLVED
    assert board.candidate is not None and board.candidate.object_id == "obj-board"
    project = resolver.resolve(
        ReferenceResolveRequest(utterance="Show the SORA project"),
        owner_id="owner-local",
        device_id="device-local",
        project_id="project-sora",
        now=now,
    )
    assert project.status is ReferenceResolutionStatus.RESOLVED
    assert project.candidate is not None and project.candidate.kind is ReferenceKind.PROJECT
    document = resolver.resolve(
        ReferenceResolveRequest(utterance="Open the status report"),
        owner_id="owner-local",
        device_id="device-local",
        project_id="project-sora",
        now=now,
    )
    assert document.status is ReferenceResolutionStatus.RESOLVED
    assert document.candidate is not None and document.candidate.kind is ReferenceKind.DOCUMENT
    wrong_scope = resolver.resolve(
        ReferenceResolveRequest(utterance="Show the SORA project"),
        owner_id="owner-local",
        device_id="device-other",
        project_id="project-sora",
        now=now,
    )
    assert wrong_scope.status is ReferenceResolutionStatus.NOT_FOUND

    expired_candidate = ReferenceCandidate(
        reference_id="reference:expired",
        kind=ReferenceKind.UI,
        label="expired control",
        owner_id="owner-local",
        device_id="device-local",
        project_id="project-sora",
        created_at=now,
        expires_at=now + timedelta(seconds=1),
        last_referenced_at=now,
        attention_target_id="attention-expired",
        provenance="fixture",
    )
    resolver.remember_candidate(expired_candidate)
    expired = resolver.resolve(
        ReferenceResolveRequest(
            utterance="Show it", explicit_reference_id=expired_candidate.reference_id
        ),
        owner_id="owner-local",
        device_id="device-local",
        project_id="project-sora",
        now=now + timedelta(seconds=2),
    )
    assert expired.status is ReferenceResolutionStatus.EXPIRED

    spatial = ReferenceCandidate(
        reference_id="reference:spatial",
        kind=ReferenceKind.UI,
        label="temporary selection",
        owner_id="owner-local",
        device_id="device-local",
        project_id="project-sora",
        created_at=now,
        expires_at=now + timedelta(seconds=2),
        last_referenced_at=now,
        attention_target_id="attention-spatial",
        screen_rect=ScreenRect(x=100, y=100, width=50, height=20),
        topology_revision=1,
        spatial_expires_at=now + timedelta(seconds=2),
        provenance="fixture",
    )
    resolver.remember_candidate(spatial, current=True)
    pinned = resolver.pin(
        spatial.reference_id,
        owner_id="owner-local",
        device_id="device-local",
        project_id="project-sora",
        ttl_seconds=60,
        now=now + timedelta(seconds=1),
    )
    assert pinned.pinned and pinned.expires_at > spatial.expires_at
    stale = resolver.resolve(
        ReferenceResolveRequest(utterance="Look at it"),
        owner_id="owner-local",
        device_id="device-local",
        project_id="project-sora",
        now=now + timedelta(seconds=3),
    )
    assert stale.status is ReferenceResolutionStatus.STALE
    assert stale.reason == "spatial_reference_requires_reacquisition"


@pytest.mark.asyncio
async def test_same_target_reuse_low_confidence_clarification_and_api_pin(
    runtime: SoraRuntime,
) -> None:
    now = datetime.now(UTC)
    target = AttentionTarget(
        target_id="attention-chain",
        source="selection",
        created_at=now,
        expires_at=now + timedelta(seconds=30),
        owner_id=runtime.config.owner_id,
        device_id="device-local",
        project_id=runtime.config.project_id,
        ui_element="selected parser",
        screen_rect=(100, 100, 80, 30),
        topology_revision=runtime.topology_manager.revision,
        confidence=0.95,
        provenance="fixture",
    )
    candidate = runtime.reference_resolver.remember_attention(target)
    first = await runtime.resolve_reference(
        ReferenceResolveRequest(utterance="Look at this"),
        device_id="device-local",
    )
    second = await runtime.resolve_reference(
        ReferenceResolveRequest(utterance="Can Cody fix it?"),
        device_id="device-local",
    )
    assert first.status is second.status is ReferenceResolutionStatus.RESOLVED
    assert first.candidate is not None and second.candidate is not None
    assert first.candidate.reference_id == second.candidate.reference_id == candidate.reference_id

    handler = RouteHandler(runtime)
    api_resolution = await handler.handle_request(
        HttpRequest(
            "POST",
            "/api/v1/references/resolve",
            headers={"x-sora-device-id": "device-local"},
            body=ReferenceResolveRequest(utterance="Can Cody fix it?").model_dump_json().encode(),
        )
    )
    assert api_resolution.status_code == 200
    assert api_resolution.parse_json()["candidate"]["reference_id"] == candidate.reference_id
    api_pin = await handler.handle_request(
        HttpRequest(
            "POST",
            "/api/v1/references/pin",
            headers={"x-sora-device-id": "device-local"},
            body=ReferencePinRequest(reference_id=candidate.reference_id, ttl_seconds=120)
            .model_dump_json()
            .encode(),
        )
    )
    assert api_pin.status_code == 200
    assert api_pin.parse_json()["pinned"] is True

    receipt, delegated_resolution = await runtime.submit_referenced_task(
        "Analyze the referenced selection",
        ReferenceResolveRequest(utterance="Can Cody fix it?"),
        device_id="device-local",
        explicit_provider="deterministic-mock",
    )
    assert delegated_resolution.status is ReferenceResolutionStatus.RESOLVED
    assert receipt is not None
    assert receipt.task.reference_context[0].reference_id == candidate.reference_id
    await runtime.wait_for_task(receipt.task.task_id)
    provider = runtime.provider
    assert isinstance(provider, DeterministicProvider)
    provider_request = provider._requests[receipt.run.run_id]
    assert "REFERENCE_CONTEXT_V1" in provider_request.context
    assert candidate.reference_id in provider_request.context
    referenced_task = await handler.handle_request(
        HttpRequest(
            "POST",
            "/api/v1/tasks",
            headers={"x-sora-device-id": "device-local"},
            body=(
                '{"intent":"Review the referenced selection",'
                '"explicit_provider":"deterministic-mock",'
                f'"reference_id":"{candidate.reference_id}"}}'
            ).encode(),
        )
    )
    assert referenced_task.status_code == 201
    assert referenced_task.parse_json()["referent_ids"] == [candidate.reference_id]

    low = target.model_copy(
        update={
            "target_id": "attention-low",
            "confidence": 0.4,
            "screen_rect": (300, 200, 90, 40),
        }
    )
    runtime.reference_resolver.remember_attention(low)
    queue = runtime.register_embodiment_queue()
    await persist_operation_grant(
        runtime,
        "desktop.present:reference-clarification",
        grant_id="grant-reference-clarification",
        operation=CapabilityOperation.DESKTOP_PRESENT,
    )
    clarification = await runtime.resolve_reference(
        ReferenceResolveRequest(utterance="Look at this"),
        device_id="device-local",
        clarification_grant_id="grant-reference-clarification",
    )
    assert clarification.status is ReferenceResolutionStatus.CLARIFICATION_REQUIRED
    assert clarification.clarification_marker_queued
    command = queue.get_nowait()
    assert command.target_rect == ScreenRect(x=300, y=200, width=90, height=40)
    assert command.target_id == clarification.resolution_id

    for index, rect in enumerate(
        (
            ScreenRect(x=20, y=20, width=40, height=40),
            ScreenRect(x=100, y=80, width=60, height=30),
        )
    ):
        runtime.reference_resolver.remember_candidate(
            ReferenceCandidate(
                reference_id=f"reference:duplicate:{index}",
                kind=ReferenceKind.UI,
                label="duplicate target",
                owner_id=runtime.config.owner_id,
                device_id="device-local",
                project_id=runtime.config.project_id,
                created_at=now,
                expires_at=now + timedelta(seconds=30),
                last_referenced_at=now,
                confidence=0.9,
                attention_target_id=f"attention-duplicate-{index}",
                screen_rect=rect,
                topology_revision=runtime.topology_manager.revision,
                spatial_expires_at=now + timedelta(seconds=30),
                provenance="fixture",
            )
        )
    await persist_operation_grant(
        runtime,
        "desktop.present:reference-clarification",
        grant_id="grant-ambiguous-clarification",
        operation=CapabilityOperation.DESKTOP_PRESENT,
    )
    ambiguous = await runtime.resolve_reference(
        ReferenceResolveRequest(utterance="Which duplicate target?"),
        device_id="device-local",
        clarification_grant_id="grant-ambiguous-clarification",
    )
    assert ambiguous.status is ReferenceResolutionStatus.CLARIFICATION_REQUIRED
    assert ambiguous.reason == "multiple_labels_match"
    assert ambiguous.clarification_marker_queued
    ambiguous_marker = queue.get_nowait()
    assert ambiguous_marker.target_rect == ScreenRect(x=20, y=20, width=140, height=90)


@pytest.mark.asyncio
async def test_moved_desktop_reference_revalidates_before_reuse(runtime: SoraRuntime) -> None:
    request = DesktopTargetRequest(
        process_id=123,
        window_handle=999,
        runtime_id=(42, 8),
        automation_id="reference-fixture",
        control_type="ControlType.Button",
    )
    runtime.windows_bridge = SequenceBridge(observation(100))
    await persist_operation_grant(
        runtime,
        request.observation_request.resource,
        grant_id="grant-reference-observe",
        operation=CapabilityOperation.DESKTOP_OBSERVE,
    )
    desktop_target = await runtime.acquire_desktop_target(
        request,
        grant_id="grant-reference-observe",
        device_id="device-local",
    )
    now = datetime.now(UTC)
    runtime.reference_resolver.remember_attention(
        AttentionTarget(
            target_id="attention-desktop",
            source="click",
            created_at=now,
            expires_at=now + timedelta(seconds=30),
            owner_id=runtime.config.owner_id,
            device_id="device-local",
            project_id=runtime.config.project_id,
            ui_element="moving fixture",
            screen_rect=(100, 100, 120, 40),
            confidence=1,
            topology_revision=runtime.topology_manager.revision,
            desktop_target_id=desktop_target.target_id,
            provenance="fixture",
        )
    )
    runtime.windows_bridge = SequenceBridge(observation(260))
    await persist_operation_grant(
        runtime,
        f"desktop.present:{desktop_target.target_id}",
        grant_id="grant-reference-revalidate",
        operation=CapabilityOperation.DESKTOP_PRESENT,
    )
    resolved = await runtime.resolve_reference(
        ReferenceResolveRequest(utterance="Look at this"),
        device_id="device-local",
        revalidation_grant_id="grant-reference-revalidate",
    )
    assert resolved.status is ReferenceResolutionStatus.RESOLVED
    assert resolved.candidate is not None
    assert resolved.candidate.screen_rect == ScreenRect(x=260, y=100, width=120, height=40)


@pytest.mark.asyncio
async def test_canonical_task_reference_is_rebuilt_after_restart(tmp_path: Path) -> None:
    config = RuntimeConfig(root=tmp_path, identity_root=ROOT / "identity")
    first = SoraRuntime(config, provider=DeterministicProvider())
    await first.start()
    receipt = await first.submit_task("Inspect the restart fixture")
    await first.close()

    second = SoraRuntime(config, provider=DeterministicProvider())
    await second.start()
    try:
        resolution = await second.resolve_reference(
            ReferenceResolveRequest(
                utterance="Show this task",
                explicit_reference_id=f"task:{receipt.task.task_id}",
            ),
            device_id="device-local",
        )
        assert resolution.status is ReferenceResolutionStatus.RESOLVED
        assert resolution.candidate is not None
        assert resolution.candidate.task_id == receipt.task.task_id
    finally:
        await second.close()
