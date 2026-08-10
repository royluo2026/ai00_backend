"""Revocable, hash-only delegation grants for non-Web consumers."""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime
from typing import Callable, Protocol

from pydantic import Field, model_validator

from .contracts import AutomationLevel, ConsumerType, FrozenModel, IDENTITY_PATTERN


class DelegationError(PermissionError):
    pass


class DelegationGrant(FrozenModel):
    delegation_id: str = Field(pattern=IDENTITY_PATTERN)
    delegated_by: str = Field(pattern=IDENTITY_PATTERN)
    user_id: str | None = Field(default=None, pattern=IDENTITY_PATTERN)
    service_id: str | None = Field(default=None, pattern=IDENTITY_PATTERN)
    tenant_id: str = Field(pattern=IDENTITY_PATTERN)
    consumer_type: ConsumerType
    consumer_id: str = Field(pattern=IDENTITY_PATTERN)
    consumer_version: str | None = Field(default=None, max_length=128)
    installation_id: str | None = Field(default=None, pattern=IDENTITY_PATTERN)
    mount_session_id: str | None = Field(default=None, pattern=IDENTITY_PATTERN)
    agent_run_id: str | None = Field(default=None, pattern=IDENTITY_PATTERN)
    catalog_release: str = Field(pattern=r"^rel_[0-9a-f]{32}$")
    capability_scopes: tuple[str, ...] = ()
    resource_scopes: tuple[str, ...] = ()
    data_scopes: tuple[str, ...] = ()
    maximum_automation_level: AutomationLevel
    authentication_method: str = Field(min_length=1, max_length=64)
    authenticated_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    @model_validator(mode="after")
    def grant_contract(self) -> "DelegationGrant":
        if (self.user_id is None) == (self.service_id is None):
            raise ValueError("delegation requires exactly one actor")
        for name, value in (
            ("authenticated_at", self.authenticated_at),
            ("expires_at", self.expires_at),
            ("revoked_at", self.revoked_at),
        ):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"{name} must be timezone-aware")
        if self.expires_at <= self.authenticated_at:
            raise ValueError("delegation expiry must follow authentication")
        return self


class IssuedDelegation(FrozenModel):
    grant: DelegationGrant
    token: str = Field(min_length=32)


class DelegationStore(Protocol):
    def save(self, token_hash: str, grant: DelegationGrant) -> None: ...
    def consume_active(self, token: str) -> DelegationGrant: ...
    def revoke(self, delegation_id: str) -> None: ...


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_delegation(store: DelegationStore, grant: DelegationGrant) -> IssuedDelegation:
    token = secrets.token_urlsafe(32)
    store.save(hash_token(token), grant)
    return IssuedDelegation(grant=grant, token=token)


class InMemoryDelegationStore:
    """Test-only store. Runtime wiring must use SqlDelegationStore."""

    def __init__(self, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._clock = clock
        self._records: dict[str, DelegationGrant] = {}

    def save(self, token_hash: str, grant: DelegationGrant) -> None:
        if token_hash in self._records or any(item.delegation_id == grant.delegation_id for item in self._records.values()):
            raise DelegationError("delegation_exists")
        self._records[token_hash] = grant

    def consume_active(self, token: str) -> DelegationGrant:
        grant = self._records.get(hash_token(token))
        if grant is None:
            raise DelegationError("delegation_invalid")
        if grant.revoked_at is not None:
            raise DelegationError("delegation_revoked")
        if grant.expires_at <= self._clock():
            raise DelegationError("delegation_expired")
        return grant

    def revoke(self, delegation_id: str) -> None:
        for token_hash, grant in self._records.items():
            if grant.delegation_id == delegation_id:
                self._records[token_hash] = grant.model_copy(update={"revoked_at": self._clock()})
                return
        raise DelegationError("delegation_not_found")

    def snapshot(self) -> tuple[tuple[str, DelegationGrant], ...]:
        return tuple(sorted(self._records.items(), key=lambda item: item[1].delegation_id))


class SqlDelegationStore:
    TABLE = "workmanship_base_consumer_delegations"

    def __init__(self, connection_factory, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._connection_factory = connection_factory
        self._clock = clock

    def save(self, token_hash: str, grant: DelegationGrant) -> None:
        conn = self._connection_factory()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"INSERT INTO {self.TABLE} "
                    "(delegation_id,token_hash,delegated_by,actor_user_id,actor_service_id,tenant_id,consumer_type,"
                    "consumer_id,consumer_version,installation_id,mount_session_id,agent_run_id,catalog_release,"
                    "capability_scopes_json,resource_scopes_json,data_scopes_json,maximum_automation_level,"
                    "authentication_method,authenticated_at,expires_at,revoked_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        grant.delegation_id, token_hash, grant.delegated_by, grant.user_id, grant.service_id, grant.tenant_id,
                        grant.consumer_type.value, grant.consumer_id, grant.consumer_version,
                        grant.installation_id, grant.mount_session_id, grant.agent_run_id, grant.catalog_release,
                        json.dumps(grant.capability_scopes), json.dumps(grant.resource_scopes),
                        json.dumps(grant.data_scopes), grant.maximum_automation_level.value,
                        grant.authentication_method, grant.authenticated_at, grant.expires_at, grant.revoked_at,
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def consume_active(self, token: str) -> DelegationGrant:
        conn = self._connection_factory()
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT * FROM {self.TABLE} WHERE token_hash=%s", (hash_token(token),))
                row = cursor.fetchone()
        finally:
            conn.close()
        if row is None:
            raise DelegationError("delegation_invalid")
        grant = _grant_from_row(row)
        if grant.revoked_at is not None:
            raise DelegationError("delegation_revoked")
        if grant.expires_at <= self._clock():
            raise DelegationError("delegation_expired")
        return grant

    def revoke(self, delegation_id: str) -> None:
        conn = self._connection_factory()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"UPDATE {self.TABLE} SET revoked_at=%s WHERE delegation_id=%s AND revoked_at IS NULL",
                    (self._clock(), delegation_id),
                )
                if cursor.rowcount != 1:
                    raise DelegationError("delegation_not_found")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _grant_from_row(row: dict) -> DelegationGrant:
    def json_tuple(name: str) -> tuple[str, ...]:
        value = row.get(name) or []
        if isinstance(value, (bytes, bytearray)):
            value = value.decode("utf-8")
        if isinstance(value, str):
            value = json.loads(value)
        return tuple(value)

    return DelegationGrant(
        delegation_id=row["delegation_id"], delegated_by=row["delegated_by"], user_id=row.get("actor_user_id"),
        service_id=row.get("actor_service_id"), tenant_id=row["tenant_id"],
        consumer_type=row["consumer_type"], consumer_id=row["consumer_id"],
        consumer_version=row.get("consumer_version"), installation_id=row.get("installation_id"),
        mount_session_id=row.get("mount_session_id"), agent_run_id=row.get("agent_run_id"),
        catalog_release=row["catalog_release"], capability_scopes=json_tuple("capability_scopes_json"),
        resource_scopes=json_tuple("resource_scopes_json"), data_scopes=json_tuple("data_scopes_json"),
        maximum_automation_level=row["maximum_automation_level"],
        authentication_method=row["authentication_method"], authenticated_at=row["authenticated_at"],
        expires_at=row["expires_at"], revoked_at=row.get("revoked_at"),
    )


__all__ = [
    "DelegationError",
    "DelegationGrant",
    "InMemoryDelegationStore",
    "IssuedDelegation",
    "SqlDelegationStore",
    "hash_token",
    "issue_delegation",
]
