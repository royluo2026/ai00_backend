from plugins.simulation.tests.test_cache_source_open import case,database,IDENTITY,admit
from plugins.simulation.simulation_backend.application.cache_preparation import prepare_cached_assembly
from plugins.simulation.simulation_backend.capabilities.cache_tc_open import TcCacheSourceOpenProvider

def test_tc_open_uses_prepared_shared_metadata_and_never_upload_receipts(case):
    base=case.provider
    prepared=prepare_cached_assembly(case.projection,endpoint_id='tc-production')
    provider=TcCacheSourceOpenProvider(base.files,connect=base.connect,load=lambda *args:prepared)
    provider.runtime=lambda context:(case.runtime,base.connector.clock())
    base.cache._read=lambda *args:dict(source_selector=dict(endpoint_id="tc-production"))
    case.provider=provider
    page=provider.inspect(case.payload,case.context).data
    assert page['files'][0]['operation_id'] is None
    result=admit(case)
    assert case.creates==0 and case.receipts==0 and case.authorizations==0
    packet=case.queue[0]['steps'][0]['payload']
    assert case.queue[0]['steps'][0]['operation_id']=='vismockup.model.open@3'
    assert 'artifact_ref' not in str(packet) and packet['tc_dependencies'][0]['file_ref']['file_uid']=='file'
    assert result['identity']==IDENTITY
