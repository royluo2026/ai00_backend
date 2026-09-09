from plugins.craft.craft_backend.data.bop_fork_mysql import MysqlBopForkStore


class Cursor:
    def __init__(self, source_repository="401"):
        self.source_repository=source_repository;self.rows=[];self.executed=[]
    def execute(self,sql,args=()):
        self.executed.append((sql,args))
        if "SELECT s.repository_gid" in sql:self.rows=[{"repository_gid":self.source_repository}]
        elif "FROM workmanship_craft_bop_space_version_members m LEFT JOIN" in sql:
            self.rows=[{"logical_gid":"101","node_revision_gid":"201","binding_revision_gid":None,
                "vpps_group_version_gid":None,"member_kind":"node","is_tombstone":0,
                "parent_node_gid":None,"node_type":"line_process","order_key":"0001",
                "properties_json":"{}","lineage_gid":"301"}]
        elif "JOIN workmanship_craft_bop_nodes n" in sql:
            self.rows=[{"logical_gid":"101","node_revision_gid":"201","lineage_gid":"301",
                "parent_node_gid":None,"node_type":"line_process","order_key":"0001",
                "properties_json":"{}","content_hash":"sha256:x","evidence_refs_json":"[]"}]
        elif "JOIN workmanship_craft_bop_bindings b" in sql:self.rows=[]
        elif "JOIN workmanship_craft_bop_vpps_groups g" in sql:self.rows=[]
        else:self.rows=[]
    def fetchone(self):return self.rows[0] if self.rows else None
    def fetchall(self):return list(self.rows)


def test_personal_fork_inside_repository_reuses_logical_node_and_revision():
    cursor=Cursor("401");store=MysqlBopForkStore()
    result=store._reuse_version(cursor,source_version_gid="501",repository_gid="401",
        space_head_gid="601",run_gid="701",fork_depth="all",tenant_gid="20")
    inserts=[(sql,args) for sql,args in cursor.executed if sql.startswith("INSERT")]
    assert result["copied_node_count"]==1
    assert not any("workmanship_craft_bop_nodes " in sql for sql,_ in inserts)
    member=next(args for sql,args in inserts if "space_head_members" in sql)
    assert member[3]=="101" and member[4]=="201"


def test_cross_repository_fork_allocates_new_gid_and_keeps_lineage():
    cursor=Cursor("400");store=MysqlBopForkStore()
    store._copy_version(cursor,source_version_gid="501",repository_gid="402",
        space_head_gid="601",run_gid="701",fork_depth="all",tenant_gid="20",actor_gid="30")
    node_insert=next(args for sql,args in cursor.executed if sql.startswith("INSERT INTO workmanship_craft_bop_nodes "))
    assert node_insert[0]!="101"
    assert node_insert[3]=="301" and node_insert[4]=="101"
    assert node_insert[5]=="400" and node_insert[6]=="501"


def test_large_cross_repository_fork_batches_database_writes():
    class ManyCursor(Cursor):
        def execute(self, sql, args=()):
            super().execute(sql, args)
            if "JOIN workmanship_craft_bop_nodes n" in sql:
                self.rows=[{
                    "logical_gid":str(1000+i),"node_revision_gid":str(2000+i),
                    "lineage_gid":str(3000+i),"parent_node_gid":None,
                    "node_type":"process","order_key":str(i),"properties_json":"{}",
                    "content_hash":"sha256:x","evidence_refs_json":"[]",
                } for i in range(500)]

    cursor=ManyCursor("400")
    result=MysqlBopForkStore()._copy_version(
        cursor,source_version_gid="501",repository_gid="402",space_head_gid="601",
        run_gid="701",fork_depth="all",tenant_gid="20",actor_gid="30",
    )
    insert_count=sum(sql.startswith("INSERT") for sql,_ in cursor.executed)
    assert result["copied_node_count"]==500
    assert insert_count <= 12
