from backend.tests.support.desktop_gateway_matrix import DesktopGatewayMatrix
from backend.tests.support.desktop_round5_fixtures import execute_base_matrix
from backend.tests.support.desktop_round5_agent_fixtures import execute_agent_matrix
from backend.tests.support.desktop_round5_project_fixtures import execute_project_matrix
from backend.tests.test_desktop_round5_exchange import execute_file_matrix
from backend.tests.test_desktop_round5_remaining import execute_remaining_matrix


def execute_gateway_matrix():
    matrix=DesktopGatewayMatrix();groups={}
    for group,run in (('base',execute_base_matrix),('agent',execute_agent_matrix),('project',execute_project_matrix),('file',execute_file_matrix),('remaining',execute_remaining_matrix)):
        before=len(matrix.rows)
        result=run(matrix)
        rows=result[0] if isinstance(result,tuple) else result
        assert len(rows)==len(matrix.rows)-before
        groups[group]=[{**row,**proof} for row,proof in zip(rows,matrix.rows[before:],strict=True)]
    return groups


def test_every_round5_owner_handler_through_gateway_policy_confirmation_and_schema():
    rows=[row for group in execute_gateway_matrix().values() for row in group]
    assert len(rows)==74
    assert len({(row['id'],row['version']) for row in rows})==73
    assert all(row['gateway_result']['ok'] for row in rows)
    assert sum(row['confirmation_exercised'] for row in rows)>25
