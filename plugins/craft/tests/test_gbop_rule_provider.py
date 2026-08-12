from __future__ import annotations

from plugins.craft.craft_backend.application.rules import RuleService
from plugins.craft.craft_backend.domain.rules import RuleRelease


def test_rule_waiver_does_not_mutate_published_release():
    release = RuleRelease(ref="craft:rule-release:R1", rules=("rule:1",), knowledge_refs=("knowledge:doc:D1:r3",), ontology_release_ref="ontology:R2")
    service = RuleService([release])
    before = service.get_release(release.ref)
    waiver = service.waive(release.ref, violation="V-1", reason="approved")
    assert waiver.release_ref == release.ref
    assert service.get_release(release.ref) == before == release


def test_gbop_and_rule_providers_publish_complete_native_ids():
    from plugins.craft.craft_backend.capabilities.gbop_descriptors import GBOP_CAPABILITY_IDS
    from plugins.craft.craft_backend.capabilities.rule_descriptors import RULE_CAPABILITY_IDS
    assert "craft.gbop.release.publish" in GBOP_CAPABILITY_IDS
    assert "craft.rule.evaluate" in RULE_CAPABILITY_IDS
    assert "craft.rule.waiver.create" in RULE_CAPABILITY_IDS
