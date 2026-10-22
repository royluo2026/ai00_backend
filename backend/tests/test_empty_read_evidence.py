"""Completed empty searches must satisfy required evidence without invented rows."""
from contextlib import contextmanager
from unittest.mock import Mock

import pytest

from backend.capabilities.models_next import CapabilityContext
from plugins.simulation.simulation_backend.capabilities import models


def test_empty_knowledge_search_has_scoped_query_evidence(monkeypatch):
    from plugins.knowledge.knowledge_backend.capabilities import knowledge_documents_next as documents
    from plugins.knowledge.knowledge_backend.data import connection

    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    cursor.fetchall.return_value = []
    conn = Mock()
    conn.cursor.return_value = cursor

    @contextmanager
    def connect():
        yield conn

    monkeypatch.setattr(connection, 'get_knowledge_conn', connect)
    result = documents.search_documents({'query': 'absent', 'limit': 1}, CapabilityContext(user_gid='u', team_gid='t'))
    assert result.data == {'items': [], 'total': 0, 'query': 'absent'}
    assert result.evidence
    assert result.evidence[0].metadata['returned_count'] == 0
    assert result.evidence[0].metadata['tenant_gid'] == 't'
    assert result.evidence[0].digest.startswith('sha256:')
    assert cursor.execute.call_count == 1


@pytest.mark.parametrize('name', ['search_parameter_sets', 'search_profiles', 'list_environments', 'search_runs'])
def test_simulation_empty_reads_include_scope_bound_result_evidence(monkeypatch, name):
    repository = Mock()
    getattr(repository, name).return_value = []
    monkeypatch.setattr(models, 'repository', repository)
    read = getattr(models, name)
    context = CapabilityContext(user_gid='u', team_gid='t')
    result = read({'limit': 1}, context)
    assert result.data['items'] == []
    assert result.data['total'] == 0
    assert result.evidence
    assert result.evidence[0].metadata['returned_count'] == 0
    assert result.evidence[0].digest == read({'limit': 1}, context).evidence[0].digest
    assert result.evidence[0].digest != read({'limit': 1}, CapabilityContext(user_gid='other', team_gid='t')).evidence[0].digest


def test_failed_simulation_query_does_not_create_success_evidence(monkeypatch):
    repository = Mock()
    repository.list_environments.side_effect = RuntimeError('database unavailable')
    monkeypatch.setattr(models, 'repository', repository)
    with pytest.raises(RuntimeError, match='database unavailable'):
        models.list_environments({}, CapabilityContext(user_gid='u'))


def test_simulation_environment_read_and_archive_keep_record_and_scoped_evidence(monkeypatch):
    repository = Mock()
    row = {'environment_id': 'env-1', 'name': 'Line', 'status': 'draft', 'source': {}}
    repository.get_environment.return_value = row
    repository.archive_environment.return_value = {**row, 'status': 'archived'}
    monkeypatch.setattr(models, 'repository', repository)
    context = CapabilityContext(user_gid='u', team_gid='t')
    found = models.get_environment({'environment_id': 'env-1'}, context)
    archived = models.archive_environment({'environment_id': 'env-1'}, context)
    assert found.data == row
    assert archived.data == {**row, 'status': 'archived'}
    assert found.evidence[0].reference == archived.evidence[0].reference == 'simulation://environment/env-1'
    assert found.evidence[0].digest != archived.evidence[0].digest
