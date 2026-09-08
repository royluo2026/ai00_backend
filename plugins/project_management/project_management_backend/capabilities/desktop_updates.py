"""Closed Task/Issue updates; the historical v1 contracts stay frozen."""
from copy import deepcopy
from backend.capability_v2.contracts import ArtifactRef
from backend.platform_sdk.artifacts import require_artifact
from ..application.service import _TASK_UPDATE_FIELDS, _ISSUE_UPDATE_FIELDS
from .provider import register_capability


def register_updates(registry):
    from .reviewed import _object, _WORK_ITEM
    attachment=_object({'name':{'type':'string','maxLength':255},'mime':{'type':'string','maxLength':128},
        'url':{'type':'string','pattern':'^artifact:','maxLength':4096},'artifact_ref':ArtifactRef.model_json_schema()},required=('name','artifact_ref'))
    for kind,fields in (('task',_TASK_UPDATE_FIELDS),('issue',_ISSUE_UPDATE_FIELDS)):
        properties={name:deepcopy(_WORK_ITEM['properties'][name]) for name in fields}
        for value in properties.values():
            if value.get('type')==['string','null']:value['maxLength']=65536
        properties['attachments']={'type':'array','maxItems':200,'items':attachment}
        properties['feishu_groups']={'type':'array','maxItems':200,'items':_object({key:{'type':'string','maxLength':2048} for key in ('chat_id','name','avatar')})}
        properties['feishu_docs']={'type':'array','maxItems':200,'items':_object({key:{'type':'string','maxLength':2048} for key in ('token','name','title','url','type')})}
        updates={**_object(properties),'minProperties':1}
        schema=_object({'arguments':_object({'gid':{'type':'string','minLength':1,'maxLength':128},'updates':updates},required=('gid','updates'))},required=('arguments',))
        original=registry.get(f'project.{kind}.change.apply.atomic.{kind}s_update',1)
        def handler(payload,context,_handler=original.handler):
            for value in payload['arguments']['updates'].get('attachments',[]):require_artifact(value['artifact_ref'],context)
            return _handler(payload,context)
        spec=original.spec.model_copy(update={'version':2,'input_schema':schema,'output_schema':_object({'data':_object({'success':{'const':True}},required=('success',))},required=('data',))})
        register_capability(registry,spec,handler)
