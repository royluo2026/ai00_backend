"""Governed Craft rule evaluation and BOP audit outcome."""
from __future__ import annotations

import json
import multiprocessing
from queue import Empty
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilityExecutionBudget, CapabilityOutput, CapabilitySpec
from backend.capability_v2.schema_validation import validate_payload

from ..application.rules import load_visible_rule, rule_revision
from ..data.connection import get_conn
from ..rule_engine.checker import check_entry_rules
from ..rule_engine.executor import RuleResult, check_rule

OPERATIONS = ("check", "audit")
MAX_ENTRY_BYTES = 8 * 1024
MAX_ENTRY_DEPTH = 4
MAX_DIAGNOSTICS = 5
MAX_DIAGNOSTIC_CODE_LENGTH = 64
RULE_EVALUATION_TIMEOUT_SECONDS = 1.0
_FORBIDDEN_ENTRY_FIELDS = {"expression", "source", "code", "sql", "provider", "secret", "script", "query"}
_ENTRY_FIELDS = (
    "gid", "node_type", "title", "name", "vpps", "version_no", "std_time", "torque", "qualification",
    "seq_no", "tools_calibrated", "headcount", "model_no", "certification_date", "calibration_interval",
    "calibrated", "vd_time", "total_time", "floor_height_need", "op_req_height", "spec", "quantity",
    "status", "asset_no", "role_type",
)
_SCALAR = {"type": ["string", "number", "integer", "boolean", "null"]}
RULE_ENTRY_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "rule_gid": {"type": "string", "minLength": 1, "maxLength": 255},
        "rule_revision": {"type": "integer", "minimum": 1, "maximum": 2147483647},
        "entry": {"type": "object", "properties": {field: _SCALAR for field in _ENTRY_FIELDS}, "maxProperties": len(_ENTRY_FIELDS), "additionalProperties": False},
    },
    "required": ["rule_gid", "rule_revision", "entry"],
    "additionalProperties": False,
}
RULE_ENTRY_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "passed": {"type": "boolean"},
        "rule_revision": {"type": "integer", "minimum": 1, "maximum": 2147483647},
        "diagnostics": {"type": "array", "maxItems": MAX_DIAGNOSTICS, "items": {"type": "object", "properties": {"code": {"type": "string", "minLength": 1, "maxLength": MAX_DIAGNOSTIC_CODE_LENGTH}}, "required": ["code"], "additionalProperties": False}},
    },
    "required": ["passed", "rule_revision", "diagnostics"],
    "additionalProperties": False,
}


def _depth(value: Any) -> int:
    if isinstance(value, dict):
        return 1 + max((_depth(item) for item in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((_depth(item) for item in value), default=0)
    return 0


def _bounded_entry(payload: dict[str, Any]) -> dict[str, Any]:
    validate_payload(RULE_ENTRY_INPUT_SCHEMA, payload)
    entry = dict(payload["entry"])
    if _depth(entry) > MAX_ENTRY_DEPTH or any(key.lower() in _FORBIDDEN_ENTRY_FIELDS for key in entry):
        raise ValueError("entry contains unsupported executable data")
    try:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError("entry must be JSON-safe") from exc
    if len(encoded.encode("utf-8")) > MAX_ENTRY_BYTES:
        raise ValueError("entry exceeds the bounded input limit")
    return entry


def _outcome(passed: bool, revision: int, code: str | None = None) -> CapabilityOutput:
    diagnostics = [] if code is None else [{"code": code[:MAX_DIAGNOSTIC_CODE_LENGTH]}]
    return CapabilityOutput(data={"passed": passed, "rule_revision": revision, "diagnostics": diagnostics[:MAX_DIAGNOSTICS]})


def _check_worker(result_queue: Any, expression: str, entry_json: str) -> None:
    """Run the already-approved pure checker in a fresh process."""
    try:
        result, _message = check_rule(expression, json.loads(entry_json))
        result_queue.put(result.value)
    except Exception:
        result_queue.put("")


def _run_isolated_check(
    expression: str,
    entry: dict[str, Any],
    timeout: float,
    *,
    worker_target: Any = _check_worker,
) -> str | None:
    """Return a checker result, or None after terminating a timed-out worker."""
    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue(maxsize=1)
    process = context.Process(target=worker_target, args=(result_queue, expression, json.dumps(entry, ensure_ascii=False)))
    started = False
    try:
        process.start()
        started = True
        process.join(timeout)
        if process.is_alive():
            process.terminate()
            process.join()
            return None
        try:
            result = result_queue.get(timeout=0.05)
        except Empty:
            return ""
        return result if result in {item.value for item in RuleResult} else ""
    finally:
        if started and process.is_alive():
            process.terminate()
            process.join()
        if started:
            process.close()
        result_queue.close()
        result_queue.join_thread()


def evaluate_rule_entry(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    """Evaluate one visible, revision-pinned Craft rule against a closed entry projection."""
    entry = _bounded_entry(payload)
    rule = load_visible_rule(payload["rule_gid"], context.user_gid, context.team_gid)
    revision = rule_revision(rule)
    if revision != payload["rule_revision"]:
        raise CapabilityBusinessError("revision_conflict", "The requested rule revision is unavailable.")
    result = _run_isolated_check(str(rule.get("expression") or ""), entry, RULE_EVALUATION_TIMEOUT_SECONDS)
    if result is None:
        return _outcome(False, revision, "evaluation_timeout")
    if result == RuleResult.PASS.value:
        return _outcome(True, revision)
    if result == RuleResult.FAIL.value:
        return _outcome(False, revision, "rule_failed")
    return _outcome(False, revision, "evaluation_unavailable")


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
    registry.register(CapabilitySpec(
        id="craft.rule.entry.evaluate", owner="craft", description="Evaluate one visible Craft rule against a bounded entry projection.",
        use_when="A governed consumer needs a revision-pinned Craft rule decision for one entry.",
        do_not_use_when="The caller supplies rule source, executable code, or a mutable rule definition.",
        risk="read", permissions=("craft.read",), input_schema=RULE_ENTRY_INPUT_SCHEMA, output_schema=RULE_ENTRY_OUTPUT_SCHEMA,
        execution_budget=CapabilityExecutionBudget(memory_class="small", max_input_bytes=MAX_ENTRY_BYTES, max_output_bytes=4 * 1024, max_parallel_per_consumer=1, max_parallel_per_tenant=8),
        tags=("craft", "rule", "entry", "evaluate"),
    ), evaluate_rule_entry)
