from plugins.craft.craft_backend.routers._bop import fork
import pytest


@pytest.mark.parametrize('operation', ['stage_advance', 'same_family_fork'])
def test_version_copy_records_the_actual_source_entry(monkeypatch, operation):
    writes = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, args):
            self.sql, self.args = sql, args
            if sql.startswith('INSERT INTO workmanship_bop_bop_entries'):
                columns = sql.split('(', 1)[1].split(')', 1)[0].split(',')
                writes.append(dict(zip([c.strip() for c in columns], args)))
        def fetchone(self):
            if 'pbom_versions' in self.sql: return {'status': 'ready'}
            return {'gid': self.args[0], 'status': 'active', 'project_gid': 'p', 'version_family_gid': 'family'}
        def fetchall(self):
            if 'FROM workmanship_bop_bop_entries' in self.sql:
                return [{'gid':'old-line', 'parent_gid':None, 'node_type':'line_process', 'sort_order':1, 'title':'A'}]
            return []
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def cursor(self): return Cursor()
        def commit(self): pass
    monkeypatch.setattr(fork, 'get_conn', lambda: Connection())
    monkeypatch.setattr(fork, '_snapshot_links', lambda *args: None)
    if operation == 'stage_advance':
        fork._legacy_stage_advance('old-version', fork.StageAdvanceBody(stage_name='new-stage', pbom_version_gid='pbom'))
    else:
        fork._legacy_fork_version('old-version', fork.ForkBody(target_version_tag='v2', target_version_family_gid='family'))
    assert len(writes) == 1
    assert writes[0].get('source_entry_gid') == 'old-line'
