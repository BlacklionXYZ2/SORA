"""HTTP routes and API dispatch handling Core services and projections."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sora.api.events import build_state_snapshot, get_stream_bounds, replay_events_since
from sora.api.lifecycle import ManagedLifecycle
from sora.api.protocol import HttpRequest, HttpResponse
from sora.attention import AttentionResolveRequest, CursorSampleBatch, SelectionSample
from sora.contracts.automation_api import AutomationChange, AutomationCreate, AutomationRunNow
from sora.contracts.base import ContractModel
from sora.contracts.capture import DesktopCaptureRequest
from sora.contracts.content import (
    ContentNavigateRequest,
    ReferencePinRequest,
    ReferenceResolveRequest,
)
from sora.contracts.desktop import (
    DesktopObservationRequest,
    DesktopPresentationRequest,
    DesktopPressRequest,
    DesktopTargetRequest,
    DesktopTargetRevalidationRequest,
    DesktopTypeRequest,
)
from sora.contracts.desktop_events import DesktopEventBatch, DesktopEventSubscriptionRequest
from sora.contracts.desktop_objects import DesktopObjectAffordanceRequest
from sora.contracts.editor import EditorFindingPresentationRequest, EditorTaskRequest
from sora.contracts.embodiment import EmbodimentCommand, MonitorDescriptor, ScreenRect
from sora.contracts.memory_browser import MemoryCorrection, MemoryForget
from sora.contracts.models import (
    ExtensionDepth,
    ExtensionRegistration,
    ReasoningEffort,
    TaskRecord,
)
from sora.contracts.runtime_identity import RuntimeIdentity
from sora.contracts.runtime_lifecycle import RuntimeLifecycle
from sora.contracts.ui_presentation import (
    UiHostCommand,
    UiHostRegistration,
    UiMemoryCommand,
    UiPresentationAck,
)
from sora.contracts.vision import AttentionCropFallbackRequest, VisionEvidenceBatchRequest
from sora.contracts.voice import (
    VoiceDeviceEvent,
    VoiceInterruptionRequest,
    VoicePlaybackEvent,
    VoiceSessionStartRequest,
    VoiceTranscriptEvent,
)
from sora.desktop import DesktopTargetError
from sora.desktop_objects import DesktopObjectAffordanceError
from sora.desktop_objects.kanban import project_tasks_to_kanban
from sora.editor import EditorContextError
from sora.memory.entries import forget_entry
from sora.persistence.records import MessageRecord
from sora.providers.base import ProviderLaunchError
from sora.providers.dialogue import DialogueProviderError, DialogueTimeoutError
from sora.references import ReferenceResolverError
from sora.runtime.app_settings import (
    ReloadRequest,
    SettingsConflict,
    SettingsEdit,
    discover_projectors,
)
from sora.runtime.automation_store import (
    AutomationConflict,
    AutomationStorageError,
    AutomationStore,
)
from sora.runtime.dialogue_turns import (
    DialogueCancelledError,
    DialogueRequestConflict,
    DialogueTurns,
)
from sora.runtime.local_files import LocalFileViewError
from sora.runtime.memory_browser import MemoryProjectionError, memory_detail, memory_page
from sora.runtime.memory_mutations import MemoryMutationConflict, mutate, receipt
from sora.runtime.model_catalog import ModelCatalogError, scan_lm_studio_models
from sora.runtime.service import DesktopVisionError, SoraRuntime
from sora.runtime.settings import RuntimeSettingsUpdate
from sora.runtime.task_history import run_evidence, run_page
from sora.runtime.ui_presentation import UiPresentationError
from sora.security.operations import OperationAuthorizationError
from sora.workspaces import (
    IntegrationAuthorizationError,
    IntegrationConflictError,
    IntegrationValidationError,
)

logger = logging.getLogger(__name__)


class RouteHandler:
    """Dispatches HTTP requests to appropriate Core services and projections."""

    def __init__(self, runtime: SoraRuntime, lifecycle: ManagedLifecycle | None = None) -> None:
        self.runtime = runtime
        self.lifecycle = lifecycle
        self.instance_id = str(uuid.uuid4())
        self.automations = AutomationStore(
            runtime.repository, runtime.config.owner_id, runtime.config.project_id,
            self.instance_id,
            scheduler_state=lambda: runtime.automation_worker.state,
        )
        runtime.memory_presentations.bind(self.instance_id)
        self._memory_cursor_key = os.urandom(32)
        self._extensions: dict[str, ExtensionRegistration] = {}
        self._extension_state_path = runtime.config.root / "data" / "extensions.json"
        self._extension_schemas: dict[str, dict[str, Any]] = {
            "schema-media-player-v1": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "sora://extensions/media-player/1.0.0",
                "type": "object",
                "properties": {"volume": {"type": "integer", "minimum": 0, "maximum": 100}},
                "additionalProperties": False,
            },
            "schema-kanban-board-v1": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "sora://extensions/kanban-board/1.0.0",
                "type": "object",
                "properties": {
                    "columns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    }
                },
                "additionalProperties": False,
            },
        }
        self._initialize_built_in_extensions()
        self._load_extension_state()

    def _initialize_built_in_extensions(self) -> None:
        """P08.6: Registers built-in fake Integration and Desktop Component."""
        ext_integration = ExtensionRegistration(
            extension_id="integration-media-player",
            depth=ExtensionDepth.INTEGRATION,
            version="1.0.0",
            enabled=False,
            capability_ids=("capability-media-pause", "capability-media-play"),
            required_grants=("grant-media-control",),
            schema_ref="schema-media-player-v1",
            config={"provider": "mock-media", "volume": 80},
        )
        ext_component = ExtensionRegistration(
            extension_id="component-kanban-board",
            depth=ExtensionDepth.DESKTOP_COMPONENT,
            version="1.0.0",
            enabled=False,
            capability_ids=("capability-kanban-show", "capability-kanban-move"),
            required_grants=("grant-desktop-render",),
            schema_ref="schema-kanban-board-v1",
            config={"columns": ["TODO", "DOING", "DONE"]},
        )
        self._extensions[ext_integration.extension_id] = ext_integration
        self._extensions[ext_component.extension_id] = ext_component

    def _load_extension_state(self) -> None:
        if not self._extension_state_path.is_file():
            return
        try:
            raw = json.loads(self._extension_state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, dict):
            return
        for ext_id, enabled in raw.items():
            if ext_id in self._extensions and isinstance(enabled, bool):
                self._extensions[ext_id] = self._extensions[ext_id].model_copy(
                    update={"enabled": enabled}
                )

    def _save_extension_state(self) -> None:
        self._extension_state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._extension_state_path.with_suffix(f".tmp-{os.getpid()}")
        temporary.write_text(
            json.dumps(
                {ext_id: ext.enabled for ext_id, ext in sorted(self._extensions.items())},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self._extension_state_path)

    @staticmethod
    def _device_id(request: HttpRequest) -> str:
        return (request.header("X-SORA-Device-ID") or "").strip()

    @staticmethod
    def _grant_id(request: HttpRequest) -> str:
        return (request.header("X-SORA-Grant-ID") or "").strip()

    async def _workspace_is_owned(self, workspace_id: str) -> bool:
        manager = self.runtime.workspace_manager
        if manager is None:
            return False
        try:
            record = manager.load(workspace_id)
        except Exception:
            return False
        task = await self.runtime.repository.get_task(record.task_id)
        return task is not None and task.owner_id == self.runtime.config.owner_id

    async def handle_request(
        self, request: HttpRequest, *, remote_scopes: frozenset[str] | None = None
    ) -> HttpResponse:
        method = request.method
        path = request.path.rstrip("/")
        if not path:
            path = "/"

        try:
            if method == "GET" and path == "/api/v1/runtime/identity":
                if remote_scopes is not None:
                    return HttpResponse.error(
                        403,
                        "Runtime identity is owner-local",
                        code="FORBIDDEN",
                    )
                identity = RuntimeIdentity(
                    instance_id=self.instance_id,
                    state_root=str(self.runtime.config.root.resolve()),
                    owner_id=self.runtime.config.owner_id,
                    project_id=self.runtime.config.project_id,
                )
                return HttpResponse.json(identity.model_dump(mode="json"))

            expected_instance = request.header("X-SORA-Core-Instance")
            if expected_instance is not None and expected_instance != self.instance_id:
                return HttpResponse.error(
                    409,
                    "Core instance changed; resync before retrying",
                    code="RUNTIME_CHANGED",
                )

            if path in {"/api/v1/runtime/lifecycle", "/api/v1/runtime/shutdown"}:
                if remote_scopes is not None:
                    return HttpResponse.error(
                        403, "Runtime lifecycle is owner-local", code="FORBIDDEN"
                    )
                if method == "GET" and path == "/api/v1/runtime/lifecycle":
                    lifecycle = (
                        self.lifecycle.projection(self.instance_id)
                        if self.lifecycle
                        else (
                            RuntimeLifecycle(
                                instance_id=uuid.UUID(self.instance_id), state="external"
                            )
                        )
                    )
                    return HttpResponse.json(lifecycle.model_dump(mode="json"))
                if method == "POST" and path == "/api/v1/runtime/shutdown":
                    if self.lifecycle is None:
                        return HttpResponse.error(
                            403,
                            "External Core is not owned by a desktop host",
                            code="HOST_OWNERSHIP_REQUIRED",
                        )
                    response = self.lifecycle.request_shutdown(request, self.instance_id)
                    if self.lifecycle.shutdown_requested:
                        self.runtime.automation_worker.fence()
                    return response
                return HttpResponse.error(
                    405, "Unsupported lifecycle method", code="METHOD_NOT_ALLOWED"
                )

            if self.lifecycle is not None and self.lifecycle.shutdown_requested and method != "GET":
                return HttpResponse.error(
                    503,
                    "Core is shutting down; no new effects are admitted",
                    code="RUNTIME_SHUTTING_DOWN",
                )

            # 1. Health and Liveness (P08.4)
            if (
                path == "/api/v1/automations"
                or path.startswith("/api/v1/automations/")
                or path.startswith("/api/v1/automation-requests/")
            ):
                if remote_scopes is not None:
                    return HttpResponse.error(403, "Automations are owner-local", code="FORBIDDEN")
                return await self._handle_automations(request, path)
            if path.startswith("/api/v1/ui/"):
                if remote_scopes is not None:
                    return HttpResponse.error(
                        403, "UI presentation is owner-local", code="FORBIDDEN"
                    )
                return await self._handle_ui_presentation(request, path)
            if path.startswith("/api/v1/memory-mutations/"):
                if remote_scopes is not None:
                    return HttpResponse.error(
                        403, "Memory receipts are owner-local", code="FORBIDDEN"
                    )
                if method != "GET":
                    return HttpResponse.error(
                        405, "Receipts are read-only", code="METHOD_NOT_ALLOWED"
                    )
                return await self._handle_memory_mutation(request, path, receipt_only=True)
            if path == "/api/v1/memories" or path.startswith("/api/v1/memories/"):
                if remote_scopes is not None:
                    return HttpResponse.error(
                        403, "Memory browsing is owner-local", code="FORBIDDEN"
                    )
                parts = path.removeprefix("/api/v1/memories/").split("/")
                if len(parts) == 2 and parts[1] in {"correct", "forget"}:
                    if method != "POST":
                        return HttpResponse.error(
                            405, "Mutation requires POST", code="METHOD_NOT_ALLOWED"
                        )
                    return await self._handle_memory_mutation(request, path)
                if method != "GET":
                    return HttpResponse.error(
                        405, "Memory browser is read-only", code="METHOD_NOT_ALLOWED"
                    )
                return await self._handle_memories(request, path)

            if method == "GET" and path == "/healthz":
                return HttpResponse.json({"status": "ok", "service": "sora-core"})

            if method == "GET" and path == "/readyz":
                await self.runtime.repository.database.read(lambda db: True)
                degraded: list[str] = []
                for provider_name, provider in self.runtime.providers.items():
                    try:
                        await provider.capabilities()
                    except Exception:
                        degraded.append(provider_name)
                if degraded:
                    return HttpResponse.json(
                        {
                            "status": "degraded",
                            "database": "connected",
                            "unavailable_providers": degraded,
                        },
                        status_code=503,
                    )
                return HttpResponse.json({"status": "ready", "database": "connected"})

            if method == "GET" and path == "/api/v1/status":
                return await self._handle_get_status()

            if method == "GET" and path == "/api/v1/events":
                return await self._handle_poll_events(request, local=remote_scopes is None)

            # 2. Task Endpoints (P08.1)
            if method == "POST" and path == "/api/v1/tasks":
                return await self._handle_submit_task(request)

            if (method, path) in {
                ("GET", "/api/v1/paths"),
                ("POST", "/api/v1/paths/reconcile"),
            }:
                if remote_scopes is not None:
                    return HttpResponse.error(
                        403,
                        "Project paths are owner-local",
                        code="FORBIDDEN",
                    )
                if method == "POST":
                    await self.runtime.project_paths.reconcile()
                return HttpResponse.json(await self.runtime.project_paths.projection())

            if (method, path) in {
                ("GET", "/api/v1/agents/catalogue"),
                ("POST", "/api/v1/agents/catalogue/refresh"),
            }:
                if remote_scopes is not None:
                    return HttpResponse.error(
                        403,
                        "Agent inventory is owner-local",
                        code="FORBIDDEN",
                    )
                catalogue = self.runtime.agent_catalogue
                return HttpResponse.json(
                    await catalogue.refresh() if method == "POST" else await catalogue.snapshot()
                )

            if method == "POST" and path == "/api/v1/editor/tasks":
                return await self._handle_submit_editor_task(request)

            if method == "GET" and path == "/api/v1/tasks":
                return await self._handle_list_tasks(request, local=remote_scopes is None)

            if method == "POST" and path == "/api/v1/board/cards":
                return await self._handle_plan_board_card(request)

            if method == "POST" and path.startswith("/api/v1/board/cards/"):
                parts = path[len("/api/v1/board/cards/") :].split("/")
                if len(parts) == 2 and parts[1] == "start":
                    return await self._handle_start_board_card(parts[0], request)
                if len(parts) == 2 and parts[1] == "retry":
                    return await self._handle_retry_board_card(parts[0])
                if len(parts) == 2 and parts[1] in {"move", "assign", "remove"}:
                    return await self._handle_update_board_card(parts[0], parts[1], request)

            if path.startswith("/api/v1/tasks/"):
                subpath = path[len("/api/v1/tasks/") :]
                parts = subpath.split("/")
                task_id = parts[0]
                if method == "GET" and len(parts) in {2, 3} and parts[1] == "runs":
                    if remote_scopes is not None:
                        return HttpResponse.error(
                            403, "Run evidence is owner-local", code="FORBIDDEN"
                        )
                    return await self._handle_task_runs(
                        task_id, parts[2] if len(parts) == 3 else None, request
                    )
                if len(parts) == 1 and method == "GET":
                    return await self._handle_get_task(task_id, local=remote_scopes is None)
                if len(parts) == 2 and parts[1] == "evidence" and method == "GET":
                    if remote_scopes is not None:
                        return HttpResponse.error(403, "Task evidence is owner-local")
                    return await self._handle_task_evidence(task_id)
                if len(parts) == 2 and method == "POST":
                    action = parts[1]
                    if action == "steer":
                        return await self._handle_steer_task(task_id, request)
                    if action == "cancel":
                        return await self._handle_cancel_task(task_id)
                    if action == "editor-finding":
                        return await self._handle_editor_finding(task_id, request)

            # 3. Message / Dialogue Endpoints (P08.1)
            if method == "POST" and path == "/api/v1/messages":
                return await self._handle_post_message(request)

            if method == "POST" and path == "/api/v1/dialogue":
                return await self._handle_dialogue(request, remote_scopes=remote_scopes)

            if method == "POST" and path == "/api/v1/dialogue/cancel":
                if remote_scopes is not None:
                    return HttpResponse.error(403, "Cancellation is owner-local", code="FORBIDDEN")
                data = request.json()
                if not isinstance(data, dict) or not isinstance(data.get("request_id"), str):
                    return HttpResponse.error(400, "A request ID is required", code="INVALID_INPUT")
                try:
                    request_id = DialogueTurns.validate_id(data["request_id"])
                except ValueError:
                    return HttpResponse.error(400, "Invalid request ID", code="INVALID_INPUT")
                cancel_state = self.runtime.cancel_dialogue(request_id)
                return HttpResponse.json({"request_id": request_id, "state": cancel_state})

            if method == "POST" and path == "/api/v1/dialogue/desktop":
                return await self._handle_desktop_dialogue(request, remote_scopes=remote_scopes)

            if method == "POST" and path == "/api/v1/models/scan":
                if remote_scopes is not None:
                    return HttpResponse.error(
                        403, "Model folders are owner-local", code="FORBIDDEN"
                    )
                return await self._handle_scan_models(request)

            if path == "/api/v1/companion" and method in {"GET", "POST"}:
                if remote_scopes is not None:
                    return HttpResponse.error(
                        403, "Companion controls are owner-local", code="FORBIDDEN"
                    )
                avatar = self.runtime.local_avatar
                if method == "GET":
                    state = self.runtime.embodiment_state
                    return HttpResponse.json(
                        {
                            **self.runtime.companion_status(),
                            "configured": avatar is not None,
                            "running": avatar is not None
                            and avatar.process is not None
                            and avatar.process.returncode is None,
                            "visible": state is not None and state.visible,
                            "error": avatar.error
                            if avatar
                            else "Start SORA with its 3D companion.",
                        }
                    )
                if avatar is None:
                    return HttpResponse.error(
                        409, "3D companion is not configured", code="EMBODIMENT_NOT_READY"
                    )
                body = request.json()
                if (
                    not isinstance(body, dict)
                    or set(body) != {"state"}
                    or not isinstance(body["state"], str)
                ):
                    return HttpResponse.error(
                        400, "Expected a companion state", code="INVALID_REQUEST"
                    )
                try:
                    await avatar.present(body["state"])
                except (ValueError, PermissionError) as exc:
                    return HttpResponse.error(409, str(exc), code="EMBODIMENT_NOT_READY")
                return HttpResponse.json({"status": "queued"})

            if method == "GET" and path == "/api/v1/messages":
                return await self._handle_list_messages(request)

            # 3a. Voice session endpoints (P14.2). Audio bytes stay on the authenticated client.
            if method == "POST" and path == "/api/v1/voice/sessions":
                return await self._handle_start_voice_session(request)

            if path.startswith("/api/v1/self/"):
                if remote_scopes is not None:
                    return HttpResponse.error(
                        403, "SORA's self is owner-local only", code="FORBIDDEN"
                    )
                from sora.api.self_routes import handle_self

                return await handle_self(self.runtime, request, path)

            if path == "/api/v1/voice/local" and method in {"GET", "POST"}:
                if remote_scopes is not None:
                    return HttpResponse.error(
                        403, "Local audio is owner-local only", code="FORBIDDEN"
                    )
                return await self._handle_local_voice(request)

            if path.startswith("/api/v1/voice/sessions/"):
                subpath = path[len("/api/v1/voice/sessions/") :]
                parts = subpath.split("/")
                session_id = parts[0]
                if len(parts) == 1 and method == "GET":
                    return await self._handle_get_voice_session(session_id, request)
                if len(parts) == 2 and method == "GET" and parts[1] == "speech":
                    return await self._handle_voice_speech(session_id, request)
                if len(parts) == 2 and method == "POST":
                    if parts[1] == "transcript":
                        return await self._handle_voice_transcript(session_id, request)
                    if parts[1] == "device":
                        return await self._handle_voice_device(session_id, request)
                    if parts[1] == "playback":
                        return await self._handle_voice_playback(session_id, request)
                    if parts[1] == "interrupt":
                        return await self._handle_voice_interruption(session_id, request)
                    if parts[1] == "close":
                        return await self._handle_close_voice_session(session_id, request)

            # 4. Workspaces & Review Endpoints (P08.1, P07 Integration)
            if method == "GET" and path == "/api/v1/workspaces":
                return await self._handle_list_workspaces()

            if path.startswith("/api/v1/workspaces/"):
                subpath = path[len("/api/v1/workspaces/") :]
                parts = subpath.split("/")
                ws_id = parts[0]
                if len(parts) == 2:
                    action = parts[1]
                    if action == "diff" and method == "GET":
                        return await self._handle_workspace_diff(ws_id)
                    if action == "validate" and method == "POST":
                        return await self._handle_workspace_validate(ws_id, request)
                    if action == "integrate" and method == "POST":
                        return await self._handle_workspace_integrate(ws_id, request)

            if method == "POST" and path.startswith("/api/v1/integrations/"):
                subpath = path[len("/api/v1/integrations/") :]
                parts = subpath.split("/")
                if len(parts) == 2 and parts[1] == "rollback":
                    return await self._handle_rollback_integration(parts[0], request)

            # 5. Companion Projections (P08.5)
            if method == "GET" and path == "/api/v1/projections/companion":
                return await self._handle_companion_projection()

            if method == "GET" and path == "/api/v1/projections/settings":
                return await self._handle_settings_projection()

            if method == "POST" and path == "/api/v1/settings":
                if remote_scopes is not None:
                    return HttpResponse.error(403, "Settings are owner-local", code="FORBIDDEN")
                return await self._handle_update_settings(request)

            if method == "POST" and path in {
                "/api/v1/model/reload",
                "/api/v1/settings/refresh",
                "/api/v1/models/projectors",
            }:
                if remote_scopes is not None:
                    return HttpResponse.error(
                        403, "Model settings are owner-local", code="FORBIDDEN"
                    )
                return self._handle_model_settings(path, request)

            if method == "GET" and path == "/api/v1/projections/permissions":
                return await self._handle_permissions_projection()

            if method == "GET" and path == "/api/v1/projections/objects":
                return await self._handle_objects_projection()

            if method == "POST" and path.startswith("/api/v1/desktop-objects/"):
                parts = path[len("/api/v1/desktop-objects/") :].split("/")
                if len(parts) == 2 and parts[1] == "affordances":
                    return await self._handle_desktop_object_affordance(parts[0], request)

            if method == "GET" and path == "/api/v1/projections/capabilities":
                return await self._handle_capabilities_projection(request)

            # Embodiment Endpoints (P09.4)
            if method == "POST" and path == "/api/v1/desktop/observe":
                return await self._handle_desktop_observation(request)

            if method == "POST" and path == "/api/v1/desktop/capture":
                return await self._handle_desktop_capture(request)

            if method == "POST" and path == "/api/v1/vision/evidence":
                return await self._handle_vision_evidence(request)

            if method == "POST" and path == "/api/v1/desktop/targets":
                return await self._handle_desktop_target_acquisition(request)

            if method == "POST" and path == "/api/v1/desktop/events":
                return await self._handle_desktop_events(request)

            if method == "POST" and path == "/api/v1/desktop/events/subscription":
                return await self._handle_desktop_event_subscription(request)

            if method == "POST" and path == "/api/v1/attention/cursor":
                return await self._handle_cursor_samples(request)

            if method == "POST" and path == "/api/v1/attention/selection":
                return await self._handle_selection_sample(request)

            if method == "POST" and path == "/api/v1/attention/resolve":
                return await self._handle_attention_resolution(request)

            if method == "POST" and path == "/api/v1/attention/crop":
                return await self._handle_attention_crop(request)

            if method == "POST" and path == "/api/v1/references/resolve":
                return await self._handle_reference_resolution(request)

            if method == "POST" and path == "/api/v1/references/pin":
                return await self._handle_reference_pin(request)

            if method == "POST" and path == "/api/v1/content/navigate":
                return await self._handle_content_navigation(request)

            if method == "GET" and path == "/api/v1/content/references":
                return self._handle_content_references(request)

            if method == "POST" and path.startswith("/api/v1/desktop/targets/"):
                parts = path[len("/api/v1/desktop/targets/") :].split("/")
                if len(parts) == 2 and parts[1] == "revalidate":
                    return await self._handle_desktop_target_revalidation(parts[0], request)
                if len(parts) == 2 and parts[1] == "present":
                    return await self._handle_desktop_target_presentation(parts[0], request)
                if len(parts) == 2 and parts[1] == "press":
                    return await self._handle_desktop_target_press(parts[0], request)
                if len(parts) == 3 and parts[1:] == ["interactions", "press"]:
                    return await self._handle_desktop_press_interaction(parts[0], request)
                if len(parts) == 2 and parts[1] == "type":
                    return await self._handle_desktop_target_type(parts[0], request)
                if len(parts) == 3 and parts[1:] == ["interactions", "type"]:
                    return await self._handle_desktop_type_interaction(parts[0], request)

            if method == "POST" and path.startswith("/api/v1/desktop/interactions/"):
                parts = path[len("/api/v1/desktop/interactions/") :].split("/")
                if len(parts) == 2 and parts[1] == "contact":
                    return await self._handle_desktop_interaction_contact(parts[0], request)

            if method == "GET" and path == "/api/v1/projections/embodiment":
                return HttpResponse.json(self.runtime.get_embodiment_projection())

            if method == "POST" and path == "/api/v1/embodiment/command":
                return await self._handle_embodiment_command(request)

            if method == "POST" and path == "/api/v1/embodiment/topology":
                return await self._handle_embodiment_topology(request)

            # 6. Extensions & Affordances (P08.6)
            if method == "GET" and path == "/api/v1/extensions":
                return HttpResponse.json(
                    [ext.model_dump(mode="json") for ext in self._extensions.values()]
                )

            if path.startswith("/api/v1/extensions/"):
                subpath = path[len("/api/v1/extensions/") :]
                parts = subpath.split("/")
                ext_id = parts[0]
                if len(parts) == 2 and method == "POST":
                    action = parts[1]
                    if action == "enable":
                        return await self._handle_enable_extension(ext_id, request)
                    if action == "disable":
                        return await self._handle_disable_extension(ext_id)
                if len(parts) == 2 and method == "GET" and parts[1] == "schema":
                    return await self._handle_extension_schema(ext_id)

            return HttpResponse.error(
                404, f"Endpoint '{method} {path}' not found", code="NOT_FOUND"
            )

        except OperationAuthorizationError as exc:
            return HttpResponse.error(403, str(exc), code="ACCESS_DISABLED")
        except Exception:
            logger.exception("Unhandled API route failure")
            return HttpResponse.error(500, "Internal server error", code="INTERNAL_ERROR")

    # --- Handlers ---

    async def _handle_get_status(self) -> HttpResponse:
        providers_status: dict[str, Any] = {}
        for p_name, p_inst in self.runtime.providers.items():
            try:
                caps = await p_inst.capabilities()
                providers_status[p_name] = {
                    "available": True,
                    "display_name": caps.display_name or p_name,
                    "sessions": caps.sessions,
                    "resume": caps.resume,
                }
            except Exception:
                logger.exception("Provider capability probe failed for %s", p_name)
                providers_status[p_name] = {"available": False, "error": "unavailable"}

        def read_counts(db: Any) -> tuple[int, int]:
            task_count = int(
                db.execute(
                    "SELECT COUNT(*) FROM tasks WHERE owner_id=?",
                    (self.runtime.config.owner_id,),
                ).fetchone()[0]
            )
            revision = int(
                db.execute("SELECT revision FROM state_meta WHERE singleton=1").fetchone()[0]
            )
            return task_count, revision

        task_count, revision = await self.runtime.repository.database.read(read_counts)

        return HttpResponse.json(
            {
                "status": "online",
                "state_revision": revision,
                "total_tasks": task_count,
                "providers": providers_status,
            }
        )

    async def _handle_poll_events(
        self,
        request: HttpRequest,
        *,
        local: bool = True,
    ) -> HttpResponse:
        """Replay a bounded event page for bearer-authenticated browser clients."""

        try:
            since_sequence = int(request.query_param("since_sequence", "0") or "0")
            limit = int(request.query_param("limit", "100") or "100")
        except ValueError:
            return HttpResponse.error(
                400, "since_sequence and limit must be integers", code="INVALID_CURSOR"
            )
        if since_sequence < 0 or not 1 <= limit <= 500:
            return HttpResponse.error(
                400,
                "since_sequence must be non-negative and limit must be between 1 and 500",
                code="INVALID_CURSOR",
            )

        stream_id = self.runtime.config.owner_id
        minimum, latest = await get_stream_bounds(self.runtime, stream_id)
        cursor_expired = minimum > 0 and since_sequence < minimum - 1
        cursor_ahead = since_sequence > latest
        if cursor_expired or cursor_ahead:
            snapshot = await build_state_snapshot(self.runtime, stream_id, local=local)
            return HttpResponse.json(
                {
                    "events": [],
                    "minimum_sequence": minimum,
                    "latest_sequence": latest,
                    "next_sequence": latest,
                    "more_available": False,
                    "resync_required": True,
                    "reason": "cursor_expired" if cursor_expired else "cursor_ahead",
                    "snapshot": snapshot,
                }
            )

        events = await replay_events_since(
            self.runtime,
            stream_id,
            since_sequence=since_sequence,
            limit=limit,
            through_sequence=latest,
        )
        replay_gap = (not events and since_sequence < latest) or (
            bool(events) and events[0].sequence > since_sequence + 1
        )
        if replay_gap:
            snapshot = await build_state_snapshot(self.runtime, stream_id, local=local)
            return HttpResponse.json(
                {
                    "events": [],
                    "minimum_sequence": minimum,
                    "latest_sequence": latest,
                    "next_sequence": latest,
                    "more_available": False,
                    "resync_required": True,
                    "reason": "replay_gap",
                    "snapshot": snapshot,
                }
            )

        next_sequence = events[-1].sequence if events else since_sequence
        return HttpResponse.json(
            {
                "events": [event.model_dump(mode="json") for event in events],
                "minimum_sequence": minimum,
                "latest_sequence": latest,
                "next_sequence": next_sequence,
                "more_available": next_sequence < latest,
                "resync_required": False,
                "reason": None,
                "snapshot": None,
            }
        )

    async def _handle_submit_task(self, request: HttpRequest) -> HttpResponse:
        try:
            return await self._submit_selected_task(request)
        except ValueError as exc:
            return HttpResponse.error(
                409,
                str(exc)[:500],
                code="TASK_SELECTION_CONFLICT",
            )
        except ProviderLaunchError as exc:
            return HttpResponse.error(
                422,
                str(exc),
                code=exc.code.value,
            )

    async def _submit_selected_task(self, request: HttpRequest) -> HttpResponse:
        data = request.json() or {}
        if not isinstance(data, dict):
            return HttpResponse.error(400, "Invalid task request", code="INVALID_INPUT")
        for field in (
            "intent",
            "idempotency_key",
            "explicit_provider",
            "explicit_model",
            "explicit_effort",
            "working_directory",
            "workspace_mode",
        ):
            if data.get(field) is not None and not isinstance(data[field], str):
                return HttpResponse.error(400, f"Invalid field '{field}'", code="INVALID_INPUT")
        intent = data.get("intent")
        if not intent or not str(intent).strip():
            return HttpResponse.error(400, "Missing required field 'intent'", code="INVALID_INPUT")

        idempotency_key = data.get("idempotency_key")
        explicit_provider = data.get("explicit_provider")
        explicit_model = data.get("explicit_model")
        explicit_effort = data.get("explicit_effort")
        from sora.runtime.agent_catalogue import validate_selection

        try:
            validate_selection(explicit_provider, explicit_model, explicit_effort)
        except ValueError:
            return HttpResponse.error(
                400,
                "Invalid provider/model/effort selection",
                code="INVALID_INPUT",
            )
        is_local_only = bool(data.get("is_local_only", False))
        reference_utterance = data.get("reference_utterance")
        reference_id = data.get("reference_id")

        if reference_utterance or reference_id:
            receipt, resolution = await self.runtime.submit_referenced_task(
                str(intent),
                ReferenceResolveRequest(
                    utterance=str(reference_utterance or intent),
                    explicit_reference_id=str(reference_id) if reference_id else None,
                ),
                device_id=self._device_id(request),
                idempotency_key=str(idempotency_key) if idempotency_key else None,
                explicit_provider=str(explicit_provider) if explicit_provider else None,
                explicit_model=explicit_model,
                explicit_effort=explicit_effort,
                working_directory=data.get("working_directory"),
                workspace_mode=data.get("workspace_mode"),
            )
            if receipt is None:
                return HttpResponse.json(
                    {
                        "error": {
                            "code": "REFERENCE_CLARIFICATION_REQUIRED",
                            "message": resolution.reason,
                        },
                        "resolution": resolution.model_dump(mode="json"),
                    },
                    status_code=409,
                )
        else:
            receipt = await self.runtime.submit_task(
                intent=str(intent),
                idempotency_key=str(idempotency_key) if idempotency_key else None,
                explicit_provider=str(explicit_provider) if explicit_provider else None,
                explicit_model=explicit_model,
                explicit_effort=explicit_effort,
                working_directory=data.get("working_directory"),
                workspace_mode=data.get("workspace_mode"),
                is_local_only=is_local_only,
            )

        return HttpResponse.json(
            {
                "task_id": receipt.task.task_id,
                "status": receipt.task.status.value,
                "selected_backend": receipt.task.effective_backend,
                "requested_model": receipt.task.requested_model,
                "requested_effort": receipt.task.requested_effort,
                "working_directory": receipt.task.working_directory,
                "workspace_mode": receipt.task.workspace_mode,
                "acknowledgement": receipt.acknowledgement,
                "acknowledged": bool(receipt.acknowledgement),
                "referent_ids": [
                    candidate.reference_id for candidate in receipt.task.reference_context
                ],
            },
            status_code=201,
        )

    async def _handle_plan_board_card(self, request: HttpRequest) -> HttpResponse:
        body = request.json()
        if not isinstance(body, dict) or not isinstance(body.get("intent"), str):
            return HttpResponse.error(400, "A plan description is required", code="INVALID_INPUT")
        key = body.get("idempotency_key")
        if key is not None and not isinstance(key, str):
            return HttpResponse.error(400, "Invalid idempotency key", code="INVALID_INPUT")
        try:
            task = await self.runtime.plan_task(body["intent"], idempotency_key=key)
        except ValueError as exc:
            return HttpResponse.error(409, str(exc), code="PLAN_CONFLICT")
        return HttpResponse.json(
            {
                "task_id": task.task_id,
                "status": task.status.value,
                "run_started": task.active_run_id is not None,
                "acknowledgement": (
                    "Saved to TODO. No specialist has been started."
                    if task.active_run_id is None
                    else "This plan already has a specialist run."
                ),
            },
            status_code=201,
        )

    async def _handle_update_board_card(
        self, task_id: str, action: str, request: HttpRequest
    ) -> HttpResponse:
        """Owner-local note edits never alter task or agent-run status."""
        body = request.json() or {}
        if not isinstance(body, dict):
            return HttpResponse.error(400, "Invalid board edit", code="INVALID_INPUT")
        column = body.get("column")
        assigned_agent = body.get("assigned_agent")
        expected_version = body.get("expected_version")
        if expected_version is not None and (
            isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version < 0
        ):
            return HttpResponse.error(400, "Invalid board version", code="INVALID_INPUT")
        if action == "move" and column not in {"TODO", "DOING", "DONE"}:
            return HttpResponse.error(400, "Invalid board column", code="INVALID_INPUT")
        if action == "assign" and assigned_agent not in {
            "codex",
            "claude",
            "hermes",
            "antigravity",
            "sora",
            "unassigned",
        }:
            return HttpResponse.error(400, "Invalid assigned agent", code="INVALID_INPUT")
        try:
            version = await self.runtime.runtime_repository.update_board_card(
                task_id,
                owner_id=self.runtime.config.owner_id,
                project_id=self.runtime.config.project_id,
                action=action,
                actor="owner",
                column=column,
                assigned_agent=assigned_agent,
                expected_version=expected_version,
                now=datetime.now(UTC),
            )
        except LookupError:
            return HttpResponse.error(404, "Board card not found", code="NOT_FOUND")
        except ValueError as exc:
            return HttpResponse.error(409, str(exc), code="BOARD_CONFLICT")
        return HttpResponse.json({"task_id": task_id, "action": action, "version": version})

    async def _handle_start_board_card(self, task_id: str, request: HttpRequest) -> HttpResponse:
        body = request.json() or {}
        if not isinstance(body, dict):
            return HttpResponse.error(400, "Invalid start request", code="INVALID_INPUT")
        provider = body.get("explicit_provider")
        if provider is not None and not isinstance(provider, str):
            return HttpResponse.error(400, "Invalid provider", code="INVALID_INPUT")
        for field in ("working_directory", "workspace_mode", "explicit_model", "explicit_effort"):
            if body.get(field) is not None and not isinstance(body[field], str):
                return HttpResponse.error(400, f"Invalid {field}", code="INVALID_INPUT")
        try:
            from sora.runtime.agent_catalogue import validate_selection

            validate_selection(provider, body.get("explicit_model"), body.get("explicit_effort"))
            effort = cast(ReasoningEffort | None, body.get("explicit_effort"))
            task = await self.runtime.start_planned_task(
                task_id,
                explicit_provider=provider,
                working_directory=body.get("working_directory"),
                workspace_mode=body.get("workspace_mode"),
                explicit_model=body.get("explicit_model"),
                explicit_effort=effort,
            )
        except LookupError:
            return HttpResponse.error(404, "Planned card not found", code="NOT_FOUND")
        except (ValueError, RuntimeError, ProviderLaunchError) as exc:
            return HttpResponse.error(409, str(exc), code="PLAN_CONFLICT")
        return HttpResponse.json(
            {
                "task_id": task.task_id,
                "status": task.status.value,
                "run_started": True,
                "selected_backend": task.effective_backend,
            },
            status_code=201,
        )

    async def _handle_retry_board_card(self, task_id: str) -> HttpResponse:
        task = await self.runtime.runtime_repository.get_task(task_id)
        if (
            task is None
            or task.owner_id != self.runtime.config.owner_id
            or task.project_id != self.runtime.config.project_id
        ):
            return HttpResponse.error(404, "Board card not found", code="NOT_FOUND")
        try:
            updated = await self.runtime.retry(task_id)
        except ValueError as exc:
            return HttpResponse.error(409, str(exc), code="RETRY_CONFLICT")
        return HttpResponse.json(
            {
                "task_id": updated.task_id,
                "status": updated.status.value,
                "run_started": True,
                "selected_backend": updated.effective_backend,
            },
            status_code=201,
        )

    async def _handle_submit_editor_task(self, request: HttpRequest) -> HttpResponse:
        try:
            submission = EditorTaskRequest.model_validate(request.json())
        except ValueError:
            return HttpResponse.error(400, "Invalid editor task request", code="INVALID_REQUEST")
        try:
            receipt = await self.runtime.submit_editor_task(
                submission.intent,
                submission.editor_context,
                grant_id=self._grant_id(request),
                device_id=self._device_id(request),
                idempotency_key=submission.idempotency_key,
                explicit_provider=submission.explicit_provider,
            )
        except PermissionError:
            return HttpResponse.error(403, "Editor context read not authorized", code="FORBIDDEN")
        except DesktopTargetError as exc:
            return self._desktop_target_error(exc)
        except EditorContextError as exc:
            return self._editor_context_error(exc)
        except ValueError:
            return HttpResponse.error(
                409, "Editor submission conflicts with existing task", code="EDITOR_CONFLICT"
            )
        context = receipt.task.editor_context
        if context is None:
            return HttpResponse.error(500, "Editor context was not bound", code="INTERNAL_ERROR")
        return HttpResponse.json(
            {
                "task_id": receipt.task.task_id,
                "status": receipt.task.status.value,
                "selected_backend": receipt.task.effective_backend,
                "acknowledgement": receipt.acknowledgement,
                "acknowledged": bool(receipt.acknowledgement),
                "editor_context_id": context.context_id,
                "relative_file_path": context.relative_file_path,
                "selection": context.selection.model_dump(mode="json"),
                "selection_sha256": context.selection_sha256,
            },
            status_code=201,
        )

    async def _handle_editor_finding(self, task_id: str, request: HttpRequest) -> HttpResponse:
        try:
            finding = EditorFindingPresentationRequest.model_validate(request.json())
        except ValueError:
            return HttpResponse.error(400, "Invalid editor finding request", code="INVALID_REQUEST")
        try:
            command = await self.runtime.present_editor_finding(
                task_id,
                finding,
                grant_id=self._grant_id(request),
                device_id=self._device_id(request),
            )
        except PermissionError:
            return HttpResponse.error(403, "Editor finding presentation denied", code="FORBIDDEN")
        except DesktopTargetError as exc:
            return self._desktop_target_error(exc)
        except EditorContextError as exc:
            return self._editor_context_error(exc)
        return HttpResponse.json({"status": "queued", "command": command.model_dump(mode="json")})

    async def _handle_list_tasks(self, request: HttpRequest, *, local: bool = True) -> HttpResponse:
        try:
            limit = int(request.query_param("limit", "50") or "50")
            offset = int(request.query_param("offset", "0") or "0")
        except ValueError:
            return HttpResponse.error(400, "limit and offset must be integers", code="INVALID_PAGE")
        if not 1 <= limit <= 100 or offset < 0:
            return HttpResponse.error(
                400,
                "limit must be between 1 and 100 and offset must be non-negative",
                code="INVALID_PAGE",
            )
        status_filter = request.query_param("status")
        owner_id = self.runtime.config.owner_id

        def read(db: Any) -> list[dict[str, Any]]:
            if status_filter:
                cursor = db.execute(
                    "SELECT payload FROM tasks WHERE owner_id=? AND status=? "
                    "ORDER BY rowid DESC LIMIT ? OFFSET ?",
                    (owner_id, status_filter, limit, offset),
                )
            else:
                cursor = db.execute(
                    "SELECT payload FROM tasks WHERE owner_id=? "
                    "ORDER BY rowid DESC LIMIT ? OFFSET ?",
                    (owner_id, limit, offset),
                )
            return [json.loads(row[0]) for row in cursor.fetchall()]

        tasks = await self.runtime.repository.database.read(read)
        if not local:
            for item in tasks:
                item.pop("working_directory", None)
                item.pop("workspace_base_ref", None)
                item.pop("companion_brief", None)
        return HttpResponse.json({"tasks": tasks, "limit": limit, "offset": offset})

    async def _handle_get_task(self, task_id: str, *, local: bool = True) -> HttpResponse:
        task = await self.runtime.repository.get_task(task_id)
        if task is None or task.owner_id != self.runtime.config.owner_id:
            return HttpResponse.error(404, f"Task '{task_id}' not found", code="NOT_FOUND")
        payload = task.model_dump(mode="json")
        if not local:
            payload.pop("working_directory", None)
            payload.pop("workspace_base_ref", None)
            payload.pop("companion_brief", None)
        return HttpResponse.json(payload)

    async def _handle_task_evidence(self, task_id: str) -> HttpResponse:
        task = await self.runtime.repository.get_task(task_id)
        if task is None or task.owner_id != self.runtime.config.owner_id:
            return HttpResponse.error(404, "Task not found", code="NOT_FOUND")

        def read(db: Any) -> dict[str, Any]:
            row = db.execute(
                "SELECT payload FROM normalized_results WHERE result_id=?",
                (task.result_ref,),
            ).fetchone()
            result = json.loads(row[0]) if row else None
            creator = db.execute(
                "SELECT content FROM messages WHERE message_id=? AND owner_id=?",
                (task.creator_message_id, task.owner_id),
            ).fetchone()
            return {
                "task": task.model_dump(mode="json"),
                "result": result,
                "owner_request": creator[0] if creator else None,
                "evidence_note": (
                    "Task completion is a validated provider report, not independent proof of "
                    "every action. Filesystem diffs show metadata changes, not their author."
                ),
            }

        return HttpResponse.json(await self.runtime.repository.database.read(read))

    async def _handle_automations(self, request: HttpRequest, path: str) -> HttpResponse:
        receipts = path.startswith("/api/v1/automation-requests/")
        page = path == "/api/v1/automations"
        parts = path.removeprefix("/api/v1/automations/").split("/")
        history = not page and not receipts and len(parts) == 2 and parts[1] == "history"
        manual = not page and not receipts and len(parts) == 2 and parts[1] == "run-now"
        if not page and not receipts and not history and not manual and len(parts) != 1:
            return HttpResponse.error(404, "Automation route not found", code="NOT_FOUND")
        if request.method not in (
            {"POST"} if manual else {"GET"} if receipts or history else {"GET", "POST"}
        ):
            return HttpResponse.error(
                405, "Unsupported Automation method", code="METHOD_NOT_ALLOWED"
            )
        params = request.query_params()
        allowed = (
            {"limit", "cursor"}
            if history
            else {"q", "state", "limit", "cursor"}
            if page and request.method == "GET"
            else set()
        )
        if (
            len(request.body) > 65536
            or request.method == "GET"
            and request.body
            or any(key not in allowed or len(value) != 1 for key, value in params.items())
        ):
            return HttpResponse.error(
                400, "Invalid Automation request", code="INVALID_AUTOMATION_REQUEST"
            )
        try:
            result: ContractModel
            code = 200
            if request.method == "POST":
                if manual:
                    run = AutomationRunNow.model_validate(request.json())
                    result = await self.automations.run_now(run, parts[0])
                    code = 200 if result.replayed else 202
                elif page:
                    command = AutomationCreate.model_validate(request.json())
                    result = await self.automations.mutate(command)
                    code = 200 if result.replayed else 201
                else:
                    change = AutomationChange.model_validate(request.json())
                    result = await self.automations.mutate(change, parts[0])
            elif receipts:
                key = uuid.UUID(path.removeprefix("/api/v1/automation-requests/"))
                result = await self.runtime.repository.database.read(
                    lambda db: self.automations.receipt_in(db, key)
                )
            elif history:
                result = await self.runtime.repository.database.read(
                    lambda db: self.automations.history_in(
                        db,
                        parts[0],
                        limit=int(params.get("limit", ["50"])[0]),
                        cursor=params.get("cursor", [None])[0],
                    )
                )
            elif page:
                result = await self.runtime.repository.database.read(
                    lambda db: self.automations.page_in(
                        db,
                        query=params.get("q", [""])[0],
                        state=params.get("state", ["all"])[0],
                        limit=int(params.get("limit", ["50"])[0]),
                        cursor=params.get("cursor", [None])[0],
                    )
                )
            else:
                result = await self.runtime.repository.database.read(
                    lambda db: self.automations.detail_in(db, parts[0])
                )
            return HttpResponse.json(result.model_dump(mode="json"), status_code=code)
        except AutomationConflict as error:
            return HttpResponse.error(
                409,
                "Automation changed or request conflicts; inspect before retrying",
                code=error.code,
            )
        except LookupError:
            return HttpResponse.error(404, "Automation/receipt not found", code="NOT_FOUND")
        except (ValueError, UnicodeError):
            return HttpResponse.error(
                400, "Invalid closed Automation request", code="INVALID_AUTOMATION_REQUEST"
            )
        except (AutomationStorageError, sqlite3.Error):
            return HttpResponse.error(
                503, "Canonical Automation storage unavailable", code="AUTOMATION_UNAVAILABLE"
            )

    async def _handle_ui_presentation(self, request: HttpRequest, path: str) -> HttpResponse:
        hub = self.runtime.memory_presentations
        posts = {
            "/api/v1/ui/host",
            "/api/v1/ui/presentations/poll",
            "/api/v1/ui/presentations/ack",
            "/api/v1/ui/present-memory",
        }
        result_path = path.startswith("/api/v1/ui/presentations/") and path not in posts
        if path not in posts and not result_path:
            return HttpResponse.error(404, "UI route not found", code="NOT_FOUND")
        if request.method != ("GET" if result_path else "POST"):
            return HttpResponse.error(405, "Unsupported UI method", code="METHOD_NOT_ALLOWED")
        if request.query_params() or len(request.body) > 8192 or result_path and request.body:
            return HttpResponse.error(400, "Invalid UI request", code="INVALID_UI_REQUEST")
        try:
            result: ContractModel
            if result_path:
                result = hub.result(uuid.UUID(path.removeprefix("/api/v1/ui/presentations/")))
            elif path == "/api/v1/ui/host":
                result = hub.register(UiHostRegistration.model_validate(request.json()))
            elif path.endswith("/poll"):
                result = hub.poll(UiHostCommand.model_validate(request.json()))
            elif path.endswith("/ack"):
                result = await hub.acknowledge(UiPresentationAck.model_validate(request.json()))
            else:
                result = await hub.request(UiMemoryCommand.model_validate(request.json()))
            return HttpResponse.json(result.model_dump(mode="json"))
        except UiPresentationError as error:
            return HttpResponse.error(
                409, "UI binding/target unavailable or changed", code=error.code
            )
        except LookupError:
            return HttpResponse.error(404, "UI target/request not found", code="NOT_FOUND")
        except (ValueError, UnicodeError):
            return HttpResponse.error(400, "Invalid closed UI request", code="INVALID_UI_REQUEST")
        except (MemoryProjectionError, sqlite3.Error):
            return HttpResponse.error(503, "Canonical UI target unavailable", code="UI_UNAVAILABLE")

    async def _handle_memory_mutation(
        self, request: HttpRequest, path: str, *, receipt_only: bool = False
    ) -> HttpResponse:
        if request.query_params() or len(request.body) > 131072:
            return HttpResponse.error(
                400, "Invalid Memory mutation", code="INVALID_MEMORY_MUTATION"
            )
        try:
            if receipt_only:
                request_id = uuid.UUID(path.removeprefix("/api/v1/memory-mutations/"))
                ack = await self.runtime.repository.database.read(
                    lambda db: receipt(
                        db,
                        owner=self.runtime.config.owner_id,
                        project=self.runtime.config.project_id,
                        request_id=request_id,
                        instance=self.instance_id,
                    )
                )
            else:
                memory_id, action = path.removeprefix("/api/v1/memories/").split("/")
                contract = MemoryCorrection if action == "correct" else MemoryForget
                command = contract.model_validate(request.json())
                ack = await mutate(
                    self.runtime.repository,
                    owner=self.runtime.config.owner_id,
                    project=self.runtime.config.project_id,
                    memory_id=memory_id,
                    instance=self.instance_id,
                    request=command,
                )
                if ack.action == "forget" and not ack.replayed:
                    # Forgetting also deletes the moment's saved images and recording.
                    forget_entry(self.runtime.memory_entries_root(), memory_id)
            return HttpResponse.json(ack.model_dump(mode="json"))
        except MemoryMutationConflict as error:
            return HttpResponse.json(
                {
                    "error": {
                        "message": "Memory changed or request conflicts; inspect before editing",
                        "code": error.code,
                        "status": 409,
                        "current_version": error.version,
                        "current_state": error.state,
                    },
                },
                status_code=409,
            )
        except LookupError:
            return HttpResponse.error(404, "Memory/receipt not found", code="NOT_FOUND")
        except (ValueError, UnicodeError):
            return HttpResponse.error(
                400,
                "Invalid closed Memory mutation/receipt request",
                code="INVALID_MEMORY_MUTATION",
            )
        except (MemoryProjectionError, sqlite3.Error):
            return HttpResponse.error(
                503, "Canonical Memory mutation unavailable", code="MEMORY_UNAVAILABLE"
            )

    async def _handle_memories(self, request: HttpRequest, path: str) -> HttpResponse:
        params = request.query_params()
        is_page = path == "/api/v1/memories"
        allowed = {"q", "state", "project", "scope", "limit", "cursor"} if is_page else set()
        if any(name not in allowed or len(values) != 1 for name, values in params.items()):
            return HttpResponse.error(400, "Invalid Memory query", code="INVALID_MEMORY_QUERY")
        try:
            if is_page:
                limit = request.query_param("limit", "50") or ""
                if not limit.isascii() or not limit.isdecimal() or len(limit) > 3:
                    raise ValueError("Invalid limit")
                page = await self.runtime.repository.database.read(
                    lambda db: memory_page(
                        db,
                        owner=self.runtime.config.owner_id,
                        project_id=self.runtime.config.project_id,
                        instance=self.instance_id,
                        key=self._memory_cursor_key,
                        state=request.query_param("state", "active") or "",
                        project=request.query_param("project", "all") or "",
                        scope=request.query_param("scope", "") or "",
                        query=request.query_param("q", "") or "",
                        limit=int(limit),
                        cursor=request.query_param("cursor"),
                    )
                )
                return HttpResponse.json(page.model_dump(mode="json"))
            memory_id = path.removeprefix("/api/v1/memories/")
            references = self.runtime.reference_resolver.list_content(
                owner_id=self.runtime.config.owner_id,
                device_id=self._device_id(request),
                project_id=self.runtime.config.project_id,
            )
            capture_root = (
                self.runtime.config.memory_captures_dir or self.runtime.config.root / "captures"
            ).resolve(strict=False)
            references = tuple(
                ref for ref in references if not ref.path.is_relative_to(capture_root)
            )
            detail = await self.runtime.repository.database.read(
                lambda db: memory_detail(
                    db,
                    owner=self.runtime.config.owner_id,
                    project_id=self.runtime.config.project_id,
                    memory_id=memory_id,
                    instance=self.instance_id,
                    device=self._device_id(request),
                    references=references,
                )
            )
            return HttpResponse.json(detail.model_dump(mode="json"))
        except LookupError:
            return HttpResponse.error(404, "Memory not found", code="NOT_FOUND")
        except ValueError:
            return HttpResponse.error(
                400, "Invalid Memory query/cursor/ID", code="INVALID_MEMORY_QUERY"
            )
        except (MemoryProjectionError, sqlite3.Error):
            return HttpResponse.error(
                503, "Canonical Memory projection unavailable", code="MEMORY_UNAVAILABLE"
            )

    async def _handle_task_runs(
        self, task_id: str, run_id: str | None, request: HttpRequest
    ) -> HttpResponse:
        try:
            if run_id is None:
                limit = int(request.query_param("limit", "50") or "0")
                page = await self.runtime.repository.database.read(
                    lambda db: run_page(
                        db,
                        self.runtime.config.owner_id,
                        task_id,
                        limit,
                        request.query_param("cursor"),
                    )
                )
                return HttpResponse.json(page.model_dump(mode="json"))
            references = self.runtime.reference_resolver.list_content(
                owner_id=self.runtime.config.owner_id,
                device_id=self._device_id(request),
                project_id=self.runtime.config.project_id,
            )
            evidence = await self.runtime.repository.database.read(
                lambda db: run_evidence(
                    db, self.runtime.config.owner_id, task_id, run_id, references
                )
            )
            return HttpResponse.json(evidence.model_dump(mode="json"))
        except LookupError:
            return HttpResponse.error(404, "Task/run not found", code="NOT_FOUND")
        except ValueError:
            return HttpResponse.error(400, "Invalid task-run page/cursor", code="INVALID_PAGE")

    async def _handle_steer_task(self, task_id: str, request: HttpRequest) -> HttpResponse:
        task = await self.runtime.repository.get_task(task_id)
        if task is None or task.owner_id != self.runtime.config.owner_id:
            return HttpResponse.error(404, "Task not found", code="NOT_FOUND")
        data = request.json() or {}
        instruction = data.get("instruction")
        if not instruction:
            return HttpResponse.error(
                400, "Missing required field 'instruction'", code="INVALID_INPUT"
            )
        err = await self.runtime.steer(task_id, str(instruction))
        if err is not None:
            return HttpResponse.error(400, err.message, code=err.code.value)
        return HttpResponse.json({"task_id": task_id, "steered": True})

    async def _handle_cancel_task(self, task_id: str) -> HttpResponse:
        task = await self.runtime.repository.get_task(task_id)
        if task is None or task.owner_id != self.runtime.config.owner_id:
            return HttpResponse.error(404, "Task not found", code="NOT_FOUND")
        cancelled = await self.runtime.cancel(task_id)
        return HttpResponse.json({"task_id": task_id, "cancelled": cancelled})

    async def _handle_post_message(self, request: HttpRequest) -> HttpResponse:
        data = request.json() or {}
        if not isinstance(data, dict):
            return HttpResponse.error(400, "Invalid conversation request", code="INVALID_INPUT")
        content = data.get("content")
        if not content:
            return HttpResponse.error(400, "Missing required field 'content'", code="INVALID_INPUT")
        msg = MessageRecord(
            message_id=f"message-{uuid.uuid4()}",
            conversation_id=self.runtime.config.conversation_id,
            owner_id=self.runtime.config.owner_id,
            project_id=self.runtime.config.project_id,
            role=str(data.get("role", "user")),
            content=str(content),
            provenance="api",
            sensitivity=str(data.get("sensitivity", "normal")),
            created_at=datetime.now(UTC),
        )
        rev = await self.runtime.repository.append_message(msg)
        return HttpResponse.json(
            {"revision": rev, "message_id": msg.message_id, "content": content},
            status_code=201,
        )

    async def _handle_dialogue(
        self, request: HttpRequest, *, remote_scopes: frozenset[str] | None = None
    ) -> HttpResponse:
        """Run one companion dialogue turn and persist the canonical user/assistant pair."""

        data = request.json() or {}
        if not isinstance(data, dict):
            return HttpResponse.error(400, "Invalid conversation request", code="INVALID_INPUT")
        try:
            request_id = DialogueTurns.validate_id(data.get("request_id"))
        except ValueError:
            return HttpResponse.error(400, "Invalid request ID", code="INVALID_INPUT")
        content = data.get("content")
        if not content or not str(content).strip():
            return HttpResponse.error(400, "Missing required field 'content'", code="INVALID_INPUT")
        raw_files = data.get("file_paths", [])
        if (
            not isinstance(raw_files, list)
            or len(raw_files) > 3
            or any(not isinstance(path, str) or not path.strip() for path in raw_files)
        ):
            return HttpResponse.error(400, "Invalid local file selection", code="INVALID_INPUT")
        try:
            response = await self.runtime.dialogue(
                str(content).strip(),
                allow_history=(remote_scopes is None or "conversation:read" in remote_scopes),
                allow_task_context=(remote_scopes is None or "tasks:read" in remote_scopes),
                allow_board_actions=remote_scopes is None,
                allow_motion_actions=remote_scopes is None,
                allow_desktop_view=remote_scopes is None,
                allow_local_files=remote_scopes is None,
                file_paths=tuple(raw_files),
                request_id=request_id,
            )
        except DialogueCancelledError:
            return HttpResponse.error(
                409,
                "Response stopped. Drafts can be edited and sent again; already-dispatched "
                "actions are not undone.",
                code="DIALOGUE_CANCELLED",
            )
        except DialogueRequestConflict:
            return HttpResponse.error(409, "Use a new request ID", code="DIALOGUE_REQUEST_CONFLICT")
        except LocalFileViewError as exc:
            return HttpResponse.error(
                403 if remote_scopes is not None else 422, str(exc), code="LOCAL_FILE_UNAVAILABLE"
            )
        except DialogueTimeoutError:
            return HttpResponse.error(
                503,
                "SORA's conversation timed out. Check the transcript before retrying; "
                "reduce model load or adjust Dialogue timeout in Settings.",
                code="DIALOGUE_TIMEOUT",
            )
        except DialogueProviderError:
            return HttpResponse.error(
                503, "Direct dialogue provider is unavailable", code="DIALOGUE_UNAVAILABLE"
            )
        return HttpResponse.json({"response": response}, status_code=201)

    async def _handle_desktop_dialogue(
        self, request: HttpRequest, *, remote_scopes: frozenset[str] | None = None
    ) -> HttpResponse:
        if remote_scopes is not None:
            return HttpResponse.error(403, "Desktop viewing is owner-local only", code="FORBIDDEN")
        data = request.json() or {}
        if not isinstance(data, dict):
            return HttpResponse.error(400, "Invalid screen request", code="INVALID_INPUT")
        try:
            request_id = DialogueTurns.validate_id(data.get("request_id"))
        except ValueError:
            return HttpResponse.error(400, "Invalid request ID", code="INVALID_INPUT")
        content = data.get("content", "What is visible on this screen?")
        if not isinstance(content, str) or len(content) > 16_000:
            return HttpResponse.error(400, "Invalid vision prompt", code="INVALID_INPUT")
        try:
            response = await self.runtime.dialogue_with_desktop_view(
                content.strip(),
                request_id=request_id,
            )
        except DialogueCancelledError:
            return HttpResponse.error(409, "Screen response stopped", code="DIALOGUE_CANCELLED")
        except DialogueRequestConflict:
            return HttpResponse.error(409, "Use a new request ID", code="DIALOGUE_REQUEST_CONFLICT")
        except DesktopVisionError as exc:
            return HttpResponse.error(422, str(exc), code="DESKTOP_VISION_UNAVAILABLE")
        except DialogueTimeoutError:
            return HttpResponse.error(
                503,
                "SORA's conversation timed out. Check the transcript before retrying; "
                "reduce model load or adjust Dialogue timeout in Settings.",
                code="DIALOGUE_TIMEOUT",
            )
        except DialogueProviderError:
            return HttpResponse.error(
                503, "Direct dialogue provider is unavailable", code="DIALOGUE_UNAVAILABLE"
            )
        return HttpResponse.json({"response": response}, status_code=201)

    async def _handle_list_messages(self, request: HttpRequest) -> HttpResponse:
        try:
            limit = int(request.query_param("limit", "50") or "50")
        except ValueError:
            return HttpResponse.error(400, "limit must be an integer", code="INVALID_PAGE")
        if not 1 <= limit <= 100:
            return HttpResponse.error(400, "limit must be between 1 and 100", code="INVALID_PAGE")
        messages = await self.runtime.repository.list_messages(self.runtime.config.conversation_id)
        if limit:
            messages = messages[-limit:]
        return HttpResponse.json([m.model_dump(mode="json") for m in messages])

    async def _handle_local_voice(self, request: HttpRequest) -> HttpResponse:
        from sora.security.local_policy import is_owner_local

        if not is_owner_local() or self.runtime.app_settings is None:
            return HttpResponse.error(403, "Local audio is owner-local only", code="FORBIDDEN")
        bridge = self.runtime.local_voice
        if request.method == "GET":
            return HttpResponse.json(
                {
                    **bridge.status(),
                    "enabled": self.runtime.app_settings.active.local_companion.voice,
                }
            )
        data = request.json()
        if not isinstance(data, dict) or set(data) != {"action"}:
            return HttpResponse.error(400, "Provide one voice action", code="INVALID_INPUT")
        action = data["action"]
        if not isinstance(action, str) or action not in {
            "start",
            "begin",
            "end",
            "stop",
            "stop_output",
            "close",
        }:
            return HttpResponse.error(400, "Unsupported voice action", code="INVALID_INPUT")
        try:
            if action == "close":
                session_id = bridge.session_id
                await bridge.close()
                if session_id is not None:
                    try:
                        await self.runtime.close_voice_session(
                            session_id, device_id="device-local-audio"
                        )
                    except LookupError:
                        pass
            else:
                self.runtime.app_settings.active.local_companion.require(("voice",))
                if action == "start":
                    await bridge.start(self.runtime.app_settings.active.voice)
                else:
                    await bridge.command(action)
        except PermissionError:
            return HttpResponse.error(403, "Voice is disabled in Settings", code="FORBIDDEN")
        except (ValueError, RuntimeError, OSError, TimeoutError) as exc:
            return HttpResponse.error(409, str(exc), code="LOCAL_VOICE_UNAVAILABLE")
        return HttpResponse.json(
            {
                **bridge.status(),
                "enabled": self.runtime.app_settings.active.local_companion.voice,
            }
        )

    async def _handle_start_voice_session(self, request: HttpRequest) -> HttpResponse:
        try:
            start = VoiceSessionStartRequest.model_validate(request.json())
        except ValueError:
            return HttpResponse.error(400, "Invalid voice session request", code="INVALID_REQUEST")
        try:
            snapshot = await self.runtime.start_voice_session(
                start,
                grant_id=self._grant_id(request),
                device_id=self._device_id(request),
            )
        except (OperationAuthorizationError, PermissionError):
            return HttpResponse.error(
                403, "Voice session authorization failed", code="AUTHORIZATION_REQUIRED"
            )
        except (RuntimeError, ValueError) as exc:
            return HttpResponse.error(409, str(exc), code="VOICE_SESSION_REJECTED")
        return HttpResponse.json(snapshot.model_dump(mode="json"), status_code=201)

    async def _handle_get_voice_session(
        self, session_id: str, request: HttpRequest
    ) -> HttpResponse:
        try:
            snapshot = await self.runtime.get_voice_session(
                session_id, device_id=self._device_id(request)
            )
        except LookupError:
            return HttpResponse.error(404, "Voice session not found", code="NOT_FOUND")
        except (OperationAuthorizationError, PermissionError):
            return HttpResponse.error(403, "Voice session access denied", code="FORBIDDEN")
        except RuntimeError as exc:
            return HttpResponse.error(409, str(exc), code="VOICE_SESSION_CLOSED")
        return HttpResponse.json(snapshot.model_dump(mode="json"))

    async def _handle_voice_speech(self, session_id: str, request: HttpRequest) -> HttpResponse:
        try:
            utterance_id = (request.query_param("utterance_id") or "").strip()
            after = int(request.query_param("after") or "0")
            if not utterance_id or len(utterance_id) > 128 or not 0 <= after <= 100_000:
                raise ValueError("Provide utterance_id and a valid after index")
            preview = await self.runtime.wait_voice_speech(
                session_id,
                device_id=self._device_id(request),
                utterance_id=utterance_id,
                after=after,
            )
        except LookupError:
            return HttpResponse.error(404, "Voice session not found", code="NOT_FOUND")
        except (OperationAuthorizationError, PermissionError):
            return HttpResponse.error(403, "Voice session access denied", code="FORBIDDEN")
        except ValueError as exc:
            return HttpResponse.error(400, str(exc), code="INVALID_INPUT")
        return HttpResponse.json(preview.model_dump(mode="json"))

    async def _handle_voice_transcript(self, session_id: str, request: HttpRequest) -> HttpResponse:
        try:
            event = VoiceTranscriptEvent.model_validate(request.json())
            if event.session_id != session_id:
                raise ValueError("voice transcript session does not match request path")
            result = await self.runtime.ingest_voice_transcript(
                event,
                device_id=self._device_id(request),
                attention_grant_id=(request.header("X-SORA-Attention-Grant-ID") or "").strip(),
            )
        except LookupError:
            return HttpResponse.error(404, "Voice session not found", code="NOT_FOUND")
        except (OperationAuthorizationError, PermissionError):
            return HttpResponse.error(403, "Voice session access denied", code="FORBIDDEN")
        except LocalFileViewError as exc:
            return HttpResponse.error(422, str(exc), code="LOCAL_FILE_UNAVAILABLE")
        except DialogueTimeoutError:
            return HttpResponse.error(
                503,
                "SORA's spoken response timed out. Check the transcript before retrying; "
                "reduce model load or adjust Dialogue timeout in Settings.",
                code="DIALOGUE_TIMEOUT",
            )
        except DialogueProviderError:
            return HttpResponse.error(
                503, "Direct dialogue provider is unavailable", code="DIALOGUE_UNAVAILABLE"
            )
        except (RuntimeError, ValueError) as exc:
            return HttpResponse.error(409, str(exc), code="VOICE_TRANSCRIPT_REJECTED")
        return HttpResponse.json(result.model_dump(mode="json"))

    async def _handle_voice_device(self, session_id: str, request: HttpRequest) -> HttpResponse:
        try:
            event = VoiceDeviceEvent.model_validate(request.json())
            if event.session_id != session_id:
                raise ValueError("voice device session does not match request path")
            snapshot = await self.runtime.update_voice_device(
                event, device_id=self._device_id(request)
            )
        except LookupError:
            return HttpResponse.error(404, "Voice session not found", code="NOT_FOUND")
        except (OperationAuthorizationError, PermissionError):
            return HttpResponse.error(403, "Voice session access denied", code="FORBIDDEN")
        except (RuntimeError, ValueError) as exc:
            return HttpResponse.error(409, str(exc), code="VOICE_DEVICE_REJECTED")
        return HttpResponse.json(snapshot.model_dump(mode="json"))

    async def _handle_voice_playback(self, session_id: str, request: HttpRequest) -> HttpResponse:
        try:
            event = VoicePlaybackEvent.model_validate(request.json())
            if event.session_id != session_id:
                raise ValueError("voice playback session does not match request path")
            snapshot = await self.runtime.update_voice_playback(
                event, device_id=self._device_id(request)
            )
        except LookupError:
            return HttpResponse.error(404, "Voice session not found", code="NOT_FOUND")
        except (OperationAuthorizationError, PermissionError):
            return HttpResponse.error(403, "Voice session access denied", code="FORBIDDEN")
        except (RuntimeError, ValueError) as exc:
            return HttpResponse.error(409, str(exc), code="VOICE_PLAYBACK_REJECTED")
        return HttpResponse.json(snapshot.model_dump(mode="json"))

    async def _handle_voice_interruption(
        self, session_id: str, request: HttpRequest
    ) -> HttpResponse:
        try:
            interruption = VoiceInterruptionRequest.model_validate(request.json())
            if interruption.session_id != session_id:
                raise ValueError("voice interruption session does not match request path")
            result = await self.runtime.interrupt_voice_session(
                interruption, device_id=self._device_id(request)
            )
        except LookupError:
            return HttpResponse.error(404, "Voice session not found", code="NOT_FOUND")
        except (OperationAuthorizationError, PermissionError):
            return HttpResponse.error(403, "Voice session access denied", code="FORBIDDEN")
        except (RuntimeError, ValueError) as exc:
            return HttpResponse.error(409, str(exc), code="VOICE_INTERRUPTION_REJECTED")
        return HttpResponse.json(result.model_dump(mode="json"))

    async def _handle_close_voice_session(
        self, session_id: str, request: HttpRequest
    ) -> HttpResponse:
        try:
            snapshot = await self.runtime.close_voice_session(
                session_id, device_id=self._device_id(request)
            )
        except LookupError:
            return HttpResponse.error(404, "Voice session not found", code="NOT_FOUND")
        except (OperationAuthorizationError, PermissionError):
            return HttpResponse.error(403, "Voice session access denied", code="FORBIDDEN")
        except RuntimeError as exc:
            return HttpResponse.error(409, str(exc), code="VOICE_SESSION_CLOSED")
        return HttpResponse.json(snapshot.model_dump(mode="json"))

    async def _handle_list_workspaces(self) -> HttpResponse:
        manager = self.runtime.workspace_manager
        if not manager:
            return HttpResponse.json({"workspaces": []})
        records = []
        for record in manager.list_workspaces():
            task = await self.runtime.repository.get_task(record.task_id)
            if task is not None and task.owner_id == self.runtime.config.owner_id:
                records.append(record)
        return HttpResponse.json(
            {
                "workspaces": [
                    {
                        "workspace_id": r.workspace_id,
                        "task_id": r.task_id,
                        "status": r.status.value,
                        "base_commit": r.base_commit,
                        "lease_owner": r.lease_owner,
                        "lease_expires_at": r.lease_expires_at.isoformat()
                        if r.lease_expires_at
                        else None,
                    }
                    for r in records
                ]
            }
        )

    async def _handle_workspace_diff(self, ws_id: str) -> HttpResponse:
        try:
            if not self.runtime.workspace_manager:
                return HttpResponse.error(
                    400, "Workspace manager unavailable", code="NO_WORKSPACE_MANAGER"
                )
            if not await self._workspace_is_owned(ws_id):
                return HttpResponse.error(404, "Workspace not found", code="NOT_FOUND")
            artifact = self.runtime.workspace_manager.diff_workspace(ws_id)
            return HttpResponse.json({"workspace_id": ws_id, "diff": artifact.diff})
        except Exception:
            logger.exception("Workspace diff failed for %s", ws_id)
            return HttpResponse.error(
                400, "Workspace diff request failed", code="WORKSPACE_DIFF_ERROR"
            )

    async def _handle_workspace_validate(self, ws_id: str, request: HttpRequest) -> HttpResponse:
        data = request.json() or {}
        commands = data.get("commands", [])
        if (
            not isinstance(commands, list)
            or not commands
            or any(not isinstance(command, str) or not command.strip() for command in commands)
        ):
            return HttpResponse.error(
                400, "commands must be a non-empty list of strings", code="INVALID_INPUT"
            )
        try:
            if not await self._workspace_is_owned(ws_id):
                return HttpResponse.error(404, "Workspace not found", code="NOT_FOUND")
            report = await self.runtime.validate_workspace_authorized(
                ws_id,
                commands,
                grant_id=self._grant_id(request),
                device_id=self._device_id(request),
            )
            return HttpResponse.json(report.model_dump(mode="json"))
        except OperationAuthorizationError:
            return HttpResponse.error(
                403, "Operation authorization failed", code="AUTHORIZATION_REQUIRED"
            )
        except IntegrationValidationError as exc:
            return HttpResponse.error(422, str(exc), code="VALIDATION_FAILED")
        except Exception:
            logger.exception("Workspace validation failed for %s", ws_id)
            return HttpResponse.error(400, "Workspace validation failed", code="VALIDATION_ERROR")

    async def _handle_workspace_integrate(self, ws_id: str, request: HttpRequest) -> HttpResponse:
        data = request.json() or {}
        commit_message = data.get("commit_message", "Integrated workspace changes")
        grant_id = self._grant_id(request)
        device_id = self._device_id(request)
        try:
            if not await self._workspace_is_owned(ws_id):
                return HttpResponse.error(404, "Workspace not found", code="NOT_FOUND")
            if not grant_id or not device_id:
                return HttpResponse.error(
                    403,
                    "A persisted grant and device identity are required.",
                    code="AUTHORIZATION_REQUIRED",
                )
            record = await self.runtime.integrate_workspace(
                workspace_id=ws_id,
                grant_id=grant_id,
                device_id=device_id,
                commit_message=str(commit_message),
            )
            return HttpResponse.json(record.model_dump(mode="json"))
        except (IntegrationAuthorizationError, OperationAuthorizationError):
            return HttpResponse.error(
                403, "Operation authorization failed", code="AUTHORIZATION_REQUIRED"
            )
        except IntegrationConflictError as exc:
            return HttpResponse.error(409, str(exc), code="INTEGRATION_CONFLICT")
        except Exception:
            logger.exception("Workspace integration failed for %s", ws_id)
            return HttpResponse.error(400, "Workspace integration failed", code="INTEGRATION_ERROR")

    async def _handle_rollback_integration(
        self, integration_id: str, request: HttpRequest
    ) -> HttpResponse:
        grant_id = self._grant_id(request)
        device_id = self._device_id(request)
        try:
            if not grant_id or not device_id:
                return HttpResponse.error(
                    403,
                    "A persisted grant and device identity are required.",
                    code="AUTHORIZATION_REQUIRED",
                )
            await self.runtime.rollback_integration(
                integration_id,
                grant_id=grant_id,
                device_id=device_id,
            )
            return HttpResponse.json({"integration_id": integration_id, "status": "rolled_back"})
        except (IntegrationAuthorizationError, OperationAuthorizationError):
            return HttpResponse.error(
                403, "Operation authorization failed", code="AUTHORIZATION_REQUIRED"
            )
        except Exception:
            logger.exception("Integration rollback failed for %s", integration_id)
            return HttpResponse.error(400, "Integration rollback failed", code="ROLLBACK_ERROR")

    async def _handle_companion_projection(self) -> HttpResponse:
        """P08.5: Exposes independent dialogue state vs background worker activity."""

        def read_active(db: Any) -> list[TaskRecord]:
            cursor = db.execute(
                "SELECT payload FROM tasks WHERE owner_id=? AND status NOT IN (?, ?, ?, ?)",
                (self.runtime.config.owner_id, "planned", "completed", "failed", "cancelled"),
            )
            return [TaskRecord.model_validate_json(row[0]) for row in cursor.fetchall()]

        active_tasks = await self.runtime.repository.database.read(read_active)
        return HttpResponse.json(
            {
                "companion": self.runtime.companion_status(),
                "specialists": {
                    "cody": {
                        "active_tasks": [
                            t.task_id
                            for t in active_tasks
                            if t.effective_backend in ("codex", "cody")
                        ]
                    },
                    "hermes": {
                        "active_tasks": [
                            t.task_id for t in active_tasks if t.effective_backend in ("hermes",)
                        ]
                    },
                    "antigravity": {
                        "active_tasks": [
                            t.task_id
                            for t in active_tasks
                            if t.effective_backend in ("antigravity",)
                        ]
                    },
                },
                "background_workers_active": len(active_tasks),
            }
        )

    async def _handle_settings_projection(self) -> HttpResponse:
        """P08.5: Exposes validated redacted settings with secrets masked."""
        return HttpResponse.json(
            {
                "owner_id": self.runtime.config.owner_id,
                "project_id": self.runtime.config.project_id,
                "conversation_id": self.runtime.config.conversation_id,
                "worker_count": self.runtime.config.worker_count,
                "dialogue_backend": self.runtime.config.dialogue_backend,
                "dialogue_model": self.runtime.config.dialogue_model,
                "dialogue_managed": self.runtime.config.managed_dialogue,
                "dialogue_model_folder": (
                    str(self.runtime.config.dialogue_model_folder)
                    if self.runtime.config.dialogue_model_folder is not None
                    else None
                ),
                "dialogue_base_url": self.runtime.config.dialogue_base_url,
                "dialogue_timeout_seconds": self.runtime.config.dialogue_timeout_seconds,
                "dialogue_api_key_configured": self.runtime.config.dialogue_api_key is not None,
                "secrets": ["***REDACTED***" for _ in self.runtime.config.secrets],
                "coding_workspace_configured": self.runtime.config.coding_workspace_root
                is not None,
                "content_roots_configured": len(self.runtime.config.allowed_content_roots()),
                "content_roots": [
                    str(root) for root in self.runtime.config.allowed_content_roots()
                ],
                "editor_roots": [str(root) for root in self.runtime.config.allowed_editor_roots()],
                "context_max_chars": self.runtime.config.context_max_chars,
                "content_handlers": [
                    {
                        "handler_id": handler.handler_id,
                        "kinds": list(handler.kinds),
                        "verbs": list(handler.verbs),
                        "supports_line": handler.supports_line,
                        "supports_column": handler.supports_column,
                        "supports_highlight": handler.supports_highlight,
                    }
                    for handler in self.runtime.config.content_handlers
                ],
                **self.runtime.runtime_settings_view(),
            }
        )

    async def _handle_scan_models(self, request: HttpRequest) -> HttpResponse:
        data = request.json() or {}
        folder = data.get("folder")
        if not isinstance(folder, str):
            return HttpResponse.error(400, "Select a local models folder", code="INVALID_INPUT")
        try:
            models = await scan_lm_studio_models(folder)
        except ModelCatalogError as exc:
            return HttpResponse.error(422, str(exc), code="MODEL_SCAN_UNAVAILABLE")
        return HttpResponse.json({"models": models, "count": len(models)})

    async def _handle_update_settings(self, request: HttpRequest) -> HttpResponse:
        """Stage one exact owner-local, credential-free runtime configuration edit."""
        controller = self.runtime.app_settings
        if controller is not None:
            try:
                update_v2 = SettingsEdit.model_validate(request.json())
                return HttpResponse.json(controller.save(update_v2))
            except SettingsConflict as exc:
                return HttpResponse.error(409, str(exc), code="SETTINGS_CONFLICT")
            except (ValueError, OSError) as exc:
                return HttpResponse.error(422, self._settings_error(exc), code="INVALID_SETTINGS")
        try:
            update = RuntimeSettingsUpdate.model_validate(request.json())
        except ValueError:
            return HttpResponse.error(
                400, "Settings fields or dialogue endpoint are invalid", code="INVALID_INPUT"
            )
        try:
            revision = await self.runtime.stage_runtime_settings(update)
        except ModelCatalogError as exc:
            return HttpResponse.error(422, str(exc), code="MODEL_SELECTION_UNAVAILABLE")
        except ValueError as exc:
            if str(exc) == "runtime settings changed before this edit":
                return HttpResponse.error(409, str(exc), code="SETTINGS_CONFLICT")
            return HttpResponse.error(400, "Settings cannot be applied", code="INVALID_INPUT")
        return HttpResponse.json(
            {
                "settings_revision": revision,
                "restart_required": revision != self.runtime.active_settings_revision,
            }
        )

    @staticmethod
    def _settings_error(exc: Exception) -> str:
        # Pydantic's str() includes inputs. Expose only field/message, never raw payload values.
        from pydantic import ValidationError

        if isinstance(exc, ValidationError):
            return "; ".join(
                ".".join(str(p) for p in item["loc"]) + ": " + item["msg"]
                for item in exc.errors(include_input=False)[:8]
            )
        return str(exc)[:500]

    def _handle_model_settings(self, path: str, request: HttpRequest) -> HttpResponse:
        controller = self.runtime.app_settings
        if controller is None:
            return HttpResponse.error(
                409, "Restart Core to enable unified Settings", code="UNAVAILABLE"
            )
        try:
            if path.endswith("/projectors"):
                data = request.json() or {}
                if not isinstance(data.get("model_path"), str):
                    raise ValueError("Select a model GGUF")
                return HttpResponse.json({"projectors": discover_projectors(data["model_path"])})
            if path.endswith("/refresh"):
                return HttpResponse.json(controller.refresh())
            result = controller.request_reload(ReloadRequest.model_validate(request.json()))
            return HttpResponse.json(result, status_code=202)
        except SettingsConflict as exc:
            return HttpResponse.error(409, str(exc), code="SETTINGS_CONFLICT")
        except (ValueError, OSError) as exc:
            return HttpResponse.error(422, self._settings_error(exc), code="INVALID_SETTINGS")

    async def _handle_permissions_projection(self) -> HttpResponse:
        """Owner-local, non-authorizing grant metadata for client inspection."""

        def read(db: Any) -> tuple[int, list[dict[str, Any]]]:
            owner_id = self.runtime.config.owner_id
            count = db.execute(
                "SELECT COUNT(*) FROM grants WHERE owner_id=?", (owner_id,)
            ).fetchone()[0]
            rows = db.execute(
                "SELECT payload FROM grants WHERE owner_id=? ORDER BY rowid DESC LIMIT 100",
                (owner_id,),
            ).fetchall()
            grants = []
            for row in rows:
                grant = json.loads(row[0])
                grants.append(
                    {
                        "device_id": grant["device_id"],
                        "project_id": grant.get("project_id"),
                        "operation": grant["operation"],
                        "resource": grant["resource"],
                        "status": grant["status"],
                        "not_before": grant["not_before"],
                        "expires_at": grant["expires_at"],
                        "max_uses": grant.get("max_uses"),
                        "used_count": grant["used_count"],
                    }
                )
            return count, grants

        total, grants = await self.runtime.repository.database.read(read)
        return HttpResponse.json({"total": total, "grants": grants, "truncated": total > 100})

    async def _handle_objects_projection(self) -> HttpResponse:
        """P08.5: Exposes canonical desktop objects (Kanban board projection)."""

        def read_kanban(db: Any) -> list[dict[str, Any]]:
            rows = db.execute(
                "SELECT t.payload, m.content, b.column_name, b.assigned_agent, "
                "b.archived_at, b.version, b.updated_by, "
                "(SELECT COUNT(*) FROM agent_runs r WHERE r.task_id=t.task_id) AS run_count "
                "FROM tasks t LEFT JOIN messages m "
                "ON m.message_id=json_extract(t.payload, '$.creator_message_id') "
                "LEFT JOIN board_cards b ON b.task_id=t.task_id "
                "WHERE t.owner_id=? AND t.project_id=? AND b.archived_at IS NULL "
                "ORDER BY t.rowid DESC LIMIT 200",
                (self.runtime.config.owner_id, self.runtime.config.project_id),
            ).fetchall()
            tasks = tuple(TaskRecord.model_validate_json(row[0]) for row in rows)
            summaries = {
                task.task_id: (row[1] or "").removeprefix("Fix this later: ")
                for task, row in zip(tasks, rows, strict=True)
            }
            board = project_tasks_to_kanban(tasks, summaries=summaries)
            return [
                {
                    "task_id": card.task_id,
                    "column": row[2] or card.column.value,
                    "status": card.status.value,
                    "intent": card.summary,
                    "referent_id": f"task:{card.task_id}",
                    "artifact_ids": [task.result_ref] if task.result_ref else [],
                    "specialist": card.specialist,
                    "assigned_agent": row[3] or card.specialist,
                    "column_source": "manual" if row[2] else "lifecycle",
                    "board_version": row[5] or 0,
                    "updated_by": row[6],
                    "needs_attention": card.needs_attention,
                    "run_count": int(row[7]),
                    "updated_at": task.updated_at.isoformat(),
                }
                for card, task, row in zip(board.cards, tasks, rows, strict=True)
            ]

        kanban_cards = await self.runtime.repository.database.read(read_kanban)
        return HttpResponse.json(
            {
                "object_id": "obj-kanban-main",
                "type": "KanbanBoard",
                "cards": kanban_cards,
                "objects": [
                    item.model_dump(mode="json") for item in self.runtime.project_desktop_objects()
                ],
            }
        )

    async def _handle_desktop_object_affordance(
        self, object_id: str, request: HttpRequest
    ) -> HttpResponse:
        """P12.6: Resolve one visible advertised object affordance under exact policy."""
        body = request.json()
        if not isinstance(body, dict):
            return HttpResponse.error(
                400, "Request body must be a JSON object", code="INVALID_REQUEST"
            )
        try:
            affordance = DesktopObjectAffordanceRequest.model_validate(body)
        except Exception as exc:
            return HttpResponse.error(
                400, f"Invalid desktop-object affordance request: {exc}", code="INVALID_REQUEST"
            )
        if affordance.object_id != object_id:
            return HttpResponse.error(
                400, "Path and body object identifiers differ", code="INVALID_REQUEST"
            )
        try:
            command = await self.runtime.present_desktop_object_affordance(
                affordance,
                grant_id=self._grant_id(request),
                device_id=self._device_id(request),
            )
        except OperationAuthorizationError:
            return HttpResponse.error(
                403, "Desktop-object affordance not authorized", code="FORBIDDEN"
            )
        except DesktopObjectAffordanceError as exc:
            status = 404 if exc.code == "not_available" else 409
            return HttpResponse.error(
                status, "Desktop object is not available", code=exc.code.upper()
            )
        return HttpResponse.json({"status": "queued", "command": command.model_dump(mode="json")})

    async def _extension_is_active(
        self, extension: ExtensionRegistration, request: HttpRequest
    ) -> bool:
        if not extension.enabled:
            return False
        for grant_id in extension.required_grants:
            try:
                await self.runtime.authorize_operation(
                    grant_id=grant_id,
                    device_id=self._device_id(request),
                    resource=f"extension.control:{extension.extension_id}",
                )
            except OperationAuthorizationError:
                return False
        return True

    async def _handle_capabilities_projection(self, request: HttpRequest) -> HttpResponse:
        """P08.5: Exposes active capability set and semantic verbs."""
        active_extensions = [
            extension.extension_id
            for extension in self._extensions.values()
            if await self._extension_is_active(extension, request)
        ]
        return HttpResponse.json(
            {
                "available_verbs": [
                    "open",
                    "show",
                    "look",
                    "point",
                    "type",
                    "play",
                    "pause",
                    "send",
                    "search",
                    "add_task",
                    "move_task",
                    "complete_task",
                    "delegate",
                ],
                "active_extensions": active_extensions,
                "projection_revision": await self.runtime.repository.database.read(
                    lambda db: int(
                        db.execute("SELECT revision FROM state_meta WHERE singleton=1").fetchone()[
                            0
                        ]
                    )
                ),
            }
        )

    async def _handle_enable_extension(self, ext_id: str, request: HttpRequest) -> HttpResponse:
        """P08.6: Enable extension and activate schemas."""
        ext = self._extensions.get(ext_id)
        if not ext:
            return HttpResponse.error(404, f"Extension '{ext_id}' not found", code="NOT_FOUND")
        grant_id = self._grant_id(request)
        if not grant_id or grant_id not in ext.required_grants:
            return HttpResponse.error(
                403,
                "The extension's required persisted grant was not supplied",
                code="AUTHORIZATION_REQUIRED",
            )
        try:
            authorization = await self.runtime.authorize_operation(
                grant_id=grant_id,
                device_id=self._device_id(request),
                resource=f"extension.control:{ext_id}",
            )
            await self.runtime.consume_operation(authorization)
        except OperationAuthorizationError:
            return HttpResponse.error(
                403, "Operation authorization failed", code="AUTHORIZATION_REQUIRED"
            )
        updated = ext.model_copy(update={"enabled": True})
        self._extensions[ext_id] = updated
        self._save_extension_state()
        return HttpResponse.json(updated.model_dump(mode="json"))

    async def _handle_disable_extension(self, ext_id: str) -> HttpResponse:
        """P08.6: Disable extension; immediately invalidates active capability sets."""
        ext = self._extensions.get(ext_id)
        if not ext:
            return HttpResponse.error(404, f"Extension '{ext_id}' not found", code="NOT_FOUND")
        updated = ext.model_copy(update={"enabled": False})
        self._extensions[ext_id] = updated
        self._save_extension_state()
        return HttpResponse.json(updated.model_dump(mode="json"))

    async def _handle_extension_schema(self, ext_id: str) -> HttpResponse:
        """Load a built-in extension's versioned schema only when requested."""
        ext = self._extensions.get(ext_id)
        if not ext:
            return HttpResponse.error(404, f"Extension '{ext_id}' not found", code="NOT_FOUND")
        if not ext.schema_ref or ext.schema_ref not in self._extension_schemas:
            return HttpResponse.error(404, "Extension schema not found", code="NOT_FOUND")
        return HttpResponse.json(
            {
                "extension_id": ext_id,
                "version": ext.version,
                "schema_ref": ext.schema_ref,
                "schema": self._extension_schemas[ext.schema_ref],
            }
        )

    async def _handle_desktop_observation(self, request: HttpRequest) -> HttpResponse:
        try:
            observation = DesktopObservationRequest.model_validate(request.json())
        except ValueError:
            return HttpResponse.error(400, "Invalid observation request", code="INVALID_REQUEST")
        try:
            result = await self.runtime.observe_desktop(
                observation,
                grant_id=self._grant_id(request),
                device_id=self._device_id(request),
            )
        except PermissionError:
            return HttpResponse.error(403, "Desktop observation not authorized", code="FORBIDDEN")
        return HttpResponse.json(result.model_dump(mode="json"))

    async def _handle_desktop_capture(self, request: HttpRequest) -> HttpResponse:
        try:
            capture_request = DesktopCaptureRequest.model_validate(request.json())
        except ValueError:
            return HttpResponse.error(
                400, "Invalid desktop capture request", code="INVALID_REQUEST"
            )
        try:
            result = await self.runtime.capture_desktop(
                capture_request,
                grant_id=self._grant_id(request),
                device_id=self._device_id(request),
            )
        except PermissionError:
            return HttpResponse.error(403, "Desktop capture not authorized", code="FORBIDDEN")
        except DesktopTargetError as exc:
            return self._desktop_target_error(exc)
        except ValueError as exc:
            return HttpResponse.error(409, str(exc), code="DESKTOP_CAPTURE_REJECTED")
        return HttpResponse.json(result.model_dump(mode="json"))

    async def _handle_vision_evidence(self, request: HttpRequest) -> HttpResponse:
        try:
            evidence_request = VisionEvidenceBatchRequest.model_validate(request.json())
        except ValueError:
            return HttpResponse.error(
                400, "Invalid vision evidence request", code="INVALID_REQUEST"
            )
        try:
            result = await self.runtime.normalize_vision_evidence(
                evidence_request,
                grant_id=self._grant_id(request),
                device_id=self._device_id(request),
            )
        except PermissionError:
            return HttpResponse.error(403, "Vision evidence not authorized", code="FORBIDDEN")
        except ValueError as exc:
            return HttpResponse.error(409, str(exc), code="VISION_EVIDENCE_REJECTED")
        return HttpResponse.json(result.model_dump(mode="json"))

    async def _handle_attention_crop(self, request: HttpRequest) -> HttpResponse:
        try:
            crop_request = AttentionCropFallbackRequest.model_validate(request.json())
        except ValueError:
            return HttpResponse.error(400, "Invalid attention crop request", code="INVALID_REQUEST")
        try:
            result = await self.runtime.capture_attention_fallback(
                crop_request,
                grant_id=self._grant_id(request),
                device_id=self._device_id(request),
            )
        except PermissionError:
            return HttpResponse.error(403, "Attention crop not authorized", code="FORBIDDEN")
        except ValueError as exc:
            return HttpResponse.error(409, str(exc), code="ATTENTION_CROP_REJECTED")
        return HttpResponse.json(result.model_dump(mode="json"))

    async def _handle_desktop_events(self, request: HttpRequest) -> HttpResponse:
        try:
            batch = DesktopEventBatch.model_validate(request.json())
        except ValueError:
            return HttpResponse.error(400, "Invalid desktop event batch", code="INVALID_REQUEST")
        try:
            result = await self.runtime.ingest_desktop_events(
                batch,
                grant_id=self._grant_id(request),
                device_id=self._device_id(request),
            )
        except PermissionError:
            return HttpResponse.error(403, "Desktop events not authorized", code="FORBIDDEN")
        except ValueError as exc:
            return HttpResponse.error(409, str(exc), code="DESKTOP_EVENT_REJECTED")
        return HttpResponse.json(result.model_dump(mode="json"))

    async def _handle_desktop_event_subscription(self, request: HttpRequest) -> HttpResponse:
        try:
            subscription = DesktopEventSubscriptionRequest.model_validate(request.json())
        except ValueError:
            return HttpResponse.error(
                400, "Invalid desktop event subscription request", code="INVALID_REQUEST"
            )
        try:
            if subscription.enabled:
                result = await self.runtime.start_desktop_event_subscription(
                    grant_id=self._grant_id(request),
                    device_id=self._device_id(request),
                )
            else:
                result = await self.runtime.stop_desktop_event_subscription()
        except PermissionError:
            return HttpResponse.error(
                403, "Desktop event subscription not authorized", code="FORBIDDEN"
            )
        except (RuntimeError, ValueError) as exc:
            return HttpResponse.error(409, str(exc), code="DESKTOP_EVENT_SUBSCRIPTION_REJECTED")
        return HttpResponse.json(result)

    async def _handle_cursor_samples(self, request: HttpRequest) -> HttpResponse:
        try:
            batch = CursorSampleBatch.model_validate(request.json())
        except ValueError:
            return HttpResponse.error(400, "Invalid cursor sample batch", code="INVALID_REQUEST")
        try:
            accepted = await self.runtime.ingest_cursor_samples(
                batch,
                grant_id=self._grant_id(request),
                device_id=self._device_id(request),
            )
        except PermissionError:
            return HttpResponse.error(403, "Cursor capture not authorized", code="FORBIDDEN")
        except ValueError as exc:
            return HttpResponse.error(409, str(exc), code="CURSOR_SAMPLE_REJECTED")
        return HttpResponse.json({"status": "accepted", "sample_count": accepted})

    async def _handle_selection_sample(self, request: HttpRequest) -> HttpResponse:
        try:
            sample = SelectionSample.model_validate(request.json())
        except ValueError:
            return HttpResponse.error(400, "Invalid selection sample", code="INVALID_REQUEST")
        try:
            await self.runtime.ingest_selection_sample(
                sample,
                grant_id=self._grant_id(request),
                device_id=self._device_id(request),
            )
        except PermissionError:
            return HttpResponse.error(403, "Selection capture not authorized", code="FORBIDDEN")
        except DesktopTargetError as exc:
            return self._desktop_target_error(exc)
        except ValueError as exc:
            return HttpResponse.error(409, str(exc), code="SELECTION_SAMPLE_REJECTED")
        return HttpResponse.json({"status": "accepted"})

    async def _handle_attention_resolution(self, request: HttpRequest) -> HttpResponse:
        try:
            resolution_request = AttentionResolveRequest.model_validate(request.json())
        except ValueError:
            return HttpResponse.error(
                400, "Invalid attention resolution request", code="INVALID_REQUEST"
            )
        try:
            resolution = await self.runtime.resolve_attention(
                resolution_request,
                grant_id=self._grant_id(request),
                device_id=self._device_id(request),
            )
        except PermissionError:
            return HttpResponse.error(403, "Attention resolution not authorized", code="FORBIDDEN")
        return HttpResponse.json(resolution.model_dump(mode="json"))

    async def _handle_reference_resolution(self, request: HttpRequest) -> HttpResponse:
        try:
            resolution_request = ReferenceResolveRequest.model_validate(request.json())
        except ValueError:
            return HttpResponse.error(400, "Invalid reference request", code="INVALID_REQUEST")
        try:
            resolution = await self.runtime.resolve_reference(
                resolution_request,
                device_id=self._device_id(request),
                revalidation_grant_id=(
                    request.header("X-SORA-Revalidation-Grant-ID") or ""
                ).strip(),
                clarification_grant_id=(
                    request.header("X-SORA-Clarification-Grant-ID") or ""
                ).strip(),
            )
        except PermissionError:
            return HttpResponse.error(
                403, "Reference presentation not authorized", code="FORBIDDEN"
            )
        return HttpResponse.json(resolution.model_dump(mode="json"))

    async def _handle_reference_pin(self, request: HttpRequest) -> HttpResponse:
        try:
            pin_request = ReferencePinRequest.model_validate(request.json())
            candidate = self.runtime.pin_reference(
                pin_request,
                device_id=self._device_id(request),
            )
        except ValueError:
            return HttpResponse.error(400, "Invalid reference pin request", code="INVALID_REQUEST")
        except ReferenceResolverError as exc:
            status = 404 if exc.code == "not_found" else 409
            return HttpResponse.error(status, str(exc), code=exc.code.upper())
        return HttpResponse.json(candidate.model_dump(mode="json"))

    async def _handle_content_navigation(self, request: HttpRequest) -> HttpResponse:
        try:
            navigation_request = ContentNavigateRequest.model_validate(request.json())
        except ValueError:
            return HttpResponse.error(
                400, "Invalid content navigation request", code="INVALID_REQUEST"
            )
        try:
            result = await self.runtime.navigate_content(
                navigation_request,
                navigation_grant_id=self._grant_id(request),
                device_id=self._device_id(request),
                presentation_grant_id=(
                    request.header("X-SORA-Presentation-Grant-ID") or ""
                ).strip(),
            )
        except PermissionError:
            return HttpResponse.error(403, "Content navigation not authorized", code="FORBIDDEN")
        return HttpResponse.json(result.model_dump(mode="json"))

    def _handle_content_references(self, request: HttpRequest) -> HttpResponse:
        references = self.runtime.reference_resolver.list_content(
            owner_id=self.runtime.config.owner_id,
            device_id=self._device_id(request),
            project_id=self.runtime.config.project_id,
        )
        return HttpResponse.json(
            {
                "references": [
                    {
                        "reference_id": item.reference_id,
                        "kind": item.kind,
                        "label": item.label,
                        "path": str(item.path),
                        "handler_id": item.handler_id,
                    }
                    for item in references
                ]
            }
        )

    async def _handle_desktop_target_acquisition(self, request: HttpRequest) -> HttpResponse:
        try:
            target_request = DesktopTargetRequest.model_validate(request.json())
        except ValueError:
            return HttpResponse.error(400, "Invalid desktop target request", code="INVALID_REQUEST")
        try:
            target = await self.runtime.acquire_desktop_target(
                target_request,
                grant_id=self._grant_id(request),
                device_id=self._device_id(request),
            )
        except PermissionError:
            return HttpResponse.error(403, "Desktop observation not authorized", code="FORBIDDEN")
        except DesktopTargetError as exc:
            return self._desktop_target_error(exc)
        return HttpResponse.json(target.model_dump(mode="json"), status_code=201)

    async def _handle_desktop_target_revalidation(
        self, target_id: str, request: HttpRequest
    ) -> HttpResponse:
        try:
            revalidation = DesktopTargetRevalidationRequest.model_validate(request.json())
        except ValueError:
            return HttpResponse.error(
                400, "Invalid target revalidation request", code="INVALID_REQUEST"
            )
        try:
            target = await self.runtime.revalidate_desktop_target(
                target_id,
                authority=revalidation.authority,
                grant_id=self._grant_id(request),
                device_id=self._device_id(request),
            )
        except PermissionError:
            return HttpResponse.error(403, "Desktop target authority denied", code="FORBIDDEN")
        except DesktopTargetError as exc:
            return self._desktop_target_error(exc)
        return HttpResponse.json(target.model_dump(mode="json"))

    async def _handle_desktop_target_presentation(
        self, target_id: str, request: HttpRequest
    ) -> HttpResponse:
        try:
            presentation = DesktopPresentationRequest.model_validate(request.json())
        except ValueError:
            return HttpResponse.error(
                400, "Invalid desktop presentation request", code="INVALID_REQUEST"
            )
        try:
            command = await self.runtime.present_desktop_target(
                target_id,
                verb=presentation.verb,
                grant_id=self._grant_id(request),
                device_id=self._device_id(request),
                marker_duration_seconds=presentation.marker_duration_seconds,
            )
        except PermissionError:
            return HttpResponse.error(403, "Desktop presentation denied", code="FORBIDDEN")
        except DesktopTargetError as exc:
            return self._desktop_target_error(exc)
        return HttpResponse.json({"status": "queued", "command": command.model_dump(mode="json")})

    async def _handle_desktop_target_press(
        self, target_id: str, request: HttpRequest
    ) -> HttpResponse:
        try:
            press = DesktopPressRequest.model_validate(request.json())
        except ValueError:
            return HttpResponse.error(400, "Invalid desktop press request", code="INVALID_REQUEST")
        try:
            result = await self.runtime.press_desktop_target(
                target_id,
                press,
                grant_id=self._grant_id(request),
                device_id=self._device_id(request),
            )
        except ValueError:
            return HttpResponse.error(
                409,
                "Desktop action attempt ID conflicts with an earlier request",
                code="ACTION_ATTEMPT_CONFLICT",
            )
        return HttpResponse.json(result.model_dump(mode="json"))

    async def _handle_desktop_press_interaction(
        self, target_id: str, request: HttpRequest
    ) -> HttpResponse:
        try:
            press = DesktopPressRequest.model_validate(request.json())
        except ValueError:
            return HttpResponse.error(400, "Invalid PRESS interaction", code="INVALID_REQUEST")
        try:
            command = await self.runtime.prepare_desktop_press_interaction(
                target_id,
                press,
                grant_id=self._grant_id(request),
                device_id=self._device_id(request),
            )
        except OperationAuthorizationError:
            return HttpResponse.error(403, "Desktop interaction denied", code="FORBIDDEN")
        except DesktopTargetError as exc:
            return self._desktop_target_error(exc)
        except ValueError as exc:
            return HttpResponse.error(409, str(exc), code="INTERACTION_NOT_READY")
        return HttpResponse.json({"status": "queued", "command": command.model_dump(mode="json")})

    async def _handle_desktop_target_type(
        self, target_id: str, request: HttpRequest
    ) -> HttpResponse:
        try:
            type_request = DesktopTypeRequest.model_validate(request.json())
        except ValueError:
            return HttpResponse.error(400, "Invalid TYPE request", code="INVALID_REQUEST")
        try:
            result = await self.runtime.type_desktop_target(
                target_id,
                type_request,
                grant_id=self._grant_id(request),
                device_id=self._device_id(request),
            )
        except ValueError:
            return HttpResponse.error(
                409,
                "Desktop action attempt ID conflicts with an earlier request",
                code="ACTION_ATTEMPT_CONFLICT",
            )
        return HttpResponse.json(result.model_dump(mode="json"))

    async def _handle_desktop_type_interaction(
        self, target_id: str, request: HttpRequest
    ) -> HttpResponse:
        try:
            type_request = DesktopTypeRequest.model_validate(request.json())
        except ValueError:
            return HttpResponse.error(400, "Invalid TYPE interaction", code="INVALID_REQUEST")
        try:
            command = await self.runtime.prepare_desktop_type_interaction(
                target_id,
                type_request,
                grant_id=self._grant_id(request),
                device_id=self._device_id(request),
            )
        except OperationAuthorizationError:
            return HttpResponse.error(403, "Desktop interaction denied", code="FORBIDDEN")
        except DesktopTargetError as exc:
            return self._desktop_target_error(exc)
        except ValueError as exc:
            return HttpResponse.error(409, str(exc), code="INTERACTION_NOT_READY")
        return HttpResponse.json({"status": "queued", "command": command.model_dump(mode="json")})

    async def _handle_desktop_interaction_contact(
        self, attempt_id: str, request: HttpRequest
    ) -> HttpResponse:
        try:
            result = await self.runtime.contact_prepared_desktop_interaction(
                attempt_id,
                device_id=self._device_id(request),
            )
        except LookupError:
            return HttpResponse.error(
                404, "Prepared interaction not found", code="INTERACTION_NOT_FOUND"
            )
        except TimeoutError:
            return HttpResponse.error(
                410, "Prepared interaction expired", code="INTERACTION_EXPIRED"
            )
        except OperationAuthorizationError:
            return HttpResponse.error(403, "Desktop interaction denied", code="FORBIDDEN")
        return HttpResponse.json(result.model_dump(mode="json"))

    @staticmethod
    def _desktop_target_error(exc: DesktopTargetError) -> HttpResponse:
        if exc.code == "not_found":
            return HttpResponse.error(404, "Desktop target not found", code="TARGET_NOT_FOUND")
        if exc.code == "expired":
            return HttpResponse.error(410, "Desktop target expired", code="TARGET_EXPIRED")
        return HttpResponse.error(
            409,
            "Desktop target requires reacquisition",
            code=f"TARGET_{exc.code.upper()}",
        )

    @staticmethod
    def _editor_context_error(exc: EditorContextError) -> HttpResponse:
        if exc.code == "task_not_found":
            return HttpResponse.error(404, "Editor task not found", code="EDITOR_TASK_NOT_FOUND")
        if exc.code == "stale_capture":
            return HttpResponse.error(410, "Editor context capture expired", code="EDITOR_STALE")
        return HttpResponse.error(
            409,
            "Editor context could not be verified",
            code=f"EDITOR_{exc.code.upper()}",
        )

    async def _handle_embodiment_command(self, request: HttpRequest) -> HttpResponse:
        """P09.4/P09.5: Dispatch movement or gaze command to embodiment client."""
        body = request.json()
        if not isinstance(body, dict):
            return HttpResponse.error(
                400, "Request body must be a JSON object", code="INVALID_REQUEST"
            )
        try:
            cmd = EmbodimentCommand.model_validate(body)
        except Exception as err:
            return HttpResponse.error(
                400, f"Invalid embodiment command: {err}", code="INVALID_COMMAND"
            )

        if not self.runtime.topology_manager.validate_revision(cmd.topology_revision):
            message = (
                f"Command topology revision {cmd.topology_revision} does not match "
                f"active revision {self.runtime.topology_manager.revision}"
            )
            return HttpResponse.error(
                409,
                message,
                code="STALE_TOPOLOGY_REVISION",
            )
        try:
            await self.runtime.dispatch_embodiment_command(
                cmd, grant_id=self._grant_id(request), device_id=self._device_id(request)
            )
        except OperationAuthorizationError:
            return HttpResponse.error(403, "Embodiment command not authorized", code="FORBIDDEN")
        except ValueError as err:
            return HttpResponse.error(409, str(err), code="EMBODIMENT_NOT_READY")
        return HttpResponse.json({"status": "queued", "command_id": cmd.command_id})

    async def _handle_embodiment_topology(self, request: HttpRequest) -> HttpResponse:
        """P09.4/P09.6: Update display topology reported by embodiment client."""
        try:
            await self.runtime.authorize_operation(
                grant_id=self._grant_id(request),
                device_id=self._device_id(request),
                resource="embodiment.topology",
            )
        except OperationAuthorizationError:
            return HttpResponse.error(403, "Topology update not authorized", code="FORBIDDEN")
        body = request.json()
        if not isinstance(body, dict):
            return HttpResponse.error(
                400, "Request body must be a JSON object", code="INVALID_REQUEST"
            )
        monitors_data = body.get("monitors")
        if not isinstance(monitors_data, list):
            return HttpResponse.error(
                400, "monitors field required as list", code="INVALID_REQUEST"
            )
        try:
            monitors = tuple(MonitorDescriptor.model_validate(m) for m in monitors_data)
            vd_data = body.get("virtual_desktop")
            vd_rect = ScreenRect.model_validate(vd_data) if vd_data else None
            new_rev = self.runtime.update_embodiment_topology(monitors, vd_rect)
        except Exception as err:
            return HttpResponse.error(400, f"Invalid topology data: {err}", code="INVALID_TOPOLOGY")

        return HttpResponse.json({"status": "updated", "revision": new_rev})
