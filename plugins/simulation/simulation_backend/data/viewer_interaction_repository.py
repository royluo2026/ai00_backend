"""Low-frequency source authorization. Never used by a local control click."""
from contextlib import contextmanager
from datetime import timedelta
import uuid
import hashlib
import json

from .connection import get_simulation_conn
from .connector_repository import _utc


class ViewerInteractionRepository:
    def __init__(self, *, connect=None):
        self.connect = connect or get_simulation_conn

    def append_events(self, batch, *, pins, now):
        from backend.contracts.viewer_interaction_v1 import SignedAuditBatch, MAX_AUDIT_BYTES
        from backend.contracts.connector_execution_plan_v2 import canonicalize_v2
        from .connector_repository import SimulationConnectorRepository
        if len(canonicalize_v2(batch)) > MAX_AUDIT_BYTES:
            raise ValueError('interaction_audit_too_large')
        batch = SignedAuditBatch.model_validate(batch)
        if (pins['runtime_type'] != 'electron' or batch.device_id != pins['device_id']
            or batch.runtime_instance_id != pins['runtime_instance_id']):
            raise ValueError('interaction_audit_scope_denied')
        acknowledged = []
        with self.connect() as conn, conn.cursor() as cur:
            runtime = SimulationConnectorRepository._authenticated_runtime(cur, pins['device_id'],
                pins['generation'], pins['runtime_instance_id'], pins['token'], now)
            jwk = runtime['device_signing_jwk']
            if isinstance(jwk, str): jwk = json.loads(jwk)
            if (runtime['runtime_type'] != 'electron' or batch.device_key_id != runtime['device_key_id']
                or not batch.verify_signature(jwk)):
                raise ValueError('interaction_audit_signature_invalid')
            for event in batch.events:
                # No grant-expiry or uploader-runtime equality: a restarted device
                # must be able to flush finalized historical results without replay.
                cur.execute('SELECT g.session_nonce,s.device_id,s.tenant_gid,s.actor_gid '
                    'FROM workmanship_sim_viewer_interaction_grants g '
                    'JOIN workmanship_sim_viewer_source_associations s ON s.source_association_id=g.source_association_id '
                    'WHERE g.grant_id=%s', (event.grant_id,))
                grant = cur.fetchone()
                if (not grant or grant['device_id'] != batch.device_id
                    or grant['tenant_gid'] != runtime['tenant_gid'] or grant['actor_gid'] != runtime['owner_user_gid']
                    or grant['session_nonce'] != event.interaction_id):
                    raise ValueError('interaction_audit_scope_denied')
                self._verify_event_proof(cur, event, grant)
                encoded = canonicalize_v2(event)
                digest = hashlib.sha256(encoded).hexdigest()
                cur.execute('SELECT event_digest FROM workmanship_sim_viewer_interaction_events '
                    'WHERE device_id=%s AND request_id=%s FOR UPDATE', (batch.device_id, event.request_id))
                previous = cur.fetchone()
                if previous and previous['event_digest'] != digest:
                    raise ValueError('interaction_audit_conflict')
                if not previous:
                    cur.execute('INSERT INTO workmanship_sim_viewer_interaction_events '
                        '(device_id,request_id,grant_id,interaction_id,sequence,event_digest,event_json,received_at) '
                        'VALUES (%s,%s,%s,%s,%s,%s,%s,%s)', (batch.device_id, event.request_id, event.grant_id,
                        event.interaction_id, event.sequence, digest, encoded.decode('utf-8'), now))
                if event.request_id not in acknowledged:
                    acknowledged.append(event.request_id)
        # Leaving the transaction commits; an exception never acknowledges data.
        return dict(acknowledged_request_ids=acknowledged)

    @staticmethod
    def _verify_event_proof(cur, event, ownership):
        from backend.contracts.connector_execution_plan_v2 import canonicalize_v2
        from backend.contracts.viewer_interaction_v1 import SignedGrant
        cur.execute('SELECT authorization_operation_id,proof_digest,proof_json '
            'FROM workmanship_sim_viewer_grant_evidence WHERE grant_id=%s', (event.grant_id,))
        row = cur.fetchone()
        try:
            if not row:
                raise ValueError('missing proof')
            proof = json.loads(row['proof_json']) if isinstance(row['proof_json'], str) else row['proof_json']
            signed = SignedGrant.model_validate(proof['signed_grant'])
            if (hashlib.sha256(canonicalize_v2(proof)).hexdigest() != row['proof_digest']
                or proof['signed_grant_digest'] != 'sha256:' + hashlib.sha256(canonicalize_v2(signed)).hexdigest()
                or not row['authorization_operation_id']
                or proof['authorization_operation_id'] != row['authorization_operation_id']
                or signed.grant_id != event.grant_id or signed.session_nonce != event.interaction_id
                or signed.device_id != ownership['device_id'] or signed.tenant_id != ownership['tenant_gid']
                or signed.actor_id != ownership['actor_gid']):
                raise ValueError('proof mismatch')
            operations = {(op.id, op.contract_hash) for op in signed.operations}
            bindings = {(b['operation_id'], b['contract_hash']) for b in proof['operation_bindings']}
            if operations != bindings:
                raise ValueError('operation proof mismatch')
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError('interaction_audit_proof_invalid') from exc
        if not any(operation_id == event.operation_id for operation_id, _ in operations):
            raise ValueError('interaction_audit_operation_forbidden')

    @staticmethod
    def record_source_association(cursor, *, tenant_gid, actor_gid, workspace_gid, document_gid,
                                  device_id, runtime_instance_id, runtime_generation,
                                  document_session, source_revision, now):
        """Internal bind-transaction hook; caller must supply verified open evidence.

        Workspace row must already be locked. No endpoint exposes these pins to a
        renderer, and no historical binding is silently promoted to an association.
        """
        association_id = uuid.uuid4().hex
        cursor.execute('UPDATE workmanship_sim_viewer_source_associations SET active=0 '
                       'WHERE workspace_gid=%s AND active=1', (workspace_gid,))
        cursor.execute('INSERT INTO workmanship_sim_viewer_source_associations '
            '(source_association_id,workspace_gid,document_gid,tenant_gid,actor_gid,device_id,'
            'runtime_instance_id,runtime_generation,document_session,source_revision,active,created_at) '
            'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s)',
            (association_id, workspace_gid, document_gid, tenant_gid, actor_gid, device_id,
             runtime_instance_id, runtime_generation, document_session, source_revision, now))
        return association_id

    @contextmanager
    def authorize_scope(self, context, request, now, *, allocate=True, evidence=None):
        """Keep locks and generation allocation through signing; failures roll back."""
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute('SELECT status FROM workmanship_sim_workspaces WHERE gid=%s '
                'AND tenant_gid=%s AND owner_gid=%s AND removed_at IS NULL FOR UPDATE',
                (request.workspace_gid, context.team_gid, context.user_gid))
            workspace = cur.fetchone()
            if not workspace:
                raise ValueError('interaction_scope_denied')
            cur.execute('SELECT * FROM workmanship_sim_viewer_source_associations '
                'WHERE workspace_gid=%s AND document_gid=%s '
                'AND tenant_gid=%s AND actor_gid=%s AND active=1 FOR UPDATE',
                (request.workspace_gid, request.document_gid,
                 context.team_gid, context.user_gid))
            sources = cur.fetchall()
            source = sources[0] if len(sources) == 1 else None
            if (not source or workspace['status'] == 'frozen'
                or allocate and source['source_association_id'] != request.source_association_id):
                raise ValueError('interaction_binding_stale')
            cur.execute('SELECT * FROM workmanship_sim_connector_runtime_devices WHERE device_id=%s FOR UPDATE',
                        (source['device_id'],))
            runtime = cur.fetchone()
            if (not runtime or runtime['owner_user_gid'] != context.user_gid
                or runtime['tenant_gid'] != context.team_gid or runtime['status'] != 'active'
                or runtime['protocol'] != 'ai00.connector.execution-plan.v2' or runtime['runtime_type'] != 'electron'
                or runtime['current_runtime_instance_id'] != source['runtime_instance_id']
                or runtime['runtime_generation'] != source['runtime_generation'] or not runtime['session_token_hash']
                or not runtime['session_expires_at'] or _utc(runtime['session_expires_at']) <= now
                or not runtime['heartbeat_at'] or not now-timedelta(seconds=120) <= _utc(runtime['heartbeat_at']) <= now):
                raise ValueError('interaction_binding_stale')
            cur.execute('SELECT content_sha256 FROM workmanship_sim_vm_documents WHERE gid=%s '
                'AND workspace_gid=%s AND tenant_gid=%s AND owner_gid=%s '
                "AND document_role='primary' AND source_kind='teamcenter_online' AND removed_at IS NULL FOR UPDATE",
                (request.document_gid, request.workspace_gid, context.team_gid, context.user_gid))
            document = cur.fetchone()
            cur.execute('SELECT document_session FROM workmanship_sim_live_document_bindings WHERE workspace_gid=%s '
                "AND tenant_gid=%s AND actor_gid=%s AND connector_device_id=%s AND state='bound' FOR UPDATE",
                (request.workspace_gid, context.team_gid, context.user_gid, source['device_id']))
            bindings = cur.fetchall()
            if (not document or document['content_sha256'] != source['source_revision']
                or len(bindings) != 1 or bindings[0]['document_session'] != source['document_session']):
                raise ValueError('interaction_binding_stale')
            if not allocate:
                yield dict(source_association_id=source['source_association_id'])
                return
            cur.execute('SELECT grant_id,grant_generation FROM workmanship_sim_viewer_interaction_grants '
                'WHERE source_association_id=%s AND session_nonce=%s ORDER BY grant_generation DESC LIMIT 1 FOR UPDATE',
                (request.source_association_id, request.session_nonce))
            previous = cur.fetchone()
            if (previous and request.prior_grant_id != previous['grant_id']) or (not previous and request.prior_grant_id):
                raise ValueError('interaction_renewal_stale')
            grant_id = uuid.uuid4().hex
            generation = previous['grant_generation'] + 1 if previous else 1
            expires = now + timedelta(seconds=60)
            cur.execute('INSERT INTO workmanship_sim_viewer_interaction_grants '
                '(grant_id,source_association_id,session_nonce,grant_generation,issued_at,expires_at) VALUES (%s,%s,%s,%s,%s,%s)',
                (grant_id, request.source_association_id, request.session_nonce, generation, now, expires))
            yield dict(grant_id=grant_id, grant_generation=generation, session_nonce=request.session_nonce,
                actor_id=context.user_gid, tenant_id=context.team_gid, device_id=source['device_id'],
                runtime_instance_id=source['runtime_instance_id'], workspace_gid=request.workspace_gid,
                document_gid=request.document_gid, source_association_id=request.source_association_id,
                document_session=source['document_session'], issued_at=now.isoformat().replace('+00:00', 'Z'),
                expires_at=expires.isoformat().replace('+00:00', 'Z'))
            from backend.contracts.connector_execution_plan_v2 import canonicalize_v2
            if not evidence or evidence.get('signed_grant', {}).get('grant_id') != grant_id:
                raise ValueError('interaction_grant_evidence_missing')
            encoded = canonicalize_v2(evidence)
            cur.execute('INSERT INTO workmanship_sim_viewer_grant_evidence '
                '(grant_id,authorization_operation_id,proof_digest,proof_json,created_at) VALUES (%s,%s,%s,%s,%s)',
                (grant_id, context.outcome_operation_id, hashlib.sha256(encoded).hexdigest(), encoded.decode('utf-8'), now))
