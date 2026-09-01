import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
REQUIRED_CASES = {
    "success", "invalid_input", "unauthenticated", "resource_denied",
    "output_contract", "consumer_contract", "version_pin",
}


def _documents():
    catalog = json.loads((ROOT / "docs/capabilities/catalog.v2.json").read_text(encoding="utf-8"))
    manifest = json.loads(
        (ROOT / "backend/tests/acceptance/fixtures/case-manifest.json").read_text(encoding="utf-8")
    )
    return catalog, manifest


def test_every_stable_capability_has_all_mandatory_cases():
    catalog, manifest = _documents()
    cases = manifest["capabilities"]

    for descriptor in catalog["capabilities"]:
        if descriptor["lifecycle_status"] != "stable":
            continue
        key = f'{descriptor["id"]}@{descriptor["major_version"]}'
        assert REQUIRED_CASES == set(cases[key]), key
        assert len(set(cases[key].values())) == len(REQUIRED_CASES), key


def test_case_manifest_is_bound_to_exact_catalog_release():
    catalog, manifest = _documents()

    assert manifest["catalog_release"] == catalog["release_id"]
    stable_keys = {
        f'{item["id"]}@{item["major_version"]}'
        for item in catalog["capabilities"]
        if item["lifecycle_status"] == "stable"
    }
    assert set(manifest["capabilities"]) == stable_keys


def test_case_manifest_is_bound_to_verified_catalog_hash():
    from backend.capability_v2.catalog import load_catalog_release

    release = load_catalog_release(
        (ROOT / "docs/governance/capability-catalog-release.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (ROOT / "backend/tests/acceptance/fixtures/case-manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["catalog_release"] == release.release_id
    assert manifest["catalog_hash"] == release.catalog_hash

