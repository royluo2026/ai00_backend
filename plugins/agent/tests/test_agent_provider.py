import json
from pathlib import Path

from plugins.agent.agent_backend.capabilities import register_capabilities


EXPECTED = {
    "agent.audit.read", "agent.audit.record", "agent.flow.change.apply", "agent.flow.read",
    "agent.workflow.node.test.execute", "agent.canvas.options.resolve",
    "agent.canvas.execution.start", "agent.canvas.execution.resume",
    "agent.interaction.request", "agent.interaction.cancel", "agent.interaction.chat.change.apply",
    "agent.catalog_tool.confirm.apply",
    "agent.memory.change.apply", "agent.memory.read", "agent.runtime.config.read", "agent.tool_catalog.read", "agent.script.generate",
    "agent.run.change.apply", "agent.run.read", "agent.session.change.apply", "agent.session.read",
    "agent.skill.change.apply", "agent.skill.read",
}
ROOT = Path(__file__).parents[3]


def test_agent_provider_matches_frozen_review_and_is_stable():
    class Registry:
        def __init__(self): self.items = []
        def register(self, spec, handler, *, descriptor=None): self.items.append((spec, descriptor))
    registry = Registry(); register_capabilities(registry)
    assert {spec.id for spec, _ in registry.items} == EXPECTED
    assert {descriptor.owner_domain for _, descriptor in registry.items} == {"agent"}
    assert all(descriptor.lifecycle_status == "stable" for _, descriptor in registry.items)
    model_hidden = {
        "agent.interaction.chat.change.apply",
        "agent.catalog_tool.confirm.apply",
        "agent.runtime.config.read",
    }
    assert all(
        descriptor.exposure.plugin == (spec.id != "agent.catalog_tool.confirm.apply")
        for spec, descriptor in registry.items
    )
    assert all(
        descriptor.exposure.agent == (spec.id not in model_hidden)
        and descriptor.exposure.mcp == (spec.id not in model_hidden)
        for spec, descriptor in registry.items
    )
    chat_versions = {
        spec.version
        for spec, _descriptor in registry.items
        if spec.id == "agent.interaction.chat.change.apply"
    }
    assert chat_versions == {1, 2}
    assert all(
        spec.confirmation == (
            "none"
            if spec.risk.value == "read"
            or (spec.id == "agent.interaction.chat.change.apply" and spec.version == 2)
            else "user"
        )
        for spec, _ in registry.items
    )


def test_agent_is_official_and_database_independent():
    manifest = json.loads((ROOT / "backend/capability_v2/official_domains.json").read_text(encoding="utf-8"))
    agent = next(item for item in manifest["domains"] if item["domain_id"] == "agent")
    assert agent["artifact"]["module"] == "agent_backend.capabilities"
    assert agent["database"]["database_name"] == "ai00_agent"
    sql = (ROOT / "backend/db/migrations/domains/agent/0001_agent.sql").read_text(encoding="utf-8")
    assert "workmanship_agent_runs" in sql
    assert "workmanship_bop_" not in sql
    confirmation_sql = (ROOT / "backend/db/migrations/domains/agent/0004_confirmation_tokens.sql").read_text(encoding="utf-8")
    assert "workmanship_agent_confirmation_tokens" in confirmation_sql
    assert "token_hash" in confirmation_sql
    assert "state VARCHAR(16) NOT NULL" in confirmation_sql


def test_every_strong_agent_write_registers_a_transactional_handler():
    class Registry:
        def __init__(self): self.items = []
        def register(self, spec, handler, *, descriptor=None):
            self.items.append((handler, descriptor))

    registry = Registry(); register_capabilities(registry)
    strong_writes = [
        handler for handler, descriptor in registry.items
        if descriptor.side_effect_level.value != "read"
        and descriptor.consistency_policy == "strong"
    ]
    assert strong_writes
    assert all(getattr(handler, "__capability_transactional__", False) for handler in strong_writes)
