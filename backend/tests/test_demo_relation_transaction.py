"""Own relation transactions remain uncommitted until Gateway accepts output."""
import asyncio
from contextlib import contextmanager
import json
import threading
from unittest.mock import MagicMock

import pytest

from backend.capabilities.models_next import CapabilityContext
from backend.capability_v2.gateway import CapabilityGatewayService
from backend.capability_v2.reliability import TransactionalCapabilityOutput
from backend.capability_v2.reliability import transactional_provider
from plugins.craft.craft_backend.capabilities import demo_relation_change as relation
from plugins.craft.craft_backend.capabilities import provider
from plugins.craft.craft_backend.data import connection, bop_migration_fence


@pytest.fixture
def transaction_case(monkeypatch):
    transaction=MagicMock();transaction.cursor.return_value.__enter__.return_value=MagicMock()
    monkeypatch.setattr(connection,'open_craft_transaction',lambda:transaction,raising=False)
    @contextmanager
    def ordinary_connection():
        try:
            yield transaction
            transaction.commit()
        except BaseException:
            transaction.rollback()
            raise
        finally:transaction.close()
    monkeypatch.setattr(connection,'get_conn',ordinary_connection)
    validation=MagicMock()
    monkeypatch.setattr(relation,'_require_demo_version',validation)
    monkeypatch.setattr(relation,'_connect',lambda *args:{'ok':True,'operation':'connect'})
    monkeypatch.setattr(relation,'_reset',lambda *args:{'ok':True,'operation':'reset'})
    return transaction,validation,CapabilityContext(user_gid='actor',active_roles=('super_admin',))


@pytest.mark.parametrize('operation',['connect','reset'])
def test_write_returns_open_transaction_without_early_commit(transaction_case,operation):
    tx,validation,context=transaction_case
    result=relation.apply_demo_relation_change({'operation':operation,'bop_gid':'demo','line_gid':'line'},context)
    assert isinstance(result,TransactionalCapabilityOutput)
    assert result.transaction is tx and result.data=={'data':{'ok':True,'operation':operation}}
    tx.commit.assert_not_called();tx.rollback.assert_not_called();tx.close.assert_not_called()
    validation.assert_called_once_with(tx.cursor.return_value.__enter__.return_value,'demo',context)


@pytest.mark.parametrize('operation',['connect','reset'])
def test_write_failure_rolls_back_and_closes_owned_transaction(transaction_case,monkeypatch,operation):
    tx,_,context=transaction_case
    def fail(*args):raise ValueError('provider rejected')
    monkeypatch.setattr(relation,'_'+operation,fail)
    with pytest.raises(ValueError,match='provider rejected'):
        relation.apply_demo_relation_change({'operation':operation,'bop_gid':'demo'},context)
    tx.rollback.assert_called_once();tx.close.assert_called_once();tx.commit.assert_not_called()


def test_status_keeps_normal_read_connection(transaction_case,monkeypatch):
    tx,_,context=transaction_case
    read=MagicMock()
    @contextmanager
    def read_connection():
        yield read
        read.commit()
    monkeypatch.setattr(connection,'get_conn',read_connection)
    monkeypatch.setattr(relation,'_status',lambda *args:{'ok':True,'operation':'status'})
    result=relation.apply_demo_relation_change({'operation':'status','bop_gid':'demo'},context)
    assert result=={'data':{'ok':True,'operation':'status'}}
    read.commit.assert_called_once();tx.cursor.assert_not_called()


def test_open_craft_transaction_explicitly_begins_and_never_autocommits(monkeypatch):
    tx=MagicMock();pool=MagicMock();pool.connection.return_value=tx
    monkeypatch.setattr(connection,'_get_pool',lambda:pool)
    monkeypatch.setattr(connection,'wrap_connection',lambda value:value)
    assert connection.open_craft_transaction() is tx
    tx.begin.assert_called_once();tx.commit.assert_not_called();tx.close.assert_not_called()


def test_open_craft_transaction_begin_failure_closes(monkeypatch):
    tx=MagicMock();tx.begin.side_effect=ValueError('begin failed');pool=MagicMock();pool.connection.return_value=tx
    monkeypatch.setattr(connection,'_get_pool',lambda:pool)
    monkeypatch.setattr(connection,'wrap_connection',lambda value:value)
    with pytest.raises(ValueError,match='begin failed'):connection.open_craft_transaction()
    tx.close.assert_called_once();tx.commit.assert_not_called()


def registered_handler():
    registry=MagicMock()
    relation.register_demo_relation_change_capability(provider.NativeContractRegistry(registry))
    return registry.register.call_args.args[1]


@pytest.mark.parametrize('enabled',[False,True])
def test_registration_preserves_transaction_marker_and_migration_journal_data(transaction_case,monkeypatch,enabled):
    tx,_,context=transaction_case
    monkeypatch.setenv('AI00_BOP_REPOSITORY_MIGRATION_FENCE_ENABLED','1' if enabled else '0')
    journal=MagicMock();cursor=journal.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value={'status':'report_only'}
    @contextmanager
    def journals():yield journal
    original=bop_migration_fence.legacy_write_lease
    monkeypatch.setattr(bop_migration_fence,'legacy_write_lease',lambda capability,ctx:original(capability,ctx,connection_factory=journals))
    handler=registered_handler()
    assert getattr(handler,'__capability_transactional__',False)
    result=handler({'operation':'connect','bop_gid':'demo'},context)
    assert result.transaction.cursor() is tx.cursor.return_value
    assert not any('write_journal' in call.args[0] for call in cursor.execute.call_args_list)
    result.transaction.commit()
    statements=[call.args for call in cursor.execute.call_args_list]+[call.args for call in tx.cursor.return_value.__enter__.return_value.execute.call_args_list]
    written=[args[1] for args in statements if 'write_journal' in args[0]]
    assert bool(written)==enabled
    if written:assert json.loads(written[0][-1])==result.data
    tx.commit.assert_called_once()


@pytest.mark.parametrize('enabled',[False,True])
def test_migration_guard_failure_preserves_cleanup(transaction_case,monkeypatch,enabled):
    tx,_,context=transaction_case
    monkeypatch.setenv('AI00_BOP_REPOSITORY_MIGRATION_FENCE_ENABLED','1' if enabled else '0')
    journal=MagicMock();cursor=journal.cursor.return_value.__enter__.return_value;cursor.fetchone.return_value={'status':'report_only'}
    @contextmanager
    def journals():yield journal
    original=bop_migration_fence.legacy_write_lease
    monkeypatch.setattr(bop_migration_fence,'legacy_write_lease',lambda capability,ctx:original(capability,ctx,connection_factory=journals))
    def fail(*args):raise ValueError('write failed')
    monkeypatch.setattr(relation,'_connect',fail)
    with pytest.raises(ValueError,match='write failed'):registered_handler()({'operation':'connect','bop_gid':'demo'},context)
    tx.rollback.assert_called_once();tx.close.assert_called_once();tx.commit.assert_not_called()
    assert not any('write_journal' in call.args[0] for call in cursor.execute.call_args_list)
    if enabled:assert any('DELETE FROM' in call.args[0] for call in cursor.execute.call_args_list)


def test_gateway_timeout_rolls_back_late_relation_transaction(transaction_case,monkeypatch):
    tx,_,context=transaction_case
    entered,release,closed=threading.Event(),threading.Event(),threading.Event()
    tx.close.side_effect=closed.set
    def delayed(*args):
        entered.set()
        if not release.wait(5):raise RuntimeError('test worker was not released')
        return {'ok':True,'operation':'connect'}
    monkeypatch.setattr(relation,'_connect',delayed)
    gateway=object.__new__(CapabilityGatewayService)
    async def run():
        task=asyncio.create_task(gateway._invoke_sync_provider(registered_handler(),{'operation':'connect','bop_gid':'demo'},context,0.05))
        assert await asyncio.to_thread(entered.wait,2)
        with pytest.raises(TimeoutError):await task
        release.set()
        assert await asyncio.to_thread(closed.wait,2)
    try:asyncio.run(run())
    finally:release.set()
    tx.rollback.assert_called_once();tx.close.assert_called_once();tx.commit.assert_not_called()


@pytest.mark.parametrize('asynchronous',[False,True])
def test_guard_journal_exit_failure_cleans_output_transaction(transaction_case,monkeypatch,asynchronous):
    tx,_,context=transaction_case
    lease=MagicMock();lease.__enter__.return_value={};lease.__exit__.side_effect=ValueError('journal failed')
    monkeypatch.setattr(bop_migration_fence,'legacy_write_lease',lambda *args:lease)
    registry=MagicMock()
    relation.register_demo_relation_change_capability(provider.NativeContractRegistry(registry))
    spec=registry.register.call_args.args[0]
    if asynchronous:
        @transactional_provider
        async def handler(payload,ctx):return TransactionalCapabilityOutput(data={'data':{'ok':True}},transaction=tx)
    else:handler=relation.apply_demo_relation_change
    provider.register_capability(registry,spec,handler)
    guarded=registry.register.call_args.args[1]
    result=guarded({'operation':'connect','bop_gid':'demo'},context)
    if asynchronous:result=asyncio.run(result)
    lease.__exit__.assert_not_called()
    with pytest.raises(ValueError,match='journal failed'):result.transaction.commit()
    tx.rollback.assert_called_once();tx.close.assert_called_once();tx.commit.assert_not_called()
    lease.__exit__.assert_called_once()


@pytest.mark.parametrize('ending',['rollback','close'])
def test_transaction_retains_lease_until_rejection_and_never_success_journals(transaction_case,monkeypatch,ending):
    tx,_,context=transaction_case
    lease=MagicMock();lease.__enter__.return_value={}
    monkeypatch.setattr(bop_migration_fence,'legacy_write_lease',lambda *args:lease)
    result=registered_handler()({'operation':'connect','bop_gid':'demo'},context)
    lease.__exit__.assert_not_called();tx.commit.assert_not_called()
    getattr(result.transaction,ending)()
    lease.__exit__.assert_called_once()
    assert lease.__exit__.call_args.args[0] is RuntimeError
    tx.rollback.assert_called_once();tx.commit.assert_not_called()


def test_journal_prepare_failure_rolls_back_before_external_lease_cleanup(transaction_case,monkeypatch):
    tx,_,context=transaction_case
    monkeypatch.setenv('AI00_BOP_REPOSITORY_MIGRATION_FENCE_ENABLED','1')
    events=[];tx.rollback.side_effect=lambda:events.append('rollback')
    txcursor=tx.cursor.return_value.__enter__.return_value
    def prepare(sql,*args):
        events.append('prepare')
        if 'write_journal' in sql:raise ValueError('prepare failed')
    txcursor.execute.side_effect=prepare
    journal=MagicMock();cursor=journal.cursor.return_value.__enter__.return_value;cursor.fetchone.return_value={'status':'report_only'}
    cursor.execute.side_effect=lambda sql,*args:events.append('external_cleanup') if sql.startswith('DELETE FROM') else None
    @contextmanager
    def journals():yield journal
    original=bop_migration_fence.legacy_write_lease
    monkeypatch.setattr(bop_migration_fence,'legacy_write_lease',lambda capability,ctx:original(capability,ctx,connection_factory=journals))
    result=registered_handler()({'operation':'connect','bop_gid':'demo'},context)
    with pytest.raises(ValueError,match='prepare failed'):result.transaction.commit()
    assert events.index('rollback') < events.index('external_cleanup')
    tx.commit.assert_not_called();tx.close.assert_called_once()


@pytest.mark.parametrize('flag',[None,'0','true','yes'])
def test_relation_diagnostics_disabled_has_no_wrapper_or_logs(monkeypatch,capsys,flag):
    if flag is None:monkeypatch.delenv('AI00_DEMO_CAPACITY_DIAGNOSTICS',raising=False)
    else:monkeypatch.setenv('AI00_DEMO_CAPACITY_DIAGNOSTICS',flag)
    raw=MagicMock()
    cur=relation._diagnostic_cursor(raw)
    assert cur is raw
    assert relation._phase_call(cur,'tree',lambda:'unchanged')=='unchanged'
    assert capsys.readouterr().err==''


def test_relation_diagnostics_counts_execute_and_fetch_without_sensitive_content(monkeypatch,capsys):
    monkeypatch.setenv('AI00_DEMO_CAPACITY_DIAGNOSTICS','1')
    ticks=iter([0.,1.,3.,4.,7.,8.])
    monkeypatch.setattr(relation.time,'perf_counter',lambda:next(ticks))
    raw=MagicMock();raw.fetchall.return_value=[{'private':'secret-value'}]
    cur=relation._diagnostic_cursor(raw)
    def read():
        cur.execute('SELECT secret-column WHERE gid=%s',('private-id',))
        return cur.fetchall()
    assert relation._phase_call(cur,'tree',read)==[{'private':'secret-value'}]
    entry=json.loads(capsys.readouterr().err)
    assert entry=={'demo_relation_timing':True,'phase':'tree','seconds':8.0,'sql_seconds':5.0,'sql_count':1}
    assert 'secret' not in json.dumps(entry) and 'private' not in json.dumps(entry)


def test_relation_diagnostics_rejects_dynamic_phase(monkeypatch,capsys):
    monkeypatch.setenv('AI00_DEMO_CAPACITY_DIAGNOSTICS','1')
    with pytest.raises(ValueError,match='unknown diagnostic phase'):
        relation._phase_call(relation._diagnostic_cursor(MagicMock()),'private-selector',lambda:None)
    assert capsys.readouterr().err==''


def test_double_cleanup_failure_retains_lease_and_allows_retry(transaction_case,monkeypatch):
    tx,_,context=transaction_case
    lease=MagicMock();box={'_cleanup_lease':MagicMock()};lease.__enter__.return_value=box
    monkeypatch.setattr(bop_migration_fence,'legacy_write_lease',lambda *args:lease)
    result=registered_handler()({'operation':'connect','bop_gid':'demo'},context)
    tx.rollback.side_effect=RuntimeError('rollback failed');tx.close.side_effect=RuntimeError('close failed')
    with pytest.raises(RuntimeError):result.transaction.close()
    assert not box.get('_rolled_back') and not box.get('_connection_closed')
    assert not result.transaction._closed
    box['_cleanup_lease'].assert_not_called();lease.__exit__.assert_not_called()
    tx.rollback.side_effect=None;tx.close.side_effect=None
    result.transaction.close()
    assert box['_rolled_back'] and result.transaction._closed
    box['_cleanup_lease'].assert_called_once()
    tx.commit.assert_not_called()


def test_journal_failure_and_double_cleanup_failure_do_not_delete_lease(transaction_case,monkeypatch):
    tx,_,context=transaction_case
    monkeypatch.setenv('AI00_BOP_REPOSITORY_MIGRATION_FENCE_ENABLED','1')
    tx.rollback.side_effect=RuntimeError('rollback failed');tx.close.side_effect=RuntimeError('close failed')
    tx.cursor.return_value.__enter__.return_value.execute.side_effect=ValueError('journal failed')
    journal=MagicMock();cursor=journal.cursor.return_value.__enter__.return_value;cursor.fetchone.return_value={'status':'report_only'}
    @contextmanager
    def journals():yield journal
    original=bop_migration_fence.legacy_write_lease
    monkeypatch.setattr(bop_migration_fence,'legacy_write_lease',lambda cap,ctx:original(cap,ctx,connection_factory=journals))
    result=registered_handler()({'operation':'connect','bop_gid':'demo'},context)
    with pytest.raises(Exception):result.transaction.commit()
    assert not any(call.args[0].startswith('DELETE FROM') for call in cursor.execute.call_args_list)
    assert not result.transaction._closed and not result.transaction._box.get('_connection_closed')
    tx.commit.assert_not_called()


@pytest.mark.parametrize('result_mode',['accepted','schema_rejected','policy_projection_rejected'])
def test_gateway_finishes_owner_lease_participant_after_acceptance_or_rejection(result_mode):
    from backend.tests.test_capability_gateway_pipeline import _descriptor,_gateway,_envelope
    from backend.capability_v2.contracts import SideEffectLevel
    from backend.capability_v2.authorization import AuthorizationDecision
    from backend.capability_v2.outcomes import InMemoryOutcomeStore
    from backend.capability_v2.reliability import ReliabilityCoordinator,InMemoryRateLimiter
    class Policy:
        def authorize(self,*args):return AuthorizationDecision(allowed=True,code='allowed',policy_version='policy-test')
        def approve(self,*args):return None
        def project(self,descriptor,identity,data):
            if result_mode=='policy_projection_rejected':raise ValueError('projection rejected')
            return data
    class Store(InMemoryOutcomeStore):
        enlisted=None
        def complete_in_transaction(self,transaction,operation_id,result):
            self.enlisted=transaction
            return self.complete(operation_id,result)
    raw=MagicMock();lease=MagicMock();box={}
    proxy=bop_migration_fence.LegacyLeaseTransaction(raw,lease,box)
    store=Store()
    descriptor=_descriptor().model_copy(update={'side_effect_level':SideEffectLevel.WRITE,'idempotency_policy':'required'})
    @transactional_provider
    def handler(*args):
        return TransactionalCapabilityOutput(data={'unexpected':'field'} if result_mode=='schema_rejected' else {'routing_id':'fixture'},transaction=proxy)
    gateway,release=_gateway(descriptor,handler,Policy(),ReliabilityCoordinator(store,InMemoryRateLimiter(limit=100)))
    result=asyncio.run(gateway.invoke(_envelope(release).model_copy(update={'idempotency_key':'fixture-once'})))
    raw.close.assert_called_once()
    if result_mode=='accepted':
        assert result.ok and store.enlisted is proxy
        raw.commit.assert_called_once();raw.rollback.assert_not_called()
        lease.__exit__.assert_called_once_with(None,None,None)
    else:
        assert not result.ok and store.enlisted is None
        raw.commit.assert_not_called();raw.rollback.assert_called_once()
        assert lease.__exit__.call_args.args[0] is RuntimeError


def test_external_lease_cleanup_failure_still_closes_rolled_back_transaction(transaction_case,monkeypatch):
    tx,_,context=transaction_case
    lease=MagicMock();cleanup=MagicMock(side_effect=RuntimeError('lease cleanup failed'))
    box={'_cleanup_lease':cleanup};lease.__enter__.return_value=box
    monkeypatch.setattr(bop_migration_fence,'legacy_write_lease',lambda *args:lease)
    result=registered_handler()({'operation':'connect','bop_gid':'demo'},context)
    with pytest.raises(RuntimeError,match='lease cleanup failed'):result.transaction.close()
    tx.rollback.assert_called_once();tx.close.assert_called_once();tx.commit.assert_not_called()
    assert box['_connection_closed'] and not result.transaction._closed
    cleanup.side_effect=None
    result.transaction.close()
    assert result.transaction._closed
    tx.close.assert_called_once();tx.rollback.assert_called_once()
