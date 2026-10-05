"""Volatile P14.2 voice-session coordination around canonical dialogue turns."""

from __future__ import annotations

import re
import uuid
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher

from sora.contracts.voice import (
    VoiceConversationAction,
    VoiceDeviceEvent,
    VoiceDeviceKind,
    VoiceDeviceState,
    VoiceInterruptionDisposition,
    VoiceInterruptionKind,
    VoiceInterruptionRequest,
    VoiceInterruptionResult,
    VoicePlaybackCommand,
    VoicePlaybackEvent,
    VoicePlaybackState,
    VoiceReferenceResolution,
    VoiceSessionSnapshot,
    VoiceSessionStartRequest,
    VoiceSessionStatus,
    VoiceTranscriptDisposition,
    VoiceTranscriptEvent,
    VoiceTranscriptKind,
    VoiceTurnResult,
)
from sora.persistence.records import VoiceTurnReceipt
from sora.security.local_policy import LocalPolicyContext
from sora.security.local_policy import OperationContext as OperationAuthorization


@dataclass(frozen=True, slots=True)
class VoiceFinalization:
    receipt: VoiceTurnReceipt
    control: VoiceConversationAction | None = None
    reference: VoiceReferenceResolution | None = None


FinalizeVoiceTurn = Callable[[VoiceTranscriptEvent, str, str, str], Awaitable[VoiceFinalization]]


class VoiceGenerationCancelled(RuntimeError):
    """The active direct-dialogue generation was cooperatively interrupted."""


@dataclass(slots=True)
class _VoiceSession:
    request: VoiceSessionStartRequest
    device_id: str
    authorization: OperationAuthorization
    input_available: bool = True
    output_available: bool = True
    input_generation: int = 1
    output_generation: int = 1
    partial_utterance_id: str | None = None
    partial_text: str | None = None
    finalized_utterances: int = 0
    active_playback: VoicePlaybackCommand | None = None
    playback_state: VoicePlaybackState | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    closed: bool = False
    transcript_events: OrderedDict[str, VoiceTranscriptEvent] = field(default_factory=OrderedDict)
    transcript_results: OrderedDict[str, VoiceTurnResult] = field(default_factory=OrderedDict)
    device_events: OrderedDict[str, VoiceDeviceEvent] = field(default_factory=OrderedDict)
    playback_events: OrderedDict[str, VoicePlaybackEvent] = field(default_factory=OrderedDict)
    utterance_sequences: dict[str, int] = field(default_factory=dict)
    finalized_ids: OrderedDict[str, None] = field(default_factory=OrderedDict)
    playback_sequence: int = -1
    output_epoch: int = 0
    active_generation_id: str | None = None
    generation_cancel_requested: bool = False
    output_suppressed: bool = False
    interruption_events: OrderedDict[str, VoiceInterruptionRequest] = field(
        default_factory=OrderedDict
    )
    interruption_results: OrderedDict[str, VoiceInterruptionResult] = field(
        default_factory=OrderedDict
    )


class VoiceSessionCoordinator:
    """Bounded in-memory session state; only finalized dialogue turns reach SQLite."""

    def __init__(self, *, capacity: int = 8, event_capacity: int = 512) -> None:
        if not 1 <= capacity <= 64:
            raise ValueError("voice session capacity must be between 1 and 64")
        if not 32 <= event_capacity <= 4096:
            raise ValueError("voice event capacity must be between 32 and 4096")
        self.capacity = capacity
        self.event_capacity = event_capacity
        self._sessions: OrderedDict[str, _VoiceSession] = OrderedDict()

    @staticmethod
    def resource(request: VoiceSessionStartRequest) -> str:
        return (
            f"voice.session:{request.session_id}:"
            f"input:{request.input_device_id}:output:{request.output_device_id}"
        )

    def activity(self) -> str | None:
        """A shared presentation status without exposing transcripts or device identities."""
        active = [session for session in self._sessions.values() if not session.closed]
        if any(session.playback_state is VoicePlaybackState.STARTED for session in active):
            return "talking"
        if any(session.active_generation_id is not None or
               session.playback_state is VoicePlaybackState.QUEUED for session in active):
            return "thinking"
        return None

    def open(
        self,
        request: VoiceSessionStartRequest,
        *,
        device_id: str,
        authorization: OperationAuthorization,
        now: datetime | None = None,
    ) -> VoiceSessionSnapshot:
        evaluated_at = now or datetime.now(UTC)
        if request.started_at > evaluated_at + timedelta(seconds=30):
            raise ValueError("voice session start is in the future")
        if request.started_at < evaluated_at - timedelta(minutes=5):
            raise ValueError("voice session start is stale")
        existing = self._sessions.get(request.session_id)
        if existing is not None:
            if (
                existing.request != request
                or existing.device_id != device_id
                or self._authority_key(existing.authorization) != self._authority_key(authorization)
            ):
                raise ValueError("voice session ID was reused with different input")
            existing.authorization = authorization
            self._sessions.move_to_end(request.session_id)
            return self._snapshot(existing)
        if len(self._sessions) >= self.capacity:
            raise RuntimeError("voice session capacity reached")
        session = _VoiceSession(
            request=request,
            device_id=device_id,
            authorization=authorization,
            updated_at=evaluated_at,
        )
        self._sessions[request.session_id] = session
        return self._snapshot(session)

    def authorization(self, session_id: str, device_id: str) -> OperationAuthorization:
        session = self._session(session_id, device_id)
        return session.authorization

    async def transcript(
        self,
        event: VoiceTranscriptEvent,
        *,
        device_id: str,
        finalize: FinalizeVoiceTurn,
        now: datetime | None = None,
    ) -> VoiceTurnResult:
        session = self._session(event.session_id, device_id)
        evaluated_at = now or datetime.now(UTC)
        replay = session.transcript_events.get(event.event_id)
        if replay is not None:
            if replay != event:
                raise ValueError("voice transcript event ID was reused with different input")
            return self._replay_result(session, event.event_id)
        self._validate_event_time(event.captured_at, session, evaluated_at)
        if not session.input_available:
            raise RuntimeError("voice input device is unavailable")
        if event.device_generation != session.input_generation:
            raise ValueError("voice transcript used a stale input-device generation")
        prior_sequence = session.utterance_sequences.get(event.utterance_id, -1)
        if event.sequence <= prior_sequence:
            raise ValueError("voice transcript sequence did not advance")
        if event.utterance_id in session.finalized_ids:
            # A different event ID can be a delivery retry after reconnect. Repository idempotency
            # decides whether it is the same final text or conflicting reuse.
            if event.kind is not VoiceTranscriptKind.FINAL:
                raise ValueError("finalized voice utterance cannot accept more partial text")
        if (
            session.partial_utterance_id is not None
            and session.partial_utterance_id != event.utterance_id
        ):
            raise ValueError("voice session already has another partial utterance")

        session.utterance_sequences[event.utterance_id] = event.sequence
        self._remember(session.transcript_events, event.event_id, event)
        session.updated_at = evaluated_at
        if event.kind is VoiceTranscriptKind.PARTIAL:
            session.partial_utterance_id = event.utterance_id
            session.partial_text = event.text
            result = VoiceTurnResult(
                disposition=VoiceTranscriptDisposition.PARTIAL_ACCEPTED,
                session=self._snapshot(session),
            )
            self._remember(session.transcript_results, event.event_id, result)
            return result

        session.partial_utterance_id = None
        session.partial_text = None
        if self._looks_like_echo(session, event.text):
            self._remember(session.finalized_ids, event.utterance_id, None)
            result = VoiceTurnResult(
                disposition=VoiceTranscriptDisposition.SUPPRESSED_ECHO,
                session=self._snapshot(session),
            )
            self._remember(session.transcript_results, event.event_id, result)
            return result

        generation_id = f"voice-generation-{uuid.uuid4()}"
        generation_epoch = session.output_epoch
        session.active_generation_id = generation_id
        session.generation_cancel_requested = False
        session.output_suppressed = False
        try:
            finalization = await finalize(
                event, device_id, generation_id, session.request.session_id
            )
        except VoiceGenerationCancelled:
            session.active_generation_id = None
            session.generation_cancel_requested = False
            session.output_suppressed = False
            session.updated_at = datetime.now(UTC)
            self._remember(session.finalized_ids, event.utterance_id, None)
            result = VoiceTurnResult(
                disposition=VoiceTranscriptDisposition.INTERRUPTED,
                session=self._snapshot(session),
            )
            self._remember(session.transcript_results, event.event_id, result)
            return result
        except BaseException:
            session.active_generation_id = None
            session.generation_cancel_requested = False
            session.output_suppressed = False
            session.transcript_events.pop(event.event_id, None)
            if prior_sequence < 0:
                session.utterance_sequences.pop(event.utterance_id, None)
            else:
                session.utterance_sequences[event.utterance_id] = prior_sequence
            session.updated_at = datetime.now(UTC)
            raise
        receipt = finalization.receipt
        self._remember(session.finalized_ids, event.utterance_id, None)
        if receipt.created:
            session.finalized_utterances += 1
        playback = None
        if (
            receipt.created
            and session.output_available
            and not session.output_suppressed
            and session.output_epoch == generation_epoch
        ):
            playback_created_at = datetime.now(UTC)
            playback = VoicePlaybackCommand(
                playback_id=f"playback-{uuid.uuid4()}",
                session_id=session.request.session_id,
                utterance_id=event.utterance_id,
                output_device_id=session.request.output_device_id,
                device_generation=session.output_generation,
                output_epoch=session.output_epoch,
                voice_id=session.request.voice_id,
                text=receipt.assistant_message.content,
                created_at=playback_created_at,
                expires_at=playback_created_at + timedelta(seconds=30),
            )
            session.active_playback = playback
            session.playback_state = VoicePlaybackState.QUEUED
            session.playback_sequence = -1
        session.active_generation_id = None
        session.generation_cancel_requested = False
        session.output_suppressed = False
        result = VoiceTurnResult(
            disposition=(
                VoiceTranscriptDisposition.FINALIZED
                if receipt.created
                else VoiceTranscriptDisposition.DUPLICATE
            ),
            session=self._snapshot(session),
            user_message_id=receipt.user_message.message_id,
            assistant_message_id=receipt.assistant_message.message_id,
            assistant_text=receipt.assistant_message.content,
            playback=playback,
            control=finalization.control,
            reference=finalization.reference,
        )
        self._remember(session.transcript_results, event.event_id, result)
        return result

    def interrupt(
        self,
        request: VoiceInterruptionRequest,
        *,
        device_id: str,
        now: datetime | None = None,
    ) -> VoiceInterruptionResult:
        """Stop output and, only for explicit modes, request generation cancellation."""

        session = self._session(request.session_id, device_id)
        evaluated_at = now or datetime.now(UTC)
        replay = session.interruption_events.get(request.event_id)
        if replay is not None:
            if replay != request:
                raise ValueError("voice interruption event ID was reused with different input")
            prior = session.interruption_results.get(request.event_id)
            if prior is None:
                raise ValueError("voice interruption replay result was evicted")
            return prior.model_copy(
                update={
                    "disposition": VoiceInterruptionDisposition.DUPLICATE,
                    "session": self._snapshot(session),
                }
            )
        self._validate_event_time(request.occurred_at, session, evaluated_at)

        generation_id = session.active_generation_id
        playback_id = (
            session.active_playback.playback_id if session.active_playback is not None else None
        )
        has_response = generation_id is not None or playback_id is not None
        cancel_generation = request.kind in {
            VoiceInterruptionKind.BARGE_IN,
            VoiceInterruptionKind.CANCEL_RESPONSE,
        }
        if has_response:
            session.output_epoch += 1
            session.active_playback = None
            session.playback_state = None
            session.playback_sequence = -1
            if generation_id is not None:
                session.output_suppressed = True
                session.generation_cancel_requested = cancel_generation
            session.updated_at = evaluated_at

        result = VoiceInterruptionResult(
            disposition=(
                VoiceInterruptionDisposition.APPLIED
                if has_response
                else VoiceInterruptionDisposition.NO_ACTIVE_RESPONSE
            ),
            kind=request.kind,
            session=self._snapshot(session),
            generation_id=generation_id,
            generation_cancel_requested=cancel_generation and generation_id is not None,
            playback_id=playback_id,
            output_stopped=has_response,
        )
        self._remember(session.interruption_events, request.event_id, request)
        self._remember(session.interruption_results, request.event_id, result)
        return result

    def device(
        self,
        event: VoiceDeviceEvent,
        *,
        device_id: str,
        now: datetime | None = None,
    ) -> VoiceSessionSnapshot:
        session = self._session(event.session_id, device_id)
        evaluated_at = now or datetime.now(UTC)
        replay = session.device_events.get(event.event_id)
        if replay is not None:
            if replay != event:
                raise ValueError("voice device event ID was reused with different input")
            return self._snapshot(session)
        self._validate_event_time(event.occurred_at, session, evaluated_at)
        expected_device = (
            session.request.input_device_id
            if event.kind is VoiceDeviceKind.INPUT
            else session.request.output_device_id
        )
        if event.device_id != expected_device:
            raise ValueError("voice device event targets another device")
        current_generation = (
            session.input_generation
            if event.kind is VoiceDeviceKind.INPUT
            else session.output_generation
        )
        available = (
            session.input_available
            if event.kind is VoiceDeviceKind.INPUT
            else session.output_available
        )
        if event.state is VoiceDeviceState.LOST:
            if not available or event.generation != current_generation:
                raise ValueError("voice device-loss event has stale generation or state")
            if event.kind is VoiceDeviceKind.INPUT:
                session.input_available = False
                session.partial_utterance_id = None
                session.partial_text = None
            else:
                session.output_available = False
                # Reconnection must not resurrect an answer generated across device loss.
                session.output_epoch += 1
                session.active_playback = None
                session.playback_state = None
                session.playback_sequence = -1
        else:
            if available or event.generation != current_generation + 1:
                raise ValueError("voice device recovery must advance generation exactly once")
            if event.kind is VoiceDeviceKind.INPUT:
                session.input_available = True
                session.input_generation = event.generation
            else:
                session.output_available = True
                session.output_generation = event.generation
                # Stale audio is deliberately not recreated after output recovery.
        session.updated_at = evaluated_at
        self._remember(session.device_events, event.event_id, event)
        return self._snapshot(session)

    def playback(
        self,
        event: VoicePlaybackEvent,
        *,
        device_id: str,
        now: datetime | None = None,
    ) -> VoiceSessionSnapshot:
        session = self._session(event.session_id, device_id)
        evaluated_at = now or datetime.now(UTC)
        replay = session.playback_events.get(event.event_id)
        if replay is not None:
            if replay != event:
                raise ValueError("voice playback event ID was reused with different input")
            return self._snapshot(session)
        self._validate_event_time(event.occurred_at, session, evaluated_at)
        command = session.active_playback
        if command is None or command.playback_id != event.playback_id:
            raise ValueError("voice playback event does not match active audio")
        if event.output_device_id != session.request.output_device_id:
            raise ValueError("voice playback event targets another output device")
        if event.device_generation != session.output_generation:
            raise ValueError("voice playback event used a stale output-device generation")
        if not session.output_available:
            raise RuntimeError("voice output device is unavailable")
        if (evaluated_at >= command.expires_at
                and session.playback_state is not VoicePlaybackState.STARTED):
            session.active_playback = None
            session.playback_state = None
            raise ValueError("voice playback command expired")
        if event.sequence <= session.playback_sequence:
            raise ValueError("voice playback sequence did not advance")
        if event.state is VoicePlaybackState.STARTED:
            if session.playback_state is not VoicePlaybackState.QUEUED:
                raise ValueError("voice playback can start only from queued state")
            session.playback_state = VoicePlaybackState.STARTED
        elif event.state in {VoicePlaybackState.COMPLETED, VoicePlaybackState.FAILED}:
            allowed_prior = (
                {VoicePlaybackState.STARTED}
                if event.state is VoicePlaybackState.COMPLETED
                else {VoicePlaybackState.QUEUED, VoicePlaybackState.STARTED}
            )
            if session.playback_state not in allowed_prior:
                raise ValueError("voice playback terminal state has an invalid predecessor")
            session.playback_state = event.state
        session.playback_sequence = event.sequence
        session.updated_at = evaluated_at
        self._remember(session.playback_events, event.event_id, event)
        if event.state in {VoicePlaybackState.COMPLETED, VoicePlaybackState.FAILED}:
            session.active_playback = None
            session.playback_state = None
            session.playback_sequence = -1
        return self._snapshot(session)

    def snapshot(self, session_id: str, *, device_id: str) -> VoiceSessionSnapshot:
        return self._snapshot(self._session(session_id, device_id))

    def close(self, session_id: str, *, device_id: str) -> VoiceSessionSnapshot:
        session = self._session(session_id, device_id)
        if session.active_generation_id is not None or session.active_playback is not None:
            session.output_epoch += 1
        session.generation_cancel_requested = session.active_generation_id is not None
        session.output_suppressed = session.active_generation_id is not None
        session.closed = True
        session.partial_utterance_id = None
        session.partial_text = None
        session.active_playback = None
        session.playback_state = None
        session.updated_at = datetime.now(UTC)
        return self._snapshot(session)

    def clear(self) -> None:
        for session in self._sessions.values():
            session.generation_cancel_requested = True
            session.output_suppressed = True
            session.closed = True
            session.active_playback = None
        self._sessions.clear()

    @staticmethod
    def _authority_key(authorization: OperationAuthorization) -> tuple[object, ...]:
        if isinstance(authorization, LocalPolicyContext):
            return ("local", authorization.request.owner_id, authorization.request.resource,
                    authorization.policy_epoch)
        return ("grant", authorization.grant.grant_id)

    def _session(self, session_id: str, device_id: str) -> _VoiceSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise LookupError("voice session was not found")
        if session.device_id != device_id:
            raise PermissionError("voice session belongs to another device")
        if session.closed:
            raise RuntimeError("voice session is closed")
        self._sessions.move_to_end(session_id)
        return session

    def _snapshot(self, session: _VoiceSession) -> VoiceSessionSnapshot:
        if session.closed:
            status = VoiceSessionStatus.CLOSED
        elif not session.input_available and not session.output_available:
            status = VoiceSessionStatus.DEVICES_UNAVAILABLE
        elif not session.input_available:
            status = VoiceSessionStatus.INPUT_UNAVAILABLE
        elif not session.output_available:
            status = VoiceSessionStatus.OUTPUT_UNAVAILABLE
        else:
            status = VoiceSessionStatus.ACTIVE
        return VoiceSessionSnapshot(
            session_id=session.request.session_id,
            status=status,
            input_device_id=session.request.input_device_id,
            output_device_id=session.request.output_device_id,
            input_generation=session.input_generation,
            output_generation=session.output_generation,
            language=session.request.language,
            voice_id=session.request.voice_id,
            partial_utterance_id=session.partial_utterance_id,
            partial_text=session.partial_text,
            finalized_utterances=session.finalized_utterances,
            active_playback_id=(
                session.active_playback.playback_id if session.active_playback is not None else None
            ),
            playback_state=session.playback_state,
            output_epoch=session.output_epoch,
            active_generation_id=session.active_generation_id,
            generation_cancel_requested=session.generation_cancel_requested,
            output_suppressed=session.output_suppressed,
            opened_at=session.request.started_at,
            updated_at=session.updated_at,
        )

    def _replay_result(self, session: _VoiceSession, event_id: str) -> VoiceTurnResult:
        result = session.transcript_results.get(event_id)
        if result is None:
            raise ValueError("voice transcript replay result was evicted")
        if result.disposition is VoiceTranscriptDisposition.FINALIZED:
            return result.model_copy(
                update={
                    "disposition": VoiceTranscriptDisposition.DUPLICATE,
                    "session": self._snapshot(session),
                    "playback": None,
                }
            )
        return result.model_copy(update={"session": self._snapshot(session)})

    def _looks_like_echo(self, session: _VoiceSession, transcript: str) -> bool:
        command = session.active_playback
        if not session.request.echo_reference_enabled or command is None:
            return False
        if session.playback_state is not VoicePlaybackState.STARTED:
            return False
        expected = _normalized_words(command.text)
        observed = _normalized_words(transcript)
        if len(expected) < 3 or len(observed) < 3:
            return False
        return SequenceMatcher(a=expected, b=observed, autojunk=False).ratio() >= 0.85

    def _remember[EventT](self, events: OrderedDict[str, EventT], key: str, value: EventT) -> None:
        events[key] = value
        events.move_to_end(key)
        while len(events) > self.event_capacity:
            events.popitem(last=False)

    @staticmethod
    def _validate_event_time(
        occurred_at: datetime, session: _VoiceSession, evaluated_at: datetime
    ) -> None:
        if occurred_at < session.request.started_at:
            raise ValueError("voice event predates its session")
        if occurred_at > evaluated_at + timedelta(seconds=30):
            raise ValueError("voice event is in the future")
        if occurred_at < evaluated_at - timedelta(minutes=5):
            raise ValueError("voice event is stale")


def _normalized_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", text.lower())
