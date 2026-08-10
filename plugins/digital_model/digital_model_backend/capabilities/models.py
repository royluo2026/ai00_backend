"""Digital Model identity, immutable snapshot, semantic diff and component capabilities."""
from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any, Mapping

from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError, CapabilityContext, CapabilityOutput, CapabilitySpec, EvidenceRef,
)
from backend.capability_v2.revision.digital_model_adapter import DigitalModelRevisionAdapter

from ..data.connection import get_digital_model_conn


def _json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return default
    return value


def _canonical(value: Mapping[str, Any]) -> tuple[str, str]:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return "sha256:" + digest, encoded.decode("utf-8")


class DigitalModelRepository:
    def create_model(self, row: Mapping[str, Any]) -> None:
        with get_digital_model_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO workmanship_model_models "
                    "(model_id,name,project_ref,owner_gid,team_gid,latest_version_id,created_at,updated_at) "
                    "VALUES (%s,%s,%s,%s,%s,NULL,NOW(),NOW())",
                    (row["model_id"], row["name"], row["project_ref"], row["owner_gid"], row.get("team_gid")),
                )
            conn.commit()

    def get_model(self, model_id: str, context: CapabilityContext) -> dict[str, Any] | None:
        with get_digital_model_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT model_id,name,project_ref,latest_version_id FROM workmanship_model_models "
                    "WHERE model_id=%s AND (owner_gid=%s OR (%s IS NOT NULL AND team_gid=%s))",
                    (model_id, context.user_gid, context.team_gid, context.team_gid),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def search_models(self, query: str, project_ref: str, limit: int, context: CapabilityContext) -> list[dict[str, Any]]:
        where = ["(owner_gid=%s OR (%s IS NOT NULL AND team_gid=%s))"]
        params: list[Any] = [context.user_gid, context.team_gid, context.team_gid]
        if query:
            where.append("name LIKE %s")
            params.append(f"%{query}%")
        if project_ref:
            where.append("project_ref=%s")
            params.append(project_ref)
        params.append(limit)
        with get_digital_model_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT model_id,name,project_ref,latest_version_id FROM workmanship_model_models "
                    f"WHERE {' AND '.join(where)} ORDER BY updated_at DESC,model_id ASC LIMIT %s",
                    tuple(params),
                )
                return [dict(row) for row in cur.fetchall()]

    def create_version(self, model: Mapping[str, Any], snapshot: Mapping[str, Any], *, expected_head: str, context: CapabilityContext) -> None:
        artifact = snapshot["artifact_ref"]
        with get_digital_model_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT latest_version_id FROM workmanship_model_models WHERE model_id=%s "
                    "AND (owner_gid=%s OR (%s IS NOT NULL AND team_gid=%s)) FOR UPDATE",
                    (model["model_id"], context.user_gid, context.team_gid, context.team_gid),
                )
                current = cur.fetchone()
                if not current:
                    raise CapabilityBusinessError("model_not_found", "Digital Model not found")
                actual = str(current.get("latest_version_id") or "")
                if actual != expected_head:
                    raise CapabilityBusinessError(
                        "version_conflict", "Digital Model head changed",
                        details={"expected_head_version_id": expected_head, "current_head_version_id": actual},
                    )
                cur.execute(
                    "INSERT INTO workmanship_model_versions "
                    "(version_id,model_id,version_label,parent_version_id,snapshot_hash,artifact_id,"
                    "artifact_media_type,artifact_sha256,artifact_byte_size,artifact_version,snapshot_json,created_by,created_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())",
                    (
                        snapshot["version_id"], model["model_id"], model["version_label"],
                        expected_head or None, snapshot["snapshot_hash"], artifact["artifact_id"],
                        artifact["media_type"], artifact["sha256"], artifact["byte_size"],
                        artifact["version"], model["snapshot_json"], context.user_gid,
                    ),
                )
                for item in snapshot["components"]:
                    cur.execute(
                        "INSERT INTO workmanship_model_components "
                        "(version_id,component_id,parent_component_id,name,component_type,geometry_summary) "
                        "VALUES (%s,%s,%s,%s,%s,%s)",
                        (
                            snapshot["version_id"], item["component_id"],
                            item.get("parent_component_id") or None, item["name"], item["component_type"],
                            json.dumps(item["geometry_summary"], ensure_ascii=False, sort_keys=True),
                        ),
                    )
                cur.execute(
                    "UPDATE workmanship_model_models SET latest_version_id=%s,updated_at=NOW() WHERE model_id=%s",
                    (snapshot["version_id"], model["model_id"]),
                )
            conn.commit()

    def get_snapshot(self, model_id: str, version_id: str, context: CapabilityContext) -> dict[str, Any] | None:
        with get_digital_model_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT v.version_id,v.model_id,v.version_label,v.snapshot_hash,v.artifact_id,"
                    "v.artifact_media_type,v.artifact_sha256,v.artifact_byte_size,v.artifact_version,v.snapshot_json "
                    "FROM workmanship_model_versions v JOIN workmanship_model_models m ON m.model_id=v.model_id "
                    "WHERE v.model_id=%s AND v.version_id=%s "
                    "AND (m.owner_gid=%s OR (%s IS NOT NULL AND m.team_gid=%s))",
                    (model_id, version_id, context.user_gid, context.team_gid, context.team_gid),
                )
                row = cur.fetchone()
        return dict(row) if row else None


repository = DigitalModelRepository()
adapter = DigitalModelRevisionAdapter()


def _model(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "model_id": str(row["model_id"]), "object_ref": f"model:{row['model_id']}",
        "name": str(row["name"]), "project_ref": str(row["project_ref"]),
        "latest_version_id": row.get("latest_version_id"),
    }


def _snapshot(row: Mapping[str, Any]) -> dict[str, Any]:
    stored = _json(row.get("snapshot_json"), {})
    return {
        "snapshot_ref": {
            "model_id": str(row["model_id"]), "version_id": str(row["version_id"]),
            "snapshot_hash": str(row["snapshot_hash"]),
            "artifact_ref": {
                "artifact_id": str(row["artifact_id"]), "media_type": str(row["artifact_media_type"]),
                "sha256": str(row["artifact_sha256"]), "byte_size": int(row["artifact_byte_size"]),
                "version": int(row["artifact_version"]),
            },
        },
        "version_label": str(row["version_label"]),
        "components": list(stored.get("components") or ()),
    }


def create_model(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    model_id = "mdl_" + secrets.token_hex(16)
    row = {
        "model_id": model_id, "name": str(payload["name"]).strip(),
        "project_ref": str(payload["project_ref"]), "owner_gid": context.user_gid,
        "team_gid": context.team_gid, "latest_version_id": None,
    }
    repository.create_model(row)
    return CapabilityOutput(data=_model(row), evidence=(EvidenceRef(kind="digital_model.model", reference=f"model:{model_id}"),))


def get_model(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    row = repository.get_model(str(payload["model_id"]), context)
    if not row:
        raise CapabilityBusinessError("model_not_found", "Digital Model not found")
    return CapabilityOutput(data=_model(row))


def search_models(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    query = str(payload.get("query") or "").strip()
    limit = max(1, min(int(payload.get("limit") or 20), 50))
    rows = repository.search_models(query, str(payload.get("project_ref") or ""), limit, context)
    return CapabilityOutput(data={"items": [_model(row) for row in rows], "total": len(rows), "query": query})


def create_version(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    model_id = str(payload["model_id"])
    model = repository.get_model(model_id, context)
    if not model:
        raise CapabilityBusinessError("model_not_found", "Digital Model not found")
    seed = {
        "model_id": model_id, "version_id": "pending",
        "artifact_ref": dict(payload["artifact_ref"]), "components": list(payload["components"]),
    }
    normalized = adapter.normalize(seed)
    normalized["version_id"] = "mdv_" + hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:32]
    snapshot_hash, snapshot_json = _canonical(normalized)
    snapshot = {**normalized, "snapshot_hash": snapshot_hash}
    repository.create_version(
        {"model_id": model_id, "version_label": str(payload["version_label"]), "snapshot_json": snapshot_json},
        snapshot, expected_head=str(payload["expected_head_version_id"]), context=context,
    )
    data = {
        "snapshot_ref": {
            "model_id": model_id, "version_id": snapshot["version_id"],
            "snapshot_hash": snapshot_hash, "artifact_ref": snapshot["artifact_ref"],
        },
        "version_label": str(payload["version_label"]), "component_count": len(snapshot["components"]),
    }
    return CapabilityOutput(data=data, evidence=(EvidenceRef(kind="digital_model.snapshot", reference=f"model:{model_id}@{snapshot['version_id']}", digest=snapshot_hash),))


def get_snapshot(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    row = repository.get_snapshot(str(payload["model_id"]), str(payload["version_id"]), context)
    if not row:
        raise CapabilityBusinessError("snapshot_not_found", "Digital Model snapshot not found")
    return CapabilityOutput(data=_snapshot(row))


def resolve_snapshot_reference(reference: Mapping[str, Any], context: CapabilityContext) -> dict[str, Any]:
    """Resolve and verify an exact immutable model snapshot for downstream domains."""
    row = repository.get_snapshot(str(reference.get("model_id") or ""), str(reference.get("version_id") or ""), context)
    if not row:
        raise CapabilityBusinessError("snapshot_not_found", "Digital Model snapshot not found")
    actual = _snapshot(row)["snapshot_ref"]
    if actual != dict(reference):
        raise CapabilityBusinessError(
            "source_version_mismatch", "Digital Model snapshot no longer matches the pinned reference",
            details={"expected_snapshot_hash": reference.get("snapshot_hash"), "actual_snapshot_hash": actual["snapshot_hash"]},
        )
    return actual


def compare_snapshots(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    model_id = str(payload["model_id"])
    before_row = repository.get_snapshot(model_id, str(payload["from_version_id"]), context)
    after_row = repository.get_snapshot(model_id, str(payload["to_version_id"]), context)
    if not before_row or not after_row:
        raise CapabilityBusinessError("snapshot_not_found", "Digital Model snapshot not found")
    before, after = _snapshot(before_row), _snapshot(after_row)
    before_content = {"model_id": model_id, "version_id": before["snapshot_ref"]["version_id"], "artifact_ref": before["snapshot_ref"]["artifact_ref"], "components": before["components"]}
    after_content = {"model_id": model_id, "version_id": after["snapshot_ref"]["version_id"], "artifact_ref": after["snapshot_ref"]["artifact_ref"], "components": after["components"]}
    changes = adapter.diff(before_content, after_content)
    return CapabilityOutput(data={
        "model_id": model_id, "from_version_id": str(payload["from_version_id"]),
        "to_version_id": str(payload["to_version_id"]),
        "changes": [change.model_dump(mode="json") for change in changes],
        "breaking": any(change.breaking for change in changes),
    })


def search_components(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    snapshot = get_snapshot(payload, context).data
    query = str(payload.get("query") or "").strip().casefold()
    limit = max(1, min(int(payload.get("limit") or 50), 200))
    items = [item for item in snapshot["components"] if not query or query in item["name"].casefold() or query in item["component_id"].casefold()][:limit]
    return CapabilityOutput(data={"model_id": str(payload["model_id"]), "version_id": str(payload["version_id"]), "items": items, "total": len(items)})


def specs() -> tuple[tuple[CapabilitySpec, Any], ...]:
    common = {"owner": "digital_model", "plugin_callable": True, "permissions": ("digital_model.use",), "tags": ("digital_model",)}
    return (
        (CapabilitySpec(id="digital_model.model.create", description="Create a governed Digital Model identity.", risk="write", confirmation="user", **common), create_model),
        (CapabilitySpec(id="digital_model.model.get", description="Read a governed Digital Model identity.", **common), get_model),
        (CapabilitySpec(id="digital_model.model.search", description="Search visible Digital Model identities.", **common), search_models),
        (CapabilitySpec(id="digital_model.version.create", description="Create an immutable artifact-backed Digital Model snapshot.", risk="write", confirmation="user", idempotent=False, **common), create_version),
        (CapabilitySpec(id="digital_model.snapshot.get", description="Read an immutable Digital Model snapshot.", **common), get_snapshot),
        (CapabilitySpec(id="digital_model.snapshot.compare", description="Compare Digital Model snapshots semantically.", **common), compare_snapshots),
        (CapabilitySpec(id="digital_model.component.search", description="Search components in an immutable Digital Model snapshot.", **common), search_components),
    )


__all__ = ["repository", "specs"]
