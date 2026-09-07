from types import SimpleNamespace
from unittest.mock import patch
import pytest
from backend.capability_v2.provider_contracts import CapabilityBusinessError
from backend.tests.support.desktop_round5_project_fixtures import execute_project_matrix, Database
from plugins.project_management.project_management_backend.infrastructure import desktop_repository as repository


def test_real_approval_lifecycle_notification_replay_and_all_desktop_handlers():
    rows,database=execute_project_matrix()
    assert len({row['id'] for row in rows})==10
    assert len(database.notifications)==2
    assert database.commits>=8


@pytest.mark.parametrize('user,revision,code',[('intruder',1,'permission_denied'),('reviewer',2,'version_conflict')])
def test_approval_rejects_wrong_participant_and_revision_without_state_change(user,revision,code):
    database=Database()
    database.orders['order']={'gid':'order','applicant_gid':'applicant','reviewer_gid':'reviewer','team_gid':'team','status':'in_review','revision':1,'opinions':[]}
    ctx=SimpleNamespace(user_gid=user,team_gid='team',active_roles=('member',),idempotency_key='fixture')
    with patch.object(repository,'get_project_management_conn',return_value=database):
        with pytest.raises(CapabilityBusinessError) as caught:
            repository.transition('project.approval.order.approve','approve',{'order_gid':'order','expected_revision':revision},ctx)
    assert caught.value.code==code
    assert database.orders['order']['status']=='in_review'
    assert not database.notifications and database.rollbacks==1
