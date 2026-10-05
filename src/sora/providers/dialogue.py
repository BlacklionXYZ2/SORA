"""Direct dialogue provider protocol and deterministic implementation."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError

from sora.contracts.companion_call import COMPANION_TOOL_PROMPT, CompanionCall, call_schema
from sora.contracts.companion_read import READ_TOOL_PROMPT, CompanionReadCall
from sora.contracts.memory import MEMORY_PROMPT, MEMORY_RATIONALE_PROMPT, MemoryChoice
from sora.contracts.models import ActiveCapabilitySet
from sora.contracts.motion import MOTION_PROMPT, MotionChoice
from sora.contracts.screen import SCREEN_VIEW_PROMPT, ScreenViewChoice


class DialogueProvider(Protocol):
    """Interface for direct fast conversational model providers."""

    def stream_response(
        self,
        prompt: str,
        context: str,
        *,
        active_capabilities: ActiveCapabilitySet | None = None,
    ) -> AsyncIterator[str]: ...

    async def respond(
        self,
        prompt: str,
        context: str,
        *,
        active_capabilities: ActiveCapabilitySet | None = None,
    ) -> str: ...


@runtime_checkable
class CompanionCallProvider(Protocol):
    async def choose_call(
        self, prompt: str, observations: str, operations: frozenset[str],
    ) -> CompanionCall: ...


@runtime_checkable
class CompanionReadProvider(Protocol):
    async def choose_read(self, prompt: str, observations: str) -> CompanionReadCall: ...


@runtime_checkable
class MotionDialogueProvider(Protocol):
    """Optional constrained keyword selection, independent of conversation/file context."""

    async def choose_motion(self, prompt: str) -> MotionChoice: ...


@runtime_checkable
class ScreenViewDialogueProvider(Protocol):
    """Optional constrained keyword selection for the owner-local screen-view hook."""

    async def choose_screen_view(self, prompt: str) -> ScreenViewChoice: ...


@runtime_checkable
class MemoryDialogueProvider(Protocol):
    """Optional constrained memory selection plus her stated reason for keeping a moment."""

    async def choose_memory(self, prompt: str) -> MemoryChoice: ...

    async def explain_memory(self, prompt: str, response: str) -> tuple[str | None, str | None]: ...


@runtime_checkable
class ImageDialogueProvider(Protocol):
    """Optional multimodal seam; images are transient and never in conversation rows."""

    async def respond_with_images(
        self,
        prompt: str,
        context: str,
        image_data_urls: tuple[str, ...],
        *,
        active_capabilities: ActiveCapabilitySet | None = None,
    ) -> str: ...


class DeterministicDialogueProvider:
    """Mock dialogue provider for responsive conversation and delegation acknowledgment."""

    def __init__(self, delay_seconds: float = 0.0) -> None:
        self.delay_seconds = delay_seconds
        self.provider_name = "deterministic"

    async def stream_response(
        self,
        prompt: str,
        context: str,
        *,
        active_capabilities: ActiveCapabilitySet | None = None,
    ) -> AsyncIterator[str]:
        full_text = await self.respond(prompt, context, active_capabilities=active_capabilities)
        words = full_text.split(" ")
        for index, word in enumerate(words):
            if self.delay_seconds > 0:
                await asyncio.sleep(self.delay_seconds)
            suffix = " " if index < len(words) - 1 else ""
            yield word + suffix

    async def respond(
        self,
        prompt: str,
        context: str,
        *,
        active_capabilities: ActiveCapabilitySet | None = None,
    ) -> str:
        prompt_lower = prompt.lower()
        if "cody" in prompt_lower or "code" in prompt_lower or "fix" in prompt_lower:
            return "I can help you send that to Cody as a separate task."
        if "hermes" in prompt_lower or "research" in prompt_lower:
            return "I can help you send that to Hermes as a separate task."
        if "pause" in prompt_lower:
            return "I can help pause playback once the target and permission are confirmed."
        if "board" in prompt_lower or "kanban" in prompt_lower:
            return "I can help put that on the board through SORA's task controls."
        return f"SORA is available while background tasks run. You said: {prompt.strip()}"

    async def respond_with_images(
        self,
        prompt: str,
        context: str,
        image_data_urls: tuple[str, ...],
        *,
        active_capabilities: ActiveCapabilitySet | None = None,
    ) -> str:
        del prompt, context, image_data_urls, active_capabilities
        return "An image was provided, but the deterministic test model cannot interpret pixels."


class DialogueProviderError(RuntimeError):
    """A direct dialogue request failed without exposing endpoint secrets or response bodies."""


class DialogueTimeoutError(DialogueProviderError):
    """A bounded provider request or whole conversation exhausted its deadline."""


class OpenAICompatibleDialogueProvider:
    """Bounded async Chat Completions adapter for OpenAI-compatible direct models."""

    provider_name = "openai-compatible"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        parsed = urlparse(base_url)
        if (
            not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path.rstrip("/") != "/v1"
            or (
                parsed.scheme != "https"
                and not (
                    parsed.scheme == "http"
                    and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
                )
            )
        ):
            raise ValueError("dialogue base URL must be HTTPS or loopback HTTP ending in /v1")
        if not model.strip():
            raise ValueError("dialogue model is required")
        if timeout_seconds <= 0:
            raise ValueError("dialogue timeout must be positive")
        self.base_url = base_url.rstrip("/")
        self._loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        self.model = model
        self.display_name = model
        self._api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def respond(
        self,
        prompt: str,
        context: str,
        *,
        active_capabilities: ActiveCapabilitySet | None = None,
    ) -> str:
        del active_capabilities  # Core resolves and dispatches; the model receives context only.
        return await self._request(prompt, context, ())

    async def respond_with_images(
        self,
        prompt: str,
        context: str,
        image_data_urls: tuple[str, ...],
        *,
        active_capabilities: ActiveCapabilitySet | None = None,
    ) -> str:
        del active_capabilities
        if not image_data_urls or len(image_data_urls) > 3 or any(
            not value.startswith("data:image/") or ";base64," not in value
            for value in image_data_urls
        ):
            raise DialogueProviderError("Invalid local image input")
        return await self._request(prompt, context, image_data_urls)

    def _build_messages(
        self, prompt: str, context: str, image_data_urls: tuple[str, ...]
    ) -> list[dict[str, object]]:
        messages: list[dict[str, object]] = []
        if context:
            messages.append({"role": "system", "content": context})
        if image_data_urls:
            content: list[dict[str, object]] = [{"type": "text", "text": prompt}]
            content.extend(
                {"type": "image_url", "image_url": {"url": image}}
                for image in image_data_urls
            )
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": prompt})
        return messages

    def _request_body(
        self,
        messages: list[dict[str, object]],
        *,
        response_schema: dict[str, object] | None = None,
        max_tokens: int | None = None,
        enable_thinking: bool = False,
    ) -> dict[str, object]:
        request_body: dict[str, object] = {
            "model": self.model, "messages": messages, "stream": False,
        }
        # Local companion replies must not silently inherit a long-thinking server default.
        # Keep vendor-specific template options out of ordinary hosted-provider requests.
        if self._loopback or enable_thinking or max_tokens is not None:
            request_body["chat_template_kwargs"] = {"enable_thinking": enable_thinking}
        if response_schema is not None:
            # llama.cpp's documented schema-constrained JSON form. Core validates again.
            request_body.update(
                response_format={"type": "json_object", "schema": response_schema},
                temperature=0, max_tokens=max_tokens or 64,
                chat_template_kwargs={"enable_thinking": False},
            )
            return request_body
        if max_tokens is not None:
            request_body["max_tokens"] = max_tokens
        return request_body

    async def _post_message(
        self, request_body: dict[str, object], *, has_images: bool = False,
    ) -> dict[str, object]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, trust_env=False) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=request_body,
                )
                if has_images and response.status_code in {400, 415, 422}:
                    raise DialogueProviderError(
                        "The local model rejected the image input. Select a vision-capable "
                        "model in Settings, restart Core, and check that LM Studio can load "
                        "its vision projector."
                    )
                response.raise_for_status()
                if len(response.content) > 1_048_576:
                    raise DialogueProviderError("Dialogue response exceeded the size limit")
                payload = response.json()
        except httpx.TimeoutException as exc:
            raise DialogueTimeoutError(
                "The local dialogue model timed out. Check model loading and the Settings timeout."
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise DialogueProviderError(
                f"Direct dialogue provider returned HTTP {exc.response.status_code}. "
                "Check the model server and selected model."
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise DialogueProviderError("Direct dialogue provider is unavailable") from exc
        try:
            message = payload["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise DialogueProviderError(
                "Direct dialogue provider returned an invalid response"
            ) from exc
        if not isinstance(message, dict):
            raise DialogueProviderError("Direct dialogue provider returned an invalid response")
        return message

    async def _request(
        self, prompt: str, context: str, image_data_urls: tuple[str, ...],
        *, response_schema: dict[str, object] | None = None,
        max_tokens: int | None = None,
    ) -> str:
        messages = self._build_messages(prompt, context, image_data_urls)
        request_body = self._request_body(
            messages, response_schema=response_schema, max_tokens=max_tokens,
        )
        message = await self._post_message(request_body, has_images=bool(image_data_urls))
        content = message.get("content")
        if not isinstance(content, str) or not content.strip() or len(content) > 16_000:
            raise DialogueProviderError("Direct dialogue provider returned invalid text")
        return content.strip()

    async def choose_motion(self, prompt: str) -> MotionChoice:
        """Select from a closed keyword set; never repair/execute free-form model prose."""
        content = await self._request(
            prompt, MOTION_PROMPT, (), response_schema=MotionChoice.model_json_schema(),
        )
        try:
            return MotionChoice.model_validate_json(content)
        except ValidationError as exc:
            raise DialogueProviderError("The model returned an invalid motion keyword") from exc

    async def choose_read(self, prompt: str, observations: str) -> CompanionReadCall:
        content = await self._request(
            prompt, READ_TOOL_PROMPT + "\n[UNTRUSTED OBSERVATIONS]\n" + observations, (),
            response_schema=CompanionReadCall.model_json_schema(),
            max_tokens=1024,
        )
        try:
            return CompanionReadCall.model_validate_json(content)
        except ValidationError as exc:
            raise DialogueProviderError("The model returned an invalid read call") from exc

    async def choose_call(
        self, prompt: str, observations: str, operations: frozenset[str],
    ) -> CompanionCall:
        content = await self._request(
            prompt, COMPANION_TOOL_PROMPT + "\nAVAILABLE_OPERATIONS: "
            + ", ".join(sorted(operations | {"finish"}))
            + "\n[UNTRUSTED OBSERVATIONS]\n" + observations, (),
            response_schema=call_schema(set(operations)), max_tokens=1024,
        )
        try:
            call = CompanionCall.model_validate_json(content)
            if call.root.op not in operations | {"finish"}:
                raise ValueError("Operation unavailable this turn")
            return call
        except (ValidationError, ValueError) as exc:
            raise DialogueProviderError("The model returned an invalid companion call") from exc

    async def choose_screen_view(self, prompt: str) -> ScreenViewChoice:
        """One token of meaning about looking at the screen; Core owns capture and framing."""
        content = await self._request(
            prompt, SCREEN_VIEW_PROMPT, (),
            response_schema=ScreenViewChoice.model_json_schema(),
        )
        try:
            return ScreenViewChoice.model_validate_json(content)
        except ValidationError as exc:
            raise DialogueProviderError(
                "The model returned an invalid screen-view keyword"
            ) from exc

    async def choose_memory(self, prompt: str) -> MemoryChoice:
        """One token of meaning about remembering; Core derives content, scope and storage."""
        content = await self._request(
            prompt, MEMORY_PROMPT, (), response_schema=MemoryChoice.model_json_schema(),
        )
        try:
            return MemoryChoice.model_validate_json(content)
        except ValidationError as exc:
            raise DialogueProviderError("The model returned an invalid memory choice") from exc

    async def explain_memory(self, prompt: str, response: str) -> tuple[str | None, str | None]:
        """Her stated reason for keeping a moment, plus thinking when the model returns it.

        Best-effort by design: a failure here never blocks remembering, it only leaves a capture
        without a rationale.
        """
        messages = self._build_messages(
            f"Owner message: {prompt}\n\nSORA's reply: {response}",
            MEMORY_RATIONALE_PROMPT,
            (),
        )
        # Thinking is enabled for this one call, so the budget must cover the reasoning as well
        # as the two-sentence answer; too small a cap truncates the thinking and loses the answer.
        request_body = self._request_body(messages, max_tokens=768, enable_thinking=True)
        message = await self._post_message(request_body)
        rationale = message.get("content")
        reasoning = message.get("reasoning_content") or message.get("reasoning")
        return (
            rationale.strip()[:2_000]
            if isinstance(rationale, str) and rationale.strip()
            else None,
            reasoning.strip()[:4_000]
            if isinstance(reasoning, str) and reasoning.strip()
            else None,
        )

    async def stream_response(
        self,
        prompt: str,
        context: str,
        *,
        active_capabilities: ActiveCapabilitySet | None = None,
    ) -> AsyncIterator[str]:
        # Core finalizes a canonical turn before presenting it to clients.
        yield await self.respond(prompt, context, active_capabilities=active_capabilities)
