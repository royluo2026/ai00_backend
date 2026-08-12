from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from backend.capability_v2.provider_contracts import CapabilityContext
from backend.capability_v2.v1_adapter import adapt_v1_spec
from plugins.project_management.project_management_backend.capabilities import (
    register_capabilities,
)
from plugins.project_management.project_management_backend.capabilities.projects import (
    register_project_capabilities,
    search_projects,
)
from plugins.project_management.project_management_backend.data.connection import _params


CONTEXT = CapabilityContext(user_gid="user-1", team_gid="team-1")
ROOT = Path(__file__).resolve().parents[3]


class Registry:
    def register(self, spec, handler, *, descriptor=None):
        self.spec = spec
        self.handler = handler
        self.descriptor = descriptor


class SnapshotRegistry:
    def __init__(self):
        self.items = []

    def register(self, spec, handler, *, descriptor=None):
        self.items.append((spec, handler, descriptor))


def _frozen_project_capability_ids() -> set[str]:
    review = json.loads(
        (ROOT / "docs/governance/capability-coverage-review/project-management.json")
        .read_text(encoding="utf-8")
    )
    return set(review["capabilities"])


def test_project_provider_is_complete_against_frozen_review():
    registry = SnapshotRegistry()
    register_capabilities(registry)
    actual = {descriptor.id for _, _, descriptor in registry.items}

    assert actual == _frozen_project_capability_ids()


def test_all_project_capabilities_have_native_stable_contracts():
    registry = SnapshotRegistry()
    register_capabilities(registry)

    for spec, _, descriptor in registry.items:
        assert descriptor is not None, spec.id
        assert descriptor.owner_domain == "project_management"
        assert descriptor.lifecycle_status == "stable"
        assert descriptor.exposure.agent is True
        assert descriptor.exposure.plugin is True
        assert descriptor.domain_errors_complete is True
        assert descriptor.domain_errors


def test_project_database_never_falls_back_to_base_credentials(monkeypatch):
    monkeypatch.delenv("AI00_PROJECT_MANAGEMENT_DB_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "mysql://base:secret@db/base")

    with pytest.raises(RuntimeError, match="AI00_PROJECT_MANAGEMENT_DB_URL"):
        _params()


def test_project_search_returns_only_stable_refs():
    fake_repository = Mock()
    fake_repository.search.return_value = [
        {"gid": "p1", "name": "Alpha", "project_code": "A-1", "status": "active"}
    ]
    with patch(
        "plugins.project_management.project_management_backend.capabilities.projects.repository",
        fake_repository,
    ):
        result = search_projects({"query": "Alpha", "limit": 10}, CONTEXT)

    assert result.data == {
        "items": [{
            "object_ref": "project:p1",
            "title": "Alpha",
            "summary": "active",
            "match_reason": "name_or_code",
            "owner": "project_management",
        }],
        "total": 1,
        "query": "Alpha",
    }
    fake_repository.search.assert_called_once_with("Alpha", 10, CONTEXT)


def test_project_search_descriptor_is_project_owned_and_automation_ready():
    registry = Registry()
    register_project_capabilities(registry)
    descriptor = registry.descriptor or adapt_v1_spec(registry.spec)

    assert descriptor.owner_domain == "project_management"
    assert descriptor.exposure.plugin is True
    assert descriptor.exposure.agent is True
    assert descriptor.output_schema["properties"]
