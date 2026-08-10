from __future__ import annotations

import json
from pathlib import Path
import pytest

from backend.capability_v2.revision.ontology_adapter import (
    OntologyRevisionAdapter,
    record_ontology_release,
)
from backend.capability_v2.revision.diff import JsonDocumentAdapter
from backend.capability_v2.revision.repository import InMemoryRevisionRepository
from backend.capability_v2.revision.service import RevisionService
from backend.capability_v2.revision.models import BranchRef
from backend.domain_ports.ontology import (
    ConceptRef,
    ImpactReference,
    OntologyVersionRef,
)
from backend.ontology.impact_analysis import (
    ImpactAnalysisService,
    ImpactProviderRegistry,
    StaticImpactProvider,
)


GOLDEN = Path(__file__).parent / "golden" / "ontology"


def _case(name: str) -> dict:
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


def test_concept_rename_preserves_stable_identity_and_version_ref():
    case = _case("concept-rename.json")
    adapter = OntologyRevisionAdapter(
        version_ref=OntologyVersionRef(**case["to_version"]),
    )

    changes = adapter.diff({"objects": case["before"]}, {"objects": case["after"]})

    assert len(changes) == 1
    change = changes[0]
    assert change.change_type == "rename"
    assert isinstance(change.resource_ref, ConceptRef)
    assert change.resource_ref.concept_id == "concept.operation"
    assert change.resource_ref.ontology_version.release_gid == "ontology-v2"
    assert change.breaking is False


def test_constraint_tightening_is_a_breaking_semantic_change():
    case = _case("constraint-breaking-change.json")
    adapter = OntologyRevisionAdapter(
        version_ref=OntologyVersionRef(**case["to_version"]),
    )

    changes = adapter.diff({"objects": case["before"]}, {"objects": case["after"]})

    assert [(item.change_type, item.identity, item.breaking) for item in changes] == [
        ("constraint_change", "constraint.operation.duration", True),
    ]


def test_impact_analysis_blocks_activation_for_unresolved_domain_consumers():
    case = _case("release-impact.json")
    adapter = OntologyRevisionAdapter(
        version_ref=OntologyVersionRef(**case["to_version"]),
    )
    changes = adapter.diff({"objects": case["before"]}, {"objects": case["after"]})
    providers = {
        name: StaticImpactProvider(
            name,
            tuple(ImpactReference(**item) for item in rows),
        )
        for name, rows in case["provider_references"].items()
    }

    report = ImpactAnalysisService(providers).analyze(changes)

    assert report.activation_allowed is False
    assert [(item.provider, item.consumer_id) for item in report.unresolved] == [
        ("agent", "workflow.optimize-routing"),
        ("craft", "craft.routing.validate"),
    ]
    assert report.missing_providers == ()


def test_breaking_activation_fails_closed_when_a_required_provider_is_missing():
    case = _case("constraint-breaking-change.json")
    changes = OntologyRevisionAdapter(
        version_ref=OntologyVersionRef(**case["to_version"]),
    ).diff({"objects": case["before"]}, {"objects": case["after"]})

    report = ImpactAnalysisService({}).analyze(changes)

    assert report.activation_allowed is False
    assert report.missing_providers == ("agent", "craft", "digital_model", "plugins")


def test_ontology_releases_are_recorded_as_linear_common_revision_commits():
    service = RevisionService(InMemoryRevisionRepository(), JsonDocumentAdapter())
    base = OntologyVersionRef(
        release_gid="ontology-v1",
        content_hash="sha256:" + "a" * 64,
    )
    target = OntologyVersionRef(
        release_gid="ontology-v2",
        content_hash="sha256:" + "b" * 64,
    )
    before = [{"kind": "concept", "stable_gid": "concept.operation", "name": "工序"}]
    after = [{"kind": "concept", "stable_gid": "concept.operation", "name": "工艺操作"}]

    recorded_base, recorded_target = record_ontology_release(
        service=service,
        base_version=base,
        base_objects=before,
        target_version=target,
        target_objects=after,
        actor_id="reviewer-1",
    )

    assert recorded_base.revision_ref is not None
    assert recorded_target.revision_ref is not None
    assert recorded_target.revision_ref.repository.owner_domain == "ontology"
    assert service.history(BranchRef(
        repository=recorded_target.revision_ref.repository,
        name="main",
    )) == (
        recorded_target.revision_ref.commit_id,
        recorded_base.revision_ref.commit_id,
    )


def test_official_impact_provider_registry_freezes_before_activation_analysis():
    registry = ImpactProviderRegistry()
    registry.register(StaticImpactProvider("craft", ()))

    service = registry.service()

    assert service is not None
    with pytest.raises(RuntimeError, match="frozen"):
        registry.register(StaticImpactProvider("agent", ()))
