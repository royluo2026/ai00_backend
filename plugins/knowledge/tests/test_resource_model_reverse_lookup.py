from backend.capability_v2.provider_contracts import CapabilityContext
from plugins.knowledge.knowledge_backend.capabilities.resource_model_reverse_lookup import (
    ResourceModelReverseLookupProvider,
    candidate_spec,
    normalize_model_number,
)


class StubRepository:
    def __init__(self, rows):
        self.rows = rows
        self.call = None

    def reverse_resolve(self, model_numbers, *, tenant_gid, as_of=None):
        self.call = (model_numbers, tenant_gid, as_of)
        return self.rows


def _context(team_gid="tenant-1"):
    return CapabilityContext(user_gid="user-1", team_gid=team_gid, request_id="request-1")


def test_exact_batch_reverse_lookup_supports_all_four_resource_types_and_trims_storage_fields():
    rows = [
        {"resource_type": kind, "normalized_code": f"{kind}-code", "model_number": f"MODEL-{index}", "mapping_version": 3}
        for index, kind in enumerate(("tool", "fixture", "equipment", "socket"), start=1)
    ]
    repository = StubRepository(rows)
    result = ResourceModelReverseLookupProvider(repository).resolve(
        {"model_numbers": [" MODEL-1 ", "model-2", "MODEL-3", "MODEL-4"]}, _context()
    ).data
    assert len(result["resolved"]) == 4
    assert not result["not_found"]
    assert not result["ambiguous"]
    assert set(result["resolved"][0]) == {"model_number", "resource_type", "resource_code", "mapping_version"}
    assert repository.call[1] == "tenant-1"


def test_not_found_and_ambiguous_are_per_input_and_no_fuzzy_auto_match_occurs():
    rows = [
        {"resource_type": "tool", "normalized_code": "t1", "model_number": "MODEL-1", "mapping_version": 1},
        {"resource_type": "fixture", "normalized_code": "f1", "model_number": "model-1", "mapping_version": 2},
    ]
    result = ResourceModelReverseLookupProvider(StubRepository(rows)).resolve(
        {"model_numbers": ["model-1", "model"]}, _context()
    ).data
    assert result["not_found"] == [{"model_number": "model"}]
    assert result["ambiguous"][0]["model_number"] == "model-1"
    assert len(result["ambiguous"][0]["candidates"]) == 2


def test_normalization_is_nfkc_exact_and_batch_is_bounded():
    assert normalize_model_number(" ＡＢＣ-１ ") == "abc-1"
    provider = ResourceModelReverseLookupProvider(StubRepository([]))
    try:
        provider.resolve({"model_numbers": [str(index) for index in range(501)]}, _context())
    except Exception as error:
        assert "mapping_batch_limit_exceeded" in str(error)
    else:
        raise AssertionError("batch limit must fail")


def test_candidate_contract_is_read_only_closed_and_not_registered_before_unified_approval():
    spec, _handler = candidate_spec(StubRepository([]))
    assert spec.id == "knowledge.resource_model_mapping.reverse_resolve"
    assert spec.input_schema["additionalProperties"] is False
    assert str(spec.confirmation.value if hasattr(spec.confirmation, "value") else spec.confirmation) == "none"
    from pathlib import Path
    registry_source = Path("plugins/knowledge/knowledge_backend/capabilities/__init__.py").read_text(encoding="utf-8")
    assert "resource_model_reverse_lookup" not in registry_source
