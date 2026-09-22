"""Validate the actual local test runner's Registry/Catalog assembly without starting it."""
from pathlib import Path

from backend.capability_v2.bootstrap import build_capability_registry
from backend.capability_v2.catalog import load_catalog_release, build_release
from backend.capability_v2.domain_manifest import load_domain_manifests

ROOT = Path(__file__).resolve().parents[2]


def test_current_provider_and_local_unpublished_catalog_resolve_all_viewer_contracts(monkeypatch):
    registry = build_capability_registry(ROOT)  # Includes frozen Provider hash validation.
    published = load_catalog_release((ROOT / 'docs/governance/capability-catalog-release.json').read_text(encoding='utf-8'))
    extension = load_catalog_release((ROOT / 'docs/governance/test-extension/capability-governance-catalog-release.json').read_text(encoding='utf-8'))
    descriptors = {(d.id, d.major_version): d for d in (*published.descriptors, *extension.descriptors)}
    for item in registry.snapshot():
        descriptor = item.descriptor
        if descriptor is None: continue
        key = descriptor.id, descriptor.major_version
        if descriptor.lifecycle_status == 'experimental':
            descriptors[key] = descriptor
        else:
            descriptors.setdefault(key, descriptor)
    manifests = load_domain_manifests(ROOT / 'backend/capability_v2/official_domains.json')
    release = build_release(descriptors.values(),
        (*[m.artifact for m in manifests.domains], *extension.provider_artifacts))
    candidate = load_catalog_release((ROOT / 'docs/governance/local-viewer-interaction-candidate/catalog.json').read_text(encoding='utf-8'))
    assert len(candidate.descriptors) == 5
    assert candidate.provider_artifacts[0] in release.provider_artifacts
    for descriptor in candidate.descriptors:
        key = descriptor.id, descriptor.major_version
        current = descriptors[key]
        assert current.input_schema == descriptor.input_schema
        assert current.output_schema == descriptor.output_schema
        assert current.capability_version_gid == descriptor.capability_version_gid
        assert current.lifecycle_status == 'experimental'
    assert ('simulation.environment.online_source.live_document.bind', 1) in descriptors
    assert ('simulation.teamcenter.visualization.launch.request', 1) in descriptors
    from types import SimpleNamespace
    from backend.capability_v2 import gateway
    from backend.capability_v2.business_definition import business_definition_hash
    from plugins.simulation.simulation_backend.application.viewer_interaction import catalog_binding
    from plugins.simulation.simulation_backend.capabilities.connector_runtime import DIRECT_VISMOCKUP_OPERATIONS
    monkeypatch.setattr(gateway, 'get_default_gateway', lambda: SimpleNamespace(catalog=lambda _: release))
    authorization = release.descriptor('simulation.viewer.interaction.authorize', 1)
    context = SimpleNamespace(catalog_release=release.release_id, outcome_operation_id='op_startup',
        capability_version_gid=authorization.capability_version_gid, business_definition_hash=business_definition_hash(authorization))
    proof = catalog_binding(context, [dict(id=op, contract_hash=digest) for op, digest in
        (DIRECT_VISMOCKUP_OPERATIONS[name] for name in ('node_visibility', 'node_selection'))])
    assert len(proof['operation_bindings']) == 2
    assert proof['provider_artifact'] == manifests.require('simulation').artifact.model_dump(mode='json')
