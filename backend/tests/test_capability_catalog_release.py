from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.capabilities.models_next import CapabilitySpec
from backend.capabilities.registry_next import CapabilityRegistry
from backend.capability_v2.catalog import (
    CatalogResolutionError,
    CatalogResolver,
    ProviderArtifact,
    build_release,
    build_catalog_entry,
    compatibility_errors,
    complete_governance_metadata,
)
from backend.capability_v2.catalog_store import InMemoryCatalogStore, SqlCatalogStore
from backend.capability_v2.contracts import (
    AutomationLevel,
    CapabilityDescriptorV2,
    DomainErrorContract,
    ExposurePolicy,
    ExecutionBudget,
    LifecycleStatus,
)
from backend.capability_v2.provider_loader import hash_domain_artifact
from backend.plugin_loader import PluginLoader, ProviderTrustError


def _descriptor(capability_id: str, major: int = 1) -> CapabilityDescriptorV2:
    return CapabilityDescriptorV2(
        id=capability_id,
        major_version=major,
        owner_domain=capability_id.split(".", 1)[0],
        title=capability_id,
        description=f"Stable contract for {capability_id}.",
        use_when="The caller needs this exact business result.",
        do_not_use_when="The caller needs a different business result.",
        exposure=ExposurePolicy(web=True, api=True),
        automation_level=AutomationLevel.A2,
        authorization_policy=f"{capability_id}.read",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        output_schema={"type": "object", "properties": {}, "additionalProperties": False},
        schema_hash="sha256:" + str(major) * 64,
    )


def _provider(plugin_id: str = "official.craft") -> ProviderArtifact:
    return ProviderArtifact(
        plugin_id=plugin_id,
        module="craft_backend.capabilities",
        version="1.0.0",
        artifact_hash="sha256:" + "a" * 64,
    )


def test_catalog_hash_is_order_independent_and_binds_provider_artifacts():
    descriptors = [_descriptor("craft.routing.get"), _descriptor("knowledge.document.get")]

    forward = build_release(descriptors, [_provider()], created_at=datetime(2026, 8, 10, tzinfo=UTC))
    reverse = build_release(reversed(descriptors), reversed([_provider()]), created_at=forward.created_at)
    changed_provider = build_release(descriptors, [_provider("official.craft-next")], created_at=forward.created_at)

    assert forward.catalog_hash == reverse.catalog_hash
    assert forward.release_id == reverse.release_id
    assert forward.catalog_hash != changed_provider.catalog_hash


def test_catalog_projects_business_definition_hash():
    descriptor = CapabilityDescriptorV2.model_validate(_descriptor("person.height.write").model_dump(mode="json") | {
        "business_acceptance_criteria": ["The normalized height is stored."],
        "business_invariants": [{
            "rule_id": "person.height.range",
            "version": 1,
            "statement": "Height is 0.3m to 2.5m.",
            "applies_when": "height changes",
            "enforcement_ref": "person.provider:validate_height",
            "error_code": "invalid_person_height",
            "test_refs": ["backend/tests/test_person_height.py::test_range"],
        }],
    })

    entry = build_catalog_entry(descriptor)

    assert entry["business_definition_hash"].startswith("sha256:")
    assert entry["business_invariants"][0]["rule_id"] == "person.height.range"


def test_generated_catalog_declares_exact_acceptance_cases_without_self_attested_results():
    from backend.scripts.build_capability_catalog import current_release

    stable = [
        descriptor
        for descriptor in current_release().descriptors
        if descriptor.lifecycle_status is LifecycleStatus.STABLE
    ]

    assert stable
    assert all(len(descriptor.test_refs) == 7 for descriptor in stable)
    assert all(
        "result" not in test_ref
        for descriptor in stable
        for test_ref in descriptor.test_refs
    )
    assert all(
        f"[{descriptor.id}@{descriptor.major_version}]" in str(test_ref["test_node_id"])
        for descriptor in stable
        for test_ref in descriptor.test_refs
    )


def test_catalog_generator_is_deterministic_with_business_definition_hashes():
    from backend.scripts.build_capability_catalog import current_release

    first = current_release()
    second = current_release()

    assert first.catalog_hash == second.catalog_hash


def test_catalog_hash_normalizes_derived_error_schema_from_domain_errors():
    descriptor = _descriptor("craft.routing.get").model_copy(update={
        "domain_errors": (DomainErrorContract(code="invalid_input", meaning="Invalid routing."),),
        "domain_errors_complete": True,
    })

    release = build_release([descriptor])

    assert release.descriptors[0].error_schema[0]["error_code"] == "invalid_input"


def test_complete_governance_metadata_does_not_synthesize_business_effect():
    descriptor = _descriptor("craft.routing.get").model_copy(update={
        "lifecycle_status": LifecycleStatus.STABLE,
    })

    completed = complete_governance_metadata(
        descriptor,
        provider_ref="craft.provider.routing",
        consumer_refs=("web.craft.routing",),
        api_refs=("gateway.capability.invoke",),
        test_refs=({"path": "backend/tests/test_craft_capability_contracts.py", "result": "declared"},),
    )

    assert completed.capability_version_gid.startswith("cv2_")
    assert completed.business_effect == ""
    assert completed.side_effects
    assert completed.transaction_policy["boundary"] == "provider"
    assert completed.provider_ref == "craft.provider.routing"
    assert completed.consumer_refs == ("web.craft.routing",)


def test_catalog_hash_binds_execution_budget():
    descriptor = _descriptor("craft.routing.get")
    paged = descriptor.model_copy(update={
        "execution_budget": ExecutionBudget(
            collection_policy="paged",
            max_page_size=100,
        ),
    })

    assert build_release([descriptor]).catalog_hash != build_release([paged]).catalog_hash


def test_catalog_rejects_new_stable_unbounded_collection_with_json_path():
    unbounded = _descriptor("craft.routing.search").model_copy(update={
        "lifecycle_status": LifecycleStatus.STABLE,
        "output_schema": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "object",
                    "properties": {
                        "items": {"type": "array", "items": {"type": "string"}},
                    },
                    "additionalProperties": False,
                },
            },
            "additionalProperties": False,
        },
    })

    with pytest.raises(ValueError, match=r"craft\.routing\.search@1.*output_schema\.data\.items"):
        build_release([unbounded], enforce_collection_boundaries=True)

    bounded_schema = unbounded.model_copy(update={
        "output_schema": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array", "maxItems": 100,
                            "items": {"type": "string"},
                        },
                    },
                    "additionalProperties": False,
                },
            },
            "additionalProperties": False,
        },
    })
    assert build_release(
        [bounded_schema], enforce_collection_boundaries=True,
    ).descriptor("craft.routing.search", 1)

    paged = unbounded.model_copy(update={
        "execution_budget": ExecutionBudget(collection_policy="paged", max_page_size=100),
    })
    artifact = unbounded.model_copy(update={
        "execution_budget": ExecutionBudget(collection_policy="artifact"),
    })
    assert build_release([paged], enforce_collection_boundaries=True).descriptor("craft.routing.search", 1)
    assert build_release([artifact], enforce_collection_boundaries=True).descriptor("craft.routing.search", 1)


def test_catalog_requires_explicit_grandfathering_for_existing_unbounded_stable_path():
    legacy = _descriptor("craft.routing.search").model_copy(update={
        "lifecycle_status": LifecycleStatus.STABLE,
        "output_schema": {
            "type": "object",
            "properties": {"items": {"type": "array", "items": {"type": "string"}}},
            "additionalProperties": False,
        },
    })

    release = build_release(
        [legacy],
        grandfathered_unbounded_paths={
            ("craft.routing.search", 1, "output_schema.items"),
        },
        enforce_collection_boundaries=True,
    )

    assert release.descriptor("craft.routing.search", 1) == legacy


def test_catalog_rejects_duplicate_capability_major_and_is_immutable():
    with pytest.raises(ValueError, match="duplicate descriptor"):
        build_release([_descriptor("craft.routing.get"), _descriptor("craft.routing.get")])

    release = build_release([_descriptor("craft.routing.get")])
    with pytest.raises(ValidationError, match="frozen"):
        release.descriptors[0].title = "mutated"


def test_catalog_deserialization_detects_descriptor_or_release_id_tampering():
    release = build_release([_descriptor("craft.routing.get")], [_provider()])
    tampered_descriptor = release.model_dump(mode="json")
    tampered_descriptor["descriptors"][0]["title"] = "Tampered"
    with pytest.raises(ValidationError, match="catalog_hash_mismatch"):
        type(release).model_validate(tampered_descriptor)

    tampered_id = release.model_dump(mode="json")
    tampered_id["release_id"] = "rel_" + "0" * 32
    with pytest.raises(ValidationError, match="release_id_mismatch"):
        type(release).model_validate(tampered_id)


def test_catalog_store_is_insert_only_even_for_identical_release():
    store = InMemoryCatalogStore()
    release = build_release([_descriptor("craft.routing.get")])

    store.publish(release)
    with pytest.raises(ValueError, match="catalog_release_exists"):
        store.publish(release)


def test_sql_catalog_store_round_trips_with_insert_and_select_only():
    release = build_release([_descriptor("craft.routing.get")], [_provider()])

    class Connection:
        def __init__(self, row=None):
            self.row = row
            self.statements = []
            self.committed = False

        def cursor(self):
            connection = self

            class Cursor:
                def __enter__(self): return self
                def __exit__(self, *_args): return False
                def execute(self, sql, params): connection.statements.append((sql, params))
                def fetchone(self): return connection.row

            return Cursor()

        def commit(self): self.committed = True
        def rollback(self): raise AssertionError("rollback was not expected")
        def close(self): pass

    write_connection = Connection()
    SqlCatalogStore(lambda: write_connection).publish(release)
    assert write_connection.committed
    assert write_connection.statements[0][0].lstrip().upper().startswith("INSERT")

    row = {
        "release_id": release.release_id,
        "catalog_hash": release.catalog_hash,
        "descriptors_json": json.dumps([item.model_dump(mode="json") for item in release.descriptors]),
        "provider_artifacts_json": json.dumps([item.model_dump(mode="json") for item in release.provider_artifacts]),
        "created_at": release.created_at,
    }
    read_connection = Connection(row)
    restored = SqlCatalogStore(lambda: read_connection).get(release.release_id)
    assert restored == release
    assert read_connection.statements[0][0].lstrip().upper().startswith("SELECT")
    assert not hasattr(SqlCatalogStore, "update")
    assert not hasattr(SqlCatalogStore, "delete")


def test_compatibility_scanner_blocks_stable_removal_and_same_major_contract_change():
    stable = _descriptor("craft.routing.get").model_copy(update={"lifecycle_status": LifecycleStatus.STABLE})
    previous = build_release([stable])
    changed = stable.model_copy(update={"schema_hash": "sha256:" + "f" * 64})

    assert compatibility_errors(previous, build_release([])) == [
        "stable capability removed: craft.routing.get@1"
    ]
    assert compatibility_errors(previous, build_release([changed])) == [
        "stable capability schema changed without major version bump: craft.routing.get@1"
    ]
    assert compatibility_errors(previous, build_release([stable, _descriptor("craft.routing.get", 2)])) == []


def test_compatibility_scanner_binds_agent_projection_schema_to_stable_major():
    stable = _descriptor("craft.routing.get").model_copy(update={
        "lifecycle_status": LifecycleStatus.STABLE,
        "exposure": ExposurePolicy(web=True, api=True, agent=True),
        "agent_output_schema": {
            "type": "object", "properties": {}, "additionalProperties": False,
        },
    })
    changed = stable.model_copy(update={
        "agent_output_schema": {
            "type": "object",
            "properties": {"new_field": {"type": "string"}},
            "additionalProperties": False,
        }
    })

    assert compatibility_errors(build_release([stable]), build_release([changed])) == [
        "stable capability agent projection changed without major version bump: craft.routing.get@1"
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("authorization_policy", "craft.routing.admin"),
        ("confirmation_policy", "admin"),
        ("idempotency_policy", "required"),
        ("consistency_policy", "eventual"),
        ("transaction_policy", {"requires_transaction": True, "participants": ["craft"]}),
        ("evidence_policy", "required"),
        ("audit_policy", "high_risk"),
        ("required_auth_freshness_seconds", 300),
    ],
)
def test_compatibility_scanner_blocks_policy_changes_without_major_bump(field, value):
    stable = _descriptor("craft.routing.get").model_copy(update={
        "lifecycle_status": LifecycleStatus.STABLE,
    })
    changed = stable.model_copy(update={field: value})

    errors = compatibility_errors(build_release([stable]), build_release([changed]))

    assert errors == [
        f"stable capability {field} changed without major version bump: craft.routing.get@1"
    ]


def test_compatibility_scanner_freezes_stable_execution_budget():
    stable = _descriptor("craft.routing.get").model_copy(update={
        "lifecycle_status": LifecycleStatus.STABLE,
    })
    changed = stable.model_copy(update={
        "execution_budget": ExecutionBudget(max_output_bytes=512 * 1024),
    })

    assert compatibility_errors(build_release([stable]), build_release([changed])) == [
        "stable capability execution budget changed without major version bump: craft.routing.get@1"
    ]


def test_resolve_requires_release_and_pinned_major_without_latest_fallback():
    registry = CapabilityRegistry()
    registry.register(
        CapabilitySpec(id="craft.routing.get", version=1, owner="craft"),
        lambda payload, context: payload,
    )
    registry.register(
        CapabilitySpec(id="craft.routing.get", version=2, owner="craft"),
        lambda payload, context: payload,
    )
    store = InMemoryCatalogStore()
    release = build_release([_descriptor("craft.routing.get", 1)])
    store.publish(release)
    resolver = CatalogResolver(store, registry)

    with pytest.raises(CatalogResolutionError, match="major_version_required"):
        resolver.resolve(release.release_id, "craft.routing.get", None)
    with pytest.raises(CatalogResolutionError, match="catalog_release_not_found"):
        resolver.resolve("missing", "craft.routing.get", 1)
    with pytest.raises(CatalogResolutionError, match="capability_not_in_release"):
        resolver.resolve(release.release_id, "craft.routing.get", 2)
    assert resolver.resolve(release.release_id, "craft.routing.get", 1).spec.version == 1


def test_resolver_rejects_release_provider_artifact_without_runtime_binding():
    registry = CapabilityRegistry()
    registry.register(
        CapabilitySpec(id="craft.routing.get", version=1, owner="craft"),
        lambda payload, context: payload,
    )
    release = build_release([_descriptor("craft.routing.get", 1)], [_provider()])
    store = InMemoryCatalogStore()
    store.publish(release)

    with pytest.raises(CatalogResolutionError, match="provider_artifact_unbound"):
        CatalogResolver(store, registry).resolve(release.release_id, "craft.routing.get", 1)


def test_resolver_rejects_runtime_provider_artifact_drift():
    registry = CapabilityRegistry()
    registry.register(
        CapabilitySpec(id="craft.routing.get", version=1, owner="craft"),
        lambda payload, context: payload,
    )
    registry.bind_provider_artifact(
        "craft",
        ProviderArtifact(
            plugin_id="official.craft",
            module="craft_backend.capabilities",
            version="1.0.0",
            artifact_hash="sha256:" + "b" * 64,
        ),
    )
    release = build_release([_descriptor("craft.routing.get", 1)], [_provider()])
    store = InMemoryCatalogStore()
    store.publish(release)

    with pytest.raises(CatalogResolutionError, match="provider_artifact_mismatch"):
        CatalogResolver(store, registry).resolve(release.release_id, "craft.routing.get", 1)


def test_official_provider_requires_exact_frozen_release_allowlist():
    provider = _provider()
    root = Path(__file__).resolve().parents[2]
    loader = PluginLoader(root / "missing-packages", root / "missing-plugins", provider_artifacts=[provider])

    with pytest.raises(ProviderTrustError, match="provider_not_in_release"):
        loader.authorize_capability_provider(
            "official.lookalike",
            module="craft_backend.capabilities",
            version="1.0.0",
            artifact_hash="sha256:" + "a" * 64,
        )
    with pytest.raises(ProviderTrustError, match="provider_artifact_mismatch"):
        loader.authorize_capability_provider(
            "official.craft",
            module="craft_backend.capabilities",
            version="1.0.0",
            artifact_hash="sha256:" + "0" * 64,
        )
    assert loader.authorize_capability_provider(
        "official.craft",
        module="craft_backend.capabilities",
        version="1.0.0",
        artifact_hash="sha256:" + "a" * 64,
    ) == provider


def test_checked_in_official_domain_hashes_match_exact_source_artifacts():
    root = Path(__file__).resolve().parents[2]
    document = json.loads(
        (root / "backend" / "capability_v2" / "official_domains.json").read_text(encoding="utf-8")
    )
    for domain in document["domains"]:
        assert domain["artifact"]["artifact_hash"] == hash_domain_artifact(
            root,
            domain["artifact_path"],
        )
