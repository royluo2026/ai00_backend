"""Recursive, fail-closed redaction for governance-to-Agent data."""
from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any


REDACTED = "[REDACTED]"

_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|authorization|cookie|credential|db(?:[_-]?(?:url|uri))?|"
    r"pass(?:word)?|secret|token|url|uri|payload)",
    re.IGNORECASE,
)
_SENSITIVE_VALUE = re.compile(
    r"(?:[a-z][a-z0-9+.-]*://|(?:api[_-]?key|authorization|password|secret|token)\s*[=:])",
    re.IGNORECASE,
)
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}$")
_DECIMAL_GID = re.compile(r"^[0-9]{1,19}$")
_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")


def _identifier(value: Any) -> str | None:
    candidate = str(value)
    return candidate if _IDENTIFIER.fullmatch(candidate) else None


def _gid(value: Any) -> str | None:
    candidate = str(value)
    return candidate if _DECIMAL_GID.fullmatch(candidate) else None


def _hash(value: Any) -> str | None:
    candidate = str(value)
    return candidate if _HASH.fullmatch(candidate) else None


def _identifiers(values: Any) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list, set, frozenset)):
        return ()
    return tuple(item for value in values if (item := _identifier(value)) is not None)


def _gids(values: Any) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list, set, frozenset)):
        return ()
    return tuple(item for value in values if (item := _gid(value)) is not None)


def _hashes(values: Any) -> dict[str, str]:
    if not isinstance(values, Mapping):
        return {}
    return {
        key: digest for raw_key, raw_value in values.items()
        if (key := _identifier(raw_key)) is not None and (digest := _hash(raw_value)) is not None
    }


def _schema_hashes(values: Any) -> dict[str, str]:
    if not isinstance(values, Mapping):
        return {}
    allowed = {"input_schema_hash", "output_schema_hash", "error_schema_hash", "policy_hash", "schema_hash"}
    return {key: digest for key in allowed if (digest := _hash(values.get(key))) is not None}


def redact(value: Any) -> Any:
    """Return a recursive copy with credentials, URLs, and business payloads removed."""
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if _SENSITIVE_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, set | frozenset):
        return tuple(sorted((redact(item) for item in value), key=repr))
    if isinstance(value, str) and _SENSITIVE_VALUE.search(value):
        return REDACTED
    return value


def sanitize_evidence(value: Any) -> dict[str, object]:
    """Keep only evidence identifiers and immutable hashes, never evidence content."""
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, object] = {}
    if keys := _identifiers(value.get("evidence_keys")):
        result["evidence_keys"] = keys
    if hashes := _hashes(value.get("evidence_hashes", value.get("hashes"))):
        result["evidence_hashes"] = hashes
    return result


def sanitize_candidate_package(value: Any) -> dict[str, object]:
    """Allow only fixed candidate metadata; source/business text is discarded."""
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, object] = {}
    if snapshot_gid := _gid(value.get("snapshot_gid")):
        result["snapshot_gid"] = snapshot_gid
    if snapshot_hash := _hash(value.get("snapshot_hash")):
        result["snapshot_hash"] = snapshot_hash
    if candidate_hash := _hash(value.get("candidate_hash")):
        result["candidate_hash"] = candidate_hash
    if relation_type := _identifier(value.get("relation_type")):
        result["relation_type"] = relation_type
    if keys := _identifiers(value.get("capability_keys")):
        result["capability_keys"] = keys
    if comparison := sanitize_evidence(value.get("field_comparison")):
        result["field_comparison"] = comparison
    if ids := _identifiers(value.get("capability_ids")):
        result["capability_ids"] = ids
    if gids := _gids(value.get("capability_version_gids")):
        result["capability_version_gids"] = gids
    capabilities = []
    if isinstance(value.get("capabilities"), (tuple, list)):
        for raw in value["capabilities"]:
            if not isinstance(raw, Mapping):
                continue
            item: dict[str, object] = {}
            if capability_id := _identifier(raw.get("capability_id")):
                item["capability_id"] = capability_id
            if version_gid := _gid(raw.get("capability_version_gid")):
                item["capability_version_gid"] = version_gid
            if hashes := _schema_hashes(raw):
                item["schema_hashes"] = hashes
            if item:
                capabilities.append(item)
    if capabilities:
        result["capabilities"] = tuple(capabilities)
    schema_summaries = []
    if isinstance(value.get("schema_summaries"), (tuple, list)):
        for raw in value["schema_summaries"]:
            if hashes := _schema_hashes(raw):
                schema_summaries.append(hashes)
    if schema_summaries:
        result["schema_summaries"] = tuple(schema_summaries)
    if policies := _hashes(value.get("policies")):
        result["policies"] = policies
    if evidence := sanitize_evidence(value.get("evidence_summaries")):
        result["evidence_summaries"] = evidence
    if model_policy_version := _identifier(value.get("model_policy_version")):
        result["model_policy_version"] = model_policy_version
    if hashes := _hashes(value.get("hashes")):
        result["hashes"] = hashes
    return result


def sanitize_repair_boundary(value: Any) -> dict[str, object]:
    """Allow only immutable repair constraints, never free-form code or business text."""
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, object] = {}
    if snapshot_gid := _gid(value.get("snapshot_gid")):
        result["snapshot_gid"] = snapshot_gid
    if snapshot_hash := _hash(value.get("snapshot_hash")):
        result["snapshot_hash"] = snapshot_hash
    for source, target, normalizer in (
        ("capability_ids", "capability_ids", _identifiers),
        ("capability_version_gids", "capability_version_gids", _gids),
        ("allowed_change_ids", "allowed_change_ids", _identifiers),
        ("forbidden_change_ids", "forbidden_change_ids", _identifiers),
        ("required_test_ids", "required_test_ids", _identifiers),
        ("acceptance_criteria_ids", "acceptance_criteria_ids", _identifiers),
    ):
        if normalized := normalizer(value.get(source)):
            result[target] = normalized
    if hashes := _hashes(value.get("observed_contract_hashes")):
        result["observed_contract_hashes"] = hashes
    return result


__all__ = [
    "REDACTED", "redact", "sanitize_candidate_package", "sanitize_evidence", "sanitize_repair_boundary",
]
