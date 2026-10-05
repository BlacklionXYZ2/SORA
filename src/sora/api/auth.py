"""Authentication and local boundary security enforcement for SORA API."""

from __future__ import annotations

import hmac
from urllib.parse import parse_qs, urlparse

from sora.api.config import ApiServerConfig


class ApiSecurityError(Exception):
    """Raised when request violates local security boundary (status 400)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.status_code = 400
        self.message = message


class ApiAuthenticationError(Exception):
    """Raised when authentication credentials are missing or invalid (status 401)."""

    def __init__(self, message: str = "Unauthorized: invalid or missing Bearer token") -> None:
        super().__init__(message)
        self.status_code = 401
        self.message = message


class ApiForbiddenError(Exception):
    """Raised when request origin or host is not allowed (status 403)."""

    def __init__(self, message: str = "Forbidden: untrusted origin or host") -> None:
        super().__init__(message)
        self.status_code = 403
        self.message = message


class SecurityValidator:
    """Validates local host, origin, and query parameters against security rules."""

    def __init__(self, config: ApiServerConfig) -> None:
        self.config = config

    def validate_request_path(self, path: str) -> None:
        """Enforces P08.3 invariant: tokens must never appear in URL query logs."""
        parsed = urlparse(path)
        if parsed.query:
            params = parse_qs(parsed.query, keep_blank_values=True)
            forbidden_fragments = ("token", "secret", "credential", "bearer", "api_key")
            for key in params:
                normalized_key = key.strip().casefold().replace("-", "_")
                if normalized_key == "key" or any(
                    fragment in normalized_key for fragment in forbidden_fragments
                ):
                    raise ApiSecurityError(
                        "Authentication tokens in URL query strings are strictly forbidden "
                        "to prevent exposure in logs. Use 'Authorization: Bearer <token>' header."
                    )

    def validate_host(self, host_header: str | None, *, remote: bool = False) -> None:
        """Validates that Host header targets an authorized local address."""
        if not host_header:
            raise ApiSecurityError("Missing Host header")

        parsed = urlparse(f"//{host_header.strip()}")
        host_part = (parsed.hostname or "").casefold()
        allowed_hosts = {"localhost", "127.0.0.1", "::1"}
        if remote:
            allowed_hosts = {
                str(self.config.remote_host or "").casefold(),
                *(host.casefold() for host in self.config.remote_allowed_hosts),
            }
        if host_part not in allowed_hosts:
            if not remote:
                raise ApiForbiddenError(
                    f"Host '{host_header}' is not an authorized local loopback address"
                )
            raise ApiForbiddenError(
                f"Host '{host_header}' is not authorized for this listener"
            )

    def validate_origin(self, origin_header: str | None, *, remote: bool = False) -> None:
        """Validates that Origin header matches allowed local/app origins."""
        if not origin_header:
            return  # Same-origin or non-browser client (e.g. CLI, Unity, test fixture)

        origin_clean = origin_header.strip().casefold()
        parsed = urlparse(origin_clean)
        if not parsed.scheme or not parsed.hostname or parsed.username or parsed.password:
            raise ApiForbiddenError("Origin is malformed or contains user information")

        if remote:
            if origin_clean not in {
                origin.strip().casefold().rstrip("/")
                for origin in self.config.remote_allowed_origins
            }:
                raise ApiForbiddenError(
                    f"Origin '{origin_header}' is not permitted by remote origin policy"
                )
            return

        is_allowed = False
        try:
            for allowed in self.config.allowed_origins:
                allowed_clean = allowed.strip().casefold()
                allowed_parsed = urlparse(allowed_clean)
                if not allowed_parsed.scheme or not allowed_parsed.hostname:
                    continue
                same_origin = (
                    parsed.scheme == allowed_parsed.scheme
                    and parsed.hostname == allowed_parsed.hostname
                    and (allowed_parsed.port is None or parsed.port == allowed_parsed.port)
                )
                if same_origin:
                    is_allowed = True
                    break
        except ValueError as exc:
            raise ApiForbiddenError("Origin contains an invalid port") from exc

        if not is_allowed:
            raise ApiForbiddenError(
                f"Origin '{origin_header}' is not permitted by CORS origin policy"
            )


class TokenAuthenticator:
    """Authenticates Bearer tokens using constant-time digest comparison."""

    def __init__(self, expected_token: str) -> None:
        self._expected_token = expected_token

    def authenticate(self, auth_header: str | None) -> None:
        """Validates the Authorization header."""
        if not auth_header:
            raise ApiAuthenticationError("Missing Authorization header")

        parts = auth_header.strip().split(None, 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise ApiAuthenticationError("Invalid Authorization scheme: expected 'Bearer <token>'")

        provided_token = parts[1].strip()
        if not hmac.compare_digest(provided_token, self._expected_token):
            raise ApiAuthenticationError("Invalid Bearer authentication token")
