"""SORA deterministic text-runtime command line."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import shutil
from pathlib import Path
from typing import NamedTuple

from pydantic import SecretStr

from sora import __version__, helper_processes
from sora.api import ApiServerConfig, SoraApiServer
from sora.api.lifecycle import ManagedLifecycle
from sora.contracts.models import TaskStatus
from sora.embodiment.avatar_settings import resolve_avatar
from sora.embodiment.local_player import LocalAvatarSession
from sora.providers.antigravity import AntigravityProvider
from sora.providers.base import ReasoningProvider
from sora.providers.claude_code import ClaudeCodeProvider
from sora.providers.codex import CodexAppServerProvider
from sora.providers.custom_endpoint import (
    CustomACPProvider,
    CustomEndpointProvider,
    split_command_arguments,
)
from sora.providers.hermes import HermesACPProvider
from sora.providers.llama_server import LlamaOptions
from sora.providers.mock import DeterministicProvider, FaultMode
from sora.runtime.agent_preferences import AgentPreferences
from sora.runtime.app_settings import AppSettings, AppSettingsController
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.runtime.settings import RuntimeSettingsStore


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="SORA deterministic local text runtime")
    result.add_argument("--root", type=Path, default=Path.cwd(), help="state/project root")
    result.add_argument("--identity-root", type=Path, default=None)
    result.add_argument("--llama-config", type=Path, default=None,
                        help="local llama.cpp JSON config; overrides saved model selection")
    result.add_argument("--settings", type=Path, default=None,
                        help="unified settings JSON (default: <root>/data/sora-settings.json)")
    result.add_argument("--embodiment-player", type=Path, default=None,
                        help="start this local Unity player with session-scoped renderer grants")
    result.add_argument("--avatar-path", type=Path, default=None,
                        help="optional VRM avatar for the managed local player")
    result.add_argument("--once", help="submit one reasoning task")
    result.add_argument("--wait", action="store_true", help="wait for --once to finish")
    result.add_argument("--state", action="store_true", help="print state summary and exit")
    result.add_argument("--tasks", action="store_true", help="print tasks and exit")
    result.add_argument("--messages", action="store_true", help="print messages and exit")
    result.add_argument("--mock-fault", choices=[item.value for item in FaultMode], default="none")
    result.add_argument("--mock-delay", type=float, default=0.0)
    result.add_argument(
        "--task-timeout",
        type=float,
        default=30.0,
        help="provider task deadline and --wait timeout in seconds",
    )
    result.add_argument(
        "--provider",
        choices=("auto", "deterministic", "hermes", "codex", "antigravity", "claude"),
        default=os.getenv("SORA_PROVIDER", "auto"),
        help=(
            "reasoning backend; auto registers every usable backend so the routing "
            "engine chooses per task at runtime, deterministic is offline, "
            "Hermes/Codex/Antigravity/Claude are external"
        ),
    )
    result.add_argument(
        "--dialogue-backend",
        choices=("deterministic", "openai-compatible"),
        default=os.getenv("SORA_DIALOGUE_BACKEND", "deterministic"),
        help="direct conversational backend, selected independently from --provider",
    )
    result.add_argument(
        "--dialogue-model",
        default=os.getenv("SORA_DIALOGUE_MODEL"),
        help="direct model identifier for the OpenAI-compatible endpoint",
    )
    result.add_argument(
        "--dialogue-base-url",
        default=os.getenv("SORA_DIALOGUE_BASE_URL"),
        help="HTTPS or loopback HTTP /v1 endpoint for direct dialogue",
    )
    result.add_argument(
        "--dialogue-timeout",
        type=float,
        default=30.0,
        help="direct dialogue request timeout in seconds",
    )
    result.add_argument(
        "--windows-bridge",
        type=Path,
        default=None,
        help="explicit trusted Windows observation helper executable; disabled by default",
    )
    result.add_argument(
        "--windows-action",
        type=Path,
        default=None,
        help="explicit trusted Windows Level 3 action helper executable; disabled by default",
    )
    result.add_argument(
        "--windows-type",
        type=Path,
        default=None,
        help="explicit trusted Windows semantic TYPE helper executable; disabled by default",
    )
    result.add_argument(
        "--windows-capture",
        type=Path,
        default=None,
        help="explicit trusted one-shot Windows capture helper executable; disabled by default",
    )
    result.add_argument(
        "--listen-on-start",
        action="store_true",
        help="start local voice at launch when Settings set listening to always (owner launch)",
    )
    result.add_argument(
        "--editor-root",
        type=Path,
        action="append",
        default=None,
        help="configured repository root accepted from cooperating editor integrations; repeatable",
    )
    result.add_argument("--hermes-command", default=os.getenv("SORA_HERMES_COMMAND", "hermes"))
    result.add_argument(
        "--hermes-cwd",
        type=Path,
        default=None,
        help="explicit Hermes working directory; required with --provider hermes",
    )
    result.add_argument(
        "--hermes-arg",
        action="append",
        default=None,
        help="Hermes ACP argument; repeat to override the default 'acp'",
    )
    result.add_argument(
        "--hermes-deny-approvals",
        action="store_true",
        help="deny Hermes ACP approval requests instead of allowing each requested operation once",
    )
    result.add_argument(
        "--hermes-skip-configured-mcp",
        action="store_true",
        help="start Hermes without globally configured MCP integrations",
    )
    result.add_argument("--codex-command", default=os.getenv("SORA_CODEX_COMMAND", "codex"))
    result.add_argument(
        "--codex-cwd",
        type=Path,
        default=None,
        help="explicit Codex working directory; required with --provider codex",
    )
    result.add_argument(
        "--codex-model",
        default=os.getenv("SORA_CODEX_MODEL", "gpt-5.6-luna"),
        help="Codex model; defaults to the cost-sensitive GPT-5.6 Luna",
    )
    result.add_argument(
        "--codex-effort",
        default="low",
        help="Codex reasoning effort; defaults to low for bounded cost",
    )
    result.add_argument(
        "--codex-sandbox",
        choices=("read-only",),
        default="read-only",
        help="Codex direct CLI sandbox; writes require the owned-workspace API",
    )
    result.add_argument(
        "--codex-write-base",
        default=None,
        help="explicit Git base ref enabling managed Codex coding writes",
    )
    result.add_argument(
        "--codex-workspace-root",
        type=Path,
        default=None,
        help="owned worktree state root; defaults below --root when write-base is configured",
    )
    result.add_argument(
        "--workspace-root",
        type=Path,
        default=None,
        help=(
            "delegated-agent working directory used when a backend has no explicit "
            "cwd of its own; defaults to <root>/workspace"
        ),
    )
    result.add_argument(
        "--antigravity-command",
        default=os.getenv("SORA_ANTIGRAVITY_COMMAND", "agy"),
        help="Antigravity CLI command executable",
    )
    result.add_argument(
        "--antigravity-arg",
        action="append",
        default=None,
        help=(
            "extra Antigravity CLI argument, e.g. --dangerously-skip-permissions for a "
            "headless run where auto-denied tools would otherwise produce an empty answer; "
            "repeatable"
        ),
    )
    result.add_argument(
        "--antigravity-ask-permissions",
        action="store_true",
        help=(
            "do not pass --dangerously-skip-permissions to Antigravity by default; headless "
            "runs then auto-deny tools that need approval"
        ),
    )
    result.add_argument(
        "--agent-write-root",
        action="append",
        default=None,
        help=(
            "grant the Codex adapter direct write access to this exact project directory, in "
            "place and without a worktree; repeatable, and required for workspace-write outside "
            "a managed worktree"
        ),
    )
    result.add_argument(
        "--antigravity-cwd",
        type=Path,
        default=None,
        help="explicit Antigravity working directory",
    )
    result.add_argument(
        "--antigravity-model",
        default=os.getenv("SORA_ANTIGRAVITY_MODEL", None),
        help="Antigravity model override",
    )
    result.add_argument(
        "--antigravity-effort",
        choices=("low", "medium", "high"),
        default=os.getenv("SORA_ANTIGRAVITY_EFFORT", "medium"),
        help="Antigravity reasoning effort level",
    )
    result.add_argument(
        "--claude-command",
        default=os.getenv("SORA_CLAUDE_COMMAND", "claude"),
        help="Claude Code CLI executable (headless, on the owner's subscription)",
    )
    result.add_argument(
        "--claude-arg",
        action="append",
        default=None,
        help=(
            "extra Claude Code argument, repeatable; replaces the default "
            "--permission-mode bypassPermissions"
        ),
    )
    result.add_argument(
        "--claude-ask-permissions",
        action="store_true",
        help=(
            "do not pass Claude Code --permission-mode bypassPermissions by default; print "
            "mode then denies tools that need approval, so Claude can read but not edit"
        ),
    )
    result.add_argument(
        "--claude-cwd",
        type=Path,
        default=None,
        help="explicit Claude Code working directory",
    )
    result.add_argument(
        "--claude-model",
        default=os.getenv("SORA_CLAUDE_MODEL", None),
        help="Claude model alias or name; blank uses Claude Code's own default",
    )
    result.add_argument(
        "--serve",
        action="store_true",
        help="start the authenticated HTTP and WebSocket API server",
    )
    result.add_argument(
        "--api-host",
        default="127.0.0.1",
        help="API server listen host (default 127.0.0.1)",
    )
    result.add_argument(
        "--api-port",
        type=int,
        default=8765,
        help="API server listen port (default 8765)",
    )
    result.add_argument(
        "--api-token",
        default=None,
        help="bearer authentication token override for the API server",
    )
    result.add_argument(
        "--api-token-file",
        type=Path,
        default=None,
        help="file to write the API server bearer token to",
    )
    result.add_argument(
        "--api-remote",
        action="store_true",
        help="opt in to a second TLS-only private-network listener",
    )
    result.add_argument(
        "--api-remote-host",
        default=None,
        help="concrete private/overlay IP for the TLS remote listener",
    )
    result.add_argument(
        "--api-remote-port",
        type=int,
        default=8766,
        help="TLS remote listener port (default 8766)",
    )
    result.add_argument(
        "--api-tls-certificate",
        type=Path,
        default=None,
        help="PEM certificate for the opt-in remote listener",
    )
    result.add_argument(
        "--api-tls-private-key",
        type=Path,
        default=None,
        help="PEM private key for the opt-in remote listener",
    )
    result.add_argument(
        "--api-remote-origin",
        action="append",
        default=None,
        help="exact trusted HTTPS browser origin; repeatable",
    )
    result.add_argument(
        "--api-remote-hostname",
        action="append",
        default=None,
        help="additional exact Host header name covered by the TLS certificate; repeatable",
    )
    return result


# Owner decision 2026-10-05: hosted agents are trusted with file writes and run without
# permission prompts unless the owner opts out or passes their own arguments.
CLAUDE_FULL_ACCESS = ("--permission-mode", "bypassPermissions")
ANTIGRAVITY_FULL_ACCESS = ("--dangerously-skip-permissions",)


def hosted_agent_args(
    explicit: list[str] | None, ask_permissions: bool, full_access: tuple[str, ...],
) -> tuple[str, ...]:
    if explicit:
        return tuple(explicit)
    return () if ask_permissions else full_access


class ProviderSetupError(Exception):
    """An explicitly selected reasoning backend cannot be started."""


class ProviderPlan(NamedTuple):
    registry: dict[str, ReasoningProvider]
    skipped: tuple[str, ...]
    codex_cwd: Path | None


def build_provider_registry(
    arguments: argparse.Namespace, agents: AgentPreferences | None = None,
) -> ProviderPlan:
    """Register the reasoning backends SORA may route work to.

    ``--provider auto`` registers every backend that is actually usable on this
    machine so the routing engine chooses per task at runtime. An explicit
    ``--provider NAME`` keeps the fail-closed behaviour: only that backend is
    registered and a missing working directory is an error.
    """
    deterministic = DeterministicProvider(
        fault=FaultMode(arguments.mock_fault),
        delay_seconds=arguments.mock_delay,
    )
    if arguments.provider == "deterministic":
        return ProviderPlan({"deterministic": deterministic}, (), None)
    auto = arguments.provider == "auto"
    workspace = arguments.workspace_root or arguments.root / "workspace"
    if auto:
        workspace.mkdir(parents=True, exist_ok=True)
    registry: dict[str, ReasoningProvider] = {}
    skipped: list[str] = []
    codex_cwd: Path | None = None

    if arguments.provider in ("auto", "hermes"):
        hermes_cwd = arguments.hermes_cwd
        if hermes_cwd is None:
            if not auto:
                raise ProviderSetupError(
                    "Hermes requires --hermes-cwd so SORA can assign the intended "
                    "working directory."
                )
            hermes_cwd = workspace
        if not hermes_cwd.is_dir():
            if not auto:
                raise ProviderSetupError(
                    f"Hermes working directory does not exist: {hermes_cwd}"
                )
            skipped.append(f"hermes: working directory does not exist: {hermes_cwd}")
        elif auto and shutil.which(arguments.hermes_command) is None:
            skipped.append(f"hermes: '{arguments.hermes_command}' is not on PATH")
        else:
            registry["hermes"] = HermesACPProvider(
                command=arguments.hermes_command,
                args=tuple(arguments.hermes_arg or ["acp"]),
                cwd=str(hermes_cwd),
                permission_policy="deny" if arguments.hermes_deny_approvals else "allow_once",
                skip_configured_mcp=arguments.hermes_skip_configured_mcp,
            )

    if arguments.provider in ("auto", "codex"):
        candidate = arguments.codex_cwd
        if candidate is None:
            if not auto:
                raise ProviderSetupError(
                    "Codex requires --codex-cwd so SORA can assign the intended "
                    "working directory."
                )
            candidate = workspace
        if not candidate.is_dir():
            if not auto:
                raise ProviderSetupError(
                    f"Codex working directory does not exist: {candidate}"
                )
            skipped.append(f"codex: working directory does not exist: {candidate}")
        elif auto and shutil.which(arguments.codex_command) is None:
            skipped.append(f"codex: '{arguments.codex_command}' is not on PATH")
        else:
            codex_cwd = candidate
            registry["codex"] = CodexAppServerProvider(
                command=arguments.codex_command,
                cwd=str(candidate),
                model=arguments.codex_model,
                reasoning_effort=arguments.codex_effort,
                sandbox=arguments.codex_sandbox,
                timeout_seconds=arguments.task_timeout,
                direct_roots=tuple(arguments.agent_write_root or ()),
            )

    if arguments.provider in ("auto", "antigravity"):
        antigravity_cwd = arguments.antigravity_cwd
        if antigravity_cwd is None and auto:
            antigravity_cwd = workspace
        if antigravity_cwd is not None and not antigravity_cwd.is_dir():
            if not auto:
                raise ProviderSetupError(
                    f"Antigravity working directory does not exist: {antigravity_cwd}"
                )
            skipped.append(
                f"antigravity: working directory does not exist: {antigravity_cwd}"
            )
        elif auto and shutil.which(arguments.antigravity_command) is None:
            skipped.append(
                f"antigravity: '{arguments.antigravity_command}' is not on PATH"
            )
        else:
            registry["antigravity"] = AntigravityProvider(
                command=arguments.antigravity_command,
                args=hosted_agent_args(
                    arguments.antigravity_arg, arguments.antigravity_ask_permissions,
                    ANTIGRAVITY_FULL_ACCESS,
                ),
                cwd=str(antigravity_cwd) if antigravity_cwd else None,
                model=arguments.antigravity_model,
                effort=arguments.antigravity_effort,
                timeout_seconds=arguments.task_timeout,
            )

    if arguments.provider in ("auto", "claude"):
        claude_cwd = arguments.claude_cwd
        if claude_cwd is None and auto:
            claude_cwd = workspace
        if claude_cwd is not None and not claude_cwd.is_dir():
            if not auto:
                raise ProviderSetupError(
                    f"Claude working directory does not exist: {claude_cwd}"
                )
            skipped.append(f"claude: working directory does not exist: {claude_cwd}")
        elif auto and shutil.which(arguments.claude_command) is None:
            skipped.append(f"claude: '{arguments.claude_command}' is not on PATH")
        else:
            registry["claude"] = ClaudeCodeProvider(
                command=arguments.claude_command,
                args=hosted_agent_args(
                    arguments.claude_arg, arguments.claude_ask_permissions, CLAUDE_FULL_ACCESS,
                ),
                cwd=str(claude_cwd) if claude_cwd else None,
                model=arguments.claude_model,
                timeout_seconds=arguments.task_timeout,
            )

    if auto and agents is not None:
        # Owner-added agents from Settings; each is reached by its nickname or description.
        for key, endpoint in agents.custom_endpoints().items():
            if not endpoint.enabled:
                continue
            if endpoint.protocol == "acp":
                if shutil.which(endpoint.command.strip()) is None and not Path(
                    endpoint.command.strip(),
                ).is_file():
                    skipped.append(f"{key}: '{endpoint.command.strip()}' was not found")
                    continue
                registry[key] = CustomACPProvider(
                    key,
                    nickname=endpoint.nickname.strip(),
                    command=endpoint.command.strip(),
                    args=split_command_arguments(endpoint.arguments),
                    cwd=str(workspace),
                    timeout_seconds=arguments.task_timeout,
                )
            else:
                registry[key] = CustomEndpointProvider(
                    key,
                    nickname=endpoint.nickname.strip(),
                    port=endpoint.port,
                    model=endpoint.default_model or None,
                    timeout_seconds=arguments.task_timeout,
                )

    registry["deterministic"] = deterministic
    return ProviderPlan(registry, tuple(skipped), codex_cwd)


async def run(arguments: argparse.Namespace) -> int:
    try:
        lifecycle = ManagedLifecycle.from_environment()
    except ValueError as error:
        print(str(error))
        return 2
    if arguments.serve:
        helper_processes.enable(arguments.root)  # the desktop host's Quit closes them all
    if lifecycle is not None and not arguments.serve:
        print("Managed desktop launch requires serve mode.")
        return 2
    # Legacy stores seed the unified file once; after that GUI settings are authoritative.
    settings_path = arguments.settings or arguments.root / "data" / "sora-settings.json"
    initial = AppSettings()
    if not settings_path.exists():
        try:
            legacy = RuntimeSettingsStore(arguments.root).load()
        except (ValueError, OSError):
            legacy = None
            print("Legacy settings could not be imported; originals preserved. Use SORA Settings.")
        backend = legacy.dialogue_backend if legacy else arguments.dialogue_backend
        llama = LlamaOptions()
        if arguments.llama_config is not None:
            backend = "managed-llama"
            try:
                if arguments.llama_config.stat().st_size > 16_384:
                    raise ValueError("Oversized legacy config")
                payload = json.loads(arguments.llama_config.read_text(encoding="utf-8-sig"))
                for key in ("executable", "model_path", "mmproj_path"):
                    if payload.get(key):
                        payload[key] = str((arguments.llama_config.parent / payload[key]).resolve())
                llama = LlamaOptions.model_validate(payload)
            except (ValueError, OSError, TypeError, AttributeError):
                print("Legacy model configuration is invalid. Repair it in SORA Settings.")
        initial = AppSettings.model_validate({
            "dialogue": {"backend": backend,
                         "timeout_seconds": legacy.dialogue_timeout_seconds if legacy
                         else arguments.dialogue_timeout,
                         "context_max_chars": legacy.context_max_chars if legacy else 8000},
            "llama": llama.model_dump(),
            "external": {"model": (legacy.dialogue_model if legacy
                                    else arguments.dialogue_model) or "",
                         "base_url": (legacy.dialogue_base_url if legacy
                                       else arguments.dialogue_base_url) or "",
                         "model_folder": str(legacy.dialogue_model_folder)
                         if legacy and legacy.dialogue_model_folder else ""},
            "runtime": {"worker_count": legacy.worker_count if legacy else 2},
        })
    controller = AppSettingsController(arguments.root, initial, path=settings_path,
                                       external_key=os.getenv("SORA_DIALOGUE_API_KEY"))
    try:
        await controller.start()
        selected = controller.boot
        managed = selected.dialogue.backend == "managed-llama"
        arguments.dialogue_backend = "openai-compatible" if managed else selected.dialogue.backend
        arguments.dialogue_model = "sora-local" if managed else selected.external.model or None
        arguments.dialogue_base_url = (f"http://127.0.0.1:{selected.llama.port}/v1" if managed
                                       else selected.external.base_url or None)
        arguments.dialogue_timeout = selected.dialogue.timeout_seconds
        if controller.last_error:
            print(controller.last_error)
        return await _run(arguments, app_settings=controller, lifecycle=lifecycle)
    finally:
        await controller.close()


async def _run(
    arguments: argparse.Namespace, *, app_settings: AppSettingsController,
    lifecycle: ManagedLifecycle | None = None,
) -> int:
    if arguments.dialogue_backend == "openai-compatible" and (
        not arguments.dialogue_model or not arguments.dialogue_base_url
    ):
        print("Direct dialogue requires --dialogue-model and --dialogue-base-url.")
        return 2
    try:
        plan = build_provider_registry(arguments, app_settings.boot.agents)
    except ProviderSetupError as error:
        print(str(error))
        return 2
    managed_codex_writes = (
        plan.codex_cwd is not None and arguments.codex_write_base is not None
    )
    runtime = SoraRuntime(
        RuntimeConfig(
            root=arguments.root,
            identity_root=arguments.identity_root,
            task_timeout_seconds=arguments.task_timeout,
            dialogue_backend=arguments.dialogue_backend,
            dialogue_model=arguments.dialogue_model,
            dialogue_base_url=arguments.dialogue_base_url,
            managed_dialogue=app_settings.boot.dialogue.backend == "managed-llama",
            worker_count=app_settings.boot.runtime.worker_count,
            context_max_chars=app_settings.active.dialogue.context_max_chars,
            dialogue_api_key=(
                SecretStr(app_settings.server.api_key) if app_settings.server is not None else
                SecretStr(os.environ["SORA_DIALOGUE_API_KEY"])
                if arguments.dialogue_backend == "openai-compatible"
                and "SORA_DIALOGUE_API_KEY" in os.environ
                else None
            ),
            dialogue_timeout_seconds=arguments.dialogue_timeout,
            coding_repository_root=(plan.codex_cwd if managed_codex_writes else None),
            coding_workspace_root=(
                arguments.codex_workspace_root or arguments.root / ".local" / "coding-workspaces"
                if managed_codex_writes
                else None
            ),
            coding_base_ref=(arguments.codex_write_base if managed_codex_writes else None),
            windows_bridge_executable=arguments.windows_bridge,
            windows_action_executable=arguments.windows_action,
            windows_type_executable=arguments.windows_type,
            windows_capture_executable=arguments.windows_capture,
            editor_repository_roots=tuple(arguments.editor_root or ()),
            report_task_outcomes=True,
        ),
        providers=plan.registry,
        app_settings=app_settings,
    )
    try:
        await runtime.start()
        if arguments.serve:
            api_cfg = ApiServerConfig(
                host=arguments.api_host,
                port=arguments.api_port,
                auth_token=arguments.api_token or secrets.token_urlsafe(32),
                token_file=arguments.api_token_file,
                remote_access_enabled=arguments.api_remote,
                remote_host=arguments.api_remote_host,
                remote_port=arguments.api_remote_port,
                remote_tls_certificate_file=arguments.api_tls_certificate,
                remote_tls_private_key_file=arguments.api_tls_private_key,
                remote_allowed_origins=tuple(arguments.api_remote_origin or ()),
                remote_allowed_hosts=tuple(arguments.api_remote_hostname or ()),
            )
            api_server = SoraApiServer(runtime, api_cfg, lifecycle=lifecycle)
            await api_server.start()
            if arguments.embodiment_player is not None:
                # An explicit --avatar-path wins; otherwise Settings → Appearance (default
                # Alice), or the built-in Seed-san when that file is missing.
                avatar = arguments.avatar_path or resolve_avatar(
                    app_settings.boot.avatar, Path(__file__).resolve().parents[2])
                if avatar is None and app_settings.boot.avatar.vrm_path.strip():
                    print(f"Avatar {app_settings.boot.avatar.vrm_path} not found; "
                          "using the built-in Seed-san.")
                try:
                    runtime.local_avatar = LocalAvatarSession(
                        runtime, arguments.embodiment_player, avatar
                    )
                    await runtime.local_avatar.start(
                        token=api_cfg.auth_token, port=api_server.actual_port
                    )
                except Exception:
                    await api_server.close()
                    raise
            if arguments.listen_on_start:
                # Owner launches only: start listening and load the decision layer early.
                runtime.start_listening_on_launch()
                runtime.warm_decision_layer()
            # Every served Core embeds and recalls memories; it needs no microphone.
            runtime.start_memory_manager()
            print(
                f"SORA API Server running on http://{api_cfg.host}:{api_server.actual_port}"
            )
            if arguments.provider == "auto":
                print(
                    "Reasoning backends registered: "
                    + ", ".join(sorted(runtime.providers))
                    + " (routing chooses per task)"
                )
                for note in plan.skipped:
                    print(f"Backend unavailable — {note}")
            if api_server.actual_remote_port is not None:
                print(
                    "SORA private remote listener running on "
                    f"https://{api_cfg.remote_host}:{api_server.actual_remote_port} "
                    "(paired scoped sessions only; owner token rejected)"
                )
            try:
                if lifecycle is not None:
                    await lifecycle.shutdown.wait()
                else:
                    while True:
                        await asyncio.sleep(3600)
            except (asyncio.CancelledError, KeyboardInterrupt):
                pass
            finally:
                if runtime.local_avatar is not None:
                    await runtime.local_avatar.close()
                await api_server.close()
            return 0
        if arguments.state:
            print(json.dumps(await runtime.inspect_state(), indent=2, sort_keys=True))
            return 0
        if arguments.tasks:
            tasks = await runtime.runtime_repository.list_tasks()
            print(json.dumps([task.model_dump(mode="json") for task in tasks], indent=2))
            return 0
        if arguments.messages:
            messages = await runtime.repository.list_messages(runtime.config.conversation_id)
            print(json.dumps([message.model_dump(mode="json") for message in messages], indent=2))
            return 0
        if arguments.once:
            receipt = await runtime.submit_task(arguments.once)
            print(f"task_id={receipt.task.task_id}")
            print(receipt.acknowledgement)
            if arguments.wait:
                report = await runtime.wait_for_task(
                    receipt.task.task_id,
                    timeout=arguments.task_timeout + 5,
                )
                print(f"status={report.status.value}")
                print(report.message)
                return 0 if report.status is TaskStatus.COMPLETED else 1
            return 0
        if arguments.provider == "auto":
            await interactive(runtime, "auto")
        else:
            provider = plan.registry[arguments.provider]
            capabilities = await provider.capabilities()
            await interactive(runtime, capabilities.provider)
        return 0
    finally:
        await runtime.close()


async def interactive(runtime: SoraRuntime, provider_name: str) -> None:
    if provider_name == "auto":
        mode = "auto routing across " + ", ".join(sorted(runtime.providers))
    elif provider_name == "deterministic-mock":
        mode = "offline deterministic mock"
    else:
        mode = f"external provider {provider_name} (native tools enabled)"
    print(
        f"SORA {__version__} — {mode}; direct dialogue: "
        f"{runtime.config.dialogue_backend} "
        f"{runtime.config.dialogue_model or ''}. Type /help for commands."
    )
    while True:
        try:
            text = await asyncio.to_thread(input, "You> ")
        except EOFError:
            break
        stripped = text.strip()
        if not stripped:
            continue
        if stripped in {"/quit", "/exit"}:
            break
        if stripped == "/help":
            print(
                "/task TEXT, /tasks, /state, /messages, /wait TASK_ID, "
                "/cancel TASK_ID, /retry TASK_ID, /quit"
            )
        elif stripped.startswith("/task "):
            receipt = await runtime.submit_task(stripped[6:])
            print(f"SORA> {receipt.acknowledgement} [{receipt.task.task_id}]")
        elif stripped == "/tasks":
            for task in await runtime.runtime_repository.list_tasks():
                print(f"{task.task_id} [{task.status.value}]")
        elif stripped == "/state":
            print(json.dumps(await runtime.inspect_state(), sort_keys=True))
        elif stripped == "/messages":
            for message in await runtime.repository.list_messages(runtime.config.conversation_id):
                print(f"{message.role}> {message.content}")
        elif stripped.startswith("/wait "):
            report = await runtime.wait_for_task(stripped[6:])
            print(f"SORA> [{report.status.value}] {report.message}")
        elif stripped.startswith("/cancel "):
            changed = await runtime.cancel(stripped[8:])
            print("SORA> cancellation requested" if changed else "SORA> task was not cancellable")
        elif stripped.startswith("/retry "):
            try:
                task = await runtime.retry(stripped[7:])
            except (LookupError, ValueError) as exc:
                print(f"SORA> retry rejected: {exc}")
            else:
                print(f"SORA> retry queued [{task.active_run_id}]")
        else:
            print("SORA> ", end="", flush=True)
            async for chunk in runtime.stream_dialogue(stripped):
                print(chunk, end="", flush=True)
            print()


def main() -> None:
    arguments = parser().parse_args()
    raise SystemExit(asyncio.run(run(arguments)))


if __name__ == "__main__":
    main()
