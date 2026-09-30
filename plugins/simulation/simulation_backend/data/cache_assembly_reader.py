"""Internal, pinned assembly projection without transferring unrelated TC properties."""
import json
from .cloud_model_cache_repository import CacheError
from .cached_assembly_projection import build_cached_assembly_projection


def read_assembly(cache, binding, context):
    cache._read(binding['batch_id'], context)
    pins = dict(expected_generation=binding['generation'], expected_snapshot_hash=binding['snapshot_hash'])
    initial = cache.repo.query_pinned(binding['batch_id'], context.team_gid,
        scope='roots', projection='structure', page_size=1, **pins)
    if initial['identity'] != binding:
        raise CacheError('cache_snapshot_mismatch')
    nodes, after = [], ''
    with cache.repo.connect() as conn, conn.cursor() as cursor:
        while True:
            # JSON_SEARCH/EXTRACT work on the deployed OceanBase compatibility layer;
            # JSON_TABLE is not available there. Validate exact names after extraction.
            cursor.execute("""SELECT n.node_key,
                JSON_EXTRACT(n.data_json,'$.structure') AS structure_json,
                JSON_ARRAY(
                    JSON_EXTRACT(n.data_json,REPLACE(JSON_UNQUOTE(JSON_SEARCH(n.data_json,'one','bl_plmxml_occ_xform',NULL,'$.properties_result.raw_fields[*].field')),'.field','')),
                    JSON_EXTRACT(n.data_json,REPLACE(JSON_UNQUOTE(JSON_SEARCH(n.data_json,'one','bl_plmxml_abs_xform',NULL,'$.properties_result.raw_fields[*].field')),'.field','')),
                    JSON_EXTRACT(n.data_json,REPLACE(JSON_UNQUOTE(JSON_SEARCH(n.data_json,'one','IMAN_Rendering',NULL,'$.properties_result.raw_fields[*].field')),'.field',''))
                ) AS fields_json
                FROM workmanship_sim_cloud_cache_nodes n
                WHERE n.batch_id=%s AND n.node_key>%s
                ORDER BY n.node_key LIMIT 500""", (binding['batch_id'], after))
            rows = cursor.fetchall()
            if not rows:
                break
            for row in rows:
                structure = json.loads(row['structure_json'])
                raw_fields = json.loads(row['fields_json'])
                wanted = ('bl_plmxml_occ_xform', 'bl_plmxml_abs_xform', 'IMAN_Rendering')
                if len(raw_fields) != 3 or any(field is not None and field.get('field') != name for field,name in zip(raw_fields,wanted)):
                    raise CacheError('cache_assembly_field_mismatch')
                fields = [field for field in raw_fields if field is not None]
                geometry = next((field for field in fields if field['field']=='IMAN_Rendering'), None)
                refs = json.loads(geometry['value_json']) if geometry and geometry['read_state']=='value' else None
                nodes.append({**structure, 'node_key':row['node_key'], 'geometry_refs':refs,
                    'properties_result':{'raw_fields':fields}})
            after = rows[-1]['node_key']
    if len(nodes) != initial['manifest']['node_count']:
        raise CacheError('cache_snapshot_node_count_mismatch')
    final = cache.repo.query_pinned(binding['batch_id'], context.team_gid,
        scope='roots', projection='structure', page_size=1, **pins)
    if final['identity'] != initial['identity'] or final['manifest']['node_count'] != len(nodes):
        raise CacheError('cache_snapshot_mismatch')
    return {'identity':initial['identity'], 'manifest':initial['manifest'],
            **build_cached_assembly_projection(nodes)}
