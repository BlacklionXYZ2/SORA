"""Persisted pairing, short-lived remote sessions, scope checks, limits, and audit."""

# ruff: noqa: E501 -- SQL statements remain whole for direct schema comparison.

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, cast

from sora.persistence.database import SQLiteDatabase


class RemoteScope(StrEnum):
    CONVERSATION_READ = "conversation:read"
    CONVERSATION_WRITE = "conversation:write"
    TASKS_READ = "tasks:read"
    TASKS_CONTROL = "tasks:control"
    EVENTS_READ = "events:read"
    PROJECTIONS_READ = "projections:read"


DEFAULT_REMOTE_SCOPES = (
    RemoteScope.CONVERSATION_READ.value,
    RemoteScope.CONVERSATION_WRITE.value,
    RemoteScope.TASKS_READ.value,
    RemoteScope.EVENTS_READ.value,
    RemoteScope.PROJECTIONS_READ.value,
)
ALL_REMOTE_SCOPES = frozenset(scope.value for scope in RemoteScope)
_DEVICE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,63}$")


class RemoteAccessError(Exception):
    """A sanitized remote-access failure with an HTTP disposition."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class RemotePrincipal:
    owner_id: str
    device_id: str
    session_id: str
    scopes: frozenset[str]


class SlidingWindowRateLimiter:
    """Small in-memory per-source limiter; restart clears counters, never credentials."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, *, limit: int, window_seconds: float) -> bool:
        now = self._clock()
        cutoff = now - window_seconds
        events = self._events[key]
        while events and events[0] <= cutoff:
            events.popleft()
        if len(events) >= limit:
            return False
        events.append(now)
        return True


def required_remote_scope(method: str, path: str) -> str | None:
    """Map only intentionally exposed semantic routes; everything else is absent."""

    normalized = path.rstrip("/") or "/"
    if method == "GET" and normalized == "/api/v1/messages":
        return RemoteScope.CONVERSATION_READ.value
    if method == "POST" and normalized == "/api/v1/dialogue":
        return RemoteScope.CONVERSATION_WRITE.value
    if method == "GET" and (
        normalized == "/api/v1/tasks" or normalized.startswith("/api/v1/tasks/")
    ):
        return RemoteScope.TASKS_READ.value
    if method == "POST" and (
        normalized == "/api/v1/tasks"
        or (
            normalized.startswith("/api/v1/tasks/")
            and (normalized.endswith("/steer") or normalized.endswith("/cancel"))
        )
    ):
        return RemoteScope.TASKS_CONTROL.value
    if method == "GET" and normalized == "/api/v1/events":
        return RemoteScope.EVENTS_READ.value
    if method == "GET" and (
        normalized
        in {
            "/api/v1/status",
            "/api/v1/projections/companion",
            "/api/v1/projections/capabilities",
            "/readyz",
        }
    ):
        return RemoteScope.PROJECTIONS_READ.value
    return None


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _validate_device_id(device_id: str) -> str:
    value = device_id.strip()
    if not _DEVICE_ID.fullmatch(value):
        raise RemoteAccessError(400, "INVALID_DEVICE", "Device ID is invalid")
    return value


def _validate_label(label: str) -> str:
    value = " ".join(label.strip().split())
    if not 1 <= len(value) <= 80:
        raise RemoteAccessError(400, "INVALID_LABEL", "Device label is invalid")
    return value


def _validate_scopes(scopes: Iterable[str]) -> tuple[str, ...]:
    values = tuple(sorted(set(str(scope) for scope in scopes)))
    if not values or any(scope not in ALL_REMOTE_SCOPES for scope in values):
        raise RemoteAccessError(400, "INVALID_SCOPE", "Remote scope set is invalid")
    return values


def _authorization_credential(header: str | None, scheme: str) -> str:
    if not header:
        raise RemoteAccessError(401, "REMOTE_UNAUTHORIZED", "Remote credential is required")
    parts = header.strip().split(None, 1)
    if len(parts) != 2 or parts[0] != scheme or not parts[1].strip():
        raise RemoteAccessError(401, "REMOTE_UNAUTHORIZED", "Remote credential is invalid")
    return parts[1].strip()


class RemoteAccessManager:
    """Owns the persisted device/session credential hierarchy for one Core owner."""

    def __init__(
        self,
        database: SQLiteDatabase,
        owner_id: str,
        *,
        invitation_ttl_seconds: int = 300,
        session_ttl_seconds: int = 900,
        audit_retention: int = 1000,
    ) -> None:
        self.database = database
        self.owner_id = owner_id
        self.invitation_ttl_seconds = invitation_ttl_seconds
        self.session_ttl_seconds = session_ttl_seconds
        self.audit_retention = audit_retention

    async def create_invitation(
        self,
        *,
        label: str,
        scopes: Iterable[str] = DEFAULT_REMOTE_SCOPES,
        expires_in_seconds: int | None = None,
        source_ip: str = "127.0.0.1",
    ) -> dict[str, Any]:
        clean_label = _validate_label(label)
        clean_scopes = _validate_scopes(scopes)
        ttl = expires_in_seconds or self.invitation_ttl_seconds
        if not 30 <= ttl <= 900:
            raise RemoteAccessError(400, "INVALID_EXPIRY", "Pairing expiry is out of bounds")
        now = _utcnow()
        expires_at = now + timedelta(seconds=ttl)
        invitation_id = f"invite-{uuid.uuid4()}"
        code = secrets.token_urlsafe(24)

        def write(db: sqlite3.Connection) -> None:
            db.execute(
                "INSERT INTO pairing_invitations(invitation_id, owner_id, code_hash, label, scopes_json, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    invitation_id,
                    self.owner_id,
                    _hash_secret(code),
                    clean_label,
                    json.dumps(clean_scopes),
                    now.isoformat(),
                    expires_at.isoformat(),
                ),
            )

        await self.database.write(write)
        await self.audit(
            action="pairing.invitation_created",
            outcome="allowed",
            source_ip=source_ip,
            method="POST",
            path="/api/v1/pairing/invitations",
            details={"invitation_id": invitation_id, "scopes": list(clean_scopes)},
        )
        return {
            "invitation_id": invitation_id,
            "pairing_code": code,
            "label": clean_label,
            "scopes": list(clean_scopes),
            "expires_at": expires_at.isoformat(),
        }

    async def claim_invitation(
        self,
        *,
        code: str,
        device_id: str,
        label: str,
        source_ip: str,
    ) -> dict[str, Any]:
        clean_device_id = _validate_device_id(device_id)
        clean_label = _validate_label(label)
        credential_secret = secrets.token_urlsafe(32)
        credential = f"{clean_device_id}.{credential_secret}"
        now = _utcnow()

        def write(db: sqlite3.Connection) -> tuple[str, tuple[str, ...]]:
            row = db.execute(
                "SELECT * FROM pairing_invitations WHERE owner_id=? AND code_hash=?",
                (self.owner_id, _hash_secret(code.strip())),
            ).fetchone()
            if row is None:
                raise RemoteAccessError(401, "PAIRING_REJECTED", "Pairing code is invalid")
            if row["claimed_at"] is not None:
                raise RemoteAccessError(409, "PAIRING_USED", "Pairing code was already used")
            if datetime.fromisoformat(str(row["expires_at"])) <= now:
                raise RemoteAccessError(410, "PAIRING_EXPIRED", "Pairing code expired")
            if db.execute(
                "SELECT 1 FROM paired_devices WHERE device_id=?", (clean_device_id,)
            ).fetchone():
                raise RemoteAccessError(409, "DEVICE_EXISTS", "Device ID is already registered")
            scopes = tuple(str(scope) for scope in json.loads(str(row["scopes_json"])))
            db.execute(
                "INSERT INTO paired_devices(device_id, owner_id, label, credential_hash, scopes_json, paired_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    clean_device_id,
                    self.owner_id,
                    clean_label,
                    _hash_secret(credential),
                    json.dumps(scopes),
                    now.isoformat(),
                ),
            )
            db.execute(
                "UPDATE pairing_invitations SET claimed_at=?, claimed_device_id=? WHERE invitation_id=?",
                (now.isoformat(), clean_device_id, row["invitation_id"]),
            )
            return str(row["invitation_id"]), scopes

        try:
            invitation_id, scopes = await self.database.write(write)
        except RemoteAccessError as exc:
            await self.audit(
                action="pairing.claim",
                outcome="denied",
                source_ip=source_ip,
                method="POST",
                path="/api/v1/pairing/claim",
                device_id=clean_device_id,
                details={"code": exc.code},
            )
            raise
        await self.audit(
            action="pairing.claim",
            outcome="allowed",
            source_ip=source_ip,
            method="POST",
            path="/api/v1/pairing/claim",
            device_id=clean_device_id,
            details={"invitation_id": invitation_id, "scopes": list(scopes)},
        )
        return {
            "device_id": clean_device_id,
            "device_credential": credential,
            "scopes": list(scopes),
        }

    async def create_session(
        self,
        *,
        authorization: str | None,
        device_id: str,
        requested_scopes: Iterable[str] | None,
        source_ip: str,
    ) -> dict[str, Any]:
        clean_device_id = _validate_device_id(device_id)
        credential = _authorization_credential(authorization, "SoraDevice")
        now = _utcnow()
        row = await self._read_device(clean_device_id)
        if row is None or row["revoked_at"] is not None or not hmac.compare_digest(
            str(row["credential_hash"]), _hash_secret(credential)
        ):
            await self.audit(
                action="session.create",
                outcome="denied",
                source_ip=source_ip,
                method="POST",
                path="/api/v1/pairing/session",
                device_id=clean_device_id,
                details={"code": "REMOTE_UNAUTHORIZED"},
            )
            raise RemoteAccessError(401, "REMOTE_UNAUTHORIZED", "Device credential is invalid")
        if not credential.startswith(f"{clean_device_id}."):
            raise RemoteAccessError(401, "REMOTE_UNAUTHORIZED", "Device credential is invalid")
        device_scopes = frozenset(str(scope) for scope in json.loads(str(row["scopes_json"])))
        scopes = (
            _validate_scopes(requested_scopes)
            if requested_scopes is not None
            else tuple(sorted(device_scopes))
        )
        if not set(scopes) <= device_scopes:
            raise RemoteAccessError(403, "SCOPE_ESCALATION", "Requested session scope is denied")
        session_id = f"remote-{uuid.uuid4()}"
        token = f"{session_id}.{secrets.token_urlsafe(32)}"
        expires_at = now + timedelta(seconds=self.session_ttl_seconds)

        def write(db: sqlite3.Connection) -> None:
            current = db.execute(
                "SELECT revoked_at FROM paired_devices WHERE device_id=?", (clean_device_id,)
            ).fetchone()
            if current is None or current["revoked_at"] is not None:
                raise RemoteAccessError(401, "REMOTE_UNAUTHORIZED", "Device was revoked")
            db.execute(
                "INSERT INTO remote_sessions(session_id, device_id, token_hash, scopes_json, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    clean_device_id,
                    _hash_secret(token),
                    json.dumps(scopes),
                    now.isoformat(),
                    expires_at.isoformat(),
                ),
            )
            db.execute(
                "UPDATE paired_devices SET last_seen_at=? WHERE device_id=?",
                (now.isoformat(), clean_device_id),
            )

        await self.database.write(write)
        await self.audit(
            action="session.create",
            outcome="allowed",
            source_ip=source_ip,
            method="POST",
            path="/api/v1/pairing/session",
            device_id=clean_device_id,
            session_id=session_id,
            details={"scopes": list(scopes), "expires_at": expires_at.isoformat()},
        )
        return {
            "session_id": session_id,
            "session_token": token,
            "device_id": clean_device_id,
            "scopes": list(scopes),
            "expires_at": expires_at.isoformat(),
        }

    async def authenticate_session(
        self,
        *,
        authorization: str | None,
        device_id: str,
    ) -> RemotePrincipal:
        clean_device_id = _validate_device_id(device_id)
        token = _authorization_credential(authorization, "SoraSession")
        session_id = token.split(".", 1)[0]
        if not session_id.startswith("remote-"):
            raise RemoteAccessError(401, "REMOTE_UNAUTHORIZED", "Remote session is invalid")
        now = _utcnow()

        def read(db: sqlite3.Connection) -> sqlite3.Row | None:
            return cast(
                sqlite3.Row | None,
                db.execute(
                    "SELECT s.*, d.owner_id, d.revoked_at AS device_revoked_at "
                    "FROM remote_sessions s JOIN paired_devices d ON d.device_id=s.device_id "
                    "WHERE s.session_id=? AND s.device_id=?",
                    (session_id, clean_device_id),
                ).fetchone(),
            )

        row = await self.database.read(read)
        if (
            row is None
            or row["revoked_at"] is not None
            or row["device_revoked_at"] is not None
            or datetime.fromisoformat(str(row["expires_at"])) <= now
            or not hmac.compare_digest(str(row["token_hash"]), _hash_secret(token))
        ):
            raise RemoteAccessError(401, "REMOTE_UNAUTHORIZED", "Remote session is invalid")
        scopes = frozenset(str(scope) for scope in json.loads(str(row["scopes_json"])))

        def touch(db: sqlite3.Connection) -> None:
            db.execute(
                "UPDATE remote_sessions SET last_seen_at=? WHERE session_id=?",
                (now.isoformat(), session_id),
            )
            db.execute(
                "UPDATE paired_devices SET last_seen_at=? WHERE device_id=?",
                (now.isoformat(), clean_device_id),
            )

        await self.database.write(touch)
        return RemotePrincipal(
            owner_id=str(row["owner_id"]),
            device_id=clean_device_id,
            session_id=session_id,
            scopes=scopes,
        )

    async def revoke_device(self, device_id: str, *, source_ip: str) -> dict[str, Any]:
        clean_device_id = _validate_device_id(device_id)
        now = _utcnow().isoformat()

        def write(db: sqlite3.Connection) -> bool:
            row = db.execute(
                "SELECT revoked_at FROM paired_devices WHERE device_id=? AND owner_id=?",
                (clean_device_id, self.owner_id),
            ).fetchone()
            if row is None:
                return False
            if row["revoked_at"] is None:
                db.execute(
                    "UPDATE paired_devices SET revoked_at=? WHERE device_id=?", (now, clean_device_id)
                )
                db.execute(
                    "UPDATE remote_sessions SET revoked_at=? WHERE device_id=? AND revoked_at IS NULL",
                    (now, clean_device_id),
                )
            return True

        found = await self.database.write(write)
        if not found:
            raise RemoteAccessError(404, "DEVICE_NOT_FOUND", "Paired device was not found")
        await self.audit(
            action="device.revoke",
            outcome="allowed",
            source_ip=source_ip,
            method="POST",
            path=f"/api/v1/pairing/devices/{clean_device_id}/revoke",
            device_id=clean_device_id,
        )
        return {"device_id": clean_device_id, "revoked": True, "revoked_at": now}

    async def list_devices(self) -> list[dict[str, Any]]:
        def read(db: sqlite3.Connection) -> list[sqlite3.Row]:
            return db.execute(
                "SELECT device_id, label, scopes_json, paired_at, last_seen_at, revoked_at "
                "FROM paired_devices WHERE owner_id=? ORDER BY paired_at DESC",
                (self.owner_id,),
            ).fetchall()

        rows = await self.database.read(read)
        return [
            {
                "device_id": str(row["device_id"]),
                "label": str(row["label"]),
                "scopes": json.loads(str(row["scopes_json"])),
                "paired_at": str(row["paired_at"]),
                "last_seen_at": row["last_seen_at"],
                "revoked_at": row["revoked_at"],
            }
            for row in rows
        ]

    async def list_audit(self, *, limit: int = 100) -> list[dict[str, Any]]:
        if not 1 <= limit <= 200:
            raise RemoteAccessError(400, "INVALID_PAGE", "Audit limit is out of bounds")

        def read(db: sqlite3.Connection) -> list[sqlite3.Row]:
            return db.execute(
                "SELECT * FROM remote_access_audit WHERE owner_id=? "
                "ORDER BY created_at DESC LIMIT ?",
                (self.owner_id, limit),
            ).fetchall()

        rows = await self.database.read(read)
        return [
            {
                "audit_id": str(row["audit_id"]),
                "device_id": row["device_id"],
                "session_id": row["session_id"],
                "source_ip": str(row["source_ip"]),
                "method": str(row["method"]),
                "path": str(row["path"]),
                "action": str(row["action"]),
                "outcome": str(row["outcome"]),
                "created_at": str(row["created_at"]),
                "details": json.loads(str(row["details_json"])),
            }
            for row in rows
        ]

    async def audit(
        self,
        *,
        action: str,
        outcome: str,
        source_ip: str,
        method: str,
        path: str,
        device_id: str | None = None,
        session_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        safe_details = details or {}
        serialized = json.dumps(safe_details, sort_keys=True)
        if len(serialized) > 2048:
            serialized = json.dumps({"truncated": True})
        now = _utcnow().isoformat()

        def write(db: sqlite3.Connection) -> None:
            db.execute(
                "INSERT INTO remote_access_audit(audit_id, owner_id, device_id, session_id, source_ip, method, path, action, outcome, created_at, details_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"audit-{uuid.uuid4()}",
                    self.owner_id,
                    device_id,
                    session_id,
                    source_ip[:64],
                    method[:12],
                    path[:256],
                    action[:80],
                    outcome[:32],
                    now,
                    serialized,
                ),
            )
            db.execute(
                "DELETE FROM remote_access_audit WHERE owner_id=? AND audit_id NOT IN "
                "(SELECT audit_id FROM remote_access_audit WHERE owner_id=? "
                "ORDER BY created_at DESC LIMIT ?)",
                (self.owner_id, self.owner_id, self.audit_retention),
            )

        await self.database.write(write)

    async def _read_device(self, device_id: str) -> sqlite3.Row | None:
        def read(db: sqlite3.Connection) -> sqlite3.Row | None:
            return cast(
                sqlite3.Row | None,
                db.execute(
                    "SELECT * FROM paired_devices WHERE device_id=? AND owner_id=?",
                    (device_id, self.owner_id),
                ).fetchone(),
            )

        return await self.database.read(read)
