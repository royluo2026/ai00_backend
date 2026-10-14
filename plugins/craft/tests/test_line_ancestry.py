from plugins.craft.craft_backend.application import project_scope


class Cursor:
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql, params): self.ids = params[1:]
    def fetchall(self):
        data = {'new': {'gid': 'new', 'source_entry_gid': 'old', 'family_gid': 'f'},
                'old': {'gid': 'old', 'source_entry_gid': 'root', 'family_gid': 'f'},
                'root': {'gid': 'root', 'source_entry_gid': None, 'family_gid': 'f'},
                'other': {'gid': 'other', 'source_entry_gid': 'foreign', 'family_gid': 'f'},
                'foreign': {'gid': 'foreign', 'source_entry_gid': None, 'family_gid': 'other-family'}}
        return [data[gid] for gid in self.ids if gid in data]


class Connection:
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def cursor(self): return Cursor()


def test_ancestry_is_bounded_and_never_crosses_bop_family(monkeypatch):
    monkeypatch.setattr('plugins.craft.craft_backend.application.project_scope.get_conn', lambda: Connection())
    assert project_scope.line_ancestor_gids('p', ['new', 'other']) == {'new': ['old', 'root'], 'other': []}
