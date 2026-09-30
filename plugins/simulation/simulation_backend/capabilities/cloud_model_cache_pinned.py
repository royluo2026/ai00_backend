"""Closed query@2 envelope; TC property bags intentionally remain extensible."""
from .connector_contracts import obj,TC_NODE_PROPERTIES_RESULT,TC_NODE_PROPERTY_VALUES,TC_GEOMETRY_REF,TC_CHILDREN_RESULT


def contracts(batch):
    text={'type':'string','maxLength':512};nullable_text={'type':['string','null'],'maxLength':512}
    generation={'type':['string','null'],'pattern':'^[a-f0-9]{32}$'}
    sha={'type':['string','null'],'pattern':'^sha256:[a-f0-9]{64}$'}
    identity=obj({'batch_id':batch['properties']['batch_id'],'generation':generation,'snapshot_hash':sha,'schema_version':{'const':1,'type':'integer'}},('batch_id','generation','snapshot_hash','schema_version'))
    readiness=obj({key:{'type':'string','enum':values} for key,values in {
        'structure':['complete'],'properties':['complete','complete_with_unavailable','unverified'],
        'geometry_references':['complete','partial','unverified'],'geometry_files':['not_requested']}.items()},('structure','properties','geometry_references','geometry_files'))
    spatial=obj({'status':{'const':'unverified','type':'string'},**{key:{'type':'null'} for key in ('unit','layout','reference_frame','direction')}},('status','unit','layout','reference_frame','direction'))
    values={**obj(TC_NODE_PROPERTY_VALUES['properties']), 'patternProperties':{'.*':{}}}
    raw_field=obj({'object_uid':text,'object_kind':text,'field':text,'read_state':{'type':'string','enum':['value','null','unavailable']},'value_json':{'type':'string','maxLength':8388608}},('object_uid','object_kind','field','read_state','value_json'))
    properties_result=obj({**TC_NODE_PROPERTIES_RESULT['properties'],'properties':values,'raw_fields':{'type':'array','maxItems':64,'items':raw_field}},('source_identity_hash','captured_at','cache_hit','properties','raw_fields'))
    manifest=obj({**batch['properties'],**identity['properties'],'configuration_date':nullable_text,'capture_started_at':nullable_text,'structure_hash':sha,'snapshot_hash_algorithm':nullable_text,'hash_status':{'type':'string','enum':['available','unavailable']},'readiness':readiness,'spatial_semantics':spatial},tuple(sorted(set(batch['required'])|set(identity['required'])|{'configuration_date','capture_started_at','structure_hash','snapshot_hash_algorithm','hash_status','readiness','spatial_semantics'})))
    node=obj({'node_key':text,'occurrence_id':text,'parent_occurrence_id':nullable_text,'occurrence_path':{'type':'array','maxItems':128,'items':obj({'occurrence_uid':text,'item_revision_uid':text},('occurrence_uid','item_revision_uid'))},
              'depth':{'type':'integer','minimum':0,'maximum':128},'child_order':{'type':'integer','minimum':0},'child_count':{'type':'integer','minimum':0},'name':{'type':'string'},'item_revision_uid':text,'revision_id':text,'component_type':nullable_text,'has_children':{'type':'boolean'},
              'properties_result':properties_result,'geometry_refs':{'type':['array','null'],'items':TC_GEOMETRY_REF}},('node_key','occurrence_id','parent_occurrence_id','occurrence_path','has_children'))
    structure=obj({key:value for key,value in node['properties'].items() if key not in ('node_key','properties_result','geometry_refs')},('occurrence_id','parent_occurrence_id','occurrence_path','has_children'))
    node['properties']['raw_snapshot']=obj({'structure':structure,'page':obj({key:value for key,value in TC_CHILDREN_RESULT['properties'].items() if key not in ('parent','nodes')},('child_count',)),'properties_result':properties_result},('structure','page','properties_result'))
    input_schema=obj({'batch_id':identity['properties']['batch_id'],'scope':{'type':'string','enum':['roots','batch','children','node']},'node_key':nullable_text,'projection':{'type':'string','enum':['structure','properties','raw']},'cursor':{'type':['string','null'],'maxLength':2048},'page_size':{'type':'integer','minimum':1,'maximum':500},'expected_generation':generation,'expected_snapshot_hash':sha},('batch_id',))
    output_schema=obj({'identity':identity,'manifest':{'anyOf':[manifest,{'type':'null'}]},'nodes':{'type':'array','maxItems':500,'items':node},'next_cursor':{'type':['string','null'],'maxLength':2048}},('identity','manifest','nodes','next_cursor'))
    return input_schema,output_schema
