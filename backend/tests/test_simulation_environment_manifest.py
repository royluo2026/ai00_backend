from __future__ import annotations

from pathlib import Path

from plugins.simulation.simulation_backend.domain.environment_manifest import compose_manifest


def _fixture(*, reversed_order: bool = False):
    operations = [
        {
            "operation_id": "op-10",
            "sequence": 10,
            "products": [{"product_ref": "P-10", "action": "install"}],
            "resources": [{"resource_type": "tool", "code": "T-10"}],
        },
        {
            "operation_id": "op-20",
            "sequence": 20,
            "products": [{"product_ref": "P-20", "action": "install"}],
            "resources": [{"resource_type": "tool", "code": "T-20"}],
        },
    ]
    nodes = [
        {"node_key": "bom-node-10", "parent_key": "bom-root", "product_ref": "P-10", "child_order": 1},
        {"node_key": "bom-node-20", "parent_key": "bom-root", "product_ref": "P-20", "child_order": 2},
        {"node_key": "bom-root", "parent_key": None, "product_ref": "ROOT", "child_order": 0},
    ]
    resolved = [
        {"resource_type": "tool", "code": "T-10", "normalized_code": "t-10", "model_ref": _model("10")},
        {"resource_type": "tool", "code": "T-20", "normalized_code": "t-20", "model_ref": _model("20")},
    ]
    if reversed_order:
        operations.reverse()
        nodes.reverse()
        resolved.reverse()
    return {
        "execution_plan": {
            "source": {"bop_version_gid": "bop-1", "revision": 7, "project_gid": "project-1"},
            "content_hash": "sha256:" + "a" * 64,
            "operations": operations,
        },
        "document_snapshot": {
            "document_id": "BOM-1",
            "root_node_key": "bom-root",
            "source_identity": "tc://item/BOM-1/revision/A",
            "snapshot_hash": "sha256:" + "b" * 64,
            "nodes": nodes,
        },
        "model_mappings": {
            "resolved": resolved,
            "unresolved": [],
            "ambiguous": [],
            "mapping_snapshot_hash": "sha256:" + "c" * 64,
        },
        "capture_profile": {"format": "png", "width": 1920, "height": 1080, "background": "current"},
    }


def _model(suffix: str):
    return {
        "model_id": f"model-{suffix}",
        "version_id": f"version-{suffix}",
        "snapshot_hash": "sha256:" + suffix[0] * 64,
        "artifact_ref": {
            "artifact_id": f"artifact-{suffix}",
            "media_type": "model/step",
            "sha256": suffix[0] * 64,
            "byte_size": 100,
            "version": 1,
        },
    }


def test_manifest_is_independent_of_input_collection_order():
    left = compose_manifest(**_fixture())
    right = compose_manifest(**_fixture(reversed_order=True))

    assert left.problems == right.problems == ()
    assert left.manifest.manifest_hash == right.manifest.manifest_hash
    assert left.manifest == right.manifest


def test_reverse_scene_uses_cumulative_products_and_current_resources_only():
    result = compose_manifest(**_fixture())

    scene = result.manifest.scene_for("op-20")

    assert scene.visible_products == ("bom-node-10", "bom-node-20")
    assert scene.visible_resources == ("resource-node-tool-20",)


def test_composition_returns_every_binding_problem_without_partial_manifest():
    fixture = _fixture()
    fixture["execution_plan"]["operations"][0]["products"] = [
        {"product_ref": "P-X", "action": "install"}
    ]
    fixture["model_mappings"] = {
        "resolved": [],
        "unresolved": [{"resource_type": "tool", "code": "T-10", "normalized_code": "t-10"}],
        "ambiguous": [{
            "resource_type": "tool",
            "code": "T-20",
            "normalized_code": "t-20",
            "candidates": [_model("20"), _model("21")],
        }],
        "mapping_snapshot_hash": "sha256:" + "d" * 64,
    }

    result = compose_manifest(**fixture)

    assert result.manifest is None
    assert [(item.kind, item.source_type, item.source_code) for item in result.problems] == [
        ("not_found", "product", "P-X"),
        ("not_found", "tool", "T-10"),
        ("ambiguous", "tool", "T-20"),
    ]


def test_connector_environment_migration_owns_complete_local_lifecycle_without_cross_domain_fks():
    root = Path(__file__).resolve().parents[2]
    sql = (
        root / "backend/db/migrations/domains/simulation/0002_connector_environments.sql"
    ).read_text(encoding="utf-8")

    for table in (
        "workmanship_sim_environment_manifests",
        "workmanship_sim_environment_bindings",
        "workmanship_sim_materialization_runs",
        "workmanship_sim_capture_runs",
        "workmanship_sim_capture_steps",
        "workmanship_sim_capture_artifact_refs",
    ):
        assert f"CREATE TABLE IF NOT EXISTS `{table}`" in sql
    assert "UNIQUE KEY `uq_sim_manifest_hash`" in sql
    assert "CHECK (`status` IN" in sql
    assert "REFERENCES `workmanship_bop_" not in sql
    assert "REFERENCES `workmanship_craft_" not in sql
    assert "REFERENCES `workmanship_knowledge_" not in sql
    assert "REFERENCES `workmanship_model_" not in sql


def test_environment_repository_depends_only_on_simulation_connection():
    root = Path(__file__).resolve().parents[2]
    source = (
        root / "plugins/simulation/simulation_backend/data/environment_repository.py"
    ).read_text(encoding="utf-8")

    assert "get_simulation_conn" in source
    assert "plugins.craft" not in source
    assert "plugins.knowledge" not in source
    assert "plugins.digital_model" not in source
