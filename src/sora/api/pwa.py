"""Exact-path static asset serving for the local SORA progressive web app."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sora.api.protocol import HttpRequest, HttpResponse


@dataclass(frozen=True)
class PwaAsset:
    """One packaged public app-shell asset and its response policy."""

    relative_path: str
    content_type: str
    cache_control: str = "no-cache"
    service_worker_allowed: bool = False


class PwaAssetServer:
    """Serves only a fixed app-shell allowlist; API data is never handled here."""

    _ASSETS: dict[str, PwaAsset] = {
        "/": PwaAsset("index.html", "text/html; charset=utf-8"),
        "/app": PwaAsset("index.html", "text/html; charset=utf-8"),
        "/index.html": PwaAsset("index.html", "text/html; charset=utf-8"),
        "/app.css": PwaAsset("app.css", "text/css; charset=utf-8"),
        "/app.js": PwaAsset("app.js", "text/javascript; charset=utf-8"),
        "/api-client.js": PwaAsset("api-client.js", "text/javascript; charset=utf-8"),
        "/sync.js": PwaAsset("sync.js", "text/javascript; charset=utf-8"),
        "/device-vault.js": PwaAsset("device-vault.js", "text/javascript; charset=utf-8"),
        "/manifest.webmanifest": PwaAsset(
            "manifest.webmanifest", "application/manifest+json; charset=utf-8"
        ),
        "/service-worker.js": PwaAsset(
            "service-worker.js",
            "text/javascript; charset=utf-8",
            cache_control="no-cache, no-store, must-revalidate",
            service_worker_allowed=True,
        ),
        "/icons/sora-192.png": PwaAsset("icons/sora-192.png", "image/png"),
        "/icons/sora-512.png": PwaAsset("icons/sora-512.png", "image/png"),
    }

    def __init__(self, asset_root: Path | None = None) -> None:
        self.asset_root = asset_root or Path(__file__).resolve().parents[1] / "pwa"

    def can_serve(self, request: HttpRequest) -> bool:
        """Return true only for safe reads of a known path without a query string."""

        return (
            request.method in {"GET", "HEAD"}
            and not request.query_string
            and request.path in self._ASSETS
        )

    def serve(self, request: HttpRequest) -> HttpResponse:
        """Read one package-owned asset and attach a restrictive browser policy."""

        asset = self._ASSETS[request.path]
        body = (self.asset_root / asset.relative_path).read_bytes()
        headers = {
            "Content-Type": asset.content_type,
            "Content-Length": str(len(body)),
            "Cache-Control": asset.cache_control,
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Cross-Origin-Resource-Policy": "same-origin",
            "Content-Security-Policy": (
                "default-src 'self'; connect-src 'self'; img-src 'self'; "
                "script-src 'self'; style-src 'self'; object-src 'none'; "
                "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
            ),
        }
        if asset.service_worker_allowed:
            headers["Service-Worker-Allowed"] = "/"
        return HttpResponse(
            status_code=200,
            headers=headers,
            body=b"" if request.method == "HEAD" else body,
        )
