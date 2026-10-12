"""Core's handle on the decision layer: follows Settings, warms the runner, never blocks a reply."""

from __future__ import annotations

from pathlib import Path

from sora.decision.families import allowed_operations
from sora.decision.laya import Decision, LayaDecisionLayer
from sora.decision.settings import DecisionSettings, resolve_paths

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class DecisionGate:
    def __init__(self, project: Path = PROJECT_ROOT, *, enabled: bool = False) -> None:
        self.project = project
        # Off until an owner launch turns it on (Core's --listen-on-start), so tests and other
        # embedded runtimes never start the laya runner.
        self.enabled = enabled
        self.layer: LayaDecisionLayer | None = None
        self._identity: tuple[Path, Path, str] | None = None

    def _layer_for(self, settings: DecisionSettings) -> LayaDecisionLayer:
        runner, model = resolve_paths(settings, self.project)
        identity = (runner, model, settings.device)
        if self.layer is None or identity != self._identity:
            self.layer = LayaDecisionLayer(runner, model, device=settings.device)
            self._identity = identity
        return self.layer

    async def warm(self, settings: DecisionSettings) -> None:
        """Start the runner before the first message so it does not pay the load time."""
        if self.enabled and settings.mode != "off":
            await self._layer_for(settings).start()

    async def decide(
        self, text: str, settings: DecisionSettings, *, agent_names: tuple[str, ...] = (),
    ) -> Decision | None:
        if not self.enabled or settings.mode == "off":
            if self.layer is not None:
                await self.close()
            return None
        layer = self._layer_for(settings)
        return await layer.decide(text, threshold=settings.threshold, agent_names=agent_names)

    @staticmethod
    def allowed(decision: Decision | None, settings: DecisionSettings) -> frozenset[str] | None:
        """Operations to offer the brain, or None for "everything" (off, shadow or no decision)."""
        if settings.mode != "enforce" or decision is None:
            return None
        return allowed_operations(decision.families)

    async def close(self) -> None:
        layer, self.layer, self._identity = self.layer, None, None
        if layer is not None:
            await layer.close()

    def status(self) -> dict[str, str]:
        if self.layer is None:
            return {"state": "stopped", "reason": ""}
        return {"state": self.layer.state, "reason": self.layer.reason}
