from __future__ import annotations

import io

import pytest

from plugins.simulation.simulation_backend.domain.plmxml_projection import (
    PlmxmlLimitError,
    PlmxmlLimits,
    PlmxmlSecurityError,
    PlmxmlStructureError,
    parse_plmxml,
)


NS = "http://www.plmxml.org/Schemas/PLMXMLSchema"


def _document(*body: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<PLMXML xmlns="{NS}" schemaVersion="6" author="test">'
        '<ProductDef id="product" defaultProductViewRef="view-root">'
        '<InstanceGraph id="graph" rootRefs="inst-root">'
        + "".join(body)
        + "</InstanceGraph></ProductDef></PLMXML>"
    ).encode()


def _representative_document() -> bytes:
    return _document(
        '<ProductInstance id="inst-root" name="ROOT/00;1-Root" partRef="#view-root"/>',
        '<ProductInstance id="inst-bolt-1" name="W01-89184128/00;1-Bolt" partRef="#view-bolt">'
        '<ApplicationRef application="TCC-VIS" label="bolt-1.part;-1;10:"/>'
        '<Transform id="t1">1 0 0 0 0 1 0 0 0 0 1 0 0.0635000000 0.311 -0 1</Transform>'
        "</ProductInstance>",
        '<ProductInstance id="inst-bolt-2" name="W01-89184128/00;1-Bolt" partRef="#view-bolt">'
        '<ApplicationRef application="TCC-VIS" label="bolt-2.part;-1;20:"/>'
        '<Transform id="t2">1 0 0 0 0 1 0 0 0 0 1 0 0.1635 0.311 0 1</Transform>'
        "</ProductInstance>",
        '<ProductRevisionView id="view-root" name="ROOT/00;1-Root" instanceRefs="inst-bolt-1 inst-bolt-2">'
        '<UserData><UserValue title="__PLM_ITEM_ID" value="ROOT"/>'
        '<UserValue title="__PLM_REVISION_ID" value="00"/></UserData>'
        "</ProductRevisionView>",
        '<ProductRevisionView id="view-bolt" name="W01-89184128/00;1-Bolt">'
        '<UserData><UserValue title="__PLM_ITEM_ID" value="W01-89184128"/>'
        '<UserValue title="__PLM_REVISION_ID" value="00"/></UserData>'
        '<Representation id="rep" format="JT" location="/opaque/W01-89184128_00.jt"/>'
        "</ProductRevisionView>",
        '<Occurrence id="occ-1" instanceRefs="#inst-root #inst-bolt-1">'
        '<UserData><UserValue title="catiaOccurrenceName" value="bolt-left"/></UserData>'
        "</Occurrence>",
        '<Occurrence id="occ-2" instanceRefs="#inst-root #inst-bolt-2">'
        '<UserData><UserValue title="catiaOccurrenceName" value="bolt-right"/></UserData>'
        "</Occurrence>",
    )


def _current_state_document() -> bytes:
    root = "ROOT/00;1-Root.asm;-1;0:"
    assembly = "ASSY-1/A;1-Assembly.asm;-1;10:"
    part = "PART-2/B;1-Part.prt;-1;20:"
    return _document(
        '<ProductInstance id="inst-root" name="ROOT/00;1-Root" partRef="#view-root"/>',
        '<ProductRevisionView id="view-root" name="ROOT/00;1-Root">'
        '<UserData><UserValue title="__PLM_ITEM_ID" value="ROOT"/>'
        '<UserValue title="__PLM_REVISION_ID" value="00"/></UserData>'
        '</ProductRevisionView>',
        '<Occurrence id="occ-assembly">'
        f'<ApplicationRef application="__TC-VIS_APP" label="#PLMXML(PS_API-doc/JT_PROP_NAME(&apos;CHLD0000\\0{root}\\0{assembly}\\0\\0&apos;))"/>'
        '<ApplicationRef application="__TC-VIS_NGID" label="#PLMXML(PS_API-doc/NGID(&apos;$$NGID&lt;chain&gt;=&quot;__PLM_CLONE_STABLE_INST_UID&quot;\\0clone-root\\0clone-assembly\\0$$NGID&lt;chain&gt;=&quot;JT_PROP_NAME&quot;\\0ignored\\0&apos;))"/>'
        '<UserData><UserValue title="__PLM_OCC_PDM_UID" value="pdm-assembly"/>'
        '<UserValue title="__PLM_ABSOCC_UID" value="abs-assembly"/>'
        '<UserValue title="catiaOccurrenceName" value="assembly-occ"/></UserData>'
        '</Occurrence>',
        '<Occurrence id="occ-part">'
        f'<ApplicationRef application="__TC-VIS_APP" label="#PLMXML(PS_API-doc/JT_PROP_NAME(&apos;CHLD0000\\0{root}\\0{assembly}\\0{part}\\0\\0&apos;))"/>'
        '<ApplicationRef application="__TC-VIS_NGID" label="#PLMXML(PS_API-doc/NGID(&apos;$$NGID&lt;chain&gt;=&quot;__PLM_CLONE_STABLE_INST_UID&quot;\\0clone-root\\0clone-assembly\\0clone-part\\0$$NGID&lt;chain&gt;=&quot;JT_PROP_NAME&quot;\\0ignored\\0&apos;))"/>'
        '<UserData><UserValue title="__PLM_OCC_PDM_UID" value="pdm-part"/>'
        '<UserValue title="__PLM_ABSOCC_UID" value="abs-part"/>'
        '<UserValue title="catiaOccurrenceName" value="part-occ"/></UserData>'
        '</Occurrence>',
    )


def test_projects_bom_revision_occurrence_path_transform_and_duplicate_instances():
    projection = parse_plmxml(io.BytesIO(_representative_document()))

    assert projection.schema_version == "6"
    assert projection.root_instance_ids == ("inst-root",)
    assert len(projection.instances) == 3
    left, right = projection.by_bom_line("W01-89184128/00;1")
    assert left.item_id == right.item_id == "W01-89184128"
    assert left.revision == right.revision == "00"
    assert left.parent_path == right.parent_path == ("inst-root",)
    assert left.catia_occurrence_name == "bolt-left"
    assert right.catia_occurrence_name == "bolt-right"
    assert left.normalized_transform[-4:] == ("0.0635", "0.311", "0", "1")
    assert left.representation_locations == ("/opaque/W01-89184128_00.jt",)


def test_projects_vismockup_current_state_occurrence_paths_and_stable_identity():
    projection = parse_plmxml(io.BytesIO(_current_state_document()))

    assert len(projection.instances) == 3
    root, assembly, part = projection.instances
    assert root.instance_id == "inst-root"
    assert assembly.parent_instance_id == "inst-root"
    assert part.parent_instance_id == assembly.instance_id
    assert part.parent_path == ("inst-root", assembly.instance_id)
    assert (assembly.item_id, assembly.revision) == ("ASSY-1", "A")
    assert (part.item_id, part.revision) == ("PART-2", "B")
    assert part.pdm_occurrence_uid == "pdm-part"
    assert part.absolute_occurrence_uid == "abs-part"
    assert part.clone_stable_chain == ("clone-root", "clone-assembly", "clone-part")
    assert part.occurrence_path[-1] == "PART-2/B;1-Part.prt;-1;20:"
    assert part.catia_occurrence_name == "part-occ"


def test_broken_part_reference_is_structured_error():
    data = _document('<ProductInstance id="inst" name="X/00;1-X" partRef="#missing"/>')
    with pytest.raises(PlmxmlStructureError, match="unresolved_part_ref"):
        parse_plmxml(io.BytesIO(data))


@pytest.mark.parametrize(
    "payload",
    [
        b'<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///never-read">]><x>&secret;</x>',
        b'<PLMXML xmlns:xi="http://www.w3.org/2001/XInclude"><xi:include href="file:///never-read"/></PLMXML>',
    ],
)
def test_rejects_dtd_entities_and_xinclude_without_external_io(payload: bytes):
    with pytest.raises(PlmxmlSecurityError):
        parse_plmxml(io.BytesIO(payload))


def test_enforces_byte_element_depth_string_reference_and_time_limits():
    cases = [
        (PlmxmlLimits(max_bytes=10), _representative_document(), "max_bytes"),
        (PlmxmlLimits(max_elements=2), _representative_document(), "max_elements"),
        (PlmxmlLimits(max_depth=2), _representative_document(), "max_depth"),
        (PlmxmlLimits(max_string_length=3), _representative_document(), "max_string_length"),
        (PlmxmlLimits(max_references=1), _representative_document(), "max_references"),
        (PlmxmlLimits(max_attributes_per_element=1), _representative_document(), "max_attributes_per_element"),
        (PlmxmlLimits(max_inbound_references=0), _representative_document(), "max_inbound_references"),
        (PlmxmlLimits(max_projected_instances=1), _representative_document(), "max_projected_instances"),
        (PlmxmlLimits(max_parse_seconds=0), _representative_document(), "max_parse_seconds"),
    ]
    for limits, payload, expected in cases:
        with pytest.raises(PlmxmlLimitError, match=expected):
            parse_plmxml(io.BytesIO(payload), limits=limits)


def test_algorithm_version_is_explicit_and_representation_location_stays_opaque():
    projection = parse_plmxml(
        io.BytesIO(_representative_document()), algorithm_version="plmxml-projection.v7"
    )
    assert projection.algorithm_version == "plmxml-projection.v7"
    assert projection.stats.total_bytes == len(_representative_document())
    assert projection.stats.element_count > len(projection.instances)
    assert projection.stats.maximum_depth > 0
    assert projection.by_bom_line("W01-89184128/00;1")[0].representation_locations[0].startswith("/opaque/")


def test_incremental_projection_reuses_moved_part_gid_and_preserves_source_refs():
    from plugins.simulation.simulation_backend.application.document_snapshots import project_incremental_vm_snapshot
    from plugins.simulation.simulation_backend.domain.vm_identity import VmObservation
    projection = parse_plmxml(io.BytesIO(_representative_document()))
    item = projection.by_bom_line("W01-89184128/00;1")[0]
    previous = (VmObservation("70", "old", "40", "part", item.item_id, item.bom_line, item.revision,
                              item.catia_occurrence_name, tuple("9" if i == 12 else x for i, x in enumerate(item.normalized_transform))),)
    result = project_incremental_vm_snapshot(projection=projection, previous=previous, session_gid="41",
                                             classify_kind=lambda _item: "part", gid_factory=iter(range(9001, 9010)).__next__)
    match = next(value for value in result.matches if value.observation.catia_occurrence_name == "bolt-left")
    assert match.occurrence_gid == "70" and match.change == "moved"
    assert match.observation.representation_locations == ("/opaque/W01-89184128_00.jt",)
