"""Exactly one deterministic contract verifier for every mandatory case key."""
import pytest

from backend.capabilities.validation_next import validate_payload
from .support import key, stable_capabilities


DESCRIPTORS = stable_capabilities()


@pytest.mark.parametrize("descriptor", DESCRIPTORS, ids=key)
def test_success_case(descriptor):
    """Offline success means the declared minimal request satisfies the frozen contract."""
    validate_payload(descriptor["input_schema"], descriptor["minimal_input_example"])


@pytest.mark.parametrize("descriptor", DESCRIPTORS, ids=key)
def test_invalid_input_case(descriptor):
    invalid = {**descriptor["minimal_input_example"], "__unknown_acceptance_field__": True}
    with pytest.raises(ValueError):
        validate_payload(descriptor["input_schema"], invalid)


@pytest.mark.parametrize("descriptor", DESCRIPTORS, ids=key)
def test_unauthenticated_case(descriptor):
    assert "authorization_failed" in descriptor["gateway_errors"]


@pytest.mark.parametrize("descriptor", DESCRIPTORS, ids=key)
def test_resource_denied_case(descriptor):
    assert "resource_scope_denied" in descriptor["gateway_errors"]


@pytest.mark.parametrize("descriptor", DESCRIPTORS, ids=key)
def test_output_contract_case(descriptor):
    assert descriptor["output_schema"]["type"] == "object"
    assert descriptor["output_schema"]["additionalProperties"] is False


@pytest.mark.parametrize("descriptor", DESCRIPTORS, ids=key)
def test_consumer_contract_case(descriptor):
    assert descriptor["schema_precision"] == "typed"
    assert descriptor["input_schema"]["additionalProperties"] is False
    assert any(descriptor["exposure"].values())


@pytest.mark.parametrize("descriptor", DESCRIPTORS, ids=key)
def test_version_pin_case(descriptor):
    assert descriptor["invoke"]["catalog_release"] == descriptor["catalog_release"]
    assert descriptor["invoke"]["major_version"] == descriptor["major_version"]
    assert descriptor["schema_hash"].startswith("sha256:")
