from pathlib import Path

import pytest

from backend.capabilities.models_next import CapabilityBusinessError, CapabilityContext
from plugins.craft.craft_backend.capabilities.demo_relation_change import apply_demo_relation_change


CAPABILITY = Path("plugins/craft/craft_backend/capabilities/demo_relation_change.py")
INIT = Path("plugins/craft/craft_backend/capabilities/__init__.py")
CONTRACTS = Path("plugins/craft/craft_backend/capabilities/contracts.py")


def test_demo_relation_capability_registered_and_contracted() -> None:
    init_source = INIT.read_text(encoding="utf-8")
    assert "register_demo_relation_change_capability(native)" in init_source
    contracts_source = CONTRACTS.read_text(encoding="utf-8")
    assert 'INPUT_SCHEMAS[("craft.bop.demo.relation.change.apply", 1)]' in contracts_source
    assert 'OUTPUT_SCHEMAS[("craft.bop.demo.relation.change.apply", 1)]' in contracts_source


def test_demo_relation_requires_super_admin_server_side() -> None:
    source = CAPABILITY.read_text(encoding="utf-8")
    assert "demo_super_admin_required" in source
    assert "active_roles" in source


def test_demo_relation_validates_operation_before_io() -> None:
    context = CapabilityContext(user_gid="u1", active_roles=("super_admin",))
    with pytest.raises(ValueError, match="operation must be one of"):
        apply_demo_relation_change({"operation": "preview", "bop_gid": "b1"}, context)


def test_demo_relation_rejects_non_super_admin_before_io() -> None:
    context = CapabilityContext(user_gid="u1", active_roles=("member",))
    with pytest.raises(CapabilityBusinessError) as exc_info:
        apply_demo_relation_change({"operation": "connect", "bop_gid": "b1"}, context)
    assert exc_info.value.code == "demo_super_admin_required"


def test_demo_relation_requires_bop_gid_before_io() -> None:
    context = CapabilityContext(user_gid="u1", active_roles=("super_admin",))
    with pytest.raises(ValueError, match="bop_gid is required"):
        apply_demo_relation_change({"operation": "connect"}, context)

