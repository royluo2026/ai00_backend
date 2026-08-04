"""Public Craft execution-plan snapshot contract consumed by Simulation."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any, Mapping

CONTRACT_ID = "craft.execution-plan"
CONTRACT_VERSION = 1
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
OPERATION_KINDS = frozenset({"process", "operation", "step"})


class ContractValidationError(ValueError):
    pass


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"{field} must be a non-empty string")
    return value


def _canonical_content(plan: Mapping[str, Any]) -> dict[str, Any]:
    content = copy.deepcopy(dict(plan))
    content.pop("content_hash", None)
    operations = content.get("operations")
    if isinstance(operations, list):
        for operation in operations:
            if isinstance(operation, dict) and isinstance(operation.get("predecessor_ids"), list):
                operation["predecessor_ids"] = sorted(operation["predecessor_ids"])
            if isinstance(operation, dict):
                for key in ("resource_refs", "model_refs"):
                    if isinstance(operation.get(key), list):
                        operation[key] = sorted(operation[key])
        content["operations"] = sorted(
            operations,
            key=lambda item: (item.get("sequence", 0), item.get("operation_id", "")),
        )
    return content


def compute_content_hash(plan: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _canonical_content(plan), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def validate_execution_plan(plan: Mapping[str, Any], *, require_hash: bool = True) -> None:
    if not isinstance(plan, Mapping):
        raise ContractValidationError("execution plan must be an object")
    if plan.get("contract_id") != CONTRACT_ID or plan.get("contract_version") != CONTRACT_VERSION:
        raise ContractValidationError(f"expected {CONTRACT_ID} v{CONTRACT_VERSION}")
    source = plan.get("source")
    if not isinstance(source, Mapping):
        raise ContractValidationError("source must be an object")
    _required_string(source.get("bop_version_gid"), "source.bop_version_gid")
    _required_string(source.get("project_gid"), "source.project_gid")
    revision = source.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ContractValidationError("source.revision must be an integer >= 1")
    _required_string(plan.get("published_at"), "published_at")

    operations = plan.get("operations")
    if not isinstance(operations, list) or not operations:
        raise ContractValidationError("operations must be a non-empty array")
    ids: set[str] = set()
    positions: dict[str, int] = {}
    for index, operation in enumerate(operations):
        if not isinstance(operation, Mapping):
            raise ContractValidationError(f"operations[{index}] must be an object")
        operation_id = _required_string(operation.get("operation_id"), f"operations[{index}].operation_id")
        if operation_id in ids:
            raise ContractValidationError(f"duplicate operation_id: {operation_id}")
        ids.add(operation_id)
        sequence = operation.get("sequence")
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
            raise ContractValidationError(f"{operation_id}.sequence must be an integer >= 0")
        positions[operation_id] = sequence
        if operation.get("kind") not in OPERATION_KINDS:
            raise ContractValidationError(f"{operation_id}.kind is unsupported")
        _required_string(operation.get("name"), f"{operation_id}.name")
        predecessors = operation.get("predecessor_ids", [])
        if not isinstance(predecessors, list) or any(not isinstance(item, str) for item in predecessors):
            raise ContractValidationError(f"{operation_id}.predecessor_ids must be a string array")
        for key in ("resource_refs", "model_refs"):
            values = operation.get(key, [])
            if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
                raise ContractValidationError(f"{operation_id}.{key} must be a string array")

    for operation in operations:
        operation_id = operation["operation_id"]
        for predecessor in operation.get("predecessor_ids", []):
            if predecessor not in ids:
                raise ContractValidationError(f"{operation_id} has unknown predecessor {predecessor}")
            if predecessor == operation_id or positions[predecessor] >= positions[operation_id]:
                raise ContractValidationError(
                    f"{operation_id} predecessor {predecessor} must have a lower sequence"
                )

    canonical_order = sorted(operations, key=lambda item: (item["sequence"], item["operation_id"]))
    if operations != canonical_order:
        raise ContractValidationError("operations must use canonical sequence/operation_id order")
    if require_hash:
        content_hash = plan.get("content_hash")
        if not isinstance(content_hash, str) or not HASH_RE.fullmatch(content_hash):
            raise ContractValidationError("content_hash must be sha256:<64 lowercase hex>")
        expected = compute_content_hash(plan)
        if content_hash != expected:
            raise ContractValidationError("content_hash does not match snapshot content")


def seal_execution_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    sealed = _canonical_content(plan)
    validate_execution_plan(sealed, require_hash=False)
    sealed["content_hash"] = compute_content_hash(sealed)
    validate_execution_plan(sealed)
    return sealed
