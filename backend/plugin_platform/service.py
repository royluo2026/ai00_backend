"""Persistent marketplace catalog and tenant installation control plane."""
from __future__ import annotations

import json
import hashlib
import os
import re
import secrets
from contextlib import contextmanager
from copy import deepcopy
from typing import Any, Callable, Iterator, Protocol

from backend.capability_v2.contracts import ConsumerIdentity, ConsumerType
from backend.domain_ports.resource_authorization import resource_authorizers

from .lifecycle import begin_upgrade, require_transition, rollback as plan_rollback
from .manifest import ManifestError, PluginManifestV2, parse_manifest
from .signing import SignatureError, canonical_release, fingerprint, sign, verify


_PLUGIN_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9.-]{2,127}")


def _authorize_plugin_installation(
    plugin_id: str, identity: ConsumerIdentity
) -> bool:
    """Bridge a managed Web lifecycle call to its tenant-scoped installation.

    The Gateway has already enforced ``system.plugin.manage`` before consulting
    this resource authorizer.  Lifecycle services derive the target tenant from
    the authenticated actor context, so accepting the plugin identifier here
    cannot select another tenant's installation.
    """
    return bool(
        identity.consumer.type is ConsumerType.WEB
        and identity.actor.user_id
        and identity.tenant.tenant_id
        and _PLUGIN_ID_PATTERN.fullmatch(plugin_id)
        and ".." not in plugin_id
    )


resource_authorizers.register("plugin-installation", _authorize_plugin_installation)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _decode(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _tenant(context) -> str:
    return context.team_gid or f"user:{context.user_gid}"


def _tenant_for_user(user: dict) -> str:
    return user.get("team_id") or f"user:{user['gid']}"


def platform_public_key() -> str:
    """Return only the separately configured verifier key; publication fails closed without it."""
    value = os.getenv("AI00_PLUGIN_PLATFORM_ED25519_PUBLIC_KEY", "").replace("\\n", "\n")
    if not value:
        raise SignatureError("platform verification key is not configured")
    return value


def validate_capability_grants(values: Any) -> tuple[str, ...]:
    """Reject unknown or platform-internal capabilities before a release can be installed."""
    grants = tuple(sorted({str(value) for value in (values or ())}))
    from backend.capability_v2.bootstrap import get_capability_registry
    capability_registry = get_capability_registry()
    for capability_id in grants:
        try:
            spec = capability_registry.get(capability_id).spec
        except KeyError as exc:
            raise ValueError(f"unknown plugin capability: {capability_id}") from exc
        if not spec.plugin_callable:
            raise ValueError(f"capability is not exposed to plugins: {capability_id}")
    return grants


class PluginLifecycleError(ValueError):
    """Closed marketplace installation lifecycle failure."""

    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(f"{code}: {message or code}")
        self.code = code


_INSTALL_COMMAND_KEYS = {"plugin_id", "release_version", "release_sha256", "requested_grants", "idempotency_key"}
_UNINSTALL_COMMAND_KEYS = {"plugin_id", "expected_revision", "retain_tenant_data", "idempotency_key"}


def _lifecycle_invalid(message: str = "invalid_input") -> None:
    raise PluginLifecycleError("invalid_input", message)


def _lifecycle_text(value: Any, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        _lifecycle_invalid()
    return value.strip()


def _lifecycle_actor(actor: dict[str, Any]) -> tuple[str, str]:
    if not isinstance(actor, dict):
        _lifecycle_invalid("invalid_actor")
    return _lifecycle_text(actor.get("gid"), maximum=128), _lifecycle_text(actor.get("tenant_gid"), maximum=128)


def _command_digest(command: dict[str, Any]) -> str:
    return hashlib.sha256(_json(command).encode("utf-8")).hexdigest()


class DependencyResolver(Protocol):
    def resolve(self, *, tenant_gid: str, manifest: PluginManifestV2) -> None: ...


class ActiveCatalogReleasePort:
    """Resolve from the immutable Catalog release currently bound to the gateway."""
    def resolve(self, capability_id: str, major: int) -> Any:
        from backend.capability_v2.gateway import get_default_gateway
        return get_default_gateway().catalog().descriptor(capability_id, major)


class CatalogDependencyResolver:
    """Resolve signed dependencies through the stable Catalog and tenant installation port."""

    def __init__(self, installations: Any, *, catalog_release_port: Any | None = None) -> None:
        self.installations = installations
        self.catalog_release_port = catalog_release_port or ActiveCatalogReleasePort()

    def resolve(self, *, tenant_gid: str, manifest: PluginManifestV2) -> None:
        for requirement in manifest.capabilities.required:
            try:
                capability = self.catalog_release_port.resolve(requirement.id, requirement.major)
            except KeyError as exc:
                raise PluginLifecycleError(
                    "release_not_verified", "required stable plugin capability dependency is unavailable"
                ) from exc
            lifecycle = getattr(getattr(capability, "lifecycle_status", None), "value", getattr(capability, "lifecycle_status", None))
            if capability is None or lifecycle != "stable" or not bool(getattr(getattr(capability, "exposure", None), "plugin", False)):
                raise PluginLifecycleError("release_not_verified", "required stable plugin capability dependency is unavailable")
        for requirement in manifest.plugins.required:
            installation = self.installations.installation(tenant_gid, requirement.plugin_id, lock=True)
            if installation is None or installation.get("state") == "uninstalled" or installation.get("release_version") != requirement.version:
                raise PluginLifecycleError("release_not_verified", "required plugin dependency is unavailable")


class SqlPluginLifecycleRepository:
    """Existing marketplace schema adapter with Base-owned lifecycle evidence."""

    def __init__(self) -> None:
        self._conn: Any | None = None

    @contextmanager
    def transaction(self) -> Iterator["SqlPluginLifecycleRepository"]:
        from backend.db.connection import get_conn

        with get_conn() as conn:
            self._conn = conn
            try:
                yield self
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                self._conn = None

    def _cursor(self) -> Any:
        if self._conn is None:
            raise RuntimeError("plugin lifecycle repository used outside a transaction")
        return self._conn.cursor()

    def release(self, plugin_id: str, version: str, *, lock: bool = False) -> dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM workmanship_plugin_releases WHERE plugin_id=%s AND version=%s" + (" FOR UPDATE" if lock else ""),
                (plugin_id, version),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def installation(self, tenant_gid: str, plugin_id: str, *, lock: bool = False) -> dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM workmanship_plugin_installations WHERE tenant_gid=%s AND plugin_id=%s" + (" FOR UPDATE" if lock else ""),
                (tenant_gid, plugin_id),
            )
            row = cur.fetchone()
        return self._row(dict(row)) if row else None

    def list_installations(self, tenant_gid: str) -> list[dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM workmanship_plugin_installations WHERE tenant_gid=%s ORDER BY plugin_id", (tenant_gid,))
            rows = cur.fetchall()
        return [self._row(dict(row)) for row in rows]

    def save_installation(self, row: dict[str, Any]) -> None:
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_plugin_installations "
                "(tenant_gid,plugin_id,current_version,previous_version,state,granted_capabilities,installed_by,installation_id,mount_revocation_version,revision) "
                "VALUES (%s,%s,%s,NULL,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                "current_version=VALUES(current_version),previous_version=NULL,state=VALUES(state),"
                "granted_capabilities=VALUES(granted_capabilities),installed_by=VALUES(installed_by),"
                "installation_id=VALUES(installation_id),mount_revocation_version=VALUES(mount_revocation_version),revision=VALUES(revision),updated_at=NOW()",
                (row["tenant_gid"], row["plugin_id"], row["release_version"], row["state"],
                 _json(row["granted_capabilities"]), row["installed_by"], row["installation_id"],
                 row["mount_revocation_version"], row["revision"]),
            )

    def claim(self, *, tenant_gid: str, actor_gid: str, operation: str, idempotency_key: str, command_sha256: str) -> dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_base_plugin_lifecycle_idempotency "
                "(tenant_gid,actor_gid,operation,idempotency_key,command_sha256,status) VALUES (%s,%s,%s,%s,%s,'pending') "
                "ON DUPLICATE KEY UPDATE tenant_gid=VALUES(tenant_gid)",
                (tenant_gid, actor_gid, operation, idempotency_key, command_sha256),
            )
            cur.execute(
                "SELECT status,result_json,command_sha256 FROM workmanship_base_plugin_lifecycle_idempotency "
                "WHERE tenant_gid=%s AND actor_gid=%s AND operation=%s AND idempotency_key=%s FOR UPDATE",
                (tenant_gid, actor_gid, operation, idempotency_key),
            )
            row = cur.fetchone()
        if row and str(row.get("command_sha256") or "") != command_sha256:
            raise PluginLifecycleError("idempotency_conflict", "idempotency key is already bound to a different command")
        return _decode(row.get("result_json")) if row and row.get("status") == "completed" else None

    def complete(self, *, tenant_gid: str, actor_gid: str, operation: str, idempotency_key: str, command_sha256: str, result: dict[str, Any]) -> None:
        with self._cursor() as cur:
            cur.execute(
                "UPDATE workmanship_base_plugin_lifecycle_idempotency SET status='completed',result_json=%s,completed_at=CURRENT_TIMESTAMP(6) "
                "WHERE tenant_gid=%s AND actor_gid=%s AND operation=%s AND idempotency_key=%s AND command_sha256=%s",
                (_json(result), tenant_gid, actor_gid, operation, idempotency_key, command_sha256),
            )

    def revoke_mounts(self, *, tenant_gid: str, plugin_id: str, installation_id: str, new_revision: int) -> None:
        with self._cursor() as cur:
            cur.execute(
                "UPDATE workmanship_plugin_mount_sessions SET status='revoked',revoked_at=UTC_TIMESTAMP(6) "
                "WHERE tenant_id=%s AND plugin_id=%s AND installation_id=%s AND status='active'",
                (tenant_gid, plugin_id, installation_id),
            )

    def preserve_tenant_data(self, *, tenant_gid: str, plugin_id: str, retain: bool) -> None:
        if not retain:
            _lifecycle_invalid("uninstall never purges tenant data")
        with self._cursor() as cur:
            # Lock policy/data rows in the same transaction; uninstall is recoverable and never deletes them.
            cur.execute(
                "SELECT plugin_id FROM workmanship_plugin_namespace_kv WHERE tenant_gid=%s AND plugin_id=%s FOR UPDATE",
                (tenant_gid, plugin_id),
            )

    def audit(self, event: dict[str, Any]) -> None:
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_plugin_lifecycle_events "
                "(gid,tenant_gid,plugin_id,from_state,to_state,version,actor_gid,detail) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (f"ple_{secrets.token_hex(16)}", event["tenant_gid"], event["plugin_id"], event.get("from_state"),
                 event["to_state"], event["release_version"], event["actor_gid"], _json(event["details"])),
            )

    @staticmethod
    def _row(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "tenant_gid": str(row["tenant_gid"]), "plugin_id": str(row["plugin_id"]),
            "release_version": str(row["current_version"]), "state": str(row["state"]),
            "granted_capabilities": list(_decode(row.get("granted_capabilities") or [])),
            "installed_by": str(row["installed_by"]), "installation_id": str(row.get("installation_id") or ""),
            "mount_revocation_version": int(row.get("mount_revocation_version") or 1),
            "revision": int(row.get("revision") or 1),
        }


class PluginPlatformService:
    """The sole owner of browser install/uninstall transitions."""

    def __init__(
        self,
        *,
        repository: Any | None = None,
        platform_public_key_provider: Callable[[], str] | None = None,
        dependency_resolver: DependencyResolver | None = None,
    ) -> None:
        self.repository = repository or SqlPluginLifecycleRepository()
        self.platform_public_key_provider = platform_public_key_provider or platform_public_key
        self.dependency_resolver = dependency_resolver or CatalogDependencyResolver(self.repository)

    def list_installed(self, *, actor: dict) -> dict[str, Any]:
        _actor_gid, tenant_gid = _lifecycle_actor(actor)
        with self.repository.transaction():
            rows = self.repository.list_installations(tenant_gid)
        return {"installations": [self._result(row) for row in rows]}

    def request_install(self, *, actor: dict, command: dict) -> dict:
        command = self._install_command(command)
        actor_gid, tenant_gid = _lifecycle_actor(actor)
        command_sha256 = _command_digest(command)
        with self.repository.transaction():
            replay = self.repository.claim(tenant_gid=tenant_gid, actor_gid=actor_gid, operation="request.create", idempotency_key=command["idempotency_key"], command_sha256=command_sha256)
            if replay is not None:
                return replay
            release = self.repository.release(command["plugin_id"], command["release_version"], lock=True)
            self._verified_release(release, command, tenant_gid=tenant_gid)
            existing = self.repository.installation(tenant_gid, command["plugin_id"], lock=True)
            if existing is not None and existing["state"] != "uninstalled":
                raise PluginLifecycleError("already_installed", "plugin is already installed")
            revision = (existing["revision"] + 1) if existing else 1
            row = {
                "tenant_gid": tenant_gid, "plugin_id": command["plugin_id"], "release_version": command["release_version"],
                "state": "disabled", "granted_capabilities": command["requested_grants"], "installed_by": actor_gid,
                "installation_id": f"installation_{secrets.token_hex(16)}", "mount_revocation_version": (existing or {}).get("mount_revocation_version", 0) + 1,
                "revision": revision,
            }
            self.repository.save_installation(row)
            result = self._result(row)
            self.repository.complete(tenant_gid=tenant_gid, actor_gid=actor_gid, operation="request.create", idempotency_key=command["idempotency_key"], command_sha256=command_sha256, result=result)
            self.repository.audit({"tenant_gid": tenant_gid, "plugin_id": row["plugin_id"], "from_state": existing["state"] if existing else None,
                                   "to_state": "disabled", "release_version": row["release_version"], "actor_gid": actor_gid,
                                   "operation": "request.create", "details": {"operation": "request.create", "grants": row["granted_capabilities"], "revision": revision}})
            return result

    def transition_uninstall(self, *, actor: dict, command: dict) -> dict:
        command = self._uninstall_command(command)
        actor_gid, tenant_gid = _lifecycle_actor(actor)
        command_sha256 = _command_digest(command)
        with self.repository.transaction():
            replay = self.repository.claim(tenant_gid=tenant_gid, actor_gid=actor_gid, operation="transition.uninstall", idempotency_key=command["idempotency_key"], command_sha256=command_sha256)
            if replay is not None:
                return replay
            row = self.repository.installation(tenant_gid, command["plugin_id"], lock=True)
            if row is None:
                raise PluginLifecycleError("resource_not_found", "plugin installation not found")
            if row["revision"] != command["expected_revision"]:
                raise PluginLifecycleError("revision_conflict", "plugin installation changed")
            try:
                require_transition(row["state"], "uninstalled")
            except ValueError as exc:
                raise PluginLifecycleError("invalid_transition", str(exc)) from exc
            # The release and plugin namespace are locked before any state changes.
            if self.repository.release(row["plugin_id"], row["release_version"], lock=True) is None:
                raise PluginLifecycleError("release_not_verified", "installed release is unavailable")
            new_row = {**row, "state": "uninstalled", "granted_capabilities": [], "revision": row["revision"] + 1,
                       "mount_revocation_version": row["mount_revocation_version"] + 1}
            self.repository.revoke_mounts(tenant_gid=tenant_gid, plugin_id=row["plugin_id"], installation_id=row["installation_id"], new_revision=new_row["mount_revocation_version"])
            self.repository.preserve_tenant_data(tenant_gid=tenant_gid, plugin_id=row["plugin_id"], retain=command["retain_tenant_data"])
            self.repository.save_installation(new_row)
            result = self._result(new_row)
            self.repository.complete(tenant_gid=tenant_gid, actor_gid=actor_gid, operation="transition.uninstall", idempotency_key=command["idempotency_key"], command_sha256=command_sha256, result=result)
            self.repository.audit({"tenant_gid": tenant_gid, "plugin_id": row["plugin_id"], "from_state": row["state"], "to_state": "uninstalled",
                                   "release_version": row["release_version"], "actor_gid": actor_gid,
                                   "operation": "transition.uninstall", "details": {"operation": "transition.uninstall", "grants_revoked": row["granted_capabilities"], "data_retained": True, "revision": new_row["revision"]}})
            return result

    @staticmethod
    def _install_command(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict) or set(value) != _INSTALL_COMMAND_KEYS:
            _lifecycle_invalid()
        command = deepcopy(value)
        command["plugin_id"] = _lifecycle_text(command["plugin_id"], maximum=255)
        command["release_version"] = _lifecycle_text(command["release_version"], maximum=64)
        command["idempotency_key"] = _lifecycle_text(command["idempotency_key"])
        if not isinstance(command["release_sha256"], str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", command["release_sha256"]):
            _lifecycle_invalid()
        if not isinstance(command["requested_grants"], list):
            _lifecycle_invalid()
        if (not all(isinstance(item, str) and re.fullmatch(r"[a-z][a-z0-9_.-]{2,127}", item) for item in command["requested_grants"])
                or command["requested_grants"] != sorted(set(command["requested_grants"]))):
            _lifecycle_invalid()
        return command

    @staticmethod
    def _uninstall_command(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict) or set(value) != _UNINSTALL_COMMAND_KEYS:
            _lifecycle_invalid()
        command = deepcopy(value)
        command["plugin_id"] = _lifecycle_text(command["plugin_id"], maximum=255)
        command["idempotency_key"] = _lifecycle_text(command["idempotency_key"])
        if isinstance(command["expected_revision"], bool) or not isinstance(command["expected_revision"], int) or command["expected_revision"] < 1:
            _lifecycle_invalid()
        if command["retain_tenant_data"] is not True:
            _lifecycle_invalid("uninstall never purges tenant data")
        return command

    def _verified_release(self, release: dict[str, Any] | None, command: dict[str, Any], *, tenant_gid: str) -> None:
        if not release or release.get("status") != "published" or not release.get("platform_signature"):
            raise PluginLifecycleError("release_not_verified", "release is not published and platform-signed")
        actual_hash = str(release.get("artifact_sha256") or "")
        if command["release_sha256"] != f"sha256:{actual_hash}":
            raise PluginLifecycleError("release_not_verified", "release hash does not match signed release")
        try:
            stored_manifest = _decode(release.get("manifest"))
            if not isinstance(stored_manifest, dict):
                raise ManifestError("release manifest must be an object")
            verify(self.platform_public_key_provider(), canonical_release(stored_manifest, actual_hash), str(release["platform_signature"]))
            manifest = parse_manifest(deepcopy(stored_manifest))
            if manifest.artifact.sha256 != actual_hash:
                raise PluginLifecycleError("release_not_verified", "release artifact does not match signed manifest")
            self.dependency_resolver.resolve(tenant_gid=tenant_gid, manifest=manifest)
        except PluginLifecycleError:
            raise
        except (ManifestError, SignatureError, TypeError, ValueError) as exc:
            raise PluginLifecycleError("release_not_verified", "release signature or dependencies cannot be verified") from exc
        allowed = list(manifest.permissions)
        if sorted(command["requested_grants"]) != sorted(allowed):
            raise PluginLifecycleError("invalid_input", "requested grants must exactly match signed release grants")

    @staticmethod
    def _result(row: dict[str, Any]) -> dict[str, Any]:
        return {"plugin_id": row["plugin_id"], "release_version": row["release_version"], "state": row["state"],
                "revision": row["revision"], "granted_capabilities": list(row["granted_capabilities"]), "tenant_gid": row["tenant_gid"]}


def _event(cur, tenant: str, plugin_id: str, old: str | None, new: str, version: str, actor: str, detail: dict | None = None) -> None:
    cur.execute(
        "INSERT INTO workmanship_plugin_lifecycle_events (gid,tenant_gid,plugin_id,from_state,to_state,version,actor_gid,detail) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (f"ple_{secrets.token_hex(16)}", tenant, plugin_id, old, new, version, actor, _json(detail or {})),
    )


def register_publisher(publisher_id: str, display_name: str, public_key_pem: str, actor_gid: str) -> dict:
    key_fingerprint = fingerprint(public_key_pem)
    if not publisher_id or "." in publisher_id or len(publisher_id) > 128:
        raise ValueError("publisher_id must be a single lowercase namespace segment")
    if not publisher_id.replace("-", "").isalnum() or publisher_id.lower() != publisher_id:
        raise ValueError("publisher_id must contain lowercase letters, digits, or hyphens")
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT publisher_id FROM workmanship_plugin_publishers WHERE publisher_id=%s", (publisher_id,))
            if cur.fetchone():
                raise ValueError("publisher already exists; key rotation requires a separate audited operation")
            cur.execute(
                "INSERT INTO workmanship_plugin_publishers (publisher_id,display_name,public_key_pem,key_fingerprint,created_by) VALUES (%s,%s,%s,%s,%s)",
                (publisher_id, display_name[:255], public_key_pem, key_fingerprint, actor_gid),
            )
        conn.commit()
    return {"publisher_id": publisher_id, "key_fingerprint": key_fingerprint, "status": "active"}


def verify_submission_signature(manifest_value: dict, publisher_signature: str) -> None:
    manifest = parse_manifest(manifest_value)
    normalized = manifest.model_dump(mode="json")
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT public_key_pem FROM workmanship_plugin_publishers WHERE publisher_id=%s AND status='active'", (manifest.publisher_id,))
            publisher = cur.fetchone()
    if not publisher:
        raise ValueError("publisher is not active")
    verify(publisher["public_key_pem"], canonical_release(normalized, manifest.artifact.sha256), publisher_signature)

def submit_release(manifest_value: dict, publisher_signature: str, actor_gid: str) -> dict:
    manifest = parse_manifest(manifest_value)
    normalized = manifest.model_dump(mode="json")
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM workmanship_plugin_publishers WHERE publisher_id=%s AND status='active'", (manifest.publisher_id,))
            publisher = cur.fetchone()
            if not publisher:
                raise ValueError("publisher is not active")
            verify(publisher["public_key_pem"], canonical_release(normalized, manifest.artifact.sha256), publisher_signature)
            cur.execute("SELECT status FROM workmanship_plugin_releases WHERE plugin_id=%s AND version=%s", (manifest.plugin_id, manifest.version))
            if cur.fetchone():
                raise ValueError("release version is immutable and already exists")
            cur.execute(
                "INSERT INTO workmanship_plugin_releases (plugin_id,version,publisher_id,manifest,artifact_object_key,artifact_sha256,publisher_signature,submitted_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (manifest.plugin_id, manifest.version, manifest.publisher_id, _json(normalized), manifest.artifact.object_key, manifest.artifact.sha256, publisher_signature, actor_gid),
            )
        conn.commit()
    return {"plugin_id": manifest.plugin_id, "version": manifest.version, "status": "submitted"}


def review_release(plugin_id: str, version: str, approved: bool, note: str, actor_gid: str) -> dict:
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM workmanship_plugin_releases WHERE plugin_id=%s AND version=%s FOR UPDATE", (plugin_id, version))
            row = cur.fetchone()
            if not row or row["status"] != "submitted":
                raise ValueError("only submitted releases can be reviewed")
            status = "rejected"
            platform_signature = None
            if approved:
                private_key = os.getenv("AI00_PLUGIN_PLATFORM_ED25519_PRIVATE_KEY", "").replace("\\n", "\n")
                if not private_key:
                    raise SignatureError("platform signing key is not configured; unsigned release cannot be published")
                manifest = parse_manifest(_decode(row["manifest"]))
                normalized = manifest.model_dump(mode="json")
                validate_capability_grants(normalized["permissions"])
                platform_signature = sign(private_key, canonical_release(normalized, row["artifact_sha256"]))
                status = "published"
            cur.execute(
                "UPDATE workmanship_plugin_releases SET status=%s,manifest=%s,platform_signature=%s,review_note=%s,reviewed_by=%s,updated_at=NOW() WHERE plugin_id=%s AND version=%s",
                (status, _json(normalized) if approved else row["manifest"], platform_signature, note[:4000], actor_gid, plugin_id, version),
            )
        conn.commit()
    return {"plugin_id": plugin_id, "version": version, "status": status}


def revoke_release(plugin_id: str, version: str, reason: str, actor_gid: str) -> dict:
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM workmanship_plugin_releases WHERE plugin_id=%s AND version=%s FOR UPDATE", (plugin_id, version))
            release = cur.fetchone()
            if not release or release["status"] != "published":
                raise ValueError("only a published release can be revoked")
            cur.execute("SELECT tenant_gid,state FROM workmanship_plugin_installations WHERE plugin_id=%s AND current_version=%s AND state<>'uninstalled' FOR UPDATE", (plugin_id, version))
            installations = list(cur.fetchall())
            cur.execute("UPDATE workmanship_plugin_releases SET status='revoked',review_note=%s,reviewed_by=%s,updated_at=NOW() WHERE plugin_id=%s AND version=%s", (reason[:4000], actor_gid, plugin_id, version))
            for installation in installations:
                old = installation["state"]
                if old != "revoked":
                    require_transition(old, "revoked")
                    cur.execute("UPDATE workmanship_plugin_installations SET state='revoked',last_error=%s,"
                                "mount_revocation_version=mount_revocation_version+1,updated_at=NOW() "
                                "WHERE tenant_gid=%s AND plugin_id=%s", (reason[:4000], installation["tenant_gid"], plugin_id))
                    _event(cur, installation["tenant_gid"], plugin_id, old, "revoked", version, actor_gid, {"reason": reason})
        conn.commit()
    return {"plugin_id": plugin_id, "version": version, "status": "revoked", "affected_installations": len(installations)}

def list_catalog() -> list[dict]:
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT plugin_id,version,publisher_id,manifest,artifact_sha256,platform_signature,updated_at FROM workmanship_plugin_releases WHERE status='published' ORDER BY plugin_id,updated_at DESC")
            rows = list(cur.fetchall())
    for row in rows:
        row["manifest"] = _decode(row["manifest"])
        row["platform_signed"] = bool(row.get("platform_signature"))
        row["updated_at"] = row["updated_at"].isoformat() if hasattr(row.get("updated_at"), "isoformat") else str(row.get("updated_at"))
    return rows


def list_releases(status: str | None = None) -> list[dict]:
    """Return the small admin review queue without exposing signature material."""
    allowed = {"submitted", "published", "rejected", "revoked"}
    if status is not None and status not in allowed:
        raise ValueError("invalid release status")
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            sql = (
                "SELECT plugin_id,version,publisher_id,manifest,artifact_sha256,status,"
                "review_note,submitted_by,reviewed_by,created_at,updated_at "
                "FROM workmanship_plugin_releases"
            )
            params: tuple = ()
            if status is not None:
                sql += " WHERE status=%s"
                params = (status,)
            sql += " ORDER BY updated_at DESC"
            cur.execute(sql, params)
            rows = [dict(row) for row in cur.fetchall()]
    for row in rows:
        row["manifest"] = _decode(row.get("manifest") or {})
        for field in ("created_at", "updated_at"):
            value = row.get(field)
            row[field] = value.isoformat() if hasattr(value, "isoformat") else str(value or "")
    return rows

def _release(cur, plugin_id: str, version: str) -> dict:
    cur.execute("SELECT * FROM workmanship_plugin_releases WHERE plugin_id=%s AND version=%s AND status='published'", (plugin_id, version))
    row = cur.fetchone()
    if not row or not row.get("platform_signature"):
        raise ValueError("release is not published and platform-signed")
    from .compatibility import satisfies
    manifest = _decode(row["manifest"])
    platform_api = os.getenv("AI00_PLATFORM_API_VERSION", "1.0.0")
    web_sdk = os.getenv("AI00_WEB_PLUGIN_SDK_VERSION", "0.1.0")
    if not satisfies(platform_api, manifest["compatibility"]["platform_api"]):
        raise ValueError("release is incompatible with current platform API")
    if not satisfies(web_sdk, manifest["compatibility"]["web_sdk"]):
        raise ValueError("release is incompatible with current Web Plugin SDK")
    return row


def _apply_uninstall_data_policy(cur, tenant: str, plugin_id: str, version: str) -> str:
    cur.execute("SELECT manifest FROM workmanship_plugin_releases WHERE plugin_id=%s AND version=%s", (plugin_id, version))
    release = cur.fetchone()
    manifest = _decode(release["manifest"]) if release else {}
    policy = manifest.get("data") or {}
    action = policy.get("uninstall", "delete")
    retention = policy.get("retention", "none")
    if action == "export-then-delete":
        raise ValueError("plugin data export is required before uninstall")
    if action == "delete" or retention in ("none", "while-installed"):
        cur.execute("DELETE FROM workmanship_plugin_namespace_kv WHERE tenant_gid=%s AND plugin_id=%s", (tenant, plugin_id))
        return "deleted"
    return "retained"


def install(payload: dict, context) -> dict:
    plugin_id, version = str(payload.get("plugin_id", "")), str(payload.get("version", ""))
    tenant = _tenant(context)
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            release = _release(cur, plugin_id, version)
            cur.execute("SELECT state FROM workmanship_plugin_installations WHERE tenant_gid=%s AND plugin_id=%s FOR UPDATE", (tenant, plugin_id))
            existing = cur.fetchone()
            if existing and existing["state"] != "uninstalled": raise ValueError("plugin is already installed; use upgrade")
            manifest = _decode(release["manifest"])
            requested = validate_capability_grants(manifest.get("permissions", []))
            consented = validate_capability_grants(payload.get("granted_capabilities", []))
            if set(consented) != set(requested):
                raise ValueError("granted_capabilities must exactly match the signed manifest permissions")
            installation_id = f"installation_{secrets.token_hex(16)}"
            if existing:
                cur.execute(
                    "UPDATE workmanship_plugin_installations SET current_version=%s,previous_version=NULL,state='disabled',"
                    "granted_capabilities=%s,previous_granted_capabilities=NULL,installed_by=%s,last_error=NULL,"
                    "installation_id=%s,mount_revocation_version=mount_revocation_version+1,updated_at=NOW() "
                    "WHERE tenant_gid=%s AND plugin_id=%s",
                    (version, _json(consented), context.user_gid, installation_id, tenant, plugin_id),
                )
            else:
                cur.execute("INSERT INTO workmanship_plugin_installations "
                            "(tenant_gid,plugin_id,current_version,state,granted_capabilities,installed_by,installation_id,mount_revocation_version) "
                            "VALUES (%s,%s,%s,'disabled',%s,%s,%s,1)",
                            (tenant, plugin_id, version, _json(consented), context.user_gid, installation_id))
            _event(cur, tenant, plugin_id, "uninstalled" if existing else None, "disabled", version, context.user_gid, {"action": "reinstall" if existing else "install"})
        conn.commit()
    return {"plugin_id": plugin_id, "version": version, "state": "disabled"}


def transition(payload: dict, context, target: str) -> dict:
    plugin_id, tenant = str(payload.get("plugin_id", "")), _tenant(context)
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM workmanship_plugin_installations WHERE tenant_gid=%s AND plugin_id=%s FOR UPDATE", (tenant, plugin_id))
            row = cur.fetchone()
            if not row: raise ValueError("plugin is not installed")
            require_transition(row["state"], target)
            detail = None
            if target == "uninstalled":
                detail = {"data": _apply_uninstall_data_policy(cur, tenant, plugin_id, row["current_version"])}
            cur.execute("UPDATE workmanship_plugin_installations SET state=%s,"
                        "mount_revocation_version=mount_revocation_version+1,updated_at=NOW() "
                        "WHERE tenant_gid=%s AND plugin_id=%s", (target, tenant, plugin_id))
            _event(cur, tenant, plugin_id, row["state"], target, row["current_version"], context.user_gid, detail)
        conn.commit()
    return {"plugin_id": plugin_id, "version": row["current_version"], "state": target}


def upgrade(payload: dict, context) -> dict:
    plugin_id, version, tenant = str(payload.get("plugin_id", "")), str(payload.get("version", "")), _tenant(context)
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            release = _release(cur, plugin_id, version)
            manifest = _decode(release["manifest"])
            requested = validate_capability_grants(manifest.get("permissions", []))
            consented = validate_capability_grants(payload.get("granted_capabilities", []))
            if set(consented) != set(requested):
                raise ValueError("granted_capabilities must exactly match the new signed manifest permissions")
            cur.execute("SELECT * FROM workmanship_plugin_installations WHERE tenant_gid=%s AND plugin_id=%s FOR UPDATE", (tenant, plugin_id))
            row = cur.fetchone()
            if not row: raise ValueError("plugin is not installed")
            require_transition(row["state"], "upgrading")
            result = begin_upgrade(row["current_version"], version)
            cur.execute("UPDATE workmanship_plugin_installations SET current_version=%s,previous_version=%s,state='upgrading',"
                        "previous_granted_capabilities=granted_capabilities,granted_capabilities=%s,"
                        "mount_revocation_version=mount_revocation_version+1,updated_at=NOW() "
                        "WHERE tenant_gid=%s AND plugin_id=%s",
                        (result.current_version, result.previous_version, _json(consented), tenant, plugin_id))
            _event(cur, tenant, plugin_id, row["state"], "upgrading", version, context.user_gid, {"previous_version": row["current_version"]})
        conn.commit()
    return {"plugin_id": plugin_id, "version": version, "previous_version": result.previous_version, "state": "upgrading"}


def finish_upgrade(payload: dict, context) -> dict:
    plugin_id, healthy, tenant = str(payload.get("plugin_id", "")), bool(payload.get("healthy")), _tenant(context)
    target = "enabled" if healthy else "failed"
    return transition({"plugin_id": plugin_id}, context, target)


def rollback(payload: dict, context) -> dict:
    plugin_id, tenant = str(payload.get("plugin_id", "")), _tenant(context)
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM workmanship_plugin_installations WHERE tenant_gid=%s AND plugin_id=%s FOR UPDATE", (tenant, plugin_id))
            row = cur.fetchone()
            if not row: raise ValueError("plugin is not installed")
            require_transition(row["state"], "rolled_back")
            result = plan_rollback(row["current_version"], row.get("previous_version"))
            _release(cur, plugin_id, result.current_version)
            cur.execute("UPDATE workmanship_plugin_installations SET current_version=%s,previous_version=%s,state='rolled_back',"
                        "granted_capabilities=previous_granted_capabilities,previous_granted_capabilities=granted_capabilities,"
                        "mount_revocation_version=mount_revocation_version+1,updated_at=NOW() "
                        "WHERE tenant_gid=%s AND plugin_id=%s",
                        (result.current_version, result.previous_version, tenant, plugin_id))
            _event(cur, tenant, plugin_id, row["state"], "rolled_back", result.current_version, context.user_gid, {"rolled_back_from": row["current_version"]})
        conn.commit()
    return {"plugin_id": plugin_id, "version": result.current_version, "state": "rolled_back"}


def list_installations(user: dict) -> list[dict]:
    tenant = _tenant_for_user(user)
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT i.plugin_id,i.current_version,i.previous_version,i.state,i.granted_capabilities,"
                "i.previous_granted_capabilities,i.last_error,i.installed_by,i.created_at,i.updated_at,"
                "r.status AS release_status,r.publisher_id,r.manifest "
                "FROM workmanship_plugin_installations i "
                "LEFT JOIN workmanship_plugin_releases r ON r.plugin_id=i.plugin_id AND r.version=i.current_version "
                "WHERE i.tenant_gid=%s ORDER BY i.updated_at DESC",
                (tenant,),
            )
            rows = [dict(row) for row in cur.fetchall()]
    for row in rows:
        row["granted_capabilities"] = _decode(row.get("granted_capabilities") or [])
        row["previous_granted_capabilities"] = _decode(row.get("previous_granted_capabilities") or [])
        manifest = _decode(row.pop("manifest", None) or {})
        row["name"] = manifest.get("name") or row["plugin_id"]
        for field in ("created_at", "updated_at"):
            value = row.get(field)
            row[field] = value.isoformat() if hasattr(value, "isoformat") else str(value or "")
    return rows


def list_lifecycle_events(user: dict, plugin_id: str, limit: int = 100) -> list[dict]:
    tenant = _tenant_for_user(user)
    bounded_limit = max(1, min(int(limit), 500))
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid,plugin_id,from_state,to_state,version,actor_gid,detail,created_at "
                "FROM workmanship_plugin_lifecycle_events "
                "WHERE tenant_gid=%s AND plugin_id=%s ORDER BY created_at DESC LIMIT %s",
                (tenant, plugin_id, bounded_limit),
            )
            rows = [dict(row) for row in cur.fetchall()]
    for row in rows:
        row["detail"] = _decode(row.get("detail") or {})
        value = row.get("created_at")
        row["created_at"] = value.isoformat() if hasattr(value, "isoformat") else str(value or "")
    return rows


def tenant_registry(user: dict) -> list[dict]:
    tenant = user.get("team_id") or f"user:{user['gid']}"
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT i.plugin_id,i.current_version,i.granted_capabilities,"
                        "i.installation_id,i.mount_revocation_version,r.manifest,"
                        "r.artifact_object_key,r.artifact_sha256,r.platform_signature "
                        "FROM workmanship_plugin_installations i "
                        "JOIN workmanship_plugin_releases r "
                        "ON r.plugin_id=i.plugin_id AND r.version=i.current_version "
                        "WHERE i.tenant_gid=%s AND i.state IN ('enabled','rolled_back') "
                        "AND r.status='published'", (tenant,))
            rows = list(cur.fetchall())
    result = []
    for row in rows:
        manifest = _decode(row["manifest"])
        result.append({
            "name": manifest["name"], "plugin_id": row["plugin_id"],
            "version": row["current_version"], "web": manifest["runtimes"]["web"],
            "permissions": _decode(row["granted_capabilities"]),
            "capabilities": manifest.get("capabilities") or {"required": [], "optional": []},
            "installation_id": row.get("installation_id"),
            "mount_revocation_version": int(row.get("mount_revocation_version") or 1),
            "artifact": {"object_key": row["artifact_object_key"], "sha256": row["artifact_sha256"]},
            "platform_signed": bool(row["platform_signature"]),
            "platform_signature": row["platform_signature"],
        })
    return result


def resolve_asset_object_key(claims, asset_path: str) -> str:
    normalized = asset_path.replace("\\", "/").strip("/")
    if not normalized or ".." in normalized.split("/") or any(":" in part for part in normalized.split("/")):
        raise PermissionError("unsafe plugin asset path")
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            version = getattr(claims, "plugin_version", None) or getattr(claims, "version", None)
            tenant = getattr(claims, "tenant_id", None) or getattr(claims, "tenant_gid", None)
            cur.execute("SELECT r.publisher_id FROM workmanship_plugin_installations i JOIN workmanship_plugin_releases r ON r.plugin_id=i.plugin_id AND r.version=i.current_version WHERE i.tenant_gid=%s AND i.plugin_id=%s AND i.current_version=%s AND i.state IN ('enabled','rolled_back') AND r.status='published' AND r.artifact_sha256=%s", (tenant, claims.plugin_id, version, claims.artifact_sha256))
            row = cur.fetchone()
    if not row: raise PermissionError("plugin mount is disabled, revoked, changed, or unknown")
    return f"plugin-assets/{row['publisher_id']}/{claims.plugin_id}/{version}/{claims.artifact_sha256}/{normalized}"
