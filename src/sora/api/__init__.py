"""SORA authenticated API server, reconnectable client SDK, and protocol engine."""

from __future__ import annotations

from .auth import (
    ApiAuthenticationError,
    ApiForbiddenError,
    ApiSecurityError,
    SecurityValidator,
    TokenAuthenticator,
)
from .client import SoraApiClient
from .config import ApiServerConfig
from .events import (
    EventBroadcaster,
    EventSubscription,
    build_state_snapshot,
    get_stream_bounds,
    replay_events_since,
)
from .protocol import (
    HttpProtocolError,
    HttpRequest,
    HttpResponse,
    WebSocketProtocolError,
    WebSocketSession,
    is_websocket_upgrade_request,
    make_websocket_upgrade_response,
    read_http_request,
)
from .routes import RouteHandler
from .server import SoraApiServer

__all__ = [
    "ApiAuthenticationError",
    "ApiForbiddenError",
    "ApiSecurityError",
    "ApiServerConfig",
    "EventBroadcaster",
    "EventSubscription",
    "HttpRequest",
    "HttpProtocolError",
    "HttpResponse",
    "RouteHandler",
    "SecurityValidator",
    "SoraApiClient",
    "SoraApiServer",
    "TokenAuthenticator",
    "WebSocketSession",
    "WebSocketProtocolError",
    "build_state_snapshot",
    "get_stream_bounds",
    "is_websocket_upgrade_request",
    "make_websocket_upgrade_response",
    "read_http_request",
    "replay_events_since",
]
