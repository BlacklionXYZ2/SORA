"""Registry used to publish deterministic JSON Schemas."""

from __future__ import annotations

from pydantic import BaseModel

from .models import (
    ActiveCapabilitySet,
    AgentRunRecord,
    AgentSessionRecord,
    ApprovalRequest,
    AttentionTarget,
    CapabilityDescriptor,
    CapabilityGrant,
    CapabilityIndex,
    CapabilityRequest,
    CapabilityResolutionRequest,
    DesktopObjectRecord,
    EventEnvelope,
    ExtensionRegistration,
    NetworkProfileProjection,
    NormalizedResult,
    PatchEnvelope,
    ProviderCapabilities,
    ProviderRequest,
    ResultPresentation,
    SocialEventRecord,
    TaskRecord,
)

PUBLIC_CONTRACTS: dict[str, type[BaseModel]] = {
    "active-capability-set": ActiveCapabilitySet,
    "agent-run-record": AgentRunRecord,
    "agent-session-record": AgentSessionRecord,
    "approval-request": ApprovalRequest,
    "attention-target": AttentionTarget,
    "capability-descriptor": CapabilityDescriptor,
    "capability-grant": CapabilityGrant,
    "capability-index": CapabilityIndex,
    "capability-request": CapabilityRequest,
    "capability-resolution-request": CapabilityResolutionRequest,
    "desktop-object-record": DesktopObjectRecord,
    "event-envelope": EventEnvelope,
    "extension-registration": ExtensionRegistration,
    "network-profile-projection": NetworkProfileProjection,
    "normalized-result": NormalizedResult,
    "patch-envelope": PatchEnvelope,
    "provider-capabilities": ProviderCapabilities,
    "provider-request": ProviderRequest,
    "result-presentation": ResultPresentation,
    "social-event-record": SocialEventRecord,
    "task-record": TaskRecord,
}

