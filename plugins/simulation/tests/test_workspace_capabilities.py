from backend.capability_v2.provider_contracts import CapabilityContext
from backend.capabilities.validation_next import validate_payload
from plugins.simulation.simulation_backend.capabilities.workspaces import WorkspaceProvider, candidate_specs


_CACHE_REVISION_HASH = "sha256:" + "a" * 64


class StubRepository:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(("create", kwargs))
        return {"workspace_gid": "101", "version_gid": "102", "name": kwargs["name"],
                "review_type": kwargs["review_type"], "version_label": kwargs["version_label"],
                "status": kwargs["status"], "visibility": kwargs["visibility"], "owner_gid": kwargs["owner_gid"],
                "is_owner": True, "project_gids": kwargs["project_gids"], "primary_project_gid": kwargs["primary_project_gid"],
                "updated_at": "2026-09-09T12:00:00", "row_version": 1,
                "cache_revision_hash": _CACHE_REVISION_HASH, "nodes": [], "bindings": []}

    def search(self, **kwargs):
        self.calls.append(("search", kwargs))
        return {"items": [{"workspace_gid": "101", "version_gid": "102", "name": "Environment", "review_type": "other",
                           "version_label": "V1", "status": "active", "visibility": "private", "owner_gid": "30", "is_owner": True,
                           "project_gids": [], "primary_project_gid": None, "updated_at": "2026-09-09T12:00:00", "row_version": 1,
                           "cache_revision_hash": _CACHE_REVISION_HASH}], "next_cursor": None}

    def get(self, workspace_gid, **kwargs):
        self.calls.append(("get", {"workspace_gid": workspace_gid, **kwargs}))
        return {"workspace_gid": workspace_gid, "version_gid": "102", "name": "Environment", "review_type": "other",
                "version_label": "V1", "status": "active", "visibility": "private", "owner_gid": "30", "is_owner": True,
                "project_gids": [], "primary_project_gid": None, "updated_at": "2026-09-09T12:00:00", "row_version": 1,
                "cache_revision_hash": _CACHE_REVISION_HASH, "nodes": [], "bindings": []}

    def mutate(self, **kwargs):
        self.calls.append(("mutate", kwargs))
        return {"entity_gid": "103", "row_version": kwargs["expected_row_version"] + 1,
                "cache_revision_hash": _CACHE_REVISION_HASH,
                "patch": {"op": kwargs["operation"], **(kwargs["values"] if kwargs["operation"] == "update_workspace" else {})}}

    def delete(self, **kwargs):
        self.calls.append(("delete", kwargs))
        return {"workspace_gid": kwargs["workspace_gid"], "deleted": True,
                "deletion_gid": "901", "row_version": kwargs["expected_row_version"] + 1,
                "cache_revision_hash": _CACHE_REVISION_HASH}


def _context():
    return CapabilityContext(user_gid="30", team_gid="20", request_id="r1")


def test_workspace_provider_scopes_create_search_and_get_to_current_owner():
    repo = StubRepository()
    provider = WorkspaceProvider(repo)
    created = provider.create({"name": "  My environment  ", "review_type": "node_review", "version_label": "V1", "status": "active", "visibility": "shared", "project_gids": ["501", "502"], "primary_project_gid": "501"}, _context())
    searched = provider.search({"page_size": 20}, _context())
    opened = provider.get({"workspace_gid": "101"}, _context())
    assert created.data["workspace_gid"] == "101"
    assert searched.data["items"][0]["workspace_gid"] == "101"
    assert opened.data["version_gid"] == "102"
    assert created.evidence and searched.evidence and opened.evidence
    assert all(call[1]["tenant_gid"] == "20" and call[1]["owner_gid"] == "30" for call in repo.calls)
    assert repo.calls[0][1]["project_gids"] == ["501", "502"]


def test_workspace_candidates_are_experimental_and_user_actions_have_no_confirmation_popup():
    specs = candidate_specs(WorkspaceProvider(StubRepository()))
    ids = [spec.id for spec, _handler in specs]
    assert ids == [
        "simulation.environment.workspace.create",
        "simulation.environment.workspace.search",
        "simulation.environment.workspace.get",
        "simulation.environment.workspace.cache_lease.get",
        "simulation.environment.workspace.update",
        "simulation.environment.workspace.delete",
        "simulation.environment.workspace.fork.preview",
        "simulation.environment.workspace.fork.apply",
        "simulation.environment.workspace_version.search",
        "simulation.environment.structure_node.create",
        "simulation.environment.structure_node.move",
        "simulation.environment.structure_node.remove",
        "simulation.environment.binding.create",
        "simulation.environment.binding.remove",
        "simulation.environment.version.freeze",
        "simulation.environment.workspace_version.export_for_import",
    ]
    create = specs[0][0]
    assert str(create.confirmation.value if hasattr(create.confirmation, "value") else create.confirmation) == "none"
    source = __import__("pathlib").Path(
        "plugins/simulation/simulation_backend/capabilities/__init__.py"
    ).read_text(encoding="utf-8")
    assert "candidate_specs" in source


def test_workspace_candidate_output_contracts_accept_real_provider_results():
    provider = WorkspaceProvider(StubRepository())
    outputs = {
        "simulation.environment.workspace.create": provider.create({"name": "Environment", "review_type": "other", "version_label": "V1", "status": "active", "visibility": "private", "project_gids": [], "primary_project_gid": None}, _context()).data,
        "simulation.environment.workspace.search": provider.search({"page_size": 20}, _context()).data,
        "simulation.environment.workspace.get": provider.get({"workspace_gid": "101"}, _context()).data,
    }
    for spec, _handler in candidate_specs(provider)[:3]:
        validate_payload(dict(spec.output_schema), outputs[spec.id], label="output")


def test_workspace_outputs_expose_authoritative_cache_revision_hash():
    specs = {spec.id: spec for spec, _handler in candidate_specs(WorkspaceProvider(StubRepository()))}
    for capability_id in (
        "simulation.environment.workspace.create",
        "simulation.environment.workspace.search",
        "simulation.environment.workspace.get",
        "simulation.environment.workspace.cache_lease.get",
        "simulation.environment.workspace.update",
        "simulation.environment.workspace.delete",
        "simulation.environment.structure_node.create",
        "simulation.environment.structure_node.move",
        "simulation.environment.structure_node.remove",
        "simulation.environment.binding.create",
        "simulation.environment.binding.remove",
    ):
        schema = specs[capability_id].output_schema
        item_schema = schema["properties"]["items"]["items"] if capability_id.endswith("workspace.search") else schema
        assert "cache_revision_hash" in item_schema["required"]
        assert item_schema["properties"]["cache_revision_hash"]["pattern"] == "^sha256:[0-9a-f]{64}$"


def test_workspace_update_forwards_metadata_as_owner_scoped_atomic_mutation():
    repo = StubRepository(); provider = WorkspaceProvider(repo)
    output = provider.update({"workspace_gid": "101", "expected_row_version": 3, "idempotency_key": "edit-1", "name": "Updated", "review_type": "node_review", "version_label": "V2", "status": "baseline", "visibility": "shared", "project_gids": ["501"], "primary_project_gid": "501"}, _context())
    call = repo.calls[-1][1]
    assert call["operation"] == "update_workspace"
    assert call["values"]["primary_project_gid"] == "501"
    assert output.data["row_version"] == 4
    spec = next(spec for spec, _handler in candidate_specs(provider) if spec.id.endswith("workspace.update"))
    validate_payload(dict(spec.output_schema), output.data, label="output")
    from plugins.simulation.simulation_backend.capabilities.provider import descriptor_for
    validate_payload(dict(descriptor_for(spec).output_schema), output.data, label="output")


def test_atomic_mutations_forward_cas_idempotency_and_owner_scope_without_confirmation():
    repo = StubRepository()
    provider = WorkspaceProvider(repo)
    output = provider.create_binding({
        "workspace_gid": "101", "node_gid": "201", "occurrence_gid": "301", "role": "load",
        "expected_row_version": 4, "idempotency_key": "drop-1",
    }, _context())
    result = output.data
    assert output.evidence
    assert result["row_version"] == 5
    call = repo.calls[-1][1]
    assert call["operation"] == "create_binding"
    assert call["tenant_gid"] == "20" and call["owner_gid"] == "30"
    for spec, _handler in candidate_specs(provider)[3:]:
        assert str(spec.confirmation.value if hasattr(spec.confirmation, "value") else spec.confirmation) == "none"


def test_freeze_candidate_is_closed_and_registered_only_as_experimental():
    specs = candidate_specs(WorkspaceProvider(StubRepository(), freeze_service=object()))
    freeze = next(spec for spec, _handler in specs if spec.id == "simulation.environment.version.freeze")
    assert freeze.input_schema["additionalProperties"] is False
    assert freeze.output_schema["additionalProperties"] is False
    from plugins.simulation.simulation_backend.capabilities.provider import descriptor_for
    descriptor = descriptor_for(freeze)
    lifecycle = descriptor.lifecycle_status.value if hasattr(descriptor.lifecycle_status, "value") else str(descriptor.lifecycle_status)
    assert lifecycle == "experimental"


def test_workspace_update_descriptor_is_owner_resource_scoped():
    spec = next(spec for spec, _handler in candidate_specs(WorkspaceProvider(StubRepository())) if spec.id.endswith("workspace.update"))
    from plugins.simulation.simulation_backend.capabilities.provider import descriptor_for
    descriptor = descriptor_for(spec)
    assert [(item.resource_type, item.payload_path) for item in descriptor.resource_selectors] == [("simulation-workspace", "workspace_gid")]


def test_workspace_delete_is_owner_scoped_cas_and_has_no_confirmation_popup():
    repo = StubRepository(); provider = WorkspaceProvider(repo)
    output = provider.delete({"workspace_gid": "101", "expected_row_version": 3,
                              "idempotency_key": "delete-1"}, _context())
    assert output.data == {"workspace_gid": "101", "deleted": True,
                           "deletion_gid": "901", "row_version": 4,
                           "cache_revision_hash": _CACHE_REVISION_HASH}
    assert repo.calls[-1] == ("delete", {"workspace_gid": "101", "tenant_gid": "20",
                                         "owner_gid": "30", "expected_row_version": 3,
                                         "idempotency_key": "delete-1"})
    spec = next(spec for spec, _handler in candidate_specs(provider)
                if spec.id == "simulation.environment.workspace.delete")
    assert spec.confirmation == "none"
    assert spec.input_schema["additionalProperties"] is False


def test_private_fork_uses_immutable_manifest_and_stays_private():
    import hashlib, json
    manifest={"schema":"ai00.simulation.environment-manifest.v1","workspace_gid":"101",
              "version_gid":"102","nodes":[],"bindings":[],"algorithms":{}}
    content=json.dumps(manifest,sort_keys=True,separators=(",", ":")).encode()
    class ForkRepo(StubRepository):
        def create_fork_preview(self, **kwargs):
            self.calls.append(("fork_preview",kwargs));return {"preview_gid":"701","plan_hash":"sha256:"+"b"*64,"source_workspace_gid":"101","source_version_gid":"102","source_content_hash":"sha256:"+hashlib.sha256(content).hexdigest(),"target_name":kwargs["target_name"],"target_version_label":kwargs["target_version_label"],"fork_depth":kwargs["fork_depth"],"visibility":"private","expires_at":"2026-09-09T12:10:00+00:00"}
        def get_fork_plan(self, **kwargs):
            return {"gid":"701","plan_hash":kwargs["plan_hash"],"source_workspace_gid":"101","source_version_gid":"102","content_hash":"sha256:"+hashlib.sha256(content).hexdigest(),"fork_depth":"process","manifest_artifact_ref":{"artifact_id":"900"}}
        def apply_fork(self, **kwargs):
            assert kwargs["manifest"]==manifest
            return {"workspace_gid":"801"}
    class Port:
        def read(self, reference, context):return content
    class Freeze:
        artifact_port=Port()
    repo=ForkRepo();provider=WorkspaceProvider(repo,freeze_service=Freeze())
    preview=provider.fork_preview({"source_workspace_gid":"101","source_version_gid":"102","target_name":"Fork 1","target_version_label":"V1","fork_depth":"process"},_context()).data
    applied=provider.fork_apply({"preview_gid":"701","plan_hash":preview["plan_hash"],"idempotency_key":"fork-1"},_context()).data
    assert preview["visibility"]=="private" and preview["fork_depth"]=="process" and applied["workspace_gid"]=="801"


def test_private_fork_copy_depth_filters_nodes_and_resource_bindings():
    from plugins.simulation.simulation_backend.data.workspace_repository import project_manifest_for_fork
    manifest={"nodes":[
        {"node_gid":"1","parent_gid":None,"node_type":"line"},
        {"node_gid":"2","parent_gid":"1","node_type":"station"},
        {"node_gid":"3","parent_gid":"2","node_type":"role"},
        {"node_gid":"4","parent_gid":"3","node_type":"process"},
        {"node_gid":"5","parent_gid":"4","node_type":"operation"},
    ],"bindings":[{"binding_gid":"6","node_gid":"5","occurrence_gid":"7"}]}
    projected=project_manifest_for_fork(manifest,"process")
    assert [row["node_gid"] for row in projected["nodes"]]==["1","2","3","4"]
    assert projected["bindings"]==[]
    assert project_manifest_for_fork(manifest,"all")["bindings"]==manifest["bindings"]
