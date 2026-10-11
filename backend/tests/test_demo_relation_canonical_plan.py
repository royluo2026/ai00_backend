"""Source-derived rear process plans preserve the real operator anchor."""
from copy import deepcopy

import pytest

from backend.capability_v2.provider_contracts import CapabilityBusinessError
from plugins.craft.craft_backend.capabilities import demo_relation_change as relation


def fixture():
    def node(gid, parent, kind, level, version):
        return dict(gid=gid, parent_gid=parent, node_type=kind, level=level,
                    version_gid=version, sort_order=0, title=kind, meta={})
    source = [node('l', None, 'line_process', 1, 'source'),
              node('s', 'l', 'station_process', 2, 'source'),
              node('a', 's', 'operator_process', 3, 'source'),
              node('p', 'a', 'process', 4, 'source'),
              node('o', 'p', 'operation', 5, 'source'),
              node('d', 's', 'process', 3, 'source')]
    clone = [dict(n, gid='c'+n['gid'], version_gid='clone',
                  parent_gid='c'+n['parent_gid'] if n['parent_gid'] else None,
                  source_entry_gid=n['gid']) for n in source]
    clone.append(dict(node('holding', None, 'line_process', 1, 'clone'),
                      source_entry_gid=None, meta={'demo_holding': True}))
    raw = dict(station_codes={'cs': ['existing-code']}, process_codes={'existing-code': 'cd'},
               operation_part_codes={'co': ['part-code']}, pbom_codes={'part-code': 'part'})
    source_version = dict(gid='source', project_gid='project')
    clone_version = dict(gid='clone', project_gid='project', meta={'demo': {
        'relation_demo': True, 'source_version_gid': 'source', 'relation_plan': raw}})
    return clone_version, source_version, clone, source


def canonical(case):
    return relation._canonical_relation_plan(*case)


def test_missing_operator_process_is_derived_without_mutating_existing_plan():
    case = fixture(); original = deepcopy(case)
    plan = canonical(case)
    assert case == original
    assert plan['station_codes'] == {'cs': ['existing-code', 'DEMO-P-cp']}
    assert plan['process_codes'] == {'existing-code': 'cd', 'DEMO-P-cp': 'cp'}
    assert plan['process_target_parents'] == {'existing-code': 'cs', 'DEMO-P-cp': 'ca'}
    assert plan['operation_part_codes'] == original[0]['meta']['demo']['relation_plan']['operation_part_codes']
    assert plan['pbom_codes'] == {'part-code': 'part'}
    assert canonical(case) == plan


def test_held_process_uses_original_source_parent_not_current_holding():
    case = fixture(); case[2][3]['parent_gid'] = 'holding'; case[2][3]['level'] = 2
    assert canonical(case)['process_target_parents']['DEMO-P-cp'] == 'ca'


def test_observed_operator_child_with_stale_process_level_uses_real_parent_graph():
    case = fixture(); case[3][3]['level'] = 3; case[2][3]['level'] = 3
    original = deepcopy(case)
    plan = canonical(case)
    assert plan['process_target_parents']['DEMO-P-cp'] == 'ca'
    assert plan['process_codes']['existing-code'] == 'cd'
    assert plan['process_target_parents']['existing-code'] == 'cs'
    assert plan['operation_part_codes'] == {'co': ['part-code']}
    assert plan['pbom_codes'] == {'part-code': 'part'}
    assert case == original


@pytest.mark.parametrize('fault', [
    'foreign_project', 'foreign_source_version', 'self_source', 'unmarked',
    'foreign_clone_node', 'foreign_source_node', 'unknown_source_entry', 'duplicate_source_entry',
    'duplicate_node', 'source_cycle', 'clone_cycle', 'missing_parent', 'missing_clone_parent',
    'wrong_node_type', 'unknown_level', 'contradictory_station', 'unknown_code_target', 'numeric_parent',
])
def test_invalid_provenance_or_targets_fail_closed(fault):
    case = fixture(); clone_v, source_v, clone, source = case
    raw = clone_v['meta']['demo']['relation_plan']
    if fault == 'foreign_project': source_v['project_gid'] = 'foreign'
    elif fault == 'foreign_source_version': source_v['gid'] = 'foreign'
    elif fault == 'self_source': clone_v['meta']['demo']['source_version_gid'] = 'clone'
    elif fault == 'unmarked': clone_v['meta']['demo']['relation_demo'] = False
    elif fault == 'foreign_clone_node': clone[3]['version_gid'] = 'foreign'
    elif fault == 'foreign_source_node': source[3]['version_gid'] = 'foreign'
    elif fault == 'unknown_source_entry': clone[3]['source_entry_gid'] = 'foreign'
    elif fault == 'duplicate_source_entry': clone[3]['source_entry_gid'] = 'a'
    elif fault == 'duplicate_node': source.append(deepcopy(source[3]))
    elif fault == 'source_cycle': source[1]['parent_gid'] = 'p'
    elif fault == 'clone_cycle': clone[1]['parent_gid'] = 'cp'
    elif fault == 'missing_parent': source[3]['parent_gid'] = 'missing'
    elif fault == 'missing_clone_parent': clone[:] = [n for n in clone if n['gid'] != 'ca']
    elif fault == 'wrong_node_type': clone[3]['node_type'] = 'operation'
    elif fault == 'unknown_level': source[1]['level'] = None
    elif fault == 'contradictory_station': raw['station_codes'] = {'ca': ['existing-code']}
    elif fault == 'unknown_code_target': raw['process_codes']['existing-code'] = 'unknown'
    elif fault == 'numeric_parent': clone[3]['parent_gid'] = 123
    with pytest.raises(CapabilityBusinessError) as exc:
        canonical(case)
    assert exc.value.code == 'demo_relation_plan_invalid'


def test_canonical_plan_is_bounded():
    case = fixture()
    case[3].extend([dict(case[3][0], gid='extra'+str(i)) for i in range(20001)])
    with pytest.raises(CapabilityBusinessError): canonical(case)


def tree(nodes):
    info = {n['gid']: deepcopy(n) for n in nodes}; children = {}
    for n in info.values(): children.setdefault(n['parent_gid'], []).append(n['gid'])
    return info, children


@pytest.mark.parametrize('operation', ['connect', 'reset', 'status'])
def test_owner_operations_share_one_plan_and_keep_operator_anchor(monkeypatch, operation):
    case = fixture(); plan = canonical(case); info, children = tree(case[2]); plans = []
    # Begin held; connect restores only process. Reset begins connected.
    if operation == 'connect':
        children['ca'].remove('cp'); children['holding'] = ['cp']
        info['cp']['parent_gid'] = 'holding'; info['cp']['level'] = 2
    monkeypatch.setattr(relation, '_load_tree', lambda *args: (info, children))
    monkeypatch.setattr(relation, '_holding_line', lambda *args: 'holding')
    def load_plan(*args): plans.append(1); return plan
    monkeypatch.setattr(relation, '_relation_plan', load_plan)
    monkeypatch.setattr(relation, '_entity_links', lambda *args: {})
    monkeypatch.setattr(relation, '_pbom_by_demo_code', lambda *args: {})
    monkeypatch.setattr(relation, '_existing_operation_part_links', lambda *args: {})
    flushed = []
    monkeypatch.setattr(relation._MovePlanner, 'flush', lambda self, cur: flushed.extend(self.moves))
    class Cursor:
        rowcount = 0
        def execute(self, *args): pass
        def executemany(self, *args): pass
    result = relation._status(Cursor(), 'clone') if operation == 'status' else getattr(relation, '_'+operation)(Cursor(), 'clone', 'cl')
    assert len(plans) == 1
    assert info['ca']['parent_gid'] == 'cs'
    if operation == 'connect':
        assert info['cp']['parent_gid'] == 'ca' and info['cp']['level'] == 4
        assert result['steps'][0]['processes'][1]['entry_gid'] == 'cp'
        assert result['processes_moved'] == 1
        assert result['operations'] == 1
    elif operation == 'reset':
        assert info['cp']['parent_gid'] == 'holding'
        assert result['processes_moved'] == 2
    else:
        assert result['lines'][0]['processes_connected'] == 2
    assert all(move[0] != 'ca' for move in flushed)


def test_ordinary_no_source_plan_does_not_read_source_tree():
    class Cursor:
        calls = []
        def execute(self, sql, params): self.calls.append((sql, params))
        def fetchone(self): return {'gid': 'ordinary', 'meta': {'demo': {'relation_demo': True}}}
        def fetchall(self): raise AssertionError('ordinary W10 must not load a source tree')
    cur = Cursor()
    assert relation._relation_plan(cur, 'ordinary') == {}
    assert len(cur.calls) == 1


def test_only_needed_source_skeleton_is_read_once_and_plan_helpers_reuse_it():
    case = fixture(); clone_v, source_v, clone, source = case
    source = [n for n in source if n['node_type'] in relation._PLAN_NODE_TYPES]
    class Cursor:
        def __init__(self): self.calls = []; self.rows = None
        def execute(self, sql, params):
            self.calls.append((sql, params))
            if 'bop_versions' in sql: self.rows = clone_v if params == ('clone',) else source_v
            else:
                assert params == ('source',)
                assert "node_type IN ('line_process','station_process','operator_process','process')" in sql
                assert 'LIMIT 20001' in sql
                self.rows = source
        def fetchone(self): return self.rows
        def fetchall(self): return self.rows
    cur = Cursor(); info, _ = tree(clone)
    plan = relation._relation_plan(cur, 'clone', info)
    assert len(cur.calls) == 3
    assert relation._station_exts(cur, {}, 'clone', plan) == plan['station_codes']
    assert relation._steps_exts(cur, {}, 'clone', plan) == plan['operation_part_codes']
    assert relation._process_by_code(cur, 'clone', plan) == plan['process_codes']
    assert len(cur.calls) == 3


def test_foreign_source_version_rejected_before_source_nodes_are_read():
    case = fixture(); case[1]['project_gid'] = 'foreign'
    class Cursor:
        def __init__(self): self.calls = 0
        def execute(self, sql, params): self.calls += 1
        def fetchone(self): return case[self.calls - 1]
        def fetchall(self): raise AssertionError('foreign source must not be read')
    cur = Cursor()
    with pytest.raises(CapabilityBusinessError): relation._relation_plan(cur, 'clone', tree(case[2])[0])
    assert cur.calls == 2


@pytest.mark.parametrize('rear_count', [224, 98])
def test_observed_rear_counts_are_real_processes_and_existing_eighteen_line_codes_are_preserved(rear_count):
    case = fixture(); clone_v, _, clone, source = case
    raw = clone_v['meta']['demo']['relation_plan']
    # Eighteen previously planned line/station/direct-process groups.
    for i in range(1, 18):
        for template, gid, parent in [(source[0], 'l'+str(i), None),
                                      (source[1], 's'+str(i), 'l'+str(i)),
                                      (source[5], 'd'+str(i), 's'+str(i))]:
            n = dict(template, gid=gid, parent_gid=parent); source.append(n)
            clone.append(dict(n, gid='c'+gid, version_gid='clone',
                              parent_gid='c'+parent if parent else None, source_entry_gid=gid))
        raw['station_codes']['cs'+str(i)] = ['code'+str(i)]
        raw['process_codes']['code'+str(i)] = 'cd'+str(i)
    for i in range(1, rear_count):
        n = dict(source[3], gid='p'+str(i)); source.append(n)
        clone.append(dict(n, gid='c'+n['gid'], version_gid='clone', parent_gid='ca', source_entry_gid=n['gid']))
    original = deepcopy(raw)
    plan = canonical(case)
    assert len(plan['process_codes']) == 18 + rear_count
    for code, gid in original['process_codes'].items():
        assert plan['process_codes'][code] == gid
        assert plan['process_target_parents'][code] == 'cs' + (code[4:] if code.startswith('code') else '')
    assert sum(parent == 'ca' for parent in plan['process_target_parents'].values()) == rear_count
    assert raw == original
