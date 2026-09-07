import pytest

from backend.capabilities.validation_next import validate_payload
from backend.capability_v2.descriptor_adapter import _closed_schema
from plugins.knowledge.knowledge_backend.capabilities.reviewed import SCHEMAS
from plugins.knowledge.knowledge_backend.ids import new_knowledge_id


@pytest.mark.parametrize(('kind', 'prefix'), [('folder', 'knf_'), ('item', 'kni_')])
def test_legacy_hub_resources_have_domain_owned_identifiers(kind, prefix):
    assert new_knowledge_id(kind).startswith(prefix)


@pytest.mark.parametrize('updates', [False, True])
@pytest.mark.parametrize('reference', [
    {'path': 'std_op_lib/std_op_lib.html'},
    {'path': 'std_op_lib/std_op_lib.html', 'label': '标准工序库 (GBOP)'},
])
def test_site_page_reference_survives_v2_contract_conversion(updates, reference):
    arguments = SCHEMAS['knowledge.hub.change.apply']['properties']['arguments']
    schema = _closed_schema(arguments)
    payload = {'site_ref': reference}
    if updates:
        payload = {'gid': '123', 'updates': payload}
    validate_payload(schema, payload)


def test_site_page_reference_still_rejects_unknown_fields():
    arguments = SCHEMAS['knowledge.hub.change.apply']['properties']['arguments']
    with pytest.raises(ValueError, match='unknown field'):
        validate_payload(_closed_schema(arguments), {'site_ref': {'path': 'gbop/index.html', 'unexpected': True}})


def test_shipped_catalog_resolves_knowledge_reads_and_gbop_creation():
    from pathlib import Path
    from backend.capability_v2.bootstrap import get_capability_registry
    from backend.capability_v2.catalog import CatalogResolver, load_catalog_release
    from backend.capability_v2.gateway import InMemoryCatalogStore

    root = Path(__file__).resolve().parents[2]
    release = load_catalog_release((root / 'docs/governance/capability-catalog-release.json').read_text(encoding='utf-8'))
    store = InMemoryCatalogStore()
    store.publish(release)
    resolver = CatalogResolver(store, get_capability_registry())
    for capability in ['knowledge.hub.read.atomic.items_list', 'knowledge.hub.read.atomic.folders_list', 'knowledge.hub.change.apply.atomic.items_create']:
        resolver.resolve(release.release_id, capability, 1)
        descriptor = resolver.descriptor(release.release_id, capability, 1)
        payload = {'scope_type': 'personal'}
        if capability.endswith('items_create'):
            payload.update(item_type='site_page', title='GBOP', site_ref={'path': 'std_op_lib/std_op_lib.html'})
        validate_payload(dict(descriptor.input_schema), payload)
