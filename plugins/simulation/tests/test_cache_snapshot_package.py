import copy
import hashlib
import io
from xml.etree import ElementTree as ET

import pytest

from plugins.simulation.simulation_backend.domain.cache_snapshot_package import (
    CacheSnapshotPackageError, build_cache_snapshot_package,
)
from plugins.simulation.simulation_backend.domain.plmxml_projection import parse_plmxml


IDENTITY = dict(batch_id='a' * 32, generation='b' * 32,
                snapshot_hash='sha256:' + 'c' * 64, schema_version=1)
SPATIAL = dict(status='verified', unit='mm', layout='row_major',
               vector_convention='row_vector', reference_frame='parent', direction='local_to_parent')
ARTIFACT = dict(artifact_id='jt-1', media_type='model/jt', sha256='d' * 64, byte_size=32, version=1)
MATRIX = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def nodes():
    result = [dict(node_key=key, parent_node_key=parent, name='Part <&>', item_revision_uid='same-revision',
                   relative_transform=MATRIX.copy(), geometry_declared=parent is not None,
                   artifact_refs=[ARTIFACT.copy()] if parent else [])
              for key, parent in [('root', None), ('a', 'root'), ('b', 'root'), ('nested', 'a')]]
    result[0]['relative_transform'][12] = 1000
    result[1]['relative_transform'] = [0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1, 0, 200, 300, 400, 1]
    result[2]['relative_transform'][12] = 500
    result[3]['relative_transform'][13] = 700
    return result


def build(rows=None, spatial=None):
    return build_cache_snapshot_package(identity=IDENTITY, nodes=nodes() if rows is None else rows,
                                        spatial_semantics=SPATIAL if spatial is None else spatial)


def test_bom_item_id_is_preserved_in_native_instance_and_revision_metadata():
    rows = nodes()
    rows[1]['name'] = 'LDP-25030016/01;1-油箱供油管总成III(OIL SUPPLY PIPE ASSY III)'
    package = build(rows)
    xml = ET.fromstring(package.plmxml)
    ns = {'p': 'http://www.plmxml.org/Schemas/PLMXMLSchema'}
    identity = package.node_map['a']['instance_id']
    for tag, gid in [('ProductInstance', identity), ('ProductRevisionView', 'view-' + identity)]:
        element = xml.find(f'.//p:{tag}[@id="{gid}"]', ns)
        metadata = element.find('p:UserData/p:UserValue[@title="itemId"]', ns)
        assert metadata is not None
        assert metadata.attrib['value'] == 'LDP-25030016'
    # A display label without a BOM item/revision prefix cannot invent an identity.
    root = xml.find(f'.//p:ProductInstance[@id="{package.node_map["root"]["instance_id"]}"]', ns)
    assert root.find('p:UserData/p:UserValue[@title="itemId"]', ns) is None


def test_environment_instance_ids_survive_subtree_opens_and_rename_but_not_another_insertion():
    context = dict(workspace_gid='10', document_gid='20', name='W10 test2')
    def export(rows, **changes):
        return build_cache_snapshot_package(identity=IDENTITY, nodes=rows, spatial_semantics=SPATIAL,
                                            environment={**context, **changes})
    whole = export(nodes())
    subtree = copy.deepcopy(nodes()[2:3])
    subtree[0]['parent_node_key'] = None
    selected = export(subtree)
    assert whole.node_map['b']['instance_id'] == selected.node_map['b']['instance_id']
    assert export(nodes(), name='Renamed').node_map == whole.node_map
    assert export(nodes(), document_gid='21').node_map['b']['instance_id'] != selected.node_map['b']['instance_id']
    assert export(nodes(), workspace_gid='11').node_map['b']['instance_id'] != selected.node_map['b']['instance_id']


def test_roundtrip_preserves_repeated_instances_nested_transforms_and_one_dependency():
    package = build()
    parsed = parse_plmxml(io.BytesIO(package.plmxml))
    by_id = {item.instance_id: item for item in parsed.instances}
    assert len(by_id) == 4 and len(package.dependencies) == 1
    assert package.content_hash == 'sha256:' + hashlib.sha256(package.plmxml).hexdigest()
    root, a, b, nested = [by_id[package.node_map[key]['instance_id']] for key in ('root', 'a', 'b', 'nested')]
    assert root.normalized_transform[12] == '1'
    assert tuple(float(value) for value in a.transform_raw) == (0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1, 0, .2, .3, .4, 1)
    assert b.normalized_transform[12] == '0.5'
    assert nested.normalized_transform[13] == '0.7'
    assert nested.parent_instance_id == a.instance_id
    assert package.node_map['nested']['instance_path'] == [root.instance_id, a.instance_id, nested.instance_id]
    # A nested origin is rotated by its parent, then translated by that parent
    # and by the explicit root. This catches lost parents and transposed matrices.
    point = [0, 0, 0, 1]
    for placement in (nested, a, root):
        matrix = [float(value) for value in placement.transform_raw]
        point = [sum(point[row] * matrix[row * 4 + col] for row in range(4)) for col in range(4)]
    assert point == pytest.approx([.5, .3, .4, 1])
    assert a.representation_locations == b.representation_locations == nested.representation_locations
    assert root.representation_locations == ()
    ns = {'p': 'http://www.plmxml.org/Schemas/PLMXMLSchema'}
    xml = ET.fromstring(package.plmxml)
    for instance in xml.findall('.//p:ProductInstance', ns):
        assert instance.find("p:UserData/p:UserValue[@title='bl_occurrence_uid']", ns).get('value') == instance.get('id')
        # PLMXML InstanceBase extends attributes with spatial data: order matters
        # to native importers even though ElementTree's lookup ignores it.
        assert [child.tag.rsplit('}',1)[-1] for child in instance]==['UserData','Transform']


def test_deterministic_across_input_order_without_mutation():
    rows = nodes()
    original = copy.deepcopy(rows)
    assert build(rows) == build(list(reversed(rows)))
    assert rows == original
    assert build().dependencies[0]['package_path'] == 'dependencies/' + 'd' * 64 + '.jt'


def test_native_root_identity_survives_import_that_keeps_only_revision_view_metadata():
    # VisMockup 14 imports root view properties but drops root instance properties.
    # Two roots can share a revision; their mapping must still use instance identity.
    rows = nodes()
    rows[2]['parent_node_key'] = None
    package = build(rows)
    ns = {'p': 'http://www.plmxml.org/Schemas/PLMXMLSchema'}
    xml = ET.fromstring(package.plmxml)
    roots = xml.find('.//p:InstanceGraph', ns).get('rootRefs').split()
    for instance_id in roots:
        instance = xml.find(f".//p:ProductInstance[@id='{instance_id}']", ns)
        view_id = instance.get('partRef').removeprefix('#')
        view = xml.find(f".//p:ProductRevisionView[@id='{view_id}']", ns)
        native_properties = {item.get('title'): item.get('value')
                             for item in view.findall('p:UserData/p:UserValue', ns)}
        assert native_properties.get('bl_occurrence_uid') == instance_id
    assert len(set(roots)) == 2


@pytest.mark.parametrize('mutation', ['missing_transform', 'root_transform', 'nan', 'perspective', 'orphan',
                                     'duplicate', 'cycle', 'missing_file', 'invalid_hash', 'non_jt'])
def test_rejects_incomplete_or_ambiguous_inputs(mutation):
    rows = nodes()
    if mutation == 'missing_transform': rows[1]['relative_transform'] = None
    elif mutation == 'root_transform': rows[0].pop('relative_transform')
    elif mutation == 'nan': rows[1]['relative_transform'][12] = float('nan')
    elif mutation == 'perspective': rows[1]['relative_transform'][3] = 1
    elif mutation == 'orphan': rows[1]['parent_node_key'] = 'missing'
    elif mutation == 'duplicate': rows.append(rows[1].copy())
    elif mutation == 'cycle': rows[0]['parent_node_key'] = 'nested'
    elif mutation == 'missing_file': rows[1]['artifact_refs'] = []
    elif mutation == 'invalid_hash': rows[1]['artifact_refs'][0]['sha256'] = '../bad'
    elif mutation == 'non_jt': rows[1]['artifact_refs'][0]['media_type'] = 'image/png'
    with pytest.raises(CacheSnapshotPackageError): build(rows)


@pytest.mark.parametrize('key,value', [('status', 'unverified'), ('unit', None), ('layout', 'column_major'),
                                      ('reference_frame', 'world'), ('direction', 'parent_to_local'),
                                      ('vector_convention', 'column_vector')])
def test_requires_explicit_supported_spatial_semantics(key, value):
    with pytest.raises(CacheSnapshotPackageError): build(spatial={**SPATIAL, key: value})


def test_metres_are_not_scaled_and_snapshot_identity_is_required():
    package = build(spatial={**SPATIAL, 'unit': 'm'})
    parsed = parse_plmxml(io.BytesIO(package.plmxml))
    root = next(item for item in parsed.instances if item.instance_id == package.node_map['root']['instance_id'])
    assert root.normalized_transform[12] == '1000'
    legacy = build_cache_snapshot_package(identity={**IDENTITY, 'snapshot_hash': None}, nodes=nodes(), spatial_semantics=SPATIAL)
    assert b'&quot;snapshot_hash&quot;:null' in legacy.plmxml
    assert legacy.node_map != package.node_map


def test_documented_units_require_explicit_evidence_without_claiming_installation_verification():
    with pytest.raises(CacheSnapshotPackageError): build(spatial={**SPATIAL, 'status':'documented'})
    assert build(spatial={**SPATIAL,'status':'documented','evidence_ref':'Siemens PLM00048 12.1 3-28'}).plmxml
