"""Lightweight derived assembly evidence; never changes a frozen snapshot.

Input: all nodes of ONE authorized pinned snapshot, as query@2 properties nodes.
spatial_authority is trusted backend configuration, never request/UI data.
No missing relative transform is inferred from potentially synthetic absolutes.
"""
import json
import math
from collections import Counter

PLMXML_AUTHORITY={'document':'Siemens Structure Manager PLM00048 12.1 (2019), 3-28 through 3-30','url':'https://studylib.net/doc/25739582/structure-manager','hosting':'third-party mirror of Siemens-authored manual','unit':'m','evidence':'documented','installation_verified':False}

def _matrix(field):
 if field is None or field.get('read_state')!='value':return None,'missing'
 try:
  value=json.loads(field['value_json'])
  if value in (None,'',[]):return None,'missing'
  tokens=value.split() if isinstance(value,str) else value
  if not isinstance(tokens,list) or len(tokens)!=16 or any(isinstance(x,bool) for x in tokens):return None,'invalid'
  values=[float(x) for x in tokens]
  if not all(math.isfinite(x) for x in values):return None,'invalid'
  return values,None
 except (ValueError,TypeError,KeyError):return None,'invalid'

def _multiply(a,b):
 return [sum(a[r*4+k]*b[k*4+c] for k in range(4)) for r in range(4) for c in range(4)]

def build_cached_assembly_projection(snapshot_nodes,spatial_authority=None):
 """Return bounded-per-node evidence for a complete fixed snapshot.

 Caller supplies fixed identity separately and checks batch permissions/pins.
 Verified installation authority requires a backend-reviewed evidence_ref;
 numerical validation alone never grants verified physical units/geometry.
 """
 authority=dict(spatial_authority or PLMXML_AUTHORITY)
 verified=authority.get('installation_verified') is True and bool(authority.get('evidence_ref')) and authority.get('unit')=='m'
 prepared={}
 for node in snapshot_nodes:
  key=node['node_key']
  if key in prepared:raise ValueError('duplicate_node_key')
  fields={f['field']:f for f in node.get('properties_result',{}).get('raw_fields',[])}
  local,le=_matrix(fields.get('bl_plmxml_occ_xform'));absolute,ae=_matrix(fields.get('bl_plmxml_abs_xform'))
  absolute_state=fields.get('bl_plmxml_abs_xform',{}).get('read_state','missing')
  if absolute_state=='value':absolute_state=('empty' if ae=='missing' else ae) or 'value'
  prepared[key]=(node,local,le,absolute,ae,absolute_state)
 result=[];counts=Counter()
 for key,(node,local,le,absolute,ae,absolute_state) in prepared.items():
  parent=node.get('parent_occurrence_id');error=None;residual=None
  if parent is None:
   transform=absolute;state='root_absolute' if absolute else ae;error='root_absolute_'+str(ae) if ae else None
  elif le:
   transform=None;state=le;error='relative_missing_absolute_may_be_placeholder' if le=='missing' else 'relative_transform_invalid'
  elif ae:
   transform=None;state=ae;error='absolute_transform_'+ae
  elif parent not in prepared or prepared[parent][3] is None:
   transform=None;state='missing';error='parent_absolute_unavailable'
  else:
   residual=max(abs(a-b) for a,b in zip(_multiply(local,prepared[parent][3]),absolute))
   state='source_validated' if residual<=1e-6 else 'inconsistent';transform=local if state=='source_validated' else None
   if transform is None:error='transform_composition_mismatch'
  counts[state]+=1
  semantics={'status':'verified' if verified and transform is not None else 'unverified','unit':authority.get('unit'),'unit_evidence':authority.get('evidence','unverified'),'layout':'row_major','vector_convention':'row_vector','reference_frame':'world' if parent is None else 'parent','direction':'root_to_world' if parent is None else 'local_to_parent'}
  result.append({'node_key':key,'parent_node_key':parent,'name':node.get('name') or node.get('display_name') or key,'item_revision_uid':node.get('item_revision_uid'),'relative_transform':transform if parent is not None else None,'root_transform':transform if parent is None else None,'absolute_transform':absolute,'absolute_read_state':absolute_state,'geometry_refs':node.get('geometry_refs'),'spatial_semantics':semantics,'transform_state':state,'error_code':error,'composition_max_abs_error':residual})
 return {'nodes':result,'transform_states':dict(counts),'spatial_authority':authority,'projection_version':1}
