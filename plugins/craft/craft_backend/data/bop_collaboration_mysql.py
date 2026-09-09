"""MySQL persistence for BOP change proposal state transitions."""
from __future__ import annotations
import hashlib,json
from backend.platform_sdk.ids import next_gid
from .bop_collaboration import ProposalError,_hash
from .connection import get_craft_conn


def _json(v):return json.dumps(v,ensure_ascii=False,separators=(",", ":"))
def _decode(v):return json.loads(v) if isinstance(v,str) else v


class MysqlCollaborationService:
    TERMINAL={"rejected","withdrawn","cancelled","superseded"}
    def __init__(self,connection_factory=get_craft_conn,export_resolver=None,manifest_loader=None):self._connect=connection_factory;self.export_resolver=export_resolver;self.manifest_loader=manifest_loader
    def _begin(self,cur,tenant,kind,resource,key,request):
        digest=_hash(request)[7:];cur.execute("SELECT request_hash,status,outcome_json FROM workmanship_craft_bop_operation_ledger WHERE tenant_gid=%s AND operation_kind=%s AND idempotency_key=%s FOR UPDATE",(tenant,kind,key));old=cur.fetchone()
        if old:
            if old["request_hash"]!=digest:raise ProposalError("idempotency_conflict")
            return _decode(old["outcome_json"]),None
        gid=str(next_gid());cur.execute("INSERT INTO workmanship_craft_bop_operation_ledger (gid,tenant_gid,operation_kind,resource_gid,idempotency_key,request_hash,status) VALUES (%s,%s,%s,%s,%s,%s,'running')",(gid,tenant,kind,resource,key,digest));return None,gid
    @staticmethod
    def _complete(cur,gid,outcome):cur.execute("UPDATE workmanship_craft_bop_operation_ledger SET status='completed',outcome_json=%s,updated_at=NOW(6) WHERE gid=%s",(_json(outcome),gid))
    def _load(self,cur,gid,lock=False):
        cur.execute("SELECT * FROM workmanship_craft_bop_change_proposals WHERE gid=%s"+(" FOR UPDATE" if lock else ""),(gid,));p=cur.fetchone()
        if not p:raise ProposalError("proposal_not_found")
        cur.execute("SELECT gid,component_gid,unit_kind,payload_json,dependencies_json,review_decision,apply_outcome_json FROM workmanship_craft_bop_change_proposal_units WHERE proposal_gid=%s ORDER BY gid",(gid,));units=[]
        for raw in cur.fetchall():
            row=dict(raw);row["unit_gid"]=str(row.pop("gid"));row["component_gid"]=str(row["component_gid"]);row["payload"]=_decode(row.pop("payload_json"));row["dependencies"]=_decode(row.pop("dependencies_json"));row["apply_outcome"]=_decode(row.pop("apply_outcome_json"));units.append(row)
        out={"proposal_gid":str(p["gid"]),"repository_gid":str(p["repository_gid"]),"personal_space_gid":str(p["personal_space_gid"]),"personal_version_gid":str(p["personal_version_gid"]),"team_base_version_gid":str(p["team_base_version_gid"]),"diff_hash":p["diff_hash"],"review_status":p["review_status"],"apply_status":p["apply_status"],"row_version":p["row_version"],"created_by":str(p["created_by"]),"components":units};out["is_terminal"]=out["apply_status"]=="applied" or out["review_status"] in self.TERMINAL;return out
    @staticmethod
    def _authorize(cur,gid,tenant_gid):
        cur.execute("SELECT 1 FROM workmanship_craft_bop_change_proposals p JOIN workmanship_craft_bop_repositories r ON r.gid=p.repository_gid WHERE p.gid=%s AND r.tenant_gid=%s AND r.deleted_at IS NULL",(gid,tenant_gid))
        if not cur.fetchone():raise ProposalError("proposal_not_found")
    def _resolve_components(self,cur,repository_gid,personal_space_gid,personal_version_gid,team_base_version_gid,actor_gid):
        cur.execute("SELECT fork_base_version_gid FROM workmanship_craft_bop_spaces WHERE gid=%s AND repository_gid=%s AND space_kind='managed_personal' AND owner_user_gid=%s AND deleted_at IS NULL",(personal_space_gid,repository_gid,actor_gid));space=cur.fetchone()
        if not space or str(space["fork_base_version_gid"])!=str(team_base_version_gid):raise ProposalError("lineage_resolution_failed")
        def version_members(version_gid):
            cur.execute("SELECT member_kind,logical_gid,node_revision_gid,binding_revision_gid,vpps_group_version_gid,is_tombstone FROM workmanship_craft_bop_space_version_members WHERE space_version_gid=%s",(version_gid,));return {(r["member_kind"],str(r["logical_gid"])):dict(r) for r in cur.fetchall()}
        base=version_members(team_base_version_gid);ours=version_members(personal_version_gid)
        cur.execute("SELECT h.gid FROM workmanship_craft_bop_spaces s JOIN workmanship_craft_bop_space_heads h ON h.space_gid=s.gid WHERE s.repository_gid=%s AND s.space_kind='team' AND s.deleted_at IS NULL",(repository_gid,));head=cur.fetchone()
        if not head:raise ProposalError("lineage_resolution_failed")
        cur.execute("SELECT member_kind,logical_gid,node_revision_gid,binding_revision_gid,vpps_group_version_gid,is_tombstone FROM workmanship_craft_bop_space_head_members WHERE space_head_gid=%s",(head["gid"],));theirs={(r["member_kind"],str(r["logical_gid"])):dict(r) for r in cur.fetchall()}
        components=[]
        for key in sorted(set(base)|set(ours)):
            before,after,current=base.get(key),ours.get(key),theirs.get(key)
            if before==after:continue
            conflict=current!=before and current!=after
            components.append({"component_gid":str(next_gid()),"unit_kind":key[0],"payload":{"logical_gid":key[1],"base":before,"ours":after,"theirs":current,"conflict":conflict},"dependencies":[]})
        component_by_member={(c["unit_kind"],c["payload"]["logical_gid"]):c["component_gid"] for c in components}
        for component in components:
            ours_row=component["payload"].get("ours") or {}
            dependency=None
            if component["unit_kind"]=="node" and ours_row.get("node_revision_gid"):
                cur.execute("SELECT parent_node_gid FROM workmanship_craft_bop_node_revisions WHERE gid=%s",(ours_row["node_revision_gid"],));row=cur.fetchone();dependency=("node",str(row["parent_node_gid"])) if row and row["parent_node_gid"] else None
            elif component["unit_kind"]=="binding" and ours_row.get("binding_revision_gid"):
                cur.execute("SELECT source_node_gid FROM workmanship_craft_bop_binding_revisions WHERE gid=%s",(ours_row["binding_revision_gid"],));row=cur.fetchone();dependency=("node",str(row["source_node_gid"])) if row else None
            if dependency in component_by_member:component["dependencies"].append(component_by_member[dependency])
        return components
    def create_proposal(self,*,repository_gid,personal_space_gid,personal_version_gid,team_base_version_gid,actor_gid,tenant_gid,idempotency_key,components=None):
        gid=str(next_gid())
        with self._connect() as conn,conn.cursor() as cur:
            replay,ledger=self._begin(cur,tenant_gid,"proposal.create",repository_gid,idempotency_key,{"repository_gid":repository_gid,"personal_space_gid":personal_space_gid,"personal_version_gid":personal_version_gid,"team_base_version_gid":team_base_version_gid})
            if replay:return replay
            components=self._resolve_components(cur,repository_gid,personal_space_gid,personal_version_gid,team_base_version_gid,actor_gid);diff=_hash(components)
            cur.execute("INSERT INTO workmanship_craft_bop_change_proposals (gid,repository_gid,personal_space_gid,personal_version_gid,team_base_version_gid,diff_hash,remaining_set_json,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",(gid,repository_gid,personal_space_gid,personal_version_gid,team_base_version_gid,diff,_json([str(c["component_gid"]) for c in components]),actor_gid))
            for c in components:
                unit_gid=str(next_gid());cur.execute("INSERT INTO workmanship_craft_bop_change_proposal_units (gid,proposal_gid,component_gid,unit_kind,payload_json,dependencies_json) VALUES (%s,%s,%s,%s,%s,%s)",(unit_gid,gid,c["component_gid"],c.get("unit_kind","component"),_json(c.get("payload",{})),_json(c.get("dependencies",[]))))
                if c.get("payload",{}).get("conflict"):cur.execute("INSERT INTO workmanship_craft_bop_change_proposal_conflicts (gid,proposal_gid,unit_gid,conflict_kind,details_json) VALUES (%s,%s,%s,'three_way_conflict',%s)",(str(next_gid()),gid,unit_gid,_json(c["payload"])))
            result=self._load(cur,gid);self._complete(cur,ledger,result);return result
    def get(self,gid,*,tenant_gid,actor_gid):
        with self._connect() as conn,conn.cursor() as cur:self._authorize(cur,gid,tenant_gid);return self._load(cur,gid)
    def _status(self,gid,allowed,target,*,tenant_gid,actor_gid,idempotency_key):
        with self._connect() as conn,conn.cursor() as cur:
            self._authorize(cur,gid,tenant_gid);replay,ledger=self._begin(cur,tenant_gid,f"proposal.{target}",gid,idempotency_key,{"proposal_gid":gid,"target":target})
            if replay:return replay
            p=self._load(cur,gid,True)
            if p["review_status"] not in allowed:raise ProposalError("proposal_state_invalid")
            cur.execute("UPDATE workmanship_craft_bop_change_proposals SET review_status=%s,row_version=row_version+1,updated_at=NOW(6) WHERE gid=%s",(target,gid));result=self._load(cur,gid);self._complete(cur,ledger,result);return result
    def submit(self,gid,**kw):return self._status(gid,{"draft"},"submitted",**kw)
    def withdraw(self,gid,**kw):
        try:return self._status(gid,{"draft","submitted","reviewing"},"withdrawn",**kw)
        except ProposalError as e:
            if str(e)=="proposal_state_invalid":raise ProposalError("proposal_not_withdrawable") from e
            raise
    def cancel(self,gid,**kw):return self._status(gid,{"draft","submitted","reviewing"},"cancelled",**kw)
    def supersede(self,gid,**kw):return self._status(gid,{"draft","submitted","reviewing","accepted","partially_accepted"},"superseded",**kw)
    def review(self,gid,decisions,*,tenant_gid,actor_gid,idempotency_key):
        with self._connect() as conn,conn.cursor() as cur:
            self._authorize(cur,gid,tenant_gid);replay,ledger=self._begin(cur,tenant_gid,"proposal.review",gid,idempotency_key,{"proposal_gid":gid,"decisions":decisions})
            if replay:return replay
            p=self._load(cur,gid,True)
            if p["review_status"] not in {"submitted","reviewing"}:raise ProposalError("proposal_state_invalid")
            known={x["component_gid"] for x in p["components"]}
            if set(decisions)-known or set(decisions.values())-{"accepted","rejected"}:raise ProposalError("proposal_state_invalid")
            combined={u["component_gid"]:decisions.get(u["component_gid"],u["review_decision"]) for u in p["components"]}
            if any(combined[u["component_gid"]]=="accepted" and any(combined.get(dep)!="accepted" for dep in u["dependencies"]) for u in p["components"]):raise ProposalError("dependency_closure_not_accepted")
            for component,value in decisions.items():cur.execute("UPDATE workmanship_craft_bop_change_proposal_units SET review_decision=%s WHERE proposal_gid=%s AND component_gid=%s",(value,gid,component))
            values=set(combined.values());status="accepted" if values=={"accepted"} else "rejected" if values=={"rejected"} else "partially_accepted"
            cur.execute("UPDATE workmanship_craft_bop_change_proposals SET review_status=%s,row_version=row_version+1,updated_at=NOW(6) WHERE gid=%s",(status,gid));result=self._load(cur,gid);self._complete(cur,ledger,result);return result
    def apply_component(self,gid,*,component_gid,tenant_gid,actor_gid,idempotency_key):
        with self._connect() as conn,conn.cursor() as cur:
            self._authorize(cur,gid,tenant_gid);replay,ledger=self._begin(cur,tenant_gid,"proposal.apply",gid,idempotency_key,{"proposal_gid":gid,"component_gid":component_gid})
            if replay:return replay
            p=self._load(cur,gid,True);unit=next((u for u in p["components"] if u["component_gid"]==str(component_gid)),None)
            if p["review_status"] not in {"accepted","partially_accepted"} or not unit or unit["review_decision"]!="accepted":raise ProposalError("proposal_state_invalid")
            outcomes={u["component_gid"]:u["apply_outcome"] for u in p["components"]}
            if any(outcomes.get(str(dep)) is None for dep in unit["dependencies"]):raise ProposalError("dependency_closure_not_accepted")
            if unit["apply_outcome"] is None:
                payload=unit["payload"];cur.execute("SELECT h.gid,h.row_version FROM workmanship_craft_bop_spaces s JOIN workmanship_craft_bop_space_heads h ON h.space_gid=s.gid WHERE s.repository_gid=%s AND s.space_kind='team' AND s.deleted_at IS NULL FOR UPDATE",(p["repository_gid"],));head=cur.fetchone()
                if not head:raise ProposalError("team_head_advanced")
                cur.execute("SELECT member_kind,logical_gid,node_revision_gid,binding_revision_gid,vpps_group_version_gid,is_tombstone FROM workmanship_craft_bop_space_head_members WHERE space_head_gid=%s AND member_kind=%s AND logical_gid=%s",(head["gid"],unit["unit_kind"],payload["logical_gid"]));current=cur.fetchone();current=dict(current) if current else None
                if current!=payload.get("theirs"):raise ProposalError("team_head_advanced")
                ours=payload.get("ours") or {"node_revision_gid":None,"binding_revision_gid":None,"vpps_group_version_gid":None,"is_tombstone":1}
                cur.execute("INSERT INTO workmanship_craft_bop_space_head_members (gid,space_head_gid,member_kind,logical_gid,node_revision_gid,binding_revision_gid,vpps_group_version_gid,is_tombstone) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE node_revision_gid=VALUES(node_revision_gid),binding_revision_gid=VALUES(binding_revision_gid),vpps_group_version_gid=VALUES(vpps_group_version_gid),is_tombstone=VALUES(is_tombstone)",(str(next_gid()),head["gid"],unit["unit_kind"],payload["logical_gid"],ours.get("node_revision_gid"),ours.get("binding_revision_gid"),ours.get("vpps_group_version_gid"),ours.get("is_tombstone",0)))
                cur.execute("UPDATE workmanship_craft_bop_space_heads SET row_version=row_version+1,updated_by=%s,updated_at=NOW(6) WHERE gid=%s AND row_version=%s",(p["created_by"],head["gid"],head["row_version"]))
                outcome={"status":"applied","outcome_hash":_hash(unit),"team_head_version":head["row_version"]+1};cur.execute("UPDATE workmanship_craft_bop_change_proposal_units SET apply_outcome_json=%s WHERE gid=%s",(_json(outcome),unit["unit_gid"]))
            fresh=self._load(cur,gid);accepted=[u for u in fresh["components"] if u["review_decision"]=="accepted"];status="applied" if all(u["apply_outcome"] for u in accepted) else "partially_applied"
            cur.execute("UPDATE workmanship_craft_bop_change_proposals SET apply_status=%s,row_version=row_version+1,updated_at=NOW(6) WHERE gid=%s",(status,gid));result=self._load(cur,gid);self._complete(cur,ledger,result);return result
    def preview_sync(self,*,base_version_gid,recorded_team_head_gid,current_team_head_gid):
        if str(recorded_team_head_gid)!=str(current_team_head_gid):raise ProposalError("team_head_advanced")
        return {"base_version_gid":str(base_version_gid),"team_head_gid":str(current_team_head_gid),"diff_hash":_hash([base_version_gid,current_team_head_gid])}
    def _claims(self,ref,actor,tenant,personal,repository):
        if not self.export_resolver:raise ProposalError("private_export_invalid")
        claims=self.export_resolver(ref); expected={"actor_gid":actor,"tenant_gid":tenant,"target_personal_space_gid":personal,"target_repository_gid":repository,"consumer":"craft.bop.managed_personal_space.import.preview@1"}
        if any(str(claims.get(k))!=str(v) for k,v in expected.items()):raise ProposalError("private_export_invalid")
        return claims
    def preview_private_import(self,*,export_ref,actor_gid,tenant_gid,personal_space_gid,repository_gid,idempotency_key,expected_personal_head):
        claims=self._claims(export_ref,actor_gid,tenant_gid,personal_space_gid,repository_gid)
        if not self.manifest_loader:raise ProposalError("private_export_invalid")
        raw=self.manifest_loader(claims["manifest_artifact_ref"]);manifest=json.loads(raw.decode() if isinstance(raw,bytes) else raw)
        units=[]
        for node in manifest.get("nodes",[]):units.append({"unit_key":f'node:{node["node_gid"]}',"unit_kind":"node","source":node,"dependencies":[f'node:{node["parent_gid"]}'] if node.get("parent_gid") else []})
        for binding in manifest.get("bindings",[]):units.append({"unit_key":f'binding:{binding["binding_gid"]}',"unit_kind":"binding","source":binding,"dependencies":[f'node:{binding["node_gid"]}']})
        gid=str(next_gid());ref_hash=hashlib.sha256(export_ref.encode()).hexdigest();preview_hash=_hash({"ref":ref_hash,"content":claims["content_hash"],"target":personal_space_gid,"head":expected_personal_head,"units":units})
        with self._connect() as conn,conn.cursor() as cur:
            cur.execute("SELECT gid,source_export_ref_hash,source_content_hash,preview_hash,status,outcome_json FROM workmanship_craft_bop_personal_import_operations WHERE personal_space_gid=%s AND idempotency_key=%s FOR UPDATE",(personal_space_gid,idempotency_key));old=cur.fetchone()
            if old:
                if old["source_export_ref_hash"]!=ref_hash:raise ProposalError("private_export_invalid")
                result=_decode(old.get("outcome_json")) or {};return result
            preview={"preview_gid":gid,"export_ref_hash":ref_hash,"content_hash":claims["content_hash"],"preview_hash":preview_hash,"expected_personal_head":expected_personal_head,"units":units,"status":"previewed"}
            cur.execute("INSERT INTO workmanship_craft_bop_personal_import_operations (gid,personal_space_gid,source_export_ref_hash,source_content_hash,preview_hash,status,idempotency_key,outcome_json) VALUES (%s,%s,%s,%s,%s,'previewed',%s,%s)",(gid,personal_space_gid,ref_hash,claims["content_hash"],preview_hash,idempotency_key,_json(preview)))
        return preview
    def apply_private_import(self,preview_gid,*,export_ref,actor_gid,tenant_gid,personal_space_gid,repository_gid,selected_units,expected_personal_head):
        claims=self._claims(export_ref,actor_gid,tenant_gid,personal_space_gid,repository_gid);ref_hash=hashlib.sha256(export_ref.encode()).hexdigest()
        with self._connect() as conn,conn.cursor() as cur:
            cur.execute("SELECT source_export_ref_hash,source_content_hash,status,outcome_json FROM workmanship_craft_bop_personal_import_operations WHERE gid=%s AND personal_space_gid=%s FOR UPDATE",(preview_gid,personal_space_gid));row=cur.fetchone()
            if not row or row["source_export_ref_hash"]!=ref_hash or row["source_content_hash"]!=claims["content_hash"]:raise ProposalError("private_export_invalid")
            preview=_decode(row["outcome_json"]);units={u["unit_key"]:u for u in preview["units"]};selected=set(selected_units)
            if not selected<=set(units) or any(dep not in selected for key in selected for dep in units[key]["dependencies"]):raise ProposalError("dependency_closure_not_accepted")
            cur.execute("SELECT h.gid,h.row_version,s.repository_gid FROM workmanship_craft_bop_spaces s JOIN workmanship_craft_bop_space_heads h ON h.space_gid=s.gid WHERE s.gid=%s AND s.tenant_gid=%s AND s.owner_user_gid=%s AND s.deleted_at IS NULL FOR UPDATE",(personal_space_gid,tenant_gid,actor_gid));head=cur.fetchone()
            if not head or str(head["repository_gid"])!=str(repository_gid):raise ProposalError("space_not_found")
            if head["row_version"]!=expected_personal_head or preview["expected_personal_head"]!=expected_personal_head:raise ProposalError("resource_version_conflict")
            node_map={}
            for unit in [u for u in preview["units"] if u["unit_key"] in selected and u["unit_kind"]=="node"]:
                source=unit["source"];node_gid,revision_gid=str(next_gid()),str(next_gid());node_map[str(source["node_gid"])]=node_gid;properties={"name":source.get("name","")};content=_hash({"parent":source.get("parent_gid"),"type":source.get("node_type"),"order":source.get("position",0),"properties":properties})
                cur.execute("INSERT INTO workmanship_craft_bop_nodes (gid,repository_gid,tenant_gid,lineage_gid,created_by) VALUES (%s,%s,%s,%s,%s)",(node_gid,repository_gid,tenant_gid,node_gid,actor_gid));cur.execute("INSERT INTO workmanship_craft_bop_node_revisions (gid,node_gid,tenant_gid,parent_node_gid,node_type,order_key,properties_json,content_hash,actor_gid,actor_type,evidence_refs_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'user','[]')",(revision_gid,node_gid,tenant_gid,node_map.get(str(source.get("parent_gid"))),source.get("node_type"),str(source.get("position",0)),_json(properties),content,actor_gid));cur.execute("INSERT INTO workmanship_craft_bop_space_head_members (gid,space_head_gid,member_kind,logical_gid,node_revision_gid,is_tombstone) VALUES (%s,%s,'node',%s,%s,0)",(str(next_gid()),head["gid"],node_gid,revision_gid))
            for unit in [u for u in preview["units"] if u["unit_key"] in selected and u["unit_kind"]=="binding"]:
                source=unit["source"];binding_gid,revision_gid=str(next_gid()),str(next_gid());source_node=node_map[str(source["node_gid"])];content=_hash(source)
                cur.execute("INSERT INTO workmanship_craft_bop_bindings (gid,repository_gid,tenant_gid,lineage_gid,created_by) VALUES (%s,%s,%s,%s,%s)",(binding_gid,repository_gid,tenant_gid,binding_gid,actor_gid));cur.execute("INSERT INTO workmanship_craft_bop_binding_revisions (gid,binding_gid,tenant_gid,source_node_gid,target_ref_kind,target_ref_gid,binding_role,properties_json,content_hash,actor_gid,evidence_refs_json) VALUES (%s,%s,%s,%s,'simulation_occurrence',%s,%s,'{}',%s,%s,'[]')",(revision_gid,binding_gid,tenant_gid,source_node,source["occurrence_gid"],source.get("role","operate"),content,actor_gid));cur.execute("INSERT INTO workmanship_craft_bop_space_head_members (gid,space_head_gid,member_kind,logical_gid,binding_revision_gid,is_tombstone) VALUES (%s,%s,'binding',%s,%s,0)",(str(next_gid()),head["gid"],binding_gid,revision_gid))
            cur.execute("UPDATE workmanship_craft_bop_space_heads SET row_version=row_version+1,updated_by=%s,updated_at=NOW(6) WHERE gid=%s",(actor_gid,head["gid"]));outcome={"preview_gid":str(preview_gid),"status":"applied","content_hash":row["source_content_hash"],"row_version":head["row_version"]+1,"imported_units":len(selected)};cur.execute("UPDATE workmanship_craft_bop_personal_import_operations SET status='applied',outcome_json=%s,updated_at=NOW(6) WHERE gid=%s",(_json(outcome),preview_gid));return outcome
    def start_diff(self,*,base_version_gid,ours_version_gid,theirs_version_gid,tenant_gid,actor_gid,idempotency_key):
        request={"base":base_version_gid,"ours":ours_version_gid,"theirs":theirs_version_gid};request_hash=_hash(request)[7:]
        with self._connect() as conn,conn.cursor() as cur:
            cur.execute("SELECT gid,request_hash,outcome_json FROM workmanship_craft_bop_operation_ledger WHERE tenant_gid=%s AND operation_kind='repository.diff' AND idempotency_key=%s FOR UPDATE",(tenant_gid,idempotency_key));old=cur.fetchone()
            if old:
                if old["request_hash"]!=request_hash:raise ProposalError("idempotency_conflict")
                return _decode(old["outcome_json"])
            def members(version):
                cur.execute("SELECT member_kind,logical_gid,node_revision_gid,binding_revision_gid,vpps_group_version_gid,is_tombstone FROM workmanship_craft_bop_space_version_members m JOIN workmanship_craft_bop_space_versions v ON v.gid=m.space_version_gid WHERE m.space_version_gid=%s AND v.tenant_gid=%s",(version,tenant_gid));return {(r["member_kind"],str(r["logical_gid"])):dict(r) for r in cur.fetchall()}
            base,ours,theirs=members(base_version_gid),members(ours_version_gid),members(theirs_version_gid);items=[]
            for key in sorted(set(base)|set(ours)|set(theirs)):
                if ours.get(key)==theirs.get(key):continue
                items.append({"member_kind":key[0],"logical_gid":key[1],"base":base.get(key),"ours":ours.get(key),"theirs":theirs.get(key),"conflict":ours.get(key)!=base.get(key) and theirs.get(key)!=base.get(key)})
            operation_gid=str(next_gid());out={"operation_gid":operation_gid,"result_hash":_hash(items),"items":items,"status":"completed"};cur.execute("INSERT INTO workmanship_craft_bop_operation_ledger (gid,tenant_gid,operation_kind,idempotency_key,request_hash,status,outcome_json) VALUES (%s,%s,'repository.diff',%s,%s,'completed',%s)",(operation_gid,tenant_gid,idempotency_key,request_hash,_json(out)));return out
    def get_diff(self,*,operation_gid,tenant_gid,actor_gid,offset,page_size):
        with self._connect() as conn,conn.cursor() as cur:cur.execute("SELECT outcome_json FROM workmanship_craft_bop_operation_ledger WHERE gid=%s AND tenant_gid=%s AND operation_kind='repository.diff'",(operation_gid,tenant_gid));row=cur.fetchone()
        if not row:raise ProposalError("operation_not_found")
        out=_decode(row["outcome_json"]);items=out.pop("items",[]);out["items"]=items[offset:offset+page_size];out["next_cursor"]=str(offset+page_size) if len(items)>offset+page_size else None;return out
    def apply_sync(self,*,operation_gid,personal_space_gid,selected_keys,expected_personal_head,tenant_gid,actor_gid,idempotency_key):
        with self._connect() as conn,conn.cursor() as cur:
            replay,ledger=self._begin(cur,tenant_gid,"personal.sync",personal_space_gid,idempotency_key,{"operation_gid":operation_gid,"selected_keys":selected_keys,"expected_personal_head":expected_personal_head})
            if replay:return replay
            cur.execute("SELECT outcome_json FROM workmanship_craft_bop_operation_ledger WHERE gid=%s AND tenant_gid=%s AND operation_kind='repository.diff' FOR UPDATE",(operation_gid,tenant_gid));row=cur.fetchone()
            if not row:raise ProposalError("operation_not_found")
            diff=_decode(row["outcome_json"]);by_key={(x["member_kind"],x["logical_gid"]):x for x in diff["items"]}
            if any(tuple(k) not in by_key for k in selected_keys):raise ProposalError("diff_selection_invalid")
            cur.execute("SELECT h.gid,h.row_version FROM workmanship_craft_bop_spaces s JOIN workmanship_craft_bop_space_heads h ON h.space_gid=s.gid WHERE s.gid=%s AND s.tenant_gid=%s AND s.owner_user_gid=%s AND s.space_kind='managed_personal' AND s.deleted_at IS NULL FOR UPDATE",(personal_space_gid,tenant_gid,actor_gid));head=cur.fetchone()
            if not head:raise ProposalError("space_not_found")
            if head["row_version"]!=expected_personal_head:raise ProposalError("resource_version_conflict")
            for selected in selected_keys:
                item=by_key[tuple(selected)];target=item.get("theirs") or {"node_revision_gid":None,"binding_revision_gid":None,"vpps_group_version_gid":None,"is_tombstone":1}
                cur.execute("INSERT INTO workmanship_craft_bop_space_head_members (gid,space_head_gid,member_kind,logical_gid,node_revision_gid,binding_revision_gid,vpps_group_version_gid,is_tombstone) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE node_revision_gid=VALUES(node_revision_gid),binding_revision_gid=VALUES(binding_revision_gid),vpps_group_version_gid=VALUES(vpps_group_version_gid),is_tombstone=VALUES(is_tombstone)",(str(next_gid()),head["gid"],item["member_kind"],item["logical_gid"],target.get("node_revision_gid"),target.get("binding_revision_gid"),target.get("vpps_group_version_gid"),target.get("is_tombstone",0)))
            cur.execute("UPDATE workmanship_craft_bop_space_heads SET row_version=row_version+1,updated_by=%s,updated_at=NOW(6) WHERE gid=%s",(actor_gid,head["gid"]));result={"operation_gid":operation_gid,"personal_space_gid":personal_space_gid,"row_version":head["row_version"]+1,"status":"applied"};self._complete(cur,ledger,result);return result
