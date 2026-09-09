"""Immutable ordered VPPS group versions and CAS current pointers."""
from __future__ import annotations
import copy,hashlib,json
from backend.platform_sdk.ids import next_gid
from .connection import get_craft_conn


class VppsGroupError(RuntimeError):pass
def _hash(v):return "sha256:"+hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",", ":")).encode()).hexdigest()


class MemoryBopVppsGroupStore:
    def __init__(self):self.groups={};self.versions={}
    def create_group(self,*,space_gid,boundary_node_gid,actor_gid):
        gid=str(next_gid());self.groups[gid]={"group_gid":gid,"space_gid":space_gid,"boundary_node_gid":boundary_node_gid,"reference_version_gid":None,"current_version_gid":None,"row_version":1};return copy.deepcopy(self.groups[gid])
    def _create(self,kind,*,group_gid,members,actor_gid,expected_current=None,reference_version_gid=None,matcher_policy_hash=None):
        group=self.groups.get(group_gid)
        if not group:raise VppsGroupError("vpps_group_not_found")
        if kind=="generated_initial":
            prior=next((v for v in self.versions.values() if v["group_gid"]==group_gid and v["version_kind"]==kind and v["reference_version_gid"]==reference_version_gid and v["matcher_policy_hash"]==matcher_policy_hash),None)
            if prior:return copy.deepcopy(prior)
        if kind=="adjustment" and group["current_version_gid"]!=expected_current:raise VppsGroupError("resource_version_conflict")
        root=str(next_gid()); normalized=[]
        for item in members:
            row=dict(item);row["parent_scope_gid"]=str(row.get("parent_scope_gid") or root);normalized.append(row)
        if len({(m["parent_scope_gid"],m["order_key"]) for m in normalized})!=len(normalized):raise VppsGroupError("vpps_order_conflict")
        gid=str(next_gid());version={"version_gid":gid,"group_gid":group_gid,"version_kind":kind,"root_scope_gid":root,"reference_version_gid":reference_version_gid or group["reference_version_gid"],"matcher_policy_hash":matcher_policy_hash,"content_hash":_hash(normalized),"members":normalized}
        self.versions[gid]=version
        if kind=="reference":group["reference_version_gid"]=gid
        return copy.deepcopy(version)
    def create_reference(self,**kw):return self._create("reference",**kw)
    def create_adjustment(self,**kw):return self._create("adjustment",**kw)
    def create_generated(self,**kw):return self._create("generated_initial",**kw)
    def set_current(self,*,group_gid,version_gid,expected_current,actor_gid):
        group=self.groups.get(group_gid)
        if not group or version_gid not in self.versions or self.versions[version_gid]["group_gid"]!=group_gid:raise VppsGroupError("vpps_group_version_invalid")
        if group["current_version_gid"]!=expected_current:raise VppsGroupError("resource_version_conflict")
        group["current_version_gid"]=version_gid;group["row_version"]+=1;return copy.deepcopy(group)


class MysqlBopVppsGroupStore:
    def __init__(self,connection_factory=get_craft_conn):self._connect=connection_factory
    def create_version(self,*,group_gid,tenant_gid,actor_gid,version_kind,members,expected_current=None,reference_version_gid=None,matcher_policy_hash=None,evidence_refs=()):
        if version_kind not in {"reference","generated_initial","adjustment"}:raise VppsGroupError("vpps_version_kind_invalid")
        root,version_gid=str(next_gid()),str(next_gid());normalized=[{**m,"parent_scope_gid":str(m.get("parent_scope_gid") or root)} for m in members]
        if len({(m["parent_scope_gid"],m["order_key"]) for m in normalized})!=len(normalized):raise VppsGroupError("vpps_order_conflict")
        with self._connect() as conn,conn.cursor() as cur:
            cur.execute("SELECT reference_group_version_gid,current_group_version_gid FROM workmanship_craft_bop_vpps_groups WHERE gid=%s FOR UPDATE",(group_gid,));group=cur.fetchone()
            if not group:raise VppsGroupError("vpps_group_not_found")
            if version_kind=="generated_initial":
                cur.execute("SELECT gid,root_scope_gid,content_hash FROM workmanship_craft_bop_vpps_group_versions WHERE target_group_gid=%s AND reference_version_gid=%s AND matcher_policy_hash=%s",(group_gid,reference_version_gid,matcher_policy_hash)); prior=cur.fetchone()
                if prior:return {"version_gid":str(prior["gid"]),"group_gid":group_gid,"version_kind":version_kind,"root_scope_gid":str(prior["root_scope_gid"]),"reference_version_gid":reference_version_gid,"matcher_policy_hash":matcher_policy_hash,"content_hash":prior["content_hash"],"members":normalized}
            if version_kind=="adjustment" and (str(group["current_group_version_gid"]) if group["current_group_version_gid"] else None)!=expected_current:raise VppsGroupError("resource_version_conflict")
            ref=reference_version_gid or group["reference_group_version_gid"]
            cur.execute("INSERT INTO workmanship_craft_bop_vpps_group_versions (gid,target_group_gid,version_kind,reference_version_gid,root_scope_gid,matcher_policy_hash,content_hash,actor_gid,actor_type,evidence_refs_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'user',%s)",(version_gid,group_gid,version_kind,ref,root,matcher_policy_hash,_hash(normalized),actor_gid,json.dumps(list(evidence_refs))))
            for m in normalized:cur.execute("INSERT INTO workmanship_craft_bop_vpps_group_members (gid,group_version_gid,vpps_gid,parent_scope_gid,node_level,order_key,source_bop_node_gid,source_node_lineage_gid) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",(str(next_gid()),version_gid,m["vpps_gid"],m["parent_scope_gid"],m["node_level"],m["order_key"],m.get("source_bop_node_gid"),m.get("source_node_lineage_gid")))
            if version_kind=="reference":cur.execute("UPDATE workmanship_craft_bop_vpps_groups SET reference_group_version_gid=%s,row_version=row_version+1 WHERE gid=%s",(version_gid,group_gid))
        return {"version_gid":version_gid,"group_gid":group_gid,"version_kind":version_kind,"root_scope_gid":root,"reference_version_gid":str(ref) if ref else None,"matcher_policy_hash":matcher_policy_hash,"content_hash":_hash(normalized),"members":normalized}
    def set_current(self,*,group_gid,version_gid,expected_current,tenant_gid,actor_gid):
        with self._connect() as conn,conn.cursor() as cur:
            cur.execute("SELECT current_group_version_gid,reference_group_version_gid,row_version FROM workmanship_craft_bop_vpps_groups WHERE gid=%s FOR UPDATE",(group_gid,));g=cur.fetchone()
            current=str(g["current_group_version_gid"]) if g and g["current_group_version_gid"] else None
            if not g or current!=expected_current:raise VppsGroupError("resource_version_conflict")
            cur.execute("SELECT gid FROM workmanship_craft_bop_vpps_group_versions WHERE gid=%s AND target_group_gid=%s",(version_gid,group_gid))
            if not cur.fetchone():raise VppsGroupError("vpps_group_version_invalid")
            cur.execute("UPDATE workmanship_craft_bop_vpps_groups SET current_group_version_gid=%s,row_version=row_version+1 WHERE gid=%s",(version_gid,group_gid))
        return {"group_gid":group_gid,"current_version_gid":version_gid,"reference_version_gid":str(g["reference_group_version_gid"]) if g["reference_group_version_gid"] else None,"row_version":g["row_version"]+1}


__all__=["VppsGroupError","MemoryBopVppsGroupStore","MysqlBopVppsGroupStore"]
