"""Acceptance tests for the independently deployable Digital Model domain."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from backend.capabilities.registry_next import CapabilityRegistry
from backend.capabilities.models_next import CapabilityContext
from backend.capabilities.validation_next import validate_payload
from backend.capability_v2.revision.digital_model_adapter import DigitalModelRevisionAdapter
from backend.domain_ports.digital_model import ModelSnapshotRef
from plugins.digital_model.digital_model_backend.capabilities import register_capabilities
from plugins.digital_model.digital_model_backend.capabilities import models as model_capabilities
from plugins.digital_model.digital_model_backend.capabilities.contracts import INPUT_SCHEMAS
from plugins.digital_model.digital_model_backend.data.connection import _params


CAPABILITY_IDS = {
    "digital_model.model.create",
    "digital_model.model.get",
    "digital_model.model.search",
    "digital_model.version.create",
    "digital_model.snapshot.get",
    "digital_model.snapshot.compare",
    "digital_model.component.search",
}
GOLDEN_ROOT = Path(__file__).with_name("golden") / "digital_model"


def _snapshot(component_parent: str = "root", artifact_id: str = "artifact_geometry_a") -> dict:
    return {
        "model_id": "model_1",
        "version_id": "version_1",
        "artifact_ref": {
            "artifact_id": artifact_id,
            "media_type": "model/step",
            "sha256": "a" * 64,
            "byte_size": 1024,
            "version": 1,
        },
        "components": [{
            "component_id": "component_1",
            "parent_component_id": component_parent,
            "name": "Bracket",
            "component_type": "part",
            "geometry_summary": {"volume_mm3": 12.5, "surface_area_mm2": 30.0},
        }],
    }


def test_provider_publishes_native_stable_plugin_agent_and_mcp_contracts():
    registry = CapabilityRegistry()
    register_capabilities(registry)
    registrations = {item.spec.id: item for item in registry.snapshot()}
    assert set(registrations) == CAPABILITY_IDS
    for capability_id, registration in registrations.items():
        descriptor = registration.descriptor
        assert descriptor.owner_domain == "digital_model", capability_id
        assert descriptor.lifecycle_status == "stable", capability_id
        assert descriptor.exposure.plugin is True
        assert descriptor.exposure.agent is True
        assert descriptor.exposure.mcp is True
        assert descriptor.input_schema["additionalProperties"] is False
        assert descriptor.output_schema["additionalProperties"] is False
        assert descriptor.output_schema["properties"]
        assert descriptor.domain_errors_complete is True


def test_model_snapshot_refs_never_accept_or_emit_server_file_paths():
    with pytest.raises(ValidationError):
        ModelSnapshotRef.model_validate({
            "model_id": "model_1", "version_id": "version_1",
            "snapshot_hash": "sha256:" + "a" * 64,
            "artifact_ref": _snapshot()["artifact_ref"],
            "file_path": "C:\\secret\\assembly.step",
        })

    valid = ModelSnapshotRef.model_validate({
        "model_id": "model_1", "version_id": "version_1",
        "snapshot_hash": "sha256:" + "a" * 64,
        "artifact_ref": _snapshot()["artifact_ref"],
    })
    assert "file_path" not in json.dumps(valid.model_dump(mode="json"))


def test_semantic_diff_classifies_component_move_replacement_and_geometry_change():
    adapter = DigitalModelRevisionAdapter()
    before = _snapshot()

    moved = _snapshot(component_parent="assembly_2")
    assert [change.change_type for change in adapter.diff(before, moved)] == ["move"]

    replaced = _snapshot(artifact_id="artifact_geometry_b")
    replaced["artifact_ref"]["sha256"] = "b" * 64
    assert any(change.change_type == "replace" for change in adapter.diff(before, replaced))

    geometry = _snapshot()
    geometry["components"][0]["geometry_summary"]["volume_mm3"] = 14.0
    assert [change.change_type for change in adapter.diff(before, geometry)] == ["geometry_change"]


@pytest.mark.parametrize("fixture_name", [
    "component-move.json", "component-replacement.json", "geometry-summary-change.json",
])
def test_semantic_diff_golden_cases(fixture_name):
    fixture = json.loads((GOLDEN_ROOT / fixture_name).read_text(encoding="utf-8"))
    before, after = _snapshot(), _snapshot()
    mutation = fixture["mutation"]
    if "parent_component_id" in mutation:
        after["components"][0]["parent_component_id"] = mutation["parent_component_id"]
    if "artifact_id" in mutation:
        after["artifact_ref"]["artifact_id"] = mutation["artifact_id"]
        after["artifact_ref"]["sha256"] = mutation["artifact_sha256"]
    if "volume_mm3" in mutation:
        after["components"][0]["geometry_summary"]["volume_mm3"] = mutation["volume_mm3"]
    assert [change.change_type for change in DigitalModelRevisionAdapter().diff(before, after)] == fixture["expected_change_types"]


def test_version_creation_accepts_artifact_refs_and_rejects_paths(monkeypatch):
    payload = {
        "model_id": "model_1", "version_label": "A.1", "expected_head_version_id": "",
        "artifact_ref": _snapshot()["artifact_ref"], "components": _snapshot()["components"],
    }
    validate_payload(INPUT_SCHEMAS["digital_model.version.create"], payload)
    with pytest.raises(ValueError, match="unknown field"):
        validate_payload(INPUT_SCHEMAS["digital_model.version.create"], {
            **payload, "file_path": "C:\\secret\\assembly.step",
        })

    class Repository:
        captured = None

        def get_model(self, model_id, context):
            return {"model_id": model_id, "name": "Assembly", "project_ref": "project:p1", "latest_version_id": None}

        def create_version(self, model, snapshot, *, expected_head, context):
            self.captured = (model, snapshot, expected_head)

    repository = Repository()
    monkeypatch.setattr(model_capabilities, "repository", repository)
    result = model_capabilities.create_version(
        payload, CapabilityContext(user_gid="u1", team_gid="t1", source="agent"),
    ).data
    assert result["snapshot_ref"]["artifact_ref"]["artifact_id"] == "artifact_geometry_a"
    assert repository.captured[2] == ""
    assert "file_path" not in json.dumps(result)


def test_digital_model_requires_an_independent_database_url():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(RuntimeError, match="AI00_DIGITAL_MODEL_DB_URL is required"):
            _params()
