import sqlite3

from plugins.craft.craft_backend.capabilities import demo_relation_change as relation


class NoQueries:
    def execute(self, *args):
        raise AssertionError('an empty selected operation scope must not scan version links')


def test_empty_selected_operations_do_not_read_links():
    assert relation._existing_operation_part_links(NoQueries(), 'clone', []) == {}


def test_selected_operation_links_are_complete_bounded_and_version_scoped():
    database = sqlite3.connect(':memory:')
    database.row_factory = sqlite3.Row
    database.executescript('''
        CREATE TABLE workmanship_bop_bop_entries(gid TEXT PRIMARY KEY,version_gid TEXT,node_type TEXT,is_deleted INTEGER);
        CREATE TABLE workmanship_bop_bop_entry_links(gid TEXT PRIMARY KEY,entry_gid TEXT,entity_gid TEXT,is_deleted INTEGER,link_type TEXT);
    ''')
    operations = [f'op{i:03}' for i in range(401)]
    database.executemany('INSERT INTO workmanship_bop_bop_entries VALUES(?,?,?,?)', [(gid, 'clone', 'operation', 0) for gid in operations])
    database.executemany('INSERT INTO workmanship_bop_bop_entry_links VALUES(?,?,?,?,?)', [(f'link{i:03}', gid, 'part', 0, 'pbom_part') for i, gid in enumerate(operations)])
    database.executemany('INSERT INTO workmanship_bop_bop_entries VALUES(?,?,?,?)', [('unselected','clone','operation',0), ('foreign','other','operation',0), ('deleted','clone','operation',1), ('process','clone','process',0)])
    database.executemany('INSERT INTO workmanship_bop_bop_entry_links VALUES(?,?,?,?,?)', [(gid, gid, 'part', 0, 'pbom_part') for gid in ('unselected','foreign','deleted','process')])
    database.execute('INSERT INTO workmanship_bop_bop_entry_links VALUES(?,?,?,?,?)', ('deleted-duplicate',operations[0],'part',1,'pbom_part'))
    database.execute('INSERT INTO workmanship_bop_bop_entry_links VALUES(?,?,?,?,?)', ('restore',operations[1],'restore-part',1,'pbom_part'))

    class Cursor:
        def __init__(self): self.calls = []; self.inner = database.cursor()
        def execute(self, sql, params):
            self.calls.append((sql, params))
            self.inner.execute(sql.replace('%s', '?'), params)
        def fetchall(self): return [dict(row) for row in self.inner.fetchall()]

    cursor = Cursor()
    result = relation._existing_operation_part_links(cursor, 'clone', operations + operations[:2] + ['foreign','deleted','process'])
    assert len(result) == 402
    assert result[(operations[0], 'part')]['gid'] == 'link000'
    assert result[(operations[1], 'restore-part')]['gid'] == 'restore'
    assert all(key[0] in operations for key in result)
    assert len(cursor.calls) == 3
    assert all(2 <= len(params) <= 201 and params[0] == 'clone' for _, params in cursor.calls)
    database.close()


def test_connect_without_selected_operations_preserves_real_steps_without_link_scan(monkeypatch):
    info = {
        'line': {'gid':'line','parent_gid':None,'node_type':'line_process','title':'line'},
        'station': {'gid':'station','parent_gid':'line','node_type':'station_process','level':2,'title':'station'},
        'process': {'gid':'process','parent_gid':'station','node_type':'process','level':3,'title':'process'},
        'holding': {'gid':'holding','parent_gid':None,'node_type':'line_process','meta':{'demo_holding':True}},
    }
    children = {'line':['station'], 'station':['process']}
    plan = {'station_codes':{'station':['code']}, 'process_codes':{'code':'process'}, 'process_target_parents':{'code':'station'}, 'operation_part_codes':{}, 'pbom_codes':{}}
    monkeypatch.setattr(relation, '_load_tree', lambda *args: (info,children))
    monkeypatch.setattr(relation, '_relation_plan', lambda *args: plan)
    monkeypatch.setattr(relation, '_pbom_by_demo_code', lambda *args: {})
    result = relation._connect(NoQueries(),'clone','line')
    assert result['line_gid'] == 'line' and result['stations'] == 1
    assert result['processes_moved'] == 0 and result['operations'] == 0 and result['part_links'] == 0
    assert result['steps'][0]['processes'][0]['entry_gid'] == 'process'
