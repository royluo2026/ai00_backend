from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest

from plugins.device.device_backend.capabilities import register_capabilities
from plugins.device.device_backend.data.connection import _params
from plugins.device.device_backend.domain.replay import ReplayDetected, ReplayGuard


ROOT = Path(__file__).parents[3]


def test_device_has_one_owner_and_independent_database():
    document = json.loads((ROOT / "backend/capability_v2/official_domains.json").read_text(encoding="utf-8"))
    domain = next(item for item in document["domains"] if item["domain_id"] == "device")
    assert domain["allowed_owners"] == ["device"]
    assert domain["database"]["database_name"] == "ai00_device"
    assert domain["database"]["migration_path"] == "backend/db/migrations/domains/device"


def test_provider_descriptors_use_only_device_owner():
    class Registry:
        def __init__(self): self.items = []
        def register(self, spec, handler, *, descriptor=None): self.items.append(descriptor)

    registry = Registry(); register_capabilities(registry)
    assert registry.items
    assert {descriptor.owner_domain for descriptor in registry.items} == {"device"}


def test_device_requires_independent_database(monkeypatch):
    monkeypatch.delenv("AI00_LOCAL_RUNTIME_DB_URL", raising=False)
    monkeypatch.delenv("AI00_DEVICE_DB_URL", raising=False)
    with pytest.raises(RuntimeError, match="AI00_DEVICE_DB_URL is required"):
        _params()


def test_local_runtime_database_url_is_a_deprecated_alias(monkeypatch):
    monkeypatch.delenv("AI00_DEVICE_DB_URL", raising=False)
    monkeypatch.setenv("AI00_LOCAL_RUNTIME_DB_URL", "mysql://device:secret@localhost/ai00_device")
    with pytest.warns(DeprecationWarning, match="AI00_LOCAL_RUNTIME_DB_URL"):
        assert _params()["database"] == "ai00_device"


def test_replayed_or_expired_local_operation_is_rejected():
    now = datetime.now(UTC)
    guard = ReplayGuard()
    guard.accept("operation-1", expires_at=now + timedelta(minutes=1), now=now)
    with pytest.raises(ReplayDetected):
        guard.accept("operation-1", expires_at=now + timedelta(minutes=1), now=now)
    with pytest.raises(ValueError, match="expired"):
        guard.accept("operation-2", expires_at=now - timedelta(seconds=1), now=now)


def test_independent_migration_owns_only_device_runtime_tables():
    sql = (ROOT / "backend/db/migrations/domains/device/0001_device.sql").read_text(encoding="utf-8")
    assert "workmanship_runtime_devices" in sql
    assert "workmanship_runtime_commands" in sql
    assert "workmanship_base_" not in sql
