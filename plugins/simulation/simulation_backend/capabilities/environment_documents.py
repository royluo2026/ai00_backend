"""Atomic governed access to Simulation environment model documents."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilityOutput, CapabilitySpec, EvidenceRef

from ..data.workspace_repository import WorkspaceRepository, WorkspaceRepositoryError


def _scope(context: CapabilityContext) -> tuple[str, str]:
    tenant_gid, actor_gid = str(context.team_gid or ""), str(context.user_gid or "")
    if not tenant_gid or not actor_gid:
        raise CapabilityBusinessError("workspace_identity_required", "workspace_identity_required")
    return tenant_gid, actor_gid


def _output(data: Any, action: str, workspace_gid: str) -> CapabilityOutput:
    body = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return CapabilityOutput(data=data, evidence=(EvidenceRef(
        kind="simulation.environment.model_document", reference=f"simulation://workspace/{workspace_gid}/documents",
        digest="sha256:" + hashlib.sha256(body.encode()).hexdigest(), summary=action,
    ),))


class EnvironmentDocumentProvider:
    def __init__(self, repository: WorkspaceRepository | None = None) -> None:
        self.repository = repository or WorkspaceRepository()

    def search(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        tenant_gid, actor_gid = _scope(context); workspace_gid = str(payload.get("workspace_gid") or "")
        try:
            return _output(self.repository.search_model_documents(workspace_gid=workspace_gid, tenant_gid=tenant_gid, actor_gid=actor_gid), "model_documents_searched", workspace_gid)
        except WorkspaceRepositoryError as exc:
            raise CapabilityBusinessError(str(exc), str(exc)) from exc

    def add(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        tenant_gid, actor_gid = _scope(context); workspace_gid = str(payload.get("workspace_gid") or "")
        if payload.get("portability") == "device_bound" and not payload.get("connector_device_id"):
            raise CapabilityBusinessError("connector_device_id_required", "connector_device_id_required")
        document = {key: payload.get(key) for key in (
            "role", "display_name", "media_type", "artifact_ref", "source_kind",
            "source_identity_hash", "content_sha256", "portability", "connector_device_id",
        )}
        document["media_type"] = {"model/jt": "model/vnd.jt"}.get(str(document["media_type"]), document["media_type"])
        if document["role"] == "primary" and document["media_type"] != "application/plmxml+xml":
            raise CapabilityBusinessError("primary_plmxml_document_required", "primary_plmxml_document_required")
        try:
            data = self.repository.add_model_document(
                workspace_gid=workspace_gid, expected_workspace_version=payload.get("expected_row_version"),
                document=document, actor_gid=actor_gid, tenant_gid=tenant_gid,
                idempotency_key=str(payload.get("idempotency_key") or ""),
            )
            return _output(data, "model_document_added", workspace_gid)
        except WorkspaceRepositoryError as exc:
            raise CapabilityBusinessError(str(exc), str(exc), retryable=str(exc) == "version_conflict") from exc

    def remove(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        tenant_gid, actor_gid = _scope(context); workspace_gid = str(payload.get("workspace_gid") or "")
        try:
            data = self.repository.remove_model_document(
                workspace_gid=workspace_gid, document_gid=str(payload.get("document_gid") or ""),
                expected_workspace_version=payload.get("expected_row_version"), actor_gid=actor_gid, tenant_gid=tenant_gid,
                idempotency_key=str(payload.get("idempotency_key") or ""),
            )
            return _output(data, "model_document_removed", workspace_gid)
        except WorkspaceRepositoryError as exc:
            raise CapabilityBusinessError(str(exc), str(exc), retryable=str(exc) == "version_conflict") from exc


def specs(provider: EnvironmentDocumentProvider | None = None):
    selected = provider or EnvironmentDocumentProvider()
    gid = {"type": "string", "pattern": "^[1-9][0-9]*$"}; sha = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
    common = dict(owner="simulation", permissions=("simulation.use",), plugin_callable=True, tags=("simulation", "environment_document", "experimental"))
    doc_input = {"workspace_gid": gid, "expected_row_version": {"type": "integer", "minimum": 1},
        "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 191},
        "role": {"type": "string", "enum": ["primary", "inserted"]}, "display_name": {"type": "string", "maxLength": 255},
        "media_type": {"type": "string", "enum": ["application/plmxml+xml", "application/vnd.siemens.plmxml+xml", "model/vnd.jt", "model/jt"]}, "artifact_ref": {"type":"object"},
        "source_kind": {"type": "string", "enum": ["artifact", "local_file", "generated"]},
        "source_identity_hash": sha, "content_sha256": sha, "portability": {"type": "string", "enum": ["portable", "device_bound"]},
        "connector_device_id": {"type":"string","minLength":1,"maxLength":191}}
    artifact = {"type":"object","required":["artifact_id","media_type","sha256","byte_size","version"],"properties":{"artifact_id":{"type":"string"},"media_type":{"type":"string"},"sha256":{"type":"string","pattern":"^[0-9a-f]{64}$"},"byte_size":{"type":"integer","minimum":0},"version":{"type":"integer","minimum":1}},"additionalProperties":False}
    doc_input["artifact_ref"] = artifact
    doc = {"type":"object","required":["document_gid","workspace_gid","role","display_name","media_type","artifact_ref","source_kind","source_identity_hash","content_sha256","portability","connector_device_id","sort_order","row_version"],"properties":{"document_gid":gid,"workspace_gid":gid,"role":doc_input["role"],"display_name":doc_input["display_name"],"media_type":doc_input["media_type"],"artifact_ref":{"anyOf":[artifact,{"type":"null"}]},"source_kind":{"type":"string"},"source_identity_hash":sha,"content_sha256":sha,"portability":doc_input["portability"],"connector_device_id":{"anyOf":[doc_input["connector_device_id"],{"type":"null"}]},"sort_order":{"type":"integer","minimum":0},"row_version":{"type":"integer","minimum":1}},"additionalProperties":False}
    add_output={"type":"object","required":["document_gid","workspace_gid","role","row_version","workspace_row_version","cache_revision_hash"],"properties":{"document_gid":gid,"workspace_gid":gid,"role":doc_input["role"],"row_version":{"type":"integer","minimum":1},"workspace_row_version":{"type":"integer","minimum":2},"cache_revision_hash":sha},"additionalProperties":False}
    remove_output={"type":"object","required":["document_gid","workspace_gid","removed","workspace_row_version","cache_revision_hash"],"properties":{"document_gid":gid,"workspace_gid":gid,"removed":{"const":True},"workspace_row_version":{"type":"integer","minimum":2},"cache_revision_hash":sha},"additionalProperties":False}
    return (
        (CapabilitySpec(id="simulation.environment.model_document.search", version=1, description="Search model documents in one readable Simulation environment.", risk="read", confirmation="none", input_schema={"type":"object","required":["workspace_gid"],"properties":{"workspace_gid":gid},"additionalProperties":False}, output_schema={"type":"object","required":["items"],"properties":{"items":{"type":"array","items":doc}},"additionalProperties":False}, **common), selected.search),
        (CapabilitySpec(id="simulation.environment.model_document.add", version=1, description="Add one PLMXML or JT model document to an owned Simulation environment.", risk="write", confirmation="none", idempotent=True, input_schema={"type":"object","required":[key for key in doc_input if key != "connector_device_id"],"properties":doc_input,"additionalProperties":False}, output_schema=add_output, **common), selected.add),
        (CapabilitySpec(id="simulation.environment.model_document.remove", version=1, description="Soft-remove one model document from an owned Simulation environment.", risk="write", confirmation="user", idempotent=True, input_schema={"type":"object","required":["workspace_gid","document_gid","expected_row_version","idempotency_key"],"properties":{"workspace_gid":gid,"document_gid":gid,"expected_row_version":{"type":"integer","minimum":1},"idempotency_key":{"type":"string","minLength":1,"maxLength":191}},"additionalProperties":False}, output_schema=remove_output, **common), selected.remove),
    )


__all__ = ["EnvironmentDocumentProvider", "specs"]
