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
    ConnectorExecutionPlanV2, ConnectorPlanOutcomeV2, compute_plan_hash,
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


def queue(database, registered, *, now=NOW, idempotency_key=None, expires_at="2026-09-07T12:10:00Z"):
    source = json.loads((ROOT / "backend/tests/fixtures/connector_execution_plan_v2.json").read_text())["plan"]
    source.update(device_id=database[1], plan_id="plan-" + uuid.uuid4().hex,
                  runtime_generation=registered.runtime_generation,
                  runtime_instance_id=registered.runtime_instance_id,
                  issued_at="2026-09-07T12:00:00Z", expires_at=expires_at)
    if idempotency_key is not None:
        source["idempotency_key"] = idempotency_key
        source['normalized_input_hash'] = 'sha256:' + hashlib.sha256(idempotency_key.encode()).hexdigest()
    source['steps'][0]['post_condition_probe_id'] = 'vismockup.application.postcondition@1'
    source["plan_hash"] = compute_plan_hash(source)
    plan = ConnectorExecutionPlanV2.model_validate(source)
    SimulationConnectorRepository().insert_v2_plan(plan, registered.session_token, now)
    return plan


def lease(database, registered, now=NOW):
    return SimulationConnectorRepository().lease_v2_plan(database[1], registered.runtime_generation,
        registered.runtime_instance_id, registered.session_token, now, lease_seconds=15)


def outcome_for(plan, leased, status="succeeded"):
    source = json.loads((ROOT / "backend/tests/fixtures/connector_execution_plan_v2.json").read_text())["outcome"]
    source.update(device_id=plan.device_id, plan_id=plan.plan_id, plan_hash=plan.plan_hash,
        lease_id=leased["lease_id"], overall_status=status, runtime_instance_id=plan.runtime_instance_id, device_key_id='device-key-001')
    source['steps'][0].update(status=status, error_code=None if status=='succeeded' else 'execution_uncertain')
    source['signature'] = sign_outcome(source)
    return ConnectorPlanOutcomeV2.model_validate(source)


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


@pytest.mark.parametrize("status", ["leased", "executing", "outcome_unknown", "manual_review_required"])
def test_unresolved_plan_blocks_registration_and_takeover(database, status):
    registered = session(database)
    current = queue(database, registered)
    lease(database, registered)
    transaction, _ = database
    with transaction() as conn, conn.cursor() as cur:
        cur.execute("UPDATE workmanship_sim_connector_runtime_plans SET status=%s WHERE plan_id=%s", (status, current.plan_id))
    with pytest.raises(ConnectorRepositoryError, match="runtime_plans_unresolved"):
        session(database, now=NOW + timedelta(seconds=61), instance="replacement")
    with pytest.raises(ConnectorRepositoryError, match="runtime_plans_unresolved"):
        takeover(database, registered, 8)
    assert read(database)["runtime_generation"] == 7


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
    with pytest.raises(ConnectorRepositoryError, match='runtime_plans_unresolved'):
        session(database, now=now, instance='new-normal')


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
