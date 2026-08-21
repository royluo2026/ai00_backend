"""Governed Craft rule evaluation and BOP audit outcome."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityOutput, CapabilitySpec

from ..data.connection import get_conn
from ..rule_engine.checker import check_entry_rules
from ..rule_engine.executor import check_rule

OPERATIONS = ("check", "audit")


def evaluate_rule_engine(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    operation = str(payload.get("operation") or "")
    if operation not in OPERATIONS:
        raise ValueError("unsupported Craft rule engine operation")
    if operation == "check":
        rule_gid = str(payload.get("rule_gid") or "")
        if not rule_gid:
            raise ValueError("rule_gid is required")
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT gid, name, expression, enforcement_level FROM workmanship_know_craft_rules WHERE gid = %s", (rule_gid,))
                row = cur.fetchone()
        if not row:
            raise ValueError("rule not found")
        if not row["expression"]:
            return CapabilityOutput(data={"rule_gid": rule_gid, "result": "SKIP", "message": "规则无 CEL 表达式"})
        result, message = check_rule(row["expression"], dict(payload.get("context") or {}))
        return CapabilityOutput(data={"rule_gid": rule_gid, "rule_name": row["name"], "result": result.value, "message": message, "enforcement_level": row["enforcement_level"]})
    version_gid = str(payload.get("version_gid") or "")
    if not version_gid:
        raise ValueError("version_gid is required")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT gid, node_type, title FROM workmanship_bop_bop_entries WHERE version_gid = %s AND is_deleted = FALSE LIMIT 500", (version_gid,))
            entries = [dict(row) for row in cur.fetchall()]
    violations = []
    for entry in entries:
        warnings = check_entry_rules(entry["node_type"], entry["gid"])
        if warnings:
            violations.append({"entry_gid": entry["gid"], "entry_title": entry.get("title", ""), "node_type": entry["node_type"], "warnings": warnings})
    return CapabilityOutput(data={"version_gid": version_gid, "total_entries": len(entries), "violation_count": len(violations), "violations": violations})


def register_rule_engine_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(id="craft.rule.engine.evaluate", owner="craft", description="Evaluate a Craft CEL rule or audit a BOP version against Craft rules.", use_when="A governed consumer needs rule evaluation or bounded BOP rule audit.", do_not_use_when="The request publishes or mutates rule definitions.", risk="read", permissions=("craft.read",), input_schema={"type": "object", "required": ["operation"], "properties": {"operation": {"type": "string", "enum": list(OPERATIONS)}, "rule_gid": {"type": "string"}, "context": {"type": "object", "maxProperties": 50, "additionalProperties": True}, "version_gid": {"type": "string"}}, "additionalProperties": False}, output_schema={"type": "object", "additionalProperties": True}, tags=("craft", "rule", "evaluate")), evaluate_rule_engine)
