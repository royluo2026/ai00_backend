"""Governed BOP fork, smart-fork, and stage-advance mutations."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilitySpec


OPERATIONS = ("fork", "smart_fork", "stage_advance")


def _required(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def apply_bop_fork_change(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    if operation not in OPERATIONS:
        raise ValueError(f"operation must be one of: {', '.join(OPERATIONS)}")
    source_gid = _required(payload, "source_version_gid")
    from ..routers._bop import fork as legacy

    actor = {"gid": context.user_gid}
    if operation == "fork":
        target_tag = _required(payload, "target_version_tag")
        body = legacy.ForkBody(
            target_version_tag=target_tag,
            target_bop_name=str(payload.get("target_bop_name") or ""),
            target_version_family_gid=payload.get("target_version_family_gid"),
            change_note=payload.get("change_note"),
            include_node_types=payload.get("include_node_types"),
            field_rules=payload.get("field_rules") or {},
            meta_key_rules=payload.get("meta_key_rules") or {},
            version_type=payload.get("version_type"),
        )
        return legacy._legacy_fork_version(source_gid, body, actor)
    if operation == "smart_fork":
        target_tag = _required(payload, "target_version_tag")
        body = legacy.SmartForkBody(
            mode=payload.get("mode"),
            target_version_tag=target_tag,
            target_bop_name=str(payload.get("target_bop_name") or ""),
            changed_part_gids=payload.get("changed_part_gids") or [],
            pbom_version_gid=payload.get("pbom_version_gid"),
            copy_depth=payload.get("copy_depth"),
        )
        return legacy._legacy_smart_fork_version(source_gid, body, actor)

    pbom_version_gid = _required(payload, "pbom_version_gid")
    stage_name = _required(payload, "stage_name")
    return legacy._legacy_stage_advance(
        source_gid,
        legacy.StageAdvanceBody(pbom_version_gid=pbom_version_gid, stage_name=stage_name),
        actor,
    )


def register_bop_fork_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.fork.change.apply", owner="craft",
        description="Fork, smart-fork, or stage-advance a BOP version with governed copy semantics.",
        use_when="A governed Craft consumer explicitly creates a derived BOP version from a source version.",
        do_not_use_when="The request only changes a fork preset, freezes links, or updates an existing version in place.",
        risk="write", confirmation="user", idempotent=False, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["operation", "source_version_gid"], "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "properties": {"data": {"type": "object", "additionalProperties": True}, "entries_count": {"type": "integer"}}, "additionalProperties": False},
        tags=("craft", "bop", "fork", "version", "write"),
    ), apply_bop_fork_change)


__all__ = ["OPERATIONS", "apply_bop_fork_change", "register_bop_fork_change_capability"]
