"""Private worker-derived presentation, with no speech or model authority in the wire data."""

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from sora.contracts.voice import VoiceEmotion
from sora.voice.presentation import VoicePresentationFrame, VoicePresentationResetReason
from sora.voice.relay import LocalPresentationRelay
from sora.voice.windows_audio import SoundDevicePlayback
from sora.voice.windows_worker import PipeLipSyncSink


@pytest.mark.asyncio
async def test_actual_pipe_sink_emits_ordered_metadata_and_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relay = LocalPresentationRelay()
    queue = relay.register()
    monkeypatch.setattr(
        "sora.voice.windows_worker.emit", lambda **data: relay.publish(data["presentation"])
    )
    sink = PipeLipSyncSink()
    await sink.begin("playback-one", 4, "warm")
    await sink.present(VoicePresentationFrame("playback-one", 4, 0, 0, 100, 0.3, VoiceEmotion.WARM))
    await sink.reset("playback-one", 4, VoicePresentationResetReason.INTERRUPTED)
    samples = [queue.get_nowait() for _ in range(3)]
    assert [sample["op"] for sample in samples] == ["begin", "frame", "reset"]
    assert [sample["serial"] for sample in samples] == [1, 2, 3]
    assert samples[1]["mouth_open"] == 0.3 and samples[2]["reason"] == "interrupted"
    assert not any("pcm" in key or "text" in key for sample in samples for key in sample)
    assert relay.register().empty()  # Reconnection cannot replay active speech.


def test_invalid_amplitude_and_audio_bytes_cannot_enter_relay() -> None:
    relay = LocalPresentationRelay()
    for bad in [float("nan"), float("inf"), -1, 2]:
        with pytest.raises(ValidationError):
            relay.publish({"op": "frame", "playback_id": "p", "output_epoch": 0, "mouth_open": bad})
    with pytest.raises(ValidationError):
        relay.publish({"op": "reset", "pcm": b"private"})
    assert relay.serial == 0


def test_overflow_discards_old_samples_and_resets_instead_of_false_continuity() -> None:
    relay = LocalPresentationRelay()
    queue = relay.register()
    for _ in range(33):
        relay.publish({"op": "begin", "playback_id": "p", "output_epoch": 0})
    assert queue.qsize() == 1
    sample = queue.get_nowait()
    assert sample["op"] == "reset" and sample["reason"] == "failed"
    old_stream = relay.stream_id
    relay.reset()
    assert queue.get_nowait()["op"] == "reset"
    assert relay.stream_id != old_stream and relay.serial == 0
    relay.unregister(queue)
    assert relay.listeners == []


@pytest.mark.asyncio
async def test_cancelled_native_write_is_not_closed_until_the_thread_releases_it() -> None:
    entered, release = threading.Event(), threading.Event()
    calls: list[str] = []

    def write(data: bytes) -> None:
        calls.append("write")
        entered.set()
        assert release.wait(3)
        calls.append("write-returned")

    sink = SoundDevicePlayback(None, 0)
    sink.stream = SimpleNamespace(
        write=write, abort=lambda: calls.append("abort"), close=lambda: calls.append("close")
    )
    writing = asyncio.create_task(sink.write(b"\0" * 4800))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        writing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await writing
        stopping = asyncio.create_task(sink.abort())
        await asyncio.sleep(0.05)
        assert calls == ["write"]
        release.set()
        await stopping
        assert calls == ["write", "write-returned", "abort", "close"]
    finally:
        release.set()
        await sink.abort()
