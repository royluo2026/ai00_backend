"""Governance of descriptors that still expose an operation envelope."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping


class AtomicityConfigurationError(ValueError):
    """Raised when the atomicity disposition ledger is malformed."""


@dataclass(frozen=True)
class AtomicityDisposition:
    capability_id: str
    major_version: int
    disposition: str
    replacement_capabilities: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    approval_reference: str | None = None
    expires_on: date | None = None

    @property
    def key(self) -> str:
        return f"{self.capability_id}@{self.major_version}"


@dataclass(frozen=True)
class AtomicityDispositionReport:
    dispositions: tuple[AtomicityDisposition, ...]

    @property
    def by_key(self) -> dict[str, AtomicityDisposition]:
        return {item.key: item for item in self.dispositions}


@dataclass(frozen=True)
class AtomicityAudit:
    generic_ids: tuple[str, ...]
    unclassified_ids: tuple[str, ...]
    invalid_ids: tuple[str, ...]
    expired_ids: tuple[str, ...]
    missing_replacement_ids: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not (
            self.unclassified_ids
            or self.invalid_ids
            or self.expired_ids
            or self.missing_replacement_ids
        )


def _read_json(path: Path) -> Mapping[str, Any]:
    if not path.is_file():
        raise AtomicityConfigurationError(f"missing atomicity disposition ledger: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AtomicityConfigurationError(f"invalid atomicity disposition ledger: {path}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("dispositions"), list):
        raise AtomicityConfigurationError("atomicity dispositions must be an array")
    return document


def load_atomicity_dispositions(path: Path) -> AtomicityDispositionReport:
    document = _read_json(path)
    result: list[AtomicityDisposition] = []
    seen: set[str] = set()
    for raw in document["dispositions"]:
        if not isinstance(raw, dict):
            raise AtomicityConfigurationError("atomicity disposition must be an object")
        capability_id = raw.get("capability_id")
        major_version = raw.get("major_version")
        disposition = raw.get("disposition")
        if not isinstance(capability_id, str) or not capability_id:
            raise AtomicityConfigurationError("atomicity capability_id is required")
        if not isinstance(major_version, int) or major_version < 1:
            raise AtomicityConfigurationError(f"invalid major_version for {capability_id}")
        if disposition not in {"split", "justified", "retire"}:
            raise AtomicityConfigurationError(f"invalid disposition for {capability_id}@{major_version}")
        key = f"{capability_id}@{major_version}"
        if key in seen:
            raise AtomicityConfigurationError(f"duplicate atomicity disposition: {key}")
        seen.add(key)
        replacements = raw.get("replacement_capabilities", [])
        evidence = raw.get("evidence_refs", [])
        if not isinstance(replacements, list) or not all(isinstance(item, str) and item for item in replacements):
            raise AtomicityConfigurationError(f"invalid replacement_capabilities for {key}")
        if not isinstance(evidence, list) or not all(isinstance(item, str) and item for item in evidence):
            raise AtomicityConfigurationError(f"invalid evidence_refs for {key}")
        expires_on = raw.get("expires_on")
        parsed_expiry: date | None = None
        if expires_on is not None:
            if not isinstance(expires_on, str):
                raise AtomicityConfigurationError(f"invalid expires_on for {key}")
            try:
                parsed_expiry = date.fromisoformat(expires_on)
            except ValueError as exc:
                raise AtomicityConfigurationError(f"invalid expires_on for {key}") from exc
        approval = raw.get("approval_reference")
        if approval is not None and (not isinstance(approval, str) or not approval):
            raise AtomicityConfigurationError(f"invalid approval_reference for {key}")
        result.append(
            AtomicityDisposition(
                capability_id=capability_id,
                major_version=major_version,
                disposition=disposition,
                replacement_capabilities=tuple(replacements),
                evidence_refs=tuple(evidence),
                approval_reference=approval,
                expires_on=parsed_expiry,
            )
        )
    return AtomicityDispositionReport(tuple(result))


def _generic_entries(catalog: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    entries = catalog.get("capabilities")
    if not isinstance(entries, list):
        raise AtomicityConfigurationError("catalog capabilities must be an array")
    result: list[Mapping[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("lifecycle_status") != "stable":
            continue
        schema = entry.get("input_schema")
        props = schema.get("properties") if isinstance(schema, dict) else None
        if isinstance(props, dict) and {"operation", "arguments"} <= set(props):
            result.append(entry)
    return result


def audit_generic_operations(
    catalog: Mapping[str, Any], dispositions: AtomicityDispositionReport
) -> AtomicityAudit:
    entries = _generic_entries(catalog)
    generic_ids = tuple(sorted(f"{e['id']}@{e.get('major_version', 1)}" for e in entries))
    by_key = dispositions.by_key
    unclassified: list[str] = []
    invalid: list[str] = []
    expired: list[str] = []
    missing_replacements: list[str] = []
    catalog_ids = {
        f"{e.get('id')}@{e.get('major_version', 1)}"
        for e in catalog.get("capabilities", [])
        if isinstance(e, dict)
    }
    for key in generic_ids:
        item = by_key.get(key)
        if item is None:
            unclassified.append(key)
            continue
        if not item.evidence_refs:
            invalid.append(key)
        if item.disposition == "split":
            if not item.replacement_capabilities:
                missing_replacements.append(key)
            elif any(
                replacement not in catalog_ids
                and f"{replacement}@1" not in catalog_ids
                for replacement in item.replacement_capabilities
            ):
                missing_replacements.append(key)
        elif item.disposition == "justified":
            if not item.approval_reference or item.expires_on is None:
                invalid.append(key)
            elif item.expires_on < date.today():
                expired.append(key)
        elif item.disposition == "retire":
            if item.replacement_capabilities or not item.evidence_refs:
                invalid.append(key)
    return AtomicityAudit(
        generic_ids=generic_ids,
        unclassified_ids=tuple(unclassified),
        invalid_ids=tuple(invalid),
        expired_ids=tuple(expired),
        missing_replacement_ids=tuple(missing_replacements),
    )


__all__ = [
    "AtomicityAudit",
    "AtomicityConfigurationError",
    "AtomicityDisposition",
    "AtomicityDispositionReport",
    "audit_generic_operations",
    "load_atomicity_dispositions",
]
