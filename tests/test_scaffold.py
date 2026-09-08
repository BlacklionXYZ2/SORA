from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import sora
from sora.persistence.migrations import CURRENT_SCHEMA_VERSION


def test_package_has_version() -> None:
    assert sora.__version__ == "0.0.0"


def test_module_entry_point_reports_runtime_state(tmp_path: Path) -> None:
    identity_root = Path(__file__).resolve().parents[1] / "identity"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "sora",
            "--root",
            str(tmp_path),
            "--identity-root",
            str(identity_root),
            "--state",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert f'"schema_version": {CURRENT_SCHEMA_VERSION}' in completed.stdout
    assert '"tasks": 0' in completed.stdout


def test_hermes_cli_requires_an_explicit_existing_working_directory(tmp_path: Path) -> None:
    identity_root = Path(__file__).resolve().parents[1] / "identity"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "sora",
            "--root",
            str(tmp_path),
            "--identity-root",
            str(identity_root),
            "--provider",
            "hermes",
            "--once",
            "Do not run.",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "requires --hermes-cwd" in completed.stdout
    assert "assign the intended working directory" in completed.stdout
    assert not (tmp_path / "data" / "sora.db").exists()


def test_codex_cli_requires_an_explicit_existing_working_directory(tmp_path: Path) -> None:
    identity_root = Path(__file__).resolve().parents[1] / "identity"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "sora",
            "--root",
            str(tmp_path),
            "--identity-root",
            str(identity_root),
            "--provider",
            "codex",
            "--once",
            "Do not run.",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "requires --codex-cwd" in completed.stdout
    assert not (tmp_path / "data" / "sora.db").exists()
