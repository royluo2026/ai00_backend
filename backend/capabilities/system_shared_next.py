"""Governed shared Capabilities composed exclusively through domain providers."""
from __future__ import annotations

from typing import Any

from backend.system_capabilities.providers import provider_registry, stable_ref
from .models_next import CapabilityContext, CapabilityOutput, CapabilitySpec


def _limit(payload, default=20, maximum=50):
    value = payload.get("limit", default)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f"limit must be between 1 and {maximum}")
    return value


def _aggregate(providers, method, *, limit, args):
    items = []
    for provider in providers:
        for raw in getattr(provider, method)(*args, limit=limit):
            ref = stable_ref(dict(raw), str(provider.owner))
            if ref:
                items.append(ref)
            if len(items) >= limit:
                return items
    return items


def system_search(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    query = str(payload.get("query") or "").strip()
    if not query: raise ValueError("query is required")
    limit = _limit(payload)
    items = []
    for provider in provider_registry.search:
        for raw in provider.search(query, limit, context):
            ref = stable_ref(dict(raw), str(provider.owner))
            if ref: items.append(ref)
            if len(items) == limit: break
        if len(items) == limit: break
    return CapabilityOutput(data={"items": items, "total": len(items), "query": query})


def activity_search(payload, context):
    limit = _limit(payload, 20, 100); items = []
    for provider in provider_registry.activity:
        items.extend(provider.search(payload, limit, context))
        if len(items) >= limit: break
    return CapabilityOutput(data={"items": items[:limit], "total": min(len(items), limit)})


def get_job(payload, context):
    owner = str(payload.get("owner") or ""); provider = provider_registry.jobs.get(owner)
    if not provider: raise LookupError("job owner provider not found")
    return CapabilityOutput(data={**provider.get(str(payload.get("job_gid") or ""), context), "rolled_back": False})


def cancel_job(payload, context):
    owner = str(payload.get("owner") or ""); provider = provider_registry.jobs.get(owner)
    if not provider: raise LookupError("job owner provider not found")
    return CapabilityOutput(data={**provider.cancel(str(payload.get("job_gid") or ""), context), "rolled_back": False})


def principal_search(payload, context):
    query = str(payload.get("query") or "").strip(); limit = _limit(payload)
    items = []
    for provider in provider_registry.identity:
        items.extend(provider.search(query, limit, context))
        if len(items) >= limit: break
    return CapabilityOutput(data={"items": items[:limit], "total": min(len(items), limit)})


def lineage_get(payload, context):
    object_ref = str(payload.get("object_ref") or "").strip()
    if not object_ref: raise ValueError("object_ref is required")
    events = []; breaks = []
    for provider in provider_registry.lineage:
        result = provider.get(object_ref, context); events.extend(result.get("events", [])); breaks.extend(result.get("breaks", []))
    return CapabilityOutput(data={"object_ref": object_ref, "events": events, "breaks": breaks, "complete": bool(events) and not breaks})


def preview_impact(payload, context):
    change_ref = str(payload.get("change_ref") or "").strip()
    if not change_ref.startswith(("preview://", "diff://")): raise ValueError("change_ref must be a server-issued preview:// or diff:// reference")
    items=[]; unknown=[]
    for provider in provider_registry.impact:
        result=provider.preview(change_ref, context); items.extend(result.get("items", [])); unknown.extend(result.get("unknown", []))
    return CapabilityOutput(data={"change_ref": change_ref, "items": items, "unknown": unknown})


def semantic_context(payload, context):
    named_view = str(payload.get("named_view") or "").strip()
    allowed={"object_neighborhood", "decision_context", "knowledge_links"}
    if named_view not in allowed: raise ValueError("named_view must be an allowlisted semantic view")
    depth=int(payload.get("depth") or 1); limit=_limit(payload, 25, 100)
    if not 1 <= depth <= 3: raise ValueError("depth must be between 1 and 3")
    items=[]
    for provider in provider_registry.semantic:
        items.extend(provider.get(named_view, payload, depth, limit, context))
        if len(items)>=limit: break
    return CapabilityOutput(data={"named_view": named_view, "items": items[:limit], "depth": depth})


def register_system_shared_capabilities(registry: Any) -> None:
    defs=(
        ("system.search", system_search, "Search stable references across registered domain providers.", "read", (), ["query"]),
        ("system.activity.search", activity_search, "Search immutable activity summaries.", "read", (), []),
        ("system.job.get", get_job, "Read one owner-scoped asynchronous job.", "read", (), ["job_gid","owner"]),
        ("system.job.cancel", cancel_job, "Request job cancellation without claiming rollback.", "write", (), ["job_gid","owner"]),
        ("identity.principal.search", principal_search, "Search bounded principal summaries.", "read", (), ["query"]),
        ("system.lineage.get", lineage_get, "Compose immutable provenance events and completeness.", "read", (), ["object_ref"]),
        ("system.change_impact.preview", preview_impact, "Compose impact from a server-issued preview or diff ref.", "read", (), ["change_ref"]),
        ("semantic.context.get", semantic_context, "Read an allowlisted bounded semantic named view.", "read", (), ["named_view"]),
    )
    for capability_id, handler, description, risk, permissions, required in defs:
        registry.register(CapabilitySpec(
            id=capability_id, owner="base", plugin_callable=False, description=description,
            use_when="A bounded shared-system composition is required.", do_not_use_when="A domain-specific stable ref is already known.",
            subject_concepts=("system.object_ref",), effects=(("request:system.job_cancel",) if capability_id=="system.job.cancel" else ("read:system.ref",)),
            risk=risk, confirmation="user" if risk=="write" else "none", permissions=permissions,
            input_schema={"type":"object","required":required}, output_schema={"type":"object"}, tags=("system","shared")), handler)
