"""Published artifacts must not be forgotten by generic read-only recovery."""
import pytest
from datetime import timedelta
from backend.tests.test_simulation_connector_runtime_v2_sql import database,session,queue,lease,read,NOW
from plugins.simulation.simulation_backend.data.connector_repository import ConnectorRepositoryError


@pytest.mark.parametrize('operation',['teamcenter.model_file.fetch@1','vismockup.view.capture@1'])
def test_artifact_upload_uncertainty_survives_runtime_restart_and_equivalent_retry(database,operation):
    registered=session(database)
    current=queue(database,registered,operation_id=operation,side_effect_classification='read')
    lease(database,registered)
    with database[0]() as conn,conn.cursor() as cur:
        cur.execute("UPDATE workmanship_sim_connector_runtime_plans SET status='outcome_unknown' WHERE plan_id=%s",(current.plan_id,))
    with pytest.raises(ConnectorRepositoryError,match='runtime_plans_unresolved'):
        session(database,now=NOW+timedelta(seconds=61),instance='replacement')
    assert read(database,'runtime_plans')['status']=='outcome_unknown'
    with pytest.raises(ConnectorRepositoryError,match='reconciliation_required'):
        queue(database,registered,idempotency_key='retry-upload',normalized_input_hash=current.normalized_input_hash,operation_id=operation,side_effect_classification='read')
    assert read(database,'runtime_plans')['status']=='outcome_unknown'
