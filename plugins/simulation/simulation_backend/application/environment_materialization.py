"""Deterministic runtime-package construction for VisMockup environments."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import PurePosixPath
import re
from typing import Any, Mapping

from ..domain.plmxml_environment_codec import EnvironmentDependency, EnvironmentModelDocument, EnvironmentRuntimeModel, export_environment_plmxml


class EnvironmentMaterializationError(ValueError): pass


@dataclass(frozen=True)
class StagedDependency:
    document_gid: str
    package_path: str
    media_type: str
    artifact_ref: Mapping[str, object]
    content_sha256: str


@dataclass(frozen=True)
class RuntimePackage:
    top_level_content: bytes
    top_level_sha256: str
    dependencies: tuple[StagedDependency, ...]
    manifest: Mapping[str, object]
    manifest_hash: str


def _extension(document: EnvironmentModelDocument) -> str:
    suffix = PurePosixPath(document.display_name.replace("\\", "/")).suffix.casefold()
    if document.media_type == "model/vnd.jt": return ".jt"
    return ".plmxml" if suffix not in {".plmxml", ".xml"} else suffix


def build_runtime_package(workspace_version: Mapping[str, Any]) -> RuntimePackage:
    model = workspace_version.get("runtime_model")
    if not isinstance(model, EnvironmentRuntimeModel): raise EnvironmentMaterializationError("runtime_model_required")
    documents = tuple(item for item in model.documents if isinstance(item, EnvironmentModelDocument))
    if len(documents) != len(model.documents): raise EnvironmentMaterializationError("model_document_metadata_required")
    if sum(item.role == "primary" for item in documents) != 1: raise EnvironmentMaterializationError("primary_model_document_required")
    connector_device_id = str(workspace_version.get("connector_device_id") or "")
    if any(item.portability == "device_bound" for item in documents) and not connector_device_id:
        raise EnvironmentMaterializationError("device_bound_document_requires_connector")
    if any(item.portability == "device_bound" and item.connector_device_id != connector_device_id for item in documents):
        raise EnvironmentMaterializationError("device_bound_document_connector_mismatch")
    dependencies = []
    export_dependencies = []
    for index, document in enumerate(sorted(documents, key=lambda item: (item.role != "primary", item.document_gid)), start=1):
        if not document.artifact_ref: raise EnvironmentMaterializationError("model_document_artifact_required")
        digest = str(document.content_sha256).removeprefix("sha256:")
        if str(document.artifact_ref.get("sha256") or "").removeprefix("sha256:") != digest:
            raise EnvironmentMaterializationError("model_document_artifact_hash_mismatch")
        safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", PurePosixPath(document.display_name.replace("\\", "/")).stem).strip("._") or "model"
        package_path = f"dependencies/{index:04d}-{safe_stem}{_extension(document)}"
        dependencies.append(StagedDependency(document_gid=document.document_gid, package_path=package_path,
            media_type=document.media_type, artifact_ref=dict(document.artifact_ref), content_sha256="sha256:" + digest))
        export_dependencies.append(EnvironmentDependency(location=package_path, media_type=document.media_type))
    exported = export_environment_plmxml(EnvironmentRuntimeModel(environment_gid=model.environment_gid,
        documents=tuple(export_dependencies), hierarchies=model.hierarchies))
    top_hash = "sha256:" + hashlib.sha256(exported.content).hexdigest()
    manifest = {"schema":"ai00.simulation.runtime-package.v1","workspace_gid":model.environment_gid,
        "version_gid":str(workspace_version.get("version_gid") or ""),"top_level_count":1,"open_only_top_level":True,
        "top_level_sha256":top_hash,"semantic_hash":exported.semantic_hash,"connector_device_id":connector_device_id or None,
        "documents":[{"document_gid":item.document_gid,"package_path":item.package_path,"media_type":item.media_type,"content_sha256":item.content_sha256} for item in dependencies]}
    manifest_hash = "sha256:" + hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return RuntimePackage(top_level_content=exported.content, top_level_sha256=top_hash,
        dependencies=tuple(dependencies), manifest=manifest, manifest_hash=manifest_hash)


__all__=["EnvironmentMaterializationError","RuntimePackage","StagedDependency","build_runtime_package"]
