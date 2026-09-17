"""Repository behavior on real SQL, with optional MySQL transaction coverage.

SQLite translates dialect only and serializes writers; the optional MySQL run
uses native row locks and executes the migration through the production adapter.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from urllib.parse import unquote, urlparse
import uuid

import pytest

from backend.contracts.connector_execution_plan_v2 import (
    ConnectorExecutionPlanV2, ConnectorPlanOutcomeV2, compute_plan_hash, canonicalize_v2,
)
from plugins.simulation.simulation_backend.data import connector_repository
from plugins.simulation.simulation_backend.data.connector_repository import (
    ConnectorRepositoryError, SimulationConnectorRepository,
)

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "backend/db/migrations/domains/simulation/0008_connector_app_runtime_v2.sql"
V2 = "ai00.connector.execution-plan.v2"
NOW = datetime(2026, 9, 7, 12, tzinfo=UTC)


class SQLiteCursor:
    def __init__(self, connection):
        self.cursor = connection.cursor()

    def execute(self, query, params=()):
        query = query.replace('DATE_ADD(NOW(6),INTERVAL %s SECOND)', "datetime('2026-09-07 12:00:00', '+' || %s || ' seconds')")
        query = query.replace('DATE_ADD(NOW(6),INTERVAL 5 SECOND)', "datetime('2026-09-07 12:00:00', '+5 seconds')")
        query = query.replace('NOW(6)', "'2026-09-07 12:00:00'")
        query = query.replace('IF(%s,', 'IIF(%s,')
        query = query.replace("%s", "?").replace(" FOR UPDATE", "").replace("<=>", "IS")
        params = tuple(p.astimezone(UTC).replace(tzinfo=None).isoformat(" ") if isinstance(p, datetime) else p for p in params)
        self.cursor.execute(query, params)

    @property
    def rowcount(self):
        return self.cursor.rowcount

    def fetchone(self):
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def fetchall(self):
        return [dict(row) for row in self.cursor.fetchall()]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.cursor.close()


class SQLiteConnection:
    def __init__(self, connection):
        self.connection = connection

    def cursor(self):
        return SQLiteCursor(self.connection)


@pytest.fixture(params=["sqlite", "mysql"])
def database(request, tmp_path, monkeypatch):
    dialect = request.param
    url = os.getenv("AI00_SIMULATION_TEST_DB_URL", "")
    if dialect == "mysql" and not url:
        pytest.skip("AI00_SIMULATION_TEST_DB_URL is required for native MySQL row-lock tests")
    if not MIGRATION.exists():
        pytest.fail("missing additive runtime v2 migration")
    db_path = tmp_path / "runtime.db"
    if dialect == "mysql":
        import pymysql
        from pymysql.cursors import DictCursor
        parsed = urlparse(url)

        def connect():
            return pymysql.connect(host=parsed.hostname, port=parsed.port or 3306,
                user=unquote(parsed.username or ""), password=unquote(parsed.password or ""),
                database=parsed.path.lstrip("/"), cursorclass=DictCursor, autocommit=False)
    else:
        def connect():
            conn = sqlite3.connect(db_path, timeout=15)
            conn.row_factory = sqlite3.Row
            return conn

    @contextmanager
    def transaction():
        conn = connect()
        try:
            if dialect == "sqlite":
                conn.execute("BEGIN IMMEDIATE")
            yield SQLiteConnection(conn) if dialect == "sqlite" else conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    ddl = '\n'.join((MIGRATION.parent / name).read_text(encoding='utf-8') for name in
        ('0008_connector_app_runtime_v2.sql', '0009_connector_app_auth.sql', '0010_connector_v2_projection.sql'))
    recovery_ddl = (MIGRATION.parent / '0027_connector_manual_recovery_status.sql').read_text(encoding='utf-8')
    if dialect == 'sqlite':
        # SQLite cannot ALTER CHECK; build the equivalent final schema in this empty fixture.
        new_check = re.search(r'CHECK \(status IN \([^;]+\)\)', recovery_ddl).group(0)
        ddl = ddl.replace("CHECK (`status` IN ('queued','leased','executing','succeeded','failed_without_effect','outcome_unknown','manual_review_required','expired'))", new_check)
    with transaction() as conn:
        if dialect == "mysql":
            from backend.db.versioned_migrations import prepare_resumable_statement
            for migration in ("0005_connector_control_plane.sql", "0007_connector_pairing_activation.sql"):
                for part in (MIGRATION.parent / migration).read_text().split(";"):
                    if part.strip():
                        statement = prepare_resumable_statement(conn, part.strip())
                        if statement:
                            with conn.cursor() as cur:
                                cur.execute(statement)
        else:
            with conn.cursor() as cur:
                for table, columns in {
                    "bindings": "connector_id TEXT PRIMARY KEY",
                    "plans": "plan_id TEXT PRIMARY KEY, connector_id TEXT, status TEXT, tenant_gid TEXT, user_gid TEXT, plan_hash TEXT, plan_json TEXT, expires_at DATETIME(6)",
                    "pairings": "pairing_id TEXT PRIMARY KEY",
                    "pairing_bootstraps": "bootstrap_id TEXT PRIMARY KEY",
                }.items():
                    cur.execute(f"CREATE TABLE workmanship_sim_connector_{table} ({columns})")
        for part in ddl.split(";"):
            statement = re.sub(r"--[^\n]*", "", part).strip()
            if not statement:
                continue
            if dialect == "sqlite":
                statement = re.sub(r"\) ENGINE=.*", ")", statement, flags=re.S)
                statement = re.sub(r"\b(?:CHARACTER SET ascii )?COLLATE (?:ascii_bin|utf8mb4_bin)", "COLLATE BINARY", statement)
                statement = re.sub(r"UNIQUE KEY `[^`]+`", "UNIQUE", statement)
                statement = re.sub(r"\bKEY `[^`]+`[^\n]*\n", "", statement)
                statement = re.sub(r",\s*\)", "\n)", statement)
                statement = statement.replace("CURRENT_TIMESTAMP(6)", "CURRENT_TIMESTAMP")
                statement = statement.replace(" ON UPDATE CURRENT_TIMESTAMP", "")
                statement = statement.replace("ADD COLUMN IF NOT EXISTS", "ADD COLUMN")
            else:
                from backend.db.versioned_migrations import prepare_resumable_statement
                statement = prepare_resumable_statement(conn, statement)
            if statement:
                with conn.cursor() as cur:
                    cur.execute(statement)
        if dialect == 'mysql':
            from backend.db.versioned_migrations import prepare_resumable_statement, split_sql
            for phase in split_sql(recovery_ddl):
                statement = prepare_resumable_statement(conn, phase)
                if statement:
                    with conn.cursor() as cur:
                        cur.execute(statement)
    monkeypatch.setattr(connector_repository, "get_simulation_conn", transaction)
    device = "test-runtime-" + uuid.uuid4().hex
    with transaction() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO workmanship_sim_connector_runtime_devices "
                    "(device_id,protocol,owner_user_gid,tenant_gid,credential_generation,runtime_generation,device_signing_jwk,device_key_id,status) "
                    "VALUES (%s,%s,'user-001','tenant-001',1,7,%s,'device-key-001','active')",
                    (device, V2, json.dumps(json.loads((ROOT / 'backend/tests/fixtures/connector_execution_plan_v2.json').read_text())['device_public_jwk'])))
    yield transaction, device
    if dialect == "mysql":
        with transaction() as conn, conn.cursor() as cur:
            cur.execute('DELETE FROM workmanship_sim_connector_runtime_projection_outbox WHERE plan_id IN '
                '(SELECT plan_id FROM workmanship_sim_connector_runtime_plans WHERE device_id=%s)', (device,))
            for table in ("app_pairings", "runtime_challenges", "runtime_recovery_sessions", "runtime_audit", "runtime_plans", "runtime_devices"):
                cur.execute(f"DELETE FROM workmanship_sim_connector_{table} WHERE device_id=%s", (device,))
            cur.execute("DELETE FROM workmanship_sim_connector_plans WHERE connector_id=%s", (device,))


def read(database, table="runtime_devices"):
    transaction, device = database
    with transaction() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT * FROM workmanship_sim_connector_{table} WHERE device_id=%s", (device,))
        return cur.fetchone()


def session(database, *, now=NOW, instance="runtime-instance-001"):
    return SimulationConnectorRepository().register_runtime_session(database[1], 7, instance, now, now + timedelta(seconds=60))


def queue(database, registered, *, now=NOW, idempotency_key=None, normalized_input_hash=None,
          side_effect_classification=None, operation_id=None, payload=None, expires_at="2026-09-07T12:10:00Z"):
    source = json.loads((ROOT / "backend/tests/fixtures/connector_execution_plan_v2.json").read_text())["plan"]
    source.update(device_id=database[1], plan_id="plan-" + uuid.uuid4().hex,
                  runtime_generation=registered.runtime_generation,
                  runtime_instance_id=registered.runtime_instance_id,
                  issued_at="2026-09-07T12:00:00Z", expires_at=expires_at)
    if idempotency_key is not None:
        source["idempotency_key"] = idempotency_key
        source['normalized_input_hash'] = 'sha256:' + hashlib.sha256(idempotency_key.encode()).hexdigest()
    if normalized_input_hash is not None:
        source['normalized_input_hash'] = normalized_input_hash
    if side_effect_classification is not None:
        source['steps'][0]['side_effect_classification'] = side_effect_classification
    if operation_id is not None:
        source['steps'][0]['operation_id'] = operation_id
    if payload is not None:
        source['steps'][0]['payload'] = payload
        source['steps'][0]['payload_hash'] = 'sha256:' + hashlib.sha256(canonicalize_v2(payload)).hexdigest()
    source['steps'][0]['post_condition_probe_id'] = 'vismockup.application.postcondition@1'
    source["plan_hash"] = compute_plan_hash(source)
    plan = ConnectorExecutionPlanV2.model_validate(source)
    SimulationConnectorRepository().insert_v2_plan(plan, registered.session_token, now)
    return plan


def lease(database, registered, now=NOW):
    return SimulationConnectorRepository().lease_v2_plan(database[1], registered.runtime_generation,
        registered.runtime_instance_id, registered.session_token, now, lease_seconds=15)


def test_interactive_plan_leases_before_earlier_structure_export(database):
    registered = session(database)
    export = queue(database, registered, idempotency_key="export", operation_id="vismockup.document.snapshot@1")
    control = queue(database, registered, now=NOW + timedelta(seconds=1),
                    idempotency_key="control", operation_id="vismockup.node.visibility.change@1")

    selected = lease(database, registered, NOW + timedelta(seconds=2))

    assert selected["plan"]["plan_id"] == control.plan_id
    transaction, _ = database
    with transaction() as conn, conn.cursor() as cur:
        cur.execute("SELECT status FROM workmanship_sim_connector_runtime_plans WHERE plan_id=%s", (export.plan_id,))
        assert cur.fetchone()["status"] == "queued"


def outcome_for(plan, leased, status="succeeded"):
    source = json.loads((ROOT / "backend/tests/fixtures/connector_execution_plan_v2.json").read_text())["outcome"]
    source.update(device_id=plan.device_id, plan_id=plan.plan_id, plan_hash=plan.plan_hash,
        lease_id=leased["lease_id"], overall_status=status, runtime_instance_id=plan.runtime_instance_id, device_key_id='device-key-001')
    source['steps'][0].update(status=status, error_code=None if status=='succeeded' else 'execution_uncertain')
    source['signature'] = sign_outcome(source)
    return ConnectorPlanOutcomeV2.model_validate(source)


def test_identity_outcome_persists_without_materialization_projection_and_verifies(database):
    from plugins.simulation.tests.test_live_document_identity_evidence import evidence
    from backend.contracts.connector_execution_plan_v2 import canonicalize_v2
    row, _ = evidence()
    registered = session(database)
    raw = row['plan_json']
    raw.update(device_id=database[1], runtime_generation=registered.runtime_generation,
        runtime_instance_id=registered.runtime_instance_id, issued_at='2026-09-07T12:00:00Z',
        expires_at='2026-09-07T12:10:00Z')
    raw['plan_hash'] = compute_plan_hash(raw)
    plan = ConnectorExecutionPlanV2.model_validate(raw)
    repo = SimulationConnectorRepository()
    repo.heartbeat_runtime(database[1], registered.runtime_generation, registered.runtime_instance_id,
        registered.session_token, NOW)
    repo.insert_v2_plan(plan, registered.session_token, NOW)
    leased = lease(database, registered)
    outcome = row['outcome_json']
    outcome.update(device_id=database[1],plan_hash=plan.plan_hash,lease_id=leased['lease_id'],reported_at='2026-09-07T12:00:02Z',device_key_id='device-key-001')
    outcome['steps'][0].update(started_at='2026-09-07T12:00:00Z',completed_at='2026-09-07T12:00:01Z')
    outcome['signature'] = sign_outcome(outcome)
    repo.complete_v2_plan(database[1], registered.runtime_generation, registered.runtime_instance_id,
        registered.session_token, outcome, NOW + timedelta(seconds=3))
    with database[0]() as conn, conn.cursor() as cur:
        cur.execute('SELECT * FROM workmanship_sim_connector_runtime_projection_outbox WHERE plan_id=%s',(plan.plan_id,))
        assert cur.fetchone() is None
    identity = repo.verified_document_identity(plan.plan_id,actor_id='user-001',tenant_id='tenant-001',now=NOW+timedelta(seconds=4))
    assert identity == dict(connector_device_id=database[1],document_session=outcome['steps'][0]['result']['document_session'])
    with pytest.raises(ConnectorRepositoryError,match='identity_unavailable'):
        repo.verified_document_identity(plan.plan_id,actor_id='other',tenant_id='tenant-001',now=NOW+timedelta(seconds=4))


def sign_outcome(source):
    import base64
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    from backend.contracts.connector_execution_plan_v2 import P256_ORDER, outcome_signature_bytes
    vector = json.loads((ROOT / 'backend/tests/fixtures/connector_execution_plan_v2.json').read_text())
    private = vector['test_only_private_keys']['device_private_jwk']['d']
    key = ec.derive_private_key(int.from_bytes(base64.urlsafe_b64decode(private+'='), 'big'), ec.SECP256R1())
    r, s = decode_dss_signature(key.sign(outcome_signature_bytes(source), ec.ECDSA(hashes.SHA256())))
    return base64.urlsafe_b64encode(r.to_bytes(32, 'big')+min(s, P256_ORDER-s).to_bytes(32, 'big')).rstrip(b'=').decode()


def reconciled_outcome(database, plan, *, instance, token, now=NOW):
    from plugins.simulation.simulation_backend.application.connector_protocol_v2 import ConnectorReconciliationEvidenceV2
    context = SimulationConnectorRepository().reconciliation_plan(
        database[1], 7, instance, token, plan.plan_id, now, 'electron')
    value = {k:v for k,v in context.items() if k not in {'required_probes', 'coverage', 'next_journal_sequence'}}
    value.update(protocol='ai00.connector.reconciliation-evidence.v2',
        probes=[dict(**p, classification='succeeded', observed_result=None) for p in context['required_probes']],
        journal_sequence=context['next_journal_sequence'], reported_at='2026-09-07T12:00:00Z',
        device_key_id='device-key-001', signature_algorithm='ecdsa-p256-sha256')
    value['signature'] = sign_outcome(value)
    return ConnectorReconciliationEvidenceV2.model_validate(value)


def complete(database, registered, outcome, *, reconciled=False, now=NOW):
    method = SimulationConnectorRepository().mark_reconciled if reconciled else SimulationConnectorRepository().complete_v2_plan
    return method(database[1], registered.runtime_generation, registered.runtime_instance_id,
                  registered.session_token, outcome, now)


def recovery_case(database, operation_id='teamcenter.visualization.launch@1', *, payload=None, side_effect_classification=None):
    registered = session(database)
    plan = queue(database, registered, operation_id=operation_id, payload=payload,
                 side_effect_classification=side_effect_classification)
    complete(database, registered, outcome_for(plan, lease(database, registered), 'outcome_unknown'))
    row = read(database, 'runtime_plans')
    return dict(device_id=database[1], plan_id=plan.plan_id, expected_generation=7,
        expected_outcome_hash='sha256:' + row['outcome_hash'], decision='not_executed',
        reason='Verified the document was not opened', actor_id='user-001', tenant_id='tenant-001', now=NOW)


def test_manual_recovery_preserves_signed_outcome_and_replays(database):
    args = recovery_case(database)
    repo = SimulationConnectorRepository()
    before = read(database, 'runtime_plans')
    items = repo.search_manual_recovery(actor_id='user-001', tenant_id='tenant-001')['items']
    assert len(items) == 1 and items[0]['eligible'] is True
    assert items[0]['outcome_hash'] == args['expected_outcome_hash']
    result = repo.resolve_manual_recovery(**args)
    assert result['retry_started'] is False and result['audit_ref']
    assert repo.resolve_manual_recovery(**args) == result
    after = read(database, 'runtime_plans')
    assert after['status'] == 'cancelled'
    assert after['outcome_json'] == before['outcome_json']
    assert after['outcome_hash'] == before['outcome_hash']
    assert repo.search_manual_recovery(actor_id='user-001', tenant_id='tenant-001')['items'] == []
    # The authenticated transport maps this closed-plan response to the existing
    # obsolete-journal acknowledgement; it must not issue a new recovery lease.
    with pytest.raises(ConnectorRepositoryError, match='plan_reconciliation_invalid'):
        repo.register_reconciliation_session(args['device_id'], 7, 'recovery-after-review', args['plan_id'],
            'a' * 64, NOW + timedelta(seconds=180), now=NOW + timedelta(seconds=90))
    assert read(database, 'runtime_recovery_sessions') is None
    with pytest.raises(ConnectorRepositoryError, match='recovery_decision_conflict'):
        repo.resolve_manual_recovery(**dict(args, decision='executed'))


@pytest.mark.parametrize('change,error', [
    ({'actor_id':'other'}, 'runtime_owner_mismatch'),
    ({'tenant_id':'other'}, 'runtime_owner_mismatch'),
    ({'expected_generation':8}, 'recovery_state_changed'),
    ({'expected_outcome_hash':'sha256:'+'0'*64}, 'recovery_state_changed'),
    ({'reason':' '}, 'recovery_input_invalid'),
])
@pytest.mark.parametrize('decision', ['not_executed', 'abandoned'])
def test_manual_recovery_refuses_wrong_owner_or_stale_state(database, change, error, decision):
    args = dict(recovery_case(database), decision=decision)
    repo = SimulationConnectorRepository()
    assert repo.search_manual_recovery(actor_id='other', tenant_id='tenant-001')['items'] == []
    assert repo.search_manual_recovery(actor_id='user-001', tenant_id='other')['items'] == []
    before = read(database, 'runtime_plans')
    with pytest.raises(ConnectorRepositoryError, match=error):
        repo.resolve_manual_recovery(**dict(args, **change))
    assert read(database, 'runtime_plans') == before


def test_manual_recovery_lists_but_refuses_unsupported_operation(database):
    args = recovery_case(database, 'vismockup.model.close@1')
    repo = SimulationConnectorRepository()
    item = repo.search_manual_recovery(actor_id='user-001', tenant_id='tenant-001')['items'][0]
    assert item['eligible'] is True and item['allowed_decisions'] == ['abandoned']
    with pytest.raises(ConnectorRepositoryError, match='recovery_operation_unsupported'):
        repo.resolve_manual_recovery(**args)


@pytest.mark.parametrize('operation,payload', [
    ('vismockup.application.probe@1', {'allow_launch': True}),
    *[('vismockup.visibility.change@1', {'action': action}) for action in ('all_on', 'all_off')],
    *[('vismockup.node.visibility.change@1', {'action': action}) for action in ('show', 'hide', 'isolate')],
    *[('vismockup.node.selection.change@1', {'action': action}) for action in ('highlight', 'select', 'unhighlight', 'deselect')],
    *[(operation, {}) for operation in ('teamcenter.visualization.launch@1',
        'teamcenter.visualization.insert@1', 'vismockup.model.open@1', 'vismockup.model.insert@1')],
])
def test_manual_recovery_bounded_actions_release_unresolved_blocker(database, operation, payload):
    args = recovery_case(database, operation, payload=payload,
                         side_effect_classification='read' if operation == 'vismockup.application.probe@1' else 'write')
    repo = SimulationConnectorRepository()
    with database[0]() as conn, conn.cursor() as cur:
        assert repo._has_unresolved_plans(cur, database[1])
    before = read(database, 'runtime_plans')
    item = repo.search_manual_recovery(actor_id='user-001', tenant_id='tenant-001')['items'][0]
    assert item['eligible'] is True
    assert item['ineligible_reason'] is None
    assert item['allowed_decisions'] == ['executed', 'not_executed', 'abandoned']
    from plugins.simulation.simulation_backend.capabilities.connector_contracts import RECOVERY_ITEM
    import jsonschema
    jsonschema.validate(item, RECOVERY_ITEM)
    result = repo.resolve_manual_recovery(**args)
    assert repo.resolve_manual_recovery(**args) == result
    with pytest.raises(ConnectorRepositoryError, match='recovery_decision_conflict'):
        repo.resolve_manual_recovery(**dict(args, decision='executed'))
    after = read(database, 'runtime_plans')
    assert after['status'] == 'cancelled'
    assert (after['outcome_json'], after['outcome_hash']) == (before['outcome_json'], before['outcome_hash'])
    with database[0]() as conn, conn.cursor() as cur:
        assert not repo._has_unresolved_plans(cur, database[1])
        cur.execute("SELECT audit_id FROM workmanship_sim_connector_runtime_audit WHERE plan_id=%s "
                    "AND event_type='human_recovery_disposition'", (args['plan_id'],))
        assert [row['audit_id'] for row in cur.fetchall()] == [result['audit_ref']]


@pytest.mark.parametrize('operation,payload,mutation,reason', [
    ('vismockup.application.probe@1', {'allow_launch': False}, None, 'unsupported_action'),
    ('vismockup.application.probe@1', {'allow_launch': 1}, None, 'unsupported_action'),
    ('vismockup.application.probe@1', {}, None, 'unsupported_action'),
    ('vismockup.visibility.change@1', {'action': 'toggle'}, None, 'unsupported_action'),
    ('vismockup.node.visibility.change@1', {'action': 'all_on'}, None, 'unsupported_action'),
    ('vismockup.node.selection.change@1', {'action': 'toggle'}, None, 'unsupported_action'),
    ('vismockup.node.selection.change@1', {'action': []}, None, 'unsupported_action'),
    ('unknown.operation@1', {'action': 'show'}, None, 'unsupported_operation'),
    ('vismockup.node.visibility.change@2', {'action': 'show'}, None, 'unsupported_operation'),
    ('vismockup.node.visibility.change@1', {'action': 'show'}, 'multiple', 'multiple_operations'),
    ('vismockup.node.visibility.change@1', {'action': 'show'}, 'missing_hash', 'missing_outcome_hash'),
])
def test_manual_recovery_ineligible_reasons_refuse_without_mutation(database, operation, payload, mutation, reason):
    args = recovery_case(database)
    plan = json.loads(read(database, 'runtime_plans')['plan_json'])
    plan['steps'][0].update(operation_id=operation, payload=payload)
    if mutation == 'multiple':
        plan['steps'].append(dict(plan['steps'][0]))
    with database[0]() as conn, conn.cursor() as cur:
        cur.execute('UPDATE workmanship_sim_connector_runtime_plans SET plan_json=%s WHERE plan_id=%s',
                    (json.dumps(plan), args['plan_id']))
        if mutation == 'missing_hash':
            cur.execute('UPDATE workmanship_sim_connector_runtime_plans SET outcome_hash=NULL WHERE plan_id=%s', (args['plan_id'],))
    before = read(database, 'runtime_plans')
    repo = SimulationConnectorRepository()
    item = repo.search_manual_recovery(actor_id='user-001', tenant_id='tenant-001')['items'][0]
    assert item['eligible'] is True
    assert item['ineligible_reason'] is None
    assert item['allowed_decisions'] == ['abandoned']
    from plugins.simulation.simulation_backend.capabilities.connector_contracts import RECOVERY_ITEM
    import jsonschema
    jsonschema.validate(item, RECOVERY_ITEM)
    error = 'recovery_state_changed' if mutation == 'missing_hash' else 'recovery_operation_unsupported'
    for decision in ('executed', 'not_executed'):
        with pytest.raises(ConnectorRepositoryError, match=error):
            repo.resolve_manual_recovery(**dict(args, decision=decision))
    assert read(database, 'runtime_plans') == before
    with database[0]() as conn, conn.cursor() as cur:
        assert repo._has_unresolved_plans(cur, database[1])
        cur.execute("SELECT audit_id FROM workmanship_sim_connector_runtime_audit WHERE plan_id=%s "
                    "AND event_type='human_recovery_disposition'", (args['plan_id'],))
        assert cur.fetchall() == []


def test_manual_recovery_capability_is_confirmed_web_only_with_closed_contracts(database):
    from backend.capabilities.models_next import CapabilityContext, CapabilityBusinessError
    from backend.capabilities.registry_next import CapabilityRegistry
    from plugins.simulation.simulation_backend.capabilities.connector_runtime import (
        ConnectorControlPlane, register_connector_runtime_capabilities,
    )
    import jsonschema
    args = recovery_case(database)
    registry = CapabilityRegistry()
    register_connector_runtime_capabilities(registry, ConnectorControlPlane(SimulationConnectorRepository(), clock=lambda: NOW))
    search = registry.get('simulation.connector.recovery.search', 1)
    resolve = registry.get('simulation.connector.recovery.resolve', 1)
    for registration in (search, resolve):
        descriptor = registration.descriptor
        assert descriptor.exposure.web and not any(value for key, value in descriptor.exposure.model_dump().items() if key != 'web')
        assert descriptor.business_invariants
        assert registration.spec.permissions == ('simulation.use',)
        assert registration.spec.input_schema['additionalProperties'] is False
    assert resolve.spec.confirmation == 'user'
    assert resolve.descriptor.replay_data_policy == 'projected'
    payload = {key: value for key, value in args.items() if key not in {'actor_id','tenant_id','now'}}
    context = CapabilityContext(user_gid='user-001', team_gid='tenant-001', source='web')
    output = search.handler({}, context).data
    jsonschema.validate(output, search.spec.output_schema)
    for source in ('agent', 'api', 'plugin', 'mcp', 'local_runtime'):
        with pytest.raises(CapabilityBusinessError, match='authenticated device owner'):
            resolve.handler(payload, context.model_copy(update={'source':source, 'confirmation_token':'receipt'}))
    with pytest.raises(CapabilityBusinessError, match='Confirm the exact'):
        resolve.handler(payload, context)
    jsonschema.validate(payload, resolve.spec.input_schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(dict(payload, unexpected=True), resolve.spec.input_schema)
    # Successful writes are exercised through the Gateway transaction boundary
    # in test_connector_recovery_gateway_transaction.py, including output validation.


@pytest.mark.parametrize('kind', ['unknown', 'unsupported_action', 'multiple', 'known', 'missing_hash'])
def test_manual_recovery_abandoned_archives_exact_plan_without_claiming_execution(database, kind):
    args = dict(recovery_case(database), decision='abandoned', reason='Abandon and archive this unfinished operation')
    plan = json.loads(read(database, 'runtime_plans')['plan_json'])
    if kind == 'unknown':
        plan['steps'][0]['operation_id'] = 'unknown.operation@1'
    elif kind == 'unsupported_action':
        plan['steps'][0].update(operation_id='vismockup.node.visibility.change@1', payload={'action': 'toggle'})
    elif kind == 'multiple':
        plan['steps'].append(dict(plan['steps'][0]))
    with database[0]() as conn, conn.cursor() as cur:
        cur.execute('UPDATE workmanship_sim_connector_runtime_plans SET plan_json=%s WHERE plan_id=%s',
                    (json.dumps(plan), args['plan_id']))
        if kind == 'missing_hash':
            cur.execute('UPDATE workmanship_sim_connector_runtime_plans SET outcome_hash=NULL WHERE plan_id=%s', (args['plan_id'],))
    before = read(database, 'runtime_plans')
    repo = SimulationConnectorRepository()
    if kind == 'missing_hash':
        with pytest.raises(ConnectorRepositoryError, match='recovery_state_changed'):
            repo.resolve_manual_recovery(**args)
        assert read(database, 'runtime_plans') == before
        with database[0]() as conn, conn.cursor() as cur:
            assert repo._has_unresolved_plans(cur, database[1])
        return
    result = repo.resolve_manual_recovery(**args)
    assert result['decision'] == 'abandoned' and result['retry_started'] is False
    assert repo.resolve_manual_recovery(**args) == result
    for decision in ('executed', 'not_executed'):
        with pytest.raises(ConnectorRepositoryError, match='recovery_decision_conflict'):
            repo.resolve_manual_recovery(**dict(args, decision=decision))
    with pytest.raises(ConnectorRepositoryError, match='recovery_decision_conflict'):
        repo.resolve_manual_recovery(**dict(args, reason='Different reason'))
    after = read(database, 'runtime_plans')
    assert after['status'] == 'cancelled' and after['reconciliation_state'] == 'not_required'
    assert (after['outcome_json'], after['outcome_hash']) == (before['outcome_json'], before['outcome_hash'])
    with database[0]() as conn, conn.cursor() as cur:
        assert not repo._has_unresolved_plans(cur, database[1])
        cur.execute("SELECT audit_id,outcome_json FROM workmanship_sim_connector_runtime_audit WHERE plan_id=%s "
                    "AND event_type='human_recovery_disposition'", (args['plan_id'],))
        audits = cur.fetchall()
        assert len(audits) == 1 and audits[0]['audit_id'] == result['audit_ref']
        assert json.loads(audits[0]['outcome_json'])['decision'] == 'abandoned'
        cur.execute('SELECT plan_id FROM workmanship_sim_connector_runtime_plans WHERE device_id=%s', (database[1],))
        assert [row['plan_id'] for row in cur.fetchall()] == [args['plan_id']]
    from plugins.simulation.simulation_backend.capabilities.connector_contracts import INPUT_SCHEMAS, OUTPUT_SCHEMAS
    import jsonschema
    jsonschema.validate({key: value for key, value in args.items() if key not in {'actor_id', 'tenant_id', 'now'}},
                        INPUT_SCHEMAS['simulation.connector.recovery.resolve'])
    jsonschema.validate(result, OUTPUT_SCHEMAS['simulation.connector.recovery.resolve'])


def test_manual_recovery_bounds_results_and_hides_other_plan_owner(database):
    args = recovery_case(database)
    transaction, device = database
    with transaction() as conn, conn.cursor() as cur:
        for index in range(23):
            cur.execute("INSERT INTO workmanship_sim_connector_runtime_plans "
                "(plan_id,protocol,device_id,runtime_generation,runtime_instance_id,session_token_hash,tenant_gid,actor_gid,"
                "idempotency_key,plan_hash,plan_json,status,expires_at) "
                "SELECT %s,protocol,device_id,runtime_generation,runtime_instance_id,session_token_hash,tenant_gid,actor_gid,"
                "%s,plan_hash,plan_json,status,expires_at FROM workmanship_sim_connector_runtime_plans WHERE plan_id=%s",
                ('copy-' + str(index), 'copy-' + str(index), args['plan_id']))
        cur.execute("UPDATE workmanship_sim_connector_runtime_plans SET actor_gid='other' WHERE plan_id=%s", (args['plan_id'],))
    repo = SimulationConnectorRepository()
    items = repo.search_manual_recovery(actor_id='user-001', tenant_id='tenant-001', page_size=20)['items']
    assert len(items) == 20
    assert all(item['plan_id'] != args['plan_id'] for item in items)
    assert all(item['outcome_hash'] is None and item['eligible'] and item['allowed_decisions'] == ['abandoned'] for item in items)
    with pytest.raises(ConnectorRepositoryError, match='runtime_owner_mismatch'):
        repo.resolve_manual_recovery(**args)


@pytest.mark.parametrize('change,error', [
    ({}, None), ({'expected_plan_hash': None}, 'recovery_state_changed'),
    ({'expected_plan_hash': 'sha256:' + '0'*64}, 'recovery_state_changed'),
    ({'expected_generation': 8}, 'recovery_state_changed'),
    ({'actor_id': 'other'}, 'runtime_owner_mismatch'),
    ({'tenant_id': 'other'}, 'runtime_owner_mismatch'),
    ({'decision': 'executed'}, 'recovery_operation_unsupported'),
    ({'decision': 'not_executed'}, 'recovery_operation_unsupported'),
    ({'stale_plan': True}, 'recovery_state_changed'),
    ({'missing_plan': True}, 'recovery_state_changed'),
])
def test_manual_recovery_missing_outcome_requires_exact_plan_identity(database, change, error):
    args = recovery_case(database, 'vismockup.application.probe@1', payload={'allow_launch': True})
    row = read(database, 'runtime_plans')
    args.pop('expected_outcome_hash')
    args.update(decision='abandoned', expected_plan_hash='sha256:' + row['plan_hash'])
    change = dict(change)
    stale = change.pop('stale_plan', False)
    missing = change.pop('missing_plan', False)
    with database[0]() as conn, conn.cursor() as cur:
        cur.execute('UPDATE workmanship_sim_connector_runtime_plans SET outcome_hash=NULL WHERE plan_id=%s', (args['plan_id'],))
        if stale or missing:
            cur.execute('UPDATE workmanship_sim_connector_runtime_plans SET plan_hash=%s WHERE plan_id=%s',
                        ('' if missing else 'f'*64, args['plan_id']))
    before = read(database, 'runtime_plans')
    repo = SimulationConnectorRepository()
    item = repo.search_manual_recovery(actor_id='user-001', tenant_id='tenant-001')['items'][0]
    assert item['plan_hash'] == (None if missing else 'sha256:' + before['plan_hash'])
    assert item['allowed_decisions'] == ['abandoned']
    assert item['eligible'] is True
    assert item['ineligible_reason'] is None
    args.update(change)
    if error:
        with pytest.raises(ConnectorRepositoryError, match=error):
            repo.resolve_manual_recovery(**args)
        assert read(database, 'runtime_plans') == before
        return
    result = repo.resolve_manual_recovery(**args)
    assert repo.resolve_manual_recovery(**args) == result
    with pytest.raises(ConnectorRepositoryError, match='recovery_decision_conflict'):
        repo.resolve_manual_recovery(**dict(args, reason='Different review'))
    after = read(database, 'runtime_plans')
    assert after['status'] == 'cancelled' and after['outcome_hash'] is None
    assert after['outcome_json'] == before['outcome_json'] and after['plan_hash'] == before['plan_hash']
    with database[0]() as conn, conn.cursor() as cur:
        assert not repo._has_unresolved_plans(cur, database[1])
        cur.execute("SELECT outcome_json FROM workmanship_sim_connector_runtime_audit WHERE plan_id=%s AND event_type='human_recovery_disposition'", (args['plan_id'],))
        audit = json.loads(cur.fetchone()['outcome_json'])
        assert audit['expected_plan_hash'] == args['expected_plan_hash']
        assert audit['expected_outcome_hash'] is None and audit['decision'] == 'abandoned'


def test_manual_recovery_result_hash_still_required_and_old_audit_replays(database):
    args = recovery_case(database)
    before = read(database, 'runtime_plans')
    plan_only = dict(args, decision='abandoned', expected_plan_hash='sha256:' + before['plan_hash'])
    plan_only.pop('expected_outcome_hash')
    repo = SimulationConnectorRepository()
    with pytest.raises(ConnectorRepositoryError, match='recovery_state_changed'):
        repo.resolve_manual_recovery(**plan_only)
    with pytest.raises(ConnectorRepositoryError, match='recovery_state_changed'):
        repo.resolve_manual_recovery(**dict(args, expected_plan_hash='sha256:'+'0'*64))
    assert read(database, 'runtime_plans') == before
    result = repo.resolve_manual_recovery(**args)
    legacy = {key: value for key, value in args.items() if key not in {'actor_id', 'tenant_id', 'now'}}
    with database[0]() as conn, conn.cursor() as cur:
        cur.execute('UPDATE workmanship_sim_connector_runtime_audit SET outcome_json=%s WHERE audit_id=%s',
                    (json.dumps(legacy), result['audit_ref']))
    assert repo.resolve_manual_recovery(**args) == result
    with database[0]() as conn, conn.cursor() as cur:
        cur.execute('SELECT outcome_json FROM workmanship_sim_connector_runtime_audit WHERE audit_id=%s', (result['audit_ref'],))
        assert json.loads(cur.fetchone()['outcome_json']) == legacy


@pytest.mark.parametrize('raw_plan', ['{invalid json', '{}', 'null', '{"steps":[null]}'])
@pytest.mark.parametrize('mutation', [None, 'plan_json', 'plan_hash', 'outcome_hash', 'status', 'runtime_generation'])
def test_manual_recovery_fingerprint_archives_damaged_plan_and_refuses_stale_snapshot(database, raw_plan, mutation):
    try:
        json.loads(raw_plan)
    except json.JSONDecodeError:
        with database[0]() as conn:
            if not isinstance(conn, SQLiteConnection):
                pytest.skip('Native JSON columns cannot store syntactically invalid JSON; SQLite covers raw corruption')
    args = recovery_case(database)
    args.pop('expected_outcome_hash')
    args['decision'] = 'abandoned'
    with database[0]() as conn, conn.cursor() as cur:
        cur.execute('UPDATE workmanship_sim_connector_runtime_plans SET outcome_hash=NULL,plan_hash=%s,plan_json=%s WHERE plan_id=%s',
                    ('', raw_plan, args['plan_id']))
    repo = SimulationConnectorRepository()
    item = repo.search_manual_recovery(actor_id='user-001', tenant_id='tenant-001')['items'][0]
    assert item['eligible'] and item['allowed_decisions'] == ['abandoned']
    assert item['operation_id'] == 'unknown_operation' and item['ineligible_reason'] is None
    assert re.fullmatch(r'sha256:[0-9a-f]{64}', item['recovery_fingerprint'])
    args['expected_recovery_fingerprint'] = item['recovery_fingerprint']
    if mutation:
        # Change the JSON value, not whitespace that native JSON may normalize.
        values = {'plan_json': json.dumps({'steps': [], 'recovery_test_revision': 1}),
                  'plan_hash': 'a'*64, 'outcome_hash': 'b'*64,
                  'status': 'manual_review_required', 'runtime_generation': 8}
        with database[0]() as conn, conn.cursor() as cur:
            cur.execute(f'UPDATE workmanship_sim_connector_runtime_plans SET {mutation}=%s WHERE plan_id=%s',
                        (values[mutation], args['plan_id']))
        before = read(database, 'runtime_plans')
        with pytest.raises(ConnectorRepositoryError, match='recovery_state_changed'):
            repo.resolve_manual_recovery(**args)
        assert read(database, 'runtime_plans') == before
        return
    before = read(database, 'runtime_plans')
    with pytest.raises(ConnectorRepositoryError, match='recovery_state_changed'):
        repo.resolve_manual_recovery(**dict(args, expected_recovery_fingerprint=None))
    result = repo.resolve_manual_recovery(**args)
    assert result['decision'] == 'abandoned' and result['retry_started'] is False
    assert repo.resolve_manual_recovery(**args) == result
    with pytest.raises(ConnectorRepositoryError, match='recovery_decision_conflict'):
        repo.resolve_manual_recovery(**dict(args, reason='Changed reason'))
    after = read(database, 'runtime_plans')
    assert after['status'] == 'cancelled'
    assert after['plan_json'] == before['plan_json'] and after['outcome_json'] == before['outcome_json']
    with database[0]() as conn, conn.cursor() as cur:
        assert not repo._has_unresolved_plans(cur, database[1])
        cur.execute("SELECT outcome_json FROM workmanship_sim_connector_runtime_audit WHERE plan_id=%s AND event_type='human_recovery_disposition'", (args['plan_id'],))
        audit = json.loads(cur.fetchone()['outcome_json'])
        assert audit['expected_recovery_fingerprint'] == args['expected_recovery_fingerprint']


def test_manual_recovery_fingerprint_binds_each_storage_identity_field(database):
    recovery_case(database)
    row = read(database, 'runtime_plans')
    fingerprint = SimulationConnectorRepository._recovery_fingerprint
    original = fingerprint(row)
    for field in ('device_id', 'plan_id', 'runtime_generation', 'status', 'plan_json',
                  'plan_hash', 'outcome_hash', 'outcome_json', 'protocol', 'actor_gid', 'tenant_gid'):
        assert fingerprint(dict(row, **{field: str(row[field]) + 'changed'})) != original
    assert fingerprint(dict(reversed(list(row.items())))) == original
    # Pure row test: raw-string sensitivity must not depend on a database keeping
    # insignificant whitespace when it stores a native JSON value.
    if isinstance(row['plan_json'], str):
        assert fingerprint(dict(row, plan_json=row['plan_json'] + ' ')) != original


def test_manual_recovery_search_count_and_page_share_one_statement(database, monkeypatch):
    recovery_case(database)
    with database[0]() as conn, conn.cursor() as cur:
        cursor_type = type(cur)
    execute = cursor_type.execute
    statements = []
    def observe(self, sql, *args, **kwargs):
        if sql.lstrip().upper().startswith('SELECT') and 'workmanship_sim_connector_runtime_plans' in sql:
            statements.append(sql)
        return execute(self, sql, *args, **kwargs)
    monkeypatch.setattr(cursor_type, 'execute', observe)
    repo = SimulationConnectorRepository()
    page = repo.search_manual_recovery(actor_id='user-001', tenant_id='tenant-001')
    assert page['total'] == 1 and len(page['items']) == 1
    # At READ COMMITTED two reads can disagree if a disposition commits between
    # them. One statement guarantees the count and items use one SQL snapshot.
    assert len(statements) == 1
    statements.clear()
    assert repo.search_manual_recovery(actor_id='user-001', tenant_id='tenant-001', page=2) == dict(
        items=[], page=2, page_size=5, total=1, page_count=1)
    assert len(statements) == 1
    statements.clear()
    assert repo.search_manual_recovery(actor_id='other', tenant_id='tenant-001') == dict(
        items=[], page=1, page_size=5, total=0, page_count=0)
    assert len(statements) == 1


def test_manual_recovery_search_paginates_scoped_stable_results(database):
    from backend.capabilities.models_next import CapabilityContext
    from backend.capabilities.registry_next import CapabilityRegistry
    from plugins.simulation.simulation_backend.capabilities.connector_runtime import ConnectorControlPlane, register_connector_runtime_capabilities
    import jsonschema
    args = recovery_case(database)
    with database[0]() as conn, conn.cursor() as cur:
        for index in range(27):
            identity = f'page-copy-{index:02d}'
            cur.execute("INSERT INTO workmanship_sim_connector_runtime_plans "
                "(plan_id,protocol,device_id,runtime_generation,runtime_instance_id,session_token_hash,tenant_gid,actor_gid,"
                "idempotency_key,plan_hash,plan_json,status,expires_at,created_at) "
                "SELECT %s,protocol,device_id,runtime_generation,runtime_instance_id,session_token_hash,tenant_gid,actor_gid,"
                "%s,plan_hash,plan_json,status,expires_at,%s FROM workmanship_sim_connector_runtime_plans WHERE plan_id=%s",
                (identity, identity, NOW, args['plan_id']))
        cur.execute("UPDATE workmanship_sim_connector_runtime_plans SET actor_gid='other' WHERE plan_id IN (%s,%s)",
                    (args['plan_id'], 'page-copy-00'))
        cur.execute("UPDATE workmanship_sim_connector_runtime_plans SET tenant_gid='other' WHERE plan_id='page-copy-01'")
        cur.execute("UPDATE workmanship_sim_connector_runtime_plans SET runtime_generation=6 WHERE plan_id='page-copy-02'")
        cur.execute("UPDATE workmanship_sim_connector_runtime_plans SET status='cancelled' WHERE plan_id='page-copy-03'")
    registry = CapabilityRegistry()
    register_connector_runtime_capabilities(registry, ConnectorControlPlane(SimulationConnectorRepository(), clock=lambda: NOW))
    search = registry.get('simulation.connector.recovery.search', 1)
    context = CapabilityContext(user_gid='user-001', team_gid='tenant-001', source='web')
    def fetch(payload):
        jsonschema.validate(payload, search.spec.input_schema)
        result = search.handler(payload, context).data
        jsonschema.validate(result, search.spec.output_schema)
        assert len(result['items']) <= result['page_size']
        return result
    first = fetch({})
    assert {k:v for k,v in first.items() if k != 'items'} == dict(page=1, page_size=5, total=23, page_count=5)
    assert [item['plan_id'] for item in first['items']] == [f'page-copy-{i:02d}' for i in range(4, 9)]
    last = fetch({'page': 5, 'page_size': 5})
    assert [item['plan_id'] for item in last['items']] == ['page-copy-24', 'page-copy-25', 'page-copy-26']
    assert last == fetch({'page': 5, 'page_size': 5})
    wide = fetch({'page': 2, 'page_size': 20})
    assert wide['items'] == last['items'] and wide['page_count'] == 2 and wide['total'] == 23
    assert fetch({'page': 6}) == dict(items=[], page=6, page_size=5, total=23, page_count=5)
    assert fetch({'page': 10**30}) == dict(items=[], page=10**30, page_size=5, total=23, page_count=5)
    other = search.handler({}, context.model_copy(update={'user_gid': 'other'})).data
    assert other == dict(items=[], page=1, page_size=5, total=0, page_count=0)
    other_tenant = search.handler({}, context.model_copy(update={'team_gid': 'other'})).data
    assert other_tenant == dict(items=[], page=1, page_size=5, total=0, page_count=0)
    with database[0]() as conn, conn.cursor() as cur:
        cur.execute('UPDATE workmanship_sim_connector_runtime_plans SET created_at=%s WHERE plan_id=%s',
                    (NOW - timedelta(days=1), 'page-copy-26'))
    assert [item['plan_id'] for item in fetch({})['items']] == ['page-copy-26', 'page-copy-04', 'page-copy-05', 'page-copy-06', 'page-copy-07']
    for invalid in ({'page': 0}, {'page': True}, {'page': 1.5}, {'page_size': 0}, {'page_size': 21}, {'page_size': False}, {'unknown': 1}):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, search.spec.input_schema)
        if 'unknown' not in invalid:
            with pytest.raises(ConnectorRepositoryError, match='recovery_input_invalid'):
                SimulationConnectorRepository().search_manual_recovery(actor_id='user-001', tenant_id='tenant-001', **invalid)


def test_manual_recovery_closes_only_reviewed_plan_and_preserves_audit(database):
    args = recovery_case(database)
    with database[0]() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO workmanship_sim_connector_runtime_plans "
            "(plan_id,protocol,device_id,runtime_generation,runtime_instance_id,session_token_hash,tenant_gid,actor_gid,"
            "idempotency_key,plan_hash,plan_json,status,expires_at) "
            "SELECT %s,protocol,device_id,runtime_generation,runtime_instance_id,session_token_hash,tenant_gid,actor_gid,"
            "%s,plan_hash,plan_json,status,expires_at FROM workmanship_sim_connector_runtime_plans WHERE plan_id=%s",
            ('unrelated-' + args['plan_id'], 'unrelated', args['plan_id']))
        cur.execute("SELECT * FROM workmanship_sim_connector_runtime_audit WHERE device_id=%s ORDER BY audit_id", (args['device_id'],))
        before = cur.fetchall()
    repo = SimulationConnectorRepository()
    result = repo.resolve_manual_recovery(**dict(args, decision='executed'))
    with database[0]() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM workmanship_sim_connector_runtime_audit WHERE device_id=%s ORDER BY audit_id", (args['device_id'],))
        after = cur.fetchall()
        assert [row for row in after if row['audit_id'] != result['audit_ref']] == before
        audit = next(row for row in after if row['audit_id'] == result['audit_ref'])
        assert audit['actor_id'] == 'user-001' and audit['reason'] == args['reason']
        assert json.loads(audit['outcome_json'])['decision'] == 'executed'
        cur.execute("SELECT status FROM workmanship_sim_connector_runtime_plans WHERE plan_id=%s", ('unrelated-' + args['plan_id'],))
        assert cur.fetchone()['status'] == 'outcome_unknown'
        cur.execute("SELECT COUNT(*) AS count FROM workmanship_sim_connector_runtime_plans WHERE device_id=%s", (args['device_id'],))
        assert cur.fetchone()['count'] == 2
    assert len(repo.search_manual_recovery(actor_id='user-001', tenant_id='tenant-001')['items']) == 1


def test_manual_recovery_concurrent_decisions_have_one_winner(database):
    args = recovery_case(database)
    def resolve(decision):
        try:
            return SimulationConnectorRepository().resolve_manual_recovery(**dict(args, decision=decision))
        except ConnectorRepositoryError as exc:
            return str(exc)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(resolve, ['executed', 'not_executed']))
    assert len([result for result in results if isinstance(result, dict)]) == 1
    assert 'recovery_decision_conflict' in results
    with database[0]() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS count FROM workmanship_sim_connector_runtime_audit "
                    "WHERE device_id=%s AND event_type='human_recovery_disposition'", (args['device_id'],))
        assert cur.fetchone()['count'] == 1


@pytest.mark.parametrize('column,value', [('actor_gid','other'), ('tenant_gid','other'), ('runtime_generation',8)])
def test_manual_recovery_requires_plan_identity_as_well_as_device_identity(database, column, value):
    args = recovery_case(database)
    with database[0]() as conn, conn.cursor() as cur:
        cur.execute(f"UPDATE workmanship_sim_connector_runtime_plans SET {column}=%s WHERE plan_id=%s", (value,args['plan_id']))
    repo = SimulationConnectorRepository()
    assert repo.search_manual_recovery(actor_id='user-001', tenant_id='tenant-001')['items'] == []
    with pytest.raises(ConnectorRepositoryError, match='recovery_state_changed|runtime_owner_mismatch'):
        repo.resolve_manual_recovery(**args)


def test_manual_recovery_rejects_same_decision_with_different_reason(database):
    args = recovery_case(database)
    repo = SimulationConnectorRepository()
    repo.resolve_manual_recovery(**args)
    with pytest.raises(ConnectorRepositoryError, match='recovery_decision_conflict'):
        repo.resolve_manual_recovery(**dict(args, reason='A different review'))


def test_manual_recovery_audit_failure_rolls_back_plan_close(database):
    args = recovery_case(database)
    before = read(database, 'runtime_plans')
    with database[0]() as conn, conn.cursor() as cur:
        if not isinstance(conn, SQLiteConnection):
            pytest.skip('SQLite trigger fault injection; native lock coverage uses the concurrent decision test')
        cur.execute("CREATE TRIGGER reject_human_audit BEFORE INSERT ON workmanship_sim_connector_runtime_audit "
                    "WHEN NEW.event_type='human_recovery_disposition' BEGIN SELECT RAISE(ABORT,'test audit unavailable'); END")
    with pytest.raises(sqlite3.IntegrityError, match='test audit unavailable'):
        SimulationConnectorRepository().resolve_manual_recovery(**args)
    assert read(database, 'runtime_plans') == before


def test_registration_race_has_one_winner_and_never_stores_plaintext(database):
    def register(instance):
        try:
            return session(database, instance=instance)
        except ConnectorRepositoryError as exc:
            return str(exc)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(register, ["first", "second"]))
    winners = [r for r in results if not isinstance(r, str)]
    assert len(winners) == 1
    assert "runtime_session_active" in results
    winner = winners[0]
    row = read(database)
    assert row["current_runtime_instance_id"] == winner.runtime_instance_id
    assert row["session_token_hash"] == hashlib.sha256(winner.session_token.encode()).hexdigest()
    assert winner.session_token not in str(row)
    assert winner.session_token not in repr(winner)


def test_expired_session_replaced_and_stale_token_fenced(database):
    old = session(database)
    new = session(database, now=NOW + timedelta(seconds=61), instance="replacement")
    assert old.session_token != new.session_token
    with pytest.raises(ConnectorRepositoryError, match="runtime_session_invalid"):
        lease(database, old, NOW + timedelta(seconds=61))


def test_authenticated_process_restart_rotates_session_and_retires_old_queued_reads(database):
    old = session(database)
    queued = queue(database, old, side_effect_classification="read")

    new = SimulationConnectorRepository().restart_runtime_session(
        database[1], old.runtime_generation, old.runtime_instance_id,
        old.session_token, "replacement", NOW + timedelta(seconds=1),
        NOW + timedelta(seconds=61),
    )

    assert new.runtime_instance_id == "replacement"
    assert new.session_token != old.session_token
    assert read(database, "runtime_plans")["status"] == "failed_without_effect"
    with pytest.raises(ConnectorRepositoryError, match="runtime_session_invalid"):
        lease(database, old, NOW + timedelta(seconds=1))
    assert lease(database, new, NOW + timedelta(seconds=1)) is None


@pytest.mark.parametrize("status", ["leased", "executing", "outcome_unknown", "manual_review_required"])
def test_unresolved_write_plan_blocks_registration_and_takeover(database, status):
    registered = session(database)
    current = queue(database, registered, side_effect_classification="write")
    lease(database, registered)
    transaction, _ = database
    with transaction() as conn, conn.cursor() as cur:
        cur.execute("UPDATE workmanship_sim_connector_runtime_plans SET status=%s WHERE plan_id=%s", (status, current.plan_id))
    with pytest.raises(ConnectorRepositoryError, match="runtime_plans_unresolved"):
        session(database, now=NOW + timedelta(seconds=61), instance="replacement")
    with pytest.raises(ConnectorRepositoryError, match="runtime_plans_unresolved"):
        takeover(database, registered, 8)
    assert read(database)["runtime_generation"] == 7


@pytest.mark.parametrize("status", ["leased", "executing", "outcome_unknown", "manual_review_required"])
def test_expired_read_only_plan_does_not_deadlock_runtime_restart(database, status):
    registered = session(database)
    current = queue(database, registered)
    lease(database, registered)
    transaction, _ = database
    with transaction() as conn, conn.cursor() as cur:
        cur.execute("UPDATE workmanship_sim_connector_runtime_plans SET status=%s WHERE plan_id=%s", (status, current.plan_id))

    replacement = session(database, now=NOW + timedelta(seconds=61), instance="replacement")

    assert replacement.runtime_instance_id == "replacement"
    assert read(database, "runtime_plans")["status"] == "failed_without_effect"
    with transaction() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT reason FROM workmanship_sim_connector_runtime_audit "
            "WHERE plan_id=%s AND event_type='plan_failed_without_effect'",
            (current.plan_id,),
        )
        assert cur.fetchone()["reason"] == "read_only_plan_abandoned_during_runtime_restart"


def test_manual_review_read_plan_with_live_lease_still_blocks_runtime_restart(database):
    registered = session(database)
    current = queue(database, registered)
    lease(database, registered)
    transaction, _ = database
    with transaction() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE workmanship_sim_connector_runtime_plans SET status='manual_review_required',lease_until=%s WHERE plan_id=%s",
            (NOW + timedelta(minutes=5), current.plan_id),
        )

    with pytest.raises(ConnectorRepositoryError, match="runtime_plans_unresolved"):
        session(database, now=NOW + timedelta(seconds=61), instance="replacement")


def takeover(database, registered, new_generation):
    return SimulationConnectorRepository().force_takeover(database[1], 7, new_generation, "replacement",
        NOW, NOW + timedelta(seconds=60), expected_runtime_instance_id=registered.runtime_instance_id,
        expected_session_token_hash=hashlib.sha256(registered.session_token.encode()).hexdigest(),
        actor_id="user-001", reason="User requested runtime replacement")


def test_takeover_requires_exact_next_generation_and_audits_actor(database):
    registered = session(database)
    for invalid in (7, 9):
        with pytest.raises(ConnectorRepositoryError, match="runtime_generation_invalid"):
            takeover(database, registered, invalid)
    new = takeover(database, registered, 8)
    assert new.runtime_generation == 8
    with pytest.raises(ConnectorRepositoryError, match="runtime_session_invalid"):
        lease(database, registered)
    assert read(database)["current_runtime_instance_id"] == "replacement"
    transaction, device = database
    with transaction() as conn, conn.cursor() as cur:
        cur.execute("SELECT actor_id,reason FROM workmanship_sim_connector_runtime_audit WHERE device_id=%s AND event_type='force_takeover'", (device,))
        assert cur.fetchone() == {"actor_id": "user-001", "reason": "User requested runtime replacement"}


def test_leasing_race_has_one_winner_and_binds_session(database):
    registered = session(database)
    queue(database, registered)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: lease(database, registered), range(2)))
    assert sum(value is not None for value in results) == 1
    row = read(database, "runtime_plans")
    assert row["runtime_generation"] == 7
    assert row["runtime_instance_id"] == registered.runtime_instance_id
    assert row["session_token_hash"] == read(database)["session_token_hash"]


def test_expired_lease_becomes_unknown_and_cannot_be_released(database):
    registered = session(database)
    queue(database, registered)
    lease(database, registered)
    assert lease(database, registered, NOW + timedelta(seconds=16)) is None
    assert read(database, "runtime_plans")["status"] == "outcome_unknown"


def test_completion_idempotency_conflict_and_reconciliation(database):
    registered = session(database)
    current = queue(database, registered)
    leased = lease(database, registered)
    unknown = outcome_for(current, leased, "outcome_unknown")
    complete(database, registered, unknown)
    complete(database, registered, unknown)
    success = reconciled_outcome(database, current, instance=registered.runtime_instance_id, token=registered.session_token)
    normal = outcome_for(current, leased).model_dump(mode='json')
    normal['journal_sequence'] = 2
    normal['signature'] = sign_outcome(normal)
    with pytest.raises(ConnectorRepositoryError, match="connector_outcome_conflict"):
        complete(database, registered, ConnectorPlanOutcomeV2.model_validate(normal))
    complete(database, registered, success, reconciled=True)
    row = read(database, "runtime_plans")
    assert row["status"] == "succeeded"
    assert row["reconciliation_state"] == "succeeded"
    with pytest.raises(ConnectorRepositoryError, match='journal_sequence_invalid'):
        complete(database, registered, success, reconciled=True)


def test_completed_write_allows_a_later_intentional_repeat_with_new_idempotency_key(database):
    registered = session(database)
    normalized = 'sha256:' + hashlib.sha256(b'all_off').hexdigest()
    first = queue(database, registered, idempotency_key='hide-1', normalized_input_hash=normalized,
                  side_effect_classification='write')
    complete(database, registered, outcome_for(first, lease(database, registered)))

    second = queue(database, registered, idempotency_key='hide-2', normalized_input_hash=normalized,
                   side_effect_classification='write')
    assert second.plan_id != first.plan_id
    assert lease(database, registered)['plan']['plan_id'] == second.plan_id


def test_wake_subscription_can_close_the_empty_lease_race_by_checking_the_queue(database):
    registered = session(database)
    repository = SimulationConnectorRepository()
    queue(database, registered, idempotency_key='wake-check')

    assert repository.has_v2_queued_plan(
        database[1], registered.runtime_generation, registered.runtime_instance_id,
        registered.session_token, NOW, 'electron',
    ) is True
    lease(database, registered)
    assert repository.has_v2_queued_plan(
        database[1], registered.runtime_generation, registered.runtime_instance_id,
        registered.session_token, NOW, 'electron',
    ) is False

@pytest.mark.parametrize("field,value", [
    ("device_id", "other"), ("runtime_generation", 8), ("runtime_instance_id", "other"),
    ("tenant_id", "other"), ("plan_hash", "0" * 64), ("lease_id", "other"),
])
def test_outcome_identity_mismatch_rolls_back(database, field, value):
    registered = session(database)
    current = queue(database, registered)
    leased = lease(database, registered)
    outcome = outcome_for(current, leased).model_copy(update={field: value})
    with pytest.raises(ConnectorRepositoryError, match="plan_lease_invalid"):
        complete(database, registered, outcome)
    assert read(database, "runtime_plans")["status"] == "leased"


def test_wrong_token_and_expired_session_cannot_complete_or_reconcile(database):
    from dataclasses import replace
    registered = session(database)
    current = queue(database, registered)
    leased = lease(database, registered)
    outcome = outcome_for(current, leased)
    for reconcile in (False, True):
        if reconcile:
            complete(database, registered, outcome_for(current, leased, 'outcome_unknown'))
            outcome = reconciled_outcome(database, current, instance=registered.runtime_instance_id, token=registered.session_token)
        with pytest.raises(ConnectorRepositoryError, match="runtime_session_invalid"):
            complete(database, replace(registered, session_token="wrong"), outcome, reconciled=reconcile)
        with pytest.raises(ConnectorRepositoryError, match="runtime_session_invalid"):
            complete(database, registered, outcome, reconciled=reconcile, now=NOW + timedelta(seconds=61))
    assert read(database, "runtime_plans")["status"] == "outcome_unknown"


def test_migration_preserves_v1_defaults_and_rejects_v1_in_v2_tables(database):
    transaction, device = database
    with transaction() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO workmanship_sim_connector_plans (plan_id,connector_id,status,tenant_gid,user_gid,plan_hash,plan_json,expires_at) "
                    "VALUES (%s,%s,'queued','t','u','h','{}',%s)", (device, device, NOW))
        cur.execute("SELECT protocol FROM workmanship_sim_connector_plans WHERE plan_id=%s", (device,))
        assert cur.fetchone()["protocol"] == "ai00.connector.execution-plan.v1"
        with pytest.raises(Exception):
            cur.execute("UPDATE workmanship_sim_connector_runtime_devices SET protocol='ai00.connector.execution-plan.v1' WHERE device_id=%s", (device,))
    assert read(database)["protocol"] == V2


def test_v1_unresolved_plan_blocks_v2_registration(database):
    transaction, device = database
    with transaction() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO workmanship_sim_connector_plans (plan_id,connector_id,status,tenant_gid,user_gid,plan_hash,plan_json,expires_at) "
                    "VALUES (%s,%s,'leased','t','u','h','{}',%s)", (device, device, NOW))
    with pytest.raises(ConnectorRepositoryError, match="runtime_plans_unresolved"):
        session(database)


@pytest.mark.parametrize("seconds", [0, -1, 301])
def test_session_expiry_is_bounded(database, seconds):
    with pytest.raises(ConnectorRepositoryError, match="runtime_session_expiry_invalid"):
        SimulationConnectorRepository().register_runtime_session(database[1], 7, "instance", NOW, NOW + timedelta(seconds=seconds))
    assert read(database)["session_token_hash"] is None


def test_stale_takeover_snapshot_cannot_replace_registered_winner(database):
    old = session(database)
    current = session(database, now=NOW + timedelta(seconds=61), instance="new")
    with pytest.raises(ConnectorRepositoryError, match="runtime_session_conflict"):
        takeover(database, old, 8)
    assert read(database)["current_runtime_instance_id"] == current.runtime_instance_id


def test_outcome_rollback_if_audit_fails(database, monkeypatch):
    from types import SimpleNamespace
    registered = session(database)
    plan = queue(database, registered)
    leased = lease(database, registered)
    audit_id = read(database, "runtime_audit")["audit_id"]
    # Force a real duplicate-key constraint failure on the audit INSERT.
    monkeypatch.setattr(connector_repository.uuid, "uuid4", lambda: SimpleNamespace(hex=audit_id))
    with pytest.raises(Exception):
        complete(database, registered, outcome_for(plan, leased))
    assert read(database, "runtime_plans")["status"] == "leased"


def test_legacy_leasing_is_fenced_for_v2_device(database):
    assert SimulationConnectorRepository().lease_plan(database[1]) is None


def test_v2_tables_have_simulation_ownership():
    ownership = json.loads((ROOT / "backend/governance/domain_table_ownership.json").read_text())
    entries = {row["table"]: row for row in ownership["tables"]}
    for table in re.findall(r"CREATE TABLE IF NOT EXISTS `([^`]+)`", MIGRATION.read_text()):
        assert entries.get(table, {}).get("owner") == "simulation"
        assert entries[table]["runtime_domain"] == "simulation"


def recovery(database, plan, *, instance="recovery-1", token="recovery-secret", now=NOW + timedelta(seconds=61)):
    return SimulationConnectorRepository().register_reconciliation_session(database[1], 7, instance,
        plan.plan_id, hashlib.sha256(token.encode()).hexdigest(), now + timedelta(seconds=60), now=now)


def uncertain(database):
    registered = session(database)
    plan = queue(database, registered)
    leased = lease(database, registered)
    complete(database, registered, outcome_for(plan, leased, "outcome_unknown"))
    return registered, plan, leased


def test_recovery_registration_race_and_scope(database):
    registered, plan, leased = uncertain(database)
    with pytest.raises(ConnectorRepositoryError, match="runtime_session_active"):
        recovery(database, plan, now=NOW)
    def register(index):
        try:
            recovery(database, plan, instance=f"recovery-{index}", token=f"token-{index}")
            return index
        except ConnectorRepositoryError as exc:
            return str(exc)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(register, [1, 2]))
    assert "reconciliation_session_active" in results
    winner = next(value for value in results if isinstance(value, int))
    now = NOW + timedelta(seconds=62)
    repo = SimulationConnectorRepository()
    for method, args in (
        (repo.lease_v2_plan, (now,)),
        (repo.complete_v2_plan, (outcome_for(plan, leased), now)),
    ):
        with pytest.raises(ConnectorRepositoryError, match="runtime_session_invalid"):
            method(database[1], 7, f"recovery-{winner}", f"token-{winner}", *args)
    with pytest.raises(ConnectorRepositoryError, match="plan_lease_invalid"):
        repo.mark_reconciled(database[1], 7, f"recovery-{winner}", f"token-{winner}",
            reconciled_outcome(database, plan, instance=f'recovery-{winner}', token=f'token-{winner}', now=now)
                .model_copy(update={"plan_id": "other-plan"}), now)
    repo.mark_reconciled(database[1], 7, f"recovery-{winner}", f"token-{winner}",
        reconciled_outcome(database, plan, instance=f'recovery-{winner}', token=f'token-{winner}', now=now), now)
    row = read(database)
    assert row["current_runtime_instance_id"] == registered.runtime_instance_id
    assert row["session_token_hash"] == hashlib.sha256(registered.session_token.encode()).hexdigest()
    assert read(database, "runtime_plans")["runtime_instance_id"] == registered.runtime_instance_id
    transaction, device = database
    with transaction() as conn, conn.cursor() as cur:
        cur.execute("SELECT runtime_instance_id,recovery_instance_id FROM workmanship_sim_connector_runtime_audit WHERE device_id=%s AND event_type='plan_reconciled'", (device,))
        assert cur.fetchone() == {"runtime_instance_id": registered.runtime_instance_id, "recovery_instance_id": f"recovery-{winner}"}
    new = session(database, now=now, instance="new-normal")
    assert new.runtime_instance_id == "new-normal"


def test_recovery_rejects_expiry_wrong_generation_and_resolved_plan(database):
    registered, plan, leased = uncertain(database)
    repo = SimulationConnectorRepository()
    with pytest.raises(ConnectorRepositoryError, match="runtime_generation_invalid"):
        repo.register_reconciliation_session(database[1], 8, "recovery", plan.plan_id, "a" * 64,
            NOW + timedelta(seconds=120), now=NOW + timedelta(seconds=61))
    recovery(database, plan)
    evidence = reconciled_outcome(database, plan, instance='recovery-1', token='recovery-secret', now=NOW + timedelta(seconds=61))
    with pytest.raises(ConnectorRepositoryError, match="runtime_session_invalid"):
        repo.mark_reconciled(database[1], 7, "recovery-1", "recovery-secret", evidence, NOW + timedelta(seconds=122))
    recovery(database, plan, instance="recovery-2", token="new-token", now=NOW + timedelta(seconds=122))
    repo.mark_reconciled(database[1], 7, "recovery-2", "new-token",
        reconciled_outcome(database, plan, instance='recovery-2', token='new-token', now=NOW + timedelta(seconds=123)),
        NOW + timedelta(seconds=123))
    with pytest.raises(ConnectorRepositoryError, match="plan_reconciliation_invalid"):
        recovery(database, plan, now=NOW + timedelta(seconds=200))


def test_reconciliation_preserves_original_signed_outcome_in_audit(database):
    registered, plan, leased = uncertain(database)
    complete(database, registered, reconciled_outcome(database, plan,
        instance=registered.runtime_instance_id, token=registered.session_token), reconciled=True)
    transaction, device = database
    with transaction() as conn, conn.cursor() as cur:
        cur.execute("SELECT outcome_json FROM workmanship_sim_connector_runtime_audit WHERE device_id=%s AND event_type='plan_outcome'", (device,))
        value = cur.fetchone()["outcome_json"]
        assert (json.loads(value) if isinstance(value, str) else value)["overall_status"] == "outcome_unknown"


def test_pairing_nonce_is_unique_and_protocol_is_required(database):
    import pymysql
    transaction, device = database
    nonce_hash = hashlib.sha256(device.encode()).hexdigest()
    statement = ("INSERT INTO workmanship_sim_connector_app_pairings "
        "(pairing_id,protocol,device_id,bootstrap_encryption_jwk,bootstrap_nonce_hash,device_signing_jwk,device_key_id,status,expires_at) "
        "VALUES (%s,%s,%s,'{}',%s,'{}','key','created',%s)")
    with transaction() as conn, conn.cursor() as cur:
        cur.execute(statement, (device, V2, device, nonce_hash, NOW))
    with pytest.raises((sqlite3.IntegrityError, pymysql.IntegrityError)):
        with transaction() as conn, conn.cursor() as cur:
            cur.execute(statement, (device + '-duplicate', V2, device, nonce_hash, NOW))
    with pytest.raises((sqlite3.IntegrityError, pymysql.IntegrityError)):
        with transaction() as conn, conn.cursor() as cur:
            cur.execute(statement, (device + '-invalid', None, device, 'b' * 64, NOW))


@pytest.mark.parametrize("status", ["leased", "executing"])
def test_crash_before_report_can_recover_after_lease_and_session_expire(database, status):
    registered = session(database)
    plan = queue(database, registered)
    leased = lease(database, registered)
    transaction, device = database
    with transaction() as conn, conn.cursor() as cur:
        cur.execute("UPDATE workmanship_sim_connector_runtime_plans SET status=%s WHERE plan_id=%s", (status, plan.plan_id))
    now = NOW + timedelta(seconds=61)
    recovery(database, plan, now=now)
    row = read(database, "runtime_plans")
    assert row["status"] == "outcome_unknown"
    assert row["reconciliation_state"] == "pending"
    assert row["runtime_instance_id"] == registered.runtime_instance_id
    with transaction() as conn, conn.cursor() as cur:
        cur.execute("SELECT runtime_instance_id,session_token_hash FROM workmanship_sim_connector_runtime_audit "
                    "WHERE device_id=%s AND plan_id=%s AND event_type='lease_expired'", (device, plan.plan_id))
        assert cur.fetchone() == {"runtime_instance_id": registered.runtime_instance_id,
            "session_token_hash": hashlib.sha256(registered.session_token.encode()).hexdigest()}
    SimulationConnectorRepository().mark_reconciled(device, 7, "recovery-1", "recovery-secret",
        reconciled_outcome(database, plan, instance='recovery-1', token='recovery-secret', now=now), now)
    # A crash gives no signed execution evidence for this read step.
    assert read(database, 'runtime_plans')['status'] == 'manual_review_required'
    evidence = read(database, 'runtime_plans')['outcome_json']
    assert session(database, now=now, instance='new-normal').runtime_instance_id == 'new-normal'
    assert read(database, 'runtime_plans')['status'] == 'failed_without_effect'
    assert read(database, 'runtime_plans')['outcome_json'] == evidence


@pytest.mark.parametrize("failure_at", ["expiry_audit", "session_audit"])
def test_crash_recovery_expiry_and_audit_failure_roll_back_together(database, monkeypatch, failure_at):
    from types import SimpleNamespace
    registered = session(database)
    plan = queue(database, registered)
    lease(database, registered)
    audit_id = read(database, "runtime_audit")["audit_id"]
    ids = iter([audit_id] if failure_at == "expiry_audit" else [uuid.uuid4().hex, audit_id])
    monkeypatch.setattr(connector_repository.uuid, "uuid4", lambda: SimpleNamespace(hex=next(ids)))
    import pymysql
    with pytest.raises((sqlite3.IntegrityError, pymysql.IntegrityError)):
        recovery(database, plan)
    assert read(database, "runtime_plans")["status"] == "leased"
    assert read(database, "runtime_recovery_sessions") is None


@pytest.mark.parametrize("replacement", ["expiry", "takeover"])
def test_replacement_terminates_queued_plan_without_rebinding_and_audits(database, replacement):
    old = session(database)
    plan = queue(database, old)
    now = NOW + timedelta(seconds=61) if replacement == "expiry" else NOW
    new = session(database, now=now, instance="new-normal") if replacement == "expiry" else takeover(database, old, 8)
    row = read(database, "runtime_plans")
    assert row["status"] == "failed_without_effect"
    assert row["attempts"] == 0 and row["lease_id"] is None
    assert row["runtime_instance_id"] == old.runtime_instance_id
    assert row["session_token_hash"] == hashlib.sha256(old.session_token.encode()).hexdigest()
    value = json.loads(row["plan_json"]) if isinstance(row["plan_json"], str) else row["plan_json"]
    assert value == plan.model_dump(mode="json")
    transaction, device = database
    with transaction() as conn, conn.cursor() as cur:
        cur.execute("SELECT runtime_instance_id,reason FROM workmanship_sim_connector_runtime_audit "
            "WHERE device_id=%s AND plan_id=%s AND event_type='plan_failed_without_effect'", (device, plan.plan_id))
        assert cur.fetchone() == {"runtime_instance_id": old.runtime_instance_id, "reason": "runtime_session_replaced_before_lease"}
    with pytest.raises(ConnectorRepositoryError, match="plan_session_mismatch"):
        SimulationConnectorRepository().insert_v2_plan(plan, new.session_token, now)
    with pytest.raises(ConnectorRepositoryError, match="plan_session_mismatch"):
        queue(database, new, now=now)  # The obsolete idempotency key also stays bound.
    equivalent = queue(database, new, now=now, idempotency_key="new-request")
    leased = lease(database, new, now)
    assert leased["plan"]["plan_id"] == equivalent.plan_id


@pytest.mark.parametrize("plan_expiry", ["2026-09-07T12:10:00Z", "2026-09-07T12:00:30Z"])
def test_reusing_instance_after_expiry_does_not_acknowledge_old_session_plan(database, plan_expiry):
    old = session(database)
    plan = queue(database, old, expires_at=plan_expiry)
    repo = SimulationConnectorRepository()
    repo.insert_v2_plan(plan, old.session_token, NOW)  # Real same-session retry.
    now = NOW + timedelta(seconds=61)
    new = session(database, now=now, instance=old.runtime_instance_id)
    with pytest.raises(ConnectorRepositoryError, match="plan_session_mismatch"):
        repo.insert_v2_plan(plan, new.session_token, now)


@pytest.mark.parametrize("replacement", ["expiry", "takeover"])
def test_replacement_rolls_back_queue_terminalization_if_final_audit_fails(database, monkeypatch, replacement):
    from types import SimpleNamespace
    import pymysql
    old = session(database)
    queue(database, old)
    audit_id = read(database, "runtime_audit")["audit_id"]
    ids = iter([uuid.uuid4().hex, audit_id])
    monkeypatch.setattr(connector_repository.uuid, "uuid4", lambda: SimpleNamespace(hex=next(ids)))
    with pytest.raises((sqlite3.IntegrityError, pymysql.IntegrityError)):
        if replacement == "expiry":
            session(database, now=NOW + timedelta(seconds=61), instance="new-normal")
        else:
            takeover(database, old, 8)
    assert read(database, "runtime_plans")["status"] == "queued"
    assert read(database)["session_token_hash"] == hashlib.sha256(old.session_token.encode()).hexdigest()


def test_replacement_terminalizes_every_obsolete_queued_plan(database):
    old = session(database)
    first = queue(database, old)
    second = queue(database, old, idempotency_key="second-request")
    session(database, now=NOW + timedelta(seconds=61), instance="replacement")
    transaction, device = database
    with transaction() as conn, conn.cursor() as cur:
        cur.execute("SELECT plan_id,status FROM workmanship_sim_connector_runtime_plans WHERE device_id=%s", (device,))
        assert {row["plan_id"]: row["status"] for row in cur.fetchall()} == {
            first.plan_id: "failed_without_effect", second.plan_id: "failed_without_effect"}


@pytest.mark.parametrize("field,value", [
    ("runtime_instance_id", "other-instance"), ("runtime_generation", 8),
    ("session_token_hash", "a" * 64), ("lease_until", NOW + timedelta(seconds=200)),
])
def test_recovery_expiry_does_not_change_a_nonmatching_or_unexpired_lease(database, field, value):
    registered = session(database)
    plan = queue(database, registered)
    lease(database, registered)
    transaction, _ = database
    with transaction() as conn, conn.cursor() as cur:
        cur.execute(f"UPDATE workmanship_sim_connector_runtime_plans SET {field}=%s WHERE plan_id=%s", (value, plan.plan_id))
    with pytest.raises(ConnectorRepositoryError, match="plan_reconciliation_invalid"):
        recovery(database, plan)
    assert read(database, "runtime_plans")["status"] == "leased"
    assert read(database, "runtime_recovery_sessions") is None


def test_terminal_acknowledgement_after_session_expiry_is_exact_and_side_effect_free(database):
    registered = session(database)
    plan = queue(database, registered)
    leased = lease(database, registered)
    outcome = outcome_for(plan, leased)
    complete(database, registered, outcome)
    before = read(database, 'runtime_plans')
    now = NOW + timedelta(seconds=61)
    repo = SimulationConnectorRepository()
    recovery(database, plan, now=now)
    with pytest.raises(ConnectorRepositoryError, match='runtime_session_invalid'):
        repo.complete_v2_plan(database[1], 7, 'recovery-1', 'recovery-secret', outcome, now)
    assert repo.acknowledge_v2_outcome(database[1], 7, 'recovery-1', 'recovery-secret', outcome, now) == {'accepted': True, 'already_applied': True}
    assert read(database, 'runtime_plans') == before
    assert read(database, 'runtime_recovery_sessions')['consumed_at'] is not None


def test_terminal_acknowledgement_rejects_different_or_missing_outcome(database):
    registered = session(database)
    plan = queue(database, registered)
    leased = lease(database, registered)
    now = NOW + timedelta(seconds=61)
    repo = SimulationConnectorRepository()
    recovery(database, plan, now=now)
    outcome = outcome_for(plan, leased)
    with pytest.raises(ConnectorRepositoryError, match='outcome_acknowledgement_conflict'):
        repo.acknowledge_v2_outcome(database[1], 7, 'recovery-1', 'recovery-secret', outcome, now)


def test_terminal_acknowledgement_rejects_changed_signed_outcome(database):
    registered = session(database)
    plan = queue(database, registered)
    leased = lease(database, registered)
    outcome = outcome_for(plan, leased)
    complete(database, registered, outcome)
    now = NOW + timedelta(seconds=61)
    recovery(database, plan, now=now)
    before = read(database, 'runtime_plans')
    changed = outcome.model_copy(update={'journal_sequence': outcome.journal_sequence + 1})
    with pytest.raises(ConnectorRepositoryError, match='outcome_acknowledgement_conflict'):
        SimulationConnectorRepository().acknowledge_v2_outcome(database[1], 7, 'recovery-1', 'recovery-secret', changed, now)
    assert read(database, 'runtime_plans') == before


def test_terminal_acknowledgement_http_recovery_auth_and_exact_response(database, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.routers import simulation_connector
    from plugins.simulation.simulation_backend.application.connector_runtime_sessions import RuntimeSessionService
    registered = session(database)
    plan = queue(database, registered)
    leased = lease(database, registered)
    outcome = outcome_for(plan, leased)
    complete(database, registered, outcome)
    now = NOW + timedelta(seconds=61)
    recovery(database, plan, now=now)
    monkeypatch.setattr(simulation_connector, 'runtime_session_service', RuntimeSessionService(SimulationConnectorRepository(), clock=lambda: now))
    app = FastAPI()
    app.include_router(simulation_connector.router)
    headers = {'X-AI00-Device-ID': database[1], 'X-AI00-Runtime-Generation': '7',
               'X-AI00-Runtime-Instance-ID': 'recovery-1', 'X-AI00-Runtime-Type': 'electron',
               'X-AI00-Runtime-Session': 'recovery-secret'}
    path = '/api/v1/simulation/connectors/v2/plans/' + plan.plan_id
    body = outcome.model_dump(mode='json')
    with TestClient(app) as client:
        assert client.post(path + '/outcome', headers=headers, json=body).status_code == 401
        changed = {**body, 'journal_sequence': body['journal_sequence'] + 1}
        assert client.post(path + '/acknowledge', headers=headers, json=changed).status_code == 409
        response = client.post(path + '/acknowledge', headers=headers, json=body)
        assert response.status_code == 200
        assert response.json() == {'success': True, 'data': {'accepted': True, 'already_applied': True}}
