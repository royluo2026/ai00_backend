"""Pure cached assembly export; callers must verify spatial semantics and file membership.

Transforms are affine row-vector, row-major local-to-parent matrices. Every
occurrence, including roots, needs an explicit matrix. Output translations are
metres. This module neither resolves Teamcenter data nor opens a viewer.
"""
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence
from xml.etree import ElementTree as ET


class CacheSnapshotPackageError(ValueError):
    pass


@dataclass(frozen=True)
class CachedSnapshotPackage:
    plmxml: bytes
    content_hash: str
    dependencies: tuple[dict[str, Any], ...]
    node_map: dict[str, dict[str, Any]]


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and not re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]', value)


def build_cache_snapshot_package(*, identity: Mapping[str, Any], nodes: Sequence[Mapping[str, Any]],
                                 spatial_semantics: Mapping[str, Any], environment: Mapping[str, str] | None = None,
                                 tc_dependencies: bool = False) -> CachedSnapshotPackage:
    """Return deterministic XML, hash-named JT dependencies and occurrence map.

    Each node requires node_key, parent_node_key, name, item_revision_uid,
    relative_transform, geometry_declared and artifact_refs. Geometry declarations
    are explicit: callers must not turn unavailable geometry into an empty list.
    Artifact refs are already-authorized immutable refs from exact file acquisition.
    """
    required = dict(layout='row_major', vector_convention='row_vector',
                    reference_frame='parent', direction='local_to_parent')
    documented = spatial_semantics.get('status') == 'documented' and bool(spatial_semantics.get('evidence_ref'))
    if (spatial_semantics.get('status') != 'verified' and not documented
            or any(spatial_semantics.get(key) != value for key, value in required.items()) or spatial_semantics.get('unit') not in ('m', 'mm')):
        raise CacheSnapshotPackageError('cache_spatial_semantics_unsupported')
    if (not isinstance(identity.get('batch_id'), str) or not re.fullmatch('[a-f0-9]{32}', identity['batch_id'])
            or identity.get('generation') is not None and not re.fullmatch('[a-f0-9]{32}', str(identity['generation']))
            or identity.get('snapshot_hash') is not None and not re.fullmatch('sha256:[a-f0-9]{64}', str(identity['snapshot_hash']))
            or type(identity.get('schema_version')) is not int or identity['schema_version'] != 1):
        raise CacheSnapshotPackageError('cache_snapshot_identity_invalid')
    if not nodes:
        raise CacheSnapshotPackageError('cache_snapshot_empty')
    pinned = {key: identity[key] for key in ('batch_id', 'generation', 'snapshot_hash', 'schema_version')}
    rows, transforms, geometry, artifacts = {}, {}, {}, {}
    for node in nodes:
        key = node.get('node_key')
        if not _text(key) or key in rows:
            raise CacheSnapshotPackageError('cache_node_identity_invalid')
        if ('parent_node_key' not in node or (node['parent_node_key'] is not None and not _text(node['parent_node_key']))
                or not _text(node.get('item_revision_uid')) or not _text(node.get('name'))):
            raise CacheSnapshotPackageError('cache_node_metadata_invalid')
        matrix = node.get('relative_transform')
        if (not isinstance(matrix, (list, tuple)) or len(matrix) != 16
                or any(type(value) not in (int, float) or not math.isfinite(value) for value in matrix)
                or any(matrix[index] != expected for index, expected in ((3, 0), (7, 0), (11, 0), (15, 1)))):
            raise CacheSnapshotPackageError('cache_relative_transform_invalid')
        values = [Decimal(str(value)) for value in matrix]
        if spatial_semantics['unit'] == 'mm':
            for index in (12, 13, 14): values[index] /= 1000
        transforms[key] = ' '.join('0' if value == 0 else format(value.normalize(), 'f') for value in values)
        refs = node.get('tc_file_refs' if tc_dependencies else 'artifact_refs')
        if (type(node.get('geometry_declared')) is not bool or not isinstance(refs, (list, tuple))
                or bool(refs) != node['geometry_declared']):
            raise CacheSnapshotPackageError('cache_geometry_files_missing_or_undeclared')
        geometry[key] = set()
        for ref in refs:
            if not isinstance(ref, Mapping):
                raise CacheSnapshotPackageError('cache_geometry_artifact_invalid')
            if tc_dependencies:
                if (set(ref) != {'dependency_key','endpoint_id','dataset_uid','file_uid','file_name','relation_type'}
                        or not all(_text(ref.get(k)) for k in ref)
                        or not re.fullmatch('[a-f0-9]{64}',ref['dependency_key'])
                        or ref['relation_type']!='IMAN_Rendering' or not ref['file_name'].lower().endswith('.jt')
                        or re.search(r'[\\/\x00-\x1f]',ref['file_name'])):
                    raise CacheSnapshotPackageError('cache_tc_dependency_invalid')
                digest=ref['dependency_key']
                if digest in artifacts and artifacts[digest]!=ref:
                    raise CacheSnapshotPackageError('cache_tc_dependency_conflict')
                artifacts[digest]=dict(ref);geometry[key].add(digest)
                continue
            digest = str(ref.get('sha256', '')).removeprefix('sha256:')
            if (not re.fullmatch('[a-f0-9]{64}', digest) or not _text(ref.get('artifact_id'))
                    or ref.get('media_type') not in ('model/jt', 'model/vnd.jt')
                    or type(ref.get('byte_size')) is not int or ref['byte_size'] < 24
                    or type(ref.get('version')) is not int or ref['version'] < 1):
                raise CacheSnapshotPackageError('cache_geometry_artifact_invalid')
            saved = artifacts.get(digest)
            if saved is not None and saved['byte_size'] != ref['byte_size']:
                raise CacheSnapshotPackageError('cache_geometry_artifact_conflict')
            candidate = {field: ref[field] for field in ('artifact_id', 'media_type', 'sha256', 'byte_size', 'version')}
            if saved is None or _canonical(candidate) < _canonical(saved): artifacts[digest] = candidate
            geometry[key].add(digest)
        rows[key] = node
    children = {key: [] for key in rows}
    roots = []
    for key, node in rows.items():
        parent = node['parent_node_key']
        if parent is None: roots.append(key)
        elif parent not in rows: raise CacheSnapshotPackageError('cache_node_orphan')
        else: children[parent].append(key)
    # Parent-first traversal proves the graph is a forest and avoids recursion limits.
    ordered, paths = [], {}
    pending = [(key, []) for key in sorted(roots, reverse=True)]
    while pending:
        key, path = pending.pop()
        ordered.append(key)
        paths[key] = path + [key]
        pending.extend((child, paths[key]) for child in sorted(children[key], reverse=True))
    if len(ordered) != len(rows): raise CacheSnapshotPackageError('cache_node_cycle')
    if environment is not None and (not _text(environment.get('name')) or any(
            not re.fullmatch(r'[1-9][0-9]*', str(environment.get(field, '')))
            for field in ('workspace_gid', 'document_gid'))):
        raise CacheSnapshotPackageError('cache_environment_identity_invalid')
    namespace = [pinned, environment['workspace_gid'], environment['document_gid']] if environment else pinned
    ids = {key: 'instance-' + hashlib.sha256(_canonical([namespace, key]).encode()).hexdigest() for key in rows}
    node_map = {key: {'instance_id': ids[key], 'instance_path': [ids[item] for item in paths[key]]} for key in ordered}
    ns = 'http://www.plmxml.org/Schemas/PLMXMLSchema'
    root = ET.Element('PLMXML', dict(xmlns=ns, schemaVersion='6', author='AI00', units='metre'))
    metadata = ET.SubElement(root, 'UserData', {'id': 'snapshot-metadata'})
    ET.SubElement(metadata, 'UserValue', {'title': 'ai00_snapshot_identity', 'value': _canonical(pinned)})
    if environment:
        root.set('name', environment['name'])
        for title, value in [('ai00_environment_gid', environment['workspace_gid']),
                             ('ai00_source_document_gid', environment['document_gid']),
                             ('ai00_cache_layout', 'frozen_absolute_geometry.v1')]:
            ET.SubElement(metadata, 'UserValue', {'title': title, 'value': value})
    product = ET.SubElement(root, 'ProductDef', {'id': 'cached-product'})
    graph = ET.SubElement(product, 'InstanceGraph', {'id': 'cached-graph', 'rootRefs': ' '.join(ids[key] for key in sorted(roots))})
    for key in ordered:
        node, instance_id = rows[key], ids[key]
        instance = ET.SubElement(graph, 'ProductInstance', {'id': instance_id, 'name': node['name'], 'partRef': '#view-' + instance_id})
        user = ET.SubElement(instance, 'UserData', {'id': 'metadata-' + instance_id})
        ET.SubElement(user, 'UserValue', {'title': 'bl_occurrence_uid', 'value': instance_id})
        ET.SubElement(instance, 'Transform', {'id': 'transform-' + instance_id}).text = transforms[key]
        attrs = {'id': 'view-' + instance_id, 'name': node['name']}
        if children[key]: attrs['instanceRefs'] = ' '.join(ids[child] for child in sorted(children[key]))
        view = ET.SubElement(graph, 'ProductRevisionView', attrs)
        user = ET.SubElement(view, 'UserData', {'id': 'revision-metadata-' + instance_id})
        ET.SubElement(user, 'UserValue', {'title': 'item_revision_uid', 'value': node['item_revision_uid']})
        if node['parent_node_key'] is None:
            # VisMockup 14 keeps the root view's metadata, but drops the root
            # ProductInstance metadata. Views here are per occurrence, so this
            # preserves the exact root identity even for repeated revisions.
            ET.SubElement(user, 'UserValue', {'title': 'bl_occurrence_uid', 'value': instance_id})
        for digest in sorted(geometry[key]):
            ET.SubElement(view, 'Representation', {'id': 'representation-' + instance_id + '-' + digest,
                          'format': 'JT', 'location': 'dependencies/' + digest + '.jt'})
    content = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    return CachedSnapshotPackage(content, 'sha256:' + hashlib.sha256(content).hexdigest(),
                                 tuple({'package_path': 'dependencies/' + digest + '.jt', 'file_ref' if tc_dependencies else 'artifact_ref': artifacts[digest]}
                                       for digest in sorted(artifacts)), node_map)
