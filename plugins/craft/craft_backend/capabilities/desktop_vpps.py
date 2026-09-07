"""Exact closed VPPS projection over the existing Craft validation service."""
from jsonschema import Draft202012Validator
from backend.capability_v2.atomic_web_contracts import obj
from backend.capability_v2.contracts import ExposurePolicy, BusinessInvariantContract
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec
from backend.capability_v2.provider_contracts import CapabilitySpec, CapabilityBusinessError
from .vpps_check import check_vpps

TEXT={'type':'string','maxLength':4096}
NUM={'type':'integer','minimum':0,'maximum':500}
def array(model):return {'type':'array','items':model,'maxItems':500}
ERROR=obj({'rule':{'enum':[1,2,3,4]},'row':NUM,**{key:TEXT for key in ('vpps','msg','gid','vpps_desc')}},('rule','row','vpps','msg'))
OUTPUT=obj({'snapshot':obj({key:TEXT for key in ('gid','version_tag','name')},('gid','version_tag','name')),'summary':obj({**{key:NUM for key in ('total_parts','parts_with_vpps','rule1_errors','rule2_errors','rule3_errors','rule4_errors','rule4_ignored','alias_matches')},'ok':{'type':'boolean'}}),'errors':obj({key:array(ERROR) for key in ('rule1','rule2','rule3','rule4')},('rule1','rule2','rule3','rule4')),'alias_matches':array(obj({'vpps':TEXT,'row':NUM,'desc':TEXT},('vpps','row','desc'))),'rule4_ignored':array(obj({'vpps':TEXT,'row':NUM},('vpps','row')))},('snapshot','summary','errors','alias_matches','rule4_ignored'))
INPUT=obj({'snapshot_gid':{**TEXT,'minLength':1,'maxLength':128}},('snapshot_gid',))
ID='craft.pbom.vpps_validation.get'

def validate(payload,context):
    if not Draft202012Validator(INPUT).is_valid(payload):raise CapabilityBusinessError('invalid_input','Select one PBOM snapshot.')
    result=check_vpps({'operation':'check',**payload},context).data
    if not Draft202012Validator(OUTPUT).is_valid(result):raise CapabilityBusinessError('provider_error','The VPPS result exceeds its closed projection.')
    return result

def register_desktop_vpps(registry):
    effect='Runs the four VPPS validation rules for one authenticated-readable Craft PBOM snapshot and returns bounded errors and concessions.'
    spec=CapabilitySpec(id=ID,version=1,owner='craft',description=effect,use_when=effect,do_not_use_when='Mutating a snapshot or its concessions.',risk='read',permissions=('craft.read',),input_schema=INPUT,output_schema=OUTPUT)
    descriptor=descriptor_from_provider_spec(spec).model_copy(update={'business_effect':effect,'business_acceptance_criteria':(effect,'At most 500 parts and 500 errors are returned.'),'business_invariants':(BusinessInvariantContract(rule_id=ID+'.read_only',version=1,statement='The real validator performs no writes and uses a single snapshot identifier.',applies_when='The validation runs.',enforcement_ref='plugins/craft/craft_backend/capabilities/vpps_check.py:check_vpps',error_code='resource_not_found',test_refs=('backend/tests/test_desktop_round5_remaining.py',)),),'no_business_invariant_reason':None,'exposure':ExposurePolicy(web=True,api=True,plugin=False,agent=False,mcp=False),'evidence_policy':'optional'})
    registry.register(spec,validate,descriptor=descriptor)
