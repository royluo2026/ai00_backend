"""Knowledge collections reject overflow without hiding review information."""
import pytest
from contextlib import nullcontext

from backend.capability_v2.provider_contracts import CapabilityBusinessError
from backend.capabilities.registry_next import CapabilityRegistry
from plugins.knowledge.knowledge_backend import feishu_markdown as converter
from plugins.knowledge.knowledge_backend import source_merge
from plugins.knowledge.knowledge_backend.capabilities.feishu_catalog_next import register_feishu_catalog_capabilities
from plugins.knowledge.knowledge_backend.capabilities.feishu_source_next import register_feishu_source_capabilities
from plugins.knowledge.knowledge_backend.capabilities.feishu_import_next import register_feishu_import_capabilities
from plugins.knowledge.knowledge_backend.capabilities import feishu_catalog_next as catalog
from plugins.knowledge.knowledge_backend.capabilities import feishu_source_next as source
from backend.capability_v2.provider_contracts import CapabilityContext


def test_stable_collection_contracts_have_finite_runtime_limits():
    registry = CapabilityRegistry()
    for register in (register_feishu_catalog_capabilities, register_feishu_source_capabilities, register_feishu_import_capabilities):
        register(registry)
    schemas = {entry.spec.id: entry.descriptor.output_schema for entry in registry.snapshot()}
    for capability, field, limit in (
        ('knowledge.source.catalog.list', 'items', 500),
        ('knowledge.source.catalog.sync', 'errors', 10000),
        ('knowledge.source.import.preview', 'conflicts', 1000),
        ('knowledge.source.pull', 'anchors', 20000),
        ('knowledge.source.snapshot.get', 'diagnostics', 20000),
    ):
        assert schemas[capability]['properties'][field].get('maxItems') == limit
    assert schemas['knowledge.source.pull']['properties']['anchors']['items']['properties']['path'].get('maxItems') == 100


def _blocks(children, elements=None):
    return [{'block_id': 'root', 'block_type': 1, 'children': children},
            {'block_id': 'p', 'block_type': 2, 'text': {'elements': elements or []}}]


def test_conversion_rejects_diagnostics_overflow_instead_of_truncating():
    result = converter.convert_blocks(_blocks(['p'], [{}] * 20000))
    assert len(result.diagnostics) == 20000
    with pytest.raises(CapabilityBusinessError, match='diagnostics'):
        converter.convert_blocks(_blocks(['p'], [{}] * 20001))


def test_conversion_rejects_anchor_expansion_and_cycles():
    with pytest.raises(CapabilityBusinessError, match='anchor'):
        converter.convert_blocks(_blocks(['p'] * 20001))
    blocks = _blocks(['p'])
    blocks[1]['children'] = ['p']
    with pytest.raises(CapabilityBusinessError, match='cycle'):
        converter.convert_blocks(blocks)


def test_conversion_path_depth_is_bounded():
    blocks = [{'block_id': 'root', 'block_type': 1, 'children': ['0']}]
    blocks += [{'block_id': str(i), 'block_type': 23, 'children': [str(i + 1)] if i < 100 else []} for i in range(101)]
    at_limit = converter.convert_blocks(blocks[:-2] + [{**blocks[-2], 'children': []}])
    assert max(len(anchor['path']) for anchor in at_limit.anchors) == 100
    with pytest.raises(CapabilityBusinessError, match='path'):
        converter.convert_blocks(blocks)


def test_merge_rejects_overflow_instead_of_hiding_conflicts():
    def content(prefix, count):
        return ''.join(f'{prefix}{i}\nkeep{i}\n' for i in range(count))
    result = source_merge.merge_markdown(content('base', 1000), content('source', 1000), content('local', 1000))
    assert len(result.conflicts) == 1000
    with pytest.raises(CapabilityBusinessError, match='conflict'):
        source_merge.merge_markdown(content('base', 1001), content('source', 1001), content('local', 1001))


class ReadCursor:
    def __init__(self, row):
        self.row = row
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        return False
    def execute(self, sql, params=()):
        assert sql.startswith('SELECT'), 'boundary rejection must precede database writes'
    def fetchone(self):
        return self.row


def _read_connection(monkeypatch, module, row):
    cursor = ReadCursor(row)
    class Connection:
        def cursor(self):
            return cursor
    monkeypatch.setattr(module, 'get_knowledge_conn', lambda: nullcontext(Connection()))
    monkeypatch.setattr(module, '_tenant', lambda _: 'tenant')
    monkeypatch.setattr(module, '_trusted_profile' if module is source else '_require_superadmin', lambda *_: None)


def test_catalog_bitable_overflow_is_a_domain_error_before_writes(monkeypatch):
    _read_connection(monkeypatch, catalog, {'source_url': 'url', 'app_token': 'app', 'table_id': 'table'})
    monkeypatch.setattr(catalog, 'parse_catalog_url', lambda _: ('bitable', 'app', 'table'))
    monkeypatch.setattr(catalog.feishu_service, 'list_bitable_records', lambda *_: {'items': [{}] * 10001, 'has_more': False})
    with pytest.raises(CapabilityBusinessError, match='catalog'):
        catalog.sync_catalog({}, CapabilityContext(user_gid='user', team_gid='tenant'))


def test_sheet_catalog_uses_same_record_limit_before_writes(monkeypatch):
    _read_connection(monkeypatch, catalog, {'source_url': 'url', 'app_token': 'app', 'table_id': 'table'})
    monkeypatch.setattr(catalog, 'parse_catalog_url', lambda _: ('sheet', 'app', 'table'))
    monkeypatch.setattr(catalog, 'user_credential', lambda _: 'credential')
    monkeypatch.setattr(catalog.feishu_service, 'list_spreadsheet_sheets', lambda *_args, **_kwargs: [
        {'title': '总表', 'sheet_id': 'sheet', 'grid_properties': {'row_count': 10001}}])
    with pytest.raises(CapabilityBusinessError, match='catalog'):
        catalog.sync_catalog({}, CapabilityContext(user_gid='user', team_gid='tenant'))


def test_pull_block_overflow_is_a_domain_error_before_writes(monkeypatch):
    _read_connection(monkeypatch, source, {'gid': 'source', 'document_url': 'url', 'linked_document_gid': None})
    monkeypatch.setattr(source, '_require_superadmin', lambda *_: None)
    monkeypatch.setattr(source, 'user_credential', lambda _: 'credential')
    def overflow(*_args, **_kwargs):
        raise ValueError('Feishu document block limit exceeded')
    monkeypatch.setattr(source, 'read_document_blocks', overflow)
    with pytest.raises(CapabilityBusinessError, match='block'):
        source.pull_source({'source_gid': 'source'}, CapabilityContext(user_gid='user', team_gid='tenant'))


@pytest.mark.parametrize('field,value', [
    ('anchors_json', [{'path': []}] * 20001),
    ('anchors_json', [{'path': [0] * 101}]),
    ('diagnostics_json', [{}] * 20001),
])
def test_stored_snapshot_cannot_exceed_declared_collections(monkeypatch, field, value):
    row = {'anchors_json': [], 'diagnostics_json': [], 'object_key': 'object', 'content_sha256': 'hash'}
    row[field] = value
    _read_connection(monkeypatch, source, row)
    monkeypatch.setattr(source, 'get_immutable', lambda *_: b'body')
    with pytest.raises(CapabilityBusinessError):
        source.get_source_snapshot({'snapshot_gid': 'snapshot'}, CapabilityContext(user_gid='user', team_gid='tenant'))
