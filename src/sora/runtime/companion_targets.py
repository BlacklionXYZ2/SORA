"""Turn-local presentation locators backed by the existing native target registry."""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Callable

from sora.contracts.desktop import DesktopNode, DesktopObservation, DesktopTarget
from sora.desktop.targets import DesktopTargetError

IssueTarget = Callable[[DesktopNode, DesktopNode, DesktopObservation], DesktopTarget]


def presentation_requested(prompt: str, operation: str) -> bool:
    """A native observation cannot invent an owner request for an avatar gesture."""
    # Keep quoted labels as data: the request verb must be outside quotes/code.
    owner = re.sub(
        r"```[\s\S]*?```|\"[^\"]*\"|(?<!\w)'[^'\n]*'(?!\w)|“[^”]*”|‘[^’]*’",
        " ", prompt,
    )
    if re.search(
        r"\b(?:do not|don't|never|stop|without)\b[^.!?;]{0,80}"
        r"\b(?:look|point|gesture|show|turn|face|indicate)\b", owner, re.IGNORECASE,
    ):
        return False
    if re.search(
        r"\b(?:hypothetically|suppose|imagine|what if|what would|how (?:would|do|can))\b|"
        r"\b(?:explain|describe|discuss)\b[^.!?;]{0,80}\b(?:look|point|gesture)\b|"
        r"\b(?:are you|can you)\s+(?:able|capable)\b", owner, re.IGNORECASE,
    ):
        return False
    pattern = (
        r"\b(?:point|gesture|indicate)\b|\bshow\s+(?:me\s+)?(?:where|which)\b"
        if operation == "point" else
        r"\b(?:look|gaze|face)\s+(?:at|toward|towards)\b|"
        r"\bturn\s+(?:your\s+)?(?:head|gaze)\b"
    )
    return re.search(pattern, owner, re.IGNORECASE) is not None


class ControlReferences:
    """A locator is not permission; Core revalidates its identity before dispatch."""

    def __init__(self, issue: IssueTarget | None = None) -> None:
        self.issue = issue
        self._nonce = uuid.uuid4().hex[:8]
        self._targets: dict[str, tuple[str, float]] = {}
        self._exposed: set[str] = set()

    def describe(
        self, node: DesktopNode, window: DesktopNode, observation: DesktopObservation,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "name": node.name, "type": node.control_type, "focused": node.focused,
            "enabled": node.enabled, "offscreen": node.offscreen,
        }
        if (self.issue is None or node.password or node.offscreen or not node.enabled
                or node.rect is None or len(self._targets) >= 256):
            return data
        try:
            target = self.issue(node, window, observation)
        except (DesktopTargetError, ValueError):
            # Inspection is still useful when geometry/identity cannot be acted on.
            return data
        ref = f"t{self._nonce}-c{len(self._targets) + 1}"
        self._targets[ref] = (target.target_id, time.monotonic())
        return {**data, "target": ref, "available_operations": ["look", "point"]}

    def resolve(self, reference: str) -> str:
        saved = self._targets.get(reference)
        if saved is None or reference not in self._exposed:
            raise DesktopTargetError(
                "not_found", "No issued presentation target matches that reference",
            )
        if time.monotonic() - saved[1] >= 60:
            raise DesktopTargetError("expired", "Presentation reference expired; inspect again")
        return saved[0]

    def expose(self, records: list[dict[str, object]]) -> None:
        """Only locators surviving the actual model-context bound become selectable."""
        for record in records:
            data = record.get("data")
            if not isinstance(data, dict) or not isinstance(data.get("nodes"), list):
                continue
            for node in data["nodes"]:
                if isinstance(node, dict) and node.get("target") in self._targets:
                    self._exposed.add(node["target"])

    def clear(self) -> None:
        self._targets.clear()
        self._exposed.clear()
