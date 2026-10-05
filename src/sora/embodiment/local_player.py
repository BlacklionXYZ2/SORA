"""Owner-started Unity companion with session-scoped credentials and lifetime."""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from sora.contracts.embodiment import (
    EmbodimentCommand,
    EmbodimentFeedbackKind,
    EmbodimentPresentationState,
    EmbodimentVerb,
    VirtualDesktopPoint,
)
from sora.contracts.models import (
    ApprovalRequest,
    ApprovalStatus,
    CapabilityGrant,
    CapabilityOperation,
    CapabilityRequest,
    GrantStatus,
)
from sora.security.local_policy import owner_local_scope

if TYPE_CHECKING:
    from sora.runtime.service import SoraRuntime


WALK_SPEED_PX_PER_SEC = 800.0
WALK_ARRIVAL_RADIUS_PX = 60
WALK_TIMEOUT_SECONDS = 20.0


class LocalAvatarSession:
    """Only the explicitly launched local player receives renderer grants."""

    STATES = frozenset({"idle", "waving", "sitting", "leaning", "climbing"})

    def __init__(self, runtime: SoraRuntime, player: Path, avatar: Path | None = None):
        self.runtime = runtime
        self.player = player.resolve(strict=True)
        self.avatar = avatar.resolve(strict=True) if avatar else None
        self.process: asyncio.subprocess.Process | None = None
        self._monitor: asyncio.Task[None] | None = None
        self._grants: dict[str, CapabilityGrant] = {}
        self._approvals: dict[str, ApprovalRequest] = {}
        self._last_activity = "idle"
        self._resting_state = "idle"
        self._walk_target: VirtualDesktopPoint | None = None
        self._walk_deadline: datetime | None = None
        self._presentation_correlation: str | None = None
        self._presentation_deadline: datetime | None = None
        self.error = ""

    async def start(self, *, token: str, port: int) -> None:
        now = datetime.now(UTC)
        if self.runtime.app_settings is not None and not (
            self.runtime.app_settings.active.local_companion.avatar_control
        ):
            self.error = "3D companion control is disabled in Settings."
            return
        try:
            # Legacy embedded runtimes retain their explicit grants. The normal settings-backed
            # companion authenticates its transport but never creates approval/grant records.
            operations = () if self.runtime.app_settings else ("connect", "topology", "command")
            for operation in operations:
                key = uuid.uuid4().hex
                capability = CapabilityRequest(
                    request_id=f"local-avatar-{key}", owner_id=self.runtime.config.owner_id,
                    device_id="device-local", project_id=self.runtime.config.project_id,
                    operation=CapabilityOperation.TOOL_INVOKE,
                    resource=f"embodiment.{operation}",
                )
                approval = ApprovalRequest(
                    approval_id=f"approval-avatar-{key}", capability=capability,
                    status=ApprovalStatus.APPROVED, created_at=now,
                    expires_at=now + timedelta(minutes=5), decided_at=now,
                    decided_by="owner-local",
                )
                grant = CapabilityGrant(
                    grant_id=f"grant-avatar-{key}", owner_id=capability.owner_id,
                    device_id=capability.device_id, project_id=capability.project_id,
                    operation=capability.operation, resource=capability.resource,
                    issued_at=now, not_before=now, expires_at=approval.expires_at,
                    approval_id=approval.approval_id,
                )
                self._approvals[operation] = approval
                self._grants[operation] = grant
                await self.runtime.repository.save_approval(approval)
                await self.runtime.repository.save_grant(grant)
            env = dict(os.environ)
            # Never inherit fixture instrumentation into the everyday companion.
            for name in tuple(env):
                if name.startswith("SORA_") and (
                    "EVIDENCE" in name or name == "SORA_DEBUG_OVERLAY"
                ):
                    env.pop(name)
            env.update(
                SORA_API_TOKEN=token, SORA_CORE_PORT=str(port),
                SORA_CORE_PARENT_PID=str(os.getpid()),
                SORA_EMBODIMENT_DEVICE_ID="device-local",
                SORA_EMBODIMENT_CONNECT_GRANT=self._grant_id("connect"),
                SORA_EMBODIMENT_TOPOLOGY_GRANT=self._grant_id("topology"),
            )
            if self.avatar:
                env["SORA_VRM_PATH"] = str(self.avatar)
            log = self.runtime.config.root / "logs" / "avatar-player.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            self.process = await asyncio.create_subprocess_exec(
                str(self.player), "-logFile", str(log), env=env, cwd=self.player.parent,
            )
            self._monitor = asyncio.create_task(self._watch(), name="local-avatar")
        except BaseException:
            await self.close()
            raise

    async def _watch(self) -> None:
        renewal_at = datetime.now(UTC) + timedelta(minutes=1)
        try:
            while self.process is not None and self.process.returncode is None:
                if self.runtime.app_settings is not None:
                    self.runtime.app_settings.active.local_companion.require(("avatar_control",))
                now = datetime.now(UTC)
                if now >= renewal_at:
                    for grant in self._grants.values():
                        current = await self.runtime.repository.get_grant(grant.grant_id)
                        approval = await self.runtime.repository.get_approval(grant.approval_id)
                        if (current is None or current.status is not GrantStatus.ACTIVE or
                                current.expires_at <= now or approval is None or
                                approval.status is not ApprovalStatus.APPROVED or
                                approval.expires_at <= now):
                            raise PermissionError("Companion permission expired or was revoked.")
                        approval = approval.model_copy(
                            update={"expires_at": now + timedelta(minutes=5)}
                        )
                        current = current.model_copy(update={"expires_at": approval.expires_at})
                        await self.runtime.repository.save_approval(approval)
                        await self.runtime.repository.save_grant(current)
                    renewal_at = now + timedelta(minutes=1)
                if self._presentation_in_progress():
                    # Thinking -> idle must not overwrite an accepted gaze/arm lifecycle.
                    pass
                elif self._walk_in_progress():
                    # Derived travel state: set_state("moving") is rejected by contract, and a
                    # pose restore here would re-anchor and cancel the walk in flight.
                    self._last_activity = "moving"
                else:
                    activity = "thinking" if self.runtime.dialogue_in_progress else (
                        "waiting_for_agent" if await self.runtime.active_specialists()
                        else self._resting_state
                    )
                    if (activity != self._last_activity
                            and self.runtime.embodiment_state is not None):
                        try:
                            await self._present(activity)
                            self._last_activity = activity
                        except (ValueError, PermissionError):
                            pass  # Reconnection/topology changes are retried on the next tick.
                await asyncio.sleep(0.5)
            self.error = "The 3D companion closed. Restart SORA to open it again."
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.error = str(exc)
        finally:
            await self._stop_player()
            await self._revoke()

    async def present(self, state: str) -> None:
        if state not in self.STATES:
            raise ValueError("Unknown companion pose.")
        await self._present(state)
        self._presentation_deadline = None
        # Keep an explicit pose across the automatic thinking -> resting transition.
        # Without this, chat-triggered poses are immediately overwritten by idle.
        self._resting_state = state
        self._last_activity = state

    async def walk_to(self, x: int, y: int) -> None:
        """Dispatch one authorized MOVE_TO toward a pointer location; this is not a pose."""
        if self.process is None or self.process.returncode is not None:
            raise ValueError("The 3D companion is not running.")
        if not self.runtime.topology_manager.is_point_on_display(x, y):
            raise ValueError("Walk target is outside active displays.")
        await self._dispatch(
            EmbodimentCommand(
                command_id=f"local-walk-{uuid.uuid4().hex}",
                verb=EmbodimentVerb.MOVE_TO,
                target_point=VirtualDesktopPoint(x=x, y=y),
                speed_px_per_sec=WALK_SPEED_PX_PER_SEC,
                topology_revision=self.runtime.topology_manager.revision,
                created_at=datetime.now(UTC),
            ),
        )
        self._walk_target = VirtualDesktopPoint(x=x, y=y)
        self._presentation_deadline = None
        self._walk_deadline = datetime.now(UTC) + timedelta(seconds=WALK_TIMEOUT_SECONDS)
        self._last_activity = "moving"

    def hold_presentation(self, command: EmbodimentCommand) -> None:
        """Keep ambient pose sync out of a native gesture; feedback is renderer evidence only."""
        self._walk_target = None
        self._presentation_correlation = command.semantic_action_id
        self._presentation_deadline = datetime.now(UTC) + timedelta(
            seconds=25 if command.semantic_action_id else 5,
        )
        self._last_activity = "native-presentation"

    def _presentation_in_progress(self) -> bool:
        if self._presentation_deadline is None:
            return False
        terminal = any(
            event.correlation_id == self._presentation_correlation
            and event.kind in {EmbodimentFeedbackKind.COMPLETED, EmbodimentFeedbackKind.FAILED}
            for event in self.runtime.embodiment_feedback
        ) if self._presentation_correlation else False
        if (terminal or datetime.now(UTC) >= self._presentation_deadline
                or not self.runtime._embodiment_command_listeners):
            self._presentation_deadline = None
            return False
        return True

    def _walk_in_progress(self) -> bool:
        """Travel ends on arrival (reported position) or timeout, whichever comes first."""
        if self._walk_target is None or self._walk_deadline is None:
            return False
        if datetime.now(UTC) >= self._walk_deadline:
            self._walk_target = None
            return False
        state = self.runtime.embodiment_state
        if state is not None:
            dx = state.current_position.x - self._walk_target.x
            dy = state.current_position.y - self._walk_target.y
            if dx * dx + dy * dy <= WALK_ARRIVAL_RADIUS_PX * WALK_ARRIVAL_RADIUS_PX:
                self._walk_target = None
                return False
        return True

    async def _present(self, state: str) -> None:
        if self.process is None or self.process.returncode is not None:
            raise ValueError("The 3D companion is not running.")
        await self._dispatch(
            EmbodimentCommand(
                command_id=f"local-pose-{uuid.uuid4().hex}",
                verb=EmbodimentVerb.SET_STATE, state=EmbodimentPresentationState(state),
                topology_revision=self.runtime.topology_manager.revision,
                created_at=datetime.now(UTC),
            ),
        )

    def _grant_id(self, operation: str) -> str:
        grant = self._grants.get(operation)
        return grant.grant_id if grant else ""

    async def _dispatch(self, command: EmbodimentCommand) -> None:
        if self.runtime.app_settings is not None:
            with owner_local_scope():
                await self.runtime.dispatch_embodiment_command(command, device_id="device-local")
        else:
            await self.runtime.dispatch_embodiment_command(
                command, grant_id=self._grant_id("command"), device_id="device-local"
            )

    async def _stop_player(self) -> None:
        if self.process is not None and self.process.returncode is None:
            try:
                self.process.terminate()
            except ProcessLookupError:
                return
            await self.process.wait()

    async def _revoke(self) -> None:
        for grant in self._grants.values():
            current = await self.runtime.repository.get_grant(grant.grant_id)
            if current is not None and current.status is GrantStatus.ACTIVE:
                await self.runtime.repository.save_grant(
                    current.model_copy(update={"status": GrantStatus.REVOKED})
                )

    async def close(self) -> None:
        self._presentation_deadline = None
        if self._monitor is not None:
            self._monitor.cancel()
            await asyncio.gather(self._monitor, return_exceptions=True)
            self._monitor = None
        await self._stop_player()
        await self._revoke()
