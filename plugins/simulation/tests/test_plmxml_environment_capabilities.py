from __future__ import annotations

import hashlib
import json

from backend.capability_v2.provider_contracts import CapabilityContext
from plugins.simulation.simulation_backend.capabilities.plmxml_environments import PlmxmlEnvironmentProvider, specs


XML = b'<PLMXML><ProductView id="a" name="ALT" usage="variant"/></PLMXML>'


class _Artifacts:
    def __init__(self): self.created = []
    def read(self, reference, context): return XML
    def create(self, content, media_type, context):
        assert content.startswith(b"<?xml") and media_type == "application/plmxml+xml"
        self.created.append(content)
        return {"artifact_id": "out", "media_type": media_type, "sha256": hashlib.sha256(content).hexdigest(), "byte_size": len(content), "version": 1}


class _Repo:
    def import_environment_projection(self, **kwargs): return {"workspace_gid": kwargs["workspace_gid"], "document_gid": "9", "hierarchy_gids": ["10"], "workspace_row_version": 2, "cache_revision_hash": "sha256:" + "0" * 64}
    def load_environment_runtime_model(self, **kwargs):
        from plugins.simulation.simulation_backend.domain.plmxml_environment_codec import EnvironmentRuntimeModel
        return EnvironmentRuntimeModel(environment_gid=kwargs["workspace_gid"], documents=(), hierarchies=())


def _frozen_runtime(model):
    from plugins.simulation.simulation_backend.domain.plmxml_environment_codec import runtime_model_to_dict
    content = json.dumps({"runtime_model": runtime_model_to_dict(model)}, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(content).hexdigest()
    reference = {"artifact_id": "manifest", "media_type": "application/vnd.ai00.simulation-environment+json",
                 "sha256": digest, "byte_size": len(content), "version": 1}

    class Repo(_Repo):
        def get_saved_version(self, **kwargs):
            return {"workspace_gid": kwargs["workspace_gid"], "version_gid": kwargs["version_gid"],
                    "status": "frozen", "content_hash": "sha256:" + digest,
                    "manifest_artifact_ref": reference}

    class Artifacts(_Artifacts):
        def read(self, artifact_ref, context):
            return content if artifact_ref["artifact_id"] == "manifest" else XML

    return Repo(), Artifacts()


def test_frozen_runtime_package_prepares_one_top_level_open_with_staged_dependencies():
    from plugins.simulation.simulation_backend.domain.plmxml_environment_codec import EnvironmentModelDocument, EnvironmentRuntimeModel
    digest = "a" * 64
    document = EnvironmentModelDocument(document_gid="9", role="primary", display_name="base.plmxml",
        media_type="application/plmxml+xml", artifact_ref={"artifact_id":"source","media_type":"application/plmxml+xml","sha256":digest,"byte_size":5,"version":1},
        source_identity_hash="sha256:"+digest, content_sha256="sha256:"+digest, portability="portable")
    jt = EnvironmentModelDocument(document_gid="10", role="inserted", display_name="part.jt",
        media_type="model/vnd.jt", artifact_ref={"artifact_id":"jt-source","media_type":"model/vnd.jt","sha256":digest,"byte_size":5,"version":1},
        source_identity_hash="sha256:"+digest, content_sha256="sha256:"+digest, portability="portable")
    repo, artifacts = _frozen_runtime(EnvironmentRuntimeModel(environment_gid="10",documents=(document,jt),hierarchies=()))
    provider = PlmxmlEnvironmentProvider(repo, artifacts)
    output = provider.prepare_runtime_package({"workspace_gid":"10","version_gid":"20","idempotency_key":"runtime-20"}, CapabilityContext(user_gid="30",team_gid="20")).data
    assert output["open_payload"]["artifact_ref"]["artifact_id"] == "out"
    assert output["open_payload"]["package_dependencies"][0]["artifact_ref"]["artifact_id"] == "source"
    assert output["open_payload"]["package_dependencies"][1]["artifact_ref"]["media_type"] == "model/vnd.jt"
    assert output["manifest"]["open_only_top_level"] is True
    from backend.capabilities.validation_next import validate_payload
    validate_payload(dict(specs(provider)[2][0].output_schema), output, label="output")


def test_bound_runtime_supplies_device_identity_for_device_bound_documents():
    from plugins.simulation.simulation_backend.domain.plmxml_environment_codec import EnvironmentModelDocument, EnvironmentRuntimeModel
    digest = "b" * 64
    document = EnvironmentModelDocument(document_gid="9", role="primary", display_name="local.plmxml",
        media_type="application/plmxml+xml", artifact_ref={"artifact_id":"source","media_type":"application/plmxml+xml","sha256":digest,"byte_size":5,"version":1},
        source_identity_hash="sha256:"+digest, content_sha256="sha256:"+digest,
        portability="device_bound", connector_device_id="device-1")
    repo, artifacts = _frozen_runtime(EnvironmentRuntimeModel(environment_gid="10",documents=(document,),hierarchies=()))
    output = PlmxmlEnvironmentProvider(repo, artifacts).prepare_runtime_package(
        {"workspace_gid":"10","version_gid":"20","idempotency_key":"runtime-20"},
        CapabilityContext(user_gid="30",team_gid="20"), connector_device_id="device-1",
    ).data
    assert output["manifest"]["connector_device_id"] == "device-1"


def test_runtime_package_fails_closed_when_frozen_manifest_has_no_runtime_model():
    content = b'{"schema":"ai00.simulation.environment-manifest.v1"}'
    digest = hashlib.sha256(content).hexdigest()
    class Repo(_Repo):
        def get_saved_version(self, **kwargs):
            return {"status": "frozen", "content_hash": "sha256:" + digest,
                    "manifest_artifact_ref": {"artifact_id": "manifest", "sha256": digest}}
    class Artifacts(_Artifacts):
        def read(self, reference, context): return content
    import pytest
    with pytest.raises(Exception, match="frozen_runtime_model_missing"):
        PlmxmlEnvironmentProvider(Repo(), Artifacts()).prepare_runtime_package(
            {"workspace_gid":"10","version_gid":"20","idempotency_key":"runtime-20"},
            CapabilityContext(user_gid="30",team_gid="20"),
        )


def test_plmxml_import_and_export_are_separate_artifact_capabilities():
    provider = PlmxmlEnvironmentProvider(_Repo(), _Artifacts())
    ctx = CapabilityContext(user_gid="30", team_gid="20", request_id="r1")
    digest = hashlib.sha256(XML).hexdigest()
    imported = provider.import_environment({"workspace_gid": "10", "expected_row_version": 1,
        "artifact_ref": {"artifact_id": "in", "media_type": "application/plmxml+xml", "sha256": digest, "byte_size": len(XML), "version": 1},
        "display_name": "source", "idempotency_key": "import-1"}, ctx)
    exported = provider.export_environment({"workspace_gid": "10", "idempotency_key": "export-1"}, ctx)
    assert imported.data["report"]["hierarchy_count"] == 1
    assert exported.data["artifact_ref"]["artifact_id"] == "out"
    assert [item[0].id for item in specs(provider)] == ["simulation.plmxml.environment.import", "simulation.plmxml.environment.export", "simulation.environment.runtime_package.prepare"]
    from backend.capabilities.validation_next import validate_payload
    for spec, output in zip((item[0] for item in specs(provider)), (imported.data, exported.data)):
        validate_payload(dict(spec.output_schema), output, label="output")
