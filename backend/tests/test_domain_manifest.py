from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.capability_v2.domain_manifest import load_domain_manifests


def _manifest_document() -> dict[str, object]:
    return {
        "schema_version": 1,
        "domains": [
            {
                "domain_id": "craft",
                "artifact": {
                    "plugin_id": "official.craft",
                    "module": "craft_backend.capabilities",
                    "version": "1.2.0",
                    "artifact_hash": f"sha256:{'a' * 64}",
                },
                "artifact_path": "plugins/craft/craft_backend",
                "allowed_owners": ["craft"],
                "database": {
                    "database_name": "ai00_craft",
                    "runtime_url_env": "AI00_CRAFT_DB_URL",
                    "ddl_url_env": "AI00_CRAFT_DDL_DB_URL",
                    "migration_path": "backend/db/migrations/domains/craft",
                },
                "search_export": {
                    "capability_id": "craft.object.search",
                    "major_version": 1,
                },
                "event_subscriptions": [
                    {
                        "subscription_id": "craft.factory_asset_events",
                        "producer_domain": "factory",
                        "event_type": "factory.asset.scrapped",
                        "min_version": 1,
                        "max_version": 2,
                    }
                ],
            }
        ],
    }


def _write_manifest(tmp_path: Path, document: dict[str, object]) -> Path:
    path = tmp_path / "domains.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_loads_explicit_domain_contract(tmp_path: Path) -> None:
    manifests = load_domain_manifests(_write_manifest(tmp_path, _manifest_document()))

    craft = manifests.require("craft")
    assert craft.artifact.plugin_id == "official.craft"
    assert craft.database.runtime_url_env == "AI00_CRAFT_DB_URL"
    assert craft.database.ddl_url_env == "AI00_CRAFT_DDL_DB_URL"
    assert craft.search_export is not None
    assert craft.search_export.capability_id == "craft.object.search"
    assert craft.event_subscriptions[0].event_type == "factory.asset.scrapped"


def test_rejects_duplicate_database_names(tmp_path: Path) -> None:
    document = _manifest_document()
    duplicate = copy.deepcopy(document["domains"][0])
    duplicate["domain_id"] = "factory"
    duplicate["artifact"]["plugin_id"] = "official.factory"
    duplicate["artifact"]["module"] = "factory_backend.capabilities"
    duplicate["artifact_path"] = "plugins/factory/factory_backend"
    duplicate["allowed_owners"] = ["factory"]
    document["domains"].append(duplicate)

    with pytest.raises(ValidationError, match="duplicate database_name: ai00_craft"):
        load_domain_manifests(_write_manifest(tmp_path, document))


def test_rejects_repository_path_escape(tmp_path: Path) -> None:
    document = _manifest_document()
    document["domains"][0]["artifact_path"] = "../outside"

    with pytest.raises(ValidationError, match="repository-relative POSIX path"):
        load_domain_manifests(_write_manifest(tmp_path, document))


def test_rejects_inverted_event_version_range(tmp_path: Path) -> None:
    document = _manifest_document()
    subscription = document["domains"][0]["event_subscriptions"][0]
    subscription["min_version"] = 3
    subscription["max_version"] = 2

    with pytest.raises(ValidationError, match="min_version must not exceed max_version"):
        load_domain_manifests(_write_manifest(tmp_path, document))


def test_rejects_duplicate_subscription_ids(tmp_path: Path) -> None:
    document = _manifest_document()
    subscriptions = document["domains"][0]["event_subscriptions"]
    subscriptions.append(copy.deepcopy(subscriptions[0]))

    with pytest.raises(ValidationError, match="duplicate subscription_id"):
        load_domain_manifests(_write_manifest(tmp_path, document))
