"""Publish, compare and guarded activation of immutable ontology releases."""
from __future__ import annotations

from typing import Any

from ..infrastructure.storage import put_immutable
from plugins.ontology.ontology_backend.activation import validate_attestations
from plugins.ontology.ontology_backend.canonical import canonicalize_release
from plugins.ontology.ontology_backend.diff import semantic_diff
from plugins.ontology.ontology_backend.proposals import OntologyProposalRepository
from plugins.ontology.ontology_backend.repository import OntologyReleaseRepository, ReleaseIntegrityError, StaleActiveRelease
from plugins.ontology.ontology_backend.releases import apply_changes
from plugins.ontology.ontology_backend.review_policy import is_publishable
from plugins.ontology.ontology_backend.impact_analysis import ImpactAnalysisService, official_impact_providers
from backend.capability_v2.revision.ontology_adapter import (
    ONTOLOGY_REVISION_REPOSITORY,
    OntologyRevisionAdapter,
    record_ontology_release,
)
from backend.capability_v2.revision.runtime import get_default_revision_service
from backend.domain_ports.ontology import OntologyVersionRef
from ..infrastructure.ids import next_gid

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilityOutput, CapabilitySpec, EvidenceRef
from .ontology_concepts_next import ONTOLOGY_VERSION_REF_SCHEMA


RELEASE_SCHEMA = {
    "type": "object",
    "required": ["release_gid", "content_sha256", "ontology_version_ref"],
    "properties": {
        "release_gid": {"type": "string"},
        "parent_release_gid": {},
        "content_sha256": {"type": "string", "pattern": r"^[0-9a-f]{64}$"},
        "object_count": {"type": "integer", "minimum": 0},
        "ois_object_key": {"type": "string"},
        "source": {"type": "string"},
        "source_gid": {},
        "revision_commit_id": {},
        "created_by": {"type": "string"},
        "created_at": {},
        "compatibility": {
            "type": "string",
            "enum": ["backward_compatible", "migration_required", "breaking"],
        },
        "ontology_version_ref": ONTOLOGY_VERSION_REF_SCHEMA,
    },
}

RELEASE_SEARCH_SCHEMA = {
    "type": "object",
    "required": ["items", "total"],
    "properties": {
        "items": {"type": "array", "items": RELEASE_SCHEMA},
        "total": {"type": "integer", "minimum": 0},
    },
}

_DIFF_CATEGORY_SCHEMA = {
    "type": "object",
    "required": ["added", "changed", "deprecated", "removed"],
    "properties": {
        "added": {"type": "array", "items": {}},
        "changed": {"type": "array", "items": {}},
        "deprecated": {"type": "array", "items": {}},
        "removed": {"type": "array", "items": {}},
    },
}

RELEASE_DIFF_SCHEMA = {
    "type": "object",
    "required": [
        "concepts", "properties", "relations", "mappings", "constraints", "compatibility",
        "from_release_gid", "to_release_gid", "from_ontology_version_ref", "to_ontology_version_ref",
    ],
    "properties": {
        **{name: _DIFF_CATEGORY_SCHEMA for name in ("concepts", "properties", "relations", "mappings", "constraints")},
        "compatibility": {
            "type": "string",
            "enum": ["backward_compatible", "migration_required", "breaking"],
        },
        "from_release_gid": {"type": "string"},
        "to_release_gid": {"type": "string"},
        "from_ontology_version_ref": ONTOLOGY_VERSION_REF_SCHEMA,
        "to_ontology_version_ref": ONTOLOGY_VERSION_REF_SCHEMA,
    },
}

ACTIVATION_SCHEMA = {
    "type": "object",
    "required": ["ref_name", "release_gid", "release_sha256", "ontology_version_ref"],
    "properties": {
        "ref_name": {"type": "string"},
        "release_gid": {"type": "string"},
        "release_sha256": {"type": "string", "pattern": r"^[0-9a-f]{64}$"},
        "ontology_version_ref": ONTOLOGY_VERSION_REF_SCHEMA,
    },
}


def _evidence(release: dict[str, Any]) -> EvidenceRef:
    return EvidenceRef(
        kind="ontology.release", reference=f"ois://{release['ois_object_key']}",
        digest=f"sha256:{release['content_sha256']}", summary=f"Immutable ontology release {release['release_gid']}",
        metadata={"release_gid": release["release_gid"], "parent_release_gid": release.get("parent_release_gid")},
    )


def _version_ref(release: dict[str, Any]) -> OntologyVersionRef:
    revision_ref = None
    if release.get("revision_commit_id"):
        revision_ref = get_default_revision_service().get_commit(
            str(release["revision_commit_id"]),
            repository=ONTOLOGY_REVISION_REPOSITORY,
        ).ref
    return OntologyVersionRef(
        release_gid=str(release["release_gid"]),
        content_hash=f"sha256:{str(release['content_sha256']).removeprefix('sha256:')}",
        revision_ref=revision_ref,
    )


def _with_version_ref(release: dict[str, Any]) -> dict[str, Any]:
    return {**release, "ontology_version_ref": _version_ref(release).model_dump(mode="json")}


def get_ontology_impact_service() -> ImpactAnalysisService:
    # Formal deployments register all four domain providers. With none registered,
    # non-breaking releases pass and breaking releases fail closed.
    return official_impact_providers.service()


def record_published_ontology_revision(
    repository: OntologyReleaseRepository,
    *,
    base: dict[str, Any],
    before: list[dict[str, Any]],
    release: dict[str, Any],
    after: list[dict[str, Any]],
    actor_id: str,
) -> OntologyVersionRef:
    base_version = OntologyVersionRef(
        release_gid=str(base["release_gid"]),
        content_hash=f"sha256:{str(base['content_sha256']).removeprefix('sha256:')}",
    )
    target_version = OntologyVersionRef(
        release_gid=str(release["release_gid"]),
        content_hash=f"sha256:{str(release['content_sha256']).removeprefix('sha256:')}",
    )
    recorded_base, recorded_target = record_ontology_release(
        service=get_default_revision_service(),
        base_version=base_version,
        base_objects=before,
        target_version=target_version,
        target_objects=after,
        actor_id=actor_id,
    )
    assert recorded_base.revision_ref is not None and recorded_target.revision_ref is not None
    repository.bind_revision(
        base_version.release_gid,
        base_version.content_hash.removeprefix("sha256:"),
        recorded_base.revision_ref,
    )
    repository.bind_revision(
        target_version.release_gid,
        target_version.content_hash.removeprefix("sha256:"),
        recorded_target.revision_ref,
    )
    return recorded_target


def publish_release(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    proposal_gid = str(payload.get("proposal_gid") or "")
    revision_gid = str(payload.get("proposal_revision_gid") or "")
    revision_hash = str(payload.get("content_sha256") or "")
    proposals = OntologyProposalRepository()
    proposal = proposals.get(proposal_gid)
    if not proposal or proposal.get("proposal_revision_gid") != revision_gid or proposal.get("content_sha256") != revision_hash:
        raise CapabilityBusinessError("proposal_revision_conflict", "Publish requires the exact current proposal revision and Hash.")
    reviews = proposals.list_reviews(proposal_gid, revision_gid)
    if not is_publishable(reviews=reviews, author_gid=str(proposal["author_gid"]), content_sha256=revision_hash):
        raise CapabilityBusinessError("proposal_not_approved", "Ontology proposal lacks an independent bound human approval.")
    repository = OntologyReleaseRepository()
    base = repository.resolve_release(str(proposal["base_release_gid"]))
    active = repository.get_active("default")
    if isinstance(active, dict) and str(active.get("release_gid")) != str(base["release_gid"]):
        raise CapabilityBusinessError("base_release_conflict", "The approved proposal base is no longer active.")
    before = repository.list_objects(base["release_gid"])
    after = apply_changes(before, proposal["changes"])
    snapshot, digest = canonicalize_release(after)
    existing = repository.find_by_source("proposal", proposal_gid)
    if isinstance(existing, dict):
        if (
            str(existing.get("content_sha256")) != digest
            or str(existing.get("parent_release_gid")) != str(base["release_gid"])
        ):
            raise CapabilityBusinessError(
                "release_integrity_error",
                "Existing proposal release does not match the approved content.",
            )
        release = existing
    else:
        release_gid = str(next_gid())
        object_key = f"ontology/releases/{release_gid}/release.{digest}.json"
        stored = put_immutable(object_key, snapshot, "application/json; charset=utf-8")
        if not stored or stored.get("object_key") != object_key or stored.get("sha256") != digest:
            raise RuntimeError("ontology release OIS snapshot verification failed")
        release = repository.create_release(
            release_gid=release_gid, parent_release_gid=base["release_gid"], objects=after,
            ois_object_key=object_key, actor_gid=context.user_gid, source="proposal", source_gid=proposal_gid,
        )
    recorded_version = record_published_ontology_revision(
        repository,
        base=base,
        before=before,
        release=release,
        after=after,
        actor_id=context.user_gid,
    )
    release["revision_commit_id"] = recorded_version.revision_ref.commit_id
    release["compatibility"] = semantic_diff(before, after)["compatibility"]
    return CapabilityOutput(data={
        **release,
        "ontology_version_ref": recorded_version.model_dump(mode="json"),
    }, evidence=(_evidence(release),))


def get_release(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    release = OntologyReleaseRepository().resolve_release(str(payload.get("release_gid") or "").strip() or None)
    return CapabilityOutput(data=_with_version_ref(release), evidence=(_evidence(release),))


def search_releases(payload: dict[str, Any], _context: CapabilityContext) -> dict[str, Any]:
    items = OntologyReleaseRepository().search_releases(limit=int(payload.get("limit") or 50))
    return {"items": [_with_version_ref(item) for item in items], "total": len(items)}


def diff_releases(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    repository = OntologyReleaseRepository()
    before_release = repository.resolve_release(str(payload.get("from_release_gid") or ""))
    after_release = repository.resolve_release(str(payload.get("to_release_gid") or ""))
    diff = semantic_diff(repository.list_objects(before_release["release_gid"]), repository.list_objects(after_release["release_gid"]))
    return CapabilityOutput(data={
        **diff,
        "from_release_gid": before_release["release_gid"],
        "to_release_gid": after_release["release_gid"],
        "from_ontology_version_ref": _version_ref(before_release).model_dump(mode="json"),
        "to_ontology_version_ref": _version_ref(after_release).model_dump(mode="json"),
    }, evidence=(_evidence(before_release), _evidence(after_release)))


def activate_release(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    gate = validate_attestations(payload.get("attestations") or [])
    if not gate["ok"]:
        raise CapabilityBusinessError("activation_gate_failed", "Ontology activation attestations are incomplete or blocking.", details=gate)
    release_gid = str(payload.get("release_gid") or "")
    expected = str(payload.get("expected_active_release_gid") or "") or None
    expected_hash = str(payload.get("release_sha256") or "")
    repository = OntologyReleaseRepository()
    target = repository.resolve_release(release_gid)
    if str(target["content_sha256"]) != expected_hash:
        raise CapabilityBusinessError("release_integrity_error", "Target release Hash does not match immutable metadata.")
    if expected and str(target.get("parent_release_gid") or "") != expected:
        raise CapabilityBusinessError("direct_rollback_forbidden", "Activation only permits a direct forward child of the active release.")
    if expected:
        base = repository.resolve_release(expected)
        before = repository.list_objects(base["release_gid"])
        after = repository.list_objects(target["release_gid"])
        adapter = OntologyRevisionAdapter(version_ref=_version_ref(target))
        impact = get_ontology_impact_service().analyze(
            adapter.diff({"objects": before}, {"objects": after})
        )
        if not impact.activation_allowed:
            raise CapabilityBusinessError(
                "ontology_impact_blocked",
                "Breaking ontology changes have unresolved or unavailable consumers.",
                details=impact.model_dump(mode="json"),
            )
    if not target.get("revision_commit_id"):
        raise CapabilityBusinessError(
            "release_revision_missing",
            "Ontology release is not bound to the common immutable Revision graph.",
        )
    if target.get("source") == "proposal":
        proposals = OntologyProposalRepository()
        proposal = proposals.get(str(target.get("source_gid") or ""))
        reviews = proposals.list_reviews(proposal["proposal_gid"], proposal["proposal_revision_gid"]) if proposal else []
        if not proposal or not is_publishable(reviews=reviews, author_gid=str(proposal["author_gid"]), content_sha256=str(proposal["content_sha256"])):
            raise CapabilityBusinessError("proposal_not_approved", "Release source proposal no longer satisfies review policy.")
    try:
        activated = repository.activate(
            ref_name="default", release_gid=release_gid, expected_release_gid=expected,
            release_sha256=expected_hash, actor_gid=context.user_gid,
        )
    except StaleActiveRelease as exc:
        raise CapabilityBusinessError("active_release_conflict", str(exc)) from exc
    except ReleaseIntegrityError as exc:
        raise CapabilityBusinessError("release_integrity_error", str(exc)) from exc
    return CapabilityOutput(data={
        **activated,
        "ontology_version_ref": _version_ref(target).model_dump(mode="json"),
    }, evidence=(_evidence(target),))


def register_ontology_release_capabilities(registry: Any) -> None:
    common = {"owner": "ontology", "plugin_callable": True, "subject_concepts": ("ontology.release",), "tags": ("ontology", "release")}
    registry.register(CapabilitySpec(**common, id="ontology.release.get", description="Read one immutable or active release.", use_when="A release identity or current active release is needed.", do_not_use_when="Comparing two releases.", effects=("read:ontology.release",), output_schema=RELEASE_SCHEMA, input_schema={"type": "object"}), get_release)
    registry.register(CapabilitySpec(**common, id="ontology.release.search", description="Search immutable release metadata.", use_when="Release history is required.", do_not_use_when="A release identity is known.", effects=("read:ontology.release",), output_schema=RELEASE_SEARCH_SCHEMA, input_schema={"type": "object"}), search_releases)
    registry.register(CapabilitySpec(**common, id="ontology.release.diff", description="Compute a semantic stable-identity release diff.", use_when="Change impact between two releases is needed.", do_not_use_when="Raw JSON text differences are expected.", effects=("read:ontology.release",), output_schema=RELEASE_DIFF_SCHEMA, input_schema={"type": "object", "required": ["from_release_gid", "to_release_gid"]}), diff_releases)
    registry.register(CapabilitySpec(**common, id="ontology.release.publish", description="Publish an approved proposal as a new immutable inactive release.", use_when="An exact proposal revision has independent approval.", do_not_use_when="Changing the active release.", effects=("create:ontology.release",), risk="write", confirmation="admin", idempotent=False, permissions=("ontology.publish",), output_schema=RELEASE_SCHEMA, input_schema={"type": "object", "required": ["proposal_gid", "proposal_revision_gid", "content_sha256"]}), publish_release)
    registry.register(CapabilitySpec(**common, id="ontology.release.activate", description="Atomically activate a verified direct forward release.", use_when="All compatibility providers report zero blockers.", do_not_use_when="Publishing or rolling back directly.", effects=("update:ontology.active_ref",), risk="write", confirmation="admin", idempotent=False, permissions=("ontology.activate",), output_schema=ACTIVATION_SCHEMA, input_schema={"type": "object", "required": ["release_gid", "release_sha256", "expected_active_release_gid", "attestations"]}), activate_release)
