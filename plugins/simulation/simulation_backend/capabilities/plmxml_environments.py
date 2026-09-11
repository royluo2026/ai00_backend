"""Governed PLMXML import/export boundary for complete Simulation environments."""
from __future__ import annotations

import hashlib
import io
import json
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilityOutput, CapabilitySpec, EvidenceRef
from backend.platform_sdk.artifacts import create_artifact, read_artifact
from backend.capability_v2.artifacts import ArtifactError

from ..data.workspace_repository import WorkspaceRepository, WorkspaceRepositoryError
from ..domain.plmxml_environment_codec import (
    EnvironmentImportProjection,
    EnvironmentDocumentDependencyError,
    export_environment_plmxml,
    import_environment_plmxml,
    runtime_model_from_dict,
)
from ..domain.plmxml_projection import PlmxmlError, PlmxmlLimits
from ..application.environment_materialization import EnvironmentMaterializationError, build_runtime_package


class _Artifacts:
    @staticmethod
    def read(reference, context): return read_artifact(reference, context, maximum=64*1024*1024)
    @staticmethod
    def create(content, media_type, context): return create_artifact(content, media_type, context, maximum=64*1024*1024)


def _scope(context: CapabilityContext) -> tuple[str, str]:
    tenant_gid, actor_gid = str(context.team_gid or ""), str(context.user_gid or "")
    if not tenant_gid or not actor_gid: raise CapabilityBusinessError("workspace_identity_required", "workspace_identity_required")
    return tenant_gid, actor_gid


def _output(data: Any, action: str, workspace_gid: str) -> CapabilityOutput:
    encoded=json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str).encode()
    return CapabilityOutput(data=data,evidence=(EvidenceRef(kind="simulation.plmxml.environment",reference=f"simulation://workspace/{workspace_gid}/plmxml",digest="sha256:"+hashlib.sha256(encoded).hexdigest(),summary=action),))


class PlmxmlEnvironmentProvider:
    def __init__(self, repository: WorkspaceRepository | None = None, artifacts=None) -> None:
        self.repository=repository or WorkspaceRepository(); self.artifacts=artifacts or _Artifacts()

    def _read_projection(self, ref: dict[str, Any], context: CapabilityContext):
        if ref.get("media_type") not in {"application/plmxml+xml", "application/vnd.siemens.plmxml+xml"}:
            raise CapabilityBusinessError("plmxml_artifact_media_type_invalid", "plmxml_artifact_media_type_invalid")
        try:
            content = self.artifacts.read(ref, context)
        except (ArtifactError, ValueError) as exc:
            raise CapabilityBusinessError("plmxml_artifact_unavailable", "plmxml_artifact_unavailable") from exc
        actual = hashlib.sha256(content).hexdigest()
        if actual != str(ref.get("sha256") or "").removeprefix("sha256:"):
            raise CapabilityBusinessError("plmxml_artifact_hash_mismatch", "plmxml_artifact_hash_mismatch")
        try:
            projection = import_environment_plmxml(
                io.BytesIO(content), limits=PlmxmlLimits(), algorithm_version="environment-codec.v1",
            )
        except PlmxmlError as exc:
            raise CapabilityBusinessError(str(exc), str(exc)) from exc
        return actual, projection

    def _resolve_dependencies(self, payload: dict[str, Any], projection: EnvironmentImportProjection,
                              context: CapabilityContext) -> dict[str, dict[str, Any]]:
        supplied: dict[str, dict[str, Any]] = {}
        for item in payload.get("dependency_artifacts") or []:
            location = str(item.get("location") or "")
            if not location or location in supplied:
                raise CapabilityBusinessError("plmxml_dependency_artifact_invalid", "plmxml_dependency_artifact_invalid")
            supplied[location] = dict(item.get("artifact_ref") or {})
        required = {item.location: item for item in projection.dependencies}
        if set(supplied) != set(required):
            raise CapabilityBusinessError("plmxml_dependency_artifact_required", "plmxml_dependency_artifact_required")
        resolved: dict[str, dict[str, Any]] = {}
        for location, dependency in required.items():
            ref = supplied[location]
            supplied_media = str(ref.get("media_type") or "")
            media_matches = supplied_media == dependency.media_type or {
                supplied_media, dependency.media_type,
            } == {"model/jt", "model/vnd.jt"}
            if not media_matches:
                raise CapabilityBusinessError("plmxml_dependency_media_type_mismatch", "plmxml_dependency_media_type_mismatch")
            try:
                content = self.artifacts.read(ref, context)
            except (ArtifactError, ValueError) as exc:
                raise CapabilityBusinessError("plmxml_dependency_artifact_unavailable", "plmxml_dependency_artifact_unavailable") from exc
            actual = hashlib.sha256(content).hexdigest()
            if actual != str(ref.get("sha256") or "").removeprefix("sha256:"):
                raise CapabilityBusinessError("plmxml_dependency_artifact_hash_mismatch", "plmxml_dependency_artifact_hash_mismatch")
            resolved[location] = ref
        return resolved

    def inspect_environment(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        _scope(context)
        ref = dict(payload.get("artifact_ref") or {})
        actual, projection = self._read_projection(ref, context)
        hierarchies = [{
            "projection_identity": item.projection_identity,
            "name": item.name,
            "placement_count": len(item.placements),
        } for item in projection.hierarchies]
        dependencies = [{"location": item.location, "media_type": item.media_type}
                        for item in projection.dependencies]
        inspection_payload = {
            "artifact_sha256": "sha256:" + actual,
            "semantic_hash": projection.original_sha256,
            "algorithm_version": projection.algorithm_version,
            "hierarchies": hierarchies,
            "dependencies": dependencies,
        }
        inspection_hash = "sha256:" + hashlib.sha256(json.dumps(
            inspection_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        report = {
            "semantic_hash": projection.original_sha256,
            "document_count": 1 + len(projection.dependencies),
            "hierarchy_count": len(projection.hierarchies),
            "placement_count": sum(len(item.placements) for item in projection.hierarchies),
            "dependency_count": len(projection.dependencies),
            "algorithm_version": projection.algorithm_version,
        }
        return _output({**inspection_payload, "inspection_hash": inspection_hash, "report": report},
                       "plmxml_environment_inspected", str(ref.get("artifact_id") or "artifact"))

    def _checked_projection(self, payload: dict[str, Any], context: CapabilityContext):
        ref = dict(payload.get("artifact_ref") or {})
        actual, projection = self._read_projection(ref, context)
        inspected = self.inspect_environment({"artifact_ref": ref}, context).data
        if str(payload.get("inspection_hash") or "") != inspected["inspection_hash"]:
            raise CapabilityBusinessError("plmxml_inspection_changed", "plmxml_inspection_changed")
        resolved = self._resolve_dependencies(payload, projection, context)
        return ref, actual, projection, inspected, resolved

    def restore_environment(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        tenant_gid, actor_gid = _scope(context)
        ref, _, projection, inspected, resolved = self._checked_projection(payload, context)
        try:
            stored = self.repository.restore_environment_projection(
                name=str(payload.get("name") or ""), display_name=str(payload.get("display_name") or ""),
                artifact_ref=ref, projection=projection, tenant_gid=tenant_gid, actor_gid=actor_gid,
                resolved_dependencies=resolved,
                idempotency_key=str(payload.get("idempotency_key") or ""),
            )
        except WorkspaceRepositoryError as exc:
            raise CapabilityBusinessError(str(exc), str(exc)) from exc
        return _output({**stored, "inspection_hash": inspected["inspection_hash"],
                        "report": inspected["report"]}, "plmxml_environment_restored",
                       str(stored["workspace_gid"]))

    def insert_environment(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        tenant_gid, actor_gid = _scope(context)
        workspace_gid = str(payload.get("workspace_gid") or "")
        ref, _, projection, inspected, resolved = self._checked_projection(payload, context)
        mode = str(payload.get("mode") or "")
        selected = [str(value) for value in payload.get("selected_hierarchy_identities") or []]
        if mode not in {"model_and_selected_hierarchies", "model_only"}:
            raise CapabilityBusinessError("plmxml_insert_mode_required", "plmxml_insert_mode_required")
        available = {item.projection_identity for item in projection.hierarchies}
        if mode == "model_and_selected_hierarchies" and (not selected or any(item not in available for item in selected)):
            raise CapabilityBusinessError("plmxml_hierarchy_selection_invalid", "plmxml_hierarchy_selection_invalid")
        if mode == "model_only" and selected:
            raise CapabilityBusinessError("plmxml_hierarchy_selection_invalid", "plmxml_hierarchy_selection_invalid")
        chosen = tuple(item for item in projection.hierarchies if item.projection_identity in set(selected))
        filtered = EnvironmentImportProjection(
            hierarchies=chosen, dependencies=projection.dependencies,
            original_sha256=projection.original_sha256, algorithm_version=projection.algorithm_version,
        )
        try:
            stored = self.repository.import_environment_projection(
                workspace_gid=workspace_gid, expected_workspace_version=payload.get("expected_row_version"),
                display_name=str(payload.get("display_name") or ""), document_role="inserted",
                artifact_ref=ref, projection=filtered, tenant_gid=tenant_gid, actor_gid=actor_gid,
                resolved_dependencies=resolved,
                idempotency_key=str(payload.get("idempotency_key") or ""),
            )
        except WorkspaceRepositoryError as exc:
            raise CapabilityBusinessError(str(exc), str(exc), retryable=str(exc) == "version_conflict") from exc
        return _output({**stored, "mode": mode, "selected_hierarchy_identities": selected,
                        "inspection_hash": inspected["inspection_hash"], "report": inspected["report"]},
                       "plmxml_environment_inserted", workspace_gid)

    def import_environment(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        tenant_gid,actor_gid=_scope(context); workspace_gid=str(payload.get("workspace_gid") or ""); ref=dict(payload.get("artifact_ref") or {})
        _, projection = self._read_projection(ref, context)
        resolved = self._resolve_dependencies(payload, projection, context)
        try:
            stored=self.repository.import_environment_projection(workspace_gid=workspace_gid,expected_workspace_version=payload.get("expected_row_version"),display_name=str(payload.get("display_name") or ""),document_role=str(payload.get("role") or "primary"),artifact_ref=ref,projection=projection,resolved_dependencies=resolved,tenant_gid=tenant_gid,actor_gid=actor_gid,idempotency_key=str(payload.get("idempotency_key") or ""))
        except (PlmxmlError,WorkspaceRepositoryError) as exc: raise CapabilityBusinessError(str(exc),str(exc),retryable=str(exc)=="version_conflict") from exc
        report={"semantic_hash":projection.original_sha256,"document_count":1+len(projection.dependencies),"hierarchy_count":len(projection.hierarchies),"placement_count":sum(len(item.placements) for item in projection.hierarchies),"dependency_count":len(projection.dependencies),"algorithm_version":projection.algorithm_version}
        return _output({**stored,"report":report},"plmxml_environment_imported",workspace_gid)

    def export_environment(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        tenant_gid,actor_gid=_scope(context); workspace_gid=str(payload.get("workspace_gid") or "")
        try: model=self.repository.load_environment_runtime_model(workspace_gid=workspace_gid,tenant_gid=tenant_gid,actor_gid=actor_gid)
        except WorkspaceRepositoryError as exc: raise CapabilityBusinessError(str(exc),str(exc)) from exc
        result=export_environment_plmxml(model)
        try: ref=self.artifacts.create(result.content,"application/plmxml+xml",context)
        except (ArtifactError,ValueError) as exc: raise CapabilityBusinessError("plmxml_artifact_unavailable","plmxml_artifact_unavailable") from exc
        return _output({"workspace_gid":workspace_gid,"artifact_ref":ref,"semantic_hash":result.semantic_hash,"report":dict(result.report)},"plmxml_environment_exported",workspace_gid)

    def prepare_runtime_package(self, payload: dict[str, Any], context: CapabilityContext,
                                *, connector_device_id: str | None = None) -> CapabilityOutput:
        tenant_gid,actor_gid=_scope(context);workspace_gid=str(payload.get("workspace_gid") or "");version_gid=str(payload.get("version_gid") or "")
        try:
            saved = self.repository.get_saved_version(
                workspace_gid=workspace_gid, version_gid=version_gid,
                tenant_gid=tenant_gid, owner_gid=actor_gid,
            )
            if str(saved.get("status") or "") != "frozen":
                raise WorkspaceRepositoryError("workspace_version_not_frozen")
            manifest_ref = saved.get("manifest_artifact_ref")
            if not isinstance(manifest_ref, dict):
                raise WorkspaceRepositoryError("frozen_manifest_missing")
            manifest_content = self.artifacts.read(manifest_ref, context)
            actual_hash = hashlib.sha256(manifest_content).hexdigest()
            expected_hash = str(saved.get("content_hash") or "").removeprefix("sha256:")
            reference_hash = str(manifest_ref.get("sha256") or "").removeprefix("sha256:")
            if not expected_hash or actual_hash != expected_hash or actual_hash != reference_hash:
                raise WorkspaceRepositoryError("frozen_manifest_hash_mismatch")
            manifest = json.loads(manifest_content.decode("utf-8"))
            runtime_raw = manifest.get("runtime_model") if isinstance(manifest, dict) else None
            if not isinstance(runtime_raw, dict):
                raise WorkspaceRepositoryError("frozen_runtime_model_missing")
            runtime_model = runtime_model_from_dict(runtime_raw)
            if runtime_model.environment_gid != workspace_gid:
                raise WorkspaceRepositoryError("frozen_runtime_model_mismatch")
            source={"runtime_model":runtime_model,"version_gid":version_gid,
                    "connector_device_id":str(connector_device_id or "") or None}
            package=build_runtime_package(source)
            top_ref=self.artifacts.create(package.top_level_content,"application/plmxml+xml",context)
        except (WorkspaceRepositoryError,EnvironmentDocumentDependencyError,EnvironmentMaterializationError,
                ArtifactError,UnicodeDecodeError,json.JSONDecodeError,ValueError) as exc:
            raise CapabilityBusinessError(str(exc),str(exc)) from exc
        dependencies=[{"document_gid":item.document_gid,"package_path":item.package_path,"artifact_ref":dict(item.artifact_ref),"content_sha256":item.content_sha256} for item in package.dependencies]
        open_payload={"artifact_ref":top_ref,"package_dependencies":[{"package_path":item["package_path"],"artifact_ref":item["artifact_ref"]} for item in dependencies]}
        data={"workspace_gid":workspace_gid,"version_gid":version_gid,"top_level_artifact_ref":top_ref,"dependencies":dependencies,"open_payload":open_payload,"manifest":dict(package.manifest),"manifest_hash":package.manifest_hash}
        return _output(data,"runtime_package_prepared",workspace_gid)


def specs(provider: PlmxmlEnvironmentProvider | None = None):
    selected=provider or PlmxmlEnvironmentProvider();gid={"type":"string","pattern":"^[1-9][0-9]*$"};key={"type":"string","minLength":1,"maxLength":191};semantic_hash={"type":"string","pattern":"^sha256:[0-9a-f]{64}$"};artifact={"type":"object","required":["artifact_id","media_type","sha256","byte_size","version"],"properties":{"artifact_id":{"type":"string"},"media_type":{"type":"string","enum":["application/plmxml+xml","application/vnd.siemens.plmxml+xml"]},"sha256":{"type":"string","pattern":"^(sha256:)?[0-9a-f]{64}$"},"byte_size":{"type":"integer","minimum":0},"version":{"type":"integer","minimum":1}},"additionalProperties":False};report={"type":"object","required":["semantic_hash","document_count","hierarchy_count","placement_count"],"properties":{"semantic_hash":semantic_hash,"document_count":{"type":"integer","minimum":0},"hierarchy_count":{"type":"integer","minimum":0},"placement_count":{"type":"integer","minimum":0},"dependency_count":{"type":"integer","minimum":0},"algorithm_version":{"type":"string"},"unresolved_refs":{"type":"array"},"omitted_ai00_only_records":{"type":"array"},"original_artifact_passthrough_eligible":{"type":"boolean"}},"additionalProperties":False};common=dict(owner="simulation",permissions=("simulation.use",),plugin_callable=True,tags=("simulation","plmxml_environment","experimental"))
    import_output={"type":"object","required":["workspace_gid","document_gid","hierarchy_gids","workspace_row_version","cache_revision_hash","report"],"properties":{"workspace_gid":gid,"document_gid":gid,"hierarchy_gids":{"type":"array","items":gid},"workspace_row_version":{"type":"integer","minimum":2},"cache_revision_hash":semantic_hash,"report":report},"additionalProperties":False}
    export_output={"type":"object","required":["workspace_gid","artifact_ref","semantic_hash","report"],"properties":{"workspace_gid":gid,"artifact_ref":artifact,"semantic_hash":semantic_hash,"report":report},"additionalProperties":False}
    runtime_artifact={**artifact,"properties":{**artifact["properties"],"media_type":{"type":"string","enum":["application/plmxml+xml","application/vnd.siemens.plmxml+xml","model/vnd.jt","model/jt"]}}}
    dependency_artifact={"type":"object","required":["location","artifact_ref"],"properties":{"location":{"type":"string","minLength":1,"maxLength":2048},"artifact_ref":runtime_artifact},"additionalProperties":False}
    dependency_artifacts={"type":"array","maxItems":10000,"items":dependency_artifact}
    dependency={"type":"object","required":["document_gid","package_path","artifact_ref","content_sha256"],"properties":{"document_gid":gid,"package_path":{"type":"string"},"artifact_ref":runtime_artifact,"content_sha256":semantic_hash},"additionalProperties":False}
    runtime_output={"type":"object","required":["workspace_gid","version_gid","top_level_artifact_ref","dependencies","open_payload","manifest","manifest_hash"],"properties":{"workspace_gid":gid,"version_gid":gid,"top_level_artifact_ref":artifact,"dependencies":{"type":"array","items":dependency},"open_payload":{"type":"object"},"manifest":{"type":"object"},"manifest_hash":semantic_hash},"additionalProperties":False}
    inspect_output={"type":"object","required":["artifact_sha256","semantic_hash","algorithm_version","inspection_hash","hierarchies","dependencies","report"],"properties":{"artifact_sha256":semantic_hash,"semantic_hash":semantic_hash,"algorithm_version":{"type":"string"},"inspection_hash":semantic_hash,"hierarchies":{"type":"array","items":{"type":"object","required":["projection_identity","name","placement_count"],"properties":{"projection_identity":{"type":"string"},"name":{"type":"string"},"placement_count":{"type":"integer","minimum":0}},"additionalProperties":False}},"dependencies":{"type":"array","items":{"type":"object","required":["location","media_type"],"properties":{"location":{"type":"string"},"media_type":{"type":"string","enum":["application/plmxml+xml","model/vnd.jt"]}},"additionalProperties":False}},"report":report},"additionalProperties":False}
    restore_output={"type":"object","required":["workspace_gid","version_gid","document_gid","hierarchy_gids","workspace_row_version","cache_revision_hash","inspection_hash","report"],"properties":{"workspace_gid":gid,"version_gid":gid,"document_gid":gid,"hierarchy_gids":{"type":"array","items":gid},"workspace_row_version":{"type":"integer","minimum":2},"cache_revision_hash":semantic_hash,"inspection_hash":semantic_hash,"report":report},"additionalProperties":False}
    insert_output={"type":"object","required":["workspace_gid","document_gid","hierarchy_gids","workspace_row_version","cache_revision_hash","mode","selected_hierarchy_identities","inspection_hash","report"],"properties":{"workspace_gid":gid,"document_gid":gid,"hierarchy_gids":{"type":"array","items":gid},"workspace_row_version":{"type":"integer","minimum":2},"cache_revision_hash":semantic_hash,"mode":{"type":"string","enum":["model_and_selected_hierarchies","model_only"]},"selected_hierarchy_identities":{"type":"array","items":{"type":"string"}},"inspection_hash":semantic_hash,"report":report},"additionalProperties":False}
    return (
        (CapabilitySpec(id="simulation.plmxml.environment.inspect",version=1,description="Inspect one immutable PLMXML Artifact and return selectable model and alternate-hierarchy projections without mutating an environment.",risk="read",confirmation="none",idempotent=True,input_schema={"type":"object","required":["artifact_ref"],"properties":{"artifact_ref":artifact},"additionalProperties":False},output_schema=inspect_output,**common),selected.inspect_environment),
        (CapabilitySpec(id="simulation.environment.restore_from_plmxml",version=1,description="Create one private draft Simulation environment from one inspected immutable PLMXML Artifact.",risk="write",confirmation="user",idempotent=True,input_schema={"type":"object","required":["artifact_ref","name","display_name","inspection_hash","idempotency_key"],"properties":{"artifact_ref":artifact,"dependency_artifacts":dependency_artifacts,"name":{"type":"string","minLength":1,"maxLength":255},"display_name":{"type":"string","minLength":1,"maxLength":255},"inspection_hash":semantic_hash,"idempotency_key":key},"additionalProperties":False},output_schema=restore_output,**common),selected.restore_environment),
        (CapabilitySpec(id="simulation.environment.plmxml.insert",version=1,description="Insert one inspected PLMXML model document and an explicit set of alternate hierarchies into one owned draft environment.",risk="write",confirmation="none",idempotent=True,input_schema={"type":"object","required":["workspace_gid","expected_row_version","artifact_ref","display_name","mode","selected_hierarchy_identities","inspection_hash","idempotency_key"],"properties":{"workspace_gid":gid,"expected_row_version":{"type":"integer","minimum":1},"artifact_ref":artifact,"dependency_artifacts":dependency_artifacts,"display_name":{"type":"string","minLength":1,"maxLength":255},"mode":{"type":"string","enum":["model_and_selected_hierarchies","model_only"]},"selected_hierarchy_identities":{"type":"array","maxItems":10000,"items":{"type":"string"}},"inspection_hash":semantic_hash,"idempotency_key":key},"additionalProperties":False},output_schema=insert_output,**common),selected.insert_environment),
        (CapabilitySpec(id="simulation.plmxml.environment.import",version=1,description="Import one immutable primary or supplemental PLMXML Artifact into an owned draft environment.",risk="write",confirmation="none",idempotent=True,input_schema={"type":"object","required":["workspace_gid","expected_row_version","artifact_ref","display_name","idempotency_key"],"properties":{"workspace_gid":gid,"expected_row_version":{"type":"integer","minimum":1},"artifact_ref":artifact,"dependency_artifacts":dependency_artifacts,"display_name":{"type":"string","minLength":1,"maxLength":255},"role":{"type":"string","enum":["primary","inserted"]},"idempotency_key":key},"additionalProperties":False},output_schema=import_output,**common),selected.import_environment),
        (CapabilitySpec(id="simulation.plmxml.environment.export",version=1,description="Export one readable environment as an immutable deterministic PLMXML Artifact.",risk="write",confirmation="none",idempotent=True,input_schema={"type":"object","required":["workspace_gid","idempotency_key"],"properties":{"workspace_gid":gid,"idempotency_key":key},"additionalProperties":False},output_schema=export_output,**common),selected.export_environment),
        (CapabilitySpec(id="simulation.environment.runtime_package.prepare",version=1,description="Prepare one deterministic frozen VisMockup package whose generated top-level PLMXML is the only document opened.",risk="write",confirmation="none",idempotent=True,input_schema={"type":"object","required":["workspace_gid","version_gid","idempotency_key"],"properties":{"workspace_gid":gid,"version_gid":gid,"idempotency_key":key},"additionalProperties":False},output_schema=runtime_output,**common),selected.prepare_runtime_package),
    )


__all__=["PlmxmlEnvironmentProvider","specs"]
