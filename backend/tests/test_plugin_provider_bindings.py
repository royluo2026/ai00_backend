"""Synthetic contracts only: these fixtures are not governance approvals."""
from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from backend.plugin_platform.manifest import ManifestError, parse_manifest
from backend.tests.test_plugin_platform_next import package_bytes, release


def provider_manifest():
    value = release(package_bytes())
    value.update(schema_version="2.1", provides=[{
        "id": "acme.ai00.layout.generate", "major": 1,
        "owner_domain": "acme.ai00", "module": "provider.mjs", "export": "generate",
        "result": "json",
    }])
    return value


def test_old_consumer_manifest_unchanged():
    value = release(package_bytes())
    assert "provides" not in parse_manifest(value).model_dump()


def test_versioned_provider_declaration():
    manifest = parse_manifest(provider_manifest())
    assert manifest.provides[0].module == "provider.mjs"
    assert manifest.provides[0].export == "generate"


@pytest.mark.parametrize("patch", [
    {"module": "../escape.mjs"}, {"module": "C:/escape.mjs"},
    {"module": "https://evil.invalid/a.mjs"}, {"module": "a%2fm.mjs"},
    {"module": "a\\m.mjs"}, {"module": "a.js"}, {"module": "a//m.mjs"},
    {"module": "a/./m.mjs"}, {"export": "constructor"},
    {"id": "base.secret.read"}, {"owner_domain": "base"},
])
def test_provider_declaration_rejects_unsafe_contract(patch):
    value = provider_manifest()
    value["provides"][0].update(patch)
    with pytest.raises(ManifestError):
        parse_manifest(value)


def test_duplicate_and_legacy_provider_declarations_rejected():
    value = provider_manifest()
    value["provides"].append(deepcopy(value["provides"][0]))
    with pytest.raises(ManifestError):
        parse_manifest(value)


def binding_fixture():
    from backend.capability_v2.business_definition import business_definition_hash
    from backend.capability_v2.catalog import build_release, ProviderArtifact
    from backend.capability_v2.contracts import CapabilityDescriptorV2
    manifest = parse_manifest(provider_manifest())
    descriptor = CapabilityDescriptorV2(
        id="acme.ai00.layout.generate", major_version=1, owner_domain="acme.ai00",
        lifecycle_status="stable", title="Fixture", description="Synthetic layout computation",
        use_when="Compute a fixture layout", do_not_use_when="Not a real approved provider",
        business_effect="Produce a deterministic arrangement of the supplied fixture lines.",
        business_acceptance_criteria=("Every supplied line has bounds.",),
        no_business_invariant_reason="Pure fixture for platform binding verification.",
        execution_mode="local", exposure={"plugin":True}, exposure_policy_source="provider_explicit",
        automation_level="A1", authorization_policy="authenticated",
        input_schema={"type":"object","properties":{},"additionalProperties":False},
        output_schema={"type":"object","properties":{},"additionalProperties":False},
        schema_hash="sha256:"+"1"*64, capability_version_gid="fixture-local-cap-version",
        provider_ref="acme.ai00.hello/provider.mjs#generate",
    )
    release = build_release([descriptor],[ProviderArtifact(plugin_id=manifest.plugin_id,module="local.javascript",version=manifest.version,artifact_hash="sha256:"+manifest.artifact.sha256)])
    definition_hash = business_definition_hash(descriptor)
    scanned = NS(capability_id=descriptor.id,major_version=1,owner_domain=descriptor.owner_domain,
        descriptor_hash="fixture-descriptor-hash",provider_hash="sha256:"+manifest.artifact.sha256,
        descriptor={**descriptor.model_dump(mode="json"),"business_definition_hash":definition_hash})
    entry = NS(capability_id=descriptor.id,major_version=1,owner_domain=descriptor.owner_domain,
        descriptor_hash=scanned.descriptor_hash,capability_version_gid=101)
    review = NS(decision="approved",reviewer_role="super_admin",definition_hash=definition_hash,
        capability_version_gid=101,evidence_snapshot_gid=201)
    snapshot = NS(snapshot_gid=201,entries=[entry],document=NS(scan_status="completed",
        product_release_id=release.release_id,catalog_hash=release.catalog_hash,scan_findings=[],capabilities=[scanned]))
    store = NS(persistent=True,latest_snapshot=lambda:snapshot,get_findings=lambda _gid:[],
        current_business_review=lambda _gid,_hash:review)
    return manifest,release,store,snapshot,review


def test_exact_detached_binding_uses_distinct_public_and_internal_identity():
    from backend.plugin_platform.provider_bindings import resolve_provider_bindings
    manifest,release,store,_,_ = binding_fixture()
    binding, = resolve_provider_bindings(manifest,release,store)
    assert binding.descriptor.capability_version_gid == "fixture-local-cap-version"
    assert binding.governance_version_gid == 101
    assert binding.artifact_sha256 == manifest.artifact.sha256


@pytest.mark.parametrize("tamper", ["memory","snapshot","artifact","hash","gid","owner","revision","review","review_snapshot","findings"])
def test_governance_binding_fails_closed(tamper):
    from backend.plugin_platform.provider_bindings import ProviderBindingError, resolve_provider_bindings
    manifest,release,store,snapshot,review = binding_fixture()
    scanned=snapshot.document.capabilities[0]
    if tamper=="memory": store.persistent=False
    if tamper=="snapshot": snapshot.document.catalog_hash="sha256:"+"0"*64
    if tamper=="artifact": scanned.provider_hash="sha256:"+"0"*64
    if tamper=="hash": scanned.descriptor["business_definition_hash"]="sha256:"+"0"*64
    if tamper=="gid": scanned.descriptor["capability_version_gid"]="wrong-public-gid"
    if tamper=="owner": snapshot.entries[0].owner_domain="other"
    if tamper=="revision": scanned.descriptor["timeout_seconds"]=20
    if tamper=="review": review.decision="rejected"
    if tamper=="review_snapshot": review.evidence_snapshot_gid=200
    if tamper=="findings": store.get_findings=lambda _gid:[{"severity":"blocking","code":"fixture_blocker"}]
    with pytest.raises(ProviderBindingError): resolve_provider_bindings(manifest,release,store)
    value = provider_manifest()
    value["schema_version"] = "2.0"
    with pytest.raises(ManifestError):
        parse_manifest(value)
