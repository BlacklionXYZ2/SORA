from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sora.contracts.models import ProviderErrorCode, ProviderOutcome, ProviderRequest
from sora.providers.base import MalformedProviderResult, ProviderLaunchError
from sora.providers.claude_code import ClaudeCodeProvider, parse_claude_result


def make_request(*, run_id: str = "run-claude-1", **extra: object) -> ProviderRequest:
    return ProviderRequest.model_validate({
        "request_id": f"request-{run_id}",
        "task_id": "task-claude-1",
        "run_id": run_id,
        "owner_id": "owner-local",
        "project_id": "project-sora",
        "intent": "Explain the cache module",
        "context": "AUTHORITATIVE_STATE\nFACT: the cache is write-through",
        "context_manifest_ref": "context-claude-1",
        "deadline": datetime.now(UTC) + timedelta(seconds=10),
        "artifact_destination": "C:/tmp/artifacts",
        "idempotency_key": f"provider-start-{run_id}",
        **extra,
    })


def wrapper(result: str, **extra: object) -> str:
    return json.dumps({
        "type": "result", "subtype": "success", "is_error": False, "result": result,
        "session_id": "session-abc", "usage": {"input_tokens": 10, "output_tokens": 5},
        **extra,
    })


# A stand-in for `claude -p --output-format json`: echoes its argv and stdin back in the answer.
FAKE_CLAUDE = """
import json, sys
argv = sys.argv[1:]
prompt = sys.stdin.read()
session = argv[argv.index('--resume') + 1] + '-continued' if '--resume' in argv else 'session-42'
answer = {'conclusion': 'Read the module', 'facts': ['It is write-through'],
          'files_read': ['cache.py']}
print(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False,
                  'result': 'Done.\\n' + json.dumps(answer), 'session_id': session,
                  'argv': argv, 'prompt_seen': 'TASK_INTENT' in prompt}))
"""


def test_plain_text_result_is_the_conclusion() -> None:
    result = parse_claude_result(wrapper("The cache is fine."), make_request())
    assert result.outcome is ProviderOutcome.COMPLETED
    assert result.conclusion == "The cache is fine."
    assert result.patch is None
    assert result.usage == {"input_tokens": 10, "output_tokens": 5}


def test_structured_answer_after_prose_is_normalised() -> None:
    text = ("I looked.\n```json\n" + json.dumps({
        "conclusion": "Write-through is right", "facts": ["Fact one"],
        "memory_updates": ["Owner prefers simple caches"], "files_changed": [],
        "changelog_path": "changelog/x.md",
    }) + "\n```")
    result = parse_claude_result(wrapper(text), make_request())
    assert result.conclusion == "Write-through is right"
    assert result.facts == ("Fact one",)
    assert result.memory_updates == ("Owner prefers simple caches",)
    assert result.changelog_path == "changelog/x.md"
    assert result.patch is not None and len(result.patch.operations) == 2
    assert result.patch.provenance == "Claude Code normalized result"


@pytest.mark.parametrize("stdout", [
    "not json", json.dumps({"type": "system"}), wrapper("   "),
    wrapper('{"conclusion": "x", "facts": "not a list"}'),
])
def test_malformed_output_is_rejected(stdout: str) -> None:
    with pytest.raises(MalformedProviderResult):
        parse_claude_result(stdout, make_request())


def test_command_line_adds_no_permission_flags_and_maps_model_and_resume() -> None:
    provider = ClaudeCodeProvider(command="claude-not-installed", model="sonnet")
    line = provider.command_line(make_request(), resume_session_id="session-9")
    assert line[1:] == ["-p", "--output-format", "json", "--model", "sonnet",
                        "--resume", "session-9"]
    assert not any("permission" in item for item in line)
    owner = ClaudeCodeProvider(command="claude-not-installed",
                               args=("--permission-mode", "acceptEdits"))
    assert owner.command_line(make_request(model="opus"))[1:] == [
        "--permission-mode", "acceptEdits", "-p", "--output-format", "json", "--model", "opus",
    ]
    with pytest.raises(ProviderLaunchError) as raised:
        provider.command_line(make_request(reasoning_effort="high"))
    assert raised.value.code is ProviderErrorCode.UNSUPPORTED


@pytest.mark.asyncio
async def test_capabilities() -> None:
    caps = await ClaudeCodeProvider().capabilities()
    assert caps.provider == "claude-code" and caps.resume and caps.cancel and not caps.steer


@pytest.mark.asyncio
async def test_missing_executable_is_unavailable(tmp_path: Path) -> None:
    provider = ClaudeCodeProvider(command=str(tmp_path / "no-claude"))
    with pytest.raises(ProviderLaunchError) as raised:
        await provider.start(make_request())
    assert raised.value.code is ProviderErrorCode.UNAVAILABLE


@pytest.mark.asyncio
async def test_lifecycle_prompt_on_stdin_session_and_resume(tmp_path: Path) -> None:
    script = tmp_path / "fake_claude.py"
    script.write_text(FAKE_CLAUDE, encoding="utf-8")
    provider = ClaudeCodeProvider(command=sys.executable, args=(str(script),),
                                  cwd=str(tmp_path), timeout_seconds=10)
    run_id = await provider.start(make_request())
    assert await provider.start(make_request()) == run_id  # idempotent
    result = await provider.result(run_id)
    assert result.conclusion == "Read the module"
    assert result.files_read == ("cache.py",)
    native = await provider.session_id(run_id)
    assert native == "session-42"

    resumed = await provider.resume(native, make_request(run_id="run-claude-2"))
    assert (await provider.result(resumed)).conclusion == "Read the module"
    assert await provider.session_id(resumed) == "session-42-continued"


@pytest.mark.asyncio
async def test_cli_error_result_is_reported_not_parsed(tmp_path: Path) -> None:
    script = tmp_path / "error_claude.py"
    script.write_text(
        "import json, sys\nsys.stdin.read()\n"
        "print(json.dumps({'type': 'result', 'subtype': 'error_max_turns', 'is_error': True,"
        " 'session_id': 's-err'}))\n",
        encoding="utf-8",
    )
    provider = ClaudeCodeProvider(command=sys.executable, args=(str(script),), timeout_seconds=10)
    await provider.start(make_request())
    with pytest.raises(ProviderLaunchError) as raised:
        await provider.result("run-claude-1")
    assert raised.value.code is ProviderErrorCode.INTERNAL
    assert "error_max_turns" in str(raised.value)


@pytest.mark.asyncio
async def test_timeout_and_cancel(tmp_path: Path) -> None:
    script = tmp_path / "hang_claude.py"
    script.write_text("import time; time.sleep(10)\n", encoding="utf-8")
    slow = ClaudeCodeProvider(command=sys.executable, args=(str(script),), timeout_seconds=0.3)
    await slow.start(make_request(run_id="run-hang"))
    with pytest.raises(ProviderLaunchError) as raised:
        await slow.result("run-hang")
    assert raised.value.code is ProviderErrorCode.TIMED_OUT

    provider = ClaudeCodeProvider(command=sys.executable, args=(str(script),), timeout_seconds=10)
    await provider.start(make_request(run_id="run-cancel"))
    await asyncio.sleep(0.05)
    await provider.cancel("run-cancel")
    assert await provider.status("run-cancel") == "cancelled"
    with pytest.raises(ProviderLaunchError):
        await provider.result("run-cancel")


def test_auto_registry_adds_claude_only_when_installed(tmp_path: Path) -> None:
    import sora.__main__ as cli

    missing = cli.parser().parse_args([
        "--root", str(tmp_path), "--claude-command", str(tmp_path / "no-claude"),
        "--hermes-command", "no-hermes", "--codex-command", "no-codex",
        "--antigravity-command", "no-agy",
    ])
    plan = cli.build_provider_registry(missing)
    assert "claude" not in plan.registry
    assert any(item.startswith("claude:") for item in plan.skipped)

    installed = cli.parser().parse_args([
        "--root", str(tmp_path), "--claude-command", sys.executable,
        "--claude-model", "sonnet", "--hermes-command", "no-hermes",
        "--codex-command", "no-codex", "--antigravity-command", "no-agy",
    ])
    provider = cli.build_provider_registry(installed).registry["claude"]
    assert isinstance(provider, ClaudeCodeProvider)
    assert provider.model == "sonnet" and provider.args == ()
    assert provider.cwd == str((tmp_path / "workspace").resolve())


def test_router_sends_private_context_to_claude_when_named() -> None:
    from sora.routing.router import RoutingEngine

    engine = RoutingEngine(registered_providers={"claude", "deterministic"})
    assert "claude" in engine.cloud_providers
    decision = engine.route("Explain this", explicit_provider="claude", is_local_only=True)
    assert decision.selected_provider == "claude"
    assert decision.metadata["private_context"] is True
