"""Experimental two-stage BOP repository Fork capabilities."""
from __future__ import annotations
import hashlib,json
from typing import Any
from backend.capability_v2.provider_contracts import CapabilityBusinessError,CapabilityContext,CapabilityOutput,CapabilitySpec,EvidenceRef
from ..data.bop_fork import BopForkError,MemoryBopForkStore, MysqlBopForkStore


class ForkProvider:
    def __init__(self,store=None):self.store=store or MysqlBopForkStore()
    def _call(self,method,p,c):
        if not c.team_gid or not c.user_gid: raise CapabilityBusinessError("repository_identity_required","repository_identity_required")
        if "owner_verdict" in p: raise CapabilityBusinessError("fork_plan_changed","fork_plan_changed")
        try:data=getattr(self.store,method)(tenant_gid=str(c.team_gid),actor_gid=str(c.user_gid),**p)
        except BopForkError as exc: raise CapabilityBusinessError(str(exc),str(exc),retryable=str(exc)=="target_repository_exists") from exc
        digest="sha256:"+hashlib.sha256(json.dumps(data,sort_keys=True,default=str).encode()).hexdigest()
        return CapabilityOutput(data=data,evidence=(EvidenceRef(kind="craft.bop.fork",reference=f"craft://bop-fork/{data.get('workflow_gid','status')}",digest=digest),))
    def repository_preview(self,p,c):return self._call("preview_repository",p,c)
    def repository_apply(self,p,c):return self._call("apply_repository",p,c)
    def personal_preview(self,p,c):return self._call("preview_personal",p,c)
    def personal_apply(self,p,c):return self._call("apply_personal",p,c)
    def get_run(self,p,c):return self._call("get_run",p,c)
    def get_workflow(self,p,c):return self._call("get_workflow",p,c)


def candidate_specs(provider=None):
    p=provider or ForkProvider(); gid={"type":"string","pattern":"^[1-9][0-9]*$"}; key={"type":"string","minLength":1,"maxLength":191}
    def schema(props,req):return {"type":"object","properties":props,"required":list(req),"additionalProperties":False}
    out={"type":"object","properties":{k:{} for k in ("preview_gid","workflow_gid","fork_run_gid","repository_gid","team_space_gid","personal_space_gid","fork_depth","status","input_hash","plan_hash","expires_at","owner_verdicts","allowed_decisions","personal_step","team","personal","tenant_gid","actor_gid","source_version_gid","target_project_gid","include_personal_migration","expected_target_slot")},"additionalProperties":False}
    common=dict(owner="craft",permissions=("craft.bop.repository.fork",),plugin_callable=True,confirmation="none",tags=("craft","bop","fork","experimental"),output_schema=out)
    preview={"source_version_gid":gid,"target_project_gid":gid,"fork_depth":{"enum":["all","operation","process","role","station"]},"include_personal_migration":{"type":"boolean"},"expected_target_slot":{"type":"integer","minimum":0},"idempotency_key":key}
    apply={"preview_gid":gid,"plan_hash":{"type":"string","pattern":"^sha256:[0-9a-f]{64}$"},"allowed_decisions":{"type":"array","maxItems":100},"expected_target_slot":{"type":"integer","minimum":0},"idempotency_key":key}
    def s(cid,h,props,req,write):return CapabilitySpec(id=cid,version=1,description=cid,risk="write" if write else "read",input_schema=schema(props,req),**common),h
    personal_preview={"source_version_gid":gid,"target_repository_gid":gid,"fork_depth":preview["fork_depth"],"workflow_gid":gid,"expected_target_slot":{"type":"integer","minimum":0},"idempotency_key":key}
    return (s("craft.bop.repository.fork.preview",p.repository_preview,preview,preview,True),s("craft.bop.repository.fork.apply",p.repository_apply,apply,apply,True),s("craft.bop.managed_personal_space.fork.preview",p.personal_preview,personal_preview,("source_version_gid","target_repository_gid","fork_depth","expected_target_slot","idempotency_key"),True),s("craft.bop.managed_personal_space.fork.apply",p.personal_apply,apply,apply,True),s("craft.bop.fork_run.get",p.get_run,{"run_gid":gid},("run_gid",),False),s("craft.bop.fork_workflow.get",p.get_workflow,{"workflow_gid":gid},("workflow_gid",),False))


__all__=["ForkProvider","candidate_specs"]
