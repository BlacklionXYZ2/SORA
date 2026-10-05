"""P10.7 configured content opening, path safety, ambiguity and API acceptance."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.authorization_helpers import persist_operation_grant

from sora.api.protocol import HttpRequest
from sora.api.routes import RouteHandler
from sora.content import ContentNavigationError
from sora.contracts.content import (
    ContentHandlerConfig,
    ContentNavigateRequest,
    ContentNavigationStatus,
    ContentReference,
)
from sora.contracts.desktop import (
    DesktopNode,
    DesktopObservation,
    DesktopObservationRequest,
    DesktopTargetRequest,
)
from sora.contracts.embodiment import ScreenRect
from sora.contracts.models import CapabilityOperation
from sora.desktop import WindowsObservationBridge
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime

ROOT = Path(__file__).resolve().parents[2]


class StaticBridge(WindowsObservationBridge):
    def __init__(self, result: DesktopObservation) -> None:
        super().__init__(Path("unused"))
        self.result = result

    async def observe(self, request: DesktopObservationRequest) -> DesktopObservation:
        return self.result


def make_handler_script(path: Path) -> None:
    path.write_text(
        "import json, pathlib, sys\n"
        "pathlib.Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:]), encoding='utf-8')\n",
        encoding="utf-8",
    )


async def make_runtime(
    tmp_path: Path,
    *,
    supports_line: bool = True,
    verbs: tuple[str, ...] = ("open", "show", "where"),
) -> tuple[SoraRuntime, Path, Path]:
    content_root = tmp_path / "content"
    content_root.mkdir()
    output = tmp_path / "handler-output.json"
    script = tmp_path / "handler.py"
    make_handler_script(script)
    handler = ContentHandlerConfig.model_validate(
        {
            "handler_id": "fixture-handler",
            "kinds": ["repository", "file", "artifact"],
            "executable": sys.executable,
            "arguments": [
                str(script),
                str(output),
                "{path}",
                "{line}",
                "{column}",
                "{verb}",
                "{reference_id}",
            ],
            "verbs": verbs,
            "supports_line": supports_line,
            "supports_column": supports_line,
            "supports_highlight": supports_line,
            "completion_timeout_seconds": 2,
        }
    )
    runtime = SoraRuntime(
        RuntimeConfig(
            root=tmp_path / "state",
            identity_root=ROOT / "identity",
            content_roots=(content_root,),
            content_handlers=(handler,),
        ),
        provider=DeterministicProvider(),
    )
    await runtime.start()
    return runtime, content_root, output


def reference(root: Path, path: Path, reference_id: str) -> ContentReference:
    return ContentReference(
        reference_id=reference_id,
        kind="file",
        label=path.name,
        owner_id="owner-local",
        device_id="device-local",
        project_id="project-sora",
        path=path.resolve(),
        root=root.resolve(),
        line=3,
        column=2,
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_configured_handler_opens_exact_file_without_shell_and_api_redacts_config(
    tmp_path: Path,
) -> None:
    runtime, content_root, output = await make_runtime(tmp_path)
    try:
        target = content_root / "strange & name.txt"
        target.write_text("one\ntwo\nthree\n", encoding="utf-8")
        candidate = runtime.register_content_reference(
            reference(content_root, target, "content:file:shell-safe"),
            current=True,
        )
        await persist_operation_grant(
            runtime,
            f"desktop.navigate:{candidate.reference_id}",
            grant_id="grant-content-open",
            operation=CapabilityOperation.DESKTOP_NAVIGATE,
        )
        handler = RouteHandler(runtime)
        listed = await handler.handle_request(
            HttpRequest(
                "GET", "/api/v1/content/references",
                headers={"x-sora-device-id": "device-local"}, body=b"",
            )
        )
        assert listed.status_code == 200
        assert candidate.reference_id in {
            item["reference_id"] for item in listed.parse_json()["references"]
        }
        other_device = await handler.handle_request(
            HttpRequest(
                "GET", "/api/v1/content/references",
                headers={"x-sora-device-id": "another-device"}, body=b"",
            )
        )
        assert other_device.parse_json()["references"] == []
        response = await handler.handle_request(
            HttpRequest(
                "POST",
                "/api/v1/content/navigate",
                headers={
                    "x-sora-grant-id": "grant-content-open",
                    "x-sora-device-id": "device-local",
                },
                body=ContentNavigateRequest(
                    utterance="Open it",
                    verb="open",
                    explicit_reference_id=candidate.reference_id,
                )
                .model_dump_json()
                .encode(),
            )
        )
        assert response.status_code == 200
        payload = response.parse_json()
        assert payload["status"] == "opened"
        arguments = json.loads(output.read_text(encoding="utf-8"))
        assert arguments == [
            str(target.resolve()),
            "3",
            "2",
            "open",
            candidate.reference_id,
        ]
        assert not (tmp_path / "calc.exe").exists()

        settings = await handler.handle_request(
            HttpRequest("GET", "/api/v1/projections/settings", headers={}, body=b"")
        )
        settings_payload = settings.parse_json()
        assert settings_payload["content_handlers"][0]["handler_id"] == "fixture-handler"
        assert "executable" not in settings_payload["content_handlers"][0]
        trace_fields = await runtime.repository.database.read(
            lambda database: tuple(
                str(row[0]) for row in database.execute("SELECT fields_json FROM traces")
            )
        )
        assert all(str(target.resolve()) not in fields for fields in trace_fields)

        # The same configured handler contract covers repository and artifact
        # references; they are not silently coerced to an arbitrary file.
        repository = runtime.register_content_reference(
            ContentReference(
                reference_id="content:repository:sora-fixture",
                kind="repository",
                label="SORA fixture",
                owner_id="owner-local",
                device_id="device-local",
                project_id="project-sora",
                path=content_root.resolve(),
                root=content_root.resolve(),
                created_at=datetime.now(UTC),
            )
        )
        await persist_operation_grant(
            runtime,
            f"desktop.navigate:{repository.reference_id}",
            grant_id="grant-repository-show",
            operation=CapabilityOperation.DESKTOP_NAVIGATE,
        )
        repository_result = await runtime.navigate_content(
            ContentNavigateRequest(
                utterance="Show the fixture repository",
                verb="show",
                explicit_reference_id=repository.reference_id,
            ),
            navigation_grant_id="grant-repository-show",
            device_id="device-local",
        )
        assert repository_result.status is ContentNavigationStatus.OPENED
        assert json.loads(output.read_text(encoding="utf-8"))[0] == str(content_root.resolve())

        artifact_path = content_root / "result.artifact"
        artifact_path.write_text("artifact", encoding="utf-8")
        artifact = runtime.register_content_reference(
            reference(content_root, artifact_path, "content:artifact:result").model_copy(
                update={"kind": "artifact", "line": None, "column": None}
            )
        )
        await persist_operation_grant(
            runtime,
            f"desktop.navigate:{artifact.reference_id}",
            grant_id="grant-artifact-open",
            operation=CapabilityOperation.DESKTOP_NAVIGATE,
        )
        artifact_result = await runtime.navigate_content(
            ContentNavigateRequest(
                utterance="Open the result",
                verb="open",
                explicit_reference_id=artifact.reference_id,
            ),
            navigation_grant_id="grant-artifact-open",
            device_id="device-local",
        )
        assert artifact_result.status is ContentNavigationStatus.OPENED
        artifact_arguments = json.loads(output.read_text(encoding="utf-8"))
        assert artifact_arguments[0] == str(artifact_path.resolve())
        assert artifact_arguments[1:3] == ["", ""]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_ambiguous_missing_unsupported_and_wrong_grants_fail_before_launch(
    tmp_path: Path,
) -> None:
    runtime, content_root, output = await make_runtime(tmp_path, verbs=("open",))
    try:
        first_path = content_root / "first.py"
        second_path = content_root / "second.py"
        first_path.write_text("first", encoding="utf-8")
        second_path.write_text("second", encoding="utf-8")
        first = runtime.register_content_reference(
            reference(content_root, first_path, "content:file:first")
        )
        runtime.register_content_reference(
            reference(content_root, second_path, "content:file:second")
        )
        await persist_operation_grant(
            runtime,
            f"desktop.navigate:{first.reference_id}",
            grant_id="grant-content-unused",
            operation=CapabilityOperation.DESKTOP_NAVIGATE,
        )
        ambiguous = await runtime.navigate_content(
            ContentNavigateRequest(utterance="Open this file", verb="open"),
            navigation_grant_id="grant-content-unused",
            device_id="device-local",
        )
        assert ambiguous.status is ContentNavigationStatus.CLARIFICATION_REQUIRED
        unused = await runtime.repository.get_grant("grant-content-unused")
        assert unused is not None and unused.used_count == 0
        assert not output.exists()

        unsupported = await runtime.navigate_content(
            ContentNavigateRequest(
                utterance="Where is it?",
                verb="where",
                explicit_reference_id=first.reference_id,
            ),
            navigation_grant_id="grant-content-unused",
            device_id="device-local",
        )
        assert unsupported.status is ContentNavigationStatus.UNSUPPORTED
        assert unsupported.reason == "verb_unsupported"
        unused = await runtime.repository.get_grant("grant-content-unused")
        assert unused is not None and unused.used_count == 0

        first_path.unlink()
        missing = await runtime.navigate_content(
            ContentNavigateRequest(
                utterance="Open it",
                verb="open",
                explicit_reference_id=first.reference_id,
            ),
            navigation_grant_id="grant-content-unused",
            device_id="device-local",
        )
        assert missing.status is ContentNavigationStatus.NOT_FOUND
        assert missing.reason == "content_unavailable"
        unused = await runtime.repository.get_grant("grant-content-unused")
        assert unused is not None and unused.used_count == 0

        handler = RouteHandler(runtime)
        wrong_grant = await handler.handle_request(
            HttpRequest(
                "POST",
                "/api/v1/content/navigate",
                headers={
                    "x-sora-grant-id": "grant-content-unused",
                    "x-sora-device-id": "device-local",
                },
                body=ContentNavigateRequest(
                    utterance="Open second",
                    verb="open",
                    explicit_reference_id="content:file:second",
                )
                .model_dump_json()
                .encode(),
            )
        )
        assert wrong_grant.status_code == 403
        assert not output.exists()

        outside = tmp_path / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        with pytest.raises(ContentNavigationError, match="escapes"):
            runtime.register_content_reference(
                reference(content_root, outside, "content:file:outside")
            )
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_unsupported_line_navigation_reports_precise_limitation(tmp_path: Path) -> None:
    runtime, content_root, output = await make_runtime(tmp_path, supports_line=False)
    try:
        target = content_root / "plain.txt"
        target.write_text("plain", encoding="utf-8")
        candidate = runtime.register_content_reference(
            reference(content_root, target, "content:file:limited"),
            current=True,
        )
        await persist_operation_grant(
            runtime,
            f"desktop.navigate:{candidate.reference_id}",
            grant_id="grant-content-limited",
            operation=CapabilityOperation.DESKTOP_NAVIGATE,
        )
        result = await runtime.navigate_content(
            ContentNavigateRequest(
                utterance="Show it",
                verb="show",
                explicit_reference_id=candidate.reference_id,
            ),
            navigation_grant_id="grant-content-limited",
            device_id="device-local",
        )
        assert result.status is ContentNavigationStatus.OPENED_WITH_LIMITATIONS
        assert result.limitations == (
            "handler cannot navigate to a line; opened the content without line targeting",
        )
        arguments = json.loads(output.read_text(encoding="utf-8"))
        assert arguments[1:3] == ["", ""]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_where_opens_content_and_points_with_separate_presentation_authority(
    tmp_path: Path,
) -> None:
    runtime, content_root, output = await make_runtime(tmp_path)
    try:
        started = datetime.now(UTC)
        node = DesktopNode(
            node_id="node-content",
            process_id=321,
            window_handle=654,
            name="Content location",
            automation_id="content-location",
            control_type="ControlType.Document",
            runtime_id=(42, 12),
            rect=ScreenRect(x=400, y=250, width=300, height=180),
            focused=False,
            enabled=True,
            offscreen=False,
            password=False,
        )
        observation = DesktopObservation(
            status="ok",
            nodes=(node,),
            topology_revision=runtime.topology_manager.revision,
            process_started_at=started,
        )
        target_request = DesktopTargetRequest(
            process_id=321,
            window_handle=999,
            runtime_id=node.runtime_id,
            automation_id=node.automation_id,
            control_type=node.control_type,
        )
        desktop_target = runtime.desktop_targets.issue(
            target_request,
            observation,
            owner_id=runtime.config.owner_id,
            device_id="device-local",
            project_id=runtime.config.project_id,
        )
        runtime.windows_bridge = StaticBridge(observation)

        content_path = content_root / "location.txt"
        content_path.write_text("location", encoding="utf-8")
        content = reference(content_root, content_path, "content:file:location").model_copy(
            update={"desktop_target_id": desktop_target.target_id}
        )
        candidate = runtime.register_content_reference(content, current=True)
        await persist_operation_grant(
            runtime,
            f"desktop.navigate:{candidate.reference_id}",
            grant_id="grant-content-where",
            operation=CapabilityOperation.DESKTOP_NAVIGATE,
        )
        await persist_operation_grant(
            runtime,
            f"desktop.present:{desktop_target.target_id}",
            grant_id="grant-content-point",
            operation=CapabilityOperation.DESKTOP_PRESENT,
        )
        queue = runtime.register_embodiment_queue()
        result = await runtime.navigate_content(
            ContentNavigateRequest(
                utterance="Where is it?",
                verb="where",
                explicit_reference_id=candidate.reference_id,
            ),
            navigation_grant_id="grant-content-where",
            presentation_grant_id="grant-content-point",
            device_id="device-local",
        )
        assert result.status is ContentNavigationStatus.OPENED
        assert result.presentation_command_id is not None
        command = queue.get_nowait()
        assert command.command_id == result.presentation_command_id
        assert command.target_rect == node.rect
        arguments = json.loads(output.read_text(encoding="utf-8"))
        assert arguments[3] == "where"
    finally:
        await runtime.close()
