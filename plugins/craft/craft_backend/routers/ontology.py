"""Legacy Ontology HTTP routes implemented only as governed Gateway adapters.

The compatibility surface intentionally contains no Ontology or foreign-domain
SQL. Mutable schema operations create proposals; historical endpoints that
depended on dynamic cross-domain table access are retired explicitly.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from backend.capability_v2.contracts import (
    ActorIdentity,
    ConsumerDescriptor,
    ConsumerIdentity,
    ConsumerType,
    InvocationEnvelope,
    TenantIdentity,
)
from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.auth import get_authenticated_principal, get_current_user


router = APIRouter(tags=["ontology"])


class _LooseBody(BaseModel):
    model_config = ConfigDict(extra="allow")


ClassBody = PropBody = RelBody = AxiomBody = _LooseBody


def _identity(user: dict, principal: Any) -> ConsumerIdentity:
    return ConsumerIdentity(
        actor=ActorIdentity(**principal.model_dump()),
        tenant=TenantIdentity(
            tenant_id=str(user.get("team_id") or "default"),
            membership="member",
            active_roles=tuple(filter(None, (user.get("org_role"), user.get("system_role")))),
        ),
        consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id="ai00.web.ontology-compat"),
    )


async def _invoke(
    capability_id: str,
    payload: dict,
    user: dict,
    principal: Any,
    *,
    write: bool = False,
) -> Any:
    gateway = get_default_gateway()
    request_id = f"onto_compat_{uuid.uuid4().hex}"
    result = await gateway.invoke(
        InvocationEnvelope(
            capability_id=capability_id,
            major_version=1,
            catalog_release=gateway.catalog_release,
            payload=payload,
            identity=_identity(user, principal),
            idempotency_key=request_id if write else None,
            request_id=request_id,
            trace_id=request_id,
        )
    )
    if not result.ok:
        detail = result.error.model_dump(mode="json") if result.error else {"code": "capability_failed"}
        raise HTTPException(status_code=422, detail=detail)
    return result.data


async def _active_release(user: dict, principal: Any) -> str:
    release = await _invoke("ontology.release.get", {}, user, principal)
    release_gid = (release or {}).get("release_gid") or (release or {}).get("gid")
    if not release_gid:
        raise HTTPException(status_code=409, detail={"code": "active_release_required"})
    return str(release_gid)


async def _propose(change: dict, user: dict, principal: Any) -> Any:
    base_release_gid = change.pop("base_release_gid", None) or await _active_release(user, principal)
    return await _invoke(
        "ontology.schema.change.apply",
        {"base_release_gid": base_release_gid, "changes": [change]},
        user,
        principal,
        write=True,
    )


def _retired() -> None:
    raise HTTPException(
        status_code=410,
        detail={
            "code": "legacy_cross_domain_endpoint_retired",
            "message": "Use immutable Ontology release refs and the owning domain capability.",
        },
    )


@router.get("/api/ontology/classes")
async def list_classes(_u=Depends(get_current_user), _p=Depends(get_authenticated_principal)):
    return await _invoke("ontology.release.get", {}, _u, _p)


@router.post("/api/ontology/classes", status_code=201)
async def create_class(body: ClassBody, _u=Depends(get_current_user), _p=Depends(get_authenticated_principal)):
    return await _propose({"change_type": "concept.create", "after": body.model_dump(exclude_none=True)}, _u, _p)


@router.patch("/api/ontology/classes/{gid}")
async def update_class(gid: str, body: dict, _u=Depends(get_current_user), _p=Depends(get_authenticated_principal)):
    return await _propose({"change_type": "concept.update", "stable_gid": gid, "after": body}, _u, _p)


@router.delete("/api/ontology/classes/{gid}", status_code=204)
async def delete_class(gid: str, _u=Depends(get_current_user), _p=Depends(get_authenticated_principal)):
    await _propose({"change_type": "concept.archive", "stable_gid": gid}, _u, _p)


@router.get("/api/ontology/classes/{gid}/full")
async def get_class_full(gid: str, _u=Depends(get_current_user), _p=Depends(get_authenticated_principal)):
    return await _invoke("ontology.concept.get", {"stable_gid": gid, "kind": "concept", "view": "schema"}, _u, _p)


@router.post("/api/ontology/properties", status_code=201)
async def create_property(body: PropBody, _u=Depends(get_current_user), _p=Depends(get_authenticated_principal)):
    return await _propose({"change_type": "property.create", "after": body.model_dump(exclude_none=True)}, _u, _p)


@router.patch("/api/ontology/properties/{gid}")
async def update_property(gid: str, body: dict, _u=Depends(get_current_user), _p=Depends(get_authenticated_principal)):
    return await _propose({"change_type": "property.update", "stable_gid": gid, "after": body}, _u, _p)


@router.delete("/api/ontology/properties/{gid}", status_code=204)
async def delete_property(gid: str, _u=Depends(get_current_user), _p=Depends(get_authenticated_principal)):
    await _propose({"change_type": "property.archive", "stable_gid": gid}, _u, _p)


@router.post("/api/ontology/relations", status_code=201)
async def create_relation(body: RelBody, _u=Depends(get_current_user), _p=Depends(get_authenticated_principal)):
    return await _propose({"change_type": "relation.create", "after": body.model_dump(exclude_none=True)}, _u, _p)


@router.patch("/api/ontology/relations/{gid}")
async def update_relation(gid: str, body: dict, _u=Depends(get_current_user), _p=Depends(get_authenticated_principal)):
    return await _propose({"change_type": "relation.update", "stable_gid": gid, "after": body}, _u, _p)


@router.delete("/api/ontology/relations/{gid}", status_code=204)
async def delete_relation(gid: str, _u=Depends(get_current_user), _p=Depends(get_authenticated_principal)):
    await _propose({"change_type": "relation.archive", "stable_gid": gid}, _u, _p)


@router.post("/api/ontology/axioms", status_code=201)
async def create_axiom(body: AxiomBody, _u=Depends(get_current_user), _p=Depends(get_authenticated_principal)):
    return await _propose({"change_type": "constraint.create", "after": body.model_dump(exclude_none=True)}, _u, _p)


@router.delete("/api/ontology/axioms/{gid}", status_code=204)
async def delete_axiom(gid: str, _u=Depends(get_current_user), _p=Depends(get_authenticated_principal)):
    await _propose({"change_type": "constraint.archive", "stable_gid": gid}, _u, _p)


@router.get("/api/ontology/schema/{node_type}")
async def get_class_schema(node_type: str, _u=Depends(get_current_user), _p=Depends(get_authenticated_principal)):
    resolved = await _invoke("ontology.concept.resolve", {"term": node_type}, _u, _p)
    stable_gid = (resolved or {}).get("stable_gid")
    if not stable_gid:
        raise HTTPException(status_code=404, detail={"code": "resource_not_found"})
    return await _invoke("ontology.concept.get", {"stable_gid": stable_gid, "kind": "concept", "view": "schema"}, _u, _p)


@router.get("/api/ontology/graph")
async def get_graph(_u=Depends(get_current_user), _p=Depends(get_authenticated_principal)):
    return await _invoke("ontology.release.get", {}, _u, _p)


@router.get("/api/ontology/classes/{gid}/axioms")
async def list_class_axioms(gid: str, include_inherited: bool = True, _u=Depends(get_current_user), _p=Depends(get_authenticated_principal)):
    return await _invoke("ontology.concept.get", {"stable_gid": gid, "kind": "concept", "view": "schema"}, _u, _p)


@router.get("/api/ontology/db-tables")
def list_db_tables(_u=Depends(get_current_user)): _retired()

@router.get("/api/ontology/node-type-suggestions")
def list_node_type_suggestions(_u=Depends(get_current_user)): _retired()

@router.get("/api/ontology/unbound-classes")
def list_unbound_classes(_u=Depends(get_current_user)): _retired()

@router.get("/api/ontology/classes/{gid}/individuals")
def list_class_individuals(gid: str, limit: int = 20, _u=Depends(get_current_user)): _retired()

@router.post("/api/ontology/classes/{gid}/sync-from-table")
def sync_props_from_table(gid: str, _u=Depends(get_current_user)): _retired()

@router.post("/api/ontology/seed")
def seed_from_bop(_u=Depends(get_current_user)): _retired()

@router.get("/api/bop/entries/{entry_gid}/entity-props")
def get_entity_props(entry_gid: str, _u=Depends(get_current_user)): _retired()

@router.patch("/api/bop/entries/{entry_gid}/entity-props")
def patch_entity_props(entry_gid: str, body: dict, _u=Depends(get_current_user)): _retired()

@router.get("/api/ontology/schema-diff")
def schema_diff(_u=Depends(get_current_user)): _retired()

@router.get("/api/ontology/node-type-config")
def get_node_type_config(_u=Depends(get_current_user)): _retired()

@router.post("/api/ontology/validate/{entry_gid}")
def validate_entry(entry_gid: str, _u=Depends(get_current_user)): _retired()

@router.get("/api/ontology/agent-schema")
def get_agent_schema(_u=Depends(get_current_user)): _retired()
