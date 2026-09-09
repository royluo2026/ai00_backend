"""Experimental BOP diff, private import, sync and proposal capabilities."""
from __future__ import annotations
import hashlib,json
from backend.capability_v2.provider_contracts import CapabilityBusinessError,CapabilityOutput,CapabilitySpec,EvidenceRef
from backend.domain_ports.versioned_resources import versioned_resource_resolvers
from backend.platform_sdk.artifacts import read_artifact
from ..data.bop_collaboration import ProposalError
from ..data.bop_collaboration_mysql import MysqlCollaborationService


def _resolve_export(reference):
    def resolve(ref):return versioned_resource_resolvers.resolve("simulation.workspace_export",{"export_ref":ref},reference)
    return resolve


class CollaborationProvider:
    def __init__(self,service=None):self.service=service
    def _service(self,c):return self.service or MysqlCollaborationService(export_resolver=_resolve_export(c),manifest_loader=lambda ref:read_artifact(ref,c))
    @staticmethod
    def _scope(c):
        if not c.team_gid or not c.user_gid:raise CapabilityBusinessError("repository_identity_required","repository_identity_required")
        return str(c.team_gid),str(c.user_gid)
    def _call(self,name,p,c,*args,**kw):
        try:data=getattr(self._service(c),name)(*args,**kw)
        except (ProposalError,LookupError) as exc:
            code=str(exc) if isinstance(exc,ProposalError) else "private_export_invalid";raise CapabilityBusinessError(code,code,retryable=code in {"team_head_advanced","resource_version_conflict"}) from exc
        digest="sha256:"+hashlib.sha256(json.dumps(data,sort_keys=True,default=str).encode()).hexdigest();return CapabilityOutput(data=data,evidence=(EvidenceRef(kind="craft.bop.collaboration",reference=f"craft://bop-collaboration/{data.get('proposal_gid') or data.get('preview_gid') or 'diff'}",digest=digest),))
    def proposal_create(self,p,c):
        tenant,actor=self._scope(c);return self._call("create_proposal",p,c,repository_gid=p["repository_gid"],personal_space_gid=p["personal_space_gid"],personal_version_gid=p["personal_version_gid"],team_base_version_gid=p["team_base_version_gid"],actor_gid=actor,tenant_gid=tenant,idempotency_key=p["idempotency_key"])
    def proposal_get(self,p,c):tenant,actor=self._scope(c);return self._call("get",p,c,p["proposal_gid"],tenant_gid=tenant,actor_gid=actor)
    def proposal_submit(self,p,c):tenant,actor=self._scope(c);return self._call("submit",p,c,p["proposal_gid"],tenant_gid=tenant,actor_gid=actor,idempotency_key=p["idempotency_key"])
    def proposal_review(self,p,c):tenant,actor=self._scope(c);return self._call("review",p,c,p["proposal_gid"],p["decisions"],tenant_gid=tenant,actor_gid=actor,idempotency_key=p["idempotency_key"])
    def proposal_apply(self,p,c):tenant,actor=self._scope(c);return self._call("apply_component",p,c,p["proposal_gid"],component_gid=p["component_gid"],tenant_gid=tenant,actor_gid=actor,idempotency_key=p["idempotency_key"])
    def proposal_withdraw(self,p,c):tenant,actor=self._scope(c);return self._call("withdraw",p,c,p["proposal_gid"],tenant_gid=tenant,actor_gid=actor,idempotency_key=p["idempotency_key"])
    def proposal_cancel(self,p,c):tenant,actor=self._scope(c);return self._call("cancel",p,c,p["proposal_gid"],tenant_gid=tenant,actor_gid=actor,idempotency_key=p["idempotency_key"])
    def proposal_supersede(self,p,c):tenant,actor=self._scope(c);return self._call("supersede",p,c,p["proposal_gid"],tenant_gid=tenant,actor_gid=actor,idempotency_key=p["idempotency_key"])
    def sync_preview(self,p,c):self._scope(c);return self._call("preview_sync",p,c,base_version_gid=p["base_version_gid"],recorded_team_head_gid=p["recorded_team_head_gid"],current_team_head_gid=p["current_team_head_gid"])
    def sync_apply(self,p,c):
        tenant,actor=self._scope(c);return self._call("apply_sync",p,c,operation_gid=p["operation_gid"],personal_space_gid=p["personal_space_gid"],selected_keys=p["selected_keys"],expected_personal_head=p["expected_personal_head"],tenant_gid=tenant,actor_gid=actor,idempotency_key=p["idempotency_key"])
    def import_preview(self,p,c):
        tenant,actor=self._scope(c);return self._call("preview_private_import",p,c,export_ref=p["export_ref"],actor_gid=actor,tenant_gid=tenant,personal_space_gid=p["personal_space_gid"],repository_gid=p["repository_gid"],idempotency_key=p["idempotency_key"],expected_personal_head=p["expected_personal_head"])
    def import_apply(self,p,c):
        tenant,actor=self._scope(c);return self._call("apply_private_import",p,c,p["preview_gid"],export_ref=p["export_ref"],actor_gid=actor,tenant_gid=tenant,personal_space_gid=p["personal_space_gid"],repository_gid=p["repository_gid"],selected_units=p["selected_units"],expected_personal_head=p["expected_personal_head"])
    def diff_start(self,p,c):
        tenant,actor=self._scope(c);return self._call("start_diff",p,c,base_version_gid=p["base_version_gid"],ours_version_gid=p["ours_version_gid"],theirs_version_gid=p["theirs_version_gid"],tenant_gid=tenant,actor_gid=actor,idempotency_key=p["idempotency_key"])
    def diff_get(self,p,c):
        tenant,actor=self._scope(c);size=p.get("page_size",50);cursor=p.get("cursor","0")
        if isinstance(size,bool) or not isinstance(size,int) or not 1<=size<=100 or not str(cursor).isdecimal():raise CapabilityBusinessError("page_size_invalid","page_size_invalid")
        return self._call("get_diff",p,c,operation_gid=p["operation_gid"],tenant_gid=tenant,actor_gid=actor,offset=int(cursor),page_size=size)


def candidate_specs(provider=None):
    p=provider or CollaborationProvider();gid={"type":"string","pattern":"^[1-9][0-9]*$"};key={"type":"string","minLength":1,"maxLength":191};common=dict(owner="craft",permissions=("craft.bop.repository.use",),plugin_callable=True,confirmation="none",tags=("craft","bop","collaboration","experimental"));out={"type":"object","properties":{k:{} for k in ("proposal_gid","preview_gid","operation_gid","repository_gid","personal_space_gid","personal_version_gid","team_base_version_gid","base_version_gid","team_head_gid","diff_hash","result_hash","review_status","apply_status","row_version","created_by","components","items","units","next_cursor","is_terminal","export_ref_hash","content_hash","preview_hash","expected_personal_head","imported_units","status")},"additionalProperties":False}
    def schema(props,req):return {"type":"object","properties":props,"required":list(req),"additionalProperties":False}
    def spec(cid,h,props,req,write=True):return CapabilitySpec(id=cid,version=1,description=cid,risk="write" if write else "read",input_schema=schema(props,req),output_schema=out,**common),h
    proposal={"proposal_gid":gid};create={"repository_gid":gid,"personal_space_gid":gid,"personal_version_gid":gid,"team_base_version_gid":gid,"idempotency_key":key};imp={"export_ref":{"type":"string","minLength":32},"personal_space_gid":gid,"repository_gid":gid,"expected_personal_head":{"type":"integer","minimum":1},"idempotency_key":key};items=[spec("craft.bop.change_proposal.create",p.proposal_create,create,create),spec("craft.bop.change_proposal.get",p.proposal_get,proposal,proposal,False),spec("craft.bop.change_proposal.submit",p.proposal_submit,{**proposal,"idempotency_key":key},("proposal_gid","idempotency_key")),spec("craft.bop.change_proposal.review",p.proposal_review,{**proposal,"decisions":{"type":"object"},"idempotency_key":key},("proposal_gid","decisions","idempotency_key")),spec("craft.bop.change_proposal.apply",p.proposal_apply,{**proposal,"component_gid":gid,"idempotency_key":key},("proposal_gid","component_gid","idempotency_key"))]
    for action,handler in (("withdraw",p.proposal_withdraw),("cancel",p.proposal_cancel),("supersede",p.proposal_supersede)):items.append(spec(f"craft.bop.change_proposal.{action}",handler,{**proposal,"idempotency_key":key},("proposal_gid","idempotency_key")))
    diff={"base_version_gid":gid,"ours_version_gid":gid,"theirs_version_gid":gid,"idempotency_key":key};sync_apply={"operation_gid":gid,"personal_space_gid":gid,"selected_keys":{"type":"array","maxItems":5000,"items":{"type":"array","minItems":2,"maxItems":2}},"expected_personal_head":{"type":"integer","minimum":1},"idempotency_key":key};apply_import={**imp,"preview_gid":gid,"selected_units":{"type":"array","maxItems":5000,"items":{"type":"string"}}};items.extend([spec("craft.bop.managed_personal_space.sync.preview",p.sync_preview,{"base_version_gid":gid,"recorded_team_head_gid":gid,"current_team_head_gid":gid},("base_version_gid","recorded_team_head_gid","current_team_head_gid")),spec("craft.bop.managed_personal_space.sync.apply",p.sync_apply,sync_apply,sync_apply),spec("craft.bop.managed_personal_space.import.preview",p.import_preview,imp,imp),spec("craft.bop.managed_personal_space.import.apply",p.import_apply,apply_import,apply_import),spec("craft.bop.repository_diff.start",p.diff_start,diff,diff),spec("craft.bop.repository_diff.get",p.diff_get,{"operation_gid":gid,"cursor":{"type":"string","pattern":"^[0-9]+$"},"page_size":{"type":"integer","minimum":1,"maximum":100}},("operation_gid",),False)]);return tuple(items)

__all__=["CollaborationProvider","candidate_specs"]
