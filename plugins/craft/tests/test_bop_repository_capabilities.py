from types import SimpleNamespace

import pytest

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext


EXPECTED = {
    "craft.bop.repository.search", "craft.bop.repository.get", "craft.bop.repository.create",
    "craft.bop.repository.archive", "craft.bop.repository.restore", "craft.bop.repository.delete",
    "craft.bop.repository_baseline.set", "craft.bop.space.search", "craft.bop.space.get",
    "craft.bop.space_version.search", "craft.bop.space_version.get",
    "craft.bop.space_version.save", "craft.bop.space_version.freeze",
    "craft.bop.managed_personal_space.delete",
}


class StubStore:
    def __init__(self): self.calls = []
    def __getattr__(self, name):
        def call(**kwargs):
            self.calls.append((name, kwargs))
            return {"operation": name, **kwargs}
        return call


def context():
    return CapabilityContext(user_gid="30", team_gid="20", resource_refs=("project:10",))


def test_repository_candidates_are_closed_and_not_stable():
    from plugins.craft.craft_backend.capabilities.bop_repositories import candidate_specs
    from plugins.craft.craft_backend.capabilities.provider import descriptor_for

    items = candidate_specs(StubStore())
    assert {spec.id for spec, _ in items} == EXPECTED
    assert all(spec.input_schema["additionalProperties"] is False for spec, _ in items)
    assert all(descriptor_for(spec).lifecycle_status.value == "experimental" for spec, _ in items)
    assert all(spec.confirmation == "none" for spec, _ in items)


def test_create_uses_trusted_context_identity_and_not_payload_identity():
    from plugins.craft.craft_backend.capabilities.bop_repositories import RepositoryProvider

    store = StubStore()
    out = RepositoryProvider(store).create_repository(
        {"project_gid": "10", "idempotency_key": "create-1"}, context()
    )
    name, args = store.calls[-1]
    assert name == "create_repository"
    assert args["tenant_gid"] == "20" and args["actor_gid"] == "30"
    assert out.data["project_gid"] == "10"


def test_search_rejects_unbounded_page_size_before_store_call():
    from plugins.craft.craft_backend.capabilities.bop_repositories import RepositoryProvider

    store = StubStore()
    with pytest.raises(CapabilityBusinessError) as error:
        RepositoryProvider(store).search_repositories({"page_size": 101}, context())
    assert error.value.code == "page_size_invalid"
    assert store.calls == []


def test_store_errors_are_stable_business_errors():
    from plugins.craft.craft_backend.capabilities.bop_repositories import RepositoryProvider
    from plugins.craft.craft_backend.data.bop_repository import BopRepositoryError

    class Broken(StubStore):
        def get_repository(self, **kwargs): raise BopRepositoryError("repository_not_found")

    with pytest.raises(CapabilityBusinessError) as error:
        RepositoryProvider(Broken()).get_repository({"repository_gid": "99"}, context())
    assert error.value.code == "repository_not_found"
