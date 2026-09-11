"""Pure comparison of expected environment manifests and Connector readback."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class VerificationReport:
    state: str
    mismatches: tuple[str, ...]
    probes: tuple[Mapping[str, Any], ...]


def _documents(value: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(sorted(str(item.get("content_sha256") or "") for item in value.get("documents", ())))


def _hierarchies(value: Mapping[str, Any]) -> tuple[tuple[str, int], ...]:
    return tuple(sorted((str(item.get("name") or ""), int(item.get("placement_count") or 0)) for item in value.get("hierarchies", ())))


def compare_runtime_readback(expected: Mapping[str, Any], actual: Mapping[str, Any],
                             sampled_scene: Sequence[Mapping[str, Any]]) -> VerificationReport:
    probes = tuple(dict(item) for item in sampled_scene)
    if any(bool(item.get("outcome_unknown")) for item in probes):
        return VerificationReport(state="outcome_unknown", mismatches=("scene_probe_outcome_unknown",), probes=probes)
    mismatches = []
    if _documents(expected) != _documents(actual): mismatches.append("document_set_mismatch")
    if _hierarchies(expected) != _hierarchies(actual): mismatches.append("alternate_hierarchy_mismatch")
    if any(not bool(item.get("matched")) for item in probes): mismatches.append("scene_probe_failed")
    return VerificationReport(state="failed" if mismatches else "verified", mismatches=tuple(mismatches), probes=probes)


__all__=["VerificationReport","compare_runtime_readback"]
