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
    compatibility_errors,
)
from backend.capability_v2.catalog_store import InMemoryCatalogStore, SqlCatalogStore
from backend.capability_v2.contracts import (
    AutomationLevel,
    CapabilityDescriptorV2,
    ExposurePolicy,
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
