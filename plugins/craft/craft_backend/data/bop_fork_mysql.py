"""Transactional MySQL persistence for two-stage BOP Fork workflows."""
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from backend.platform_sdk.ids import next_gid
from .bop_fork import BopForkError, _hash
from .connection import get_craft_conn


def _decode(value): return json.loads(value) if isinstance(value,str) else value


class MysqlBopForkStore:
    DEPTHS={"all","operation","process","role","station"}
    def __init__(self,connection_factory=get_craft_conn): self._connect=connection_factory
    def preview_repository(self,*,tenant_gid,actor_gid,source_version_gid,target_project_gid,fork_depth,include_personal_migration,expected_target_slot,idempotency_key):
        if fork_depth not in self.DEPTHS: raise BopForkError("fork_depth_invalid")
        fixed={"tenant_gid":tenant_gid,"actor_gid":actor_gid,"source_version_gid":source_version_gid,"target_project_gid":target_project_gid,"fork_depth":fork_depth,"include_personal_migration":bool(include_personal_migration),"expected_target_slot":expected_target_slot}
        workflow_gid,preview_gid=str(next_gid()),str(next_gid()); decisions=[]; input_hash=_hash(fixed); plan_hash=_hash({**fixed,"owner_verdicts":[],"allowed_decisions":decisions}); expires=datetime.now(timezone.utc)+timedelta(minutes=10)
        with self._connect() as conn,conn.cursor() as cur:
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
            result={"workflow_gid":str(p["workflow_gid"]),"fork_run_gid":run,"repository_gid":repo,"team_space_gid":space,"fork_depth":p["fork_depth"],"status":"completed"}
            if p["include_personal_migration"]:result["personal_step"]={"status":"pending","step_key":f'{p["workflow_gid"]}:personal'}
            cur.execute("INSERT INTO workmanship_craft_bop_fork_runs (gid,workflow_gid,plan_gid,repository_gid,step_kind,status,idempotency_key,request_hash,outcome_json) VALUES (%s,%s,%s,%s,'team','completed',%s,%s,%s)",(run,p["workflow_gid"],preview_gid,repo,idempotency_key,request_hash,json.dumps(result,separators=(",", ":"))));cur.execute("UPDATE workmanship_craft_bop_fork_workflows SET status='team_completed',updated_at=NOW(6) WHERE gid=%s",(p["workflow_gid"],))
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
            result={"workflow_gid":str(p["workflow_gid"]),"fork_run_gid":run,"personal_space_gid":space,"fork_depth":p["fork_depth"],"status":"completed"}
            cur.execute("INSERT INTO workmanship_craft_bop_fork_runs (gid,workflow_gid,plan_gid,repository_gid,step_kind,status,idempotency_key,request_hash,outcome_json) VALUES (%s,%s,%s,%s,'personal','completed',%s,%s,%s)",(run,p["workflow_gid"],preview_gid,p["target_repository_gid"],idempotency_key,request_hash,json.dumps(result,separators=(",", ":"))))
        return result
    def get_run(self,*,run_gid,tenant_gid,actor_gid):
        with self._connect() as conn,conn.cursor() as cur:cur.execute("SELECT r.outcome_json FROM workmanship_craft_bop_fork_runs r JOIN workmanship_craft_bop_fork_workflows w ON w.gid=r.workflow_gid WHERE r.gid=%s AND w.tenant_gid=%s",(run_gid,tenant_gid));row=cur.fetchone()
        if not row:raise BopForkError("fork_run_not_found")
        return _decode(row["outcome_json"])
    def get_workflow(self,*,workflow_gid,tenant_gid,actor_gid):
        with self._connect() as conn,conn.cursor() as cur:cur.execute("SELECT gid workflow_gid,status,target_project_gid,include_personal_migration FROM workmanship_craft_bop_fork_workflows WHERE gid=%s AND tenant_gid=%s",(workflow_gid,tenant_gid));row=cur.fetchone()
        if not row:raise BopForkError("fork_workflow_not_found")
        return dict(row)
