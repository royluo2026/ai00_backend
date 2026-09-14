import asyncio
from types import SimpleNamespace
import pytest
from backend.capability_v2.provider_contracts import CapabilityContext
from plugins.craft.craft_backend.capabilities import bop_alt_hierarchy
from plugins.simulation.simulation_backend.capabilities.alternate_hierarchies import AlternateHierarchyProvider, build_bop_projection_plan, specs
from plugins.simulation.simulation_backend.capabilities.provider import descriptor_for


class _Repo:
    def __init__(self): self.calls = []
    def search_alternate_hierarchies(self, **kwargs): self.calls.append(("search", kwargs)); return {"items": []}
    def get_alternate_hierarchy(self, **kwargs): self.calls.append(("get", kwargs)); return {"hierarchy_gid": kwargs["hierarchy_gid"], "workspace_gid": "10", "name": "ALT", "status": "active", "projection_identity": "alt", "row_version": 1, "placements": []}
    def create_alternate_hierarchy(self, **kwargs): self.calls.append(("create", kwargs)); return {"hierarchy_gid": "12", "workspace_gid": kwargs["workspace_gid"], "name": kwargs["name"], "row_version": 1}
    def add_placement(self, **kwargs): self.calls.append(("placement", kwargs)); return {"placement_gid": "13", "hierarchy_gid": kwargs["hierarchy_gid"], "workspace_gid": "10", "row_version": 1, "hierarchy_row_version": 2}
    def mutate_alternate_hierarchy(self, **kwargs): self.calls.append(("mutate_hierarchy", kwargs)); return {"hierarchy_gid": kwargs["hierarchy_gid"], "workspace_gid": "10", "row_version": 2, "workspace_row_version": 3, "cache_revision_hash": "sha256:" + "0" * 64, "operation": kwargs["operation"]}
    def mutate_placement(self, **kwargs): self.calls.append(("mutate_placement", kwargs)); return {"placement_gid": kwargs["placement_gid"], "hierarchy_gid": "12", "workspace_gid": "10", "hierarchy_row_version": 2, "workspace_row_version": 3, "cache_revision_hash": "sha256:" + "0" * 64, "operation": kwargs["operation"]}
    def bootstrap_alternate_hierarchy(self, **kwargs):
        self.calls.append(("bootstrap", kwargs))
        return {"hierarchy_gid":"12","workspace_gid":kwargs["workspace_gid"],"name":kwargs["name"],
                "row_version":1,"workspace_row_version":kwargs["expected_workspace_version"]+1,
                "status":"active","node_count":len(kwargs["projection"]["nodes"])}
    def get(self, workspace_gid, **kwargs):
        return {"workspace_gid": workspace_gid, "owner_gid": "30", "is_owner": True, "status": "active", "row_version": 3}
    def insert_bop_projection(self, **kwargs):
        self.calls.append(("insert_bop", kwargs))
        return {"hierarchy_gid": "12", "workspace_gid": kwargs["workspace_gid"], "name": kwargs["plan"]["hierarchy_name"],
                "row_version": 1, "workspace_row_version": 4, "status": "active", "node_count": len(kwargs["plan"]["nodes"])}


def test_hierarchy_capabilities_keep_sources_as_refs_and_allow_repeated_placement():
    repo = _Repo(); provider = AlternateHierarchyProvider(repo)
    ctx = CapabilityContext(user_gid="30", team_gid="20", request_id="r1")
    payload = {"hierarchy_gid": "12", "target_node_gid": "14", "parent_placement_gid": None,
               "source_kind": "jt", "source_ref": {"document_gid": "44"}, "transform": [1.0] * 16,
               "display_name": "Tool", "expected_row_version": 1, "idempotency_key": "place-1"}
    asyncio.run(provider.create_placement(payload, ctx)); asyncio.run(provider.create_placement({**payload, "idempotency_key": "place-2"}, ctx))
    assert repo.calls[0][1]["source_ref"] == {"document_gid": "44"}
    ids = [item[0].id for item in specs(provider)]
    assert ids == [
        "simulation.environment.alternate_hierarchy.search", "simulation.environment.alternate_hierarchy.get",
        "simulation.environment.alternate_hierarchy.create", "simulation.environment.alternate_hierarchy.bootstrap_from_bop_fork", "simulation.environment.alternate_hierarchy.update",
        "simulation.environment.alternate_hierarchy.archive", "simulation.environment.placement.create",
        "simulation.environment.placement.move", "simulation.environment.placement.remove",
        "simulation.environment.bop_projection.preview", "simulation.environment.bop_projection.apply",
    ]
    get_spec = next(spec for spec, _ in specs(provider) if spec.id == "simulation.environment.alternate_hierarchy.get")
    assert {"nodes", "placements"} <= set(get_spec.output_schema["required"])
    create_spec = next(spec for spec, _ in specs(provider) if spec.id == "simulation.environment.alternate_hierarchy.create")
    assert "root_node_gid" in create_spec.output_schema["required"]


def test_bop_projection_plan_applies_line_scope_depth_and_separates_refs():
    execution = {"source": {"bop_version_gid": "100", "project_gid": "200", "revision": 7},
        "content_hash": "sha256:" + "a" * 64, "nodes": [
            {"node_id":"1","parent_id":None,"kind":"line_process","sequence":10,"name":"L1","part_refs":[]},
            {"node_id":"2","parent_id":"1","kind":"station_process","sequence":20,"name":"S1","part_refs":[]},
            {"node_id":"3","parent_id":"2","kind":"operation","sequence":30,"name":"O1","part_refs":["part:9"],"tool_refs":["tool:8"]},
            {"node_id":"4","parent_id":None,"kind":"line_process","sequence":40,"name":"L2","part_refs":[]},
        ]}
    plan = build_bop_projection_plan(execution, workspace_gid="10", expected_workspace_version=3,
        line_gid="1", fork_depth="station", hierarchy_name="L1 方案")
    assert [item["source_gid"] for item in plan["nodes"]] == ["1", "2"]
    assert plan["nodes"][0]["parent_source_gid"] is None
    assert plan["model_reference_count"] == 1
    assert plan["resource_reference_count"] == 1
    assert plan["model_references"] == [{"source_node_gid":"3","reference":"part:9"}]
    assert plan["resource_references"] == [{"source_node_gid":"3","resource_type":"tool","reference":"tool:8"}]
    assert plan["plan_hash"].startswith("sha256:")


def test_bop_projection_preview_and_apply_recheck_owner_source_and_plan_hash():
    execution = {"source": {"bop_version_gid": "100", "project_gid": "200", "revision": 7},
        "content_hash": "sha256:" + "a" * 64, "nodes": [
            {"node_id":"1","parent_id":None,"kind":"line_process","sequence":10,"name":"L1","part_refs":[]},
        ], "operations": [], "dependencies": [], "conditions": []}
    class Client:
        async def invoke(self, invocation, identity, correlation):
            assert invocation.capability_id == "craft.bop.execution_structure.get"
            assert invocation.payload == {"version_gid": "100"}
            return SimpleNamespace(ok=True, data=execution, error=None)
    repo = _Repo(); provider = AlternateHierarchyProvider(repo)
    context = CapabilityContext(user_gid="30", team_gid="20", request_id="bop-1",
        domain_client=Client(), effective_identity=SimpleNamespace())
    payload = {"workspace_gid":"10","version_gid":"100","line_gid":"1","fork_depth":"all",
        "hierarchy_name":"L1","expected_row_version":3}
    preview = asyncio.run(provider.preview_bop_projection(payload, context)).data
    applied = asyncio.run(provider.apply_bop_projection({**payload, "plan_hash":preview["plan_hash"],
        "idempotency_key":"bop-apply-1"}, context)).data
    assert applied["node_count"] == 1
    assert repo.calls[-1][0] == "insert_bop"
    with pytest.raises(Exception, match="bop_projection_plan_changed"):
        asyncio.run(provider.apply_bop_projection({**payload, "plan_hash":"sha256:"+"b"*64,
            "idempotency_key":"bop-apply-2"}, context))


def test_bop_projection_preview_falls_back_to_active_revision_pinned_preview():
    execution = {"source": {"bop_version_gid": "100", "project_gid": "200", "revision": 1},
        "content_hash": "sha256:" + "a" * 64, "nodes": [
            {"node_id":"1","parent_id":None,"kind":"line_process","sequence":10,"name":"L1","part_refs":[]},
        ], "operations": [], "dependencies": [], "conditions": []}

    class Client:
        def __init__(self): self.calls = []

        async def invoke(self, invocation, identity, correlation):
            self.calls.append((invocation.capability_id, invocation.payload))
            if invocation.capability_id == "craft.bop.execution_structure.get":
                return SimpleNamespace(ok=False, data=None,
                    error=SimpleNamespace(code="version_not_published"))
            if invocation.capability_id == "craft.bop.version.get":
                return SimpleNamespace(ok=True, data={"revision": 1}, error=None)
            assert invocation.capability_id == "craft.bop.execution_structure.preview"
            assert invocation.payload == {"version_gid": "100", "expected_revision": 1}
            assert invocation.expected_resource_version == "1"
            return SimpleNamespace(ok=True, data=execution, error=None)

    client = Client(); repo = _Repo(); provider = AlternateHierarchyProvider(repo)
    context = CapabilityContext(user_gid="30", team_gid="20", request_id="bop-active-1",
        domain_client=client, effective_identity=SimpleNamespace())
    payload = {"workspace_gid":"10","version_gid":"100","line_gid":"1","fork_depth":"all",
        "hierarchy_name":"L1 active","expected_row_version":3}
    result = asyncio.run(provider.preview_bop_projection(payload, context)).data
    assert result["source_revision"] == 1
    assert [call[0] for call in client.calls] == [
        "craft.bop.execution_structure.get", "craft.bop.version.get",
        "craft.bop.execution_structure.preview",
    ]


def test_bop_alt_hierarchy_can_bound_line_discovery_without_loading_the_full_tree(monkeypatch):
    class Cursor:
        def __init__(self): self.sql = ""; self.params = []
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def execute(self, sql, params): self.sql, self.params = sql, list(params)
        def fetchall(self):
            return [{"gid": "1", "parent_gid": None, "node_type": "line_process", "sort_order": 0,
                     "title": "L1", "vpps": None, "level": 1, "ai00_level": 1,
                     "part_gid": None, "part_no": None, "catia_occurrence_name": None,
                     "part_name": None, "part_vpps": None, "quantity": None}]

    class Connection:
        def __init__(self): self.cursor_obj = Cursor()
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def cursor(self): return self.cursor_obj

    connection = Connection()
    monkeypatch.setattr(bop_alt_hierarchy, "get_craft_conn", lambda: connection)
    result = bop_alt_hierarchy.read_bop_alt_hierarchy(
        {"version_gid": "100", "node_types": ["line", "line_process"]}, None,
    )
    assert result.data["entries"][0]["node_type"] == "line_process"
    assert "e.node_type IN (%s,%s)" in connection.cursor_obj.sql
    assert connection.cursor_obj.params == ["100", "line", "line_process"]


def test_bop_projection_descriptors_are_web_only_and_governance_complete():
    values = [descriptor_for(spec) for spec, _ in specs(AlternateHierarchyProvider(_Repo())) if spec.id.startswith("simulation.environment.bop_projection.")]
    assert len(values) == 2
    for descriptor in values:
        assert descriptor.lifecycle_status.value == "experimental"
        assert descriptor.exposure.web is True
        assert descriptor.exposure.api is False
        assert descriptor.domain_errors_complete is True
        assert descriptor.business_effect
        assert descriptor.business_acceptance_criteria
    apply = next(descriptor for descriptor in values if descriptor.id.endswith(".apply"))
    assert apply.consistency_policy == "external"


def test_alternate_hierarchy_detail_contract_accepts_bop_source_references():
    from backend.capabilities.validation_next import validate_payload
    descriptor = next(descriptor_for(spec) for spec, _ in specs(AlternateHierarchyProvider(_Repo()))
                      if spec.id == "simulation.environment.alternate_hierarchy.get")
    validate_payload(descriptor.output_schema, {
        "hierarchy_gid": "12", "workspace_gid": "10", "name": "前悬分装线",
        "status": "active", "projection_identity": "craft-bop:100:1:station:sha256:x",
        "row_version": 1,
        "source_refs": {"model_references": [{"source_node_gid": "21", "reference": "part:22"}],
                        "resource_references": [{"source_node_gid": "21", "resource_type": "tool", "reference": "tool:23"}]},
        "nodes": [{"node_gid": "20", "workspace_gid": "10", "hierarchy_gid": "12",
                   "parent_gid": None, "node_type": "line_process", "name": "前悬分装线",
                   "sort_order": 0, "source_bop_node_gid": "21", "row_version": 1}],
        "placements": [{"placement_gid": "30", "hierarchy_gid": "12", "workspace_gid": "10",
                        "target_node_gid": "20", "parent_placement_gid": None,
                        "source_kind": "plmxml", "source_ref": {"document_gid": "44", "node_key": "part-7",
                        "occurrence_id": "occ-7"}, "transform": [1.0] * 16,
                        "display_name": "零件7", "sort_order": 0, "row_version": 1}],
    })
    create_descriptor = next(descriptor_for(spec) for spec, _ in specs(AlternateHierarchyProvider(_Repo()))
                             if spec.id == "simulation.environment.placement.create")
    validate_payload(create_descriptor.input_schema, {"hierarchy_gid": "12", "target_node_gid": "20",
        "source_kind": "plmxml", "source_ref": {"document_gid": "44", "node_key": "part-7"},
        "transform": [1.0] * 16, "expected_row_version": 1, "idempotency_key": "place-part-7"})


def test_bop_fork_bootstrap_consumes_governed_projection_and_is_repairable():
    class Client:
        async def invoke(self, invocation, identity, correlation):
            assert invocation.capability_id == "craft.bop.fork_projection.get"
            assert invocation.payload == {"fork_run_gid": "70"}
            return SimpleNamespace(ok=True, data={"source_repository_gid":"90","source_version_gid":"100",
                "source_content_hash":"sha256:"+"a"*64,"fork_operation_gid":"70","nodes":[
                    {"node_gid":"101","parent_gid":None,"node_type":"line","name":"总装线","position":0}
                ]}, error=None)

    repo = _Repo(); provider = AlternateHierarchyProvider(repo)
    context = CapabilityContext(user_gid="30", team_gid="20", request_id="repair-1",
        domain_client=Client(), effective_identity=SimpleNamespace())
    result = asyncio.run(provider.bootstrap_from_bop_fork({"workspace_gid":"10","fork_run_gid":"70",
        "name":"W10 BOP","expected_row_version":3,"idempotency_key":"bootstrap-70"}, context)).data
    assert result["node_count"] == 1
    assert repo.calls[-1][1]["projection"]["source_repository_gid"] == "90"


def test_resource_placement_uses_exact_craft_owner_projection():
    class Client:
        async def invoke(self, invocation, identity, correlation):
            assert invocation.capability_id == "craft.resource_requirement.get"
            assert invocation.payload == {"gid": "77"}
            return SimpleNamespace(ok=True, data={"gid":"77","resource_type":"tool","code":"T-1",
                "name":"Tool","status":"active","resource_version":4}, error=None)
    repo = _Repo(); provider = AlternateHierarchyProvider(repo)
    context = CapabilityContext(user_gid="30", team_gid="20", request_id="resource-1",
        domain_client=Client(), effective_identity=SimpleNamespace())
    asyncio.run(provider.create_placement({"hierarchy_gid":"12","target_node_gid":"14",
        "source_kind":"resource","source_ref":{"resource_gid":"77","name":"forged"},
        "transform":[1.0]*16,"display_name":"Tool","expected_row_version":1,
        "idempotency_key":"resource-place-1"}, context))
    stored = repo.calls[-1][1]["source_ref"]
    assert {key: stored[key] for key in ("resource_gid","resource_type","resource_code","resource_name","resource_version")} == {
        "resource_gid":"77","resource_type":"tool","resource_code":"T-1","resource_name":"Tool","resource_version":"4"}
    assert stored["source_projection_hash"].startswith("sha256:")
