"""Resolve Knowledge-owned resource codes to immutable Digital Model snapshots."""
from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import datetime

from pydantic import ValidationError

from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError,
    CapabilityContext,
    CapabilityOutput,
    CapabilityRisk,
    CapabilitySpec,
)
from backend.domain_ports.digital_model import ModelSnapshotRef

from ..data import connection
from ..provider import register_capability


RESOURCE_TYPES = {"tool", "equipment", "fixture"}
HASH_SCHEMA = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
ARTIFACT_REF_SCHEMA = {
    "type": "object",
    "required": ["artifact_id", "media_type", "sha256", "byte_size", "version"],
    "properties": {
        "artifact_id": {"type": "string", "minLength": 1},
        "media_type": {"type": "string", "minLength": 1},
        "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "byte_size": {"type": "integer", "minimum": 0},
        "version": {"type": "integer", "minimum": 1},
    },
    "additionalProperties": False,
}
MODEL_REF_SCHEMA = {
    "type": "object",
    "required": ["model_id", "version_id", "snapshot_hash", "artifact_ref"],
    "properties": {
        "model_id": {"type": "string", "minLength": 1},
        "version_id": {"type": "string", "minLength": 1},
        "snapshot_hash": HASH_SCHEMA,
        "artifact_ref": ARTIFACT_REF_SCHEMA,
    },
    "additionalProperties": False,
}
ITEM_SCHEMA = {
    "type": "object",
    "required": ["resource_type", "code"],
    "properties": {
        "resource_type": {"type": "string", "enum": sorted(RESOURCE_TYPES)},
        "code": {"type": "string", "minLength": 1, "maxLength": 255},
    },
    "additionalProperties": False,
}
RESOLVED_SCHEMA = {
    "type": "object",
    "required": ["resource_type", "code", "normalized_code", "model_ref"],
    "properties": {
        **ITEM_SCHEMA["properties"],
        "normalized_code": {"type": "string"},
        "model_ref": MODEL_REF_SCHEMA,
    },
    "additionalProperties": False,
}
UNRESOLVED_SCHEMA = {
    "type": "object",
    "required": ["resource_type", "code", "normalized_code"],
    "properties": {
        **ITEM_SCHEMA["properties"],
        "normalized_code": {"type": "string"},
    },
    "additionalProperties": False,
}
AMBIGUOUS_SCHEMA = {
    "type": "object",
    "required": ["resource_type", "code", "normalized_code", "candidates"],
    "properties": {
        **UNRESOLVED_SCHEMA["properties"],
        "candidates": {"type": "array", "items": MODEL_REF_SCHEMA, "minItems": 2, "maxItems": 100},
    },
    "additionalProperties": False,
}
INPUT_SCHEMA = {
    "type": "object",
    "required": ["items"],
    "properties": {
        "items": {"type": "array", "items": ITEM_SCHEMA, "maxItems": 500},
        "as_of": {"type": "string", "format": "date-time"},
    },
    "additionalProperties": False,
}
OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["resolved", "unresolved", "ambiguous", "mapping_snapshot_hash"],
    "properties": {
        "resolved": {"type": "array", "items": RESOLVED_SCHEMA, "maxItems": 500},
        "unresolved": {"type": "array", "items": UNRESOLVED_SCHEMA, "maxItems": 500},
        "ambiguous": {"type": "array", "items": AMBIGUOUS_SCHEMA, "maxItems": 500},
        "mapping_snapshot_hash": HASH_SCHEMA,
    },
    "additionalProperties": False,
}


def normalize_code(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value)).strip().casefold()
    if not normalized:
        raise CapabilityBusinessError(
            "resource_code_invalid", "resource_code_invalid: resource code cannot be blank"
        )
    return normalized


def _canonical_hash(value) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


class ResourceModelMappingRepository:
    def resolve(self, keys, *, tenant_gid: str, as_of: str | None = None):
        if not keys:
            return []
        clauses = " OR ".join(
            "(resource_type = %s AND normalized_code = %s)" for _ in keys
        )
        instant = as_of or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")
        params = [tenant_gid, instant, instant]
        for resource_type, code in keys:
            params.extend((resource_type, code))
        sql = f"""
            SELECT resource_type, normalized_code, model_ref_json,
                   mapping_version, content_hash
            FROM workmanship_knowledge_resource_model_mappings
            WHERE tenant_gid = %s
              AND valid_from <= %s
              AND (valid_to IS NULL OR valid_to > %s)
              AND ({clauses})
            ORDER BY resource_type, normalized_code, mapping_version
        """
        with connection.get_knowledge_conn() as conn, conn.cursor() as cursor:
            cursor.execute(sql, tuple(params))
            return list(cursor.fetchall())


class ResourceModelMappingProvider:
    def __init__(self, repository=None):
        self.repository = repository or ResourceModelMappingRepository()

    def resolve(self, payload: dict, context: CapabilityContext) -> CapabilityOutput:
        if not context.team_gid:
            raise CapabilityBusinessError(
                "tenant_context_required",
                "tenant_context_required: resource mappings require a tenant scope",
            )
        requested = {}
        for item in payload.get("items", ()):
            resource_type = item.get("resource_type")
            if resource_type not in RESOURCE_TYPES:
                raise CapabilityBusinessError(
                    "resource_type_invalid",
                    f"resource_type_invalid: unsupported resource type {resource_type!r}",
                )
            normalized = normalize_code(item.get("code", ""))
            requested.setdefault((resource_type, normalized), item["code"])
        if len(requested) > 500:
            raise CapabilityBusinessError(
                "mapping_batch_limit_exceeded",
                "mapping_batch_limit_exceeded: at most 500 unique mappings are allowed",
            )
        keys = tuple(sorted(requested))
        rows = self.repository.resolve(
            keys, tenant_gid=context.team_gid, as_of=payload.get("as_of")
        )
        candidates = {key: [] for key in keys}
        snapshot_rows = []
        for row in rows:
            key = (row["resource_type"], row["normalized_code"])
            if key not in candidates:
                continue
            model_ref = row["model_ref_json"]
            if isinstance(model_ref, str):
                model_ref = json.loads(model_ref)
            try:
                model_ref = ModelSnapshotRef.model_validate(model_ref).model_dump(mode="json")
            except (TypeError, ValueError, ValidationError) as exc:
                raise CapabilityBusinessError(
                    "mapping_data_invalid",
                    "mapping_data_invalid: stored model reference is not immutable",
                ) from exc
            if model_ref not in candidates[key]:
                candidates[key].append(model_ref)
                if len(candidates[key]) > 100:
                    raise CapabilityBusinessError(
                        "mapping_candidate_limit_exceeded",
                        "mapping_candidate_limit_exceeded: one typed code has more than 100 active model mappings",
                    )
            snapshot_rows.append({
                "resource_type": key[0],
                "normalized_code": key[1],
                "mapping_version": int(row["mapping_version"]),
                "content_hash": row["content_hash"],
                "model_ref": model_ref,
            })

        resolved, unresolved, ambiguous = [], [], []
        for resource_type, normalized in keys:
            base = {
                "resource_type": resource_type,
                "code": requested[(resource_type, normalized)],
                "normalized_code": normalized,
            }
            models = candidates[(resource_type, normalized)]
            if not models:
                unresolved.append(base)
            elif len(models) == 1:
                resolved.append({**base, "model_ref": models[0]})
            else:
                ambiguous.append({**base, "candidates": models})
        return CapabilityOutput(data={
            "resolved": resolved,
            "unresolved": unresolved,
            "ambiguous": ambiguous,
            "mapping_snapshot_hash": _canonical_hash(snapshot_rows),
        })


def register_resource_model_mapping_capability(registry, repository=None) -> None:
    provider = ResourceModelMappingProvider(repository)
    spec = CapabilitySpec(
        id="knowledge.resource_model_mapping.resolve",
        version=1,
        owner="knowledge",
        description="Resolve typed resource codes to immutable Digital Model snapshots.",
        use_when="A workflow needs deterministic tool, equipment, or fixture model bindings.",
        do_not_use_when="The caller needs product BOM bindings or mutable operational data.",
        risk=CapabilityRisk.READ,
        confirmation="none",
        permissions=("knowledge.reference_data.read",),
        input_schema=INPUT_SCHEMA,
        output_schema=OUTPUT_SCHEMA,
        tags=("knowledge", "resource_model_mapping"),
        plugin_callable=True,
    )
    register_capability(registry, spec, provider.resolve)


__all__ = [
    "INPUT_SCHEMA",
    "OUTPUT_SCHEMA",
    "ResourceModelMappingProvider",
    "ResourceModelMappingRepository",
    "normalize_code",
    "register_resource_model_mapping_capability",
]
