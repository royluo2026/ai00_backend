from backend.capability_v2.provider_contracts import CapabilityContext
from plugins.simulation.simulation_backend.capabilities.product_structures import (
    ProductStructureProvider, specs,
)


class _Repo:
    def __init__(self):
        self.calls = []

    def register_online_source(self, **kwargs):
        self.calls.append(("bind", kwargs))
        return {"source_gid": "11", "document_gid": "12",
                "source_identity_hash": "sha256:" + "a" * 64,
                "insertion_instance_id": kwargs["insertion_instance_id"],
                "workspace_row_version": 3,
                "cache_revision_hash": "sha256:" + "b" * 64}

    def begin_observation(self, **kwargs):
        self.calls.append(("begin", kwargs))
        return {"observation_gid": "13", "observation_id": kwargs["observation_id"],
                "captured_at": kwargs["captured_at"], "node_count": kwargs["node_count"],
                "page_count": kwargs["page_count"], "manifest_hash": "sha256:" + "c" * 64,
                "complete": False}

    def append_observation_page(self, **kwargs):
        self.calls.append(("append", kwargs))
        return {"page_hash": "sha256:" + "d" * 64, "replayed": False}

    def publish_observation(self, observation_gid, **kwargs):
        self.calls.append(("publish", {"observation_gid": observation_gid, **kwargs}))
        return {"observation_id": "tcobs:" + "e" * 64, "complete": True,
                "node_count": 1, "page_count": 1}

    def get_observation_page(self, **kwargs):
        self.calls.append(("page", kwargs))
        return {"observation_id": kwargs["observation_id"], "cursor": 0,
                "next_cursor": None, "nodes": [], "node_count": 1}


def _context():
    return CapabilityContext(user_gid="30", team_gid="20", request_id="r1")


def _selector():
    return {"endpoint_id": "tc-production", "object_uid": "uid-1",
            "item_revision_uid": "rev-1", "bom_view_uid": "bvr-1",
            "revision_rule": "Latest Working",
            "configuration_date": "2026-09-16T00:00:00+00:00"}


def _node():
    return {"occurrence_id": "occ-1", "parent_occurrence_id": None, "depth": 0,
            "child_order": 0, "name": "Root", "item_uid": "item-1", "item_id": "STU-1",
            "item_revision_uid": "rev-1", "revision_id": "00;1", "component_type": "C9_StudyRevision",
            "owning_user": "luoyi8", "owning_group": "Engineering", "transform": None, "bbox": None,
            "geometry_refs": [{"dataset_uid": "ds-1", "file_uid": "file-1",
                               "file_name": "part.jt", "relation_type": "IMAN_Rendering"}]}


def test_product_structure_capabilities_are_simulation_owned_and_scoped():
    repo = _Repo()
    provider = ProductStructureProvider(repo)
    provider.bind_source({"workspace_gid": "10", "expected_row_version": 2,
                          "display_name": "Tool2025", "insertion_instance_id": "insert-1",
                          "source_selector": _selector()}, _context())
    provider.begin({"workspace_gid": "10", "source_gid": "11",
                    "observation_id": "tcobs:" + "e" * 64,
                    "captured_at": "2026-09-16T00:01:00+00:00",
                    "node_count": 1, "page_count": 1}, _context())
    provider.append_page({"observation_gid": "13", "page_index": 0,
                          "cursor": 0, "next_cursor": None, "nodes": [_node()]}, _context())
    provider.publish({"observation_gid": "13"}, _context())
    provider.read_page({"observation_id": "tcobs:" + "e" * 64,
                        "cursor": 0, "page_size": 1000}, _context())
    assert repo.calls[0][1]["tenant_gid"] == "20"
    assert repo.calls[0][1]["actor_gid"] == "30"
    capability_specs = [item[0] for item in specs(provider)]
    assert [item.id for item in capability_specs] == [
        "simulation.environment.online_source.bind",
        "simulation.product_structure.observation.begin",
        "simulation.product_structure.observation.page.append",
        "simulation.product_structure.observation.publish",
        "simulation.product_structure.snapshot.page.get",
    ]
    assert all(item.owner == "simulation" for item in capability_specs)
    assert capability_specs[0].risk == "write"
    assert capability_specs[-1].risk == "read"
