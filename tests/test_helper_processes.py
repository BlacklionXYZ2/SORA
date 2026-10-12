"""Helper-process records that let the desktop host's Quit close every part of SORA."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sora import helper_processes


def test_records_only_when_enabled_and_children_inherit_the_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(helper_processes.STATE_ROOT_ENV, "")  # restored after the test
    helper_processes.record("laya", 123)  # off: tests and CLI runs leave nothing behind
    assert not (tmp_path / "private").exists()
    helper_processes.enable(tmp_path)
    helper_processes.record("laya", 456)
    folder = tmp_path / "private" / "helpers"
    assert (folder / "core.pid").read_text() == str(os.getpid())
    assert (folder / "laya.pid").read_text() == "456"
    assert os.environ[helper_processes.STATE_ROOT_ENV] == str(tmp_path.resolve())
