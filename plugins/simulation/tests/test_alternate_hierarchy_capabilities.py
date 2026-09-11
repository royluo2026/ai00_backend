import asyncio
from types import SimpleNamespace
from backend.capability_v2.provider_contracts import CapabilityContext
from plugins.simulation.simulation_backend.capabilities.alternate_hierarchies import AlternateHierarchyProvider, specs


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


def test_hierarchy_capabilities_keep_sources_as_refs_and_allow_repeated_placement():
    repo = _Repo(); provider = AlternateHierarchyProvider(repo)
    ctx = CapabilityContext(user_gid="30", team_gid="20", request_id="r1")
    payload = {"hierarchy_gid": "12", "target_node_gid": "14", "parent_placement_gid": None,
               "source_kind": "jt", "source_ref": {"document_gid": "44"}, "transform": [1.0] * 16,
               "display_name": "Tool", "expected_row_version": 1, "idempotency_key": "place-1"}
    provider.create_placement(payload, ctx); provider.create_placement({**payload, "idempotency_key": "place-2"}, ctx)
    assert repo.calls[0][1]["source_ref"] == {"document_gid": "44"}
    ids = [item[0].id for item in specs(provider)]
    assert ids == [
        "simulation.environment.alternate_hierarchy.search", "simulation.environment.alternate_hierarchy.get",
        "simulation.environment.alternate_hierarchy.create", "simulation.environment.alternate_hierarchy.bootstrap_from_bop_fork", "simulation.environment.alternate_hierarchy.update",
        "simulation.environment.alternate_hierarchy.archive", "simulation.environment.placement.create",
        "simulation.environment.placement.move", "simulation.environment.placement.remove",
    ]


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
