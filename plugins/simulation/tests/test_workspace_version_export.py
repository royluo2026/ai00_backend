from datetime import datetime, timezone

import pytest

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext
from plugins.simulation.simulation_backend.capabilities.workspaces import WorkspaceProvider, candidate_specs
from plugins.simulation.simulation_backend.security.export_refs import verify_export_ref


class Repo:
    def __init__(self, status="frozen"):
        self.status=status; self.recorded=None
    def get_saved_version(self, **kwargs):
        return {"workspace_gid":"101","version_gid":"102","status":self.status,
                "content_hash":"sha256:"+"a"*64,"manifest_artifact_ref":{"artifact_gid":"900"}}
    def record_export_ref(self, **kwargs): self.recorded=kwargs


def ctx(): return CapabilityContext(user_gid="30",team_gid="20")


def payload():
    return {"workspace_gid":"101","version_gid":"102","target_personal_space_gid":"501",
            "target_repository_gid":"401","consumer_capability_id":"craft.bop.managed_personal_space.import.preview",
            "consumer_major_version":1,"expires_in_seconds":300,"idempotency_key":"export-1"}


def test_export_ref_is_bound_to_caller_target_consumer_and_hash(monkeypatch):
    monkeypatch.setenv("AI00_SIMULATION_EXPORT_SIGNING_KEY","test-signing-key")
    repo=Repo(); out=WorkspaceProvider(repo).export_for_import(payload(),ctx()).data
    claims=verify_export_ref(out["export_ref"])
    assert claims["actor_gid"]=="30" and claims["tenant_gid"]=="20"
    assert claims["target_personal_space_gid"]=="501"
    assert claims["consumer"]=="craft.bop.managed_personal_space.import.preview@1"
    assert claims["content_hash"]==out["content_hash"]
    assert repo.recorded["token_digest"].startswith("sha256:")


def test_only_saved_immutable_versions_can_be_exported(monkeypatch):
    monkeypatch.setenv("AI00_SIMULATION_EXPORT_SIGNING_KEY","test-signing-key")
    with pytest.raises(CapabilityBusinessError) as error:
        WorkspaceProvider(Repo("draft")).export_for_import(payload(),ctx())
    assert error.value.code=="source_version_not_immutable"


def test_export_candidate_is_closed_and_experimental():
    spec=next(s for s,_ in candidate_specs(WorkspaceProvider(Repo())) if s.id.endswith("export_for_import"))
    assert spec.input_schema["additionalProperties"] is False
    from plugins.simulation.simulation_backend.capabilities.provider import descriptor_for
    assert descriptor_for(spec).lifecycle_status.value=="experimental"
