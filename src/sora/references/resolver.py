"""P10.6 scoped conversational reference memory and deterministic resolution."""

from __future__ import annotations

import re
import uuid
from collections import OrderedDict
from datetime import UTC, datetime, timedelta

from sora.contracts.content import (
    ContentReference,
    ReferenceCandidate,
    ReferenceKind,
    ReferenceResolution,
    ReferenceResolutionStatus,
    ReferenceResolveRequest,
)
from sora.contracts.embodiment import ScreenRect
from sora.contracts.models import AttentionTarget


class ReferenceResolverError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ReferenceResolver:
    """Bounded per-runtime referent memory; candidates never confer action authority."""

    _PRONOUN = re.compile(r"\b(this|that|it|these|those)\b", re.IGNORECASE)
    _KIND_HINTS: dict[ReferenceKind, tuple[str, ...]] = {
        ReferenceKind.UI: ("control", "button", "window", "screen", "selection", "circle"),
        ReferenceKind.PROJECT: ("project", "repository", "repo"),
        ReferenceKind.FILE: ("file", "code", "source"),
        ReferenceKind.TASK: ("task", "job", "run"),
        ReferenceKind.DOCUMENT: ("document", "doc", "report", "image"),
        ReferenceKind.OBJECT: ("object", "board", "card", "widget", "note"),
        ReferenceKind.ARTIFACT: ("artifact", "result", "diff", "patch"),
    }

    def __init__(self, *, max_candidates: int = 256) -> None:
        if max_candidates < 1:
            raise ValueError("max_candidates must be positive")
        self.max_candidates = max_candidates
        self._candidates: OrderedDict[str, ReferenceCandidate] = OrderedDict()
        self._content: dict[str, ContentReference] = {}
        self._current: dict[tuple[str, str, str | None], str] = {}

    @staticmethod
    def _scope(
        owner_id: str, device_id: str, project_id: str | None
    ) -> tuple[str, str, str | None]:
        return owner_id, device_id, project_id

    def clear(self) -> None:
        self._candidates.clear()
        self._content.clear()
        self._current.clear()

    def invalidate_spatial(
        self,
        *,
        owner_id: str,
        device_id: str,
        project_id: str | None,
        now: datetime,
    ) -> int:
        """Expire volatile geometry in one scope without deleting canonical referents."""
        scope = self._scope(owner_id, device_id, project_id)
        invalidated = 0
        for reference_id, candidate in tuple(self._candidates.items()):
            if (candidate.owner_id, candidate.device_id, candidate.project_id) != scope:
                continue
            if candidate.screen_rect is None and candidate.attention_target_id is None:
                continue
            self._candidates[reference_id] = candidate.model_copy(
                update={"spatial_expires_at": now}
            )
            invalidated += 1
        current_id = self._current.get(scope)
        if current_id is not None:
            current = self._candidates.get(current_id)
            if current is not None and current.attention_target_id is not None:
                del self._current[scope]
        return invalidated

    def remember_candidate(self, candidate: ReferenceCandidate, *, current: bool = False) -> None:
        self._candidates[candidate.reference_id] = candidate
        self._candidates.move_to_end(candidate.reference_id)
        if current:
            self._current[
                self._scope(candidate.owner_id, candidate.device_id, candidate.project_id)
            ] = candidate.reference_id
        while len(self._candidates) > self.max_candidates:
            reference_id, removed = self._candidates.popitem(last=False)
            self._content.pop(removed.content_reference_id or "", None)
            for scope, current_id in tuple(self._current.items()):
                if current_id == reference_id:
                    del self._current[scope]

    def remember_attention(self, target: AttentionTarget) -> ReferenceCandidate:
        kind = {
            "task": ReferenceKind.TASK,
            "document": ReferenceKind.DOCUMENT,
            "object": ReferenceKind.OBJECT,
        }.get(target.source, ReferenceKind.UI)
        rect = (
            ScreenRect(
                x=target.screen_rect[0],
                y=target.screen_rect[1],
                width=target.screen_rect[2],
                height=target.screen_rect[3],
            )
            if target.screen_rect is not None
            else None
        )
        label = target.ui_element or target.window_title or f"{target.source} target"
        candidate = ReferenceCandidate(
            reference_id=f"reference:{target.target_id}",
            kind=kind,
            label=label,
            aliases=(target.source,),
            owner_id=target.owner_id,
            device_id=target.device_id,
            project_id=target.project_id,
            created_at=target.created_at,
            expires_at=target.expires_at,
            last_referenced_at=target.created_at,
            confidence=target.confidence,
            pinned=target.pinned,
            attention_target_id=target.target_id,
            desktop_target_id=target.desktop_target_id,
            screen_rect=rect,
            topology_revision=target.topology_revision,
            spatial_expires_at=target.expires_at,
            provenance=target.provenance,
        )
        self.remember_candidate(candidate, current=True)
        return candidate

    def remember_content(
        self,
        reference: ContentReference,
        *,
        confidence: float = 1.0,
        current: bool = False,
        ttl_seconds: float = 86_400,
    ) -> ReferenceCandidate:
        self._content[reference.reference_id] = reference
        kind = {
            "repository": ReferenceKind.PROJECT,
            "file": ReferenceKind.FILE,
            "artifact": ReferenceKind.ARTIFACT,
        }.get(reference.kind, ReferenceKind.DOCUMENT)
        candidate = ReferenceCandidate(
            reference_id=reference.reference_id,
            kind=kind,
            label=reference.label,
            aliases=(reference.path.name,),
            owner_id=reference.owner_id,
            device_id=reference.device_id,
            project_id=reference.project_id,
            created_at=reference.created_at,
            expires_at=reference.created_at + timedelta(seconds=ttl_seconds),
            last_referenced_at=reference.created_at,
            confidence=confidence,
            desktop_target_id=reference.desktop_target_id,
            content_reference_id=reference.reference_id,
            provenance="configured_content",
        )
        self.remember_candidate(candidate, current=current)
        return candidate

    def remember_task(
        self,
        task_id: str,
        *,
        label: str,
        owner_id: str,
        device_id: str,
        project_id: str | None,
        created_at: datetime,
        current: bool = False,
    ) -> ReferenceCandidate:
        candidate = ReferenceCandidate(
            reference_id=f"task:{task_id}",
            kind=ReferenceKind.TASK,
            label=label,
            aliases=(task_id,),
            owner_id=owner_id,
            device_id=device_id,
            project_id=project_id,
            created_at=created_at,
            expires_at=created_at + timedelta(days=1),
            last_referenced_at=created_at,
            task_id=task_id,
            provenance="canonical_task_reference",
        )
        self.remember_candidate(candidate, current=current)
        return candidate

    def remember_object(
        self,
        object_id: str,
        *,
        label: str,
        owner_id: str,
        device_id: str,
        project_id: str | None,
        created_at: datetime | None = None,
    ) -> ReferenceCandidate:
        now = created_at or datetime.now(UTC)
        candidate = ReferenceCandidate(
            reference_id=f"object:{object_id}",
            kind=ReferenceKind.OBJECT,
            label=label,
            aliases=(object_id,),
            owner_id=owner_id,
            device_id=device_id,
            project_id=project_id,
            created_at=now,
            expires_at=now + timedelta(days=1),
            last_referenced_at=now,
            object_id=object_id,
            provenance="desktop_object_projection",
        )
        self.remember_candidate(candidate)
        return candidate

    def content(self, reference_id: str) -> ContentReference | None:
        return self._content.get(reference_id)

    def list_content(
        self, *, owner_id: str, device_id: str, project_id: str | None,
        now: datetime | None = None,
    ) -> tuple[ContentReference, ...]:
        """Return only live content in an exact conversational scope."""
        checked_at = now or datetime.now(UTC)
        return tuple(
            content
            for reference_id, content in self._content.items()
            if (candidate := self._candidates.get(reference_id)) is not None
            and candidate.expires_at > checked_at
            and content.owner_id == owner_id
            and content.device_id == device_id
            and content.project_id == project_id
        )

    def get(
        self,
        reference_id: str,
        *,
        owner_id: str,
        device_id: str,
        project_id: str | None,
    ) -> ReferenceCandidate:
        candidate = self._candidates.get(reference_id)
        if candidate is None or (
            candidate.owner_id != owner_id
            or candidate.device_id != device_id
            or candidate.project_id != project_id
        ):
            raise ReferenceResolverError("not_found", "reference was not found in this scope")
        return candidate

    def pin(
        self,
        reference_id: str,
        *,
        owner_id: str,
        device_id: str,
        project_id: str | None,
        ttl_seconds: float,
        now: datetime | None = None,
    ) -> ReferenceCandidate:
        pinned_at = now or datetime.now(UTC)
        candidate = self.get(
            reference_id,
            owner_id=owner_id,
            device_id=device_id,
            project_id=project_id,
        )
        if pinned_at >= candidate.expires_at and not candidate.pinned:
            raise ReferenceResolverError("expired", "reference expired before it could be pinned")
        updated = candidate.model_copy(
            update={
                "pinned": True,
                "expires_at": max(candidate.expires_at, pinned_at + timedelta(seconds=ttl_seconds)),
                "last_referenced_at": pinned_at,
            }
        )
        self.remember_candidate(updated, current=True)
        return updated

    def update_spatial(
        self,
        reference_id: str,
        *,
        rect: ScreenRect,
        topology_revision: int,
        now: datetime,
    ) -> ReferenceCandidate:
        candidate = self._candidates[reference_id]
        updated = candidate.model_copy(
            update={
                "screen_rect": rect,
                "topology_revision": topology_revision,
                "spatial_expires_at": now + timedelta(seconds=60),
                "last_referenced_at": now,
            }
        )
        self.remember_candidate(updated, current=True)
        return updated

    def resolve(
        self,
        request: ReferenceResolveRequest,
        *,
        owner_id: str,
        device_id: str,
        project_id: str | None,
        now: datetime | None = None,
    ) -> ReferenceResolution:
        resolved_at = now or datetime.now(UTC)
        scope = self._scope(owner_id, device_id, project_id)
        candidates = tuple(
            candidate
            for candidate in self._candidates.values()
            if (candidate.owner_id, candidate.device_id, candidate.project_id) == scope
        )
        resolution_id = f"reference-resolution-{uuid.uuid4()}"

        if request.explicit_reference_id is not None:
            explicit = next(
                (
                    candidate
                    for candidate in candidates
                    if candidate.reference_id == request.explicit_reference_id
                ),
                None,
            )
            if explicit is None:
                return ReferenceResolution(
                    resolution_id=resolution_id,
                    status=ReferenceResolutionStatus.NOT_FOUND,
                    reason="explicit_reference_not_found",
                )
            return self._finish(explicit, request, resolved_at, resolution_id, scope)

        lowered = request.utterance.casefold()
        label_matches = tuple(
            candidate
            for candidate in candidates
            if any(
                value.casefold() in lowered
                for value in (candidate.label, *candidate.aliases)
                if len(value.strip()) >= 3
            )
        )
        if len(label_matches) == 1:
            return self._finish(label_matches[0], request, resolved_at, resolution_id, scope)
        if len(label_matches) > 1:
            return self._ambiguous(label_matches, resolution_id, "multiple_labels_match")

        hinted_kinds = {
            kind
            for kind, hints in self._KIND_HINTS.items()
            if any(re.search(rf"\b{re.escape(hint)}\b", lowered) for hint in hints)
        }
        hinted = tuple(candidate for candidate in candidates if candidate.kind in hinted_kinds)
        has_pronoun = self._PRONOUN.search(lowered) is not None

        current_id = self._current.get(scope)
        current = next(
            (candidate for candidate in candidates if candidate.reference_id == current_id),
            None,
        )
        if (
            has_pronoun
            and current is not None
            and (not hinted_kinds or current.kind in hinted_kinds)
        ):
            return self._finish(current, request, resolved_at, resolution_id, scope)

        pool = hinted if hinted_kinds else candidates if has_pronoun else ()
        if len(pool) == 1:
            return self._finish(pool[0], request, resolved_at, resolution_id, scope)
        if len(pool) > 1:
            return self._ambiguous(pool, resolution_id, "multiple_references_match")
        return ReferenceResolution(
            resolution_id=resolution_id,
            status=ReferenceResolutionStatus.NOT_FOUND,
            reason="no_reference_match",
        )

    def _finish(
        self,
        candidate: ReferenceCandidate,
        request: ReferenceResolveRequest,
        now: datetime,
        resolution_id: str,
        scope: tuple[str, str, str | None],
    ) -> ReferenceResolution:
        if now >= candidate.expires_at:
            return ReferenceResolution(
                resolution_id=resolution_id,
                status=ReferenceResolutionStatus.EXPIRED,
                reason="reference_expired",
                alternatives=(candidate,),
            )
        if (
            candidate.spatial_expires_at is not None
            and now >= candidate.spatial_expires_at
            and candidate.desktop_target_id is None
        ):
            return ReferenceResolution(
                resolution_id=resolution_id,
                status=ReferenceResolutionStatus.STALE,
                reason="spatial_reference_requires_reacquisition",
                alternatives=(candidate,),
            )
        if candidate.confidence < request.minimum_confidence:
            return ReferenceResolution(
                resolution_id=resolution_id,
                status=ReferenceResolutionStatus.CLARIFICATION_REQUIRED,
                reason="reference_confidence_below_threshold",
                alternatives=(candidate,),
            )
        touched = candidate.model_copy(update={"last_referenced_at": now})
        self.remember_candidate(touched)
        self._current[scope] = touched.reference_id
        return ReferenceResolution(
            resolution_id=resolution_id,
            status=ReferenceResolutionStatus.RESOLVED,
            reason="reference_resolved",
            candidate=touched,
        )

    @staticmethod
    def _ambiguous(
        candidates: tuple[ReferenceCandidate, ...],
        resolution_id: str,
        reason: str,
    ) -> ReferenceResolution:
        ordered = tuple(
            sorted(
                candidates,
                key=lambda candidate: (candidate.last_referenced_at, candidate.reference_id),
                reverse=True,
            )[:8]
        )
        return ReferenceResolution(
            resolution_id=resolution_id,
            status=ReferenceResolutionStatus.CLARIFICATION_REQUIRED,
            reason=reason,
            alternatives=ordered,
        )
