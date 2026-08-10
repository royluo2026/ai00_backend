"""Short-lived signed mount URLs for opaque-origin Web Plugin iframes."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable, Protocol
from urllib.parse import quote

from pydantic import Field, model_validator

from backend.capability_v2.contracts import FrozenModel, IDENTITY_PATTERN


class MountTokenError(PermissionError):
    pass


@dataclass(frozen=True)
class MountClaims:
    tenant_gid: str
    plugin_id: str
    version: str
    artifact_sha256: str
    expires_at: int


def _secret() -> bytes:
    value = os.getenv("AI00_PLUGIN_MOUNT_SECRET", "").encode("utf-8")
    if len(value) < 32:
        raise MountTokenError("AI00_PLUGIN_MOUNT_SECRET must contain at least 32 bytes")
    return value


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_mount_token(*, tenant_gid: str, plugin_id: str, version: str, artifact_sha256: str, ttl_seconds: int = 300) -> str:
    ttl_seconds = max(30, min(int(ttl_seconds), 600))
    payload = {"t": tenant_gid, "p": plugin_id, "v": version, "h": artifact_sha256, "exp": int(time.time()) + ttl_seconds, "n": secrets.token_urlsafe(12)}
    encoded = _encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    signature = _encode(hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def verify_mount_token(token: str) -> MountClaims:
    try:
        encoded, supplied = token.split(".", 1)
        expected = _encode(hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, supplied): raise MountTokenError("invalid mount token signature")
        value = json.loads(_decode(encoded))
        claims = MountClaims(str(value["t"]), str(value["p"]), str(value["v"]), str(value["h"]), int(value["exp"]))
        if claims.expires_at < int(time.time()): raise MountTokenError("mount token expired")
        if len(claims.artifact_sha256) != 64: raise MountTokenError("invalid artifact binding")
        return claims
    except MountTokenError:
        raise
    except Exception as exc:
        raise MountTokenError("malformed mount token") from exc


def mount_url(token: str, plugin_id: str, version: str, entry: str) -> str:
    parts = [quote(part, safe="") for part in entry.replace("\\", "/").split("/")]
    return f"/api/v1/plugin-marketplace/assets/{quote(token, safe='.')}/{quote(plugin_id, safe='.')}/{quote(version, safe='.-')}/{'/'.join(parts)}"


class MountSessionError(PermissionError):
    pass


class PluginMountSession(FrozenModel):
    mount_session_id: str = Field(pattern=IDENTITY_PATTERN)
    user_id: str = Field(pattern=IDENTITY_PATTERN)
    tenant_id: str = Field(pattern=IDENTITY_PATTERN)
    installation_id: str = Field(pattern=IDENTITY_PATTERN)
    plugin_id: str = Field(pattern=IDENTITY_PATTERN)
    plugin_version: str = Field(min_length=1, max_length=128)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalog_release: str = Field(pattern=r"^rel_[0-9a-f]{32}$")
    capability_grants: tuple[str, ...] = ()
    resource_scopes: tuple[str, ...] = ()
    data_scopes: tuple[str, ...] = ()
    revocation_version: int = Field(ge=1)
    asset_token_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    authenticated_at: datetime
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    @model_validator(mode="after")
    def timestamp_contract(self):
        for value in (self.authenticated_at, self.created_at, self.expires_at, self.revoked_at):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("mount timestamps must be timezone-aware")
        if self.expires_at <= self.created_at:
            raise ValueError("mount session expiry must follow creation")
        return self


class IssuedMountSession(FrozenModel):
    session: PluginMountSession
    asset_token: str = Field(min_length=32)
    asset_token_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class AssetMountClaims(FrozenModel):
    mount_session_id: str = Field(pattern=IDENTITY_PATTERN)
    tenant_id: str = Field(pattern=IDENTITY_PATTERN)
    plugin_id: str = Field(pattern=IDENTITY_PATTERN)
    plugin_version: str
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expires_at: datetime


class MountSessionStore(Protocol):
    def save(self, session: PluginMountSession) -> None: ...
    def get_live_by_id(self, mount_session_id: str) -> PluginMountSession: ...
    def get_live_by_token_hash(self, token_hash: str) -> PluginMountSession: ...


class InMemoryMountSessionStore:
    def __init__(self, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._clock = clock
        self._sessions: dict[str, PluginMountSession] = {}
        self._tokens: dict[str, str] = {}
        self._installation_revisions: dict[str, int] = {}

    def save(self, session: PluginMountSession) -> None:
        if session.mount_session_id in self._sessions or session.asset_token_hash in self._tokens:
            raise MountSessionError("mount_session_exists")
        self._sessions[session.mount_session_id] = session
        self._tokens[session.asset_token_hash] = session.mount_session_id
        self._installation_revisions.setdefault(session.installation_id, session.revocation_version)

    def get_live_by_id(self, mount_session_id: str) -> PluginMountSession:
        session = self._sessions.get(mount_session_id)
        return self._assert_live(session)

    def get_live_by_token_hash(self, token_hash: str) -> PluginMountSession:
        mount_session_id = self._tokens.get(token_hash)
        return self._assert_live(self._sessions.get(mount_session_id or ""))

    def _assert_live(self, session: PluginMountSession | None) -> PluginMountSession:
        if session is None:
            raise MountSessionError("mount session invalid")
        if session.revoked_at is not None:
            raise MountSessionError("mount session revoked")
        if session.expires_at <= self._clock():
            raise MountSessionError("mount session expired")
        if self._installation_revisions.get(session.installation_id) != session.revocation_version:
            raise MountSessionError("mount session revoked by installation change")
        return session

    def revoke_installation(self, installation_id: str, *, new_revocation_version: int) -> None:
        self._installation_revisions[installation_id] = new_revocation_version

    def snapshot(self) -> tuple[PluginMountSession, ...]:
        return tuple(sorted(self._sessions.values(), key=lambda value: value.mount_session_id))


class SqlMountSessionStore:
    TABLE = "workmanship_plugin_mount_sessions"

    def __init__(self, connection_context_factory,
                 *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._connections = connection_context_factory
        self._clock = clock

    def save(self, session: PluginMountSession) -> None:
        with self._connections() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"INSERT INTO {self.TABLE} "
                    "(mount_session_id,asset_token_hash,user_id,tenant_id,installation_id,plugin_id,"
                    "plugin_version,artifact_sha256,catalog_release,capability_grants_json,"
                    "resource_scopes_json,data_scopes_json,revocation_version,status,authenticated_at,"
                    "created_at,expires_at,revoked_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'active',%s,%s,%s,%s)",
                    (
                        session.mount_session_id, session.asset_token_hash, session.user_id,
                        session.tenant_id, session.installation_id, session.plugin_id,
                        session.plugin_version, session.artifact_sha256, session.catalog_release,
                        json.dumps(session.capability_grants), json.dumps(session.resource_scopes),
                        json.dumps(session.data_scopes), session.revocation_version,
                        session.authenticated_at, session.created_at, session.expires_at,
                        session.revoked_at,
                    ),
                )

    def get_live_by_id(self, mount_session_id: str) -> PluginMountSession:
        return self._select_live("s.mount_session_id=%s", mount_session_id)

    def get_live_by_token_hash(self, token_hash: str) -> PluginMountSession:
        return self._select_live("s.asset_token_hash=%s", token_hash)

    def _select_live(self, predicate: str, value: str) -> PluginMountSession:
        with self._connections() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT s.* FROM {self.TABLE} s "
                    "JOIN workmanship_plugin_installations i "
                    "ON i.tenant_gid=s.tenant_id AND i.plugin_id=s.plugin_id "
                    "AND i.installation_id=s.installation_id "
                    "JOIN workmanship_plugin_releases r "
                    "ON r.plugin_id=s.plugin_id AND r.version=s.plugin_version "
                    f"WHERE {predicate} AND s.status='active' AND s.revoked_at IS NULL "
                    "AND s.expires_at>NOW() AND i.mount_revocation_version=s.revocation_version "
                    "AND i.state IN ('enabled','rolled_back') AND i.current_version=s.plugin_version "
                    "AND r.status='published' AND r.artifact_sha256=s.artifact_sha256",
                    (value,),
                )
                row = cursor.fetchone()
        if not row:
            raise MountSessionError("mount session invalid, expired, or revoked")
        return _session_from_row(row)


class MountSessionService:
    def __init__(self, store: MountSessionStore, *,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._store = store
        self._clock = clock

    def issue(
        self,
        *,
        user_id: str,
        tenant_id: str,
        installation_id: str,
        plugin_id: str,
        plugin_version: str,
        artifact_sha256: str,
        catalog_release: str,
        capability_grants: tuple[str, ...],
        resource_scopes: tuple[str, ...],
        data_scopes: tuple[str, ...],
        revocation_version: int,
        authenticated_at: datetime,
        ttl: timedelta = timedelta(minutes=15),
    ) -> IssuedMountSession:
        if ttl < timedelta(seconds=30) or ttl > timedelta(hours=24):
            raise MountSessionError("invalid mount session ttl")
        now = self._clock()
        expires_at = now + ttl
        mount_session_id = f"mount_{secrets.token_hex(16)}"
        asset_token = _issue_asset_token(mount_session_id, expires_at)
        token_hash = hashlib.sha256(asset_token.encode("utf-8")).hexdigest()
        session = PluginMountSession(
            mount_session_id=mount_session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            installation_id=installation_id,
            plugin_id=plugin_id,
            plugin_version=plugin_version,
            artifact_sha256=artifact_sha256,
            catalog_release=catalog_release,
            capability_grants=tuple(sorted(set(capability_grants))),
            resource_scopes=tuple(sorted(set(resource_scopes))),
            data_scopes=tuple(sorted(set(data_scopes))),
            revocation_version=revocation_version,
            asset_token_hash=token_hash,
            authenticated_at=authenticated_at,
            created_at=now,
            expires_at=expires_at,
        )
        self._store.save(session)
        return IssuedMountSession(
            session=session, asset_token=asset_token, asset_token_hash=token_hash
        )

    def resolve_for_user(self, mount_session_id: str, *, current_user_id: str,
                         current_tenant_id: str) -> PluginMountSession:
        session = self._store.get_live_by_id(mount_session_id)
        if session.user_id != current_user_id:
            raise MountSessionError("mount session user mismatch")
        if session.tenant_id != current_tenant_id:
            raise MountSessionError("mount session tenant mismatch")
        return session

    def resolve_asset_token(
        self,
        token: str,
        *,
        expected_plugin_id: str | None = None,
        expected_version: str | None = None,
    ) -> AssetMountClaims:
        token_session_id, token_expiry = _verify_asset_token(token)
        if token_expiry <= self._clock():
            raise MountSessionError("mount asset token expired")
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        session = self._store.get_live_by_token_hash(token_hash)
        if session.mount_session_id != token_session_id:
            raise MountSessionError("mount asset token binding mismatch")
        if expected_plugin_id is not None and (
            session.plugin_id != expected_plugin_id or session.plugin_version != expected_version
        ):
            raise MountSessionError("mount asset route mismatch")
        return AssetMountClaims(
            mount_session_id=session.mount_session_id,
            tenant_id=session.tenant_id,
            plugin_id=session.plugin_id,
            plugin_version=session.plugin_version,
            artifact_sha256=session.artifact_sha256,
            expires_at=session.expires_at,
        )


def _issue_asset_token(mount_session_id: str, expires_at: datetime) -> str:
    payload = {
        "sid": mount_session_id,
        "exp": int(expires_at.timestamp()),
        "nonce": secrets.token_urlsafe(16),
    }
    encoded = _encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    signature = _encode(hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def _verify_asset_token(token: str) -> tuple[str, datetime]:
    try:
        encoded, supplied = token.split(".", 1)
        expected = _encode(hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, supplied):
            raise MountSessionError("invalid mount asset token signature")
        value = json.loads(_decode(encoded))
        return str(value["sid"]), datetime.fromtimestamp(int(value["exp"]), tz=UTC)
    except MountSessionError:
        raise
    except Exception as exc:
        raise MountSessionError("malformed mount asset token") from exc


def _session_from_row(row) -> PluginMountSession:
    def tuple_field(name: str) -> tuple[str, ...]:
        value = row.get(name) or []
        if isinstance(value, (bytes, bytearray)):
            value = value.decode("utf-8")
        if isinstance(value, str):
            value = json.loads(value)
        return tuple(value)

    def utc(name: str) -> datetime | None:
        value = row.get(name)
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    return PluginMountSession(
        mount_session_id=row["mount_session_id"], user_id=row["user_id"],
        tenant_id=row["tenant_id"], installation_id=row["installation_id"],
        plugin_id=row["plugin_id"], plugin_version=row["plugin_version"],
        artifact_sha256=row["artifact_sha256"], catalog_release=row["catalog_release"],
        capability_grants=tuple_field("capability_grants_json"),
        resource_scopes=tuple_field("resource_scopes_json"),
        data_scopes=tuple_field("data_scopes_json"),
        revocation_version=int(row["revocation_version"]),
        asset_token_hash=row["asset_token_hash"], authenticated_at=utc("authenticated_at"),
        created_at=utc("created_at"), expires_at=utc("expires_at"), revoked_at=utc("revoked_at"),
    )
