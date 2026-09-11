from __future__ import annotations

import io
from pathlib import Path

import pytest

from plugins.simulation.simulation_backend.domain.plmxml_environment_codec import (
    EnvironmentRuntimeModel,
    EnvironmentDocumentDependencyError,
    export_environment_plmxml,
    import_environment_plmxml,
    resolve_package_reference,
    validate_document_dependency_graph,
)
from plugins.simulation.simulation_backend.domain.plmxml_projection import (
    PlmxmlLimitError,
    PlmxmlLimits,
    PlmxmlSecurityError,
)


def _environment_xml() -> bytes:
    return b'''<?xml version="1.0"?>
<PLMXML xmlns="http://www.plmxml.org/Schemas/PLMXMLSchema" schemaVersion="6" author="test">
  <ProductView id="alt-1" name="1111" usage="variant" rootRefs="variant-root"/>
  <ProductInstance id="external-root" name="external" partRef="base.plmxml#base-view"/>
  <ProductRevisionView id="local-view" name="tool">
    <Representation id="tool-rep" format="JT" location="models/Pitou.jt"/>
  </ProductRevisionView>
</PLMXML>'''


def _populated_environment_xml() -> bytes:
    return b'''<?xml version="1.0"?>
<PLMXML xmlns="http://www.plmxml.org/Schemas/PLMXMLSchema" schemaVersion="6" author="test">
  <ProductView id="alt-1" name="First" usage="variant" primaryOccurrenceRef="occ-root">
    <Occurrence id="occ-root" name="Assembly" occurrenceRefs="occ-part" visible="false"/>
    <Occurrence id="occ-part" name="Part" visible="true">
      <ApplicationRef application="__TC-VIS_NGID" label="stable-part"/>
    </Occurrence>
  </ProductView>
  <ProductView id="alt-empty" name="Empty" usage="variant"/>
</PLMXML>'''


def test_import_discovers_variant_hierarchy_and_external_model_documents():
    result = import_environment_plmxml(
        io.BytesIO(_environment_xml()), limits=PlmxmlLimits(), algorithm_version="environment-codec.v1"
    )

    assert [(item.name, item.projection_identity) for item in result.hierarchies] == [("1111", "alt-1")]
    assert [(item.location, item.media_type) for item in result.dependencies] == [
        ("base.plmxml", "application/plmxml+xml"),
        ("models/Pitou.jt", "model/vnd.jt"),
    ]
    assert result.algorithm_version == "environment-codec.v1"
    assert result.original_sha256.startswith("sha256:")


def test_dependency_graph_rejects_supplement_that_points_back_to_primary():
    with pytest.raises(EnvironmentDocumentDependencyError, match="model_document_dependency_cycle"):
        validate_document_dependency_graph(
            primary="base.plmxml",
            supplements={"W10-2.plmxml": ("base.plmxml",)},
        )


def test_dependency_graph_allows_independent_supplements_and_deduplicates_dependencies():
    result = validate_document_dependency_graph(
        primary="base.plmxml",
        supplements={"fixture.plmxml": ("models/tool.jt", "models/tool.jt")},
    )
    assert result == {"base.plmxml": (), "fixture.plmxml": ("models/tool.jt",)}


def test_import_projects_multiple_hierarchies_and_stable_occurrences():
    result = import_environment_plmxml(
        io.BytesIO(_populated_environment_xml()),
        limits=PlmxmlLimits(),
        algorithm_version="environment-codec.v1",
    )

    assert [item.name for item in result.hierarchies] == ["First", "Empty"]
    assert result.hierarchies[0].root_placement_identity == "occ-root"
    assert [(item.name, item.parent_identity) for item in result.hierarchies[0].placements] == [
        ("Assembly", None),
        ("Part", "occ-root"),
    ]
    assert result.hierarchies[0].placements[1].stable_identity.startswith("ngid:")
    assert result.hierarchies[1].placements == ()


def test_export_is_deterministic_and_round_trips_semantic_environment():
    imported = import_environment_plmxml(
        io.BytesIO(_populated_environment_xml()),
        limits=PlmxmlLimits(),
        algorithm_version="environment-codec.v1",
    )
    model = EnvironmentRuntimeModel(
        environment_gid="9001",
        documents=imported.dependencies,
        hierarchies=imported.hierarchies,
    )

    first = export_environment_plmxml(model)
    second = export_environment_plmxml(model)
    reparsed = import_environment_plmxml(
        io.BytesIO(first.content), limits=PlmxmlLimits(), algorithm_version="environment-codec.v1"
    )

    assert first.content == second.content
    assert first.semantic_hash == second.semantic_hash
    assert first.report["hierarchy_count"] == 2
    assert first.report["placement_count"] == 2
    assert [item.name for item in reparsed.hierarchies] == ["First", "Empty"]


@pytest.mark.parametrize("location", ["https://example.invalid/model.jt", "file:///C:/secret/model.jt"])
def test_import_rejects_unsupported_external_uri_schemes(location: str):
    xml = f'''<PLMXML><ProductRevisionView><Representation location="{location}"/></ProductRevisionView></PLMXML>'''.encode()
    with pytest.raises(PlmxmlSecurityError, match="unsupported_external_uri_scheme"):
        import_environment_plmxml(io.BytesIO(xml), limits=PlmxmlLimits(), algorithm_version="v1")


@pytest.mark.parametrize("location", ["../outside/model.jt", "/absolute/model.jt", r"C:\\outside\\model.jt"])
def test_package_resolution_rejects_path_traversal_and_absolute_paths(location: str):
    with pytest.raises(PlmxmlSecurityError, match="external_reference_outside_package"):
        resolve_package_reference(location, package_root="models")


def test_package_resolution_keeps_controlled_relative_reference_inside_root():
    assert resolve_package_reference("parts/tool.jt", package_root="models") == "models/parts/tool.jt"


def test_import_enforces_projected_instance_limit_across_all_hierarchies():
    xml = b'<PLMXML><ProductView id="a" usage="variant"><Occurrence id="1"/></ProductView><ProductView id="b" usage="variant"><Occurrence id="2"/></ProductView></PLMXML>'
    with pytest.raises(PlmxmlLimitError, match="max_projected_instances"):
        import_environment_plmxml(io.BytesIO(xml), limits=PlmxmlLimits(max_projected_instances=1), algorithm_version="v1")


def test_import_enforces_external_reference_limit():
    with pytest.raises(PlmxmlLimitError, match="max_external_references"):
        import_environment_plmxml(
            io.BytesIO(_environment_xml()),
            limits=PlmxmlLimits(max_references=1),
            algorithm_version="v1",
        )


@pytest.mark.parametrize("payload", [
    b'<!DOCTYPE x [<!ENTITY e "boom">]><PLMXML>&e;</PLMXML>',
    b'<PLMXML xmlns:xi="http://www.w3.org/2001/XInclude"><xi:include href="x"/></PLMXML>',
])
def test_import_rejects_external_xml_expansion(payload: bytes):
    with pytest.raises(PlmxmlSecurityError):
        import_environment_plmxml(io.BytesIO(payload), limits=PlmxmlLimits(), algorithm_version="v1")


def test_real_w10_files_import_within_limits_when_present():
    directory = Path(r"D:\Temp\vis\plmxml")
    paths = sorted(directory.glob("*.plmxml"))
    if len(paths) < 2:
        pytest.skip("local W10 PLMXML fixtures are absent")

    results = [
        import_environment_plmxml(path.open("rb"), limits=PlmxmlLimits(), algorithm_version="v1")
        for path in paths
    ]
    assert any(any(hierarchy.placements for hierarchy in result.hierarchies) for result in results)
