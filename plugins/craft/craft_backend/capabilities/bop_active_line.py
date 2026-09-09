"""Bounded active BOP line discovery for explicit responsibility mapping."""
from __future__ import annotations

import base64
from typing import Any

from backend.capability_v2.contracts import (
    AutomationLevel, CapabilityDescriptorV2, DomainErrorContract,
    ExposurePolicy, LifecycleStatus,
)
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec
from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityRisk, CapabilitySpec

from ..data.connection import get_craft_conn


MAX_DEPTH = 32
MAX_NODES = 5000
ID = {"type": "string", "minLength": 1, "maxLength": 256}


def _object(properties: dict[str, Any], required: tuple[str, ...] = ()) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


def _decode_cursor(raw: Any) -> str:
    if raw in (None, ""):
        return ""
    try:
        return base64.urlsafe_b64decode(str(raw) + "==").decode("utf-8")
    except Exception as exc:
        raise CapabilityBusinessError("invalid_cursor", "The BOP line cursor is invalid.") from exc


def _encode_cursor(gid: str) -> str:
    return base64.urlsafe_b64encode(gid.encode("utf-8")).decode("ascii").rstrip("=")


def _active_line_page(
    project_gid: str, after: str, page_size: int
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    with get_craft_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT e.gid,e.parent_gid,e.node_type,COALESCE(e.title,'') AS title,"
            "v.gid AS version_gid,COALESCE(v.version_tag,'') AS version_tag "
            "FROM workmanship_bop_bop_entries e "
            "JOIN workmanship_bop_bop_versions v ON v.gid=e.version_gid "
            "WHERE v.project_gid=%s AND v.status='active' AND e.is_deleted=FALSE "
            "AND e.node_type='line_process' AND e.gid>%s "
            "ORDER BY e.gid LIMIT %s",
            (project_gid, after, page_size + 1),
        )
        lines = [dict(row) for row in cur.fetchall()]
        selected = lines[:page_size]
        by_gid = {str(row["gid"]): row for row in selected}
        frontier = {str(row["parent_gid"]) for row in selected if row.get("parent_gid")}
        depth = 0
        while frontier:
            depth += 1
            if depth > MAX_DEPTH:
                raise CapabilityBusinessError(
                    "graph_limit_exceeded", "The active BOP path exceeds its safe graph limit."
                )
            placeholders = ",".join(["%s"] * len(frontier))
            cur.execute(
                "SELECT e.gid,e.parent_gid,e.node_type,COALESCE(e.title,'') AS title,"
                "v.gid AS version_gid,COALESCE(v.version_tag,'') AS version_tag "
                "FROM workmanship_bop_bop_entries e "
                "JOIN workmanship_bop_bop_versions v ON v.gid=e.version_gid "
                "WHERE v.project_gid=%s AND v.status='active' AND e.is_deleted=FALSE "
                f"AND e.gid IN ({placeholders})",
                (project_gid, *sorted(frontier)),
            )
            parents = [dict(row) for row in cur.fetchall()]
            for row in parents:
                by_gid[str(row["gid"])] = row
            if len(by_gid) > MAX_NODES:
                raise CapabilityBusinessError(
                    "graph_limit_exceeded", "The selected BOP paths exceed the safe graph limit."
                )
            frontier = {
                str(row["parent_gid"])
                for row in parents
                if row.get("parent_gid") and str(row["parent_gid"]) not in by_gid
            }
    return lines, by_gid


def _path(row: dict[str, Any], by_gid: dict[str, dict[str, Any]]) -> str:
    labels = [str(row.get("title") or row["gid"])]
    seen = {str(row["gid"])}
    parent = row.get("parent_gid")
    depth = 0
    while parent:
        depth += 1
        if depth > MAX_DEPTH or str(parent) in seen:
            raise CapabilityBusinessError("graph_limit_exceeded", "The active BOP path exceeds its safe graph limit.")
        seen.add(str(parent))
        current = by_gid.get(str(parent))
        if current is None:
            break
        labels.append(str(current.get("title") or current["gid"]))
        parent = current.get("parent_gid")
    labels.append(str(row.get("version_tag") or row["version_gid"]))
    return " / ".join(reversed(labels))


def search_active_lines(payload: dict[str, Any], _context: object) -> dict[str, Any]:
    project_gid = str(payload["project_gid"])
    page_size = payload.get("page_size", 100)
    if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 100:
        raise CapabilityBusinessError("invalid_page_size", "page_size must be between 1 and 100")
    after = _decode_cursor(payload.get("cursor"))
    lines, by_gid = _active_line_page(project_gid, after, page_size)
    has_more = len(lines) > page_size
    selected = lines[:page_size]
    items = [{
        "gid": str(row["gid"]),
        "version_gid": str(row["version_gid"]),
        "version_tag": str(row.get("version_tag") or ""),
        "title": str(row.get("title") or ""),
        "path": _path(row, by_gid),
    } for row in selected]
    return {"data": {"items": items, "next_cursor": _encode_cursor(items[-1]["gid"]) if has_more and items else None}}


def validate_active_line(payload: dict[str, Any], _context: object) -> dict[str, Any]:
    with get_craft_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT e.gid,e.node_type,e.is_deleted,v.project_gid,v.status "
            "FROM workmanship_bop_bop_entries e JOIN workmanship_bop_bop_versions v ON v.gid=e.version_gid "
            "WHERE e.gid=%s LIMIT 1",
            (payload["bop_line_gid"],),
        )
        raw = cur.fetchone()
    if not raw:
        raise CapabilityBusinessError("resource_not_found", "The BOP line does not exist.")
    row = dict(raw)
    if str(row["project_gid"]) != str(payload["project_gid"]):
        raise CapabilityBusinessError("bop_line_wrong_project", "The BOP line belongs to another project.")
    if row.get("status") != "active" or bool(row.get("is_deleted")):
        raise CapabilityBusinessError("bop_line_inactive", "The BOP line is not active.")
    if row.get("node_type") != "line_process":
        raise CapabilityBusinessError("invalid_input", "The selected BOP entry is not a line_process.")
    return {"data": {"gid": str(row["gid"]), "active": True}}


def _descriptor(spec: CapabilitySpec, *, business_effect: str) -> CapabilityDescriptorV2:
    base = descriptor_from_provider_spec(spec)
    errors = tuple(DomainErrorContract(code=code, meaning=code.replace("_", " "), retryable=False) for code in (
        "invalid_input", "invalid_cursor", "invalid_page_size", "resource_not_found",
        "bop_line_wrong_project", "bop_line_inactive", "graph_limit_exceeded",
    ))
    return CapabilityDescriptorV2.model_validate({
        **base.model_dump(), "lifecycle_status": LifecycleStatus.STABLE,
        "exposure": ExposurePolicy(web=True, api=True, plugin=True, agent=True, mcp=True),
        "exposure_policy_source": "provider_explicit", "automation_level": AutomationLevel.A2,
        "authorization_policy": "craft.v2:craft.read", "data_classification": "confidential",
        "delegation_policy": "scoped", "agent_output_schema": spec.output_schema,
        "operation_policy": "none", "idempotency_policy": "none", "consistency_policy": "strong",
        "evidence_policy": "optional", "audit_policy": "standard",
        "domain_errors": errors, "domain_errors_complete": True,
        "business_effect": business_effect,
        "business_acceptance_criteria": (
            "Only active-version nondeleted line_process entries are returned or accepted.",
            "Graph traversal is bounded to 5000 nodes and depth 32.",
            "The capability does not mutate Craft state.",
        ),
        "business_invariants": (),
        "no_business_invariant_reason": "This read projects Craft-owned active BOP state without creating a new business decision.",
    })


def register_bop_active_line_capabilities(registry: Any) -> None:
    item = _object({"gid": ID, "version_gid": ID, "version_tag": {"type": "string", "maxLength": 256}, "title": {"type": "string", "maxLength": 512}, "path": {"type": "string", "maxLength": 4096}}, ("gid", "version_gid", "version_tag", "title", "path"))
    definitions = (
        ("craft.bop.active_line.search", search_active_lines, "Returns the bounded active BOP lines that may be assigned to a project responsibility node.", _object({"project_gid": ID, "cursor": {"type": ["string", "null"], "maxLength": 512}, "page_size": {"type": "integer", "minimum": 1, "maximum": 100}}, ("project_gid",)), _object({"data": _object({"items": {"type": "array", "items": item, "maxItems": 100}, "next_cursor": {"type": ["string", "null"], "maxLength": 512}}, ("items", "next_cursor"))}, ("data",))),
        ("craft.bop.active_line.validate", validate_active_line, "Confirms that a selected BOP line remains active, undeleted, and owned by the requested project.", _object({"project_gid": ID, "bop_line_gid": ID}, ("project_gid", "bop_line_gid")), _object({"data": _object({"gid": ID, "active": {"const": True}}, ("gid", "active"))}, ("data",))),
    )
    for capability_id, handler, business_effect, input_schema, output_schema in definitions:
        spec = CapabilitySpec(id=capability_id, version=1, owner="craft", description=f"Governed {capability_id} active BOP line outcome.", use_when="A responsibility editor needs an explicit active BOP line.", do_not_use_when="The caller wants to mutate BOP content.", risk=CapabilityRisk.READ, confirmation="none", permissions=("craft.read",), input_schema=input_schema, output_schema=output_schema, tags=("craft", "bop", "active_line"))
        registry.register(spec, handler, descriptor=_descriptor(spec, business_effect=business_effect))


__all__ = ["MAX_DEPTH", "MAX_NODES", "register_bop_active_line_capabilities", "search_active_lines", "validate_active_line"]
