from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sora.operations.install import (
    InstallOperationError,
    install_bundle,
    rollback_install,
    uninstall_install,
    update_bundle,
)
from sora.operations.release import (
    ReleaseVerificationError,
    build_release_manifest,
    verify_release_manifest,
)
from sora.operations.state import verify_state
from sora.persistence.database import SQLiteDatabase
from sora.persistence.records import MessageRecord
from sora.persistence.repository import SoraRepository

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


def make_bundle(root: Path, release_id: str) -> Path:
    bundle = root / release_id
    python = bundle / "payload/core/python/python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"portable-python-fixture")
    identity = bundle / "payload/resources/identity"
    shutil.copytree(IDENTITY_ROOT, identity)
    for script in ("install.ps1", "update.ps1", "rollback.ps1", "uninstall.ps1"):
        (bundle / script).write_text(f"# {script} fixture\n", encoding="utf-8")
    metadata = {"fixture": True, "personal_data": "separate"}
    (bundle / "release-metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    build_release_manifest(
        bundle,
        release_id=release_id,
        app_version="test",
        metadata=metadata,
        created_at=datetime(2026, 9, 22, tzinfo=UTC),
    )
    return bundle


def active_slot(install_root: Path, state_root: Path) -> Path:
    current = json.loads((install_root / "current.json").read_text(encoding="utf-8"))
    return state_root / "slots" / str(current["state_slot"])


def test_release_manifest_rejects_tamper_extra_files_and_unsafe_paths(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path, "release-a")
    verified = verify_release_manifest(bundle)
    assert verified["release_id"] == "release-a"

    extra = bundle / "unexpected.txt"
    extra.write_text("not in manifest", encoding="utf-8")
    with pytest.raises(ReleaseVerificationError, match="file set mismatch"):
        verify_release_manifest(bundle)
    extra.unlink()

    python = bundle / "payload/core/python/python.exe"
    python.write_bytes(b"tampered")
    with pytest.raises(ReleaseVerificationError, match="size mismatch|hash mismatch"):
        verify_release_manifest(bundle)

    with pytest.raises(ReleaseVerificationError, match="release_id"):
        build_release_manifest(
            bundle,
            release_id="../unsafe",
            app_version="test",
            metadata={},
        )


@pytest.mark.asyncio
async def test_install_upgrade_rollback_uninstall_and_reinstall_preserve_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle_a = make_bundle(tmp_path / "bundles", "release-a")
    bundle_b = make_bundle(tmp_path / "bundles", "release-b")
    install_root = tmp_path / "profile/app"
    state_root = tmp_path / "profile/state"
    startup = tmp_path / "profile/startup/SORA.cmd"

    installed = await install_bundle(
        bundle_a,
        install_root=install_root,
        state_root=state_root,
        startup_entry=startup,
        enable_startup=True,
    )
    assert installed["current"]["release_id"] == "release-a"
    assert startup.is_file()
    widget_launcher = (install_root / "bin/sora-widget.ps1").read_text(encoding="utf-8")
    assert "clients/widget/SoraWidget.exe" in widget_launcher
    assert str(state_root / "private/sora-api-token") not in widget_launcher
    assert '"private/sora-api-token"' in widget_launcher
    assert '"widget/settings.json"' in widget_launcher
    desktop_launcher = (install_root / "bin/sora-desktop.ps1").read_text(encoding="utf-8")
    assert "clients/desktop/SoraDesktop.exe" in desktop_launcher
    assert str(state_root / "private/sora-api-token") not in desktop_launcher
    assert '"private/sora-api-token"' in desktop_launcher
    assert '"desktop/settings.json"' in desktop_launcher

    first_slot = active_slot(install_root, state_root)
    repository = SoraRepository(SQLiteDatabase(first_slot / "data/sora.db"))
    await repository.append_message(
        MessageRecord(
            message_id="message-p15-upgrade",
            conversation_id="conversation-main",
            owner_id="owner-local",
            project_id="project-sora",
            role="user",
            content="state-preserving upgrade sentinel",
            provenance="P15.3 acceptance fixture",
            created_at=datetime(2026, 9, 22, 12, 0, tzinfo=UTC),
        )
    )

    def fake_new_runtime(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        command = args[0]
        assert isinstance(command, list)
        staged_root = Path(command[command.index("--root") + 1])
        result = json.dumps({"database": str(staged_root / "data/sora.db"), "quick_check": "ok"})
        return subprocess.CompletedProcess(command, 0, stdout=result, stderr="")

    monkeypatch.setattr("sora.operations.install.subprocess.run", fake_new_runtime)
    updated = await update_bundle(
        bundle_b,
        install_root=install_root,
        state_root=state_root,
        startup_entry=startup,
    )
    assert updated["current"]["release_id"] == "release-b"
    upgraded_slot = active_slot(install_root, state_root)
    upgraded_repository = SoraRepository(SQLiteDatabase(upgraded_slot / "data/sora.db"))
    upgraded_messages = await upgraded_repository.list_messages("conversation-main")
    assert [item.content for item in upgraded_messages] == ["state-preserving upgrade sentinel"]
    assert list((state_root / "backups").glob("pre-upgrade-*"))

    rolled_back = await rollback_install(
        install_root=install_root,
        state_root=state_root,
        startup_entry=startup,
    )
    assert rolled_back["current"]["release_id"] == "release-a"
    assert active_slot(install_root, state_root) == first_slot

    uninstalled = uninstall_install(
        install_root=install_root,
        state_root=state_root,
        startup_entry=startup,
    )
    assert uninstalled["personal_data_retained"] is True
    assert not install_root.exists()
    assert state_root.is_dir()
    assert not startup.exists()

    reinstalled = await install_bundle(
        bundle_b,
        install_root=install_root,
        state_root=state_root,
    )
    assert reinstalled["current"]["release_id"] == "release-b"
    recovered_slot = active_slot(install_root, state_root)
    recovered_repository = SoraRepository(SQLiteDatabase(recovered_slot / "data/sora.db"))
    recovered_messages = await recovered_repository.list_messages("conversation-main")
    assert [item.content for item in recovered_messages] == ["state-preserving upgrade sentinel"]
    assert (await verify_state(recovered_slot))["quick_check"] == "ok"


@pytest.mark.asyncio
async def test_failed_upgrade_never_switches_current_pointer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle_a = make_bundle(tmp_path / "bundles", "release-a")
    bundle_b = make_bundle(tmp_path / "bundles", "release-b")
    install_root = tmp_path / "app"
    state_root = tmp_path / "state"
    await install_bundle(bundle_a, install_root=install_root, state_root=state_root)
    before = (install_root / "current.json").read_bytes()

    def fail_new_runtime(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 1, stdout="", stderr="migration rejected")

    monkeypatch.setattr("sora.operations.install.subprocess.run", fail_new_runtime)
    with pytest.raises(InstallOperationError, match="rejected the staged state"):
        await update_bundle(bundle_b, install_root=install_root, state_root=state_root)
    assert (install_root / "current.json").read_bytes() == before


@pytest.mark.asyncio
async def test_uninstall_purge_requires_exact_managed_state_marker(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path / "bundles", "release-a")
    install_root = tmp_path / "app"
    state_root = tmp_path / "state"
    await install_bundle(bundle, install_root=install_root, state_root=state_root)
    marker = json.loads((state_root / ".sora-state.json").read_text(encoding="utf-8"))
    marker["state_root"] = str(tmp_path / "wrong")
    (state_root / ".sora-state.json").write_text(json.dumps(marker), encoding="utf-8")

    with pytest.raises(InstallOperationError, match="state marker"):
        uninstall_install(
            install_root=install_root,
            state_root=state_root,
            purge_data=True,
        )
    assert state_root.exists()
