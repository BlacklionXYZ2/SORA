"""Configuration for the local authenticated SORA API server."""

from __future__ import annotations

import ipaddress
import secrets
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, model_validator

from sora.contracts.base import StrictModel


class ApiServerConfig(StrictModel):
    """Configuration for SoraApiServer enforcing local loopback and security bounds."""

    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=0, le=65535)
    auth_token: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    token_file: Path | None = None
    loopback_only: bool = True
    allowed_origins: tuple[str, ...] = (
        "http://localhost",
        "http://127.0.0.1",
        "https://localhost",
        "https://127.0.0.1",
        "app://sora",
    )
    max_payload_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)  # 10 MB limit
    client_buffer_capacity: int = Field(default=100, ge=10, le=10_000)
    replay_limit: int = Field(default=500, ge=1, le=10_000)
    request_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    websocket_hello_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    max_header_bytes: int = Field(default=64 * 1024, ge=1024, le=1024 * 1024)
    cors_enabled: bool = True
    remote_access_enabled: bool = False
    remote_host: str | None = None
    remote_port: int = Field(default=8766, ge=0, le=65535)
    remote_tls_certificate_file: Path | None = None
    remote_tls_private_key_file: Path | None = None
    remote_allowed_origins: tuple[str, ...] = ()
    remote_allowed_hosts: tuple[str, ...] = ()
    remote_session_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    pairing_invitation_ttl_seconds: int = Field(default=300, ge=30, le=900)
    remote_request_limit: int = Field(default=120, ge=10, le=10_000)
    remote_request_window_seconds: int = Field(default=60, ge=1, le=3600)
    pairing_attempt_limit: int = Field(default=5, ge=1, le=100)
    pairing_attempt_window_seconds: int = Field(default=60, ge=1, le=3600)

    @model_validator(mode="after")
    def validate_security(self) -> ApiServerConfig:
        if not self.loopback_only:
            raise ValueError(
                "the owner listener must remain loopback-only; use the separate TLS remote listener"
            )
        if self.loopback_only:
            try:
                ip = ipaddress.ip_address(self.host)
                if not ip.is_loopback:
                    raise ValueError(f"Host '{self.host}' is not a loopback address")
            except ValueError as exc:
                if "is not a loopback address" in str(exc):
                    raise
                if self.host.lower() not in {"localhost", "127.0.0.1", "::1"}:
                    raise ValueError(f"Host '{self.host}' is not a loopback address") from exc

        if not self.auth_token or len(self.auth_token.strip()) < 16:
            raise ValueError("auth_token must be at least 16 characters long")

        if any(origin.strip().endswith("*") for origin in self.allowed_origins):
            raise ValueError(
                "allowed_origins does not accept prefix wildcards; list trusted origins exactly"
            )

        if self.remote_access_enabled:
            if not self.remote_host:
                raise ValueError("remote_host is required when remote access is enabled")
            try:
                remote_ip = ipaddress.ip_address(self.remote_host)
            except ValueError as exc:
                raise ValueError("remote_host must be one concrete IP address") from exc
            if (
                remote_ip.is_unspecified
                or remote_ip.is_multicast
                or remote_ip.is_reserved
                or remote_ip.is_global
            ):
                raise ValueError(
                    "remote_host must be a concrete loopback, private, link-local, or overlay IP"
                )
            if self.remote_tls_certificate_file is None or self.remote_tls_private_key_file is None:
                raise ValueError("remote TLS certificate and private key are required")
            if not self.remote_allowed_origins:
                raise ValueError("at least one exact remote HTTPS origin is required")
            for origin in self.remote_allowed_origins:
                parsed = urlparse(origin.strip())
                if (
                    parsed.scheme != "https"
                    or not parsed.hostname
                    or parsed.username
                    or parsed.password
                    or parsed.path not in {"", "/"}
                    or parsed.query
                    or parsed.fragment
                ):
                    raise ValueError("remote origins must be exact HTTPS origins without paths")
            if any("*" in host for host in self.remote_allowed_hosts):
                raise ValueError("remote_allowed_hosts does not accept wildcards")
        elif any(
            value is not None
            for value in (
                self.remote_host,
                self.remote_tls_certificate_file,
                self.remote_tls_private_key_file,
            )
        ) or self.remote_allowed_origins or self.remote_allowed_hosts:
            raise ValueError("remote access settings require remote_access_enabled")

        return self
