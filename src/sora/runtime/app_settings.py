"""Unified owner settings, explicit effect tiers, and recoverable model reloads."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal, get_args

from pydantic import Field, model_validator

from sora.contracts.base import StrictModel
from sora.decision.settings import DecisionSettings
from sora.embodiment.avatar_settings import CREDIT, AvatarSettings
from sora.memory.settings import MemoryManagerSettings
from sora.providers.dialogue import (
    DeterministicDialogueProvider,
    DialogueProvider,
    DialogueProviderError,
    OpenAICompatibleDialogueProvider,
)
from sora.providers.llama_server import (
    LlamaOptions,
    LlamaServerConfig,
    ManagedLlamaServer,
    llama_arguments,
    public_llama_arguments,
)
from sora.providers.turn_audio import projector_modalities
from sora.providers.vision_detail import expand_choice
from sora.runtime.agent_preferences import AgentPreference, AgentPreferences, CustomEndpoint
from sora.runtime.perception import PerceptionSettings
from sora.runtime.project_paths import project_directory
from sora.security.local_policy import LocalCompanionPolicy
from sora.voice.settings import LISTENING_FIELDS, VoiceSettings


class DialogueSettings(StrictModel):
    backend: Literal["managed-llama", "openai-compatible", "deterministic"] = "deterministic"
    timeout_seconds: float = Field(default=90, ge=1, le=300)
    context_max_chars: int = Field(default=8000, ge=256, le=65536)


class ExternalSettings(StrictModel):
    model: str = Field(default="", max_length=200)
    base_url: str = Field(default="", max_length=2048)
    model_folder: str = Field(default="", max_length=2048)


class WorkerSettings(StrictModel):
    worker_count: int = Field(default=2, ge=1, le=16)
    task_timeout_seconds: float = Field(default=300, ge=5, le=3600)


MAX_SETTINGS_BYTES = 262_144  # Bounded canonical store, including four 64-row purpose lists.


class AppSettings(StrictModel):
    version: Literal[10] = 10
    revision: int = Field(default=0, ge=0)
    delegation_epoch: int = Field(default=0, ge=0)
    dialogue: DialogueSettings = Field(default_factory=DialogueSettings)
    llama: LlamaOptions = Field(default_factory=LlamaOptions)
    external: ExternalSettings = Field(default_factory=ExternalSettings)
    runtime: WorkerSettings = Field(default_factory=WorkerSettings)
    local_companion: LocalCompanionPolicy = Field(default_factory=LocalCompanionPolicy)
    perception: PerceptionSettings = Field(default_factory=PerceptionSettings)
    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    agents: AgentPreferences = Field(default_factory=AgentPreferences)
    # Added 2026-10-08; settings saved before then load with the defaults.
    decision: DecisionSettings = Field(default_factory=DecisionSettings)
    # Added 2026-10-09; settings saved before then load with the defaults.
    memory: MemoryManagerSettings = Field(default_factory=MemoryManagerSettings)
    # Added 2026-10-11 (Alice as the default avatar); settings saved before then load with it.
    avatar: AvatarSettings = Field(default_factory=AvatarSettings)

    @model_validator(mode="after")
    def external_endpoint(self) -> AppSettings:
        if self.dialogue.backend == "openai-compatible":
            OpenAICompatibleDialogueProvider(
                base_url=self.external.base_url, model=self.external.model
            )
        return self


class SettingsEdit(StrictModel):
    version: Literal[2, 3, 4, 5, 6, 7, 8, 9, 10]
    expected_revision: int = Field(ge=0)
    changes: dict[str, Any]


class ReloadRequest(StrictModel):
    expected_revision: int = Field(ge=0)


class SettingsConflict(ValueError):
    pass


BOOT_FIELDS = {
    "avatar.vrm_path",  # the avatar loads when her player starts
    "dialogue.backend",
    "llama.executable",
    "llama.port",
    "llama.startup_timeout",
    "runtime.worker_count",
}
LABELS = {
    "runtime.task_timeout_seconds": "Specialist task time limit (seconds; new runs only)",
    "voice.python_executable": "Voice Python interpreter (blank uses installed voice runtime)",
    "voice.stt_model_path": "Whisper model directory (blank reuses installed assets)",
    "voice.tts_model_path": "Kokoro ONNX model (blank reuses installed assets)",
    "voice.voices_path": "Kokoro voice bank (blank reuses installed assets)",
    "voice.input_device": "Microphone device key (blank uses Windows default)",
    "voice.output_device": "Speaker device key (blank uses Windows default)",
    "voice.voice_id": "Kokoro voice name",
    "voice.recording_limit_seconds": "Maximum press-to-talk recording (seconds)",
    "voice.speech_speed": "Speech speed",
    "voice.listening": "Listening",
    "voice.wake_words": "Names she answers to (always-on listening)",
    "voice.follow_on_seconds": "Keep listening after she replies (seconds)",
    "voice.audio_route": "Voice to the brain",
    "perception.mode": "Automatic perception mode",
    "perception.paused": "Pause automatic perception",
    "perception.window_context": "Include window metadata on prompts",
    "perception.desktop_context": "Include Desktop file metadata on prompts",
    "perception.interval_seconds": "Background refresh interval (seconds)",
    "perception.context_max_age_seconds": "Background context maximum age (seconds)",
    "local_companion.desktop_observe": "Read windows and application text",
    "local_companion.desktop_capture": "View desktop images",
    "local_companion.file_read": "Read local files",
    "local_companion.desktop_interact": "Interact with applications",
    "local_companion.avatar_control": "Control the 3D companion",
    "local_companion.agent_delegation": "Delegate to specialist agents",
    "local_companion.direct_file_write": "Direct user-file writing (no writer available)",
    "local_companion.voice": "Enable voice features",
    "dialogue.backend": "Model source",
    "dialogue.context_max_chars": "Prompt budget (characters)",
    "dialogue.timeout_seconds": "Dialogue timeout (seconds)",
    "llama.model_path": "Brain model file (GGUF)",
    "llama.mmproj_path": "Vision projector file (GGUF, found automatically beside the model)",
    "external.model": "External server model ID",
    "external.base_url": "External server URL",
    "llama.context_size": "Context length (tokens)",
    "llama.vision_detail": "Vision detail",
    "decision.mode": "Decision layer (System-1)",
    "decision.threshold": "Offer a tool family from this probability",
    "decision.device": "Decision layer device",
    "decision.executable": "laya runner (blank uses the setup script's)",
    "decision.model_path": "Laya model GGUF (blank uses the setup script's)",
    "avatar.vrm_path": "Avatar model (VRM)",
    "memory.mode": "Memory manager",
    "memory.device": "Memory embedder device",
    "memory.server": "Embedding server (blank uses the setup script's)",
    "memory.model_path": "Embedding model GGUF (blank uses the setup script's)",
    "llama.image_max_tokens": "Image token budget (per image)",
    "llama.gpu_layers": "GPU offload layers",
    "llama.cache_type_k": "K cache quantisation",
    "llama.cache_type_v": "V cache quantisation",
    "llama.flash_attn": "Flash attention",
    "llama.speculative.type": "Speculative mode (MTP / DFlash)",
    "llama.speculative.draft_model_path": "Compatible draft model GGUF",
}
CUSTOM_LABELS = {
    "enabled": "Enable this custom agent",
    "nickname": "Nickname (what SORA calls it)",
    "spoken_aliases": "Spoken aliases (comma-separated)",
    "protocol": "Protocol (OpenAI-compatible API or Agent Client Protocol)",
    "port": "Local port (OpenAI-compatible only; API at 127.0.0.1)",
    "command": "Command to launch (ACP only, e.g. an executable on PATH)",
    "arguments": "Command arguments (ACP only; quote values with spaces)",
    "default_model": "Default model",
    "purpose": "Usage description (SORA reads this to choose an agent)",
}
CUSTOM_HELP = (
    "Choose the protocol. OpenAI-compatible: any harness serving /v1/chat/completions on this "
    "machine, at the port given. ACP: SORA launches the command with its arguments for each task "
    "and talks Agent Client Protocol over stdio, like Hermes. "
    "SORA asks it when you use its nickname or an alias, or when its usage description fits "
    "the task. Changes apply after SORA restarts, except the description, which is live."
)
POLICY_HELP = {
    "desktop_observe": "Read window metadata and accessible text. No per-window approval.",
    "desktop_capture": "Allow requested images and the selected automatic perception mode.",
    "file_read": "Read any local file your Windows account can read, including private documents.",
    "desktop_interact": "Use supported application controls; file authoring is delegated.",
    "avatar_control": "Allow companion poses, movement and presentation.",
    "agent_delegation": "Allow tasks to be dispatched to configured specialist agents.",
    "direct_file_write": (
        "Off by default. File authoring goes to specialists. This does not install a writer."
    ),
    "voice": "Make voice available. Start the microphone separately in the voice interface.",
}
PERCEPTION_HELP = {
    "mode": (
        "native-only adds no automatic images; image-on-prompt attaches a reduced image of the "
        "whole desktop (every monitor) to each message, and SORA can look closer at one window; "
        "adaptive interprets changed window images at the configured interval. "
        "Images are never recorded."
    ),
    "paused": (
        "Pause automatic metadata and images. Explicit read/look requests remain available "
        "under Companion access."
    ),
    "window_context": (
        "Add fresh window titles and recent application identity, not document bodies. "
        "Requires window access."
    ),
    "desktop_context": (
        "Add a bounded Desktop directory preview, not file contents. Requires local-file access."
    ),
    "interval_seconds": (
        "Adaptive only. Minimum time between refreshes; conversation preempts background work. "
        "Unchanged window images do not invoke the model again."
    ),
    "context_max_age_seconds": (
        "Adaptive only. Reject background context not reverified within this age. "
        "It is interpreted data, never authority for an action."
    ),
}


VISION_DISCLAIMER = (
    "Higher detail increases response times and context usage, but SORA reads your screen "
    "more reliably and guesses less."
)
VISION_HELP = {
    "llama.vision_detail": (
        "How much of each image SORA's model can see. Low, medium and high set the image token "
        "budget, physical batch and context length together; changing any of those by hand "
        "makes this Custom. " + VISION_DISCLAIMER + " Applies when the model reloads."
    ),
    "llama.image_max_tokens": (
        "llama.cpp --image-max-tokens: the most tokens one image may use. Set by Vision detail; "
        "editing it switches Vision detail to Custom. Physical batch must be at least this."
    ),
    "llama.ubatch_size": (
        "llama.cpp --ubatch-size. Set by Vision detail and must be at least the image token "
        "budget; editing it switches Vision detail to Custom."
    ),
    "llama.context_size": (
        "llama.cpp --ctx-size. Set by Vision detail, since images use context; editing it "
        "switches Vision detail to Custom."
    ),
}


DECISION_HELP = {
    "mode": (
        "A small fast model (Laya, on the GPU) chooses which kinds of tools her brain sees for "
        "each message. Fewer choices make a small brain's tool use more reliable. shadow: it "
        "decides and the decision is logged for training, but every tool stays available. "
        "enforce: only the chosen kinds are offered. off: not used. Needs "
        "scripts/setup-decision-layer.ps1."
    ),
    "threshold": (
        "Lower offers more tools (fewer missed, more for the brain to choose from); higher "
        "offers fewer. Untrained, 0.25 kept every needed kind in testing while offering about "
        "half."
    ),
    "device": "auto uses the GPU when available (Vulkan on AMD). Applies to the next message.",
    "executable": "The ggmlc laya runner. Blank: .local/decision from the setup script.",
    "model_path": "A Laya GGUF compiled by ggmlc (not a llama.cpp model).",
}
AVATAR_HELP = (
    "The VRM avatar she wears, applied when SORA next starts. Default: Alice, kept in "
    ".local\\avatars\\Alice.vrm (outside git; her licence forbids sharing or editing the file). "
    f"Credit: {CREDIT}. Blank, or a missing file, uses the built-in Seed-san."
)
MEMORY_HELP = {
    "mode": (
        "A small embedding model (EmbeddingGemma 2) reads each memory so she can find memories "
        "by meaning, link related ones and notice repeats and updates. on (default): her "
        "replies see the memories most relevant to your message. shadow: her replies see "
        "memories sharing words with your message and your most recent ones, and what "
        "meaning-based recall would have chosen is recorded for comparison. off: not used. "
        "Needs scripts/setup-memory-embedder.ps1."
    ),
    "device": "gpu uses about 0.2 GB of video memory; cpu is slower but uses none.",
    "server": "llama.cpp b11516 or newer. Blank: .local/llama.cpp-b11516 from the setup script.",
    "model_path": "An EmbeddingGemma 2 GGUF. Changing it re-embeds every memory.",
}
LISTENING_HELP = {
    "voice.listening": (
        "press: hold the Chat microphone button to talk. always: the microphone stays open while "
        "voice is on, and she answers when you say her name (or keep talking just after she "
        "replies). Audio stays in memory on this PC; it is saved only with a moment she "
        "chooses to remember, and forgetting that memory deletes it. Start voice again to apply."
    ),
    "voice.wake_words": (
        "Comma-separated names she answers to when listening is always on, for example "
        "\"sora, zora\" if speech recognition sometimes mishears her name."
    ),
    "voice.follow_on_seconds": (
        "After she finishes speaking, you can keep talking without her name for this many "
        "seconds. 0 turns it off."
    ),
    "voice.audio_route": (
        "auto: brains that hear audio natively (Gemma 4 E2B and E4B) receive your voice itself, "
        "with the transcript as a hint. transcribe: send only the speech-to-text transcript."
    ),
}


def flatten(value: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(item, dict):
            result.update(flatten(item, name))
        else:
            result[name] = item
    return result


def update_values(settings: AppSettings, changes: dict[str, Any]) -> AppSettings:
    payload = settings.model_dump(mode="json")
    for key, value in changes.items():
        node = payload
        parts = key.split(".")
        for part in parts[:-1]:
            node = node[part]
        node[parts[-1]] = value
    return AppSettings.model_validate(payload)


BUILTIN_AGENT_KEYS = ("codex", "hermes", "antigravity", "claude")
CUSTOM_AGENT_KEYS = ("custom_1", "custom_2", "custom_3", "custom_4")
SETTINGS_CATEGORIES = (
    "General", "Appearance", "Models", "Audio", "Vision", "Memory", "Tools",
    "Automation", "Performance", "Advanced",
)
# Deliberate UI mapping, not an extra settings store. Adding a preference requires
# assigning its category; metadata never changes effect tiers or authorization.
SETTINGS_CATEGORY_KEYS = {
    "General": {"dialogue.backend", "dialogue.timeout_seconds", "dialogue.context_max_chars"},
    "Models": {
        "llama.model_path", "llama.mmproj_path", "llama.context_size", "llama.gpu_layers",
        "llama.flash_attn", "llama.cache_type_k", "llama.cache_type_v",
        "external.model", "external.base_url", "external.model_folder",
        "decision.mode", "decision.threshold", "decision.device", "decision.executable",
        "decision.model_path",
        *{f"llama.speculative.{name}" for name in (
            "type", "draft_model_path", "draft_gpu_layers", "draft_cache_type_k",
            "draft_cache_type_v", "draft_tokens_min", "draft_tokens_max",
        )},
        *{f"agents.{agent}.{name}" for agent in BUILTIN_AGENT_KEYS
          for name in ("enabled", "purpose", "preferred_model", "preferred_effort",
                       "model_purpose", "model_choices")},
        *{f"agents.{slot}.{name}" for slot in CUSTOM_AGENT_KEYS
          for name in CustomEndpoint.model_fields},
    },
    "Audio": {"local_companion.voice", *{f"voice.{name}" for name in (
        "python_executable", "stt_model_path", "tts_model_path", "voices_path",
        "input_device", "output_device", "voice_id", "recording_limit_seconds", "speech_speed",
        "listening", "wake_words", "follow_on_seconds", "audio_route",
    )}},
    "Vision": {"llama.vision_detail", "local_companion.desktop_observe",
               "local_companion.desktop_capture",
               *{f"perception.{name}" for name in (
                   "mode", "paused", "window_context", "desktop_context", "interval_seconds",
                   "context_max_age_seconds",
               )}},
    "Tools": {
        *{f"local_companion.{name}" for name in (
            "file_read", "desktop_interact", "avatar_control", "agent_delegation",
            "direct_file_write",
        )},
        *{f"agents.{agent}.{name}" for agent in BUILTIN_AGENT_KEYS
          for name in ("project_root", "workspace_mode", "base_ref")},
        "runtime.task_timeout_seconds",
    },
    "Appearance": {"avatar.vrm_path"},
    "Memory": {"memory.mode", "memory.device", "memory.server", "memory.model_path"},
    "Performance": {f"llama.{name}" for name in (
        "image_max_tokens", "batch_size", "ubatch_size", "split_mode", "tensor_split", "main_gpu",
        "cpu_moe", "n_cpu_moe", "load_mode", "swa_full",
    )} | {"runtime.worker_count"},
    "Advanced": {"llama.executable", "llama.port", "llama.startup_timeout"},
}
SETTINGS_ADVANCED_KEYS = {
    "decision.device", "decision.executable", "decision.model_path",
    "memory.device", "memory.server", "memory.model_path",
    "dialogue.timeout_seconds", "dialogue.context_max_chars", "external.model_folder",
    "voice.python_executable", "voice.stt_model_path", "voice.tts_model_path", "voice.voices_path",
    *{f"llama.speculative.{name}" for name in (
        "draft_gpu_layers", "draft_cache_type_k", "draft_cache_type_v",
        "draft_tokens_min", "draft_tokens_max",
    )},
}


def field_definitions() -> list[dict[str, Any]]:
    """Schema-backed controls: every stored preference has exactly one effect tier."""
    result: list[dict[str, Any]] = []

    def visit(model: StrictModel, prefix: str = "") -> None:
        for name, field in type(model).model_fields.items():
            if not prefix and name in {"version", "revision", "delegation_epoch"}:
                continue
            value = getattr(model, name)
            key = f"{prefix}.{name}" if prefix else name
            if isinstance(value, StrictModel):
                visit(value, key)
                continue
            choices = (
                list(get_args(field.annotation))
                if (str(field.annotation).startswith("typing.Literal["))
                else []
            )
            kind = "string"
            if key.startswith("agents.") and name == "preferred_effort":
                choices = [
                    "configured", "none", "minimal", "low", "medium", "high",
                    "xhigh", "max", "ultra",
                ]
                if ".hermes." in key or ".claude." in key:
                    choices = ["configured"]
                elif ".antigravity." in key:
                    choices = ["configured", "low", "medium", "high", "max"]
            if name.endswith("gpu_layers") or name == "gpu_layers":
                kind, choices = "gpu", ["auto", "all"]
            elif choices:
                kind = "enum"
            elif isinstance(value, bool):
                kind = "bool"
            elif field.annotation is float:
                kind = "float"
            elif isinstance(value, int):
                kind = "int"
            elif isinstance(value, float) or name.endswith("seconds") or name == "startup_timeout":
                kind = "float"
            elif key == "voice.stt_model_path":
                kind = "path-dir"
            elif key in {"voice.tts_model_path", "voice.voices_path", "avatar.vrm_path"}:
                kind = "path-file"
            elif key == "voice.python_executable":
                kind = "path-exe"
            elif name.endswith("path"):
                kind = "path-gguf"
            elif name == "executable" or key in {"decision.executable", "memory.server"}:
                kind = "path-exe"
            elif name == "model_folder":
                kind = "path-dir"
            elif key.startswith("agents.") and name == "preferred_model":
                kind = "agent-model"
            elif key.startswith("agents.") and name == "project_root":
                kind = "path-dir"
            elif key.startswith("agents.") and name == "model_choices":
                kind = "agent-model-purposes"
            custom_agent = key.startswith("agents.custom_")
            tier = (
                "next_boot"
                if key in BOOT_FIELDS or key.startswith("external.")
                # Custom agents are registered when Core starts; only the description is live.
                or (custom_agent and name != "purpose")
                else "model_reload"
                if key.startswith("llama.")
                else "live"
            )
            group = (
                "Agents · Custom agent " + key.split(".")[1].removeprefix("custom_")
                if custom_agent
                else "Agents · " + key.split(".")[1].title()
                if key.startswith("agents.")
                else
                "Companion access"
                if key.startswith("local_companion.")
                else "Vision detail"
                if key == "llama.vision_detail"
                else "Decision layer (Laya)"
                if key.startswith("decision.")
                else "Memory manager (EmbeddingGemma 2)"
                if key.startswith("memory.")
                else "Avatar"
                if key.startswith("avatar.")
                else "Speculative decoding"
                if ".speculative." in key
                # The brain's own files come first in Models, apart from tuning knobs.
                else "Brain (local model)"
                if key in {"llama.model_path", "llama.mmproj_path"}
                else "External server (only when Model source is external)"
                if key.startswith("external.")
                else "Model & performance"
                if key.startswith("llama.")
                else key.split(".")[0].title()
            )
            item: dict[str, Any] = {
                "key": key,
                "label": (CUSTOM_LABELS[name] if custom_agent else
                          "Usage description (SORA reads this to choose an agent)"
                          if key.startswith("agents.") and name == "purpose" else
                          "Model shortlist and purposes" if name == "model_choices" else
                          "Default model purpose (fallback)" if key.startswith("agents.")
                          and name == "model_purpose" else
                          LABELS.get(key, name.replace("_", " ").capitalize())),
                "group": group,
                "category": next(category for category, keys in SETTINGS_CATEGORY_KEYS.items()
                                 if key in keys),
                "advanced": key in SETTINGS_ADVANCED_KEYS,
                "type": kind,
                "tier": tier,
                "choices": choices,
                "editable": True,
                "help": (
                    "Edit multiple exact model IDs and purposes. Saved rows override provider "
                    "descriptions and are offered first to SORA; other listed models remain "
                    "discoverable. This is descriptive metadata, not permission or verified "
                    "access. Does not change the preferred model or existing tasks."
                    if kind == "agent-model-purposes" else
                    CUSTOM_HELP
                    if custom_agent else
                    "Saved locally. Blank model and configured effort retain the harness default. "
                    "Model IDs must exactly match the catalogue; listing is not verified access. "
                    "Preferences apply to new tasks. Disabling an agent revokes local runs."
                    if key.startswith("agents.") else
                    POLICY_HELP[name]
                    if key.startswith("local_companion.")
                    else PERCEPTION_HELP[name]
                    if key.startswith("perception.")
                    else LISTENING_HELP[key]
                    if key in LISTENING_HELP
                    else "Local speech only. Changes stop active voice; start it again to apply. "
                    "Device keys are shown in the Voice window. No automatic model download."
                    if key.startswith("voice.")
                    else VISION_HELP[key]
                    if key in VISION_HELP
                    else DECISION_HELP[name]
                    if key.startswith("decision.")
                    else MEMORY_HELP[name]
                    if key.startswith("memory.")
                    else AVATAR_HELP
                    if key.startswith("avatar.")
                    else "Requires compatible model, draft weights and runtime support."
                    if ".speculative." in key
                    else "Model changes are saved first; Reload model applies them."
                ),
            }
            for bound in field.metadata:
                if hasattr(bound, "ge"):
                    item["min"] = bound.ge
                if hasattr(bound, "le"):
                    item["max"] = bound.le
            result.append(item)

    visit(AppSettings())
    # Everyday access controls should not be buried beneath advanced GPU/draft knobs.
    return sorted(result, key=lambda item: {"Companion access": 0, "Perception": 1}.get(
        item["group"], 2
    ))


FIELDS = field_definitions()
TIERS = {field["key"]: field["tier"] for field in FIELDS}


class AppSettingsStore:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.digest = self.disk_digest()

    def disk_digest(self) -> str:
        if not self.path.exists():
            return ""
        if self.path.stat().st_size > MAX_SETTINGS_BYTES:
            # Do not read an unbounded malformed file, but detect replacements.
            stat = self.path.stat()
            return f"oversized:{stat.st_size}:{stat.st_mtime_ns}"
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def unchanged(self) -> None:
        if self.disk_digest() != self.digest:
            raise SettingsConflict("Settings changed on disk. Use Refresh from disk before saving.")

    def load(self) -> AppSettings:
        if self.path.stat().st_size > MAX_SETTINGS_BYTES:
            raise ValueError("Settings exceed the 256 KiB limit")
        raw = self.path.read_text(encoding="utf-8-sig")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("Settings must be an object")
        old_version = payload.get("version")
        migrating = old_version in {2, 3, 4, 5, 6, 7, 8, 9}
        if old_version != 2 and (not isinstance(payload.get("local_companion"), dict) or (
            set(payload["local_companion"]) != set(LocalCompanionPolicy.model_fields)
        )):
            raise ValueError("Settings require complete companion access settings")
        perception_fields = set(PerceptionSettings.model_fields)
        if old_version == 4:
            perception_fields -= {"interval_seconds", "context_max_age_seconds"}
        if old_version in {4, 5, 6, 7, 8, 9, 10} and (
            not isinstance(payload.get("perception"), dict)
            or set(payload["perception"]) != perception_fields
        ):
            raise ValueError("Settings require complete automatic perception settings")
        if migrating:
            payload["version"] = 10
            if old_version in {2, 3}:
                # Never switch automatic images on by upgrading: pre-perception settings keep the
                # mode they effectively had. Only new settings start with image-on-prompt.
                payload.setdefault(
                    "perception", PerceptionSettings(mode="native-only").model_dump(),
                )
        if old_version in {6, 7, 8, 9, 10} and (not isinstance(payload.get("voice"), dict) or (
            not set(VoiceSettings.model_fields) - LISTENING_FIELDS
            <= set(payload["voice"])
            <= set(VoiceSettings.model_fields)
        )):
            raise ValueError("Settings require complete local voice settings")
        agent_keys = set(AgentPreferences.model_fields)
        if old_version in {7, 8, 9}:
            agent_keys = {"codex", "hermes", "antigravity"}
        if old_version in {7, 8, 9, 10} and (not isinstance(payload.get("agents"), dict) or (
            set(payload["agents"]) != agent_keys
        )):
            raise ValueError("Settings require complete agent preferences")
        required_agent_fields = set(AgentPreference.model_fields)
        if old_version in {7, 8}:
            required_agent_fields -= {"model_choices"}
        if old_version == 7:
            required_agent_fields -= {"project_root", "workspace_mode", "base_ref"}
        if old_version in {7, 8, 9, 10} and any(
            not isinstance(value, dict) or set(value) != (
                set(CustomEndpoint.model_fields) if name.startswith("custom_")
                else required_agent_fields
            )
            for name, value in payload["agents"].items()
        ):
            raise ValueError("Settings require complete preferences for each agent")
        if old_version in {7, 8}:
            for entry in payload["agents"].values():
                # Preserve the legacy fallback field too, including orphan descriptions.
                entry["model_choices"] = ([{
                    "id": entry["preferred_model"], "purpose": entry["model_purpose"],
                }] if entry["preferred_model"] and entry["model_purpose"] else [])
        if old_version in {7, 8, 9}:
            # v10 adds Claude and four custom-agent slots, all with default descriptions.
            defaults = AgentPreferences().model_dump(mode="json")
            for name in set(defaults) - set(payload["agents"]):
                payload["agents"][name] = defaults[name]
        settings = AppSettings.model_validate(payload)
        self.digest = self.disk_digest()
        if migrating:
            import shutil

            shutil.copyfile(
                self.path, self.path.with_suffix(f".v{old_version}-{uuid.uuid4().hex}.json")
            )
            self.write(settings)
        return settings

    def write(self, settings: AppSettings, *, backup_invalid: bool = False) -> None:
        self.unchanged()
        encoded = settings.model_dump_json(indent=2) + "\n"
        if len(encoded.encode("utf-8")) > MAX_SETTINGS_BYTES:
            raise ValueError("Settings exceed the 256 KiB limit")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if backup_invalid and self.path.exists():
            import shutil

            shutil.copyfile(self.path, self.path.with_suffix(f".invalid-{uuid.uuid4().hex}.json"))
        temporary = self.path.with_suffix(f".tmp-{uuid.uuid4().hex}")
        try:
            temporary.write_text(encoded, encoding="utf-8")
            self.unchanged()
            os.replace(temporary, self.path)
            self.digest = self.disk_digest()
        finally:
            temporary.unlink(missing_ok=True)


def discover_projectors(model_path: str) -> list[str]:
    model = LlamaServerConfig.local_file(Path(model_path))
    with model.open("rb") as stream:
        if model.suffix.lower() != ".gguf" or stream.read(4) != b"GGUF":
            raise ValueError("Select a GGUF model")
    return sorted(
        str(path.resolve())
        for path in model.parent.glob("*.gguf")
        if path.name.lower().startswith("mmproj") and path != model
    )[:100]


class AppSettingsController:
    def __init__(
        self,
        root: Path,
        initial: AppSettings,
        *,
        path: Path | None = None,
        server_factory: Callable[
            [LlamaServerConfig, Path], ManagedLlamaServer
        ] = ManagedLlamaServer,
        external_key: str | None = None,
    ):
        self.root = root
        self.store = AppSettingsStore(path or root / "data" / "sora-settings.json")
        self.disk_error = ""
        self.migration_note = ""
        self.policy_epoch = 0
        self.on_policy_change: Callable[[], None] = lambda: None
        if self.store.path.exists():
            try:
                initial = self.store.load()
            except (ValueError, OSError):
                self.disk_error = (
                    "Settings file is invalid. Save repaired settings to back up and replace it."
                )
                try:
                    initial = AppSettingsStore(self.store.path.with_name(
                        "sora-settings.recovery.json"
                    )).load()
                    self.disk_error += " Last readable settings restored."
                except (ValueError, OSError):
                    initial = initial.model_copy(update={
                        "local_companion": LocalCompanionPolicy.disabled(),
                    })
                    self.disk_error += " Companion access is disabled until settings are repaired."
        else:
            self.store.write(initial)
            self.migration_note = (
                "Imported startup/legacy preferences; original files were preserved."
            )
        self.saved = initial
        self.active = initial
        self.boot = initial
        self.model_revision = 0
        self.model_state = "down" if initial.dialogue.backend == "managed-llama" else "ready"
        self.last_error = self.disk_error
        self.rollback_applied = False
        self.server: ManagedLlamaServer | None = None
        self.server_factory = server_factory
        self.external_key = external_key
        self.provider: DialogueProvider = DeterministicDialogueProvider()
        self.on_provider: Callable[[DialogueProvider], None] = lambda provider: None
        self.task: asyncio.Task[None] | None = None
        self._inflight = 0
        self._idle = asyncio.Event()
        self._idle.set()
        self._last_good: AppSettings | None = None
        self.runtime_support = "Not checked"
        if not self.disk_error:
            self._save_recovery()

    def _save_recovery(self) -> None:
        try:
            AppSettingsStore(self.store.path.with_name("sora-settings.recovery.json")).write(
                self.saved
            )
        except OSError:
            self.migration_note = "Settings saved, but the recovery copy could not be updated."

    def projection(self) -> dict[str, Any]:
        saved = flatten(self.saved.model_dump(mode="json"))
        active = flatten(self.active.model_dump(mode="json"))
        fields = [
            {
                **field,
                "value": saved[field["key"]],
                "active_value": active[field["key"]],
                "pending": saved[field["key"]] != active[field["key"]],
            }
            for field in FIELDS
        ]
        if self.boot.dialogue.backend == "managed-llama" and self.model_state == "down":
            for field in fields:
                if field["tier"] == "model_reload":
                    field.update(active_value=None, pending=True)
        model_pending = any(f["pending"] and f["tier"] == "model_reload" for f in fields)
        return {
            "settings_version": 10,
            "settings_revision": self.saved.revision,
            "active_settings_revision": self.boot.revision,
            "boot_revision": self.boot.revision,
            "model_revision": self.model_revision,
            "fields": fields,
            "pending_settings": None,
            "restart_required": any(f["pending"] and f["tier"] == "next_boot" for f in fields),
            "model_reload_required": model_pending,
            "can_reload": self.boot.dialogue.backend == "managed-llama"
            and self.model_state != "reloading",
            "model_state": self.model_state,
            "runtime_support": self.runtime_support,
            "model_error": self.last_error,
            "rollback_applied": self.rollback_applied,
            "disk_changed": self.store.disk_digest() != self.store.digest,
            "settings_warning": self.disk_error or self.migration_note,
            "settings_path": str(self.store.path),
            "dialogue_timeout_seconds": self.active.dialogue.timeout_seconds,
            "context_max_chars": self.active.dialogue.context_max_chars,
            "launch_details": self.launch_details(),
        }

    def reload_candidate(self) -> AppSettings:
        """Same model-tier blend for admission and preview, without path/runtime probes."""
        values = flatten(self.saved.model_dump(mode="json"))
        candidate = update_values(
            self.active, {key: values[key] for key, tier in TIERS.items() if tier == "model_reload"}
        )
        return candidate.model_copy(update={"revision": self.saved.revision})

    def launch_details(self) -> dict[str, Any]:
        def preview(settings: AppSettings, note: str) -> dict[str, Any]:
            if settings.dialogue.backend != "managed-llama":
                return {"argv": None, "note": "Not applicable: not managed llama.cpp."}
            try:
                argv = public_llama_arguments(llama_arguments(settings.llama))
            except ValueError:
                argv = None
            return {"argv": argv, "note": note if argv is not None else
                    "Preview unavailable: select model/projector/draft paths "
                    "with bounded printable values."}

        argv = None
        if (self.boot.dialogue.backend == "managed-llama" and self.server is not None
                and self.server.process is not None and self.server.process.returncode is None
                and self.server.launch_arguments is not None):
            argv = public_llama_arguments(self.server.launch_arguments)
        return {
            "version": 1,
            "active": {
                "argv": argv,
                "note": "Core-captured submitted arguments for the managed worker. "
                        "Not independent OS attestation or measured model/GPU capability."
                        if argv is not None else
                        "No live managed-worker argument capture is available. "
                        "Do not infer a loaded model from saved preferences.",
            },
            "next_reload": preview(self.reload_candidate(),
                "Saved model-tier values with current effective boot settings; "
                "not file/runtime validated or applied."),
            "next_start": preview(self.saved,
                "Saved configuration for the next Core start, including boot-only changes; "
                "not file/runtime validated or applied."),
        }

    def _check(self, revision: int) -> None:
        if revision != self.saved.revision:
            raise SettingsConflict("Settings changed before this edit. Refresh and try again.")
        self.store.unchanged()
        if self.model_state == "reloading":
            raise SettingsConflict("A model reload is already running")

    def save(self, edit: SettingsEdit) -> dict[str, Any]:
        self._check(edit.expected_revision)
        unknown = set(edit.changes) - TIERS.keys()
        if unknown:
            raise ValueError(f"Unknown setting: {', '.join(sorted(unknown))}")
        changes = dict(edit.changes)
        for key, value in tuple(changes.items()):
            if key.startswith("agents.") and key.endswith(".project_root") and value:
                if not isinstance(value, str):
                    raise ValueError("Select a local project directory")
                changes[key] = str(project_directory(value))
        for key, value in tuple(changes.items()):
            if value and (
                key.endswith("_path") or key in {"llama.executable", "voice.python_executable"}
            ):
                if not isinstance(value, str) or value.startswith(("\\\\", "//")):
                    raise ValueError("Select an absolute local file path")
                path = Path(value)
                if not path.is_absolute():
                    raise ValueError("Select an absolute local file path")
                changes[key] = str(path.resolve())
        # GUI auto-detection is convenience only; Core independently resolves/validates it.
        if changes.get("llama.model_path") and (
            changes["llama.model_path"] != str(self.saved.llama.model_path)
        ):
            candidates = discover_projectors(str(changes["llama.model_path"]))
            if not changes.get("llama.mmproj_path"):
                if len(candidates) != 1:
                    raise ValueError("Select a matching projector: none or multiple were found")
                changes["llama.mmproj_path"] = candidates[0]
        changes = expand_choice(changes, self.saved.llama.batch_size)
        proposed = update_values(self.saved, changes)
        if proposed.dialogue.backend == "managed-llama" and any(
            key.startswith("llama.") or key == "dialogue.backend" for key in changes
        ):
            LlamaServerConfig.model_validate(proposed.llama.model_dump())
        if proposed == self.saved and not self.disk_error:
            return self.projection()
        proposed = proposed.model_copy(update={
            "revision": self.saved.revision + 1,
            "delegation_epoch": self.saved.delegation_epoch + int(
                proposed.local_companion.agent_delegation
                != self.saved.local_companion.agent_delegation
                or proposed.agents.enabled_state() != self.saved.agents.enabled_state()
            ),
        })
        self.store.write(proposed, backup_invalid=bool(self.disk_error))
        self.saved = proposed
        self.disk_error = ""
        self._apply_live()
        self._save_recovery()
        return self.projection()

    def refresh(self) -> dict[str, Any]:
        if self.model_state == "reloading":
            raise SettingsConflict("Wait for model reload before refreshing")
        try:
            loaded = self.store.load()
            epoch = max(loaded.delegation_epoch, self.saved.delegation_epoch)
            if (loaded.local_companion.agent_delegation
                    != self.saved.local_companion.agent_delegation
                    or loaded.agents.enabled_state() != self.saved.agents.enabled_state()):
                epoch += 1
            changed = loaded.model_dump(exclude={"revision", "delegation_epoch"}) != (
                self.saved.model_dump(exclude={"revision", "delegation_epoch"})
            )
            revision = max(loaded.revision, self.saved.revision + int(changed))
            if epoch != loaded.delegation_epoch or revision != loaded.revision:
                loaded = loaded.model_copy(update={
                    "delegation_epoch": epoch,
                    "revision": max(revision, self.saved.revision + 1),
                })
                self.store.write(loaded)
            self.saved = loaded
            self.disk_error = ""
            self._apply_live()
            self._save_recovery()
        except (ValueError, OSError):
            # Explicit refresh acknowledges the external edit. Preserve it; a subsequent
            # explicit Save backs up the invalid bytes before replacing them.
            self.store.digest = self.store.disk_digest()
            self.disk_error = (
                "Disk settings are invalid. Showing the last readable preferences; "
                "Save will back up the invalid file before replacing it."
            )
        return self.projection()

    def _apply_live(self) -> None:
        previous_policy = self.active.local_companion
        previous_perception = self.active.perception
        previous_voice = self.active.voice
        previous_delegation_epoch = self.active.delegation_epoch
        values = flatten(self.saved.model_dump(mode="json"))
        self.active = update_values(
            self.active, {key: values[key] for key, tier in TIERS.items() if tier == "live"}
        )
        self.active = self.active.model_copy(update={
            "delegation_epoch": self.saved.delegation_epoch,
        })
        if (self.active.local_companion != previous_policy
                or self.active.perception != previous_perception
                or self.active.voice != previous_voice
                or self.active.delegation_epoch != previous_delegation_epoch):
            self.policy_epoch += 1
            self.on_policy_change()
        # Existing turns hold their own provider reference; only new turns use this timeout.
        if isinstance(self.provider, OpenAICompatibleDialogueProvider):
            display_name = self.provider.display_name
            self.provider = OpenAICompatibleDialogueProvider(
                base_url=self.provider.base_url,
                model=self.provider.model,
                api_key=self.provider._api_key,
                timeout_seconds=self.active.dialogue.timeout_seconds,
                llama_native=self.provider.llama_native,
            )
            self.provider.display_name = display_name
            self.on_provider(self.provider)

    async def start(self) -> None:
        if self.disk_error:
            self.model_state = "down"
            return
        if self.boot.dialogue.backend == "managed-llama":
            self.model_state = "reloading"
            await self._reload(self.saved, startup=True)
        elif self.boot.dialogue.backend == "openai-compatible":
            self.provider = OpenAICompatibleDialogueProvider(
                base_url=self.boot.external.base_url,
                model=self.boot.external.model,
                api_key=self.external_key,
                timeout_seconds=self.active.dialogue.timeout_seconds,
            )

    def request_reload(self, request: ReloadRequest) -> dict[str, Any]:
        self._check(request.expected_revision)
        if self.boot.dialogue.backend != "managed-llama":
            raise ValueError("Choose managed llama.cpp and restart SORA before reloading")
        candidate = self.reload_candidate()
        LlamaServerConfig.model_validate(candidate.llama.model_dump())
        self.model_state = "reloading"  # Synchronous admission closes the dialogue race.
        self.task = asyncio.create_task(self._reload(candidate), name="settings-model-reload")
        return self.projection()

    async def _launch(self, candidate: AppSettings) -> None:
        config = LlamaServerConfig.model_validate(candidate.llama.model_dump())
        server = self.server_factory(config, self.root)
        self.server = server
        await server.start()
        self.provider = OpenAICompatibleDialogueProvider(
            base_url=server.base_url,
            model="sora-local",
            api_key=server.api_key,
            timeout_seconds=self.active.dialogue.timeout_seconds,
            llama_native=True,
        )
        self.provider.display_name = config.model_path.name
        # Gemma 4 E2B/E4B projectors carry an audio encoder: voice turns can send the clip itself.
        self.provider.audio_input = "audio" in projector_modalities(config.mmproj_path)
        self.on_provider(self.provider)

    async def _preflight(self, candidate: AppSettings) -> None:
        config = LlamaServerConfig.model_validate(candidate.llama.model_dump())
        probe = self.server_factory(config, self.root)
        self.runtime_support = await probe.inspect_runtime()

    async def _reload(self, candidate: AppSettings, *, startup: bool = False) -> None:
        previous = self._last_good
        self.last_error = ""
        self.rollback_applied = False
        stopped = self.server is None
        try:
            try:
                await self._preflight(candidate)
            except ValueError as exc:
                if startup:
                    raise
                self.last_error = str(exc)[:500]
                self.model_state = "ready" if self.server is not None else "down"
                return
            # A turn is bounded by its provider timeout. Do not kill a still-active turn.
            await asyncio.wait_for(self._idle.wait(), self.active.dialogue.timeout_seconds + 5)
            if self.server is not None:
                await self.server.close()
            stopped = True
            await self._launch(candidate)
            self.active = candidate
            self.model_revision = candidate.revision
            self._last_good = candidate
            self.model_state = "ready"
            good_store = AppSettingsStore(self.store.path.with_name("sora-settings.last-good.json"))
            try:
                good_store.write(candidate)
            except (OSError, SettingsConflict):
                self.last_error = (
                    "Model loaded, but the last-good recovery file could not be written."
                )
        except asyncio.CancelledError:
            self.model_state = "down"
            if self.server is not None:
                await self.server.close()
            raise
        except Exception as exc:
            # No arbitrary backend response/log dump: it may contain prompts or secrets.
            self.last_error = (
                f"Model load failed ({type(exc).__name__}). "
                "Check model/projector compatibility and local llama-server.log."
            )
            if isinstance(exc, ValueError):
                self.last_error = "Model paths or options are invalid. Correct them in Settings."
            if not stopped:
                self.model_state = "ready" if self.server is not None else "down"
                self.last_error = (
                    "Reload aborted before stopping the active model. "
                    "Check runtime support or wait for the active turn to finish."
                )
                return
            if self.server is not None:
                await self.server.close()
            if startup and previous is None:
                try:
                    previous = AppSettingsStore(
                        self.store.path.with_name("sora-settings.last-good.json")
                    ).load()
                    # Recover only model-tier values, never stale executable/bind/boot settings.
                    values = flatten(previous.model_dump(mode="json"))
                    previous = update_values(
                        candidate,
                        {key: values[key] for key, tier in TIERS.items() if tier == "model_reload"},
                    )
                except (ValueError, OSError):
                    previous = None
            if previous is not None:
                try:
                    await self._launch(previous)
                    self.active = previous
                    self._apply_live()
                    self.model_state = "ready"
                    self.model_revision = previous.revision
                    self._last_good = previous
                    self.rollback_applied = True
                    self.last_error += " Previous model restored; saved edits remain pending."
                    return
                except Exception:
                    if self.server is not None:
                        await self.server.close()
                    self.last_error += " Recovery also failed. Settings remains available."
            self.model_state = "down"

    @asynccontextmanager
    async def session(self) -> AsyncIterator[DialogueProvider]:
        if self.model_state != "ready":
            raise DialogueProviderError(
                "Model reloading or unavailable. Check Settings, then retry."
            )
        self._inflight += 1
        self._idle.clear()
        provider = self.provider
        try:
            yield provider
        finally:
            self._inflight -= 1
            if self._inflight == 0:
                self._idle.set()

    async def close(self) -> None:
        if self.task is not None and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        if self.server is not None:
            await self.server.close()
