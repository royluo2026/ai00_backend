"""Frozen geometry in world coordinates beneath synthetic logical grouping frames."""
from collections import defaultdict
import math

IDENTITY = [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]

def select_cached_assembly(projection, *, root_node_key=None):
    nodes = projection['nodes']
    by_key = {node['node_key']: node for node in nodes}
    if len(by_key) != len(nodes):
        raise ValueError('cache_node_duplicate')
    children = defaultdict(list)
    for node in nodes:
        parent = node['parent_node_key']
        if parent is not None and parent not in by_key:
            raise ValueError('cache_node_orphan')
        children[parent].append(node['node_key'])
    scope = None
    if root_node_key is not None:
        if root_node_key not in by_key:
            raise ValueError('cache_scope_node_not_found')
        scope, stack = set(), [root_node_key]
        while stack:
            key = stack.pop()
            if key in scope:
                raise ValueError('cache_node_cycle')
            scope.add(key)
            stack.extend(children[key])
    selected, excluded, files, visited = [], [], {}, set()
    pending = sorted(children[None], reverse=True)
    while pending:
        key = pending.pop()
        if key in visited:
            raise ValueError('cache_node_cycle')
        visited.add(key)
        node = by_key[key]
        pending.extend(sorted(children[key], reverse=True))
        if scope is not None and key not in scope:
            continue
        refs = node.get('geometry_refs')
        error = None
        if refs is None:
            error = 'cache_geometry_references_unavailable'
        elif not isinstance(refs, list) or any(
            not isinstance(ref, dict) or not ref.get('dataset_uid') or not ref.get('file_uid')
            or ref.get('relation_type') != 'IMAN_Rendering'
            or not ref.get('file_name', '').lower().endswith('.jt') for ref in refs):
            error = 'cache_geometry_reference_unsupported'
        elif refs:
            expected = 'root_absolute' if node['parent_node_key'] is None else 'source_validated'
            error = node.get('error_code')
            if not error and node.get('transform_state') != expected:
                error = 'cache_transform_unavailable'
            absolute = node.get('absolute_transform')
            if not error and (node.get('absolute_read_state') != 'value'
                    or not isinstance(absolute, (list, tuple)) or len(absolute) != 16
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in absolute)
                    or any(absolute[i] != v for i, v in ((3,0),(7,0),(11,0),(15,1)))):
                error = 'cache_absolute_transform_unavailable'
        if error:
            excluded.append({'node_key': key, 'name': node['name'], 'error_code': error})
        # Every source node stays as a logical group, even if its own geometry is excluded.
        selected.append({**node, 'geometry_refs': [] if error else refs,
                         'parent_node_key': None if key == root_node_key else node['parent_node_key'],
                         'placement_mode': 'synthetic_world_group'})
        if not error:
            for ref in refs:
                identity = (ref['dataset_uid'], ref['file_uid'])
                if identity not in files:
                    files[identity] = {'node_key': key, 'item_revision_uid': node['item_revision_uid'], **ref}
    if len(visited) != len(nodes):
        raise ValueError('cache_node_cycle')
    return {'nodes': selected, 'excluded': excluded,
            'files': [files[key] for key in sorted(files)],
            'placement_mode': 'frozen_absolute_geometry',
            'spatial_authority': dict(projection['spatial_authority'])}


def materialize_cache_nodes(selection, artifacts_by_file, *, reference_field='artifact_refs'):
    """Emit world-frame groups plus separate frozen-absolute geometry children.

    Identity group matrices are presentation frames, never repaired TC transforms.
    Public node_map must be filtered to original selection node keys by the caller.
    """
    result = []
    original = {node['node_key'] for node in selection['nodes']}
    for node in selection['nodes']:
        result.append({**node, 'relative_transform': list(IDENTITY),
                       'geometry_declared': False, reference_field: []})
        refs = node['geometry_refs']
        if not refs:
            continue
        key = 'ai00-geometry:' + node['node_key']
        while key in original:
            key = 'ai00-geometry:' + key
        original.add(key)
        artifacts = []
        for ref in refs:
            artifact = artifacts_by_file.get((ref['dataset_uid'], ref['file_uid']))
            if artifact is None:
                raise ValueError('cache_geometry_artifact_missing')
            artifacts.append(artifact)
        result.append({**node, 'node_key': key, 'parent_node_key': node['node_key'],
                       'relative_transform': list(node['absolute_transform']),
                       'geometry_declared': True, reference_field: artifacts,
                       'placement_mode': 'frozen_absolute_geometry'})
    return result
