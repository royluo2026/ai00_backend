"""Experimental ordered VPPS group capabilities."""
import hashlib,json
from backend.capability_v2.provider_contracts import CapabilityBusinessError,CapabilityOutput,CapabilitySpec,EvidenceRef
from ..data.bop_vpps_groups import MysqlBopVppsGroupStore,VppsGroupError


class VppsGroupProvider:
    def __init__(self,store=None):self.store=store or MysqlBopVppsGroupStore()
    def _scope(self,c):
        if not c.team_gid or not c.user_gid:raise CapabilityBusinessError("repository_identity_required","repository_identity_required")
        return str(c.team_gid),str(c.user_gid)
    def _out(self,data):
        h="sha256:"+hashlib.sha256(json.dumps(data,sort_keys=True,default=str).encode()).hexdigest();return CapabilityOutput(data=data,evidence=(EvidenceRef(kind="craft.bop.vpps_group",reference=f"craft://bop-vpps/{data.get('group_gid')}",digest=h),))
    def _create(self,kind,p,c):
        tenant,actor=self._scope(c)
        try:return self._out(self.store.create_version(group_gid=p["group_gid"],tenant_gid=tenant,actor_gid=actor,version_kind=kind,members=p.get("members",[]),expected_current=p.get("expected_current"),reference_version_gid=p.get("reference_version_gid"),matcher_policy_hash=p.get("matcher_policy_hash"),evidence_refs=p.get("evidence_refs",[])))
        except VppsGroupError as e:raise CapabilityBusinessError(str(e),str(e),retryable=str(e)=="resource_version_conflict") from e
    def generate(self,p,c):return self._create("generated_initial",p,c)
    def adjust(self,p,c):return self._create("adjustment",p,c)
    def set_current(self,p,c):
        tenant,actor=self._scope(c)
        try:return self._out(self.store.set_current(group_gid=p["group_gid"],version_gid=p["version_gid"],expected_current=p.get("expected_current"),tenant_gid=tenant,actor_gid=actor))
        except VppsGroupError as e:raise CapabilityBusinessError(str(e),str(e),retryable=True) from e


def candidate_specs(provider=None):
    p=provider or VppsGroupProvider();gid={"type":"string","pattern":"^[1-9][0-9]*$"};nullable={"type":["string","null"],"pattern":"^[1-9][0-9]*$"};member={"type":"object","required":["vpps_gid","node_level","order_key"],"properties":{"vpps_gid":gid,"parent_scope_gid":nullable,"node_level":{"type":"string"},"order_key":{"type":"string","minLength":1,"maxLength":128},"source_bop_node_gid":gid,"source_node_lineage_gid":gid},"additionalProperties":False};common={"owner":"craft","permissions":('craft.bop.repository.use',),"plugin_callable":True,"risk":"write","confirmation":"none","tags":('craft','bop','vpps','experimental')};out={"type":"object","properties":{k:{} for k in ('group_gid','version_gid','version_kind','root_scope_gid','reference_version_gid','current_version_gid','matcher_policy_hash','content_hash','members','row_version')},"additionalProperties":False}
    def schema(props,req):return {"type":"object","properties":props,"required":list(req),"additionalProperties":False}
    key={"type":"string","minLength":1,"maxLength":191};base={"group_gid":gid,"members":{"type":"array","maxItems":5000,"items":member},"expected_current":nullable,"reference_version_gid":gid,"matcher_policy_hash":{"type":"string","pattern":"^sha256:[0-9a-f]{64}$"},"evidence_refs":{"type":"array","maxItems":100},"idempotency_key":key}
    return ((CapabilitySpec(id="craft.bop.vpps_group.initial.generate",version=1,description="Generate an immutable initial VPPS group version without advancing current.",input_schema=schema(base,("group_gid","members","reference_version_gid","matcher_policy_hash","idempotency_key")),output_schema=out,**common),p.generate),(CapabilitySpec(id="craft.bop.vpps_group.adjustment.create",version=1,description="Create an immutable ordered VPPS adjustment.",input_schema=schema(base,("group_gid","members","expected_current","idempotency_key")),output_schema=out,**common),p.adjust),(CapabilitySpec(id="craft.bop.vpps_group.current.set",version=1,description="Advance the VPPS current pointer with CAS.",input_schema=schema({"group_gid":gid,"version_gid":gid,"expected_current":nullable,"idempotency_key":key},("group_gid","version_gid","expected_current","idempotency_key")),output_schema=out,**common),p.set_current))

__all__=["VppsGroupProvider","candidate_specs"]
