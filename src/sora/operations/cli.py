"""Operator CLI used by portable release and maintenance scripts."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from sora import __version__

from .install import install_bundle, rollback_install, uninstall_install, update_bundle
from .release import build_release_manifest, verify_release_manifest
from .state import backup_state, initialize_state, restore_state, verify_state


def _default_startup_entry() -> Path | None:
    appdata = os.getenv("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "Microsoft/Windows/Start Menu/Programs/Startup/SORA.cmd"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="SORA release and state operations")
    sub = result.add_subparsers(dest="command", required=True)

    manifest = sub.add_parser("build-manifest")
    manifest.add_argument("--bundle", type=Path, required=True)
    manifest.add_argument("--release-id", required=True)
    manifest.add_argument("--metadata", type=Path, required=True)

    verify_manifest = sub.add_parser("verify-manifest")
    verify_manifest.add_argument("--bundle", type=Path, required=True)

    initialize = sub.add_parser("initialize-state")
    initialize.add_argument("--root", type=Path, required=True)
    initialize.add_argument("--identity-root", type=Path, required=True)

    backup = sub.add_parser("backup")
    backup.add_argument("--root", type=Path, required=True)
    backup.add_argument("--destination", type=Path, required=True)

    restore = sub.add_parser("restore")
    restore.add_argument("--backup", type=Path, required=True)
    restore.add_argument("--destination", type=Path, required=True)

    verify = sub.add_parser("verify-state")
    verify.add_argument("--root", type=Path, required=True)
    verify.add_argument("--migrate", action="store_true")

    for name in ("install", "update"):
        operation = sub.add_parser(name)
        operation.add_argument("--bundle", type=Path, required=True)
        operation.add_argument("--install-root", type=Path, required=True)
        operation.add_argument("--state-root", type=Path, required=True)
        operation.add_argument("--startup-entry", type=Path, default=None)
        if name == "install":
            operation.add_argument("--enable-startup", action="store_true")

    rollback = sub.add_parser("rollback")
    rollback.add_argument("--install-root", type=Path, required=True)
    rollback.add_argument("--state-root", type=Path, required=True)
    rollback.add_argument("--startup-entry", type=Path, default=None)

    uninstall = sub.add_parser("uninstall")
    uninstall.add_argument("--install-root", type=Path, required=True)
    uninstall.add_argument("--state-root", type=Path, required=True)
    uninstall.add_argument("--startup-entry", type=Path, default=None)
    uninstall.add_argument("--purge-data", action="store_true")
    return result


async def _run(arguments: argparse.Namespace) -> dict[str, Any]:
    command = str(arguments.command)
    if command == "build-manifest":
        metadata = json.loads(arguments.metadata.read_text(encoding="utf-8"))
        path = build_release_manifest(
            arguments.bundle,
            release_id=arguments.release_id,
            app_version=__version__,
            metadata=metadata,
        )
        return {"manifest": str(path)}
    if command == "verify-manifest":
        return verify_release_manifest(arguments.bundle)
    if command == "initialize-state":
        return await initialize_state(arguments.root, identity_root=arguments.identity_root)
    if command == "backup":
        path = await backup_state(arguments.root, arguments.destination)
        return {"manifest": str(path)}
    if command == "restore":
        return await restore_state(arguments.backup, arguments.destination)
    if command == "verify-state":
        return await verify_state(arguments.root, migrate=arguments.migrate)
    startup_entry = arguments.startup_entry or _default_startup_entry()
    if command == "install":
        return await install_bundle(
            arguments.bundle,
            install_root=arguments.install_root,
            state_root=arguments.state_root,
            startup_entry=startup_entry,
            enable_startup=arguments.enable_startup,
        )
    if command == "update":
        return await update_bundle(
            arguments.bundle,
            install_root=arguments.install_root,
            state_root=arguments.state_root,
            startup_entry=startup_entry,
        )
    if command == "rollback":
        return await rollback_install(
            install_root=arguments.install_root,
            state_root=arguments.state_root,
            startup_entry=startup_entry,
        )
    if command == "uninstall":
        return uninstall_install(
            install_root=arguments.install_root,
            state_root=arguments.state_root,
            startup_entry=startup_entry,
            purge_data=arguments.purge_data,
        )
    raise AssertionError(f"unhandled command: {command}")


def main() -> int:
    try:
        result = asyncio.run(_run(parser().parse_args()))
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
