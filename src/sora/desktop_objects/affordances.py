"""Visibility- and capability-aware bridge from desktop objects to embodiment."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, JsonValue, model_validator

from sora.capabilities import CapabilityRegistry, CapabilityResolver
from sora.contracts.base import NonEmptyText, StrictModel
from sora.contracts.desktop_objects import (
    DesktopObjectAffordance,
    DesktopObjectAffordanceRequest,
    DesktopObjectProjection,
)
from sora.contracts.embodiment import ScreenRect
from sora.contracts.models import (
    CapabilityCategory,
    CapabilityDescriptor,
    CapabilityResolutionRequest,
    CapabilityScope,
    DesktopObjectRecord,
    DesktopObjectVisibility,
    SemanticVerb,
)


class DesktopObjectDefinition(StrictModel):
    """Core-owned object state. This record is never sent without projection."""

    record: DesktopObjectRecord
    label: NonEmptyText
    rect: ScreenRect
    topology_revision: Annotated[int, Field(ge=1)]
    content: dict[str, JsonValue] = Field(default_factory=dict)
    hidden: bool = False

    @model_validator(mode="after")
    def validate_definition(self) -> DesktopObjectDefinition:
        normalized = tuple(value.strip().lower() for value in self.record.affordances)
        if len(normalized) != len(set(normalized)):
            raise ValueError("desktop-object affordances must be unique")
        return self


class DesktopObjectAffordanceError(ValueError):
    """A non-enumerating failure to project or resolve a desktop object."""

    def __init__(self, code: str, message: str = "desktop object is not available") -> None:
        super().__init__(message)
        self.code = code


class DesktopObjectAffordanceBridge:
    """Resolve only relevant, visible, advertised affordances for registered objects."""

    def __init__(self, *, resolver_revision: int = 1, capacity: int = 64) -> None:
        if capacity < 1 or capacity > 256:
            raise ValueError("desktop-object capacity must be between 1 and 256")
        self._resolver = CapabilityResolver(revision=resolver_revision)
        self._capacity = capacity
        self._objects: dict[str, DesktopObjectDefinition] = {}

    def register(self, definition: DesktopObjectDefinition) -> None:
        object_id = definition.record.object_id
        if object_id not in self._objects and len(self._objects) >= self._capacity:
            raise ValueError("desktop-object registry is full")
        self._objects[object_id] = definition

    def snapshot(self, object_id: str) -> DesktopObjectDefinition | None:
        return self._objects.get(object_id)

    def project(
        self,
        *,
        scope: CapabilityScope,
        actor_id: str,
    ) -> tuple[DesktopObjectProjection, ...]:
        projections: list[DesktopObjectProjection] = []
        for definition in sorted(
            self._objects.values(), key=lambda value: value.record.object_id
        ):
            if not self._visible(definition, scope=scope, actor_id=actor_id):
                continue
            affordances = tuple(
                affordance
                for affordance in DesktopObjectAffordance
                if self._resolve_capability(definition, affordance, scope=scope)
            )
            record = definition.record
            projections.append(
                DesktopObjectProjection(
                    object_id=record.object_id,
                    object_type=record.object_type,
                    label=definition.label,
                    anchor=record.anchor,
                    rect=definition.rect,
                    topology_revision=definition.topology_revision,
                    affordances=affordances,
                    content=definition.content,
                    canonical_ref=record.canonical_ref,
                    version=record.version,
                )
            )
        return tuple(projections)

    def resolve(
        self,
        request: DesktopObjectAffordanceRequest,
        *,
        scope: CapabilityScope,
        actor_id: str,
    ) -> DesktopObjectDefinition:
        definition = self._objects.get(request.object_id)
        if definition is None or not self._visible(
            definition, scope=scope, actor_id=actor_id
        ):
            raise DesktopObjectAffordanceError("not_available")
        if request.expected_version != definition.record.version:
            raise DesktopObjectAffordanceError("stale_version")
        if not self._resolve_capability(definition, request.affordance, scope=scope):
            raise DesktopObjectAffordanceError("not_available")
        return definition

    @staticmethod
    def _visible(
        definition: DesktopObjectDefinition,
        *,
        scope: CapabilityScope,
        actor_id: str,
    ) -> bool:
        if definition.hidden:
            return False
        record = definition.record
        visibility = record.visibility
        if visibility is DesktopObjectVisibility.PRIVATE:
            return scope is CapabilityScope.LOCAL_OWNER and actor_id == record.owner_id
        if visibility is DesktopObjectVisibility.LOCAL_ONLY:
            return scope in {CapabilityScope.LOCAL_OWNER, CapabilityScope.LOCAL_RESTRICTED}
        if visibility is DesktopObjectVisibility.GUEST_VISIBLE:
            return scope in {
                CapabilityScope.LOCAL_OWNER,
                CapabilityScope.LOCAL_RESTRICTED,
                CapabilityScope.REMOTE_GUEST,
            }
        return visibility is DesktopObjectVisibility.PUBLIC

    def _resolve_capability(
        self,
        definition: DesktopObjectDefinition,
        affordance: DesktopObjectAffordance,
        *,
        scope: CapabilityScope,
    ) -> bool:
        advertised = {value.strip().lower() for value in definition.record.affordances}
        if affordance.value not in advertised:
            return False
        registry = CapabilityRegistry()
        for candidate in DesktopObjectAffordance:
            if candidate.value not in advertised:
                continue
            registry.register(
                CapabilityDescriptor(
                    capability_id=self.capability_id(
                        definition.record.object_id, candidate
                    ),
                    category=CapabilityCategory.DESKTOP_OBJECTS,
                    verbs=(SemanticVerb(candidate.value),),
                    description=f"{candidate.value} at {definition.label}",
                    required_scope=CapabilityScope.LOCAL_OWNER,
                )
            )
        capability_id = self.capability_id(definition.record.object_id, affordance)
        active = self._resolver.resolve(
            CapabilityResolutionRequest(
                request_id=f"resolve-{definition.record.object_id}-{affordance.value}",
                actor_id=definition.record.owner_id,
                session_id="desktop-object-affordance",
                scope=scope,
                intent=f"{affordance.value} object {definition.label}",
                desktop_object_refs=(definition.record.object_id,),
                max_capabilities=1,
            ),
            registry,
        )
        return any(
            selected.capability_id == capability_id
            for selected in active.selected_capabilities
        )

    @staticmethod
    def capability_id(object_id: str, affordance: DesktopObjectAffordance) -> str:
        return f"desktop-object:{object_id}:{affordance.value}"

    @staticmethod
    def resource(object_id: str, affordance: DesktopObjectAffordance) -> str:
        return f"desktop.object:{object_id}:{affordance.value}"
