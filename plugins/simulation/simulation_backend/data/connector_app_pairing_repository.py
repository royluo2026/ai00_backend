"""Atomic persistence for App pairing; never reads or writes legacy v1 bindings."""
from __future__ import annotations

import json
import uuid
from pymysql.err import IntegrityError

from backend.contracts.connector_execution_plan_v2 import PROTOCOL_V2
from ..domain.connector_pairing import PairingError
from . import connector_repository as storage


class SqlAppPairingRepository:
    @staticmethod
    def _record(row):
        if row:
            for field in ('device_signing_jwk', 'bootstrap_encryption_jwk'):
                if isinstance(row[field], str):
                    row[field] = json.loads(row[field])
            for field in ('expires_at', 'challenge_expires_at', 'challenge_consumed_at'):
                if row.get(field) is not None:
                    row[field] = storage._utc(row[field])
        return row

    @staticmethod
    def _audit(cursor, pairing_id, event, now, *, actor=None, reason=None, device_id=None):
        cursor.execute('INSERT INTO workmanship_sim_connector_runtime_audit '
            '(audit_id,protocol,pairing_id,device_id,event_type,actor_id,reason,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
            (uuid.uuid4().hex, PROTOCOL_V2, pairing_id, device_id, event, actor, reason, now))

    def audit_pairing(self, pairing_id, event, now, *, actor=None, reason=None):
        with storage.get_simulation_conn() as conn, conn.cursor() as cursor:
            self._audit(cursor, pairing_id, event, now, actor=actor, reason=reason)

    def create_pairing(self, record, now):
        try:
            with storage.get_simulation_conn() as conn, conn.cursor() as cursor:
                cursor.execute('SELECT pairing_id FROM workmanship_sim_connector_app_pairings WHERE bootstrap_nonce_hash=%s',
                               (record['bootstrap_nonce_hash'],))
                if cursor.fetchone():
                    raise PairingError('pairing_nonce_reused')
                columns = tuple(record)
                values = tuple(json.dumps(record[k]) if isinstance(record[k], dict) else record[k] for k in columns)
                cursor.execute('INSERT INTO workmanship_sim_connector_app_pairings (' + ','.join(columns) + ') VALUES (' + ','.join(['%s'] * len(columns)) + ')', values)
                self._audit(cursor, record['pairing_id'], 'pairing_created', now)
        except IntegrityError as exc:
            raise PairingError('pairing_nonce_reused') from exc

    def get_pairing(self, pairing_id):
        with storage.get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute('SELECT * FROM workmanship_sim_connector_app_pairings WHERE pairing_id=%s AND protocol=%s', (pairing_id, PROTOCOL_V2))
            return self._record(cursor.fetchone())

    def bind_pairing(self, pairing_id, user_id, tenant_id, expected_version, now):
        with storage.get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute('SELECT * FROM workmanship_sim_connector_app_pairings WHERE pairing_id=%s AND protocol=%s FOR UPDATE', (pairing_id, PROTOCOL_V2))
            row = cursor.fetchone()
            if not row:
                raise PairingError('pairing_not_found')
            if row['owner_user_gid'] is not None and (row['owner_user_gid'], row['tenant_gid']) != (user_id, tenant_id):
                raise PairingError('pairing_owner_mismatch')
            if storage._utc(row['expires_at']) <= now:
                raise PairingError('pairing_expired')
            if row['status'] != 'created' or row['resource_version'] != expected_version:
                raise PairingError('pairing_version_conflict')
            cursor.execute("UPDATE workmanship_sim_connector_app_pairings SET owner_user_gid=%s,tenant_gid=%s,status='user_bound',"
                'user_bound_at=%s,resource_version=resource_version+1,updated_at=%s WHERE pairing_id=%s AND resource_version=%s',
                (user_id, tenant_id, now, now, pairing_id, expected_version))
            if cursor.rowcount != 1:
                raise PairingError('pairing_version_conflict')
            self._audit(cursor, pairing_id, 'pairing_user_bound', now, actor=user_id)
        return self.get_pairing(pairing_id)

    def close_pairing(self, pairing_id, status, now, *, user_id=None, tenant_id=None, expected_version=None):
        with storage.get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute('SELECT * FROM workmanship_sim_connector_app_pairings WHERE pairing_id=%s AND protocol=%s FOR UPDATE', (pairing_id, PROTOCOL_V2))
            row = cursor.fetchone()
            if not row:
                raise PairingError('pairing_not_found')
            if status == 'cancelled' and (row['owner_user_gid'], row['tenant_gid']) != (user_id, tenant_id):
                raise PairingError('pairing_owner_mismatch')
            if row['status'] not in ('created', 'user_bound') or (expected_version is not None and row['resource_version'] != expected_version):
                raise PairingError('pairing_consumed')
            cursor.execute('UPDATE workmanship_sim_connector_app_pairings SET status=%s,bootstrap_encryption_jwk=%s,'
                'signing_challenge_hash=NULL,activation_challenge_hash=NULL,challenge_consumed_at=%s,cancelled_at=%s,'
                'resource_version=resource_version+1,updated_at=%s WHERE pairing_id=%s AND resource_version=%s',
                (status, '{}', now, now if status == 'cancelled' else None, now, pairing_id, row['resource_version']))
            self._audit(cursor, pairing_id, 'pairing_' + status, now, actor=user_id)
        return self.get_pairing(pairing_id)

    def activate_pairing(self, record, device_id, credential_hash, now):
        with storage.get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute("UPDATE workmanship_sim_connector_app_pairings SET status='activated',device_id=%s,credential_generation=1,"
                'bootstrap_encryption_jwk=%s,activation_challenge_hash=NULL,signing_challenge_hash=NULL,credential_envelope_json=NULL,'
                'activated_at=%s,challenge_consumed_at=%s,resource_version=resource_version+1,updated_at=%s '
                "WHERE pairing_id=%s AND protocol=%s AND resource_version=%s AND status='user_bound' AND expires_at>%s AND challenge_expires_at>%s AND challenge_consumed_at IS NULL",
                (device_id, '{}', now, now, now, record['pairing_id'], PROTOCOL_V2, record['resource_version'], now, now))
            if cursor.rowcount != 1:
                raise PairingError('pairing_consumed')
            cursor.execute('INSERT INTO workmanship_sim_connector_runtime_devices '
                '(device_id,protocol,owner_user_gid,tenant_gid,device_signing_jwk,device_key_id,device_credential_hash,'
                'credential_generation,runtime_generation,runtime_type,status,activated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,1,1,%s,\'active\',%s)',
                (device_id, PROTOCOL_V2, record['owner_user_gid'], record['tenant_gid'], json.dumps(record['device_signing_jwk']),
                 record['device_key_id'], credential_hash, record['runtime_type'], now))
            self._audit(cursor, record['pairing_id'], 'pairing_activated', now, actor=record['owner_user_gid'], device_id=device_id)
