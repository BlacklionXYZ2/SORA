from __future__ import annotations

import asyncio
from pathlib import Path

from sora.contracts.models import TaskStatus
from sora.providers.mock import DeterministicProvider, FaultMode
from sora.runtime.service import RuntimeConfig, SoraRuntime

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


def make_runtime(
    root: Path,
    *,
    fault: FaultMode = FaultMode.NONE,
    delay: float = 0,
    supports_steer: bool = True,
    timeout: float = 1,
    workers: int = 2,
    queue_capacity: int = 100,
    max_attempts: int = 3,
    secrets: tuple[str, ...] = (),
) -> tuple[SoraRuntime, DeterministicProvider]:
    provider = DeterministicProvider(
        fault=fault,
        delay_seconds=delay,
        supports_steer=supports_steer,
    )
    runtime = SoraRuntime(
        RuntimeConfig(
            root=root,
            identity_root=IDENTITY_ROOT,
            worker_count=workers,
            queue_capacity=queue_capacity,
            task_timeout_seconds=timeout,
            lease_seconds=0.2,
            max_attempts=max_attempts,
            secrets=secrets,
        ),
        provider,
    )
    return runtime, provider


async def wait_for_status(
    runtime: SoraRuntime,
    task_id: str,
    status: TaskStatus,
    *,
    timeout: float = 1,
) -> None:
    async with asyncio.timeout(timeout):
        while True:
            task = await runtime.runtime_repository.get_task(task_id)
            if task is not None and task.status is status:
                return
            await asyncio.sleep(0.005)
