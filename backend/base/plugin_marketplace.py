"""Tenant-bound, read-only marketplace projection for Web and desktop consumers."""
from __future__ import annotations

import json
from jsonschema import Draft202012Validator

from backend.capability_v2.contracts import BusinessInvariantContract, DomainErrorContract, ExposurePolicy
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec
from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilitySpec


CAPABILITY_ID = "base.plugin.marketplace.search"


def obj(properties, required=None):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required, "additionalProperties": False}


TEXT = {"type": "string", "maxLength": 4000}
GRANTS = {"type": "array", "maxItems": 200, "items": {"type": "string", "maxLength": 128}}
ITEM = obj({
    "plugin_id": TEXT, "name": TEXT, "description": TEXT, "version": TEXT,
    "release_sha256": TEXT, "requested_grants": GRANTS, "granted_capabilities": GRANTS,
    "current_version": TEXT, "previous_version": TEXT, "last_error": TEXT,
    "state": {"enum": ["available", "disabled", "enabled", "upgrading", "failed", "rolled_back", "revoked"]},
    "revision": {"type": "integer", "minimum": 0},
})
INPUT = obj({
    "view": {"enum": ["catalog", "installed"]},
    "query": {"type": "string", "maxLength": 200},
    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
    "offset": {"type": "integer", "minimum": 0, "maximum": 1000000},
}, ["view"])
OUTPUT = obj({"items": {"type": "array", "maxItems": 200, "items": ITEM},
              "next_offset": {"type": ["integer", "null"], "minimum": 0}})


def _metadata(value, kind):
    try:
        result = json.loads(value) if isinstance(value, str) else value
    except ValueError as exc:
        raise CapabilityBusinessError("marketplace_data_invalid", "Stored plugin metadata is invalid.") from exc
    if not isinstance(result, kind) or (kind is list and not all(isinstance(item, str) for item in result)):
        raise CapabilityBusinessError("marketplace_data_invalid", "Stored plugin metadata has an invalid shape.")
    return result


def search_marketplace(payload, context):
    from backend.db.connection import get_conn
    from backend.base.desktop_actions import _actor

    if not Draft202012Validator(INPUT).is_valid(payload):
        raise CapabilityBusinessError("invalid_input", "The marketplace query does not match its contract.")
    # Re-read the Base principal so an old session cannot select a former tenant.
    _actor(context)

    limit, offset = payload.get("limit", 50), payload.get("offset", 0)
    tenant = context.team_gid or f"user:{context.user_gid}"
    query = str(payload.get("query", "")).strip()
    # LIKE is parameterized; literal wildcard characters are searched literally.
    pattern = "%" + query.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
    fields = ("r.version,r.manifest,r.artifact_sha256,r.status AS release_status,"
              "i.current_version,i.previous_version,i.state,i.granted_capabilities,i.revision,i.last_error ")
    if payload["view"] == "catalog":
        sql = ("SELECT r.plugin_id," + fields + "FROM workmanship_plugin_releases r "
               "LEFT JOIN workmanship_plugin_installations i ON i.plugin_id=r.plugin_id AND i.tenant_gid=%s "
               "WHERE r.status='published' AND r.platform_signature IS NOT NULL "
               "AND r.platform_signature<>'' ")
        order = "r.plugin_id,r.updated_at DESC,r.version DESC"
    else:
        sql = ("SELECT i.plugin_id," + fields + "FROM workmanship_plugin_installations i "
               "LEFT JOIN workmanship_plugin_releases r ON r.plugin_id=i.plugin_id AND r.version=i.current_version "
               "WHERE i.tenant_gid=%s AND i.state<>'uninstalled' ")
        order = "i.plugin_id"
    sql += "AND (" + ("r" if payload["view"] == "catalog" else "i") + ".plugin_id LIKE %s ESCAPE '!' OR r.manifest LIKE %s ESCAPE '!') "
    sql += f"ORDER BY {order} LIMIT %s OFFSET %s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (tenant, pattern, pattern, limit + 1, offset))
            rows = cur.fetchall()
    items = []
    for row in rows[:limit]:
        manifest = _metadata(row.get("manifest") or {}, dict)
        grants = _metadata(row.get("granted_capabilities") or [], list)
        installed = row.get("state") not in (None, "uninstalled")
        items.append({
            "plugin_id": row["plugin_id"], "name": str(manifest.get("name") or row["plugin_id"])[:4000],
            "description": str(manifest.get("description") or "")[:4000],
            "version": row.get("version") or row.get("current_version") or "",
            "release_sha256": "sha256:" + row["artifact_sha256"] if row.get("artifact_sha256") and row.get("release_status") == "published" else "",
            "requested_grants": sorted(set(_metadata(manifest.get("permissions") or [], list))),
            "granted_capabilities": grants if installed else [],
            "current_version": (row.get("current_version") or "") if installed else "",
            "previous_version": (row.get("previous_version") or "") if installed else "",
            "state": row["state"] if installed else "available",
            "revision": int(row.get("revision") or 0) if installed else 0,
            "last_error": str(row.get("last_error") or "")[:4000] if installed else "",
        })
    result = {"items": items, "next_offset": offset + limit if len(rows) > limit else None}
    if not Draft202012Validator(OUTPUT).is_valid(result):
        raise CapabilityBusinessError("marketplace_data_invalid", "Stored plugin metadata does not match the marketplace contract.")
    return result


def register_marketplace_search(registry):
    # Version 1 remains intact; its generic operation/resource contract is not
    # silently repurposed for this closed, paginated page projection.
    spec = CapabilitySpec(
        owner="base", id=CAPABILITY_ID, version=2,
        description="Returns signed published plugin releases or the caller tenant's installed plugins, with bounded lifecycle metadata.",
        risk="read", confirmation="none", permissions=(), plugin_callable=False,
        input_schema=INPUT, output_schema=OUTPUT, tags=("base", "plugin", "marketplace", "read"),
    )
    descriptor = descriptor_from_provider_spec(spec).model_copy(update={
        "authorization_policy": "base.v2:authenticated",
        "exposure": ExposurePolicy(web=True, api=True, plugin=False, agent=False, mcp=False),
        "exposure_policy_source": "provider_explicit",
        "agent_output_schema": None, "delegation_policy": "none",
        "consistency_policy": "strong", "data_classification": "confidential",
        "domain_errors": (
            DomainErrorContract(code="invalid_input", meaning="Query is outside the closed marketplace contract.", is_caller_error=True),
            DomainErrorContract(code="permission_denied", meaning="The Base actor is inactive or its tenant has changed."),
            DomainErrorContract(code="marketplace_data_invalid", meaning="Stored metadata violates the bounded marketplace projection."),
        ),
        "domain_errors_complete": True,
        "business_invariants": (BusinessInvariantContract(
            rule_id="base.plugin.marketplace.tenant_bound", version=1,
            statement="Only the authenticated Base tenant's installation metadata is returned.",
            applies_when="a marketplace view is read",
            enforcement_ref="backend/base/plugin_marketplace.py:search_marketplace",
            error_code="permission_denied",
            test_refs=("backend/tests/test_plugin_marketplace_search.py::test_gateway_enforces_actor_tenant_version_and_closed_contract",),
        ),),
        "business_acceptance_criteria": (
            "Catalog rows refer only to published releases bearing a platform signature.",
            "Installation metadata is scoped to the authenticated tenant and cannot be selected by caller input.",
            "Each response contains at most 200 rows and a continuation offset.",
        ),
    })
    descriptor = type(descriptor).model_validate(descriptor.model_dump())
    registry.register(spec, search_marketplace, descriptor=descriptor)
