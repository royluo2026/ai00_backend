from pathlib import Path

TEST_FILE = Path(__file__).resolve().parent / 'test_schema_migration_mock.py'


def test_mock_conn_seed_support_present():
    text = TEST_FILE.read_text(encoding='utf-8')
    assert 'proj_tasks_display_seq' in text
    assert 'proj_issues_display_seq' in text
    assert 'fetchone.side_effect' in text
