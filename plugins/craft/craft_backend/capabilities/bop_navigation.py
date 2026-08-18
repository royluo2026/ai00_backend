"""Bounded, revision-pinned BOP navigation Capability adapters."""
from __future__ import annotations

from typing import Any, Mapping

from backend.capability_v2.provider_contracts import (
    CapabilityContext, CapabilityExecutionBudget, CapabilityOutput, CapabilitySpec, EvidenceRef,
)

from ..services.bop_navigation import repository


def _reject_unknown(payload: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"unsupported fields: {', '.join(unknown)}")


def _text(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _revision(payload: Mapping[str, Any]) -> int:
    value = payload.get("revision")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("revision must be an integer >= 1")
    return value


def _page_size(payload: Mapping[str, Any], default: int, maximum: int) -> int:
    value = payload.get("page_size", default)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f"page_size must be between 1 and {maximum}")
    return value


def _cursor(payload: Mapping[str, Any]) -> str | None:
    value = payload.get("cursor")
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError("cursor must be a non-empty string")
    return value


def _evidence(kind: str, version_gid: str, revision: int, suffix: str) -> EvidenceRef:
    return EvidenceRef(
        kind=kind,
        reference=f"craft://bop/version/{version_gid}/{suffix}/r{revision}",
        summary=f"Bounded BOP navigation projection for revision {revision}",
        metadata={"version_gid": version_gid, "revision": revision},
    )


def get_outline(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    _reject_unknown(payload, {"version_gid", "revision", "cursor", "page_size"})
    version_gid = _text(payload, "version_gid"); revision = _revision(payload)
    data = repository.get_outline_page(
        version_gid, revision, cursor=_cursor(payload), page_size=_page_size(payload, 50, 100),
    )
    return CapabilityOutput(
        data=data,
        evidence=(_evidence("craft.bop.structure.outline", version_gid, revision, "outline"),),
    )


def get_work_package_page(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    _reject_unknown(payload, {
        "version_gid", "revision", "scope_kind", "scope_gid", "cursor", "page_size",
    })
    version_gid = _text(payload, "version_gid"); revision = _revision(payload)
    scope_kind = _text(payload, "scope_kind")
    if scope_kind not in {"line", "station"}:
        raise ValueError("scope_kind must be line or station")
    scope_gid = _text(payload, "scope_gid")
    data = repository.get_work_package_page(
        version_gid, revision, scope_kind, scope_gid,
        cursor=_cursor(payload), page_size=_page_size(payload, 100, 200),
    )
    return CapabilityOutput(
        data=data,
        evidence=(_evidence(
            "craft.bop.work_package", version_gid, revision,
            f"work-package/{scope_kind}/{scope_gid}",
        ),),
    )


def get_entry_detail(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    _reject_unknown(payload, {"version_gid", "revision", "entry_gid"})
    version_gid = _text(payload, "version_gid"); revision = _revision(payload)
    entry_gid = _text(payload, "entry_gid")
    data = repository.get_entry_detail(version_gid, revision, entry_gid)
    return CapabilityOutput(
        data=data,
        evidence=(_evidence(
            "craft.bop.entry.detail", version_gid, revision, f"entry/{entry_gid}",
        ),),
    )


def register_bop_navigation_capabilities(registry: Any) -> None:
    common = {
        "owner": "craft", "plugin_callable": True, "permissions": (),
        "subject_concepts": ("craft.bop.version", "craft.bop.entry"),
        "tags": ("craft", "bop", "navigation", "bounded", "read"),
    }
    registry.register(CapabilitySpec(
        id="craft.bop.structure.outline.get", version=1,
        description="Read one bounded page of the navigable BOP structure outline.",
        use_when="A consumer needs BOP lines and aggregate counts before loading details.",
        do_not_use_when="A consumer needs an official complete execution structure.",
        effects=("read:craft.bop.structure.outline",),
        execution_budget=CapabilityExecutionBudget(
            memory_class="small", max_input_bytes=64 * 1024,
            max_output_bytes=512 * 1024, collection_policy="paged", max_page_size=100,
            max_parallel_per_consumer=1, max_parallel_per_tenant=8,
        ),
        **common,
    ), get_outline)
    registry.register(CapabilitySpec(
        id="craft.bop.work_package.get", version=2,
        description="Read one bounded page of a line or station BOP work package.",
        use_when="A consumer needs lightweight nodes and references for one BOP scope.",
        do_not_use_when="A consumer needs the complete BOP or a role projection from version 1.",
        effects=("read:craft.bop.work_package",),
        execution_budget=CapabilityExecutionBudget(
            memory_class="medium", max_input_bytes=64 * 1024,
            max_output_bytes=1024 * 1024, collection_policy="paged", max_page_size=200,
            max_parallel_per_consumer=1, max_parallel_per_tenant=4,
        ),
        **common,
    ), get_work_package_page)
    registry.register(CapabilitySpec(
        id="craft.bop.entry.detail.get", version=1,
        description="Read the full governed detail of one BOP entry at an exact revision.",
        use_when="A consumer selects one BOP node and needs its complete detail.",
        do_not_use_when="A consumer is rendering a BOP list or outline.",
        effects=("read:craft.bop.entry.detail",),
        execution_budget=CapabilityExecutionBudget(
            memory_class="small", max_input_bytes=64 * 1024,
            max_output_bytes=512 * 1024, collection_policy="bounded",
            max_parallel_per_consumer=4, max_parallel_per_tenant=16,
        ),
        **common,
    ), get_entry_detail)


__all__ = [
    "get_entry_detail", "get_outline", "get_work_package_page",
    "register_bop_navigation_capabilities",
]
