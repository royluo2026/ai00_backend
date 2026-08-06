from dataclasses import dataclass

import pytest

from backend.capabilities.models_next import CapabilityContext
from backend.capabilities.registry_next import CapabilityRegistry
from backend.capabilities.system_shared_next import (
    cancel_job,
    preview_impact,
    register_system_shared_capabilities,
    semantic_context,
    system_search,
)
from backend.system_capabilities.providers import provider_registry


CONTEXT = CapabilityContext(user_gid="u1", team_gid="t1")


@dataclass
class SearchProvider:
    owner: str = "craft"

    def search(self, query, limit, context):
        return [{
            "object_ref": "craft://bop/v1", "title": "Station BOP", "summary": "match",
            "match_reason": "title", "owner": self.owner,
            "internal_row": {"must": "not leak"},
        }]


class JobProvider:
    owner = "base"

    def get(self, job_gid, context): return {"job_gid": job_gid, "status": "running", "owner": self.owner}
    def cancel(self, job_gid, context): return {"job_gid": job_gid, "status": "cancel_requested", "owner": self.owner}


def setup_function():
    provider_registry.clear()


def teardown_function():
    provider_registry.clear()


def test_system_search_returns_refs_not_domain_details():
    provider_registry.register_search(SearchProvider())
    item = system_search({"query": "station"}, CONTEXT).data["items"][0]
    assert set(item) <= {"object_ref", "title", "summary", "match_reason", "owner"}
    assert item["owner"] == "craft"


def test_semantic_context_rejects_arbitrary_query_languages():
    with pytest.raises(ValueError, match="named_view"):
        semantic_context({"sparql": "SELECT * WHERE {?s ?p ?o}"}, CONTEXT)


def test_job_cancel_does_not_claim_rollback():
    provider_registry.register_jobs(JobProvider())
    result = cancel_job({"job_gid": "j1", "owner": "base"}, CONTEXT)
    assert result.data["rolled_back"] is False
    assert result.data["status"] == "cancel_requested"


def test_change_impact_requires_server_issued_change_ref():
    with pytest.raises(ValueError, match="change_ref"):
        preview_impact({"description": "change the station"}, CONTEXT)


def test_shared_capability_ids_are_registered_without_overlap():
    registry = CapabilityRegistry()
    register_system_shared_capabilities(registry)
    ids = {spec.id for spec in registry.list()}
    assert ids == {
        "system.search", "system.activity.search", "system.job.get", "system.job.cancel",
        "identity.principal.search", "system.lineage.get", "system.change_impact.preview",
        "semantic.context.get", "base.project.search",
    }
