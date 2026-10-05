"""Serve an isolated, exact-scope content fixture for P15.7 manual Windows UI QA."""

from __future__ import annotations

import argparse
import asyncio
import secrets
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sora.api import ApiServerConfig, SoraApiServer
from sora.contracts.content import ContentHandlerConfig, ContentReference
from sora.contracts.models import (
    ApprovalRequest,
    ApprovalStatus,
    CapabilityGrant,
    CapabilityOperation,
    CapabilityRequest,
)
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_ID = "content:file:p15-7-qa"
GRANT_ID = "grant-p15-7-content"


async def serve(root: Path, port: int) -> None:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    content_root = root / "content"
    content_root.mkdir(exist_ok=True)
    target = content_root / "p15-7-example.txt"
    target.write_text("P15.7 exact content reference acceptance\n", encoding="utf-8")
    output = root / "handler-observation.json"
    handler = ContentHandlerConfig(
        handler_id="p15-7-fixture-handler",
        kinds=("file",),
        executable=Path(sys.executable).resolve(),
        arguments=(
            str(PROJECT_ROOT / "scripts/fixtures/full_app_content_handler.py"),
            str(output),
            "{path}",
            "{verb}",
            "{reference_id}",
        ),
        verbs=("open", "show", "where"),
        completion_timeout_seconds=2,
    )
    runtime = SoraRuntime(
        RuntimeConfig(
            root=root / "state",
            identity_root=PROJECT_ROOT / "identity",
            content_roots=(content_root,),
            content_handlers=(handler,),
        ),
        provider=DeterministicProvider(),
    )
    await runtime.start()
    server: SoraApiServer | None = None
    try:
        runtime.register_content_reference(
            ContentReference(
                reference_id=REFERENCE_ID,
                kind="file",
                label=target.name,
                owner_id=runtime.config.owner_id,
                device_id="device-local",
                project_id=runtime.config.project_id,
                path=target.resolve(),
                root=content_root.resolve(),
                created_at=datetime.now(UTC),
            )
        )
        now = datetime.now(UTC)
        capability = CapabilityRequest(
            request_id="request-p15-7-content",
            owner_id=runtime.config.owner_id,
            device_id="device-local",
            project_id=runtime.config.project_id,
            operation=CapabilityOperation.DESKTOP_NAVIGATE,
            resource=f"desktop.navigate:{REFERENCE_ID}",
        )
        approval = ApprovalRequest(
            approval_id="approval-p15-7-content",
            capability=capability,
            status=ApprovalStatus.APPROVED,
            created_at=now - timedelta(minutes=1),
            expires_at=now + timedelta(hours=1),
            decided_at=now - timedelta(seconds=30),
            decided_by="owner-local",
        )
        grant = CapabilityGrant(
            grant_id=GRANT_ID,
            owner_id=runtime.config.owner_id,
            device_id="device-local",
            project_id=runtime.config.project_id,
            operation=CapabilityOperation.DESKTOP_NAVIGATE,
            resource=f"desktop.navigate:{REFERENCE_ID}",
            issued_at=now - timedelta(seconds=30),
            not_before=now - timedelta(seconds=30),
            expires_at=now + timedelta(hours=1),
            approval_id=approval.approval_id,
        )
        await runtime.repository.save_approval(approval)
        await runtime.repository.save_grant(grant)
        token = secrets.token_urlsafe(32)
        (root / "token").write_text(token, encoding="utf-8")
        server = SoraApiServer(
            runtime,
            ApiServerConfig(host="127.0.0.1", port=port, auth_token=token),
        )
        await server.start()
        print(
            f"READY port={server.actual_port} reference={REFERENCE_ID} "
            f"grant={GRANT_ID} output={output}",
            flush=True,
        )
        await asyncio.Event().wait()
    finally:
        if server is not None:
            await server.close()
        await runtime.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18768)
    args = parser.parse_args()
    asyncio.run(serve(args.root, args.port))


if __name__ == "__main__":
    main()
