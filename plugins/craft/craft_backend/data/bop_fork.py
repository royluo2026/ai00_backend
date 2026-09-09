"""Deterministic repository Fork workflow model used by Provider and contract tests."""
from __future__ import annotations
import copy, hashlib, json
from datetime import datetime, timedelta, timezone
from backend.platform_sdk.ids import next_gid


class BopForkError(RuntimeError): pass
def _hash(v): return "sha256:"+hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",", ":")).encode()).hexdigest()


class MemoryBopForkStore:
    DEPTHS={"all","operation","process","role","station"}
    def __init__(self):
        self.previews={}; self.workflows={}; self.runs={}; self.applies={}; self.occupied_projects=set(); self.team_apply_count=0
    def preview_repository(self, *, tenant_gid, actor_gid, source_version_gid, target_project_gid, fork_depth, include_personal_migration, expected_target_slot, idempotency_key):
        if fork_depth not in self.DEPTHS: raise BopForkError("fork_depth_invalid")
        fixed={"tenant_gid":tenant_gid,"actor_gid":actor_gid,"source_version_gid":source_version_gid,"target_project_gid":target_project_gid,"fork_depth":fork_depth,"include_personal_migration":bool(include_personal_migration),"expected_target_slot":expected_target_slot}
        workflow_gid=str(next_gid()); preview_gid=str(next_gid()); decisions=[]; plan_hash=_hash({**fixed,"owner_verdicts":[],"allowed_decisions":decisions})
        row={"preview_gid":preview_gid,"workflow_gid":workflow_gid,"input_hash":_hash(fixed),"plan_hash":plan_hash,"expires_at":(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat(),"owner_verdicts":[],"allowed_decisions":decisions,**fixed}
        self.previews[preview_gid]=row; self.workflows[workflow_gid]={"workflow_gid":workflow_gid,"status":"previewed","team":None,"personal":None,**fixed}; return copy.deepcopy(row)
    def apply_repository(self, *, preview_gid, tenant_gid, actor_gid, plan_hash, allowed_decisions, expected_target_slot, idempotency_key):
        p=self.previews.get(preview_gid)
        if not p or p["tenant_gid"]!=tenant_gid or p["actor_gid"]!=actor_gid: raise BopForkError("fork_preview_expired")
        if datetime.fromisoformat(p["expires_at"])<=datetime.now(timezone.utc): raise BopForkError("fork_preview_expired")
        if plan_hash!=p["plan_hash"] or allowed_decisions!=p["allowed_decisions"] or expected_target_slot!=p["expected_target_slot"]: raise BopForkError("fork_plan_changed")
        key=(preview_gid,idempotency_key)
        if key in self.applies:return copy.deepcopy(self.applies[key])
        slot=(tenant_gid,p["target_project_gid"])
        if slot in self.occupied_projects: raise BopForkError("target_repository_exists")
        self.occupied_projects.add(slot); self.team_apply_count+=1
        result={"workflow_gid":p["workflow_gid"],"fork_run_gid":str(next_gid()),"repository_gid":str(next_gid()),"team_space_gid":str(next_gid()),"fork_depth":p["fork_depth"],"status":"completed"}
        if p["include_personal_migration"]: result["personal_step"]={"status":"pending","step_key":f'{p["workflow_gid"]}:personal'}
        self.applies[key]=result; self.workflows[p["workflow_gid"]]["team"]=result; self.workflows[p["workflow_gid"]]["status"]="team_completed"; return copy.deepcopy(result)
    def preview_personal(self, *, workflow_gid=None, **kw):
        if workflow_gid and workflow_gid not in self.workflows: raise BopForkError("fork_workflow_not_found")
        row=self.preview_repository(include_personal_migration=False,**kw)
        if workflow_gid: row["workflow_gid"]=workflow_gid; self.previews[row["preview_gid"]]["workflow_gid"]=workflow_gid
        return row
    def apply_personal(self, **kw):
        result=self.apply_repository(**kw); result["personal_space_gid"]=result.pop("repository_gid"); return result
    def get_run(self, *, run_gid, tenant_gid, actor_gid):
        row=self.runs.get(run_gid)
        if not row: raise BopForkError("fork_run_not_found")
        return copy.deepcopy(row)
    def get_workflow(self, *, workflow_gid, tenant_gid, actor_gid):
        row=self.workflows.get(workflow_gid)
        if not row or row["tenant_gid"]!=tenant_gid: raise BopForkError("fork_workflow_not_found")
        return copy.deepcopy(row)


__all__=["BopForkError","MemoryBopForkStore"]
