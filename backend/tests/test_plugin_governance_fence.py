from contextlib import contextmanager
from types import SimpleNamespace as NS

import pytest


def test_artifact_commit_revalidates_governance_under_shared_lock(monkeypatch):
    from backend.plugin_platform.local_providers import provider_commit_guard
    from backend.plugin_platform.provider_bindings import ProviderBindingError
    from backend.tests.test_plugin_local_providers import fixture_provider
    from backend.db import connection
    events=[]
    class Cursor:
        def __enter__(self): return self
        def __exit__(self,*_args): pass
        def execute(self,sql,args=()):
            if 'runtime_fence' in sql: events.append('fence');self.row={'fence_id':1}
            elif 'plugin_installations' in sql: self.row={'current_version':'1.2.3','mount_revocation_version':1,'state':'enabled'}
            elif 'plugin_releases' in sql: self.row={'status':'published','artifact_sha256':provider.binding.artifact_sha256,'manifest':{}}
        def fetchone(self): return self.row
    conn=NS(cursor=lambda:Cursor())
    @contextmanager
    def connections(): yield conn
    monkeypatch.setattr(connection,'get_conn',connections)
    # Simulate a rejection committed while the caller was waiting for the fence.
    from backend.plugin_platform import local_providers
    def revalidate(*_args):
        assert events==['fence']
        events.append('revalidate')
        raise ProviderBindingError('provider_approval_missing')
    monkeypatch.setattr(local_providers,'revalidate_locked_provider',revalidate,raising=False)
    provider=fixture_provider()
    session=NS(installation_id='consumer',plugin_version='1.2.3',revocation_version=1)
    with pytest.raises(ProviderBindingError,match='approval_missing'):
        with provider_commit_guard({'gid':'u','team_id':'t'},session,provider):
            events.append('effect')
    assert events==['fence','revalidate']


def test_business_review_append_waits_for_runtime_publication_fence():
    import threading
    from datetime import UTC,datetime
    from backend.capability_governance_test.store import SqlGovernanceStore
    from backend.capability_governance_test.business_models import CapabilityBusinessReview
    lock=threading.Lock();waiting=threading.Event();done=threading.Event();events=[]
    class Cursor:
        def execute(self,sql,args=()):
            if 'runtime_fence' in sql:
                waiting.set();lock.acquire();events.append('writer_fenced')
            elif 'INSERT INTO workmanship_base_capability_business_reviews' in sql:
                events.append('review_appended')
        def fetchone(self): return {'fence_id':1}
        def close(self): pass
    class Conn:
        def cursor(self): return Cursor()
        def commit(self): events.append('review_commit');lock.release()
        def rollback(self): lock.release()
    review=CapabilityBusinessReview(10,11,'sha256:'+'a'*64,'rejected','fixture rejection','12','super_admin',datetime.now(UTC),13,14)
    lock.acquire()
    def writer():
        SqlGovernanceStore(Conn()).save_business_review(review);done.set()
    worker=threading.Thread(target=writer,daemon=True);worker.start()
    assert waiting.wait(1)
    assert not done.wait(.05)
    events.append('artifact_published');lock.release()
    assert done.wait(1);worker.join()
    assert events==['artifact_published','writer_fenced','review_appended','review_commit']


def test_missing_runtime_fence_never_allows_artifact_publication():
    from backend.capability_governance_test.runtime_fence import acquire_runtime_fence
    cursor=NS(execute=lambda *_args:None,fetchone=lambda:None)
    assert acquire_runtime_fence(cursor) is False
    with pytest.raises(RuntimeError,match='fence_unavailable'):
        acquire_runtime_fence(cursor,required=True)
