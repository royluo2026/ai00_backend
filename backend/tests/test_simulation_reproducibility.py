"""Acceptance tests for reproducible Simulation capabilities."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.capabilities.models_next import CapabilityContext
from backend.capabilities.registry_next import CapabilityRegistry
from backend.capabilities.validation_next import validate_payload
from backend.capability_v2.revision.simulation_adapter import SimulationRevisionAdapter
from backend.domain_ports.simulation import SimulationEnvironmentRef
from plugins.simulation.simulation_backend.capabilities import register_capabilities
from plugins.simulation.simulation_backend.capabilities import models as simulation_capabilities
from plugins.simulation.simulation_backend.capabilities.contracts import INPUT_SCHEMAS
from plugins.craft.craft_backend.capabilities import bop_structure
from plugins.digital_model.digital_model_backend.capabilities import models as digital_model_capabilities


CAPABILITY_IDS = {
    "simulation.parameter_set.create",
    "simulation.parameter_set.get",
    "simulation.parameter_set.search",
    "simulation.solver_profile.create",
    "simulation.solver_profile.get",
    "simulation.solver_profile.search",
    "simulation.environment.create",
    "simulation.environment.get",
    "simulation.environment.search",
    "simulation.environment.archive",
    "simulation.run.start",
    "simulation.run.get",
    "simulation.run.search",
    "simulation.result.get",
    "simulation.result.compare",
}
ROOT = Path(__file__).resolve().parents[2]


def _artifact() -> dict:
    return {
        "artifact_id": "artifact_result_1",
        "media_type": "application/vnd.ai00.simulation-result+json",
        "sha256": "d" * 64,
        "byte_size": 2048,
        "version": 1,
    }


def _refs() -> dict:
    return {
        "execution_plan_ref": {
            "version_gid": "bop_version_1",
            "revision": 7,
            "content_hash": "sha256:" + "a" * 64,
        },
        "model_snapshot_ref": {
            "model_id": "model_1",
            "version_id": "model_version_1",
            "snapshot_hash": "sha256:" + "b" * 64,
            "artifact_ref": {
                "artifact_id": "artifact_model_1",
                "media_type": "model/step",
                "sha256": "b" * 64,
                "byte_size": 1024,
                "version": 1,
            },
        },
        "parameter_set_ref": {
            "parameter_set_id": "parameter_set_1",
            "version": 3,
            "content_hash": "sha256:" + "c" * 64,
        },
        "simulation_profile_ref": {
            "profile_id": "profile_1",
            "version": 2,
            "content_hash": "sha256:" + "d" * 64,
        },
    }


def test_provider_publishes_native_stable_plugin_agent_and_mcp_contracts():
    registry = CapabilityRegistry()
    register_capabilities(registry)
    registrations = {item.spec.id: item for item in registry.snapshot()}
    assert set(registrations) == CAPABILITY_IDS
    for capability_id, registration in registrations.items():
        descriptor = registration.descriptor
        assert descriptor.owner_domain == "simulation", capability_id
        assert descriptor.lifecycle_status == "stable", capability_id
        assert descriptor.exposure.plugin and descriptor.exposure.agent and descriptor.exposure.mcp
        assert descriptor.input_schema["additionalProperties"] is False
        assert descriptor.output_schema["additionalProperties"] is False
        assert descriptor.output_schema["properties"]
        assert descriptor.domain_errors_complete is True
    create_descriptor = registrations["simulation.environment.create"].descriptor
    assert {selector.resource_type for selector in create_descriptor.resource_selectors} == {
        "craft-bop-version", "digital-model", "digital-model-version",
        "simulation-parameter-set", "simulation-profile",
    }
    assert registrations["simulation.run.start"].descriptor.execution_mode == "cloud_async"
    retryable_errors = {
        error.code for error in registrations["simulation.result.get"].descriptor.domain_errors
        if error.retryable
    }
    assert retryable_errors == {"source_resolver_unavailable", "simulation_result_not_ready"}


def test_environment_creation_rejects_caller_plan_json_paths_and_unpinned_refs():
    valid = {"name": "Line balance", **_refs()}
    validate_payload(INPUT_SCHEMAS["simulation.environment.create"], valid)
    for forbidden in (
        {"execution_plan": {"steps": []}},
        {"execution_plan_snapshot_uri": "file:///secret/plan.json"},
        {"file_path": "C:\\secret\\model.step"},
    ):
        with pytest.raises(ValueError, match="unknown field"):
            validate_payload(INPUT_SCHEMAS["simulation.environment.create"], {**valid, **forbidden})

    with pytest.raises(ValueError):
        validate_payload(INPUT_SCHEMAS["simulation.environment.create"], {
            **valid,
            "execution_plan_ref": {"version_gid": "bop_version_1", "revision": 7},
        })


def test_environment_pins_resolved_versions_and_run_preserves_exact_sources(monkeypatch):
    class Repository:
        environment = None
        run = None

        def get_parameter_set(self, ref, context):
            assert ref == _refs()["parameter_set_ref"]
            return {**ref, "values": {"friction": 0.2}}

        def get_profile(self, ref, context):
            assert ref == _refs()["simulation_profile_ref"]
            return {**ref, "solver": "solver-x", "solver_version": "5.4.1", "settings": {}}

        def create_environment(self, row):
            self.environment = dict(row)

        def get_environment(self, environment_id, context):
            return self.environment if self.environment and self.environment["environment_id"] == environment_id else None

        def create_run(self, row):
            self.run = dict(row)

    class SourceResolver:
        def resolve_execution_plan(self, ref, context):
            return {**ref, "craft_commit_ref": "craft://bop/version/bop_version_1/r7", "node_count": 12}

        def resolve_model_snapshot(self, ref, context):
            return dict(ref)

    repository = Repository()
    monkeypatch.setattr(simulation_capabilities, "repository", repository)
    monkeypatch.setattr(simulation_capabilities, "source_resolver", SourceResolver())
    context = CapabilityContext(user_gid="user_1", team_gid="team_1", source="agent")

    environment = simulation_capabilities.create_environment(
        {"name": "Line balance", **_refs()}, context,
    ).data
    source = environment["source"]
    assert source["execution_plan"]["craft_commit_ref"].endswith("/r7")
    assert source["model_snapshot"]["snapshot_hash"] == "sha256:" + "b" * 64
    assert source["parameter_set"]["version"] == 3
    assert source["simulation_profile"]["solver_version"] == "5.4.1"
    assert source["source_fingerprint"].startswith("sha256:")
    assert "file://" not in json.dumps(source)

    run = simulation_capabilities.start_run(
        {"environment_id": environment["environment_id"]}, context,
    ).data
    assert run["source_fingerprint"] == source["source_fingerprint"]
    assert run["craft_commit_ref"].endswith("/r7")
    assert run["model_snapshot_hash"] == "sha256:" + "b" * 64
    assert run["parameter_version"] == 3
    assert run["solver_version"] == "5.4.1"
    assert run["operation_ref"]["status"] == "accepted"
    assert run["run_id"] != run["operation_ref"]["operation_id"]


def test_simulation_refs_and_revision_adapter_are_closed_and_semantic():
    with pytest.raises(ValueError):
        SimulationEnvironmentRef.model_validate({
            "environment_id": "environment_1",
            "source_fingerprint": "sha256:" + "a" * 64,
            "file_path": "C:\\secret",
        })
    adapter = SimulationRevisionAdapter()
    before = {"source": _refs(), "result_artifact_refs": []}
    after = {"source": _refs(), "result_artifact_refs": [_artifact()]}
    assert [item.change_type for item in adapter.diff(before, after)] == ["result_add"]
    changed = {"source": {**_refs(), "parameter_set_ref": {**_refs()["parameter_set_ref"], "version": 4}}, "result_artifact_refs": []}
    changes = adapter.diff(before, changed)
    assert len(changes) == 1 and changes[0].change_type == "input_change" and changes[0].breaking


def test_owning_domain_resolvers_reject_stale_reference_hashes(monkeypatch):
    context = CapabilityContext(user_gid="user_1", source="agent")
    monkeypatch.setattr(bop_structure, "build_execution_structure", lambda *args, **kwargs: {
        "source": {"bop_version_gid": "bop_version_1", "revision": 8},
        "content_hash": "sha256:" + "f" * 64,
        "nodes": [],
    })
    with pytest.raises(Exception, match="no longer matches"):
        bop_structure.resolve_execution_plan_reference(_refs()["execution_plan_ref"], context)

    monkeypatch.setattr(digital_model_capabilities.repository, "get_snapshot", lambda *args, **kwargs: {
        "model_id": "model_1", "version_id": "model_version_1", "version_label": "A",
        "snapshot_hash": "sha256:" + "f" * 64,
        "artifact_id": "artifact_model_1", "artifact_media_type": "model/step",
        "artifact_sha256": "b" * 64, "artifact_byte_size": 1024, "artifact_version": 1,
        "snapshot_json": "{\"components\":[]}",
    })
    with pytest.raises(Exception, match="no longer matches"):
        digital_model_capabilities.resolve_snapshot_reference(_refs()["model_snapshot_ref"], context)


def test_run_refuses_a_tampered_persisted_environment(monkeypatch):
    source = {
        "execution_plan": {**_refs()["execution_plan_ref"], "craft_commit_ref": "craft://bop/version/bop_version_1/r7", "node_count": 1},
        "model_snapshot": _refs()["model_snapshot_ref"],
        "parameter_set": {**_refs()["parameter_set_ref"], "parameters": []},
        "simulation_profile": {**_refs()["simulation_profile_ref"], "solver": "solver-x", "solver_version": "5.4.1", "settings": []},
        "source_fingerprint": "sha256:" + "0" * 64,
    }

    class Repository:
        def get_environment(self, environment_id, context):
            return {"environment_id": environment_id, "name": "tampered", "status": "draft", "source": source}

    monkeypatch.setattr(simulation_capabilities, "repository", Repository())
    with pytest.raises(Exception, match="fingerprint"):
        simulation_capabilities.start_run(
            {"environment_id": "environment_1"},
            CapabilityContext(user_gid="user_1", source="agent"),
        )


def test_parameter_profile_and_result_capabilities_preserve_versions_and_artifact_refs(monkeypatch):
    class Repository:
        parameter = None
        profile = None
        run = None

        def create_parameter_set(self, row): self.parameter = dict(row)
        def get_parameter_set(self, ref, context): return self.parameter
        def create_profile(self, row): self.profile = dict(row)
        def get_profile(self, ref, context): return self.profile
        def get_run(self, run_id, context): return self.run

    repository = Repository()
    monkeypatch.setattr(simulation_capabilities, "repository", repository)
    context = CapabilityContext(user_gid="user_1", team_gid="team_1", source="plugin")

    parameter = simulation_capabilities.create_parameter_set({
        "name": "Nominal", "parameters": [{"name": "friction", "value": 0.2, "unit": "ratio"}],
    }, context).data
    assert parameter["parameter_set_ref"]["version"] == 1
    assert simulation_capabilities.get_parameter_set({
        "parameter_set_ref": parameter["parameter_set_ref"],
    }, context).data == parameter

    profile = simulation_capabilities.create_profile({
        "name": "Solver X", "solver": "solver-x", "solver_version": "5.4.1",
        "settings": [{"name": "precision", "value": "high"}],
    }, context).data
    assert profile["simulation_profile_ref"]["version"] == 1
    assert simulation_capabilities.get_profile({
        "simulation_profile_ref": profile["simulation_profile_ref"],
    }, context).data == profile

    repository.run = {
        "run_id": "operation_1", "status": "completed",
        "source_fingerprint": "sha256:" + "a" * 64,
        "result_artifact_refs": [_artifact()],
    }
    result = simulation_capabilities.get_result({"run_id": "operation_1"}, context).data
    assert result["result_artifact_refs"] == [_artifact()]
    assert result["result_ref"]["result_hash"].startswith("sha256:")
    assert "file_path" not in json.dumps(result)

    repository.run = {**repository.run, "run_id": "operation_2", "result_artifact_refs": [{**_artifact(), "sha256": "e" * 64}]}
    changed = simulation_capabilities.get_result({"run_id": "operation_2"}, context).data
    repository.runs = {"operation_1": {**repository.run, "run_id": "operation_1", "result_artifact_refs": [_artifact()]}, "operation_2": repository.run}
    repository.get_run = lambda run_id, context: repository.runs.get(run_id)
    comparison_output = simulation_capabilities.compare_results({
        "left_result_ref": result["result_ref"],
        "right_result_ref": changed["result_ref"],
    }, context)
    comparison = comparison_output.data
    assert comparison["same_inputs"] is True
    assert comparison["changes"][0]["change_type"] == "artifact_changed"
    assert {item.digest for item in comparison_output.evidence} == {
        result["result_ref"]["result_hash"], changed["result_ref"]["result_hash"],
    }

    repository.runs["operation_1"] = {**repository.runs["operation_1"], "status": "running", "result_artifact_refs": []}
    with pytest.raises(Exception, match="not ready"):
        simulation_capabilities.get_result({"run_id": "operation_1"}, context)


def test_solver_profile_rejects_versions_outside_the_domain_allowlist(monkeypatch):
    class Repository:
        def create_profile(self, row):
            raise AssertionError("unapproved solver must not be persisted")

    monkeypatch.setattr(simulation_capabilities, "repository", Repository())
    with pytest.raises(Exception, match="allowlist"):
        simulation_capabilities.create_profile({
            "name": "Unknown", "solver": "arbitrary-shell", "solver_version": "latest", "settings": [],
        }, CapabilityContext(user_gid="user_1", source="agent"))


def test_run_schema_materializes_every_reproducibility_coordinate():
    sql = (ROOT / "backend/db/migrations/202608100010_simulation_reproducibility.sql").read_text(encoding="utf-8")
    for column in (
        "craft_commit_ref", "model_snapshot_hash", "parameter_set_id", "parameter_version",
        "profile_id", "profile_version", "solver", "solver_version", "result_artifact_refs",
    ):
        assert column in sql


def test_search_and_archive_handlers_return_domain_owned_records(monkeypatch):
    source_without_hash = {
        "execution_plan": {**_refs()["execution_plan_ref"], "craft_commit_ref": "craft://bop/version/bop_version_1/r7", "node_count": 2},
        "model_snapshot": _refs()["model_snapshot_ref"],
        "parameter_set": {**_refs()["parameter_set_ref"], "parameters": []},
        "simulation_profile": {**_refs()["simulation_profile_ref"], "solver": "solver-x", "solver_version": "5.4.1", "settings": []},
    }
    fingerprint, _ = simulation_capabilities._canonical(source_without_hash)
    source = {**source_without_hash, "source_fingerprint": fingerprint}

    class Repository:
        def search_parameter_sets(self, query, limit, context):
            return [{**_refs()["parameter_set_ref"], "name": "Nominal", "values": {"friction": 0.2}}]

        def search_profiles(self, query, limit, context):
            return [{**_refs()["simulation_profile_ref"], "name": "Solver X", "solver": "solver-x", "solver_version": "5.4.1", "settings": {}}]

        def list_environments(self, limit, context):
            return [{"environment_id": "env-1", "name": "Line", "status": "draft", "source": source}]

        def archive_environment(self, environment_id, context):
            return {"environment_id": environment_id, "name": "Line", "status": "archived", "source": source}

        def search_runs(self, environment_id, limit, context):
            return [{"run_id": "run-1", "environment_id": "env-1", "operation_id": "op-1", "status": "queued", "source_fingerprint": fingerprint, "source": source}]

    monkeypatch.setattr(simulation_capabilities, "repository", Repository())
    context = CapabilityContext(user_gid="user_1", source="plugin")

    assert simulation_capabilities.search_parameter_sets({}, context).data["total"] == 1
    assert simulation_capabilities.search_profiles({}, context).data["total"] == 1
    assert simulation_capabilities.list_environments({}, context).data["total"] == 1
    assert simulation_capabilities.archive_environment({"environment_id": "env-1"}, context).data["status"] == "archived"
    assert simulation_capabilities.search_runs({}, context).data["items"][0]["run_id"] == "run-1"
