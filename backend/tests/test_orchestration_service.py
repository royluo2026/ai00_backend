from unittest.mock import Mock

import pytest

from plugins.agent.agent_backend.orchestration.models import GraphDraft
from plugins.agent.agent_backend.orchestration.reference_resolver import UntrustedCapabilityReference
from plugins.agent.agent_backend.orchestration.service import OrchestrationService, PublishBlocked


def publishable_graph(binding_count=1):
    return GraphDraft.model_validate({
        "nodes": [{
            "gid": "n1", "node_key": "bop", "title": "BOP 规划",
            "x_item_key": "TG1", "y_item_key": "工艺规划",
            "objective": "形成可发布 BOP", "owner_ref": "role:process-owner",
            "inputs": [{"name": "PBOM"}], "outputs": [{"name": "BOP"}],
            "acceptance_criteria": ["完整性通过"],
        }],
        "edges": [],
        "items": [
            {"gid": f"tool-{index}", "item_type": "task_tool", "title": "BOP Task Tool"}
            for index in range(binding_count)
        ],
        "capability_bindings": [
            {
                "gid": f"bind-{index}",
                "source_item_gid": f"tool-{index}",
                "capability_version_gid": "cv2_1",
                "purpose": "读取 BOP",
            }
            for index in range(binding_count)
        ],
    })


def trusted_binding():
    return {
        "capability_version_gid": "cv2_1",
        "capability_id": "craft.bop.read",
        "major_version": 1,
        "lifecycle_status": "stable",
        "provider_ref": "craft.provider",
        "gateway_ref": "agent.gateway.v1",
        "catalog_release_gid": "release-1",
        "artifact_hash": "sha256:abc",
    }


def test_publish_rejects_untrusted_capability_reference():
    repo = Mock()
    repo.get_graph.return_value = publishable_graph()
    resolver = Mock()
    resolver.resolve_capability_binding.side_effect = UntrustedCapabilityReference("cv2_1")
    service = OrchestrationService(repo, resolver)

    with pytest.raises(UntrustedCapabilityReference, match="cv2_1"):
        service.publish("v1", expected_revision=3, actor_gid="u1", tenant_gid="t1", project_gid="p1")

    repo.publish_version.assert_not_called()


def test_publish_rejects_incomplete_business_contract():
    repo = Mock()
    repo.get_graph.return_value = GraphDraft.model_validate({
        "nodes": [{"gid": "n1", "node_key": "bop", "title": "BOP", "x_item_key": "TG1", "y_item_key": "工艺规划"}],
        "edges": [],
    })
    service = OrchestrationService(repo, Mock())

    with pytest.raises(PublishBlocked, match="objective"):
        service.publish("v1", expected_revision=1, actor_gid="u1", tenant_gid="t1", project_gid="p1")


def test_publish_resolves_each_version_once_and_persists_only_trusted_projection():
    repo = Mock()
    repo.get_graph.return_value = publishable_graph(binding_count=2)
    repo.publish_version.return_value = {"version_gid": "v1", "revision": 4}
    resolver = Mock()
    resolver.resolve_capability_binding.return_value = trusted_binding()
    service = OrchestrationService(repo, resolver)

    result = service.publish("v1", expected_revision=3, actor_gid="u1", tenant_gid="t1", project_gid="p1")

    repo.get_graph.assert_called_once_with("v1", actor_gid="u1", tenant_gid="t1", project_gid="p1")
    resolver.resolve_capability_binding.assert_called_once_with("cv2_1", "u1")
    call = repo.publish_version.call_args
    assert call.args == ("v1",)
    assert call.kwargs["expected_revision"] == 3
    assert call.kwargs["actor_gid"] == "u1"
    assert [item["binding_gid"] for item in call.kwargs["resolved_bindings"]] == ["bind-0", "bind-1"]
    assert all(item["provider_ref"] == "craft.provider" for item in call.kwargs["resolved_bindings"])
    assert result["revision"] == 4


def test_publish_forwards_tenant_and_project_scope_to_read_and_write_guards():
    repo = Mock()
    repo.get_graph.return_value = publishable_graph()
    repo.publish_version.return_value = {"version_gid": "v1", "revision": 4}
    resolver = Mock()
    resolver.resolve_capability_binding.return_value = trusted_binding()
    service = OrchestrationService(repo, resolver)

    service.publish(
        "v1", expected_revision=3, actor_gid="u1",
        tenant_gid="tenant-1", project_gid="project-1",
    )

    repo.get_graph.assert_called_once_with(
        "v1", actor_gid="u1", tenant_gid="tenant-1", project_gid="project-1",
    )
    assert repo.publish_version.call_args.kwargs["tenant_gid"] == "tenant-1"
    assert repo.publish_version.call_args.kwargs["project_gid"] == "project-1"


def test_delete_binding_only_removes_agent_owned_binding():
    repo = Mock()
    service = OrchestrationService(repo, Mock())

    service.delete_capability_binding("bind-1", actor_gid="u1", tenant_gid="t1", project_gid="p1")

    repo.delete_binding.assert_called_once_with("bind-1", actor_gid="u1", tenant_gid="t1", project_gid="p1")
