"""Preview SORA's web panels in an ordinary browser, outside SoraShell.

Serves clients/panels/ on 127.0.0.1 and forwards same-origin /api/v1/ calls to Core with the
owner token, the same contract as SoraShell's WebView2 request filter (PanelApiProxy.cs). The
token stays in this process. Use it for design review and tests; the real panels run in
SoraShell. Example:

    uv run python scripts/panels-dev-server.py --core-url http://127.0.0.1:8765 \
        --token-file .local/manual-test/private/sora-api-token
    # then open http://127.0.0.1:8790/chat/
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

PANELS = Path(__file__).resolve().parents[1] / "clients" / "panels"
MAX_BODY = 262_144
FORWARD_TIMEOUT = 330  # A dialogue turn may run for minutes on a slow local model.


def panel_api_allowed(method: str, path: str) -> bool:
    """Same rule as PanelApiProxy.TryParse: GET or POST to /api/v1/ only, no traversal."""
    route = urlsplit(path).path
    return (
        method in {"GET", "POST"}
        and route.startswith("/api/v1/")
        and ".." not in route
        and "//" not in route
    )


def make_handler(core_url: str, token_file: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "SoraPanelsDev/1"

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

        def do_GET(self) -> None:  # noqa: N802
            if self.path.startswith("/api/"):
                self._forward("GET")
            else:
                self._static()

        def do_POST(self) -> None:  # noqa: N802
            self._forward("POST")

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _error(self, status: int, message: str, code: str) -> None:
            body = json.dumps({"error": {"message": message, "code": code}}).encode()
            self._send(status, body, "application/json")

        def _static(self) -> None:
            route = urlsplit(self.path).path
            target = (PANELS / route.lstrip("/")).resolve()
            if target.is_dir():
                target = target / "index.html"
            if not target.is_relative_to(PANELS) or not target.is_file():
                self._send(404, b"Not found", "text/plain")
                return
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if target.suffix == ".js":
                content_type = "text/javascript"
            self._send(200, target.read_bytes(), content_type)

        def _forward(self, method: str) -> None:
            if not panel_api_allowed(method, self.path):
                self._error(404, "Panels may only call /api/v1/ routes.", "PANEL_ROUTE_REFUSED")
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                self._error(413, "Request too large.", "PANEL_BODY_TOO_LARGE")
                return
            body = self.rfile.read(length) if length else None
            try:
                token = token_file.read_text(encoding="utf-8").strip()
            except OSError:
                self._error(503, "Core token is not ready yet.", "CORE_UNAVAILABLE")
                return
            request = urllib.request.Request(core_url + self.path, data=body, method=method)
            request.add_header("Authorization", f"Bearer {token}")
            request.add_header("X-SORA-Device-ID", "device-local")
            request.add_header("Accept", "application/json")
            if body is not None:
                request.add_header("Content-Type", "application/json")
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            try:
                with opener.open(request, timeout=FORWARD_TIMEOUT) as response:
                    self._send(response.status, response.read(), "application/json")
            except urllib.error.HTTPError as error:
                self._send(error.code, error.read(), "application/json")
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                self._error(503, "SORA's Core is not reachable.", "CORE_UNAVAILABLE")

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--core-url", default="http://127.0.0.1:8765")
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8790)
    arguments = parser.parse_args()
    server = ThreadingHTTPServer(
        ("127.0.0.1", arguments.port),
        make_handler(arguments.core_url.rstrip("/"), arguments.token_file),
    )
    print(f"SORA panels on http://127.0.0.1:{server.server_address[1]}/  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
