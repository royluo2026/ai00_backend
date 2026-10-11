"""TC-backed local-open contract: no cloud JT artifacts or caller local paths."""
from typing import Literal, Any
from pydantic import BaseModel,ConfigDict,Field
from .cache_open_evidence import CacheBinding, cache_package_hash
from .live_document_identity import NativeDocumentIdentity

# Bounds on metadata, not on the JT geometry files fetched by the client.
MAX_ASSEMBLY_XML_BYTES = 64 * 1024 * 1024
MAX_CACHE_OPEN_PACKET_BYTES = 96 * 1024 * 1024

class ClosedModel(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
class TcFileReference(ClosedModel):
    dependency_key:str=Field(pattern='^[a-f0-9]{64}$')
    endpoint_id:str=Field(min_length=1,max_length=512)
    dataset_uid:str=Field(min_length=1,max_length=512)
    file_uid:str=Field(min_length=1,max_length=128)
    file_name:str=Field(min_length=1,max_length=512)
    relation_type:Literal['IMAN_Rendering']
class TcDependency(ClosedModel):
    package_path:str=Field(pattern='^dependencies/[a-f0-9]{64}[.]jt$')
    file_ref:TcFileReference
    node_key:str=Field(min_length=1,max_length=512)
    item_revision_uid:str=Field(min_length=1,max_length=512)
class TcCacheOpenPayload(ClosedModel):
    cache_binding:CacheBinding
    preparation_hash:str=Field(pattern='^sha256:[a-f0-9]{64}$')
    package_hash:str=Field(pattern='^sha256:[a-f0-9]{64}$')
    source_selector:dict[str,Any]
    assembly_xml:str=Field(min_length=1,max_length=MAX_ASSEMBLY_XML_BYTES)
    tc_dependencies:list[TcDependency]=Field(max_length=10000)
class LocalFileProof(ClosedModel):
    dependency_key:str=Field(pattern='^[a-f0-9]{64}$')
    sha256:str=Field(pattern='^[a-f0-9]{64}$')
    byte_size:int=Field(ge=24,le=512*1024*1024)
class OpenedTcCacheResult(ClosedModel):
    protocol:Literal['ai00.viewer.opened-tc-cache.v1']
    cache_binding:CacheBinding
    package_hash:str=Field(pattern='^sha256:[a-f0-9]{64}$')
    files:list[LocalFileProof]=Field(max_length=10000)
    document_identity:NativeDocumentIdentity

def contract():
    def inline(schema):
        definitions=schema.pop('$defs',{})
        def visit(value):
            if isinstance(value,dict):
                if '$ref' in value:return visit(definitions[value['$ref'].split('/')[-1]])
                return {k:visit(v) for k,v in value.items() if k!='title'}
            if isinstance(value,list):return [visit(v) for v in value]
            return value
        return visit(schema)
    return dict(id='vismockup.model.open@3',input=inline(TcCacheOpenPayload.model_json_schema()),output=inline(OpenedTcCacheResult.model_json_schema()))
TC_OPEN_CONTRACT=contract()
TC_OPEN_CONTRACT_HASH=cache_package_hash(TC_OPEN_CONTRACT)
