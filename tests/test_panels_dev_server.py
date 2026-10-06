"""The browser preview server forwards only what SoraShell's panel proxy would."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "panels-dev-server.py"
spec = importlib.util.spec_from_file_location("panels_dev_server", SCRIPT)
assert spec is not None and spec.loader is not None
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


@pytest.mark.parametrize(("method", "path", "allowed"), [
    ("GET", "/api/v1/messages?limit=100", True),
    ("POST", "/api/v1/dialogue", True),
    ("DELETE", "/api/v1/messages", False),
    ("GET", "/api/v2/anything", False),
    ("GET", "/api/v1/../v0/secret", False),
    ("GET", "/api/v1//messages", False),
    ("GET", "/chat/index.html", False),
])
def test_forwarding_rule_matches_the_shell_proxy(method: str, path: str, allowed: bool) -> None:
    assert server.panel_api_allowed(method, path) is allowed
