from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sora.contracts.models import ProviderErrorCode, ProviderOutcome, ProviderRequest
from sora.providers.antigravity import AntigravityProvider, parse_antigravity_result
from sora.providers.base import MalformedProviderResult, ProviderLaunchError


def make_request(
    *,
    project_id: str | None = "project-sora",
    run_id: str = "run-ag-1",
) -> ProviderRequest:
    return ProviderRequest(
        request_id=f"request-{run_id}",
        task_id="task-ag-1",
        run_id=run_id,
        owner_id="owner-local",
        project_id=project_id,
        intent="Research architecture constraints",
        context="AUTHORITATIVE_STATE\nFACT: existing architecture",
        context_manifest_ref="context-ag-1",
        deadline=datetime.now(UTC) + timedelta(seconds=10),
        artifact_destination="C:/tmp/artifacts",
        idempotency_key=f"provider-start-{run_id}",
    )


def test_antigravity_wrapped_json_result_normalization() -> None:
    agy_stdout = (
        '{"conversation_id": "conv-12345", "status": "SUCCESS", '
        '"response": "{\\"conclusion\\": \\"Analysis complete\\", '
        '\\"facts\\": [\\"Rule verified\\"], \\"memory_updates\\": [\\"Keep this\\"]}", '
        '"usage": {"prompt_tokens": 100, "completion_tokens": 50}}'
    )
    result = parse_antigravity_result(agy_stdout, make_request())
    assert result.outcome is ProviderOutcome.COMPLETED
    assert result.conclusion == "Analysis complete"
    assert result.facts == ("Rule verified",)
    assert result.memory_updates == ("Keep this",)
    assert result.patch is not None
    assert len(result.patch.operations) == 2
    assert result.usage == {"prompt_tokens": 100, "completion_tokens": 50}


def test_antigravity_plain_text_normalization() -> None:
    text_stdout = "Here is the direct analysis from Antigravity without JSON formatting."
    result = parse_antigravity_result(text_stdout, make_request())
    assert result.outcome is ProviderOutcome.COMPLETED
    assert result.conclusion == text_stdout
    assert result.patch is None
    assert result.facts == ()


def test_antigravity_malformed_empty_result_raises() -> None:
    with pytest.raises(MalformedProviderResult):
        parse_antigravity_result("   ", make_request())


def test_antigravity_invalid_list_field_raises() -> None:
    bad_json = '{"conclusion": "done", "facts": "not-a-list"}'
    with pytest.raises(MalformedProviderResult):
        parse_antigravity_result(bad_json, make_request())


def test_antigravity_owner_only_scope() -> None:
    text = '{"conclusion": "done", "facts": ["owner fact"]}'
    result = parse_antigravity_result(text, make_request(project_id=None))
    assert result.patch is not None
    assert result.patch.scope == "owner-local"


@pytest.mark.asyncio
async def test_antigravity_capabilities() -> None:
    provider = AntigravityProvider()
    caps = await provider.capabilities()
    assert caps.provider == "antigravity"
    assert caps.sessions is True
    assert caps.resume is True
    assert caps.events is False
    assert caps.steer is False
    assert caps.cancel is True
    assert caps.display_name == "Antigravity"


@pytest.mark.asyncio
async def test_antigravity_steer_unsupported() -> None:
    provider = AntigravityProvider()
    with pytest.raises(NotImplementedError):
        await provider.steer("run-1", "instruction")


@pytest.mark.asyncio
async def test_missing_antigravity_executable_raises_unavailable(tmp_path: Path) -> None:
    provider = AntigravityProvider(command=str(tmp_path / "nonexistent-agy.exe"))
    with pytest.raises(ProviderLaunchError) as exc_info:
        await provider.start(make_request())
    assert exc_info.value.code is ProviderErrorCode.UNAVAILABLE


@pytest.mark.asyncio
async def test_antigravity_execution_lifecycle_with_fake_script(tmp_path: Path) -> None:
    fake_cli = tmp_path / "fake_agy.py"
    fake_cli.write_text(
        "import json, sys\n"
        "args = sys.argv[1:]\n"
        "conv_id = 'conv-resume-999' if '--continue' in args else 'conv-native-42'\n"
        "out = {\n"
        "    'conversation_id': conv_id,\n"
        "    'status': 'SUCCESS',\n"
        "    'response': '{\\\"conclusion\\\": \\\"Research verified\\\", "
        "\\\"facts\\\": [\\\"Discovered fact\\\"]}',\n"
        "    'usage': {'tokens': 42}\n"
        "}\n"
        "print(json.dumps(out))\n",
        encoding="utf-8",
    )

    provider = AntigravityProvider(
        command=sys.executable,
        args=(str(fake_cli),),
        timeout_seconds=5.0,
    )
    req = make_request(run_id="ag-run-test-1")

    # Verify launch, status, session_id, and result
    run_id = await provider.start(req)
    assert run_id == "ag-run-test-1"
    # Idempotent start returns same run_id
    assert await provider.start(req) == run_id

    result = await provider.result(run_id)
    assert result.outcome is ProviderOutcome.COMPLETED
    assert result.conclusion == "Research verified"
    assert result.facts == ("Discovered fact",)

    # Native session ID captured
    native_id = await provider.session_id(run_id)
    assert native_id == "conv-native-42"

    # Now test resume
    resume_req = make_request(run_id="ag-run-resume-1")
    resume_run_id = await provider.resume(native_id or "conv-native-42", resume_req)
    resume_result = await provider.result(resume_run_id)
    assert resume_result.conclusion == "Research verified"
    assert await provider.session_id(resume_run_id) == "conv-resume-999"


@pytest.mark.asyncio
async def test_antigravity_timeout_handling(tmp_path: Path) -> None:
    hanging_script = tmp_path / "hang_agy.py"
    hanging_script.write_text(
        "import time; time.sleep(10)\n",
        encoding="utf-8",
    )
    provider = AntigravityProvider(
        command=sys.executable,
        args=(str(hanging_script),),
        timeout_seconds=0.3,
    )
    req = make_request(run_id="hang-run")
    await provider.start(req)
    with pytest.raises(ProviderLaunchError) as exc_info:
        await provider.result("hang-run")
    assert exc_info.value.code is ProviderErrorCode.TIMED_OUT


@pytest.mark.asyncio
async def test_antigravity_cancel_handling(tmp_path: Path) -> None:
    hanging_script = tmp_path / "hang_agy_cancel.py"
    hanging_script.write_text(
        "import time; time.sleep(10)\n",
        encoding="utf-8",
    )
    provider = AntigravityProvider(
        command=sys.executable,
        args=(str(hanging_script),),
        timeout_seconds=5.0,
    )
    req = make_request(run_id="cancel-run")
    await provider.start(req)
    await asyncio.sleep(0.05)
    await provider.cancel("cancel-run")
    assert await provider.status("cancel-run") == "cancelled"
    with pytest.raises(ProviderLaunchError):
        await provider.result("cancel-run")
