"""Adaptive refresh has one transient slot, change detection and foreground priority."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from sora.contracts.desktop import DesktopObservation, DesktopObservationRequest
from sora.desktop.bridge import WindowsObservationBridge
from sora.desktop.capture import WindowsCaptureBridge
from sora.desktop.foreground import ForegroundIdentity
from sora.providers.llama_server import LlamaServerConfig
from sora.providers.mock import DeterministicProvider
from sora.runtime.app_settings import AppSettings, AppSettingsController, SettingsEdit
from sora.runtime.perception import (
    AdaptivePerception,
    PerceptionBusyError,
    PerceptionSample,
    PromptImage,
)
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.security.local_policy import owner_local_scope
from tests.desktop.test_foreground import FakeForegroundSource, identity
from tests.runtime.test_companion_reads import window
from tests.runtime.test_perception import PerceptionDialogue, reply

ROOT = Path(__file__).resolve().parents[2]


def sample(digest: str = "a", *, pid: int = 12) -> PerceptionSample:
    return PerceptionSample(
        identity(pid=pid),
        PromptImage("fixture", datetime.now(UTC), "data:image/png;base64,fixture", digest),
    )


def scheduler(samples: AsyncMock, interpretations: AsyncMock) -> AdaptivePerception:
    return AdaptivePerception(
        enabled=lambda: True, interval=lambda: 0.02,
        sample=samples, interpret=interpretations,
    )


def test_v4_migration_retains_complete_original(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    old = AppSettings(revision=3).model_dump(mode="json")
    old["version"] = 4
    old["perception"].pop("interval_seconds")
    old["perception"].pop("context_max_age_seconds")
    old["perception"].update(mode="image-on-prompt", paused=True)
    path.write_text(json.dumps(old))
    settings = AppSettingsController(tmp_path, AppSettings(), path=path)
    assert settings.saved.version == 10 and settings.saved.revision == 3
    assert settings.active.perception.paused
    assert settings.active.perception.mode == "image-on-prompt"
    assert settings.active.perception.interval_seconds == 30
    assert json.loads(next(tmp_path.glob("settings.v4-*.json")).read_text()) == old


@pytest.mark.asyncio
async def test_same_pixels_skip_model_but_reverify_identity_and_time() -> None:
    samples = AsyncMock(side_effect=[sample(), sample(), sample("b"), sample("b", pid=99)])
    interpret = AsyncMock(return_value="visible synthetic content")
    service = scheduler(samples, interpret)
    assert await service.refresh_once()
    first = service.context
    assert first is not None
    assert await service.refresh_once()
    second = service.context
    assert second is not None and second.captured_at == first.captured_at
    assert second.verified_at >= first.verified_at and interpret.await_count == 1
    assert service.unchanged == 1
    assert await service.refresh_once()
    assert await service.refresh_once()
    assert service.interpretations == 3
    assert service.recent(identity(), 90) is None  # Different current process.
    assert service.recent(identity(pid=99), 90) is not None
    assert service.recent(identity(pid=99), 90, now=datetime.now(UTC) + timedelta(weeks=1)) is None
    await service.stop()
    assert service.context is None


@pytest.mark.asyncio
async def test_conversation_preempts_inference_and_drops_late_reply() -> None:
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def interpret(_: PromptImage) -> str:
        started.set()
        try:
            await asyncio.Event().wait()
            return "unexpected unblocked result"
        except asyncio.CancelledError:
            cancelled.set()
            return "late background result"  # Simulate a backend acknowledging too late.

    samples = AsyncMock(return_value=sample())
    service = scheduler(samples, AsyncMock(side_effect=interpret))
    refresh = asyncio.create_task(service.refresh_once())
    await asyncio.wait_for(started.wait(), 1)
    async with service.foreground():
        assert cancelled.is_set() and service.context is None
        assert not await service.refresh_once()
        assert samples.await_count == 1
    assert refresh.cancelled()
    assert service.interpretations == 0
    service.interpret = AsyncMock(return_value="fresh")
    assert await service.refresh_once()
    assert service.context is not None and service.context.summary == "fresh"
    await service.stop()


@pytest.mark.asyncio
async def test_invalidation_and_failure_discard_private_context() -> None:
    started = asyncio.Event()

    async def capture() -> PerceptionSample:
        started.set()
        await asyncio.Event().wait()
        return sample()

    service = scheduler(AsyncMock(side_effect=capture), AsyncMock())
    refresh = asyncio.create_task(service.refresh_once())
    await asyncio.wait_for(started.wait(), 1)
    service.invalidate()
    with pytest.raises(asyncio.CancelledError):
        await refresh
    assert service.context is None
    service.sample = AsyncMock(return_value=sample())
    service.interpret = AsyncMock(side_effect=RuntimeError("private details must not appear"))
    assert not await service.refresh_once()
    assert service.state == "unavailable" and service.context is None
    await service.stop()


@pytest.mark.asyncio
async def test_unresponsive_cancellation_does_not_admit_or_publish_late() -> None:
    started, release = asyncio.Event(), asyncio.Event()

    async def resistant(_: PromptImage) -> str:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await release.wait()
        return "late private result"

    service = scheduler(AsyncMock(return_value=sample()), AsyncMock(side_effect=resistant))
    refresh = asyncio.create_task(service.refresh_once())
    await asyncio.wait_for(started.wait(), 1)
    try:
        with pytest.raises(PerceptionBusyError):
            async with service.foreground():
                pytest.fail("Foreground must not overlap an unreleased background transport")
    finally:
        release.set()
        await asyncio.gather(refresh, return_exceptions=True)
        await service.stop()
    assert refresh.cancelled() and service.context is None and service.interpretations == 0


@pytest.mark.asyncio
async def test_timer_does_not_accumulate_work_during_conversation() -> None:
    samples = AsyncMock(return_value=sample())
    interpret = AsyncMock(return_value="hello")
    service = scheduler(samples, interpret)
    service.start()
    try:
        async with service.foreground():
            await asyncio.sleep(0.09)
            assert samples.await_count == interpret.await_count == 0
        async with asyncio.timeout(1):
            while interpret.await_count == 0:
                await asyncio.sleep(0.005)
        async with asyncio.timeout(1):
            while samples.await_count < 2:
                await asyncio.sleep(0.005)
        assert interpret.await_count == 1 and samples.await_count >= 2
    finally:
        await service.stop()
    count = samples.await_count
    await asyncio.sleep(0.03)
    assert samples.await_count == count and service.context is None


@pytest.mark.asyncio
async def test_live_interval_increase_and_decrease_reschedule_without_old_ticks() -> None:
    period = 0.02
    samples = AsyncMock(return_value=sample())
    service = scheduler(samples, AsyncMock(return_value="hello"))
    service.interval = lambda: period
    service.start()
    try:
        await asyncio.sleep(0.005)
        period = 0.15
        service.invalidate()
        await asyncio.sleep(0.055)
        assert samples.await_count == 0
        async with asyncio.timeout(1):
            while samples.await_count == 0:
                await asyncio.sleep(0.005)
        period = 0.01
        service.invalidate()
        count = samples.await_count
        async with asyncio.timeout(0.1):
            while samples.await_count == count:
                await asyncio.sleep(0.002)
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_runtime_ambient_context_is_local_transient_and_revocable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sora.runtime.read_turn.desktop_directories", lambda: [])
    settings = AppSettingsController(
        tmp_path, AppSettings.model_validate({"perception": {"mode": "adaptive"}}),
    )
    source = FakeForegroundSource()
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=ROOT / "identity"),
        provider=DeterministicProvider(), app_settings=settings, foreground_source=source,
    )
    runtime.windows_bridge = AsyncMock()
    runtime.windows_bridge.observe.return_value = DesktopObservation(status="ok", nodes=(window(),))
    runtime.windows_capture_bridge = AsyncMock(spec=WindowsCaptureBridge)
    runtime.windows_capture_bridge.capture.side_effect = reply
    await runtime.start()
    provider = PerceptionDialogue()
    settings.provider = provider
    runtime.dialogue_provider = provider
    try:
        source.callbacks[-1](identity())
        await asyncio.sleep(0)
        assert await runtime.adaptive_perception.refresh_once()
        assert len(provider.images) == 1 and runtime.desktop_captures.count == 0
        assert not await runtime.repository.list_messages(runtime.config.conversation_id)
        with owner_local_scope():
            answer = await runtime.dialogue("Hello")
        assert len(provider.images) == 1  # Uses summary, not another image request.
        assert "Background window context:" in answer
        assert "interval context, not a fresh targeted read" in provider.contexts[-1]
        await runtime.dialogue("Hello", allow_desktop_view=False, allow_local_files=False)
        assert "CORE BACKGROUND CONTEXT" not in provider.contexts[-1]
        # Lock/Desktop invalidation clears both cache and in-flight background context.
        source.callbacks[-1](None)
        await asyncio.sleep(0)
        assert runtime.adaptive_perception.context is None
        source.callbacks[-1](identity())
        await asyncio.sleep(0)
        assert await runtime.adaptive_perception.refresh_once()
        settings.save(SettingsEdit(
            version=5, expected_revision=settings.saved.revision,
            changes={"perception.paused": True},
        ))
        assert runtime.adaptive_perception.context is None
        assert not await runtime.adaptive_perception.refresh_once()
        await asyncio.gather(*tuple(runtime._policy_tasks))
        assert not source.running
    finally:
        await runtime.close()


def test_context_process_start_time_reuse_is_rejected() -> None:
    service = scheduler(AsyncMock(), AsyncMock())
    from sora.runtime.perception import AmbientContext

    original = identity()
    service.context = AmbientContext(original, datetime.now(UTC), datetime.now(UTC), "old", "x")
    reused = replace(original, process_started_at=datetime.now(UTC))
    assert service.recent(reused, 90) is None


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("SORA_TEST_PERCEPTION_MODEL_CONFIG"),
    reason="opt-in native/local-model adaptive context",
)
async def test_native_adaptive_context_with_local_model(tmp_path: Path) -> None:
    """Actual capture/model/runtime seam; seeded fixture identity, not GUI handoff evidence."""
    config = LlamaServerConfig.load(Path(os.environ["SORA_TEST_PERCEPTION_MODEL_CONFIG"]))
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    settings = AppSettingsController(tmp_path, AppSettings.model_validate({
        "dialogue": {"backend": "managed-llama"},
        "llama": {**config.model_dump(), "port": port},
        "perception": {
            "mode": "adaptive", "desktop_context": False, "interval_seconds": 5,
        },
        "local_companion": {"file_read": False},
    }))
    source = FakeForegroundSource()
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=ROOT / "identity"),
        provider=DeterministicProvider(), app_settings=settings, foreground_source=source,
    )
    native = WindowsObservationBridge(
        ROOT / "clients/windows_bridge/bin/Debug/net10.0-windows/windows_bridge.exe"
    )
    runtime.windows_capture_bridge = WindowsCaptureBridge(
        ROOT / "clients/windows_capture/bin/Debug/net10.0-windows/windows_capture.exe"
    )
    evidence = tmp_path / "fixture.json"
    fixture = await asyncio.create_subprocess_exec(
        str(ROOT / "clients/uia_fixture/bin/Debug/net10.0-windows/uia_fixture.exe"),
        str(evidence), "--read-selection",
    )
    try:
        async with asyncio.timeout(10):
            while not evidence.exists():
                await asyncio.sleep(0.05)
        before = json.loads(evidence.read_text())

        async def observe(request: DesktopObservationRequest) -> DesktopObservation:
            result = await native.observe(request)
            if request.operation == "inventory":
                return result.model_copy(update={
                    "nodes": tuple(n for n in result.nodes if n.window_handle == before["hwnd"]),
                })
            assert request.process_id == fixture.pid
            return result

        runtime.windows_bridge = AsyncMock(spec=WindowsObservationBridge)
        runtime.windows_bridge.observe.side_effect = observe
        node = (await observe(DesktopObservationRequest(operation="inventory"))).nodes[0]
        assert node.process_started_at is not None
        await settings.start()
        assert settings.model_state == "ready"
        await runtime.start()
        target = ForegroundIdentity(
            fixture.pid, before["hwnd"], node.process_started_at,
            "uia_fixture.exe", datetime.now(UTC),
        )
        source.callbacks[-1](target)
        await asyncio.sleep(0)
        started = time.monotonic()
        async with asyncio.timeout(20):
            while runtime.adaptive_perception.context is None:
                await asyncio.sleep(0.02)
        cached = runtime.adaptive_perception.context
        assert cached is not None
        print(
            f"Adaptive timer context after {time.monotonic() - started:.2f}s "
            f"(refresh {runtime.adaptive_perception.last_duration_seconds}s): {cached.summary}"
        )
        assert "before" in cached.summary.casefold()
        assert not await runtime.repository.list_messages(runtime.config.conversation_id)
        async with asyncio.timeout(10):
            while runtime.adaptive_perception.unchanged == 0:
                await asyncio.sleep(0.02)
        assert runtime.adaptive_perception.interpretations == 1
        assert runtime.adaptive_perception.unchanged == 1
        with owner_local_scope():
            answer = await runtime.dialogue(
                "What word is visible in the editable text field of the application "
                "I was using? Answer with the word only."
            )
        print(f"Adaptive foreground answer: {answer}")
        assert "Background window context:" in answer
        assert "before" in answer.casefold()
        assert runtime.desktop_captures.count == 0
        # Exercise cancellation against the actual HTTP/model transport, not just a mock.
        runtime.adaptive_perception.invalidate()
        background = asyncio.create_task(runtime.adaptive_perception.refresh_once())
        async with asyncio.timeout(5):
            while runtime.adaptive_perception.state != "interpreting":
                await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)
        started = time.monotonic()
        with owner_local_scope():
            foreground = await runtime.dialogue(
                "What word is visible in the editable text field of the application "
                "I was using? Answer with the word only."
            )
        print(f"Preempting foreground {time.monotonic() - started:.2f}s: {foreground}")
        assert background.cancelled()
        assert "before" in foreground.casefold()
        assert runtime.adaptive_perception.interpretations == 1
        after = json.loads(evidence.read_text())
        assert after["press_count"] == after["text_change_count"] == 0
    finally:
        await runtime.close()
        if fixture.returncode is None:
            fixture.kill()
        await fixture.wait()
