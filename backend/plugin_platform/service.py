"""Persistent marketplace catalog and tenant installation control plane."""
from __future__ import annotations

import json
import os
import secrets
from typing import Any

from .lifecycle import begin_upgrade, require_transition, rollback as plan_rollback
from .manifest import parse_manifest
from .signing import SignatureError, canonical_release, fingerprint, sign, verify


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


def validate_capability_grants(values: Any) -> tuple[str, ...]:
    """Reject unknown or platform-internal capabilities before a release can be installed."""
    grants = tuple(sorted({str(value) for value in (values or ())}))
    from backend.capabilities.registry_next import capability_registry
    for capability_id in grants:
        try:
            spec = capability_registry.get(capability_id).spec
        except KeyError as exc:
            raise ValueError(f"unknown plugin capability: {capability_id}") from exc
        if not spec.plugin_callable:
            raise ValueError(f"capability is not exposed to plugins: {capability_id}")
    return grants


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
                manifest = _decode(row["manifest"])
                validate_capability_grants(manifest.get("permissions", []))
                platform_signature = sign(private_key, canonical_release(manifest, row["artifact_sha256"]))
                status = "published"
            cur.execute(
                "UPDATE workmanship_plugin_releases SET status=%s,platform_signature=%s,review_note=%s,reviewed_by=%s,updated_at=NOW() WHERE plugin_id=%s AND version=%s",
                (status, platform_signature, note[:4000], actor_gid, plugin_id, version),
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
