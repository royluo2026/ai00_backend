"""Major-2 result boundary for the existing Craft library operation matrix."""
from backend.capability_v2.provider_contracts import CapabilityOutput
from .library_change import change_library, _OPERATIONS

def _object(properties, required):
    return {'type':'object','properties':properties,'required':list(required),'additionalProperties':False}

OUTPUT_SCHEMA={'oneOf':[]}
for operation in _OPERATIONS:
    fields={'operation':{'const':operation},'success':{'const':True}}
    if operation.endswith('.create'):
        fields['data']=_object({'gid':{'type':'string','minLength':1,'maxLength':128}},('gid',))
    elif operation.endswith('.batch_add_from_pbom'):
        fields.update({key:{'type':'integer','minimum':0,'maximum':500} for key in ('added','skipped')})
    elif operation.endswith(('.accept_alias','.batch_accept_alias')):
        fields.update({key:{'type':'integer','minimum':0,'maximum':500} for key in ('processed','failed')})
        fields.update(accepted_by={'type':'string','maxLength':128},accepted_at={'type':'string','maxLength':32})
    OUTPUT_SCHEMA['oneOf'].append(_object(fields,tuple(fields)))

def change_library_v2(payload,context):
    """Keep v1 business behavior; identify the exact closed result branch."""
    outcome=change_library(payload,context)
    return CapabilityOutput(data={'operation':payload['operation'],**outcome.data},evidence=outcome.evidence)
