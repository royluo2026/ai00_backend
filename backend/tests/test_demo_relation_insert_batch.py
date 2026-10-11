"""Installed driver, no connection: relation inserts stay bounded and truly batched."""
import math

import pytest
from pymysql.cursors import Cursor, RE_INSERT_VALUES

from plugins.craft.craft_backend.capabilities import demo_relation_change as relation


class OfflineCursor(Cursor):
    def __init__(self):
        self.calls = []
        self.rowcount = 0

    def execute(self, query, args=None):
        self.calls.append((query, args))
        return 1


@pytest.mark.parametrize('row_count', [0, 1, 200, 201, 401])
def test_real_driver_inserts_one_statement_per_bounded_chunk_preserving_values(row_count):
    rows = [(f'gid-{i}', f'entry-{i}', f'part-{i}', '{"fixture":true}', 'version') for i in range(row_count)]
    cur = OfflineCursor()
    relation._insert_part_links(cur, rows)
    assert len(cur.calls) == math.ceil(row_count / 200)
    actual_parameters = []
    for sql, parameters in cur.calls:
        chunk_size = len(parameters) // 5
        assert 1 <= chunk_size <= 200
        assert sql.startswith('INSERT INTO workmanship_bop_bop_entry_links ')
        assert '(gid,entry_gid,link_type,entity_gid,is_primary,is_inherited,snapshot_data,version_gid,created_at)' in sql
        assert sql.count("(%s,%s,'pbom_part',%s,FALSE,FALSE,%s,%s,NOW(6))") == chunk_size
        assert sql.count('%s') == len(parameters) == chunk_size * 5
        actual_parameters.extend(parameters)
    assert actual_parameters == [value for row in rows for value in row]


def test_existing_driver_executemany_reproducer_is_200_individual_execute_calls():
    sql = "INSERT INTO workmanship_bop_bop_entry_links (gid,entry_gid,link_type,entity_gid,is_primary,is_inherited,snapshot_data,version_gid,created_at) VALUES (%s,%s,'pbom_part',%s,FALSE,FALSE,%s,%s,NOW(6))"
    assert not RE_INSERT_VALUES.match(sql)
    cur = OfflineCursor()
    cur.executemany(sql, [('gid', 'entry', 'part', '{}', 'version')] * 200)
    assert len(cur.calls) == 200


def test_connect_uses_batched_insert_without_changing_return_or_generated_identity(monkeypatch):
    from backend.platform_sdk import ids
    monkeypatch.setattr(ids, 'next_gid', lambda: 'generated-gid')
    info = {
        'line': {'node_type': 'line_process', 'level': 1},
        'holding': {'node_type': 'line_process', 'level': 1},
        'station': {'node_type': 'station_process', 'level': 2, 'title': 'station'},
        'process': {'node_type': 'process', 'parent_gid': 'holding', 'level': 2, 'title': 'process'},
        'operation': {'node_type': 'operation', 'parent_gid': 'process', 'level': 3, 'title': 'operation'},
    }
    children = {'line': ['station'], 'holding': ['process'], 'process': ['operation']}
    monkeypatch.setattr(relation, '_load_tree', lambda *args: (info, children))
    monkeypatch.setattr(relation, '_relation_plan', lambda *args: {})
    monkeypatch.setattr(relation, '_holding_line', lambda *args: 'holding')
    monkeypatch.setattr(relation, '_entity_links', lambda *args: {})
    monkeypatch.setattr(relation, '_station_exts', lambda *args: {'station': ['process-code']})
    monkeypatch.setattr(relation, '_steps_exts', lambda *args: {'operation': ['part-code']})
    monkeypatch.setattr(relation, '_process_by_code', lambda *args: {'process-code': 'process'})
    monkeypatch.setattr(relation, '_pbom_by_demo_code', lambda *args: {'part-code': {'gid': 'part'}})
    monkeypatch.setattr(relation, '_existing_operation_part_links', lambda *args: {})
    cur = OfflineCursor()
    result = relation._connect(cur, 'version', 'line')
    inserts = [(sql, parameters) for sql, parameters in cur.calls if sql.startswith('INSERT INTO')]
    assert len(inserts) == 1
    assert inserts[0][1] == ['generated-gid', 'operation', 'part', '{"demo": "w10_relation"}', 'version']
    assert result['ok'] and result['processes_moved'] == result['part_links'] == 1
    assert result['steps'][0]['processes'][0]['entry_gid'] == 'process'
