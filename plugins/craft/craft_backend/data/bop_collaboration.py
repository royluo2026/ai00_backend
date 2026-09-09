"""Three-way collaboration rules independent from transport and storage."""
from __future__ import annotations
import copy,hashlib,json
from backend.platform_sdk.ids import next_gid


class ProposalError(RuntimeError):pass
def _hash(value):return "sha256:"+hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",", ":")).encode()).hexdigest()


class CollaborationService:
    TERMINAL_REVIEW={"rejected","withdrawn","cancelled","superseded"}
    def __init__(self,export_resolver=None):self.proposals={};self.previews={};self.export_resolver=export_resolver
    def create_proposal(self,*,repository_gid,personal_space_gid,personal_version_gid,team_base_version_gid,components,actor_gid):
        gid=str(next_gid());items={str(x["component_gid"]):{**x,"review_decision":None,"apply_outcome":None} for x in components};row={"proposal_gid":gid,"repository_gid":repository_gid,"personal_space_gid":personal_space_gid,"personal_version_gid":personal_version_gid,"team_base_version_gid":team_base_version_gid,"diff_hash":_hash(components),"review_status":"draft","apply_status":"not_started","components":items,"row_version":1,"created_by":actor_gid};self.proposals[gid]=row;return self._view(row)
    def _get(self,gid):
        if gid not in self.proposals:raise ProposalError("proposal_not_found")
        return self.proposals[gid]
    def _view(self,p):
        out=copy.deepcopy(p);out["components"]=list(out["components"].values());out["is_terminal"]=p["apply_status"]=="applied" or p["review_status"] in self.TERMINAL_REVIEW;return out
    def submit(self,gid):
        p=self._get(gid)
        if p["review_status"]!="draft":raise ProposalError("proposal_state_invalid")
        p["review_status"]="submitted";p["row_version"]+=1;return self._view(p)
    def review(self,gid,decisions):
        p=self._get(gid)
        if p["review_status"] not in {"submitted","reviewing"}:raise ProposalError("proposal_state_invalid")
        if any(key not in p["components"] or value not in {"accepted","rejected"} for key,value in decisions.items()):raise ProposalError("proposal_state_invalid")
        combined={key:decisions.get(key,item["review_decision"]) for key,item in p["components"].items()}
        if any(combined[key]=="accepted" and any(combined.get(str(dep))!="accepted" for dep in item.get("dependencies",[])) for key,item in p["components"].items()):raise ProposalError("dependency_closure_not_accepted")
        for key,value in decisions.items():p["components"][key]["review_decision"]=value
        values={x["review_decision"] for x in p["components"].values()};p["review_status"]="accepted" if values=={"accepted"} else "rejected" if values=={"rejected"} else "partially_accepted";p["row_version"]+=1;return self._view(p)
    def apply_component(self,gid,*,component_gid):
        p=self._get(gid);c=p["components"].get(component_gid)
        if p["review_status"] not in {"accepted","partially_accepted"} or not c or c["review_decision"]!="accepted":raise ProposalError("proposal_state_invalid")
        if any(p["components"].get(str(dep),{}).get("apply_outcome") is None for dep in c.get("dependencies",[])):raise ProposalError("dependency_closure_not_accepted")
        if c["apply_outcome"] is not None:return self._view(p)
        c["apply_outcome"]={"status":"applied","outcome_hash":_hash(c)}
        accepted=[x for x in p["components"].values() if x["review_decision"]=="accepted"]
        p["apply_status"]="applied" if all(x["apply_outcome"] for x in accepted) else "partially_applied";p["row_version"]+=1;return self._view(p)
    def withdraw(self,gid):
        p=self._get(gid)
        if p["review_status"] not in {"draft","submitted","reviewing"}:raise ProposalError("proposal_not_withdrawable")
        p["review_status"]="withdrawn";return self._view(p)
    def cancel(self,gid):
        p=self._get(gid);p["review_status"]="cancelled";return self._view(p)
    def supersede(self,gid):
        p=self._get(gid);p["review_status"]="superseded";return self._view(p)
    def preview_sync(self,*,base_version_gid,recorded_team_head_gid,current_team_head_gid):
        if recorded_team_head_gid!=current_team_head_gid:raise ProposalError("team_head_advanced")
        return {"base_version_gid":base_version_gid,"team_head_gid":current_team_head_gid,"diff_hash":_hash([base_version_gid,current_team_head_gid])}
    def _claims(self,ref,actor,tenant,personal,repository):
        if not self.export_resolver:raise ProposalError("private_export_invalid")
        claims=self.export_resolver(ref);expected={"actor_gid":actor,"tenant_gid":tenant,"target_personal_space_gid":personal,"target_repository_gid":repository,"consumer":"craft.bop.managed_personal_space.import.preview@1"}
        if any(str(claims.get(k))!=str(v) for k,v in expected.items()):raise ProposalError("private_export_invalid")
        return claims
    def preview_private_import(self,*,export_ref,actor_gid,tenant_gid,personal_space_gid,repository_gid):
        claims=self._claims(export_ref,actor_gid,tenant_gid,personal_space_gid,repository_gid);gid=str(next_gid());row={"preview_gid":gid,"export_ref_hash":_hash(export_ref),"content_hash":claims["content_hash"],"scope":(actor_gid,tenant_gid,personal_space_gid,repository_gid)};self.previews[gid]=row;return copy.deepcopy(row)
    def apply_private_import(self,preview_gid,*,export_ref,actor_gid,tenant_gid,personal_space_gid,repository_gid):
        p=self.previews.get(preview_gid);claims=self._claims(export_ref,actor_gid,tenant_gid,personal_space_gid,repository_gid)
        if not p or p["export_ref_hash"]!=_hash(export_ref) or p["content_hash"]!=claims["content_hash"]:raise ProposalError("private_export_invalid")
        return {"preview_gid":preview_gid,"status":"applied","content_hash":p["content_hash"]}


__all__=["CollaborationService","ProposalError"]
