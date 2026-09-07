"""Finalized immutable desktop file references; no caller filesystem paths or URLs."""
from backend.capability_v2.atomic_web_contracts import obj
from backend.capability_v2.contracts import ArtifactRef
from backend.platform_sdk.artifacts import require_artifact, read_artifact, create_artifact

REF=ArtifactRef.model_json_schema()
NAME={'type':'string','minLength':1,'maxLength':255,'pattern':r'^[^/\\\x00-\x1f]+$'}
MIME={'enum':['text/markdown','text/plain','text/csv','application/json']}
TEXT={'type':'string','maxLength':1048576}
OUTPUT=obj({'artifact_ref':REF,'name':NAME},('artifact_ref','name'))

def adopt(payload,context):
    return {'artifact_ref':require_artifact(payload['artifact_ref'],context),'name':payload['name']}

def text_get(payload,context):
    ref=require_artifact(payload['artifact_ref'],context)
    if ref['media_type'] not in MIME['enum']: raise ValueError('This ArtifactRef is not a text document.')
    return {'artifact_ref':ref,'content':read_artifact(ref,context,maximum=1048576).decode('utf-8-sig')}

def text_create(payload,context):
    return {'artifact_ref':create_artifact(payload['content'].encode('utf-8'),payload['media_type'],context),'name':payload['name']}

def revise(payload,context):
    require_artifact(payload['previous_artifact_ref'],context)
    return adopt(payload,context)

def batch(payload,context):
    return {'artifacts':[adopt(item,context) for item in payload['artifacts']]}

def bytes_get(payload,context):
    import base64
    ref=require_artifact(payload['artifact_ref'],context)
    return {'artifact_ref':ref,'data_base64':base64.b64encode(read_artifact(ref,context)).decode('ascii')}

DEFINITIONS=[
 ('base.artifact.batch.import',batch,obj({'artifacts':{'type':'array','items':OUTPUT,'minItems':1,'maxItems':20}},('artifacts',)),obj({'artifacts':{'type':'array','items':OUTPUT,'minItems':1,'maxItems':20}},('artifacts',)),False,'','Adopts up to 20 finalized artifacts selected and uploaded by Main under the authenticated owner.'),
 ('base.artifact.bytes.get',bytes_get,obj({'artifact_ref':REF},('artifact_ref',)),obj({'artifact_ref':REF,'data_base64':{'type':'string','maxLength':6990510}},('artifact_ref','data_base64')),False,'','Reads one owned immutable artifact for preview with size and hash verification.'),
 ('base.artifact.import',adopt,obj({'artifact_ref':REF,'name':NAME},('artifact_ref','name')),OUTPUT,False,'','Adopts one finalized artifact selected and uploaded by Main, preserving its immutable hash, size and MIME.'),
 ('base.artifact.get',adopt,obj({'artifact_ref':REF,'name':NAME},('artifact_ref','name')),OUTPUT,False,'','Authorizes one immutable artifact for Main preview or native download.'),
 ('base.artifact.text.get',text_get,obj({'artifact_ref':REF},('artifact_ref',)),obj({'artifact_ref':REF,'content':TEXT},('artifact_ref','content')),False,'','Reads an owned bounded text artifact with verified hash and UTF-8 decoding.'),
 ('base.artifact.text.create',text_create,obj({'content':TEXT,'media_type':MIME,'name':NAME},('content','media_type','name')),OUTPUT,True,'','Creates a new immutable text artifact from the user document content.'),
 ('base.artifact.revise',revise,obj({'previous_artifact_ref':REF,'artifact_ref':REF,'name':NAME},('previous_artifact_ref','artifact_ref','name')),OUTPUT,True,'','Associates a newly selected immutable replacement after checking access to both revisions.'),
]
