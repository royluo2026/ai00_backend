from plugins.simulation.tests.test_cache_source_open import case,database,IDENTITY,admit
from plugins.simulation.simulation_backend.application.cache_preparation import prepare_cached_assembly
from plugins.simulation.simulation_backend.capabilities.cache_tc_open import TcCacheSourceOpenProvider
import pytest
from backend.capability_v2.provider_contracts import CapabilityBusinessError
from plugins.simulation.simulation_backend.capabilities.connector_runtime import ConnectorError

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

@pytest.mark.parametrize('code',['connector_offline','adapter_contract_mismatch','plan_payload_too_large'])
def test_native_admission_preserves_connector_rejection_without_generic_materialization_error(case,code):
    base=case.provider
    prepared=prepare_cached_assembly(case.projection,endpoint_id='tc-production')
    provider=TcCacheSourceOpenProvider(base.files,connect=base.connect,load=lambda *args:prepared)
    provider.runtime=lambda context:(case.runtime,base.connector.clock())
    base.cache._read=lambda *args:dict(source_selector=dict(endpoint_id='tc-production'))
    def rejected(*args,**kwargs):
        raise ConnectorError(code)
    provider.connector.queue_v2=rejected
    case.provider=provider
    with pytest.raises(CapabilityBusinessError) as error:
        admit(case)
    assert error.value.code==code
    assert case.creates==0 and not case.queue

def test_materialization_diagnostics_never_log_input_or_exception_message(caplog):
    from plugins.simulation.simulation_backend.capabilities.cache_source_open import _log_materialization_error
    from plugins.simulation.simulation_backend.application.cache_tc_open_contract import TcCacheOpenPayload
    try:
        TcCacheOpenPayload.model_validate({'private_payload':'DO_NOT_LOG_THIS_VALUE'})
    except ValueError as error:
        _log_materialization_error(error)
    assert 'ValidationError' in caplog.text and 'cache_binding' in caplog.text
    assert 'DO_NOT_LOG_THIS_VALUE' not in caplog.text

@pytest.mark.parametrize(('character','count'),[('x',64*1024*1024+1),('门',64*1024*1024//3+1)],ids=['ascii_overlimit','utf8_overlimit'])
def test_oversized_assembly_rejected_during_inspection_before_any_native_effect(case,monkeypatch,character,count):
    from plugins.simulation.simulation_backend.capabilities import cache_tc_open
    base=case.provider
    prepared=prepare_cached_assembly(case.projection,endpoint_id='tc-production')
    provider=TcCacheSourceOpenProvider(base.files,connect=base.connect,load=lambda *args:prepared)
    monkeypatch.setattr(cache_tc_open,'scoped_preparation',lambda *args,**kwargs:{'assembly_xml':character*count})
    with pytest.raises(CapabilityBusinessError) as error:
        provider.inspect(case.payload,case.context)
    assert error.value.code=='cache_package_result_limit'
    assert case.creates==0 and not case.queue

@pytest.mark.parametrize(('character','count'),[('门',3*1024*1024),('x',63*1024*1024)],ids=['utf8_above_old_limit','near_new_limit'])
def test_assembly_above_old_limit_can_be_inspected_and_queued(case,monkeypatch,character,count):
    from plugins.simulation.simulation_backend.capabilities import cache_tc_open
    base=case.provider
    prepared=prepare_cached_assembly(case.projection,endpoint_id='tc-production')
    original=cache_tc_open.scoped_preparation
    def large_scope(*args,**kwargs):
        scope=original(*args,**kwargs)
        scope['assembly_xml'] += '<!--' + character*count + '-->'
        return scope
    monkeypatch.setattr(cache_tc_open,'scoped_preparation',large_scope)
    provider=TcCacheSourceOpenProvider(base.files,connect=base.connect,load=lambda *args:prepared)
    provider.runtime=lambda context:(case.runtime,base.connector.clock())
    base.cache._read=lambda *args:dict(source_selector=dict(endpoint_id='tc-production'))
    case.provider=provider
    provider.inspect(case.payload,case.context)
    admit(case)
    packet=case.queue[0]['steps'][0]['payload']
    assert len(packet['assembly_xml'].encode('utf-8'))>7*1024*1024

def test_complete_packet_limit_includes_dependency_metadata_before_admission(case):
    base=case.provider
    prepared=prepare_cached_assembly(case.projection,endpoint_id='tc-production')
    provider=TcCacheSourceOpenProvider(base.files,connect=base.connect,load=lambda *args:prepared)
    base.cache._read=lambda *args:dict(source_selector=dict(endpoint_id='tc-production',notes='x'*(96*1024*1024)))
    case.provider=provider
    with pytest.raises(CapabilityBusinessError) as error:
        admit(case)
    assert error.value.code=='cache_package_result_limit'
    assert case.creates==0 and not case.queue
