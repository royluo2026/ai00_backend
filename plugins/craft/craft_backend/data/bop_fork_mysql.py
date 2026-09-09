"""Transactional MySQL persistence for two-stage BOP Fork workflows."""
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from backend.platform_sdk.ids import next_gid
from .bop_fork import BopForkError, _hash
from .connection import get_craft_conn


def _decode(value): return json.loads(value) if isinstance(value,str) else value


def _bulk_insert(cur, statement, rows, batch_size=200):
    if not rows:return
    prefix,row_sql=statement.split(" VALUES ",1)
    for offset in range(0,len(rows),batch_size):
        batch=rows[offset:offset+batch_size]
        cur.execute(prefix+" VALUES "+",".join([row_sql]*len(batch)),tuple(value for row in batch for value in row))


class MysqlBopForkStore:
    DEPTHS={"all","operation","process","role","station"}
    def __init__(self,connection_factory=get_craft_conn): self._connect=connection_factory
    @staticmethod
    def _level(node_type):
        return {"line":0,"line_process":0,"station":1,"station_process":1,
                "role":2,"operator_process":2,"process":3,"operation":4}.get(str(node_type),99)
    def _copy_version(self,cur,*,source_version_gid,repository_gid,space_head_gid,run_gid,
                      fork_depth,tenant_gid,actor_gid):
        max_level={"station":1,"role":2,"process":3,"operation":4,"all":99}[fork_depth]
        cur.execute("SELECT s.repository_gid FROM workmanship_craft_bop_space_versions v JOIN workmanship_craft_bop_spaces s ON s.gid=v.space_gid WHERE v.gid=%s AND v.tenant_gid=%s AND s.deleted_at IS NULL",(source_version_gid,tenant_gid)); source=cur.fetchone()
        if not source:raise BopForkError("space_version_not_found")
        source_repository_gid=str(source["repository_gid"])
        cur.execute("SELECT m.logical_gid,m.node_revision_gid,n.lineage_gid,r.parent_node_gid,r.node_type,r.order_key,r.properties_json,r.content_hash,r.evidence_refs_json FROM workmanship_craft_bop_space_version_members m JOIN workmanship_craft_bop_nodes n ON n.gid=m.logical_gid JOIN workmanship_craft_bop_node_revisions r ON r.gid=m.node_revision_gid WHERE m.space_version_gid=%s AND m.member_kind='node' AND m.is_tombstone=0 ORDER BY r.node_type,r.order_key,m.logical_gid",(source_version_gid,)); source_nodes=[dict(row) for row in cur.fetchall()]
        included=[row for row in source_nodes if self._level(row["node_type"])<=max_level]
        node_map={str(row["logical_gid"]):str(next_gid()) for row in included}; revision_map={str(row["logical_gid"]):str(next_gid()) for row in included}
        member_refs=[];nodes=[];revisions=[];head_members=[]
        for row in included:
            old=str(row["logical_gid"]); node_gid=node_map[old]; revision_gid=revision_map[old]
            parent=str(row["parent_node_gid"]) if row["parent_node_gid"] is not None else None
            parent_gid=node_map.get(parent) if parent else None
            lineage=str(row["lineage_gid"] or old)
            nodes.append((node_gid,repository_gid,tenant_gid,lineage,old,source_repository_gid,source_version_gid,actor_gid))
            revisions.append((revision_gid,node_gid,tenant_gid,parent_gid,row["node_type"],row["order_key"],row["properties_json"],row["content_hash"],actor_gid,row["evidence_refs_json"]))
            head_members.append((str(next_gid()),space_head_gid,node_gid,revision_gid));member_refs.append(("node",node_gid,revision_gid))
        _bulk_insert(cur,"INSERT INTO workmanship_craft_bop_nodes (gid,repository_gid,tenant_gid,lineage_gid,derived_from_node_gid,source_repository_gid,source_version_gid,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",nodes)
        _bulk_insert(cur,"INSERT INTO workmanship_craft_bop_node_revisions (gid,node_gid,tenant_gid,parent_node_gid,node_type,order_key,properties_json,content_hash,actor_gid,actor_type,evidence_refs_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'user',%s)",revisions)
        _bulk_insert(cur,"INSERT INTO workmanship_craft_bop_space_head_members (gid,space_head_gid,member_kind,logical_gid,node_revision_gid,is_tombstone) VALUES (%s,%s,'node',%s,%s,0)",head_members)
        blueprint_map={}
        blueprints=[]
        for row in source_nodes:
            old=str(row["logical_gid"])
            if old in node_map:continue
            props=_decode(row["properties_json"]) or {}; vpps=props.get("vpps_gid") or props.get("vpps")
            if not str(vpps or "").isdigit():continue
            blueprint_map[old]=str(next_gid())
        for row in source_nodes:
            old=str(row["logical_gid"])
            if old not in blueprint_map:continue
            props=_decode(row["properties_json"]) or {}; vpps=str(props.get("vpps_gid") or props.get("vpps"))
            parent=str(row["parent_node_gid"]) if row["parent_node_gid"] is not None else None
            blueprints.append((blueprint_map[old],run_gid,old,str(row["lineage_gid"] or old),blueprint_map.get(parent),vpps,row["node_type"],row["order_key"]))
        _bulk_insert(cur,"INSERT INTO workmanship_craft_bop_fork_blueprint_nodes (gid,fork_run_gid,source_node_gid,source_node_lineage_gid,parent_blueprint_gid,vpps_gid,node_level,order_key) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",blueprints)
        if fork_depth=="all":
            cur.execute("SELECT m.logical_gid,b.lineage_gid,r.source_node_gid,r.target_ref_kind,r.target_ref_gid,r.binding_role,r.properties_json,r.content_hash,r.evidence_refs_json FROM workmanship_craft_bop_space_version_members m JOIN workmanship_craft_bop_bindings b ON b.gid=m.logical_gid JOIN workmanship_craft_bop_binding_revisions r ON r.gid=m.binding_revision_gid WHERE m.space_version_gid=%s AND m.member_kind='binding' AND m.is_tombstone=0 ORDER BY m.logical_gid",(source_version_gid,))
            bindings=[];binding_revisions=[];binding_members=[]
            for row in cur.fetchall():
                source_node=node_map.get(str(row["source_node_gid"])); old=str(row["logical_gid"])
                if not source_node:continue
                binding_gid,revision_gid=str(next_gid()),str(next_gid())
                bindings.append((binding_gid,repository_gid,tenant_gid,str(row["lineage_gid"] or old),old,actor_gid))
                binding_revisions.append((revision_gid,binding_gid,tenant_gid,source_node,row["target_ref_kind"],row["target_ref_gid"],row["binding_role"],row["properties_json"],row["content_hash"],actor_gid,row["evidence_refs_json"]))
                binding_members.append((str(next_gid()),space_head_gid,binding_gid,revision_gid));member_refs.append(("binding",binding_gid,revision_gid))
            _bulk_insert(cur,"INSERT INTO workmanship_craft_bop_bindings (gid,repository_gid,tenant_gid,lineage_gid,derived_from_binding_gid,created_by) VALUES (%s,%s,%s,%s,%s,%s)",bindings)
            _bulk_insert(cur,"INSERT INTO workmanship_craft_bop_binding_revisions (gid,binding_gid,tenant_gid,source_node_gid,target_ref_kind,target_ref_gid,binding_role,properties_json,content_hash,actor_gid,evidence_refs_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",binding_revisions)
            _bulk_insert(cur,"INSERT INTO workmanship_craft_bop_space_head_members (gid,space_head_gid,member_kind,logical_gid,binding_revision_gid,is_tombstone) VALUES (%s,%s,'binding',%s,%s,0)",binding_members)
        cur.execute("SELECT m.logical_gid,m.vpps_group_version_gid,g.boundary_node_gid,g.group_lineage_gid,v.root_scope_gid,v.content_hash,v.evidence_refs_json FROM workmanship_craft_bop_space_version_members m JOIN workmanship_craft_bop_vpps_groups g ON g.gid=m.logical_gid JOIN workmanship_craft_bop_vpps_group_versions v ON v.gid=m.vpps_group_version_gid WHERE m.space_version_gid=%s AND m.member_kind='vpps' AND m.is_tombstone=0 ORDER BY m.logical_gid",(source_version_gid,))
        for source_group in [dict(row) for row in cur.fetchall()]:
            boundary=node_map.get(str(source_group["boundary_node_gid"]))
            if not boundary:continue
            group_gid,version_gid=str(next_gid()),str(next_gid())
            root=node_map.get(str(source_group["root_scope_gid"]),boundary)
            cur.execute("INSERT INTO workmanship_craft_bop_vpps_groups (gid,space_gid,boundary_node_gid,group_lineage_gid,derived_from_group_gid,reference_group_version_gid,current_group_version_gid) VALUES (%s,(SELECT space_gid FROM workmanship_craft_bop_space_heads WHERE gid=%s),%s,%s,%s,%s,%s)",(group_gid,space_head_gid,boundary,str(source_group["group_lineage_gid"] or source_group["logical_gid"]),source_group["logical_gid"],version_gid,version_gid))
            cur.execute("INSERT INTO workmanship_craft_bop_vpps_group_versions (gid,target_group_gid,version_kind,reference_version_gid,root_scope_gid,generation_status,content_hash,actor_gid,actor_type,evidence_refs_json) VALUES (%s,%s,'reference',%s,%s,'ready',%s,%s,'user',%s)",(version_gid,group_gid,source_group["vpps_group_version_gid"],root,source_group["content_hash"],actor_gid,source_group["evidence_refs_json"]))
            cur.execute("SELECT vpps_gid,parent_scope_gid,node_level,order_key,source_bop_node_gid,source_node_lineage_gid FROM workmanship_craft_bop_vpps_group_members WHERE group_version_gid=%s ORDER BY parent_scope_gid,order_key,gid",(source_group["vpps_group_version_gid"],))
            for member in cur.fetchall():
                parent_scope=node_map.get(str(member["parent_scope_gid"]),root);source_node=node_map.get(str(member["source_bop_node_gid"])) if member["source_bop_node_gid"] is not None else None
                cur.execute("INSERT INTO workmanship_craft_bop_vpps_group_members (gid,group_version_gid,vpps_gid,parent_scope_gid,node_level,order_key,source_bop_node_gid,source_node_lineage_gid) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",(str(next_gid()),version_gid,member["vpps_gid"],parent_scope,member["node_level"],member["order_key"],source_node,member["source_node_lineage_gid"]))
            cur.execute("INSERT INTO workmanship_craft_bop_space_head_members (gid,space_head_gid,member_kind,logical_gid,vpps_group_version_gid,is_tombstone) VALUES (%s,%s,'vpps',%s,%s,0)",(str(next_gid()),space_head_gid,group_gid,version_gid));member_refs.append(("vpps",group_gid,version_gid))
        content_hash=_hash({"members":member_refs})
        cur.execute("UPDATE workmanship_craft_bop_space_heads SET content_hash=%s WHERE gid=%s",(content_hash,space_head_gid))
        return {"copied_node_count":len(included),"blueprint_node_count":len(blueprint_map),"content_hash":content_hash}

    def _reuse_version(self,cur,*,source_version_gid,repository_gid,space_head_gid,run_gid,
                       fork_depth,tenant_gid):
        """Materialise a personal head inside the same repository.

        Team and personal spaces in one repository share logical identities.  Reusing
        immutable revision references is what makes later three-way diff possible;
        allocating new node GIDs here would incorrectly turn a personal fork into a
        cross-repository fork.
        """
        max_level={"station":1,"role":2,"process":3,"operation":4,"all":99}[fork_depth]
        cur.execute("SELECT s.repository_gid FROM workmanship_craft_bop_space_versions v JOIN workmanship_craft_bop_spaces s ON s.gid=v.space_gid WHERE v.gid=%s AND v.tenant_gid=%s AND s.deleted_at IS NULL",(source_version_gid,tenant_gid)); source=cur.fetchone()
        if not source:raise BopForkError("space_version_not_found")
        if str(source["repository_gid"])!=str(repository_gid):
            return None
        cur.execute("SELECT m.logical_gid,m.node_revision_gid,m.binding_revision_gid,m.vpps_group_version_gid,m.member_kind,m.is_tombstone,r.parent_node_gid,r.node_type,r.order_key,r.properties_json,n.lineage_gid FROM workmanship_craft_bop_space_version_members m LEFT JOIN workmanship_craft_bop_node_revisions r ON r.gid=m.node_revision_gid LEFT JOIN workmanship_craft_bop_nodes n ON n.gid=m.logical_gid WHERE m.space_version_gid=%s ORDER BY m.member_kind,m.logical_gid",(source_version_gid,)); members=[dict(row) for row in cur.fetchall()]
        included_nodes={str(row["logical_gid"]) for row in members if row["member_kind"]=="node" and not row["is_tombstone"] and self._level(row["node_type"])<=max_level}
        refs=[]
        for row in members:
            kind=row["member_kind"]; logical=str(row["logical_gid"])
            include=(kind=="node" and logical in included_nodes) or (kind=="binding" and fork_depth=="all") or kind=="vpps"
            if not include:continue
            cur.execute("INSERT INTO workmanship_craft_bop_space_head_members (gid,space_head_gid,member_kind,logical_gid,node_revision_gid,binding_revision_gid,vpps_group_version_gid,is_tombstone) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",(str(next_gid()),space_head_gid,kind,logical,row["node_revision_gid"],row["binding_revision_gid"],row["vpps_group_version_gid"],row["is_tombstone"]));refs.append((kind,logical,str(row["node_revision_gid"] or row["binding_revision_gid"] or row["vpps_group_version_gid"] or "")))
        blueprint_map={}
        for row in members:
            if row["member_kind"]!="node" or row["is_tombstone"] or str(row["logical_gid"]) in included_nodes:continue
            props=_decode(row["properties_json"]) or {};vpps=props.get("vpps_gid") or props.get("vpps")
            if str(vpps or "").isdigit():blueprint_map[str(row["logical_gid"])]=str(next_gid())
        for row in members:
            old=str(row["logical_gid"])
            if old not in blueprint_map:continue
            props=_decode(row["properties_json"]) or {};parent=str(row["parent_node_gid"]) if row["parent_node_gid"] is not None else None
            cur.execute("INSERT INTO workmanship_craft_bop_fork_blueprint_nodes (gid,fork_run_gid,source_node_gid,source_node_lineage_gid,parent_blueprint_gid,vpps_gid,node_level,order_key) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",(blueprint_map[old],run_gid,old,str(row["lineage_gid"] or old),blueprint_map.get(parent),str(props.get("vpps_gid") or props.get("vpps")),row["node_type"],row["order_key"]))
        content_hash=_hash({"members":refs})
        cur.execute("UPDATE workmanship_craft_bop_space_heads SET content_hash=%s WHERE gid=%s",(content_hash,space_head_gid))
        return {"copied_node_count":len(included_nodes),"blueprint_node_count":len(blueprint_map),"content_hash":content_hash}
    def preview_repository(self,*,tenant_gid,actor_gid,source_version_gid,target_project_gid,fork_depth,include_personal_migration,expected_target_slot,idempotency_key):
        if fork_depth not in self.DEPTHS: raise BopForkError("fork_depth_invalid")
        fixed={"tenant_gid":tenant_gid,"actor_gid":actor_gid,"source_version_gid":source_version_gid,"target_project_gid":target_project_gid,"fork_depth":fork_depth,"include_personal_migration":bool(include_personal_migration),"expected_target_slot":expected_target_slot}
        workflow_gid,preview_gid=str(next_gid()),str(next_gid()); decisions=[]; input_hash=_hash(fixed); plan_hash=_hash({**fixed,"owner_verdicts":[],"allowed_decisions":decisions}); expires=datetime.now(timezone.utc)+timedelta(minutes=10)
        with self._connect() as conn,conn.cursor() as cur:
            cur.execute("SELECT v.gid FROM workmanship_craft_bop_space_versions v JOIN workmanship_craft_bop_spaces s ON s.gid=v.space_gid WHERE v.gid=%s AND v.tenant_gid=%s AND s.space_kind='team' AND s.deleted_at IS NULL",(source_version_gid,tenant_gid))
            if not cur.fetchone():raise BopForkError("space_version_not_found")
            cur.execute("SELECT p.gid preview_gid,p.workflow_gid,p.input_hash,p.plan_hash,p.owner_verdicts_json,p.allowed_decisions_json,p.expires_at,w.target_project_gid,w.include_personal_migration FROM workmanship_craft_bop_fork_plans p JOIN workmanship_craft_bop_fork_workflows w ON w.gid=p.workflow_gid WHERE w.tenant_gid=%s AND w.actor_gid=%s AND p.input_hash=%s AND p.expires_at>NOW(6) ORDER BY p.created_at DESC LIMIT 1",(tenant_gid,actor_gid,input_hash)); prior=cur.fetchone()
            if prior:return self._plan(prior,tenant_gid,actor_gid,source_version_gid,fork_depth,expected_target_slot)
            cur.execute("INSERT INTO workmanship_craft_bop_fork_workflows (gid,tenant_gid,actor_gid,target_project_gid,include_personal_migration,status,correlation_gid) VALUES (%s,%s,%s,%s,%s,'previewing',%s)",(workflow_gid,tenant_gid,actor_gid,target_project_gid,int(include_personal_migration),workflow_gid))
            cur.execute("INSERT INTO workmanship_craft_bop_fork_plans (gid,workflow_gid,tenant_gid,source_version_gid,target_project_gid,fork_depth,input_hash,plan_hash,owner_verdicts_json,allowed_decisions_json,expires_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",(preview_gid,workflow_gid,tenant_gid,source_version_gid,target_project_gid,fork_depth,input_hash,plan_hash,"[]","[]",expires))
        return {"preview_gid":preview_gid,"workflow_gid":workflow_gid,"input_hash":input_hash,"plan_hash":plan_hash,"expires_at":expires.isoformat(),"owner_verdicts":[],"allowed_decisions":decisions,**fixed}
    @staticmethod
    def _plan(row,tenant,actor,source,depth,slot):
        return {"preview_gid":str(row["preview_gid"]),"workflow_gid":str(row["workflow_gid"]),"input_hash":row["input_hash"],"plan_hash":row["plan_hash"],"expires_at":row["expires_at"].replace(tzinfo=timezone.utc).isoformat(),"owner_verdicts":_decode(row["owner_verdicts_json"]),"allowed_decisions":_decode(row["allowed_decisions_json"]),"tenant_gid":str(tenant),"actor_gid":str(actor),"source_version_gid":str(source),"target_project_gid":str(row["target_project_gid"]),"fork_depth":depth,"include_personal_migration":bool(row["include_personal_migration"]),"expected_target_slot":slot}
    def apply_repository(self,*,preview_gid,tenant_gid,actor_gid,plan_hash,allowed_decisions,expected_target_slot,idempotency_key):
        request_hash=_hash({"preview_gid":preview_gid,"plan_hash":plan_hash,"allowed_decisions":allowed_decisions,"expected_target_slot":expected_target_slot})[7:]
        with self._connect() as conn,conn.cursor() as cur:
            cur.execute("SELECT p.*,w.actor_gid,w.include_personal_migration FROM workmanship_craft_bop_fork_plans p JOIN workmanship_craft_bop_fork_workflows w ON w.gid=p.workflow_gid WHERE p.gid=%s AND p.tenant_gid=%s FOR UPDATE",(preview_gid,tenant_gid)); p=cur.fetchone()
            if not p or str(p["actor_gid"])!=str(actor_gid) or p["expires_at"]<=datetime.now():raise BopForkError("fork_preview_expired")
            if p["plan_hash"]!=plan_hash or _decode(p["allowed_decisions_json"])!=allowed_decisions:raise BopForkError("fork_plan_changed")
            cur.execute("SELECT request_hash,outcome_json FROM workmanship_craft_bop_fork_runs WHERE workflow_gid=%s AND step_kind='team' AND idempotency_key=%s FOR UPDATE",(p["workflow_gid"],idempotency_key)); old=cur.fetchone()
            if old:
                if old["request_hash"]!=request_hash:raise BopForkError("idempotency_conflict")
                return _decode(old["outcome_json"])
            cur.execute("SELECT gid FROM workmanship_craft_bop_repositories WHERE tenant_gid=%s AND project_gid=%s AND deleted_at IS NULL FOR UPDATE",(tenant_gid,p["target_project_gid"]))
            if cur.fetchone():raise BopForkError("target_repository_exists")
            run,repo,space,head=map(str,(next_gid(),next_gid(),next_gid(),next_gid())); empty=_hash({"members":[]})
            cur.execute("INSERT INTO workmanship_craft_bop_repositories (gid,tenant_gid,project_gid,created_by) VALUES (%s,%s,%s,%s)",(repo,tenant_gid,p["target_project_gid"],actor_gid)); cur.execute("INSERT INTO workmanship_craft_bop_spaces (gid,repository_gid,tenant_gid,space_kind,fork_base_version_gid,created_by) VALUES (%s,%s,%s,'team',%s,%s)",(space,repo,tenant_gid,p["source_version_gid"],actor_gid)); cur.execute("INSERT INTO workmanship_craft_bop_space_heads (gid,space_gid,tenant_gid,content_hash,updated_by) VALUES (%s,%s,%s,%s,%s)",(head,space,tenant_gid,empty,actor_gid))
            cur.execute("INSERT INTO workmanship_craft_bop_fork_runs (gid,workflow_gid,plan_gid,repository_gid,step_kind,status,idempotency_key,request_hash) VALUES (%s,%s,%s,%s,'team','running',%s,%s)",(run,p["workflow_gid"],preview_gid,repo,idempotency_key,request_hash))
            copy_result=self._copy_version(cur,source_version_gid=p["source_version_gid"],repository_gid=repo,space_head_gid=head,run_gid=run,fork_depth=p["fork_depth"],tenant_gid=tenant_gid,actor_gid=actor_gid)
            result={"workflow_gid":str(p["workflow_gid"]),"fork_run_gid":run,"repository_gid":repo,"team_space_gid":space,"fork_depth":p["fork_depth"],"status":"completed",**copy_result}
            if p["include_personal_migration"]:result["personal_step"]={"status":"pending","step_key":f'{p["workflow_gid"]}:personal'}
            cur.execute("UPDATE workmanship_craft_bop_fork_runs SET status='completed',outcome_json=%s,updated_at=NOW(6) WHERE gid=%s",(json.dumps(result,separators=(",", ":")),run));cur.execute("UPDATE workmanship_craft_bop_fork_workflows SET status='team_completed',updated_at=NOW(6) WHERE gid=%s",(p["workflow_gid"],))
        return result
    def preview_personal(self,*,tenant_gid,actor_gid,source_version_gid,target_repository_gid,fork_depth,expected_target_slot,idempotency_key,workflow_gid=None):
        if fork_depth not in self.DEPTHS:raise BopForkError("fork_depth_invalid")
        fixed={"tenant_gid":tenant_gid,"actor_gid":actor_gid,"source_version_gid":source_version_gid,"target_repository_gid":target_repository_gid,"fork_depth":fork_depth,"expected_target_slot":expected_target_slot}
        preview_gid=str(next_gid()); decisions=[]; input_hash=_hash(fixed);plan_hash=_hash({**fixed,"owner_verdicts":[],"allowed_decisions":decisions});expires=datetime.now(timezone.utc)+timedelta(minutes=10)
        with self._connect() as conn,conn.cursor() as cur:
            if workflow_gid:
                cur.execute("SELECT gid FROM workmanship_craft_bop_fork_workflows WHERE gid=%s AND tenant_gid=%s AND actor_gid=%s FOR UPDATE",(workflow_gid,tenant_gid,actor_gid))
                if not cur.fetchone():raise BopForkError("fork_workflow_not_found")
            else:
                workflow_gid=str(next_gid());cur.execute("INSERT INTO workmanship_craft_bop_fork_workflows (gid,tenant_gid,actor_gid,include_personal_migration,status,correlation_gid) VALUES (%s,%s,%s,1,'previewing',%s)",(workflow_gid,tenant_gid,actor_gid,workflow_gid))
            cur.execute("SELECT gid FROM workmanship_craft_bop_repositories WHERE gid=%s AND tenant_gid=%s AND deleted_at IS NULL",(target_repository_gid,tenant_gid))
            if not cur.fetchone():raise BopForkError("repository_not_found")
            cur.execute("INSERT INTO workmanship_craft_bop_fork_plans (gid,workflow_gid,tenant_gid,source_version_gid,fork_depth,input_hash,plan_hash,owner_verdicts_json,allowed_decisions_json,expires_at) VALUES (%s,%s,%s,%s,%s,%s,%s,'[]','[]',%s)",(preview_gid,workflow_gid,tenant_gid,source_version_gid,fork_depth,input_hash,plan_hash,expires))
            cur.execute("INSERT INTO workmanship_craft_bop_personal_fork_targets (plan_gid,target_repository_gid,expected_target_slot) VALUES (%s,%s,%s)",(preview_gid,target_repository_gid,expected_target_slot))
        return {"preview_gid":preview_gid,"workflow_gid":workflow_gid,"input_hash":input_hash,"plan_hash":plan_hash,"expires_at":expires.isoformat(),"owner_verdicts":[],"allowed_decisions":[],**fixed}
    def apply_personal(self,*,preview_gid,tenant_gid,actor_gid,plan_hash,allowed_decisions,expected_target_slot,idempotency_key):
        request_hash=_hash({"preview_gid":preview_gid,"plan_hash":plan_hash,"allowed_decisions":allowed_decisions,"expected_target_slot":expected_target_slot})[7:]
        with self._connect() as conn,conn.cursor() as cur:
            cur.execute("SELECT p.*,t.target_repository_gid,t.expected_target_slot,w.actor_gid FROM workmanship_craft_bop_fork_plans p JOIN workmanship_craft_bop_personal_fork_targets t ON t.plan_gid=p.gid JOIN workmanship_craft_bop_fork_workflows w ON w.gid=p.workflow_gid WHERE p.gid=%s AND p.tenant_gid=%s FOR UPDATE",(preview_gid,tenant_gid));p=cur.fetchone()
            if not p or str(p["actor_gid"])!=str(actor_gid) or p["expires_at"]<=datetime.now():raise BopForkError("fork_preview_expired")
            if p["plan_hash"]!=plan_hash or _decode(p["allowed_decisions_json"])!=allowed_decisions or p["expected_target_slot"]!=expected_target_slot:raise BopForkError("fork_plan_changed")
            cur.execute("SELECT request_hash,outcome_json FROM workmanship_craft_bop_fork_runs WHERE workflow_gid=%s AND step_kind='personal' AND idempotency_key=%s FOR UPDATE",(p["workflow_gid"],idempotency_key));old=cur.fetchone()
            if old:
                if old["request_hash"]!=request_hash:raise BopForkError("idempotency_conflict")
                return _decode(old["outcome_json"])
            cur.execute("SELECT gid FROM workmanship_craft_bop_spaces WHERE repository_gid=%s AND space_kind='managed_personal' AND owner_user_gid=%s AND deleted_at IS NULL FOR UPDATE",(p["target_repository_gid"],actor_gid))
            if cur.fetchone():raise BopForkError("managed_personal_space_exists")
            run,space,head=map(str,(next_gid(),next_gid(),next_gid()));empty=_hash({"members":[]})
            cur.execute("INSERT INTO workmanship_craft_bop_spaces (gid,repository_gid,tenant_gid,space_kind,owner_user_gid,fork_base_version_gid,created_by) VALUES (%s,%s,%s,'managed_personal',%s,%s,%s)",(space,p["target_repository_gid"],tenant_gid,actor_gid,p["source_version_gid"],actor_gid));cur.execute("INSERT INTO workmanship_craft_bop_space_heads (gid,space_gid,tenant_gid,content_hash,updated_by) VALUES (%s,%s,%s,%s,%s)",(head,space,tenant_gid,empty,actor_gid))
            cur.execute("INSERT INTO workmanship_craft_bop_fork_runs (gid,workflow_gid,plan_gid,repository_gid,step_kind,status,idempotency_key,request_hash) VALUES (%s,%s,%s,%s,'personal','running',%s,%s)",(run,p["workflow_gid"],preview_gid,p["target_repository_gid"],idempotency_key,request_hash))
            copied=self._reuse_version(cur,source_version_gid=p["source_version_gid"],repository_gid=p["target_repository_gid"],space_head_gid=head,run_gid=run,fork_depth=p["fork_depth"],tenant_gid=tenant_gid)
            if copied is None:
                copied=self._copy_version(cur,source_version_gid=p["source_version_gid"],repository_gid=p["target_repository_gid"],space_head_gid=head,run_gid=run,fork_depth=p["fork_depth"],tenant_gid=tenant_gid,actor_gid=actor_gid)
            result={"workflow_gid":str(p["workflow_gid"]),"fork_run_gid":run,"personal_space_gid":space,"fork_depth":p["fork_depth"],"status":"completed",**copied}
            cur.execute("UPDATE workmanship_craft_bop_fork_runs SET status='completed',outcome_json=%s,updated_at=NOW(6) WHERE gid=%s",(json.dumps(result,separators=(",", ":")),run))
        return result
    def get_run(self,*,run_gid,tenant_gid,actor_gid):
        with self._connect() as conn,conn.cursor() as cur:cur.execute("SELECT r.outcome_json FROM workmanship_craft_bop_fork_runs r JOIN workmanship_craft_bop_fork_workflows w ON w.gid=r.workflow_gid WHERE r.gid=%s AND w.tenant_gid=%s",(run_gid,tenant_gid));row=cur.fetchone()
        if not row:raise BopForkError("fork_run_not_found")
        return _decode(row["outcome_json"])
    def get_workflow(self,*,workflow_gid,tenant_gid,actor_gid):
        with self._connect() as conn,conn.cursor() as cur:cur.execute("SELECT gid workflow_gid,status,target_project_gid,include_personal_migration FROM workmanship_craft_bop_fork_workflows WHERE gid=%s AND tenant_gid=%s",(workflow_gid,tenant_gid));row=cur.fetchone()
        if not row:raise BopForkError("fork_workflow_not_found")
        return dict(row)
