"""Whole sentences from a reply that is still streaming, so speech can start early."""

from __future__ import annotations

import re
from typing import Protocol

# A sentence ends at . ! ? or an ellipsis, optionally followed by closing quotes or brackets,
# then whitespace. A line break also ends one (lists and short lines).
_BOUNDARY = re.compile(r"[.!?…]+[\"')\]”’]*\s+|\n+")
_HAS_WORD = re.compile(r"[^\W\d_]", re.UNICODE)


class SentenceStream:
    """Feed text deltas; get back each sentence once it is complete."""

    def __init__(self) -> None:
        self._buffer = ""
        self._carry = ""

    def feed(self, delta: str) -> list[str]:
        self._buffer += delta
        sentences: list[str] = []
        while match := _BOUNDARY.search(self._buffer):
            piece = self._buffer[: match.end()]
            self._buffer = self._buffer[match.end() :]
            sentences.extend(self._emit(piece))
        return sentences

    def flush(self) -> list[str]:
        rest, self._buffer = self._buffer, ""
        sentences = self._emit(rest)
        if self._carry.strip():
            sentences.append(self._carry.strip())
        self._carry = ""
        return sentences

    def _emit(self, piece: str) -> list[str]:
        text = (self._carry + piece).strip()
        if not text:
            return []
        if not _HAS_WORD.search(text):
            # A list number such as "1." or a lone symbol joins the next sentence.
            self._carry = text + " "
            return []
        self._carry = ""
        return [text]


class SpeechSink(Protocol):
    def speech_sentence(self, session_id: str, generation_id: str, sentence: str) -> None: ...

    def finish_speech(self, session_id: str, generation_id: str) -> None: ...


# Context for voice turns. Her reply is spoken, so markdown and long essays only slow her down.
VOICE_REPLY_NOTE = (
    "[CORE VOICE] The owner spoke this turn and your reply will be read aloud. Answer the way "
    "a person talks: usually one to three short sentences, plain words, no markdown, lists, "
    "headings, links or emoji. Say more only when the owner asks for detail."
)


class SpokenReply:
    """Passes each finished sentence of a voice reply to the session as the model writes it."""

    def __init__(self, sink: SpeechSink, session_id: str, generation_id: str) -> None:
        self._sink = sink
        self._session_id = session_id
        self._generation_id = generation_id
        self._sentences = SentenceStream()

    def __call__(self, delta: str) -> None:
        for sentence in self._sentences.feed(delta):
            self._sink.speech_sentence(self._session_id, self._generation_id, sentence)

    def close(self, *, completed: bool) -> None:
        """Speak the unfinished tail only if the reply completed, then end the preview."""
        if completed:
            for sentence in self._sentences.flush():
                self._sink.speech_sentence(self._session_id, self._generation_id, sentence)
        self._sink.finish_speech(self._session_id, self._generation_id)
