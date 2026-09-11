from plugins.simulation.simulation_backend.application.environment_materialization import build_runtime_package
from plugins.simulation.simulation_backend.domain.plmxml_environment_codec import EnvironmentModelDocument, EnvironmentRuntimeModel


def _document(gid, role, name, media, digest, portability="portable", connector_device_id=None):
    return EnvironmentModelDocument(document_gid=gid, role=role, display_name=name, media_type=media,
        artifact_ref={"artifact_id": "artifact_" + gid, "media_type": media, "sha256": digest, "byte_size": 1, "version": 1},
        source_identity_hash="sha256:" + digest, content_sha256="sha256:" + digest,
        portability=portability, connector_device_id=connector_device_id)


def test_runtime_package_is_deterministic_with_one_generated_top_level_and_sorted_dependencies():
    model = EnvironmentRuntimeModel(environment_gid="10", documents=(
        _document("3", "inserted", "z tool.jt", "model/vnd.jt", "c" * 64),
        _document("1", "primary", "base.plmxml", "application/plmxml+xml", "a" * 64),
        _document("2", "inserted", "a fixture.jt", "model/vnd.jt", "b" * 64),
    ), hierarchies=())
    first = build_runtime_package({"runtime_model": model, "version_gid": "20"})
    second = build_runtime_package({"runtime_model": model, "version_gid": "20"})
    assert first.top_level_content == second.top_level_content
    assert [item.document_gid for item in first.dependencies] == ["1", "2", "3"]
    assert first.manifest["top_level_count"] == 1
    assert first.manifest["open_only_top_level"] is True


def test_runtime_package_requires_exactly_one_primary_and_rejects_unbound_device_document():
    import pytest
    from plugins.simulation.simulation_backend.application.environment_materialization import EnvironmentMaterializationError
    no_primary = EnvironmentRuntimeModel(environment_gid="10", documents=(_document("2", "inserted", "a.jt", "model/vnd.jt", "b" * 64),), hierarchies=())
    with pytest.raises(EnvironmentMaterializationError, match="primary_model_document_required"):
        build_runtime_package({"runtime_model": no_primary, "version_gid": "20"})
    device_bound = EnvironmentRuntimeModel(environment_gid="10", documents=(_document("1", "primary", "base.plmxml", "application/plmxml+xml", "a" * 64, "device_bound"),), hierarchies=())
    with pytest.raises(EnvironmentMaterializationError, match="device_bound_document_requires_connector"):
        build_runtime_package({"runtime_model": device_bound, "version_gid": "20"})
    wrong_device = EnvironmentRuntimeModel(environment_gid="10", documents=(
        _document("1", "primary", "base.plmxml", "application/plmxml+xml", "a" * 64,
                  "device_bound", "device-1"),
    ), hierarchies=())
    with pytest.raises(EnvironmentMaterializationError, match="device_bound_document_connector_mismatch"):
        build_runtime_package({"runtime_model": wrong_device, "version_gid": "20", "connector_device_id": "device-2"})
