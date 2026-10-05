"""Side-by-side Windows install, state-slot upgrade, rollback, and uninstall."""

# ruff: noqa: E501 -- generated PowerShell templates remain readable as complete commands.

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .release import verify_release_manifest
from .state import backup_state, initialize_state, restore_state, verify_state, write_state_marker

CURRENT_FILE = "current.json"
HISTORY_FILE = "history.json"
INSTALL_MARKER = ".sora-install.json"


class InstallOperationError(RuntimeError):
    """A safe, user-facing release operation failure."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _safe_managed_root(path: Path, *, name: str) -> Path:
    resolved = path.resolve()
    if resolved == Path(resolved.anchor) or resolved == Path.home().resolve():
        raise InstallOperationError(f"{name} cannot be a drive root or the user profile")
    if resolved.exists() and not resolved.is_dir():
        raise InstallOperationError(f"{name} is not a directory: {resolved}")
    return resolved


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallOperationError(f"managed metadata is missing or invalid: {path}") from exc
    if not isinstance(value, dict):
        raise InstallOperationError(f"managed metadata is invalid: {path}")
    return value


def _assert_install_marker(install_root: Path, state_root: Path | None = None) -> dict[str, Any]:
    marker = _read_json(install_root / INSTALL_MARKER)
    if Path(str(marker.get("install_root", ""))).resolve() != install_root:
        raise InstallOperationError("install marker does not match the requested install root")
    if state_root is not None and Path(str(marker.get("state_root", ""))).resolve() != state_root:
        raise InstallOperationError("install marker does not match the requested state root")
    return marker


def _copy_release_payload(bundle: Path, install_root: Path, release_id: str) -> Path:
    destination = install_root / "versions" / release_id
    if destination.exists():
        raise InstallOperationError(f"release is already installed: {release_id}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging_root = install_root / ".staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    staging = staging_root / f"{release_id}-{uuid.uuid4().hex}"
    try:
        shutil.copytree(bundle / "payload", staging, symlinks=False)
        last_error: OSError | None = None
        for attempt in range(30):
            try:
                os.replace(staging, destination)
                last_error = None
                break
            except PermissionError as exc:
                last_error = exc
                time.sleep(min(0.1 * (attempt + 1), 1.0))
        if last_error is not None:
            raise InstallOperationError(
                "Windows did not release the staged payload for atomic promotion"
            ) from last_error
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return destination


def _pointer_paths(install_root: Path, state_root: Path, pointer: dict[str, Any]) -> tuple[Path, Path]:
    release_id = str(pointer.get("release_id", ""))
    state_slot = str(pointer.get("state_slot", ""))
    if not release_id or not state_slot or "/" in release_id or "\\" in release_id:
        raise InstallOperationError("current install pointer is invalid")
    return install_root / "versions" / release_id, state_root / "slots" / state_slot


def _write_launchers(install_root: Path, state_root: Path) -> None:
    bin_root = install_root / "bin"
    bin_root.mkdir(parents=True, exist_ok=True)
    launch = f'''[CmdletBinding()]
param([Parameter(ValueFromRemainingArguments=$true)][string[]]$SoraArguments)
$ErrorActionPreference = "Stop"
$installRoot = "{install_root}"
$stateRoot = "{state_root}"
$current = Get-Content -Raw -LiteralPath (Join-Path $installRoot "{CURRENT_FILE}") | ConvertFrom-Json
$versionRoot = Join-Path (Join-Path $installRoot "versions") $current.release_id
$slotRoot = Join-Path (Join-Path $stateRoot "slots") $current.state_slot
$python = Join-Path $versionRoot "core/python/python.exe"
$base = @("-m", "sora", "--root", $slotRoot, "--identity-root", (Join-Path $versionRoot "resources/identity"))
$helpers = @{{
  "--windows-bridge" = "helpers/windows_bridge/windows_bridge.exe"
  "--windows-action" = "helpers/windows_action/windows_action.exe"
  "--windows-type" = "helpers/windows_type/windows_type.exe"
  "--windows-capture" = "helpers/windows_capture/windows_capture.exe"
}}
foreach ($entry in $helpers.GetEnumerator()) {{
  $helper = Join-Path $versionRoot $entry.Value
  if (Test-Path -LiteralPath $helper) {{ $base += @($entry.Key, $helper) }}
}}
& $python -B @base @SoraArguments
exit $LASTEXITCODE
'''
    (bin_root / "sora.ps1").write_text(launch, encoding="utf-8")
    widget = f'''[CmdletBinding()]
param()
$ErrorActionPreference = "Stop"
$installRoot = "{install_root}"
$stateRoot = "{state_root}"
$current = Get-Content -Raw -LiteralPath (Join-Path $installRoot "{CURRENT_FILE}") | ConvertFrom-Json
$versionRoot = Join-Path (Join-Path $installRoot "versions") $current.release_id
$executable = Join-Path $versionRoot "clients/widget/SoraWidget.exe"
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {{
  throw "This SORA release does not include the desktop widget."
}}
$tokenFile = Join-Path $stateRoot "private/sora-api-token"
$settingsFile = Join-Path $stateRoot "widget/settings.json"
& $executable --token-file $tokenFile --core-url http://127.0.0.1:8765 --settings-file $settingsFile
exit $LASTEXITCODE
'''
    (bin_root / "sora-widget.ps1").write_text(widget, encoding="utf-8")
    desktop = f'''[CmdletBinding()]
param()
$ErrorActionPreference = "Stop"
$installRoot = "{install_root}"
$stateRoot = "{state_root}"
$current = Get-Content -Raw -LiteralPath (Join-Path $installRoot "{CURRENT_FILE}") | ConvertFrom-Json
$versionRoot = Join-Path (Join-Path $installRoot "versions") $current.release_id
$executable = Join-Path $versionRoot "clients/desktop/SoraDesktop.exe"
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {{
  throw "This SORA release does not include the full desktop application."
}}
$tokenFile = Join-Path $stateRoot "private/sora-api-token"
$settingsFile = Join-Path $stateRoot "desktop/settings.json"
& $executable --token-file $tokenFile --core-url http://127.0.0.1:8765 --settings-file $settingsFile
exit $LASTEXITCODE
'''
    (bin_root / "sora-desktop.ps1").write_text(desktop, encoding="utf-8")
    ops = f'''[CmdletBinding()]
param([Parameter(ValueFromRemainingArguments=$true)][string[]]$OperationsArguments)
$ErrorActionPreference = "Stop"
$installRoot = "{install_root}"
$current = Get-Content -Raw -LiteralPath (Join-Path $installRoot "{CURRENT_FILE}") | ConvertFrom-Json
$python = Join-Path (Join-Path (Join-Path $installRoot "versions") $current.release_id) "core/python/python.exe"
& $python -B -m sora.operations.cli @OperationsArguments
exit $LASTEXITCODE
'''
    (bin_root / "sora-ops.ps1").write_text(ops, encoding="utf-8")
    uninstall = f'''[CmdletBinding()]
param([switch]$PurgeData)
$ErrorActionPreference = "Stop"
$installRoot = "{install_root}"
$stateRoot = "{state_root}"
$current = Get-Content -Raw -LiteralPath (Join-Path $installRoot "{CURRENT_FILE}") | ConvertFrom-Json
$sourcePython = Join-Path (Join-Path (Join-Path $installRoot "versions") $current.release_id) "core/python"
$temporary = Join-Path ([System.IO.Path]::GetTempPath()) ("sora-uninstall-" + [guid]::NewGuid())
Copy-Item -LiteralPath $sourcePython -Destination $temporary -Recurse
$python = Join-Path $temporary "python.exe"
$arguments = @("-m", "sora.operations.cli", "uninstall", "--install-root", $installRoot, "--state-root", $stateRoot)
if ($PurgeData) {{ $arguments += "--purge-data" }}
& $python -B @arguments
$exitCode = $LASTEXITCODE
Remove-Item -LiteralPath $temporary -Recurse -Force
exit $exitCode
'''
    (bin_root / "uninstall.ps1").write_text(uninstall, encoding="utf-8")


def _startup_contents(install_root: Path, state_root: Path) -> str:
    launcher = install_root / "bin" / "sora.ps1"
    token_file = state_root / "private" / "sora-api-token"
    return (
        "@echo off\n"
        f'start "" /min powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass '
        f'-File "{launcher}" --serve --api-token-file "{token_file}"\n'
    )


def _configure_startup(
    startup_entry: Path | None, install_root: Path, state_root: Path, *, enabled: bool
) -> None:
    if startup_entry is None:
        return
    if enabled:
        startup_entry.parent.mkdir(parents=True, exist_ok=True)
        startup_entry.write_text(_startup_contents(install_root, state_root), encoding="utf-8")
    elif startup_entry.exists():
        expected = _startup_contents(install_root, state_root)
        if startup_entry.read_text(encoding="utf-8") == expected:
            startup_entry.unlink()


async def install_bundle(
    bundle: Path,
    *,
    install_root: Path,
    state_root: Path,
    startup_entry: Path | None = None,
    enable_startup: bool = False,
) -> dict[str, Any]:
    source = bundle.resolve(strict=True)
    install = _safe_managed_root(install_root, name="install_root")
    state = _safe_managed_root(state_root, name="state_root")
    if (install / CURRENT_FILE).exists() or (install / INSTALL_MARKER).exists():
        raise InstallOperationError("SORA is already installed; use update")
    if install.exists() and any(install.iterdir()):
        raise InstallOperationError("install_root must be missing or empty")
    retained_pointer: dict[str, Any] | None = None
    if state.exists() and any(state.iterdir()):
        state_marker = _read_json(state / ".sora-state.json")
        if Path(str(state_marker.get("state_root", ""))).resolve() != state:
            raise InstallOperationError("existing state marker does not match state_root")
        last_install = state / "last-install.json"
        if not last_install.is_file():
            raise InstallOperationError("existing managed state has no retained install pointer")
        retained_pointer = _read_json(last_install)
    manifest = verify_release_manifest(source)
    release_id = str(manifest["release_id"])
    install.mkdir(parents=True, exist_ok=True)
    state.mkdir(parents=True, exist_ok=True)
    version_root = _copy_release_payload(source, install, release_id)
    slot_id = f"state-{uuid.uuid4().hex}"
    slot_root = state / "slots" / slot_id
    try:
        if retained_pointer is None:
            initialized = await initialize_state(
                slot_root, identity_root=version_root / "resources" / "identity"
            )
        else:
            _, retained_slot = _pointer_paths(install, state, retained_pointer)
            # The retained version may have been uninstalled; only its state slot is required.
            retained_slot = state / "slots" / str(retained_pointer.get("state_slot", ""))
            if not retained_slot.is_dir():
                raise InstallOperationError("retained state slot is missing")
            backup_id = f"pre-reinstall-{uuid.uuid4().hex[:12]}"
            backup_root = state / "backups" / backup_id
            await backup_state(retained_slot, backup_root)
            initialized = await restore_state(backup_root, slot_root)
        pointer = {
            "schema_version": 1,
            "release_id": release_id,
            "state_slot": slot_id,
            "activated_at": _now(),
        }
        _atomic_json(install / CURRENT_FILE, pointer)
        _atomic_json(install / HISTORY_FILE, {"schema_version": 1, "entries": []})
        _atomic_json(
            install / INSTALL_MARKER,
            {
                "schema_version": 1,
                "install_root": str(install),
                "state_root": str(state),
                "created_at": _now(),
            },
        )
        write_state_marker(state, install)
        last_install = state / "last-install.json"
        if last_install.exists():
            last_install.unlink()
        (state / "private").mkdir(parents=True, exist_ok=True)
        _write_launchers(install, state)
        _configure_startup(startup_entry, install, state, enabled=enable_startup)
    except Exception:
        if not (install / CURRENT_FILE).exists() and version_root.exists():
            shutil.rmtree(version_root)
        raise
    return {"operation": "install", "current": pointer, "state": initialized}


async def update_bundle(
    bundle: Path,
    *,
    install_root: Path,
    state_root: Path,
    startup_entry: Path | None = None,
) -> dict[str, Any]:
    source = bundle.resolve(strict=True)
    install = _safe_managed_root(install_root, name="install_root")
    state = _safe_managed_root(state_root, name="state_root")
    _assert_install_marker(install, state)
    current = _read_json(install / CURRENT_FILE)
    current_version, current_slot = _pointer_paths(install, state, current)
    if not current_version.is_dir() or not current_slot.is_dir():
        raise InstallOperationError("current release or state slot is missing")
    manifest = verify_release_manifest(source)
    release_id = str(manifest["release_id"])
    if release_id == current.get("release_id"):
        raise InstallOperationError("the requested release is already active")
    version_root = _copy_release_payload(source, install, release_id)
    backup_id = f"pre-upgrade-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    backup_root = state / "backups" / backup_id
    slot_id = f"state-{uuid.uuid4().hex}"
    slot_root = state / "slots" / slot_id
    try:
        await backup_state(current_slot, backup_root)
        restored = await restore_state(backup_root, slot_root)
        # Run verification with the new bundled runtime, proving its imports and migration path.
        new_python = version_root / "core" / "python" / "python.exe"
        completed = subprocess.run(
            [
                str(new_python),
                "-B",
                "-m",
                "sora.operations.cli",
                "verify-state",
                "--root",
                str(slot_root),
                "--migrate",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if completed.returncode != 0:
            raise InstallOperationError(
                f"new release rejected the staged state: {completed.stderr.strip()}"
            )
        new_runtime_verification = json.loads(completed.stdout)
        history = _read_json(install / HISTORY_FILE)
        entries = history.get("entries")
        if not isinstance(entries, list):
            raise InstallOperationError("install history is invalid")
        entries.append(current)
        pointer = {
            "schema_version": 1,
            "release_id": release_id,
            "state_slot": slot_id,
            "activated_at": _now(),
            "backup": backup_id,
        }
        _atomic_json(install / HISTORY_FILE, {"schema_version": 1, "entries": entries})
        _atomic_json(install / CURRENT_FILE, pointer)
        _write_launchers(install, state)
        if startup_entry is not None and startup_entry.exists():
            _configure_startup(startup_entry, install, state, enabled=True)
    except Exception:
        # The current pointer is intentionally untouched until every migration gate passes.
        raise
    return {
        "operation": "update",
        "previous": current,
        "current": pointer,
        "backup": str(backup_root),
        "state": restored,
        "new_runtime_state": new_runtime_verification,
    }


async def rollback_install(
    *, install_root: Path, state_root: Path, startup_entry: Path | None = None
) -> dict[str, Any]:
    install = _safe_managed_root(install_root, name="install_root")
    state = _safe_managed_root(state_root, name="state_root")
    _assert_install_marker(install, state)
    current = _read_json(install / CURRENT_FILE)
    history = _read_json(install / HISTORY_FILE)
    entries = history.get("entries")
    if not isinstance(entries, list) or not entries:
        raise InstallOperationError("no previous release/state pair is available for rollback")
    previous = entries.pop()
    if not isinstance(previous, dict):
        raise InstallOperationError("install history contains an invalid pointer")
    version_root, slot_root = _pointer_paths(install, state, previous)
    if not version_root.is_dir() or not slot_root.is_dir():
        raise InstallOperationError("rollback release or state slot is missing")
    verified = await verify_state(slot_root, migrate=False)
    _atomic_json(install / HISTORY_FILE, {"schema_version": 1, "entries": entries})
    rolled_back = {**previous, "rolled_back_at": _now()}
    _atomic_json(install / CURRENT_FILE, rolled_back)
    _write_launchers(install, state)
    if startup_entry is not None and startup_entry.exists():
        _configure_startup(startup_entry, install, state, enabled=True)
    return {
        "operation": "rollback",
        "from": current,
        "current": rolled_back,
        "state": verified,
    }


def uninstall_install(
    *,
    install_root: Path,
    state_root: Path,
    startup_entry: Path | None = None,
    purge_data: bool = False,
) -> dict[str, Any]:
    install = _safe_managed_root(install_root, name="install_root")
    state = _safe_managed_root(state_root, name="state_root")
    _assert_install_marker(install, state)
    current = _read_json(install / CURRENT_FILE)
    _configure_startup(startup_entry, install, state, enabled=False)
    _atomic_json(state / "last-install.json", current)
    shutil.rmtree(install)
    retained = True
    if purge_data:
        marker = _read_json(state / ".sora-state.json")
        if Path(str(marker.get("state_root", ""))).resolve() != state:
            raise InstallOperationError("state marker does not match the requested purge target")
        shutil.rmtree(state)
        retained = False
    return {
        "operation": "uninstall",
        "install_removed": True,
        "personal_data_retained": retained,
        "state_root": str(state),
    }
