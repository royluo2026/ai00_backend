import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plugins.craft.craft_backend.routers import projects


def test_row_to_project_serializes_project_row():
    row = {
        'gid': 'proj-1',
        'name': 'P-2026-A',
        'project_code': 'P',
        'model_year': 2026,
        'suffix': 'A',
        'description': 'desc',
        'status': 'preparing',
        'vehicle_model_gid': 'vm-1',
        'factory_gid': 'fac-1',
        'team_id': 'team-1',
        'owner_gid': 'user-1',
        'owner_name': 'Owner',
        'share_scope': 'team',
        'jph': 12.5,
        'is_deleted': False,
        'is_archived': False,
        'deleted_at': None,
        'archived_at': None,
        'created_at': '2026-07-15 10:00:00',
        'updated_at': '2026-07-15 10:01:00',
    }

    result = projects._row_to_project(row)

    assert result['gid'] == 'proj-1'
    assert result['owner_name'] == 'Owner'
    assert result['factory_gid'] == 'fac-1'
    assert result['created_at'] == '2026-07-15 10:00:00'
    assert result['updated_at'] == '2026-07-15 10:01:00'
