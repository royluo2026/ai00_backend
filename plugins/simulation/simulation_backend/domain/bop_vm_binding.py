"""Deterministic first-pass BOP-to-VM binding suggestions.

Only owner-supplied exact identities may become automatic candidates. Names,
counts and topology are deliberately excluded: they are useful review hints but
are not safe identities.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping
import unicodedata


def _identity(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip().casefold()


def build_binding_draft(
    execution: Mapping[str, Any], snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    operations = sorted(
        (dict(item) for item in execution.get("operations", ()) if isinstance(item, Mapping)),
        key=lambda item: str(item.get("operation_id") or ""),
    )
    vm_nodes = sorted(
        (dict(item) for item in snapshot.get("nodes", ()) if isinstance(item, Mapping)),
        key=lambda item: str(item.get("node_key") or ""),
    )
    vm_by_identity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in vm_nodes:
        key = _identity(node.get("product_ref"))
        if key:
            vm_by_identity[key].append(node)

    has_parts = any(operation.get("products") for operation in operations)
    has_vpps = any(_identity((operation.get("parameters") or {}).get("vpps")) for operation in operations)
    mode = "parts" if has_parts else "vpps" if has_vpps else "structure_only"
    bindings: list[dict[str, Any]] = []
    unmatched_bop: list[str] = []
    claimed_vm: set[str] = set()

    for operation in operations:
        operation_id = str(operation.get("operation_id") or "")
        parameters = operation.get("parameters") if isinstance(operation.get("parameters"), Mapping) else {}
        role = "load" if parameters.get("is_load_part") is True else "operate"
        if mode == "parts":
            identities = sorted({_identity(item.get("product_ref")) for item in operation.get("products", ())
                                 if isinstance(item, Mapping) and _identity(item.get("product_ref"))})
            basis, confidence = "product_ref_exact", 970
        elif mode == "vpps":
            value = _identity(parameters.get("vpps"))
            identities = [value] if value else []
            basis, confidence = "vpps_exact", 960
        else:
            identities, basis, confidence = [], "none", 0

        operation_matched = False
        for identity in identities:
            candidates = vm_by_identity.get(identity, [])
            if not candidates:
                continue
            operation_matched = True
            disposition = "auto" if len(candidates) == 1 else "ambiguous"
            for node in candidates:
                node_key = str(node.get("node_key") or "")
                claimed_vm.add(node_key)
                bindings.append({
                    "bop_node_gid": operation_id,
                    "vm_node_key": node_key,
                    "role": role,
                    "disposition": disposition,
                    "confidence_milli": confidence if disposition == "auto" else 800,
                    "match_basis": basis,
                    "conflict_code": "duplicate_vm_identity" if disposition == "ambiguous" else "",
                })
        if not operation_matched:
            unmatched_bop.append(operation_id)

    load_by_vm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in bindings:
        if item["role"] == "load" and item["disposition"] == "auto":
            load_by_vm[item["vm_node_key"]].append(item)
    for conflicts in load_by_vm.values():
        if len(conflicts) > 1:
            for item in conflicts:
                item.update(disposition="conflict", confidence_milli=0, conflict_code="multiple_load_claims")

    bindings.sort(key=lambda item: (item["bop_node_gid"], item["vm_node_key"], item["role"]))
    return {
        "mode": mode,
        "bindings": bindings,
        "auto_count": sum(item["disposition"] == "auto" for item in bindings),
        "review_count": sum(item["disposition"] != "auto" for item in bindings),
        "unmatched_bop_node_gids": sorted(set(unmatched_bop)),
        "unmatched_vm_node_keys": sorted(
            str(node.get("node_key") or "") for node in vm_nodes
            if str(node.get("node_key") or "") not in claimed_vm
        ),
    }


__all__ = ["build_binding_draft"]
