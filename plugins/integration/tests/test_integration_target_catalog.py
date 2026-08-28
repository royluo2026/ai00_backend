from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.capability_v2.catalog import CatalogResolver, build_release
from backend.capability_v2.catalog_lineage import CatalogLineage
from backend.capability_v2.catalog_store import InMemoryCatalogStore
from plugins.integration.tests.test_integration_mapping_commands import (
    bound_mapping_payload,
)
from plugins.integration.tests.test_integration_owner_services import (
    CONTEXT,
    MemoryRepository,
    _seed_connector_and_mapping,
    app,
)


TARGET_ID = "knowledge.reference_dataset.publish"
TARGET_CONTRACT = "knowledge.reference_dataset.publish.v1"


class Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.selected = []
        self.last = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        self.selected.append((sql, params))
        actor_gid, team_gid = params[-2:]
        eligible = [
            row for row in self.rows
            if row["owner_gid"] == actor_gid and row["team_gid"] == team_gid
        ]
        if "binding_id=%s" in sql:
            eligible = [row for row in eligible if row["binding_id"] == params[0]]
        else:
            requested = set(params[:-2])
            eligible = [row for row in eligible if row["ontology_object_gid"] in requested]
        self.last = eligible

    def fetchone(self):
        return self.last[0] if self.last else None

    def fetchall(self):
        return self.last


class Connection:
    def __init__(self, rows):
        self.cursor_value = Cursor(rows)

    def cursor(self):
        return self.cursor_value


class _UnavailableProviderRegistry:
    def get(self, *_args, **_kwargs):
        raise KeyError("provider_resolution_unavailable")


def _target_descriptor():
    from backend.capability_v2.catalog import CatalogRelease

    release = CatalogRelease.model_validate_json(
        Path("docs/governance/capability-catalog-release.json").read_text(encoding="utf-8")
    )
    return release.descriptor(TARGET_ID, 1)


def _release_context(*, add_unrelated: bool = False):
    registry = _UnavailableProviderRegistry()
    target = _target_descriptor()
    descriptors = [target]
    if add_unrelated:
        descriptors.append(target.model_copy(update={
            "id": "knowledge.unrelated.read", "title": "knowledge.unrelated.read",
            "capability_version_gid": None,
        }))
    release = build_release(descriptors, created_at=datetime(2026, 8, 29, tzinfo=UTC))
    return registry, release


def _resolver_and_lineage(*releases, registry=None):
    registry = registry or _UnavailableProviderRegistry()
    store = InMemoryCatalogStore()
    for release in releases:
        store.publish(release)
    return CatalogResolver(store, registry), CatalogLineage.from_releases(releases)


def _binding(release_id, owner_gid="actor-1", team_gid="team-1", **changes):
    value = {
        "binding_id": "ontology:concept-part",
        "ontology_object_gid": "concept-part",
        "target_domain": "knowledge",
        "target_capability_id": TARGET_ID,
        "target_major_version": 1,
        "minimum_catalog_release": release_id,
        "input_contract": TARGET_CONTRACT,
        "resource_gid": "dataset-parts",
        "expected_version": 7,
        "owner_gid": owner_gid,
        "team_gid": team_gid,
    }
    value.update(changes)
    return value


def _production_catalog(rows, *, active_release, resolver, lineage):
    from plugins.integration.integration_backend.infrastructure.target_catalog import (
        IntegrationTargetCatalog,
    )

    connection = Connection(rows)

    @contextmanager
    def connect():
        yield connection

    return IntegrationTargetCatalog(
        connect,
        catalog_resolver=resolver,
        active_release_id=active_release.release_id,
        release_lineage=lineage,
    ), connection


def test_production_target_catalog_uses_real_catalog_resolver_and_scopes_seeded_binding():
    registry, release = _release_context()
    resolver, lineage = _resolver_and_lineage(release, registry=registry)
    rows = [_binding(release.release_id), _binding(release.release_id, "actor-2", "team-2")]
    catalog, connection = _production_catalog(
        rows, active_release=release, resolver=resolver, lineage=lineage
    )

    projected = catalog.project_mapping_targets_for_ontology_objects(
        ("concept-part",), actor_gid="actor-1", team_gid="team-1"
    )
    assert projected == [{
        key: value for key, value in _binding(release.release_id).items()
        if key not in {"owner_gid", "team_gid"}
    }]
    assert catalog.resolve_mapping_target(
        "ontology:concept-part", actor_gid="actor-2", team_gid="team-1"
    ) is None
    catalog.require_stable(TARGET_ID, 1, release.release_id)
    assert "owner_gid=%s AND team_gid=%s" in connection.cursor_value.selected[0][0]


def test_production_catalog_composes_with_application_projection_create_and_import_reauthorization():
    registry, release = _release_context()
    resolver, lineage = _resolver_and_lineage(release, registry=registry)
    catalog, _connection = _production_catalog(
        [_binding(release.release_id)], active_release=release,
        resolver=resolver, lineage=lineage,
    )
    repository = MemoryRepository()
    _seed_connector_and_mapping(repository)
    repository.mappings.clear()
    repository.field_mappings.clear()
    application = app(repository, catalog=catalog)

    projection = asyncio.run(application.invoke(
        "integration.mapping_target.search",
        {"ontology_object_gids": ["concept-part"]},
        CONTEXT,
    ))
    created = asyncio.run(application.invoke(
        "integration.mapping.create", bound_mapping_payload(), CONTEXT,
    ))
    started = asyncio.run(application.invoke(
        "integration.mapping.import.start",
        {"mapping_gid": created["gid"], "idempotency_key": "import-production-catalog-1"},
        CONTEXT,
    ))

    assert projection["items"][0]["target_capability_id"] == TARGET_ID
    assert created["target_capability_id"] == TARGET_ID
    run = next(item for item in repository.imports if item["run_id"] == started["run_id"])
    assert run["target_invocation"]["capability_id"] == TARGET_ID
    assert run["target_invocation"]["payload"] == {
        "dataset_gid": "dataset-parts",
        "expected_version": 7,
        "schema": {"fields": [{"name": "code", "source_field": "part_no"}]},
        "rows": [],
    }


def test_minimum_release_is_a_compatible_floor_not_exact_current_equality():
    registry, older = _release_context()
    target = _target_descriptor()
    unrelated = target.model_copy(update={
        "id": "knowledge.unrelated.read", "title": "knowledge.unrelated.read",
        "capability_version_gid": None,
    })
    newer = build_release(
        [target, unrelated],
        created_at=datetime(2026, 8, 30, tzinfo=UTC),
    )
    resolver, lineage = _resolver_and_lineage(older, newer, registry=registry)
    catalog, _connection = _production_catalog(
        [_binding(older.release_id)], active_release=newer,
        resolver=resolver, lineage=lineage,
    )

    assert catalog.resolve_mapping_target(
        "ontology:concept-part", actor_gid="actor-1", team_gid="team-1"
    )["minimum_catalog_release"] == older.release_id

    old_resolver, old_lineage = _resolver_and_lineage(older, newer, registry=registry)
    old_catalog, _ = _production_catalog(
        [_binding(newer.release_id)], active_release=older,
        resolver=old_resolver, lineage=old_lineage,
    )
    with pytest.raises(ValueError, match="catalog_release_floor_not_met"):
        old_catalog.resolve_mapping_target(
            "ontology:concept-part", actor_gid="actor-1", team_gid="team-1"
        )


def test_incompatible_or_bogus_target_binding_is_never_projected():
    registry, release = _release_context()
    resolver, lineage = _resolver_and_lineage(release, registry=registry)
    bogus = _binding(
        release.release_id,
        target_capability_id="knowledge.reference_data.change.apply",
    )
    catalog, _connection = _production_catalog(
        [bogus], active_release=release, resolver=resolver, lineage=lineage,
    )

    with pytest.raises(ValueError, match="target_binding_incompatible"):
        catalog.project_mapping_targets_for_ontology_objects(
            ("concept-part",), actor_gid="actor-1", team_gid="team-1"
        )


def test_production_target_catalog_fails_closed_without_authenticated_scope():
    registry, release = _release_context()
    resolver, lineage = _resolver_and_lineage(release, registry=registry)
    catalog, _connection = _production_catalog(
        [_binding(release.release_id)], active_release=release,
        resolver=resolver, lineage=lineage,
    )

    with pytest.raises(ValueError, match="authenticated_scope_required"):
        catalog.resolve_mapping_target(
            "ontology:concept-part", actor_gid="", team_gid="team-1"
        )


def test_target_binding_migration_is_integration_owned_and_tenant_scoped():
    sql = Path(
        "backend/db/migrations/domains/integration/0004_integration_target_catalog.sql"
    ).read_text(encoding="utf-8").casefold()
    assert "workmanship_int_mapping_target_bindings" in sql
    assert "owner_gid" in sql and "team_gid" in sql
    assert "unique key" in sql and "binding_id" in sql
    assert "password" not in sql and "credential" not in sql and "filter_sql" not in sql


def test_production_factory_supplies_catalog_and_fails_closed_for_unconfigured_external_ports():
    from plugins.integration.integration_backend.infrastructure.production_adapters import build

    adapters = build()
    assert adapters.catalog.__class__.__name__ == "IntegrationTargetCatalog"
    with pytest.raises(RuntimeError, match="credential_enrollment_unavailable"):
        adapters.credential_enrollment.consume("handle", "actor", "team")
