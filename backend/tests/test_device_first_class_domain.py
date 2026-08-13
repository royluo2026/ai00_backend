from pathlib import Path

import pytest

from backend.capability_v2.contracts import ConsumerType, ExposurePolicy
from backend.capability_v2.domain_manifest import load_domain_manifests
from backend.governance import load_registry
from plugins.device.device_backend.data.connection import _params


ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_DOMAINS = ROOT / "backend/capability_v2/official_domains.json"


def test_device_replaces_local_runtime_as_first_class_domain() -> None:
    manifests = load_domain_manifests(OFFICIAL_DOMAINS)

    assert {item.domain_id for item in manifests.domains} == {
        "agent",
        "base",
        "craft",
        "device",
        "digital_model",
        "factory",
        "integration",
        "knowledge",
        "ontology",
        "project_management",
        "simulation",
    }
    device = manifests.require("device")
    assert device.artifact.plugin_id == "official.device"
    assert device.artifact_path == "plugins/device/device_backend"
    assert device.database.database_name == "ai00_device"
    assert device.database.migration_path == "backend/db/migrations/domains/device"
    with pytest.raises(KeyError):
        manifests.require("local_runtime")


def test_local_runtime_remains_a_device_component_not_a_data_owner() -> None:
    registry = load_registry()

    assert "device" in registry.product_domains
    assert "local_runtime" not in registry.product_domains
    assert registry.source_domain("plugins/device/device_backend/control_plane.py") == "device"
    ownership = registry.table_owner("workmanship_runtime_devices")
    assert ownership is not None
    assert ownership.owner == "device"
    assert ownership.runtime_domain == "device"

    policy = ExposurePolicy(local_runtime=True)
    assert policy.allows(ConsumerType.LOCAL_RUNTIME) is True


def test_device_database_url_is_primary_and_local_runtime_url_is_temporary_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "AI00_DEVICE_DB_URL",
        "mysql://device:device-secret@db.example:2881/ai00_device",
    )
    monkeypatch.delenv("AI00_LOCAL_RUNTIME_DB_URL", raising=False)
    assert _params()["database"] == "ai00_device"

    monkeypatch.delenv("AI00_DEVICE_DB_URL")
    monkeypatch.setenv(
        "AI00_LOCAL_RUNTIME_DB_URL",
        "mysql://legacy:legacy-secret@db.example:2881/ai00_device",
    )
    with pytest.warns(DeprecationWarning, match="AI00_LOCAL_RUNTIME_DB_URL"):
        assert _params()["user"] == "legacy"
