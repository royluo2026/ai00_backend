"""Exact model-number to Knowledge resource reverse lookup.

The provider is intentionally not registered until its experimental Capability
descriptor completes the later consolidated governance review.
"""
from __future__ import annotations

from datetime import datetime
import unicodedata

from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError,
    CapabilityContext,
    CapabilityOutput,
    CapabilitySpec,
)

from ..data import connection


RESOURCE_TYPES = frozenset({"tool", "fixture", "equipment", "socket"})


def normalize_model_number(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value)).strip().casefold()
    if not normalized:
        raise CapabilityBusinessError("model_number_invalid", "model_number_invalid")
    return normalized


class ResourceModelReverseLookupRepository:
    def reverse_resolve(self, model_numbers, *, tenant_gid: str, as_of: str | None = None):
        if not model_numbers:
            return []
        placeholders = ",".join("%s" for _ in model_numbers)
        instant = as_of or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")
        sql = f"""
            SELECT resource_type, normalized_code,
                   LOWER(TRIM(JSON_UNQUOTE(JSON_EXTRACT(model_ref_json, '$.model_id')))) AS model_number,
                   mapping_version
            FROM workmanship_knowledge_resource_model_mappings
            WHERE tenant_gid=%s
              AND resource_type IN ('tool','fixture','equipment','socket')
              AND valid_from <= %s AND (valid_to IS NULL OR valid_to > %s)
              AND LOWER(TRIM(JSON_UNQUOTE(JSON_EXTRACT(model_ref_json, '$.model_id')))) IN ({placeholders})
            ORDER BY model_number, resource_type, normalized_code, mapping_version
        """
        with connection.get_knowledge_conn() as conn, conn.cursor() as cursor:
            cursor.execute(sql, (tenant_gid, instant, instant, *model_numbers))
            return list(cursor.fetchall())


class ResourceModelReverseLookupProvider:
    def __init__(self, repository=None):
        self.repository = repository or ResourceModelReverseLookupRepository()

    def resolve(self, payload: dict, context: CapabilityContext) -> CapabilityOutput:
        if not context.team_gid:
            raise CapabilityBusinessError("tenant_context_required", "tenant_context_required")
        requested: dict[str, str] = {}
        for value in payload.get("model_numbers", ()):
            normalized = normalize_model_number(value)
            requested.setdefault(normalized, str(value).strip())
        if len(requested) > 500:
            raise CapabilityBusinessError("mapping_batch_limit_exceeded", "mapping_batch_limit_exceeded")
        keys = tuple(sorted(requested))
        rows = self.repository.reverse_resolve(
            keys, tenant_gid=context.team_gid, as_of=payload.get("as_of")
        )
        candidates: dict[str, list[dict[str, object]]] = {key: [] for key in keys}
        for row in rows:
            model_number = normalize_model_number(row.get("model_number", ""))
            resource_type = str(row.get("resource_type") or "")
            if model_number not in candidates or resource_type not in RESOURCE_TYPES:
                continue
            candidate = {
                "model_number": requested[model_number],
                "resource_type": resource_type,
                "resource_code": str(row.get("normalized_code") or ""),
                "mapping_version": int(row.get("mapping_version") or 0),
            }
            if candidate not in candidates[model_number]:
                candidates[model_number].append(candidate)

        resolved, not_found, ambiguous = [], [], []
        for key in keys:
            values = candidates[key]
            if not values:
                not_found.append({"model_number": requested[key]})
            elif len(values) == 1:
                resolved.append(values[0])
            else:
                ambiguous.append({"model_number": requested[key], "candidates": values})
        return CapabilityOutput(data={
            "resolved": resolved, "not_found": not_found, "ambiguous": ambiguous,
        })


def candidate_spec(repository=None):
    """Build the advisory candidate without registering it into the active Catalog."""
    provider = ResourceModelReverseLookupProvider(repository)
    spec = CapabilitySpec(
        id="knowledge.resource_model_mapping.reverse_resolve", version=1,
        owner="knowledge", plugin_callable=True,
        description="Resolve exact VM model numbers to governed Knowledge resource candidates.",
        use_when="Simulation must classify VM occurrences as tool, fixture, equipment, or socket.",
        do_not_use_when="The caller wants fuzzy automatic classification or product-part identity.",
        risk="read", confirmation="none", permissions=("knowledge.reference_data.read",),
        tags=("knowledge", "resource", "model", "reverse_lookup", "experimental"),
        input_schema={"type": "object", "required": ["model_numbers"], "properties": {
            "model_numbers": {"type": "array", "maxItems": 500,
                              "items": {"type": "string", "minLength": 1, "maxLength": 255}},
            "as_of": {"type": "string", "format": "date-time"}}, "additionalProperties": False},
        output_schema={"type": "object", "required": ["resolved", "not_found", "ambiguous"],
                       "properties": {name: {"type": "array", "maxItems": 500}
                                      for name in ("resolved", "not_found", "ambiguous")},
                       "additionalProperties": False},
    )
    return spec, provider.resolve


__all__ = [
    "ResourceModelReverseLookupProvider", "ResourceModelReverseLookupRepository",
    "normalize_model_number",
    "candidate_spec",
]
