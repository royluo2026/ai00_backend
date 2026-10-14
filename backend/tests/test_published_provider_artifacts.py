from pathlib import Path

from backend.capability_v2.bootstrap import build_capability_registry
from backend.scripts.audit_official_domain_artifacts import audit_official_domain_artifacts

ROOT = Path(__file__).resolve().parents[2]


def test_published_manifest_matches_every_provider_artifact():
    report = audit_official_domain_artifacts(ROOT, ROOT / 'backend/capability_v2/official_domains.json')
    assert report['clean'], [(item['domain'], item['status']) for item in report['domains'] if item['status'] != 'match']


def test_published_official_registry_bootstraps_without_database_or_test_overrides():
    registry = build_capability_registry(ROOT)
    assert registry.keys()
    assert registry.get('base.runtime.data_environment.get', 1) is not None


def test_published_catalog_binds_all_runtime_providers(monkeypatch):
    from backend.capability_v2 import gateway

    monkeypatch.setattr(gateway, '_default_gateway', None)
    registry = build_capability_registry(ROOT)
    service = gateway.configure_default_gateway(
        registry,
        release_path=ROOT / 'docs/governance/capability-catalog-release.json',
    )
    assert service is not None


def test_container_build_checks_provider_artifacts_before_runtime():
    dockerfile = (ROOT / 'backend/Dockerfile').read_text(encoding='utf-8')
    assert 'RUN python -m backend.scripts.audit_official_domain_artifacts' in dockerfile
    assert 'configure_default_gateway(build_capability_registry())' in dockerfile
    assert 'RUN ENV_FILE= AI00_DEPLOY_PROFILE=production python -c' in dockerfile
    assert dockerfile.index('pip install -r backend/requirements.txt') < dockerfile.index('RUN python -m backend.scripts.audit_official_domain_artifacts')
