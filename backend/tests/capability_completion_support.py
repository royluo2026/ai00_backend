"""Shared test support for domain-completion slices."""
from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.capabilities.registry_next import CapabilityRegistry


DOMAIN_REVIEW_FILES = {
    "agent": "agent.json",
    "base": "base-platform.json",
    "craft": "craft.json",
    "digital_model": "digital-model.json",
    "factory": "factory.json",
    "integration": "integration.json",
    "knowledge": "knowledge.json",
    "device": "local-runtime.json",
    "ontology": "ontology.json",
    "project_management": "project-management.json",
    "simulation": "simulation.json",
}


@dataclass(frozen=True)
class FrozenCoverageReview:
    root: Path

    def capability_ids(self, owner: str) -> frozenset[str]:
        document = self._document(owner)
        supplement = document.get("official_provider_capabilities", {})
        return frozenset(document.get("capabilities", {})) | frozenset(supplement.get("capability_ids", ()))

    def catalog_capability_ids(self, owner: str) -> frozenset[str]:
        return frozenset(self._document(owner).get("capabilities", {}))

    def _document(self, owner: str) -> dict[str, Any]:
        filename = DOMAIN_REVIEW_FILES[owner]
        path = (
            self.root
            / "docs/governance/capability-coverage-review"
            / filename
        )
        return json.loads(path.read_text(encoding="utf-8"))


def registered_descriptor_ids(module_name: str) -> set[str]:
    registry = CapabilityRegistry()
    module = importlib.import_module(module_name)
    module.register_capabilities(registry)
    return {
        item.descriptor.id
        for item in registry.snapshot()
        if item.descriptor is not None
    }


def assert_database_denied(connection: Any, sql: str) -> None:
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql)
    except Exception as exc:
        code = exc.args[0] if getattr(exc, "args", ()) else None
        if code in {1044, 1045, 1142, 1227}:
            return
        raise AssertionError(f"database operation failed for non-permission reason: {code}") from exc
    raise AssertionError("cross-domain database operation was not denied")
