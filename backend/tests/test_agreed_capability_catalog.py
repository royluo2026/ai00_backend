from pathlib import Path

from backend.capabilities.agreed_catalog import (
    APPROVED_CAPABILITY_IDS,
    FORBIDDEN_INTERNAL_PROTOCOL_IDS,
)
from backend.capabilities.registry_next import CapabilityRegistry
from backend.capability_v2.bootstrap import get_capability_registry
from plugins.craft.craft_backend.capabilities import register_capabilities


def test_catalog_never_publishes_forbidden_internal_protocol_ids():
    craft = CapabilityRegistry(); register_capabilities(craft)
    implemented = {spec.id for spec in get_capability_registry().list()} | {spec.id for spec in craft.list()}
    assert implemented.isdisjoint(FORBIDDEN_INTERNAL_PROTOCOL_IDS)


def test_migrated_craft_is_plugin_callable():
    craft = CapabilityRegistry(); register_capabilities(craft)
    craft_specs = craft.list()
    assert craft_specs
    assert all(spec.plugin_callable is True for spec in craft_specs)


def test_agent_adapter_uses_bounded_context_and_never_advertises_discovery_tool():
    root = Path(__file__).resolve().parents[2]
    source = (root / "plugins/agent/agent_backend/ai_assistant/catalog_tools.py").read_text(encoding="utf-8")
    assert "release.descriptors" in source
    assert "find_capabilities" not in source
    assert "database.sql.execute" not in source


def test_agent_bop_and_ontology_reads_use_governed_capabilities():
    root = Path(__file__).resolve().parents[2]
    adapter = (root / "plugins/agent/agent_backend/ai_assistant/catalog_tools.py").read_text(encoding="utf-8")
    assert "DomainInvocation" in adapter
    assert "self.client.invoke" in adapter
    assert not any((root / "plugins/agent/agent_backend/ai_assistant/tool_handlers").rglob("*.py"))
