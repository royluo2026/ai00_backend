from backend.capability_v2.provider_contracts import CapabilityContext
from backend.capabilities.validation_next import validate_payload
from plugins.simulation.simulation_backend.capabilities.workspaces import WorkspaceProvider, candidate_specs


class StubRepository:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(("create", kwargs))
        return {"workspace_gid": "101", "version_gid": "102", "name": kwargs["name"],
                "status": "active", "row_version": 1, "nodes": [], "bindings": []}

    def search(self, **kwargs):
        self.calls.append(("search", kwargs))
        return {"items": [{"workspace_gid": "101", "version_gid": "102", "name": "Environment",
                           "status": "active", "row_version": 1}], "next_cursor": None}

    def get(self, workspace_gid, **kwargs):
        self.calls.append(("get", {"workspace_gid": workspace_gid, **kwargs}))
        return {"workspace_gid": workspace_gid, "version_gid": "102", "name": "Environment",
                "status": "active", "row_version": 1, "nodes": [], "bindings": []}

    def mutate(self, **kwargs):
        self.calls.append(("mutate", kwargs))
        return {"entity_gid": "103", "row_version": kwargs["expected_row_version"] + 1,
                "patch": {"op": kwargs["operation"]}}


def _context():
    return CapabilityContext(user_gid="30", team_gid="20", request_id="r1")


def test_workspace_provider_scopes_create_search_and_get_to_current_owner():
    repo = StubRepository()
    provider = WorkspaceProvider(repo)
    created = provider.create({"name": "  My environment  "}, _context())
    searched = provider.search({"page_size": 20}, _context())
    opened = provider.get({"workspace_gid": "101"}, _context())
    assert created.data["workspace_gid"] == "101"
    assert searched.data["items"][0]["workspace_gid"] == "101"
    assert opened.data["version_gid"] == "102"
    assert created.evidence and searched.evidence and opened.evidence
    assert all(call[1]["tenant_gid"] == "20" and call[1]["owner_gid"] == "30" for call in repo.calls)


def test_workspace_candidates_are_experimental_and_user_actions_have_no_confirmation_popup():
    specs = candidate_specs(WorkspaceProvider(StubRepository()))
    ids = [spec.id for spec, _handler in specs]
    assert ids == [
        "simulation.environment.workspace.create",
        "simulation.environment.workspace.search",
        "simulation.environment.workspace.get",
        "simulation.environment.structure_node.create",
        "simulation.environment.structure_node.move",
        "simulation.environment.structure_node.remove",
        "simulation.environment.binding.create",
        "simulation.environment.binding.remove",
        "simulation.environment.version.freeze",
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
        "simulation.environment.workspace.create": provider.create({"name": "Environment"}, _context()).data,
        "simulation.environment.workspace.search": provider.search({"page_size": 20}, _context()).data,
        "simulation.environment.workspace.get": provider.get({"workspace_gid": "101"}, _context()).data,
    }
    for spec, _handler in candidate_specs(provider)[:3]:
        validate_payload(dict(spec.output_schema), outputs[spec.id], label="output")


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
