"""SORA deterministic text-runtime command line."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from sora import __version__
from sora.contracts.models import TaskStatus
from sora.providers.antigravity import AntigravityProvider
from sora.providers.base import ReasoningProvider
from sora.providers.codex import CodexAppServerProvider
from sora.providers.hermes import HermesACPProvider
from sora.providers.mock import DeterministicProvider, FaultMode
from sora.runtime.service import RuntimeConfig, SoraRuntime


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="SORA deterministic local text runtime")
    result.add_argument("--root", type=Path, default=Path.cwd(), help="state/project root")
    result.add_argument("--identity-root", type=Path, default=None)
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
        choices=("deterministic", "hermes", "codex", "antigravity"),
        default=os.getenv("SORA_PROVIDER", "deterministic"),
        help="reasoning backend; deterministic is offline, Hermes/Codex/Antigravity are external",
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
        "--antigravity-command",
        default=os.getenv("SORA_ANTIGRAVITY_COMMAND", "agy"),
        help="Antigravity CLI command executable",
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
    return result


async def run(arguments: argparse.Namespace) -> int:
    provider: ReasoningProvider
    if arguments.provider == "hermes":
        if arguments.hermes_cwd is None:
            print("Hermes requires --hermes-cwd so SORA can assign the intended working directory.")
            return 2
        if not arguments.hermes_cwd.is_dir():
            print(f"Hermes working directory does not exist: {arguments.hermes_cwd}")
            return 2
        provider = HermesACPProvider(
            command=arguments.hermes_command,
            args=tuple(arguments.hermes_arg or ["acp"]),
            cwd=str(arguments.hermes_cwd) if arguments.hermes_cwd else None,
            permission_policy="deny" if arguments.hermes_deny_approvals else "allow_once",
            skip_configured_mcp=arguments.hermes_skip_configured_mcp,
        )
    elif arguments.provider == "codex":
        if arguments.codex_cwd is None:
            print("Codex requires --codex-cwd so SORA can assign the intended working directory.")
            return 2
        if not arguments.codex_cwd.is_dir():
            print(f"Codex working directory does not exist: {arguments.codex_cwd}")
            return 2
        provider = CodexAppServerProvider(
            command=arguments.codex_command,
            cwd=str(arguments.codex_cwd),
            model=arguments.codex_model,
            reasoning_effort=arguments.codex_effort,
            sandbox=arguments.codex_sandbox,
            timeout_seconds=arguments.task_timeout,
        )
    elif arguments.provider == "antigravity":
        if arguments.antigravity_cwd is not None and not arguments.antigravity_cwd.is_dir():
            print(
                f"Antigravity working directory does not exist: {arguments.antigravity_cwd}"
            )
            return 2
        provider = AntigravityProvider(
            command=arguments.antigravity_command,
            cwd=str(arguments.antigravity_cwd) if arguments.antigravity_cwd else None,
            model=arguments.antigravity_model,
            effort=arguments.antigravity_effort,
            timeout_seconds=arguments.task_timeout,
        )
    else:
        provider = DeterministicProvider(
            fault=FaultMode(arguments.mock_fault),
            delay_seconds=arguments.mock_delay,
        )
    managed_codex_writes = (
        arguments.provider == "codex" and arguments.codex_write_base is not None
    )
    provider_registry: dict[str, ReasoningProvider] = {arguments.provider: provider}
    if arguments.provider != "deterministic":
        provider_registry["deterministic"] = DeterministicProvider()
    runtime = SoraRuntime(
        RuntimeConfig(
            root=arguments.root,
            identity_root=arguments.identity_root,
            task_timeout_seconds=arguments.task_timeout,
            coding_repository_root=(arguments.codex_cwd if managed_codex_writes else None),
            coding_workspace_root=(
                arguments.codex_workspace_root
                or arguments.root / ".local" / "coding-workspaces"
                if managed_codex_writes
                else None
            ),
            coding_base_ref=(arguments.codex_write_base if managed_codex_writes else None),
        ),
        providers=provider_registry,
    )
    await runtime.start()
    try:
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
        capabilities = await provider.capabilities()
        await interactive(runtime, capabilities.provider)
        return 0
    finally:
        await runtime.close()


async def interactive(runtime: SoraRuntime, provider_name: str) -> None:
    mode = (
        "offline deterministic mock"
        if provider_name == "deterministic-mock"
        else f"external provider {provider_name} (native tools enabled)"
    )
    print(f"SORA {__version__} — {mode}. Type /help for commands.")
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
