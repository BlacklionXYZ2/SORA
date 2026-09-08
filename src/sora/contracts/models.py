"""SORA v1 records, provider envelopes, patches, events, and permission contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, JsonValue, model_validator

from .base import ContractModel, Identifier, NonEmptyText, StrictModel, require_aware


class TaskStatus(StrEnum):
    QUEUED = "queued"
    ROUTING = "routing"
    REASONING = "reasoning"
    WORKING = "working"
    WAITING_FOR_PERMISSION = "waiting_for_permission"
    WAITING_FOR_INPUT = "waiting_for_input"
    CANCEL_REQUESTED = "cancel_requested"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunStatus(StrEnum):
    PENDING = "pending"
    LAUNCHING = "launching"
    RUNNING = "running"
    WAITING_FOR_PERMISSION = "waiting_for_permission"
    WAITING_FOR_INPUT = "waiting_for_input"
    CANCEL_REQUESTED = "cancel_requested"
    INTERRUPTED = "interrupted"
    UNCERTAIN = "uncertain"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    LOST = "lost"
    CLOSED = "closed"


class ProviderOutcome(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class ProviderErrorCode(StrEnum):
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    INVALID_REQUEST = "invalid_request"
    MALFORMED_RESULT = "malformed_result"
    RATE_LIMITED = "rate_limited"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    LOST_SESSION = "lost_session"
    UNCERTAIN_LAUNCH = "uncertain_launch"
    INTERNAL = "internal"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class GrantStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXHAUSTED = "exhausted"


class CapabilityOperation(StrEnum):
    TOOL_INVOKE = "tool.invoke"
    PATH_READ = "path.read"
    PATH_WRITE = "path.write"
    DESKTOP_OBSERVE = "desktop.observe"
    DESKTOP_PRESENT = "desktop.present"
    DESKTOP_NAVIGATE = "desktop.navigate"
    DESKTOP_INTERACT = "desktop.interact"


class TaskRecord(ContractModel):
    task_id: Identifier
    owner_id: Identifier
    project_id: Identifier | None = None
    creator_message_id: Identifier
    status: TaskStatus
    requested_backend: Identifier = "auto"
    effective_backend: Identifier | None = None
    base_revision: Annotated[int, Field(ge=0)]
    active_run_id: Identifier | None = None
    grant_ids: tuple[Identifier, ...] = ()
    constraints: tuple[NonEmptyText, ...] = ()
    result_ref: Identifier | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_record(self) -> TaskRecord:
        require_aware(self.created_at, "created_at")
        require_aware(self.updated_at, "updated_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        if len(set(self.grant_ids)) != len(self.grant_ids):
            raise ValueError("grant_ids must be unique")
        if self.status is TaskStatus.COMPLETED and self.result_ref is None:
            raise ValueError("completed tasks require result_ref")
        if (
            self.status not in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}
            and self.result_ref
        ):
            raise ValueError("non-terminal tasks cannot have result_ref")
        return self


class AgentRunRecord(ContractModel):
    run_id: Identifier
    task_id: Identifier
    attempt: Annotated[int, Field(ge=1)]
    provider: Identifier
    status: RunStatus
    native_session_id: Identifier | None = None
    lease_expires_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    outcome: ProviderOutcome | None = None

    @model_validator(mode="after")
    def validate_record(self) -> AgentRunRecord:
        for name, value in (
            ("lease_expires_at", self.lease_expires_at),
            ("started_at", self.started_at),
            ("finished_at", self.finished_at),
        ):
            if value is not None:
                require_aware(value, name)
        terminal = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}
        if self.status in terminal and (self.finished_at is None or self.outcome is None):
            raise ValueError("terminal runs require finished_at and outcome")
        if self.status not in terminal and (
            self.finished_at is not None or self.outcome is not None
        ):
            raise ValueError("non-terminal runs cannot have finished_at or outcome")
        return self


class AgentSessionRecord(ContractModel):
    session_id: Identifier
    task_id: Identifier
    owner_id: Identifier
    project_id: Identifier | None = None
    provider: Identifier
    native_session_id: Identifier
    status: SessionStatus
    resume_supported: bool
    context_fingerprint: Annotated[str, Field(min_length=16, max_length=128)]
    created_at: datetime
    last_seen_at: datetime

    @model_validator(mode="after")
    def validate_record(self) -> AgentSessionRecord:
        require_aware(self.created_at, "created_at")
        require_aware(self.last_seen_at, "last_seen_at")
        if self.last_seen_at < self.created_at:
            raise ValueError("last_seen_at cannot precede created_at")
        return self


class ProviderCapabilities(ContractModel):
    provider: Identifier
    sessions: bool = False
    resume: bool = False
    events: bool = False
    steer: bool = False
    cancel: bool = False
    tool_restrictions: bool = False
    supported_result_version: Literal["1.0"] = "1.0"
    streaming: bool = False
    filesystem: bool = False
    worktree_support: bool = False
    structured_output: bool = True
    display_name: str | None = None

    @model_validator(mode="after")
    def validate_resume(self) -> ProviderCapabilities:
        if self.resume and not self.sessions:
            raise ValueError("resume requires session support")
        return self


class ProviderRequest(ContractModel):
    request_id: Identifier
    task_id: Identifier
    run_id: Identifier
    owner_id: Identifier
    project_id: Identifier | None = None
    intent: NonEmptyText
    context: NonEmptyText
    context_manifest_ref: Identifier
    session_ref: Identifier | None = None
    workspace_ref: Identifier | None = None
    grant_ids: tuple[Identifier, ...] = ()
    deadline: datetime
    token_budget: Annotated[int, Field(ge=1)] | None = None
    artifact_destination: NonEmptyText
    idempotency_key: Identifier

    @model_validator(mode="after")
    def validate_record(self) -> ProviderRequest:
        require_aware(self.deadline, "deadline")
        if len(set(self.grant_ids)) != len(self.grant_ids):
            raise ValueError("grant_ids must be unique")
        return self


class ProviderError(StrictModel):
    code: ProviderErrorCode
    message: NonEmptyText
    retryable: bool = False
    retry_after_seconds: Annotated[float, Field(gt=0)] | None = None

    @model_validator(mode="after")
    def validate_retry(self) -> ProviderError:
        if self.retry_after_seconds is not None and not self.retryable:
            raise ValueError("retry_after_seconds requires retryable=true")
        return self


class ProposedFact(StrictModel):
    content: NonEmptyText
    epistemic_status: Literal["assertion", "observation", "inference"]
    confidence: Annotated[float, Field(ge=0, le=1)]
    evidence_refs: tuple[Identifier, ...] = ()


class ProposedMemory(StrictModel):
    content: NonEmptyText
    scope: NonEmptyText
    sensitivity: Literal["normal", "private", "secret"] = "normal"
    retention: Literal["transient", "session", "durable"] = "durable"
    evidence_refs: tuple[Identifier, ...] = ()


class ProposeFactOperation(StrictModel):
    operation: Literal["propose_fact"]
    operation_id: Identifier
    fact: ProposedFact


class ProposeMemoryOperation(StrictModel):
    operation: Literal["propose_memory"]
    operation_id: Identifier
    memory: ProposedMemory


class UpdateTaskMetadataOperation(StrictModel):
    operation: Literal["update_task_metadata"]
    operation_id: Identifier
    task_id: Identifier
    summary: NonEmptyText


PatchOperation = Annotated[
    ProposeFactOperation | ProposeMemoryOperation | UpdateTaskMetadataOperation,
    Field(discriminator="operation"),
]


class EntityPrecondition(StrictModel):
    entity_type: Literal["task", "fact", "memory", "project", "conversation"]
    entity_id: Identifier
    expected_version: Annotated[int, Field(ge=0)]


class PatchEnvelope(ContractModel):
    patch_id: Identifier
    source_run_id: Identifier
    base_revision: Annotated[int, Field(ge=0)]
    scope: NonEmptyText
    provenance: NonEmptyText
    evidence_refs: tuple[Identifier, ...] = ()
    idempotency_key: Identifier
    preconditions: tuple[EntityPrecondition, ...] = ()
    operations: Annotated[tuple[PatchOperation, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_uniqueness(self) -> PatchEnvelope:
        operation_ids = [item.operation_id for item in self.operations]
        if len(set(operation_ids)) != len(operation_ids):
            raise ValueError("operation_id values must be unique")
        preconditions = [(item.entity_type, item.entity_id) for item in self.preconditions]
        if len(set(preconditions)) != len(preconditions):
            raise ValueError("entity preconditions must be unique")
        return self


class NormalizedResult(ContractModel):
    result_id: Identifier
    task_id: Identifier
    run_id: Identifier
    base_revision: Annotated[int, Field(ge=0)]
    outcome: ProviderOutcome
    summary: NonEmptyText
    conclusion: NonEmptyText | None = None
    facts: tuple[NonEmptyText, ...] = ()
    actions_taken: tuple[NonEmptyText, ...] = ()
    files_read: tuple[NonEmptyText, ...] = ()
    files_changed: tuple[NonEmptyText, ...] = ()
    commands_run: tuple[NonEmptyText, ...] = ()
    uncertainties: tuple[NonEmptyText, ...] = ()
    warnings: tuple[NonEmptyText, ...] = ()
    memory_updates: tuple[NonEmptyText, ...] = ()
    task_updates: tuple[NonEmptyText, ...] = ()
    suggested_response: NonEmptyText | None = None
    error: ProviderError | None = None
    patch: PatchEnvelope | None = None
    usage: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> NormalizedResult:
        if self.outcome is ProviderOutcome.COMPLETED and self.conclusion is None:
            raise ValueError("completed results require conclusion")
        if self.outcome is ProviderOutcome.FAILED and self.error is None:
            raise ValueError("failed results require error")
        if self.outcome is ProviderOutcome.UNKNOWN and not self.uncertainties:
            raise ValueError("unknown results require at least one uncertainty")
        if self.outcome is not ProviderOutcome.FAILED and self.error is not None:
            raise ValueError("only failed results can carry error")
        if self.patch is not None and self.patch.source_run_id != self.run_id:
            raise ValueError("patch source_run_id must match result run_id")
        return self


class EventEnvelope(ContractModel):
    event_id: Identifier
    stream_id: Identifier
    sequence: Annotated[int, Field(ge=1)]
    timestamp: datetime
    owner_id: Identifier
    source: NonEmptyText
    event_type: Identifier
    task_id: Identifier | None = None
    run_id: Identifier | None = None
    correlation_id: Identifier
    causation_id: Identifier | None = None
    revision: Annotated[int, Field(ge=0)] | None = None
    payload: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_timestamp(self) -> EventEnvelope:
        require_aware(self.timestamp, "timestamp")
        return self


class CapabilityRequest(ContractModel):
    request_id: Identifier
    owner_id: Identifier
    device_id: Identifier
    project_id: Identifier | None = None
    operation: CapabilityOperation
    resource: NonEmptyText

    @model_validator(mode="after")
    def validate_path_resource(self) -> CapabilityRequest:
        if self.operation in {CapabilityOperation.PATH_READ, CapabilityOperation.PATH_WRITE}:
            if not Path(self.resource).is_absolute():
                raise ValueError("path capability resources must be absolute")
        return self


class CapabilityGrant(ContractModel):
    grant_id: Identifier
    owner_id: Identifier
    device_id: Identifier
    project_id: Identifier | None = None
    operation: CapabilityOperation
    resource: NonEmptyText
    status: GrantStatus = GrantStatus.ACTIVE
    issued_at: datetime
    not_before: datetime
    expires_at: datetime
    max_uses: Annotated[int, Field(ge=1)] | None = None
    used_count: Annotated[int, Field(ge=0)] = 0
    approval_id: Identifier

    @model_validator(mode="after")
    def validate_record(self) -> CapabilityGrant:
        for name, value in (
            ("issued_at", self.issued_at),
            ("not_before", self.not_before),
            ("expires_at", self.expires_at),
        ):
            require_aware(value, name)
        if self.not_before < self.issued_at:
            raise ValueError("not_before cannot precede issued_at")
        if self.expires_at <= self.not_before:
            raise ValueError("expires_at must follow not_before")
        if self.max_uses is not None and self.used_count > self.max_uses:
            raise ValueError("used_count cannot exceed max_uses")
        if self.operation in {CapabilityOperation.PATH_READ, CapabilityOperation.PATH_WRITE}:
            if not Path(self.resource).is_absolute():
                raise ValueError("path grant resources must be absolute")
        return self


class ApprovalRequest(ContractModel):
    approval_id: Identifier
    capability: CapabilityRequest
    status: ApprovalStatus
    created_at: datetime
    expires_at: datetime
    decided_at: datetime | None = None
    decided_by: Identifier | None = None

    @model_validator(mode="after")
    def validate_record(self) -> ApprovalRequest:
        require_aware(self.created_at, "created_at")
        require_aware(self.expires_at, "expires_at")
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must follow created_at")
        if self.decided_at is not None:
            require_aware(self.decided_at, "decided_at")
        decided = self.status is not ApprovalStatus.PENDING
        if decided != (self.decided_at is not None and self.decided_by is not None):
            raise ValueError("terminal approval states require decision time and actor")
        return self


# --- P03A Additive Contracts ---


class CapabilityCategory(StrEnum):
    DESKTOP = "desktop"
    FILES = "files"
    MEDIA = "media"
    TASKS = "tasks"
    SOCIAL = "social"
    CALENDAR = "calendar"
    DESKTOP_OBJECTS = "desktop_objects"
    REASONING_AGENTS = "reasoning_agents"


class CapabilityScope(StrEnum):
    LOCAL_OWNER = "local_owner"
    LOCAL_RESTRICTED = "local_restricted"
    NETWORK_PUBLIC = "network_public"
    REMOTE_GUEST = "remote_guest"


class SemanticVerb(StrEnum):
    OPEN = "open"
    SHOW = "show"
    LOOK = "look"
    POINT = "point"
    TYPE = "type"
    PLAY = "play"
    PAUSE = "pause"
    SEND = "send"
    SEARCH = "search"
    ADD_TASK = "add_task"
    MOVE_TASK = "move_task"
    COMPLETE_TASK = "complete_task"
    DELEGATE = "delegate"


class CapabilityDescriptor(ContractModel):
    capability_id: Identifier
    category: CapabilityCategory
    verbs: tuple[SemanticVerb, ...] = ()
    description: NonEmptyText
    required_scope: CapabilityScope = CapabilityScope.LOCAL_OWNER
    parameters_schema: dict[str, JsonValue] = Field(default_factory=dict)
    side_effect_class: Literal["read_only", "idempotent_write", "consequential_write"] = "read_only"


class CapabilityIndexEntry(StrictModel):
    category: CapabilityCategory
    capability_ids: tuple[Identifier, ...] = ()
    summary: NonEmptyText


class CapabilityIndex(ContractModel):
    version: Literal["1.0"] = "1.0"
    entries: tuple[CapabilityIndexEntry, ...] = ()


class CapabilityResolutionRequest(ContractModel):
    request_id: Identifier
    actor_id: Identifier
    session_id: Identifier
    scope: CapabilityScope
    intent: NonEmptyText
    active_window: str | None = None
    attention_target_refs: tuple[Identifier, ...] = ()
    desktop_object_refs: tuple[Identifier, ...] = ()
    max_capabilities: Annotated[int, Field(ge=1)] = 10


class ActiveCapabilityManifestEntry(StrictModel):
    capability_id: Identifier
    included: bool
    reason: NonEmptyText


class ActiveCapabilitySet(ContractModel):
    set_id: Identifier
    resolver_revision: Annotated[int, Field(ge=0)]
    scope: CapabilityScope
    selected_capabilities: tuple[CapabilityDescriptor, ...] = ()
    manifest: tuple[ActiveCapabilityManifestEntry, ...] = ()
    expires_at: datetime

    @model_validator(mode="after")
    def validate_record(self) -> ActiveCapabilitySet:
        require_aware(self.expires_at, "expires_at")
        return self


class PresentationMode(StrEnum):
    SILENT = "silent"
    BRIEF = "brief"
    EXPLAIN = "explain"
    WALKTHROUGH = "walkthrough"


class ResultPresentation(ContractModel):
    presentation_id: Identifier
    result_id: Identifier
    mode: PresentationMode
    significance: Literal["low", "medium", "high"]
    actor_provenance: NonEmptyText
    summary: NonEmptyText
    explanation: str | None = None
    evidence_refs: tuple[Identifier, ...] = ()
    artifact_refs: tuple[Identifier, ...] = ()
    attention_target_id: Identifier | None = None
    physical_cues: tuple[str, ...] = ()
    attention_required: bool = False


class AttentionTarget(ContractModel):
    target_id: Identifier
    source: Literal["hover", "click", "selection", "circle", "app", "task", "document", "object"]
    created_at: datetime
    expires_at: datetime
    owner_id: Identifier
    device_id: Identifier
    window_title: str | None = None
    ui_element: str | None = None
    screen_rect: tuple[int, int, int, int] | None = None
    crop_ref: Identifier | None = None
    confidence: Annotated[float, Field(ge=0, le=1)] = 1.0
    pinned: bool = False

    @model_validator(mode="after")
    def validate_record(self) -> AttentionTarget:
        require_aware(self.created_at, "created_at")
        require_aware(self.expires_at, "expires_at")
        if self.expires_at < self.created_at:
            raise ValueError("expires_at cannot precede created_at")
        return self


class SemanticActionPhase(StrEnum):
    PREPARE_INTERACTION = "PrepareInteraction"
    ACQUIRE_TARGET = "AcquireTarget"
    NAVIGATE = "Navigate"
    ORIENT = "Orient"
    BEGIN_PHYSICAL_ACTION = "BeginPhysicalAction"
    CONTACT = "Contact"
    EXECUTE_SEMANTIC_ACTION = "ExecuteSemanticAction"
    VERIFY = "Verify"
    END_PHYSICAL_ACTION = "EndPhysicalAction"
    RETURN_TO_IDLE = "ReturnToIdle"


class DesktopObjectVisibility(StrEnum):
    PRIVATE = "private"
    LOCAL_ONLY = "local_only"
    GUEST_VISIBLE = "guest_visible"
    PUBLIC = "public"


class DesktopObjectRecord(ContractModel):
    object_id: Identifier
    object_type: Identifier
    owner_id: Identifier
    anchor: NonEmptyText
    visibility: DesktopObjectVisibility = DesktopObjectVisibility.PRIVATE
    affordances: tuple[NonEmptyText, ...] = ()
    canonical_ref: Identifier | None = None
    version: Annotated[int, Field(ge=0)] = 0


class SocialEventRecord(ContractModel):
    event_id: Identifier
    network: Identifier
    actor: NonEmptyText
    content: NonEmptyText
    timestamp: datetime
    trust_classification: Literal[
        "untrusted_external", "trusted_contact", "verified_peer"
    ] = "untrusted_external"

    @model_validator(mode="after")
    def validate_record(self) -> SocialEventRecord:
        require_aware(self.timestamp, "timestamp")
        return self


class NetworkProfileProjection(ContractModel):
    profile_id: Identifier
    network: Identifier
    handle: NonEmptyText
    display_name: NonEmptyText
    bio: str = ""
    public_interests: tuple[str, ...] = ()


class ExtensionDepth(StrEnum):
    INTEGRATION = "integration"
    DESKTOP_COMPONENT = "desktop_component"
    AGENT_EXTENSION = "agent_extension"


class ExtensionRegistration(ContractModel):
    extension_id: Identifier
    depth: ExtensionDepth
    version: NonEmptyText
    enabled: bool = True
    capability_ids: tuple[Identifier, ...] = ()
    required_grants: tuple[str, ...] = ()
    config: dict[str, JsonValue] = Field(default_factory=dict)
