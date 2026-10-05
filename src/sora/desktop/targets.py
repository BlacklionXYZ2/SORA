"""Volatile desktop target lifecycle and deterministic UIA revalidation."""

from __future__ import annotations

import uuid
from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sora.contracts.desktop import (
    DesktopNode,
    DesktopObservation,
    DesktopTarget,
    DesktopTargetRequest,
)


class DesktopTargetError(RuntimeError):
    """A target cannot be acquired or safely reused."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class DesktopTargetRegistry:
    """Bounded in-memory targets; UI identities never become durable authority."""

    def __init__(
        self,
        *,
        max_targets: int = 256,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if max_targets < 1:
            raise ValueError("max_targets must be positive")
        self.max_targets = max_targets
        self._clock = clock or (lambda: datetime.now(UTC))
        self._targets: OrderedDict[str, DesktopTarget] = OrderedDict()

    @staticmethod
    def _select(request: DesktopTargetRequest, observation: DesktopObservation) -> DesktopNode:
        if observation.status != "ok":
            raise DesktopTargetError(observation.status, "desktop observation did not succeed")
        candidates = [
            node
            for node in observation.nodes
            if (not request.runtime_id or node.runtime_id == request.runtime_id)
            and (not request.automation_id or node.automation_id == request.automation_id)
            and (not request.name or node.name == request.name)
            and (not request.control_type or node.control_type == request.control_type)
        ]
        if not candidates:
            code = "incomplete_observation" if observation.truncated else "unavailable"
            raise DesktopTargetError(code, "target selector did not resolve")
        if len(candidates) != 1:
            raise DesktopTargetError("ambiguous", "target selector resolved multiple elements")
        node = candidates[0]
        rect = node.rect
        if rect is None:
            raise DesktopTargetError("unavailable", "target has no usable screen rectangle")
        if node.offscreen:
            raise DesktopTargetError("unavailable", "target is currently offscreen")
        if node.password:
            raise DesktopTargetError("unavailable", "password controls cannot become targets")
        if not node.runtime_id and node.window_handle == 0 and not node.automation_id:
            raise DesktopTargetError("identity_unavailable", "target has no reusable UIA identity")
        return node

    def issue(
        self,
        request: DesktopTargetRequest,
        observation: DesktopObservation,
        *,
        owner_id: str,
        device_id: str,
        project_id: str | None,
    ) -> DesktopTarget:
        if observation.process_started_at is None:
            raise DesktopTargetError(
                "identity_unavailable", "observation did not include process identity"
            )
        if observation.topology_revision < 1:
            raise DesktopTargetError("stale_layout", "observation has no current topology revision")
        node = self._select(request, observation)
        if node.rect is None:  # Narrowed defensively after _select's validation.
            raise DesktopTargetError("unavailable", "target has no usable screen rectangle")
        now = self._clock()
        target = DesktopTarget(
            target_id=f"desktop-target-{uuid.uuid4()}",
            owner_id=owner_id,
            device_id=device_id,
            project_id=project_id,
            process_id=request.process_id,
            process_started_at=observation.process_started_at,
            root_window_handle=request.window_handle,
            native_window_handle=node.window_handle,
            runtime_id=node.runtime_id,
            automation_id=node.automation_id,
            name=node.name,
            control_type=node.control_type,
            rect=node.rect,
            enabled=node.enabled,
            topology_revision=observation.topology_revision,
            created_at=now,
            expires_at=now + timedelta(seconds=request.ttl_seconds),
            last_validated_at=now,
        )
        self._targets[target.target_id] = target
        self._targets.move_to_end(target.target_id)
        while len(self._targets) > self.max_targets:
            self._targets.popitem(last=False)
        return target

    def get(
        self,
        target_id: str,
        *,
        owner_id: str,
        device_id: str,
        project_id: str | None,
    ) -> DesktopTarget:
        target = self._targets.get(target_id)
        if target is None or (
            target.owner_id != owner_id
            or target.device_id != device_id
            or target.project_id != project_id
        ):
            raise DesktopTargetError("not_found", "desktop target was not found")
        now = self._clock()
        if now >= target.expires_at:
            target = target.model_copy(update={"status": "expired"})
            self._targets[target_id] = target
            raise DesktopTargetError("expired", "desktop target has expired")
        if target.status != "active":
            raise DesktopTargetError(target.status, f"desktop target is {target.status}")
        self._targets.move_to_end(target_id)
        return target

    def mark(self, target_id: str, status: str) -> None:
        target = self._targets.get(target_id)
        if target is not None:
            self._targets[target_id] = target.model_copy(update={"status": status})

    def mark_window(self, window_handle: int, status: str) -> int:
        """Invalidate active targets belonging to one changed native window."""
        changed = 0
        for target_id, target in tuple(self._targets.items()):
            if target.status != "active":
                continue
            if window_handle not in {target.root_window_handle, target.native_window_handle}:
                continue
            self._targets[target_id] = target.model_copy(update={"status": status})
            changed += 1
        return changed

    def revalidate(
        self,
        target: DesktopTarget,
        observation: DesktopObservation,
    ) -> DesktopTarget:
        if observation.status != "ok":
            status = "stale_layout" if observation.status == "stale_layout" else "unavailable"
            self.mark(target.target_id, status)
            raise DesktopTargetError(status, "target revalidation observation failed")
        if observation.process_started_at != target.process_started_at:
            self.mark(target.target_id, "unavailable")
            raise DesktopTargetError("unavailable", "target process identity changed")
        if observation.topology_revision != target.topology_revision:
            self.mark(target.target_id, "stale_layout")
            raise DesktopTargetError("stale_layout", "target topology revision changed")

        matches = [node for node in observation.nodes if self._same_identity(target, node)]
        if not matches:
            status = "ambiguous" if observation.truncated else "unavailable"
            self.mark(target.target_id, status)
            raise DesktopTargetError(status, "target identity no longer resolves")
        if len(matches) != 1:
            self.mark(target.target_id, "ambiguous")
            raise DesktopTargetError("ambiguous", "target identity is no longer unique")
        node = matches[0]
        if node.rect is None or node.offscreen or not node.enabled or node.password:
            self.mark(target.target_id, "unavailable")
            raise DesktopTargetError("unavailable", "target is not currently presentable")
        updated = target.model_copy(
            update={
                "native_window_handle": node.window_handle,
                "name": node.name,
                "rect": node.rect,
                "enabled": node.enabled,
                "last_validated_at": self._clock(),
            }
        )
        self._targets[target.target_id] = updated
        self._targets.move_to_end(target.target_id)
        return updated

    @staticmethod
    def _same_identity(target: DesktopTarget, node: DesktopNode) -> bool:
        if target.runtime_id and node.runtime_id != target.runtime_id:
            return False
        if target.native_window_handle and node.window_handle != target.native_window_handle:
            return False
        if target.automation_id and node.automation_id != target.automation_id:
            return False
        if node.control_type != target.control_type:
            return False
        if not target.runtime_id and not target.native_window_handle and node.name != target.name:
            return False
        return True
