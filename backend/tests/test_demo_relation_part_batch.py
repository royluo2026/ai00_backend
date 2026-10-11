from plugins.craft.craft_backend.capabilities.demo_relation_change import _existing_operation_part_links

def test_existing_links_are_loaded_once_from_selected_version_and_active_wins():
    class Cursor:
        queries=[]
        def execute(self,sql,params):
            self.queries.append((sql,params))
            assert 'e.version_gid=%s' in sql and "e.node_type='operation'" in sql
            assert params==('demo-version',)
        def fetchall(self):
            return [{'gid':'active','entry_gid':'op1','entity_gid':'part1','is_deleted':0},
                    {'gid':'deleted','entry_gid':'op1','entity_gid':'part1','is_deleted':1},
                    {'gid':'restore','entry_gid':'op2','entity_gid':'part2','is_deleted':1}]
    cur=Cursor();links=_existing_operation_part_links(cur,'demo-version')
    assert links[('op1','part1')]['gid']=='active'
    assert links[('op2','part2')]['gid']=='restore'
    assert len(cur.queries)==1
