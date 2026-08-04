"""Simulation-side pin and verification rules for Craft execution plans."""
from __future__ import annotations

from typing import Any, Mapping

from .craft_execution_plan_v1 import ContractValidationError, compute_content_hash, validate_execution_plan


def pin_environment_source(plan: Mapping[str, Any], snapshot_uri: str) -> dict[str, Any]:
    validate_execution_plan(plan)
    if not isinstance(snapshot_uri, str) or not snapshot_uri.strip():
        raise ContractValidationError("snapshot_uri must be a non-empty immutable OIS reference")
    source = plan["source"]
    return {
        "contract_id": "simulation.environment-source",
        "contract_version": 1,
        "source_bop_version_gid": source["bop_version_gid"],
        "source_bop_revision": source["revision"],
        "source_bop_hash": plan["content_hash"],
        "execution_plan_snapshot_uri": snapshot_uri,
    }


def verify_environment_source(pinned: Mapping[str, Any], plan: Mapping[str, Any]) -> None:
    validate_execution_plan(plan)
    expected = pin_environment_source(plan, pinned.get("execution_plan_snapshot_uri", ""))
    for key in (
        "contract_id",
        "contract_version",
        "source_bop_version_gid",
        "source_bop_revision",
        "source_bop_hash",
    ):
        if pinned.get(key) != expected[key]:
            raise ContractValidationError(f"pinned Simulation source mismatch: {key}")
    if pinned["source_bop_hash"] != compute_content_hash(plan):
        raise ContractValidationError("pinned source hash does not match execution plan")
