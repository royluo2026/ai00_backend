import pytest

from backend.utils.gid import (
    SnowflakeGID,
    configure_gid_generator,
    gid_to_json,
    machine_id_from_environment,
)


def test_formal_governance_profile_requires_machine_id():
    with pytest.raises(RuntimeError, match="AI00_GID_MACHINE_ID"):
        machine_id_from_environment({"AI00_DEPLOYMENT_PROFILE": "test-governance"})


def test_gid_is_safe_signed_bigint_and_serialized_as_string():
    generator = SnowflakeGID(machine_id=41)
    value = generator.next_id()

    assert 0 < value < 2**63
    assert gid_to_json(value) == str(value)


def test_configured_generators_do_not_share_machine_identity():
    first = configure_gid_generator(7)
    second = configure_gid_generator(8)

    assert first is not second
    assert first.machine_id == 7
    assert second.machine_id == 8


@pytest.mark.parametrize("value", [0, -1, 2**63])
def test_gid_to_json_rejects_values_outside_signed_bigint_range(value):
    with pytest.raises(ValueError, match="gid_out_of_signed_bigint_range"):
        gid_to_json(value)
