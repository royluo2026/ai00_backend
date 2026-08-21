"""Governed PBOM VPPS operation-audit outcomes."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityOutput, CapabilitySpec

from ..data.connection import get_conn
from ..vpps_audit import MySqlVppsOperationRepository, VppsAuditService

READ_OPERATIONS = ("list", "rule4_ignores")
CHANGE_OPERATIONS = ("rule4_bulk_ignore", "revert")


def _op_to_dict(op: Any) -> dict[str, Any]:
    return {
        "gid": op.gid, "pbom_version_gid": op.pbom_version_gid, "pbom_row_gid": op.pbom_row_gid,
        "operation_type": op.operation_type, "rule_no": op.rule_no, "field_name": op.field_name,
        "original_value": op.original_value, "new_value": op.new_value, "actor_gid": op.actor_gid,
        "actor_name": op.actor_name, "created_at": op.created_at.isoformat() if op.created_at else None,
        "notes": op.notes, "is_active": op.is_active, "reverted_at": op.reverted_at.isoformat() if op.reverted_at else None,
        "reverted_by_gid": op.reverted_by_gid, "reverted_by_name": op.reverted_by_name,
    }


def read_vpps_audit(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    operation = str(payload.get("operation") or "")
    if operation not in READ_OPERATIONS:
        raise ValueError("unsupported VPPS audit read operation")
    version_gid = str(payload.get("pbom_version_gid") or "")
    if not version_gid:
        raise ValueError("pbom_version_gid is required")
    with get_conn() as conn:
        service = VppsAuditService(MySqlVppsOperationRepository(conn))
        ops = service.get_active_operations(version_gid, "rule4_bulk_ignore" if operation == "rule4_ignores" else payload.get("operation_type"))
    items = [_op_to_dict(op) for op in ops]
    if operation == "rule4_ignores":
        return CapabilityOutput(data={"success": True, "ignored_row_gids": sorted({item["pbom_row_gid"] for item in items}), "operations": items})
    return CapabilityOutput(data={"success": True, "items": items})


def change_vpps_audit(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    operation = str(payload.get("operation") or "")
    if operation not in CHANGE_OPERATIONS:
        raise ValueError("unsupported VPPS audit change operation")
    actor_gid = str(payload.get("actor_gid") or context.user_gid)
    actor_name = str(payload.get("actor_name") or "")
    with get_conn() as conn:
        service = VppsAuditService(MySqlVppsOperationRepository(conn))
        if operation == "rule4_bulk_ignore":
            version_gid = str(payload.get("pbom_version_gid") or "")
            rows = list(payload.get("rows") or [])[:500]
            if not version_gid:
                raise ValueError("pbom_version_gid is required")
            ops = service.bulk_ignore_rule4(version_gid, rows, actor_gid, actor_name)
            conn.commit()
            return CapabilityOutput(data={"success": True, "created": len(ops), "operations": [_op_to_dict(op) for op in ops]})
        gid = str(payload.get("gid") or "")
        if not gid:
            raise ValueError("gid is required")
        op = service.revert_operation(gid, actor_gid, actor_name)
        conn.commit()
    if not op:
        raise ValueError("operation not found or already reverted")
    return CapabilityOutput(data={"success": True, "operation": _op_to_dict(op)})


def register_vpps_audit_capabilities(registry: Any) -> None:
    registry.register(CapabilitySpec(id="craft.vpps_audit.read", owner="craft", description="Read bounded PBOM VPPS operation audit records.", use_when="A governed consumer needs VPPS operation audit history or Rule4 ignore state.", do_not_use_when="The request changes PBOM content itself.", risk="read", permissions=("craft.read",), input_schema={"type": "object", "required": ["operation", "pbom_version_gid"], "properties": {"operation": {"type": "string", "enum": list(READ_OPERATIONS)}, "pbom_version_gid": {"type": "string"}, "operation_type": {"type": "string"}}, "additionalProperties": False}, output_schema={"type": "object", "additionalProperties": False, "properties": {"success": {"type": "boolean"}, "items": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}, "ignored_row_gids": {"type": "array", "maxItems": 500, "items": {"type": "string"}}, "operations": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}}}, tags=("craft", "vpps_audit", "read")), read_vpps_audit)
    registry.register(CapabilitySpec(id="craft.vpps_audit.change.apply", owner="craft", description="Apply governed PBOM VPPS operation audit changes.", use_when="A governed consumer needs to bulk-ignore Rule4 rows or revert an audit operation.", do_not_use_when="The request changes PBOM structure or version content.", risk="write", confirmation="user", permissions=("craft.write",), input_schema={"type": "object", "required": ["operation"], "properties": {"operation": {"type": "string", "enum": list(CHANGE_OPERATIONS)}, "gid": {"type": "string"}, "pbom_version_gid": {"type": "string"}, "rows": {"type": "array", "maxItems": 500, "items": {"type": "object", "maxProperties": 10, "additionalProperties": True}}, "actor_gid": {"type": "string"}, "actor_name": {"type": "string"}}, "additionalProperties": False}, output_schema={"type": "object", "required": ["success"], "properties": {"success": {"type": "boolean"}, "created": {"type": "integer", "minimum": 0}, "operations": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}, "operation": {"type": "object", "additionalProperties": True}}}, tags=("craft", "vpps_audit", "write")), change_vpps_audit)
