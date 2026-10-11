"""Real SQL fixture proves full card fields are read only for the selected page."""
import json
import sqlite3
import pytest

from plugins.craft.craft_backend.services.bop_navigation import BopNavigationRepository


@pytest.mark.parametrize('width', [0, 201, 401])
@pytest.mark.parametrize('cycle', [False, True])
def test_pages_preserve_fields_counts_and_cursor_without_loading_other_lines_metadata(width, cycle):
    sql = sqlite3.connect(':memory:')
    sql.row_factory = sqlite3.Row
    sql.create_function('JSON_UNQUOTE', 1, lambda value: value)
    sql.executescript('''
        CREATE TABLE workmanship_bop_bop_versions (gid TEXT, revision INTEGER, is_deleted INTEGER);
        INSERT INTO workmanship_bop_bop_versions VALUES ('v',7,0);
        CREATE TABLE workmanship_bop_bop_entries (gid TEXT,parent_gid TEXT,node_type TEXT,
          sort_order REAL,title TEXT,vpps TEXT,meta TEXT,process_flow_pic TEXT,
          process_chart_pic TEXT,version_gid TEXT,is_deleted INTEGER);
    ''')
    rows = [
        ('line','b' if cycle else None,'line_process',0,'line',None,'{}','[]','[]','v',0),
        ('a','line','process',1,'first','A',json.dumps({'tc_key':'bom-a','kept':'a'}),'[{"p":1}]','[]','v',0),
        ('b','a','operation',1,'second','B',json.dumps({'kept':'b'}),'[]','[{"c":2}]','v',0),
        ('other',None,'line_process',2,'other',None,'{}','[]','[]','v',0),
        ('huge','other','part',3,'hidden',None,json.dumps({'blob':'x'*200000}),'[]','[]','v',0),
        ('deleted','a','part',3,'deleted',None,'{}','[]','[]','v',1),
        ('foreign','a','part',3,'foreign',None,'{}','[]','[]','other-version',0),
    ]
    rows.extend((f'w{i:04d}','line','process',2,'wide',None,'{}','[]','[]','v',0) for i in range(width))
    sql.executemany('INSERT INTO workmanship_bop_bop_entries VALUES (?,?,?,?,?,?,?,?,?,?,?)', rows)
    transferred = []
    statements = []

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, statement, parameters=()):
            statements.append((statement, parameters))
            # Link-card SQL has independent repository contract tests. This
            # fixture has no links; execute the actual entry SQL unchanged.
            if 'FROM workmanship_bop_bop_entry_links' in statement:
                self.result = []; return
            self.result = [dict(row) for row in sql.execute(statement.replace('%s','?'),parameters).fetchall()]
            if 'FROM workmanship_bop_bop_entries' in statement:
                transferred.extend(self.result)
        def fetchall(self): return self.result
        def fetchone(self): return self.result[0] if self.result else None

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def cursor(self): return Cursor()

    repository = BopNavigationRepository(Connection)
    pages = []; cursor = None
    while True:
        page = repository.get_work_package_page('v',7,'line','line',cursor=cursor,page_size=2 if not width else 200)
        pages.append(page); cursor = page['next_cursor']
        if not cursor: break
    assert all(p['total_count'] == 3 + width for p in pages)
    nodes = [node for page in pages for node in page['nodes']]
    expected = ['line','a','b'] + [f'w{i:04d}' for i in range(width)]
    assert [node['gid'] for node in nodes] == expected
    assert nodes[1]['meta'] == {'tc_key':'bom-a','kept':'a'}
    assert nodes[1]['bom_row_id'] == 'bom-a'
    assert nodes[1]['process_flow_pic'] == [{'p':1}]
    assert nodes[2]['process_chart_pic'] == [{'c':2}]
    detailed = [row for row in transferred if 'meta' in row]
    assert {row['gid'] for row in detailed} == set(expected)
    assert len(detailed) == 3 + width  # Each full card is hydrated once.
    assert all('blob' not in row.get('meta','') for row in detailed)
    assert {row['gid'] for row in transferred} == set(expected)
    child_queries = [(sql, args) for sql, args in statements if 'AND parent_gid IN (' in sql]
    assert child_queries and all('LIMIT 201' in sql and len(args) <= 202 for sql,args in child_queries)
    sql.close()


def test_outline_counts_complete_graph_without_a_redundant_count_scan():
    from plugins.craft.craft_backend.services.bop_navigation import encode_cursor
    sql = sqlite3.connect(':memory:')
    sql.row_factory = sqlite3.Row
    sql.executescript("""
        CREATE TABLE workmanship_bop_bop_versions (gid TEXT,revision INTEGER,is_deleted INTEGER);
        INSERT INTO workmanship_bop_bop_versions VALUES ('v',7,0);
        CREATE TABLE workmanship_bop_bop_entries (gid TEXT,parent_gid TEXT,node_type TEXT,
            sort_order REAL,title TEXT,version_gid TEXT,is_deleted INTEGER);
        INSERT INTO workmanship_bop_bop_entries VALUES
            ('root',NULL,'factory_bop',0,'root','v',0),
            ('l1','root','line_process',1,'one','v',0),
            ('l2','root','line_process',2,'two','v',0),
            ('l3','root','line_process',3,'three','v',0),
            ('s1','l1','station_process',4,'station','v',0),
            ('s3','l3','station_process',5,'station','v',0);
    """)
    statements = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def execute(self,statement,parameters=()):
            statements.append(statement)
            self.rows = [dict(r) for r in sql.execute(statement.replace('%s','?'),parameters).fetchall()]
        def fetchall(self): return self.rows
        def fetchone(self): return self.rows[0] if self.rows else None
    class Connection:
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def cursor(self): return Cursor()
    repo = BopNavigationRepository(Connection)
    first = repo.get_outline_page('v',7,cursor=None,page_size=2)
    assert first['total_lines'] == 3
    assert [r['gid'] for r in first['lines']] == ['l1','l2']
    assert first['lines'][0]['counts']['stations'] == 1
    assert first['lines'][1]['counts']['stations'] == 0
    assert first['next_cursor'] == encode_cursor(2,'l2')
    empty = repo.get_outline_page('v',7,cursor=encode_cursor(3,'l3'),page_size=2)
    assert empty['total_lines'] == 3 and empty['lines'] == [] and empty['next_cursor'] is None
    assert not any('COUNT(' in statement for statement in statements)
    sql.close()
