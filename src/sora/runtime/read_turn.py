"""Bounded, read-only companion orchestration; observations never become instructions."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from sora.contracts.companion_call import (
    CompanionCall,
    Delegate,
    FindMemory,
    ListAgents,
    Look,
    Move,
    Point,
    Pose,
    PresentMemory,
)
from sora.contracts.companion_read import (
    CompanionReadCall,
    CompanionReadResult,
    FinishRead,
    InspectWindow,
)
from sora.contracts.desktop import DesktopNode
from sora.desktop.targets import DesktopTargetError
from sora.providers.dialogue import (
    CompanionCallProvider,
    CompanionReadProvider,
    DialogueProviderError,
    DialogueTimeoutError,
)
from sora.runtime.delegation_catalogue import DelegationCatalogue
from sora.runtime.memory_references import MemoryReferences, MemoryTarget
from sora.runtime.read_tools import CompanionReadTools, desktop_directories


def bounded_observations(records: list[dict[str, Any]], budget: int) -> str:
    """Trim structured data, never slice serialized JSON halfway through a field."""
    copies = json.loads(json.dumps(records))
    while len(encoded := json.dumps(copies, ensure_ascii=False)) > budget:
        # Discard older context before clipping the fresh inspection that answers the task.
        older = [row for row in copies[:-1] if row.get("data")]
        biggest = older[0] if older else copies[-1]
        data = biggest.get("data", {})
        lists = [value for value in data.values() if isinstance(value, list) and value]
        if lists:
            max(lists, key=lambda value: len(json.dumps(value))).pop()
        elif any(
            isinstance(data.get(key), str) and len(data[key]) > 128
            for key in ("text", "selected_text")
        ):
            key = "selected_text" if len(str(data.get("selected_text", ""))) > 128 else "text"
            data[key] = data[key][: len(data[key]) // 2]
            if isinstance(data.get("offset"), int):
                data["next_offset"] = data["offset"] + len(data[key])
        elif data:
            biggest["data"] = {}
        else:
            # Only envelopes remain: retain the most recent results and disclose omission.
            copies.pop(0)
            if not copies:
                return '[{"status":"partial","reason":"Observation budget exhausted"}]'
        biggest["truncated"] = True
        if biggest.get("status") == "ok":
            biggest["status"] = "partial"
        biggest["context_clipped"] = True
    return encoded


@dataclass(frozen=True)
class ReadTurn:
    observations: str
    attempted: bool
    sources: tuple[str, ...]
    action: Delegate | Pose | Move | Look | Point | PresentMemory | None = None
    presentation_target: str | None = None
    action_error: str | None = None
    memory_target: MemoryTarget | None = None
    memory_supplied: tuple[str, ...] = ()
    move_window: DesktopNode | None = None


async def collect_reads(
    prompt: str,
    *,
    provider: CompanionReadProvider | CompanionCallProvider,
    tools: CompanionReadTools,
    check_epoch: Callable[[], None],
    file_read: bool,
    desktop_read: bool,
    timeout: float,
    budget: int,
    seed_windows: bool = False,
    seed_desktop: bool = True,
    catalogue: DelegationCatalogue | None = None,
    avatar_control: bool = False,
    native_presentation: bool = False,
    memory: MemoryReferences | None = None,
    memory_presentation: bool = False,
) -> ReadTurn:
    records: list[dict[str, Any]] = []
    sources: list[str] = []
    attempted = False
    seen: set[str] = set()
    repair_used = False
    action: Delegate | Pose | Move | Look | Point | PresentMemory | None = None
    memory_target: MemoryTarget | None = None
    presentation_target: str | None = None
    action_error: str | None = None
    move_window: DesktopNode | None = None
    operations = {"finish"}
    if file_read:
        operations.update({"list_files", "search_files", "read_file"})
    if desktop_read:
        operations.update({"list_windows", "inspect_window"})
    if catalogue is not None:
        operations.add("list_agents")
        if catalogue.rows:
            operations.add("delegate")
    if avatar_control:
        operations.update({"pose", "move"})
    if desktop_read and native_presentation:
        operations.update({"look", "point"})
    if memory is not None:
        operations.add("find_memory")
        records.append(
            {
                "operation": "memory_context",
                "source": "core",
                "status": "ok",
                "data": memory.preview(),
            }
        )
        if memory_presentation:
            operations.add("present_memory")
    # Capability facts are Core-owned; the model cannot switch settings on.
    capabilities = json.dumps({"file_read": file_read, "desktop_observe": desktop_read})
    if catalogue is not None:
        records.append(
            {
                "operation": "agent_defaults",
                "source": "core",
                "status": "ok",
                "data": catalogue.preview(),
            }
        )
    try:
        async with asyncio.timeout(timeout):
            if desktop_read and seed_windows:
                check_epoch()
                seed = CompanionReadCall.model_validate({"op": "list_windows"})
                result = await tools.execute(seed)
                check_epoch()
                records.append({"operation": "list_windows", **result.model_dump(mode="json")})
                seen.add(seed.model_dump_json())
                sources.append(
                    f"Window context: {result.source}, {result.status}, "
                    f"{result.observed_at.isoformat(timespec='seconds')}"
                )
            if file_read and seed_desktop:
                for path in await asyncio.to_thread(desktop_directories):
                    check_epoch()
                    result = await tools.execute(
                        CompanionReadCall.model_validate(
                            {
                                "op": "list_files",
                                "path": path,
                            }
                        )
                    )
                    entries = result.data.get("entries")
                    if isinstance(entries, list) and len(entries) > 10:
                        result = result.model_copy(
                            update={
                                "status": "partial",
                                "truncated": True,
                                "continuation": None,
                                "data": {
                                    **result.data,
                                    "entries": entries[:10],
                                    "note": "Desktop preview only; list_files for the full page",
                                },
                            }
                        )
                    records.append(
                        {
                            "operation": "desktop_metadata",
                            **result.model_dump(
                                mode="json",
                            ),
                        }
                    )
            for _ in range(6):
                check_epoch()
                try:
                    bounded = bounded_observations(records, budget)
                    tools.presentation_targets.expose(json.loads(bounded))
                    if memory is not None:
                        chooser_supplied = memory.expose(json.loads(bounded))
                        await memory.publish("chooser", chooser_supplied)
                        check_epoch()
                    observations = "Enabled read capabilities: " + capabilities + "\n" + bounded
                    if isinstance(provider, CompanionCallProvider):
                        call = CompanionCall.model_validate(
                            await provider.choose_call(
                                prompt,
                                observations,
                                frozenset(operations),
                            )
                        )
                        if call.root.op not in operations:
                            raise ValueError("Operation not enabled")
                    else:
                        legacy = await provider.choose_read(prompt, observations)
                        call = CompanionCall.model_validate(legacy.model_dump())
                except DialogueTimeoutError:
                    raise  # Transport timeouts are not malformed JSON to repair/retry.
                except (DialogueProviderError, ValidationError, ValueError):
                    attempted = True
                    records.append(
                        {
                            "source": "core",
                            "status": "unsupported",
                            "data": {
                                "reason": (
                                    "Invalid call; return one enabled valid call or finish"
                                    if isinstance(provider, CompanionCallProvider)
                                    else "Invalid read call; return one valid read call or finish"
                                ),
                            },
                        }
                    )
                    if repair_used:
                        break
                    repair_used = True
                    continue
                check_epoch()
                if isinstance(call.root, FinishRead):
                    break
                if isinstance(call.root, (Delegate, Pose, Move, Look, Point, PresentMemory)):
                    action = call.root
                    attempted = True
                    if isinstance(action, (Look, Point)):
                        try:
                            presentation_target = tools.presentation_targets.resolve(action.target)
                        except DesktopTargetError as exc:
                            action_error = str(exc)
                    if isinstance(action, Move) and action.window is not None:
                        stored = tools.windows.get(action.window)
                        if stored is None or time.monotonic() - stored[1] > 60:
                            action_error = (
                                "That window reference is not current; list windows again"
                            )
                        elif stored[0].rect is None or stored[0].offscreen:
                            action_error = "That window is minimized or has no position on screen"
                        else:
                            move_window = stored[0]
                    if isinstance(action, PresentMemory):
                        assert memory is not None
                        try:
                            memory_target = memory.resolve(action.target)
                        except ValueError as exc:
                            action_error = str(exc)
                    break  # Defer ONE effect to Core after final freshness/commit checks.
                attempted = True
                signature = call.model_dump_json()
                if signature in seen:
                    records.append(
                        {
                            "source": "core",
                            "status": "partial",
                            "data": {
                                "reason": "Repeated read stopped; use evidence already returned",
                            },
                        }
                    )
                    break
                seen.add(signature)
                if isinstance(call.root, FindMemory):
                    assert memory is not None
                    try:
                        data = await memory.find(call.root.query, call.root.cursor)
                        record = {
                            "operation": "find_memory",
                            "source": "core",
                            "status": "ok",
                            "data": data,
                        }
                    except ValueError as exc:
                        record = {
                            "operation": "find_memory",
                            "source": "core",
                            "status": "stale",
                            "data": {"reason": str(exc)},
                        }
                    check_epoch()
                    records.append(record)
                    continue
                if isinstance(call.root, ListAgents):
                    assert catalogue is not None
                    try:
                        data = catalogue.list_agents(call.root)
                        result = CompanionReadResult(
                            call_id=str(uuid4()),
                            source="core",
                            observed_at=datetime.now(UTC),
                            status="partial" if data["continuation"] else "ok",
                            data=data,
                            continuation=data["continuation"],
                        )
                    except ValueError as exc:
                        result = CompanionReadResult(
                            call_id=str(uuid4()),
                            source="core",
                            observed_at=datetime.now(UTC),
                            status="stale",
                            data={"reason": str(exc)},
                        )
                    check_epoch()
                    records.append({"operation": "list_agents", **result.model_dump(mode="json")})
                    continue
                result = await tools.execute(CompanionReadCall.model_validate(call.model_dump()))
                check_epoch()
                records.append({"operation": call.root.op, **result.model_dump(mode="json")})
                operation_label = call.root.op + (
                    f" ({call.root.view})" if isinstance(call.root, InspectWindow) else ""
                )
                sources.append(
                    f"{operation_label}: {result.source}, {result.status}, "
                    f"{result.observed_at.isoformat(timespec='seconds')}"
                )
            else:
                records.append(
                    {
                        "source": "core",
                        "status": "partial",
                        "data": {
                            "reason": "Six-step limit reached; search is not exhaustive",
                        },
                    }
                )
    except TimeoutError:
        attempted = True
        records.append(
            {
                "source": "core",
                "status": "timeout",
                "data": {
                    "reason": "Read deadline reached; only use observations already returned",
                },
            }
        )
        sources.append("Read loop: deadline reached; results may be incomplete")
    check_epoch()
    encoded = bounded_observations(records, budget)
    if any(row.get("context_clipped") for row in json.loads(encoded)):
        sources.append("Model context was shortened; the answer may omit observed items")
    supplied = tuple(memory.expose(json.loads(encoded))) if memory is not None else ()
    return ReadTurn(
        encoded,
        attempted,
        tuple(sources),
        action,
        presentation_target,
        action_error,
        memory_target,
        supplied,
        move_window,
    )
