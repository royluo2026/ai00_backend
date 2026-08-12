from __future__ import annotations

from collections.abc import Callable

from backend.capabilities.registry_next import CapabilityRegistry
from backend.base.official_provider import register_capabilities as register_base
from backend.knowledge.official_provider import register_capabilities as register_knowledge
from backend.ontology.official_provider import register_capabilities as register_ontology


def _snapshot(register: Callable[[CapabilityRegistry], None]):
    registry = CapabilityRegistry()
    register(registry)
    return registry.snapshot()


def test_official_entrypoints_register_only_their_domain_owners() -> None:
    base = _snapshot(register_base)
    knowledge = _snapshot(register_knowledge)
    ontology = _snapshot(register_ontology)

    assert {item.spec.owner for item in base} == {"base"}
    assert {item.spec.owner for item in knowledge} == {"knowledge"}
    assert {item.spec.owner for item in ontology} == {"ontology"}
    assert all(item.spec.id != "system.echo" for item in (*base, *knowledge, *ontology))
