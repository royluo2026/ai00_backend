import pytest

from plugins.craft.craft_backend.capabilities import demo_relation_change as relation


class NoQueries:
    def execute(self, *args):
        raise AssertionError('the already loaded transaction tree must be reused')


def test_holding_reuses_complete_current_transaction_tree():
    info = {
        'ordinary': {'gid': 'ordinary', 'node_type': 'line_process', 'meta': '{}'},
        'leaf': {'gid': 'leaf', 'node_type': 'operation', 'meta': '{"demo_holding":true}'},
        'holding': {'gid': 'holding', 'node_type': 'line_process', 'meta': '{"demo_holding":true}'},
    }
    assert relation._holding_line(NoQueries(), 'clone', info) == 'holding'


def test_missing_holding_in_loaded_tree_still_fails():
    with pytest.raises(relation.CapabilityBusinessError) as error:
        relation._holding_line(NoQueries(), 'clone', {})
    assert error.value.code == 'demo_holding_line_missing'


def test_status_with_canonical_plan_needs_no_unused_station_entity_read(monkeypatch):
    info = {
        'line': {'gid': 'line', 'parent_gid': None, 'node_type': 'line_process', 'title': 'line', 'meta': {}},
        'station': {'gid': 'station', 'parent_gid': 'line', 'node_type': 'station_process', 'level': 2, 'title': 'station'},
        'process': {'gid': 'process', 'parent_gid': 'station', 'node_type': 'process', 'title': 'process'},
        'holding': {'gid': 'holding', 'parent_gid': None, 'node_type': 'line_process', 'meta': {'demo_holding': True}},
    }
    children = {None: ['line', 'holding'], 'line': ['station'], 'station': ['process']}
    plan = {'station_codes': {'station': ['code']}, 'process_codes': {'code': 'process'},
            'process_target_parents': {'code': 'station'}}
    monkeypatch.setattr(relation, '_load_tree', lambda *args: (info, children))
    monkeypatch.setattr(relation, '_relation_plan', lambda *args: plan)
    result = relation._status(NoQueries(), 'clone')
    assert len(result['lines']) == 1
    line = result['lines'][0]
    assert line['connected'] is True and line['processes_connected'] == 1
    assert line['steps'][0]['station_gid'] == 'station'
    assert line['steps'][0]['processes'][0]['entry_gid'] == 'process'


def test_legacy_without_plan_still_reads_station_entities(monkeypatch):
    monkeypatch.setattr(relation, '_load_tree', lambda *args: ({
        'holding': {'gid': 'holding', 'parent_gid': None, 'node_type': 'line_process', 'meta': {'demo_holding': True}},
    }, {}))
    monkeypatch.setattr(relation, '_relation_plan', lambda *args: {})
    with pytest.raises(AssertionError, match='already loaded'):
        relation._status(NoQueries(), 'clone')
