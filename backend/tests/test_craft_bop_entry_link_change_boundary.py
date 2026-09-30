from pathlib import Path
import asyncio
import sqlite3
from contextlib import contextmanager

import pytest

from plugins.craft.craft_backend.capabilities.bop_entry_link_change import apply_bop_entry_link_change


ROUTER = Path("plugins/craft/craft_backend/routers/_bop/entries.py")


def test_entry_link_routes_use_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.bop.entry_link.change.apply"') == 1
    assert "def _legacy_create_entry_link" in source
    assert "def _legacy_delete_entry_link" in source


def test_entry_link_change_validates_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be one of"):
        apply_bop_entry_link_change({"operation": "replace"}, object())


def test_entry_link_change_validates_attach_fields_before_io() -> None:
    with pytest.raises(ValueError, match="entry_gid is required"):
        apply_bop_entry_link_change({"operation": "attach"}, object())


@pytest.fixture
def link_gateway(monkeypatch):
    from backend.capabilities.registry_next import CapabilityRegistry
    from backend.capability_v2.authorization import AuthorizationDecision
    from backend.capability_v2.catalog import CatalogResolver, build_release
    from backend.capability_v2.catalog_store import InMemoryCatalogStore
    from backend.capability_v2.contracts import InvocationEnvelope
    from backend.capability_v2.gateway import CapabilityGatewayService
    from backend.capability_v2.outcomes import InMemoryOutcomeStore
    from backend.capability_v2.reliability import ReliabilityCoordinator, InMemoryRateLimiter
    from backend.tests.test_capability_gateway_pipeline import _identity
    from backend.capability_v2.contracts import ConsumerType
    from plugins.craft.craft_backend.capabilities import bop_entry_link_change as module
    from plugins.craft.craft_backend.capabilities.provider import NativeContractRegistry

    raw = sqlite3.connect(":memory:", check_same_thread=False)
    raw.row_factory = sqlite3.Row
    raw.executescript("""
        CREATE TABLE workmanship_bop_bop_entries (gid TEXT, version_gid TEXT, title TEXT);
        INSERT INTO workmanship_bop_bop_entries VALUES ('entry-1','version-1','Operation');
        CREATE TABLE workmanship_bop_bop_versions (gid TEXT, status TEXT);
        INSERT INTO workmanship_bop_bop_versions VALUES ('version-1','active');
        CREATE TABLE workmanship_bop_bop_entry_links (
            gid TEXT,entry_gid TEXT,version_gid TEXT,link_type TEXT,entity_gid TEXT,
            is_primary INTEGER,created_by TEXT,is_deleted INTEGER DEFAULT 0,deleted_at TEXT,
            UNIQUE(entry_gid,link_type,entity_gid));
        CREATE TABLE link_audit (operation TEXT);
    """)
    events = []

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, params=()):
            self.cursor = raw.execute(sql.replace('%s', '?').replace(' FOR UPDATE', ''), params)
        def fetchone(self):
            row = self.cursor.fetchone()
            return dict(row) if row is not None else None

    class Connection:
        def begin(self): raw.execute('BEGIN')
        def cursor(self): return Cursor()
        def commit(self): events.append('commit'); raw.commit()
        def rollback(self): events.append('rollback'); raw.rollback()
        def close(self): events.append('close')

    def open_transaction():
        return Connection()

    @contextmanager
    def legacy_connections():
        conn = open_transaction()
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    monkeypatch.setattr(module, 'get_craft_conn', legacy_connections, raising=False)
    monkeypatch.setattr(module, '_check_line_editable', lambda *_: None)
    monkeypatch.setattr(module, 'next_gid', lambda: 'link-1')
    monkeypatch.setattr(module, '_log_entry_op', lambda cur, **kw:
                        cur.execute('INSERT INTO link_audit VALUES (%s)', (kw['op_type'],)))

    class Policy:
        def authorize(self, *_):
            return AuthorizationDecision(allowed=True, code='allowed', policy_version='link-test')
        def approve(self, *_): return None
        def project(self, _descriptor, _identity, data): return data

    def build(broken_contract=False):
        registry = CapabilityRegistry()
        module.register_bop_entry_link_change_capability(NativeContractRegistry(registry))
        descriptor = registry.get('craft.bop.entry_link.change.apply', 1).descriptor
        if broken_contract:
            monkeypatch.setattr(module, 'output_schema_for', lambda *_: {
                'type':'object', 'additionalProperties':False, 'properties':{'data':{
                    'type':'object', 'properties':{}, 'additionalProperties':False}}, 'required':['data']})
        release = build_release([descriptor])
        store = InMemoryCatalogStore()
        store.publish(release)
        gateway = CapabilityGatewayService(CatalogResolver(store, registry), Policy(), reliability=
            ReliabilityCoordinator(InMemoryOutcomeStore(), InMemoryRateLimiter(limit=100))).bind_release(release.release_id)

        def invoke(payload, key):
            return asyncio.run(gateway.invoke(InvocationEnvelope(
                capability_id=descriptor.id, major_version=1, catalog_release=release.release_id,
                payload=payload, identity=_identity(ConsumerType.WEB), request_id=key,
                trace_id=key, idempotency_key=key)))
        return invoke

    yield build, raw, events
    raw.close()


ATTACH = {'operation':'attach', 'entry_gid':'entry-1', 'link_type':'pbom_part',
          'entity_gid':'part-1', 'is_primary':True}


def test_entry_link_gateway_attach_detach_and_retry(link_gateway):
    build, db, events = link_gateway
    invoke = build()
    attached = invoke(ATTACH, 'attach-1')
    assert attached.ok, attached.error
    assert attached.data == {'data': {'gid': 'link-1'}}
    assert invoke(ATTACH, 'attach-1').ok
    # A fresh click after the old false failure must reuse the existing relation.
    assert invoke(ATTACH, 'attach-2').ok
    assert db.execute('SELECT COUNT(*) FROM workmanship_bop_bop_entry_links').fetchone()[0] == 1
    assert db.execute('SELECT COUNT(*) FROM link_audit').fetchone()[0] == 1
    deleted = invoke({'operation':'detach', 'link_gid':'link-1'}, 'detach-1')
    assert deleted.ok, deleted.error
    assert deleted.data == {'data': {'gid':'link-1', 'deleted':True}}
    assert db.execute('SELECT COUNT(*) FROM workmanship_bop_bop_entry_links').fetchone()[0] == 0


@pytest.mark.parametrize('operation', ['attach', 'detach'])
def test_entry_link_output_rejection_rolls_back_relation_and_audit(link_gateway, operation):
    build, db, events = link_gateway
    if operation == 'detach':
        db.execute("INSERT INTO workmanship_bop_bop_entry_links (gid,entry_gid,version_gid,link_type,entity_gid,is_primary,created_by) VALUES ('link-1','entry-1','version-1','pbom_part','part-1',1,'user_1')")
        db.commit()
    result = build(broken_contract=True)(ATTACH if operation == 'attach' else
        {'operation':'detach','link_gid':'link-1'}, 'rejected-1')
    assert not result.ok
    assert result.error.code == 'provider_failed'
    assert db.execute('SELECT COUNT(*) FROM workmanship_bop_bop_entry_links').fetchone()[0] == (operation == 'detach')
    assert db.execute('SELECT COUNT(*) FROM link_audit').fetchone()[0] == 0
    assert events == ['rollback', 'close']


@pytest.mark.parametrize('state', ['frozen', 'deleted_link', 'different_primary'])
def test_entry_link_rejects_invalid_state_without_extra_writes(link_gateway, state):
    build, db, events = link_gateway
    invoke = build()
    assert invoke(ATTACH, 'initial-link').ok
    if state == 'frozen':
        db.execute("UPDATE workmanship_bop_bop_versions SET status='frozen'")
    elif state == 'deleted_link':
        db.execute("UPDATE workmanship_bop_bop_entry_links SET is_deleted=1")
    else:
        db.execute("UPDATE workmanship_bop_bop_entry_links SET is_primary=0")
    db.commit()
    events.clear()
    result = invoke(ATTACH, 'invalid-state')
    assert not result.ok
    assert result.error.code == 'invalid_state'
    assert db.execute('SELECT COUNT(*) FROM link_audit').fetchone()[0] == 1
    assert events == ['rollback', 'close']
