"""Exercise the actual SELECT against an in-memory SQL fixture, no network."""
import sqlite3

from plugins.craft.craft_backend.capabilities import demo_relation_change as relation


def test_tree_keeps_complete_parent_graph_without_transferring_unused_leaf_metadata():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('CREATE TABLE workmanship_bop_bop_entries (gid TEXT, parent_gid TEXT, node_type TEXT, level INTEGER, sort_order INTEGER, title TEXT, meta TEXT, version_gid TEXT, source_entry_gid TEXT, is_deleted INTEGER)')
    rows = [
        ('holding', None, 'line_process', 1, 0, 'holding', '{"demo_holding":true}', 'clone', None, 0),
        ('p', 'holding', 'process', 2, 0, 'process', '{"anchor":true}', 'clone', 'source-p', 0),
        ('o', 'p', 'operation', 3, 0, 'operation', 'x' * 100000, 'clone', 'source-o', 0),
        ('part', 'o', 'part', 4, 0, 'part', 'y' * 100000, 'clone', 'source-part', 0),
        ('deleted', 'o', 'part', 4, 0, 'deleted', '{}', 'clone', 'source-deleted', 1),
    ]
    conn.executemany('INSERT INTO workmanship_bop_bop_entries VALUES (?,?,?,?,?,?,?,?,?,?)', rows)

    # The production cursor uses MySQL placeholders, but the SQL expression
    # itself is executed here rather than emulated by a fixed-result stub.
    class Cursor:
        def execute(self, sql, parameters):
            self.result = conn.execute(sql.replace('%s', '?'), parameters)
        def fetchall(self):
            return self.result.fetchall()

    info, children = relation._load_tree(Cursor(), 'clone')
    assert set(info) == {'holding', 'p', 'o', 'part'}
    assert children == {None: ['holding'], 'holding': ['p'], 'p': ['o'], 'o': ['part']}
    assert info['holding']['meta'] == '{"demo_holding":true}'
    assert info['p']['meta'] == '{"anchor":true}'
    assert info['o']['meta'] is None and info['part']['meta'] is None
    for row in rows[:4]:
        for name, index in [('gid', 0), ('parent_gid', 1), ('node_type', 2), ('level', 3), ('title', 5), ('version_gid', 7), ('source_entry_gid', 8)]:
            assert info[row[0]][name] == row[index]
    conn.close()
