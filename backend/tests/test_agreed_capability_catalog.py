from pathlib import Path

from backend.capabilities.agreed_catalog import (
    AGREED_WAVE_PREFIXES,
    APPROVED_CAPABILITY_IDS,
    FORBIDDEN_INTERNAL_PROTOCOL_IDS,
)
from backend.capabilities.registry_next import CapabilityRegistry, capability_registry
from plugins.craft.craft_backend.capabilities import register_capabilities


def test_catalog_contains_only_implemented_approved_ids():
    craft = CapabilityRegistry(); register_capabilities(craft)
    implemented = {spec.id for spec in capability_registry.list()} | {spec.id for spec in craft.list()}
    assert implemented <= APPROVED_CAPABILITY_IDS
    assert implemented.isdisjoint(FORBIDDEN_INTERNAL_PROTOCOL_IDS)


def test_first_wave_plugin_exposure_remains_closed():
    craft = CapabilityRegistry(); register_capabilities(craft)
    specs = capability_registry.list() + craft.list()
    governed = [spec for spec in specs if spec.id.startswith(AGREED_WAVE_PREFIXES)]
    assert governed
    assert all(spec.plugin_callable is False for spec in governed)


def test_agent_adapter_uses_bounded_context_and_never_advertises_discovery_tool():
    root = Path(__file__).resolve().parents[2]
    source = (root / "plugins/agent/agent_backend/ai_assistant/tool_handlers/capability_tools.py").read_text(encoding="utf-8")
    assert '"knowledge.context.retrieve"' in source
    assert '"knowledge.document.search"' not in source
    assert "find_capabilities" not in source
    assert "database.sql.execute" not in source


def test_agent_bop_and_ontology_reads_use_governed_capabilities():
    root = Path(__file__).resolve().parents[2]
    handlers = root / "plugins/agent/agent_backend/ai_assistant/tool_handlers"
    adapter = (handlers / "capability_tools.py").read_text(encoding="utf-8")
    craft = (handlers / "craft_tools.py").read_text(encoding="utf-8")
    knowledge = (handlers / "knowledge_tools.py").read_text(encoding="utf-8")

    assert '"craft.bop.execution_structure.get"' in adapter
    assert '"ontology.concept.resolve"' in adapter
    assert '"ontology.concept.get"' in adapter
    assert "/api/bop/versions/{version_gid}/entries" not in craft
    assert "/api/ontology/schema/" not in knowledge
