from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import jsonschema
import pytest

from backend.capability_v2.catalog_targets import CatalogTargetIndex
from backend.scripts.repair_legacy_route_targets import (
    MappingConfigurationError,
    load_mapping_families,
    repair_inventory,
)


ROOT = Path(__file__).resolve().parents[2]
MAPPING_PATH = ROOT / "docs/governance/legacy-route-target-mappings.json"
SCHEMA_PATH = ROOT / "docs/governance/legacy-route-target-mappings.schema.json"
INVENTORY_PATH = ROOT / "docs/governance/legacy_route_inventory.json"
CATALOG_PATH = ROOT / "docs/capabilities/catalog.v2.json"
EXPECTED_FAMILIES = {
    "craft-manufacturing-resource-change": ("craft.manufacturing_resource.change.apply", 1, 37),
    "craft-manufacturing-resource-read": ("craft.manufacturing_resource.read", 1, 11),
    "craft-gbop-change": ("craft.gbop.change.apply", 1, 24),
    "craft-gbop-read": ("craft.gbop.read", 1, 8),
    "project-craft-scope-read": ("project.craft_scope.read", 1, 1),
}
EXPECTED_COUNTS = {source_id: count for source_id, _version, count in EXPECTED_FAMILIES.values()}


def _document(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, document: object) -> None:
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")


def _catalog_index(catalog: dict[str, object] | None = None) -> CatalogTargetIndex:
    return CatalogTargetIndex.from_catalog(catalog or _document(CATALOG_PATH))


def test_mapping_file_matches_schema_and_contains_five_complete_families() -> None:
    jsonschema.Draft202012Validator(_document(SCHEMA_PATH)).validate(_document(MAPPING_PATH))

    families = load_mapping_families(MAPPING_PATH)

    assert {
        family.family_id: (
            family.source_capability_id,
            family.source_major_version,
            len(family.routes),
        )
        for family in families
    } == EXPECTED_FAMILIES


def test_mapping_loader_rejects_wrong_source_major_version(tmp_path: Path) -> None:
    document = _document(MAPPING_PATH)
    document["mapping_families"][0]["source_major_version"] = 2
    path = tmp_path / "wrong-major.json"
    _write(path, document)

    with pytest.raises(MappingConfigurationError, match="unexpected_mapping_family"):
        load_mapping_families(path)


def test_mapping_loader_rejects_arbitrary_family_id(tmp_path: Path) -> None:
    document = _document(MAPPING_PATH)
    document["mapping_families"][0]["family_id"] = "arbitrary-family"
    path = tmp_path / "wrong-family.json"
    _write(path, document)

    with pytest.raises(MappingConfigurationError, match="unexpected_mapping_family"):
        load_mapping_families(path)


def test_mapping_loader_rejects_duplicate_normalized_route_keys(tmp_path: Path) -> None:
    document = _document(MAPPING_PATH)
    duplicate = copy.deepcopy(document["mapping_families"][0]["routes"][0])
    duplicate["route_pattern"] = "/api/bop/factories/{different_name}"
    document["mapping_families"][0]["routes"].append(duplicate)
    path = tmp_path / "duplicate.json"
    _write(path, document)

    with pytest.raises(MappingConfigurationError, match="duplicate route mapping"):
        load_mapping_families(path)


def test_repair_rejects_deprecated_replacement() -> None:
    catalog = _document(CATALOG_PATH)
    target = next(
        entry for entry in catalog["capabilities"]
        if entry["id"] == "factory.structure.archive" and entry.get("major_version", 1) == 1
    )
    target["lifecycle_status"] = "deprecated"

    with pytest.raises(MappingConfigurationError, match="target_not_stable") as captured:
        repair_inventory(
            _document(INVENTORY_PATH),
            load_mapping_families(MAPPING_PATH),
            _catalog_index(catalog),
        )

    assert captured.value.failure.serialized() == {
        "reason_code": "target_not_stable",
        "family_id": "craft-manufacturing-resource-change",
        "source_capability_id": "craft.manufacturing_resource.change.apply",
        "source_major_version": 1,
        "method": "DELETE",
        "route_pattern": "/api/bop/factories/{}",
        "target_capability_id": "factory.structure.archive",
        "target_major_version": 1,
    }


def test_repair_rejects_cross_owner_replacement(tmp_path: Path) -> None:
    document = _document(MAPPING_PATH)
    document["mapping_families"][0]["routes"][0]["owner"] = "craft"
    path = tmp_path / "cross-owner.json"
    _write(path, document)

    with pytest.raises(MappingConfigurationError, match="target_owner_mismatch"):
        repair_inventory(
            _document(INVENTORY_PATH),
            load_mapping_families(path),
            _catalog_index(),
        )


def test_repair_updates_all_authoritative_rows_and_reports_unmatched() -> None:
    inventory = _document(INVENTORY_PATH)
    families = load_mapping_families(MAPPING_PATH)
    source_by_route = {
        (route.route_method, route.route_pattern): family.source_capability_id
        for family in families
        for route in family.routes
    }
    for entry in inventory["entries"]:
        key = (
            entry["method"].upper(),
            re.sub(r"\{[^/{}]+\}", "{}", entry["route_path"].rstrip("/")),
        )
        if key in source_by_route:
            entry["migration_target_capability"] = source_by_route[key]
            entry.pop("migration_target_major_version", None)

    result = repair_inventory(inventory, families, _catalog_index())

    assert result.updated == 81
    assert result.unchanged == 0
    assert result.unmatched == ()
    assert dict(result.counts_by_source) == EXPECTED_COUNTS
    repaired_by_route = {
        (
            entry["method"].upper(),
            re.sub(r"\{[^/{}]+\}", "{}", entry["route_path"].rstrip("/")),
        ): entry
        for entry in inventory["entries"]
        if (
            entry["method"].upper(),
            re.sub(r"\{[^/{}]+\}", "{}", entry["route_path"].rstrip("/")),
        ) in source_by_route
    }
    assert len(repaired_by_route) == 81
    for family in families:
        for route in family.routes:
            entry = repaired_by_route[(route.route_method, route.route_pattern)]
            assert (
                entry["migration_target_capability"],
                entry["migration_target_major_version"],
                entry["owner"],
            ) == (
                route.target_capability_id,
                route.target_major_version,
                route.owner,
            )


def test_repair_reports_source_row_without_mapping() -> None:
    inventory = _document(INVENTORY_PATH)
    families = load_mapping_families(MAPPING_PATH)
    family = next(
        item for item in families if item.source_capability_id == "craft.gbop.read"
    )
    mapped_route = family.routes[0]
    row = next(
        entry for entry in inventory["entries"]
        if entry["method"] == mapped_route.route_method
        and re.sub(r"\{[^/{}]+\}", "{}", entry["route_path"].rstrip("/"))
        == mapped_route.route_pattern
    )
    row["migration_target_capability"] = family.source_capability_id
    row["route_path"] = "/api/gbop/unreviewed"

    result = repair_inventory(inventory, families, _catalog_index())

    assert [failure.serialized() for failure in result.unmatched] == [
        {
            "reason_code": "inventory_route_missing",
            "family_id": "craft-gbop-read",
            "source_capability_id": "craft.gbop.read",
            "source_major_version": 1,
            "method": "GET",
            "route_pattern": "/api/gbop/entries/{}/links",
        },
        {
            "reason_code": "source_route_unmapped",
            "family_id": "craft-gbop-read",
            "source_capability_id": "craft.gbop.read",
            "source_major_version": 1,
            "method": "GET",
            "route_pattern": "/api/gbop/unreviewed",
        },
    ]
    assert json.loads(str(result.unmatched[1])) == result.unmatched[1].serialized()


def test_members_matrix_is_not_falsely_registered_as_legacy_member_list() -> None:
    inventory = _document(INVENTORY_PATH)

    assert not any(
        entry["method"] == "GET"
        and entry["route_path"] == "/api/projects/members/matrix"
        for entry in inventory["entries"]
    )
