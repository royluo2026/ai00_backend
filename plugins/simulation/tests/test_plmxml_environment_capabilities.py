from __future__ import annotations

import hashlib
import json

from backend.capability_v2.provider_contracts import CapabilityContext
from plugins.simulation.simulation_backend.capabilities.plmxml_environments import PlmxmlEnvironmentProvider, specs
from plugins.simulation.simulation_backend.capabilities.provider import descriptor_for


XML = b'<PLMXML><ProductView id="a" name="ALT" usage="variant"/></PLMXML>'
XML_TWO = b'<PLMXML><ProductView id="a" name="ALT A" usage="variant"/><ProductView id="b" name="ALT B" usage="variant"/></PLMXML>'
XML_DEP = b'<PLMXML><Representation location="parts/a.jt"/></PLMXML>'
XML_MODEL = b'''<PLMXML><ProductDef><InstanceGraph id="graph" rootRefs="root">
<ProductInstance id="root" name="ROOT/00;1-Root" partRef="#view-root"/>
<ProductInstance id="child" name="PART/01;1-Child" partRef="#view-child"/>
<ProductRevisionView id="view-root" instanceRefs="child"/><ProductRevisionView id="view-child"/>
</InstanceGraph></ProductDef></PLMXML>'''
XML_MODEL_WITH_EXTERNAL_PRODUCT = b'''<PLMXML>
<ProductInstance id="external-root" name="External product" partRef="base.plmxml#base-view"/>
</PLMXML>'''


class _Artifacts:
    def __init__(self): self.created = []
    def read(self, reference, context): return XML
    def create(self, content, media_type, context):
        assert content.startswith(b"<?xml") and media_type == "application/plmxml+xml"
        self.created.append(content)
        return {"artifact_id": "out", "media_type": media_type, "sha256": hashlib.sha256(content).hexdigest(), "byte_size": len(content), "version": 1}


class _Repo:
    def __init__(self): self.import_calls = []
    def import_environment_projection(self, **kwargs):
        self.import_calls.append(kwargs)
        return {"workspace_gid": kwargs["workspace_gid"], "document_gid": "9", "hierarchy_gids": ["10"], "workspace_row_version": 2, "cache_revision_hash": "sha256:" + "0" * 64}
    def restore_environment_projection(self, **kwargs):
        self.restore_call = kwargs
        return {"workspace_gid": "11", "version_gid": "12", "document_gid": "13", "hierarchy_gids": ["14"], "workspace_row_version": 2, "cache_revision_hash": "sha256:" + "0" * 64}
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
    validate_payload(dict(specs(provider)[5][0].output_schema), output, label="output")


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
    assert [item[0].id for item in specs(provider)] == [
        "simulation.plmxml.environment.inspect", "simulation.environment.restore_from_plmxml",
        "simulation.environment.plmxml.insert", "simulation.plmxml.environment.import",
        "simulation.plmxml.environment.export", "simulation.environment.runtime_package.prepare",
        "simulation.plmxml.model_tree.read",
    ]
    from backend.capabilities.validation_next import validate_payload
    for spec, output in zip((specs(provider)[3][0], specs(provider)[4][0]), (imported.data, exported.data)):
        validate_payload(dict(spec.output_schema), output, label="output")


def test_plmxml_inspect_is_read_only_and_returns_explicit_hierarchy_choices():
    repo = _Repo()
    provider = PlmxmlEnvironmentProvider(repo, _Artifacts())
    digest = hashlib.sha256(XML).hexdigest()
    output = provider.inspect_environment({"artifact_ref": {
        "artifact_id": "in", "media_type": "application/plmxml+xml", "sha256": digest,
        "byte_size": len(XML), "version": 1,
    }}, CapabilityContext(user_gid="30", team_gid="20", request_id="inspect-1")).data
    assert output["inspection_hash"].startswith("sha256:")
    assert output["artifact_sha256"] == "sha256:" + digest
    assert output["hierarchies"] == [{"projection_identity": "a", "name": "ALT", "placement_count": 0}]
    assert output["dependencies"] == []
    assert not hasattr(repo, "last_import")
    from backend.capabilities.validation_next import validate_payload
    validate_payload(dict(specs(provider)[0][0].output_schema), output, label="output")


def test_plmxml_model_tree_read_projects_product_nodes_without_mutation():
    class Artifacts(_Artifacts):
        def read(self, reference, context): return XML_MODEL
    provider = PlmxmlEnvironmentProvider(_Repo(), Artifacts())
    digest = hashlib.sha256(XML_MODEL).hexdigest()
    ref = {"artifact_id":"model","media_type":"application/plmxml+xml",
           "sha256":digest,"byte_size":len(XML_MODEL),"version":1}
    output = provider.read_model_tree(
        {"artifact_ref":ref}, CapabilityContext(user_gid="30", team_gid="20", request_id="tree-1"),
    ).data
    assert output["state"] == "ready"
    assert output["node_count"] == 2
    assert output["nodes"] == [
        {"node_key":"root","parent_key":None,"child_order":0,"name":"ROOT/00;1-Root",
         "bom_line":"ROOT/00;1","item_id":"","revision":"","occurrence_id":"","has_more":True},
        {"node_key":"child","parent_key":"root","child_order":0,"name":"PART/01;1-Child",
         "bom_line":"PART/01;1","item_id":"","revision":"","occurrence_id":"","has_more":False},
    ]
    assert output["next_offset"] is None
    from backend.capabilities.validation_next import validate_payload
    validate_payload(dict(specs(provider)[6][0].output_schema), output, label="output")


def test_plmxml_model_tree_read_pages_large_trees_without_losing_total_count():
    class Artifacts(_Artifacts):
        def read(self, reference, context): return XML_MODEL
    provider = PlmxmlEnvironmentProvider(_Repo(), Artifacts())
    digest = hashlib.sha256(XML_MODEL).hexdigest()
    ref = {"artifact_id":"model","media_type":"application/plmxml+xml",
           "sha256":digest,"byte_size":len(XML_MODEL),"version":1}
    context = CapabilityContext(user_gid="30", team_gid="20", request_id="tree-page")

    first = provider.read_model_tree({"artifact_ref":ref, "offset":0, "limit":1}, context).data
    second = provider.read_model_tree({"artifact_ref":ref, "offset":1, "limit":1}, context).data

    assert first["node_count"] == second["node_count"] == 2
    assert [item["node_key"] for item in first["nodes"]] == ["root"]
    assert first["next_offset"] == 1
    assert [item["node_key"] for item in second["nodes"]] == ["child"]
    assert second["next_offset"] is None


def test_imported_model_tree_reads_database_cache_without_reopening_artifact(monkeypatch):
    from plugins.simulation.simulation_backend.capabilities import plmxml_environments as module
    ref = {"artifact_id":"model","media_type":"application/plmxml+xml",
           "sha256":"a" * 64,"byte_size":100,"version":1}
    tree = {"state":"ready", "nodes":[{"node_key":"part-1"}, {"node_key":"part-2"}],
            "dependency_locations":[]}
    monkeypatch.setattr(module, "read_product_tree", lambda **kwargs: tree)
    class Artifacts:
        def read(self, reference, context): raise AssertionError("artifact reopened on cache hit")
    provider = PlmxmlEnvironmentProvider(_Repo(), Artifacts())
    output = provider.read_model_tree({"artifact_ref":ref, "document_gid":"44", "offset":1, "limit":1},
        CapabilityContext(user_gid="30", team_gid="20", request_id="tree-cached")).data
    assert output["node_count"] == 2
    assert output["nodes"] == [{"node_key":"part-2"}]
    assert output["next_offset"] is None


def test_cached_tree_still_authorizes_dependency_artifacts(monkeypatch):
    from plugins.simulation.simulation_backend.capabilities import plmxml_environments as module
    checked = []
    monkeypatch.setattr(module, "require_artifact", lambda ref, context: checked.append(ref["artifact_id"]))
    monkeypatch.setattr(module, "read_product_tree", lambda **kwargs: {
        "state":"ready", "nodes":[], "dependency_locations":[]})
    provider = PlmxmlEnvironmentProvider(_Repo())
    provider.read_model_tree({"artifact_ref":{"artifact_id":"primary"}, "document_gid":"44",
        "dependency_artifacts":[{"location":"base.plmxml", "artifact_ref":{"artifact_id":"dependency"}}]},
        CapabilityContext(user_gid="30", team_gid="20", request_id="tree-auth"))
    assert checked == ["dependency"]


def test_imported_model_tree_backfills_once_then_pages_from_database(monkeypatch):
    from plugins.simulation.simulation_backend.capabilities import plmxml_environments as module
    cached = {}
    monkeypatch.setattr(module, "read_product_tree", lambda **kwargs: cached.get("tree"))
    monkeypatch.setattr(module, "save_product_tree", lambda **kwargs: cached.update(tree=kwargs["tree"]))
    class Artifacts:
        reads = 0
        def read(self, reference, context):
            self.reads += 1
            return XML_MODEL
    artifacts = Artifacts()
    provider = PlmxmlEnvironmentProvider(_Repo(), artifacts)
    ref = {"artifact_id":"model","media_type":"application/plmxml+xml",
           "sha256":hashlib.sha256(XML_MODEL).hexdigest(),"byte_size":len(XML_MODEL),"version":1}
    context = CapabilityContext(user_gid="30", team_gid="20", request_id="tree-backfill")
    first = provider.read_model_tree({"artifact_ref":ref,"document_gid":"44","limit":1}, context).data
    second = provider.read_model_tree({"artifact_ref":ref,"document_gid":"44","offset":1,"limit":1}, context).data
    assert [row["node_key"] for row in first["nodes"]] == ["root"]
    assert [row["node_key"] for row in second["nodes"]] == ["child"]
    assert artifacts.reads == 1
    assert len(cached["tree"]["nodes"]) == 2


def test_plmxml_model_tree_read_reports_external_product_document_dependency():
    class Artifacts(_Artifacts):
        def read(self, reference, context): return XML_MODEL_WITH_EXTERNAL_PRODUCT
    provider = PlmxmlEnvironmentProvider(_Repo(), Artifacts())
    digest = hashlib.sha256(XML_MODEL_WITH_EXTERNAL_PRODUCT).hexdigest()
    ref = {"artifact_id":"external-model","media_type":"application/plmxml+xml",
           "sha256":digest,"byte_size":len(XML_MODEL_WITH_EXTERNAL_PRODUCT),"version":1}

    output = provider.read_model_tree(
        {"artifact_ref":ref}, CapabilityContext(user_gid="30", team_gid="20", request_id="tree-external"),
    ).data

    assert output == {
        "state": "dependency_required", "node_count": 0, "nodes": [],
        "dependency_locations": ["base.plmxml"], "next_offset": None,
    }


def test_plmxml_model_tree_read_uses_supplied_product_document_dependency():
    class Artifacts:
        def read(self, reference, context):
            return XML_MODEL_WITH_EXTERNAL_PRODUCT if reference["artifact_id"] == "primary" else XML_MODEL

    provider = PlmxmlEnvironmentProvider(_Repo(), Artifacts())
    primary_digest = hashlib.sha256(XML_MODEL_WITH_EXTERNAL_PRODUCT).hexdigest()
    dependency_digest = hashlib.sha256(XML_MODEL).hexdigest()
    primary_ref = {"artifact_id": "primary", "media_type": "application/plmxml+xml",
                   "sha256": primary_digest, "byte_size": len(XML_MODEL_WITH_EXTERNAL_PRODUCT), "version": 1}
    dependency_ref = {"artifact_id": "dependency", "media_type": "application/vnd.siemens.plmxml+xml",
                      "sha256": dependency_digest, "byte_size": len(XML_MODEL), "version": 1}

    output = provider.read_model_tree(
        {"artifact_ref": primary_ref, "dependency_artifacts": [
            {"location": "base.plmxml", "artifact_ref": dependency_ref},
        ]},
        CapabilityContext(user_gid="30", team_gid="20", request_id="tree-external-resolved"),
    ).data

    assert output["state"] == "ready"
    assert output["node_count"] == 2
    assert [item["node_key"] for item in output["nodes"]] == ["root", "child"]
    assert output["dependency_locations"] == []


def test_plmxml_insert_requires_matching_inspection_and_explicit_hierarchy_selection():
    class Artifacts(_Artifacts):
        def read(self, reference, context): return XML_TWO
    repo = _Repo(); provider = PlmxmlEnvironmentProvider(repo, Artifacts())
    ref = {"artifact_id":"in","media_type":"application/plmxml+xml",
           "sha256":hashlib.sha256(XML_TWO).hexdigest(),"byte_size":len(XML_TWO),"version":1}
    ctx = CapabilityContext(user_gid="30", team_gid="20", request_id="insert-1")
    inspection = provider.inspect_environment({"artifact_ref": ref}, ctx).data
    inserted = provider.insert_environment({"workspace_gid":"10","expected_row_version":1,
        "artifact_ref":ref,"display_name":"source","mode":"model_and_selected_hierarchies",
        "selected_hierarchy_identities":["b"],"inspection_hash":inspection["inspection_hash"],
        "idempotency_key":"insert-1"}, ctx).data
    assert inserted["selected_hierarchy_identities"] == ["b"]
    assert repo.import_calls[-1]["document_role"] == "auto"
    assert [item.projection_identity for item in repo.import_calls[-1]["projection"].hierarchies] == ["b"]


def test_plmxml_restore_creates_new_environment_without_reusing_import_contract():
    repo = _Repo(); provider = PlmxmlEnvironmentProvider(repo, _Artifacts())
    ref = {"artifact_id":"in","media_type":"application/plmxml+xml",
           "sha256":hashlib.sha256(XML).hexdigest(),"byte_size":len(XML),"version":1}
    ctx = CapabilityContext(user_gid="30", team_gid="20", request_id="restore-1")
    inspection = provider.inspect_environment({"artifact_ref": ref}, ctx).data
    restored = provider.restore_environment({"artifact_ref":ref,"name":"Restored ALT","display_name":"source",
        "inspection_hash":inspection["inspection_hash"],"idempotency_key":"restore-1"},ctx).data
    assert restored["workspace_gid"] == "11"
    assert repo.restore_call["name"] == "Restored ALT"


def test_plmxml_restore_records_unresolved_external_dependencies_without_forcing_upload():
    class Artifacts(_Artifacts):
        def read(self, reference, context):
            return XML_DEP if reference["artifact_id"] == "in" else b"JT"
    repo = _Repo(); provider = PlmxmlEnvironmentProvider(repo, Artifacts())
    ref = {"artifact_id":"in","media_type":"application/plmxml+xml",
           "sha256":hashlib.sha256(XML_DEP).hexdigest(),"byte_size":len(XML_DEP),"version":1}
    ctx = CapabilityContext(user_gid="30", team_gid="20", request_id="restore-deps")
    inspection = provider.inspect_environment({"artifact_ref": ref}, ctx).data
    payload = {"artifact_ref":ref,"name":"Restored","display_name":"source",
        "inspection_hash":inspection["inspection_hash"],"idempotency_key":"restore-deps"}
    restored = provider.restore_environment(payload, ctx).data
    assert repo.restore_call["resolved_dependencies"] == {}
    assert restored["report"]["unresolved_refs"] == ["parts/a.jt"]
    assert restored["report"]["document_count"] == 1
    dep = {"artifact_id":"jt","media_type":"model/vnd.jt","sha256":hashlib.sha256(b"JT").hexdigest(),"byte_size":2,"version":1}
    provider.restore_environment({**payload, "dependency_artifacts":[{"location":"parts/a.jt","artifact_ref":dep}]}, ctx)
    assert repo.restore_call["resolved_dependencies"]["parts/a.jt"]["artifact_id"] == "jt"


def test_plmxml_insert_records_structure_without_requesting_external_files():
    class Artifacts(_Artifacts):
        def read(self, reference, context): return XML_DEP
    repo = _Repo(); provider = PlmxmlEnvironmentProvider(repo, Artifacts())
    ref = {"artifact_id":"in","media_type":"application/plmxml+xml",
           "sha256":hashlib.sha256(XML_DEP).hexdigest(),"byte_size":len(XML_DEP),"version":1}
    ctx = CapabilityContext(user_gid="30", team_gid="20", request_id="insert-deps")
    inspection = provider.inspect_environment({"artifact_ref": ref}, ctx).data
    inserted = provider.insert_environment({"workspace_gid":"10","expected_row_version":1,
        "artifact_ref":ref,"display_name":"source","mode":"model_only",
        "selected_hierarchy_identities":[],"inspection_hash":inspection["inspection_hash"],
        "idempotency_key":"insert-deps"}, ctx).data
    assert repo.import_calls[-1]["resolved_dependencies"] == {}
    assert inserted["report"]["unresolved_refs"] == ["parts/a.jt"]


def test_plmxml_insert_reads_the_immutable_artifact_once_after_inspection():
    class Artifacts(_Artifacts):
        def __init__(self): super().__init__(); self.read_calls = 0
        def read(self, reference, context): self.read_calls += 1; return XML_TWO
    artifacts = Artifacts(); provider = PlmxmlEnvironmentProvider(_Repo(), artifacts)
    ref = {"artifact_id":"in","media_type":"application/plmxml+xml",
           "sha256":hashlib.sha256(XML_TWO).hexdigest(),"byte_size":len(XML_TWO),"version":1}
    ctx = CapabilityContext(user_gid="30", team_gid="20", request_id="insert-single-read")
    inspection = provider.inspect_environment({"artifact_ref": ref}, ctx).data
    artifacts.read_calls = 0
    provider.insert_environment({"workspace_gid":"10","expected_row_version":1,
        "artifact_ref":ref,"display_name":"source","mode":"model_only",
        "selected_hierarchy_identities":[],"inspection_hash":inspection["inspection_hash"],
        "idempotency_key":"insert-single-read"}, ctx)
    assert artifacts.read_calls == 1


def test_plmxml_capabilities_publish_every_stable_dependency_and_inspection_error():
    provider = PlmxmlEnvironmentProvider(_Repo(), _Artifacts())
    by_id = {spec.id: descriptor_for(spec) for spec, _ in specs(provider)}
    inspect_codes = {error.code for error in by_id["simulation.plmxml.environment.inspect"].domain_errors}
    write_codes = {error.code for error in by_id["simulation.environment.plmxml.insert"].domain_errors}

    assert {"plmxml_artifact_hash_mismatch", "plmxml_artifact_unavailable"} <= inspect_codes
    assert {
        "plmxml_dependency_artifact_invalid",
        "plmxml_dependency_media_type_mismatch",
        "plmxml_dependency_artifact_unavailable",
        "plmxml_dependency_artifact_hash_mismatch",
        "plmxml_insert_mode_required",
        "plmxml_hierarchy_selection_invalid",
        "plmxml_inspection_changed",
    } <= write_codes


def test_experimental_plmxml_capabilities_are_exposed_only_to_the_real_web_consumer():
    descriptors = [descriptor_for(spec) for spec, _ in specs(PlmxmlEnvironmentProvider(_Repo(), _Artifacts()))]
    for descriptor in descriptors[:3]:
        assert descriptor.lifecycle_status.value == "experimental"
        assert descriptor.exposure.web is True
        assert descriptor.exposure.api is False
        assert descriptor.exposure.plugin is False
        assert descriptor.exposure.agent is False
        assert descriptor.exposure.mcp is False
        assert not descriptor.business_effect.startswith("Governed ")
