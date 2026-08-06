"""Publish, compare and guarded activation of immutable ontology releases."""
from __future__ import annotations

from typing import Any

from backend.core.ois_storage import put_immutable
from backend.ontology.activation import validate_attestations
from backend.ontology.canonical import canonicalize_release
from backend.ontology.diff import semantic_diff
from backend.ontology.proposals import OntologyProposalRepository
from backend.ontology.repository import OntologyReleaseRepository, ReleaseIntegrityError, StaleActiveRelease
from backend.ontology.releases import apply_changes
from backend.ontology.review_policy import is_publishable
from backend.utils.gid import next_gid

from .models_next import CapabilityBusinessError, CapabilityContext, CapabilityOutput, CapabilitySpec, EvidenceRef


def _evidence(release: dict[str, Any]) -> EvidenceRef:
    return EvidenceRef(
        kind="ontology.release", reference=f"ois://{release['ois_object_key']}",
        digest=f"sha256:{release['content_sha256']}", summary=f"Immutable ontology release {release['release_gid']}",
        metadata={"release_gid": release["release_gid"], "parent_release_gid": release.get("parent_release_gid")},
    )


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
    release_gid = str(next_gid())
    object_key = f"ontology/releases/{release_gid}/release.{digest}.json"
    stored = put_immutable(object_key, snapshot, "application/json; charset=utf-8")
    if not stored or stored.get("object_key") != object_key or stored.get("sha256") != digest:
        raise RuntimeError("ontology release OIS snapshot verification failed")
    release = repository.create_release(
        release_gid=release_gid, parent_release_gid=base["release_gid"], objects=after,
        ois_object_key=object_key, actor_gid=context.user_gid, source="proposal", source_gid=proposal_gid,
    )
    release["compatibility"] = semantic_diff(before, after)["compatibility"]
    return CapabilityOutput(data=release, evidence=(_evidence(release),))


def get_release(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    release = OntologyReleaseRepository().resolve_release(str(payload.get("release_gid") or "").strip() or None)
    return CapabilityOutput(data=release, evidence=(_evidence(release),))


def search_releases(payload: dict[str, Any], _context: CapabilityContext) -> dict[str, Any]:
    items = OntologyReleaseRepository().search_releases(limit=int(payload.get("limit") or 50))
    return {"items": items, "total": len(items)}


def diff_releases(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    repository = OntologyReleaseRepository()
    before_release = repository.resolve_release(str(payload.get("from_release_gid") or ""))
    after_release = repository.resolve_release(str(payload.get("to_release_gid") or ""))
    diff = semantic_diff(repository.list_objects(before_release["release_gid"]), repository.list_objects(after_release["release_gid"]))
    return CapabilityOutput(data={**diff, "from_release_gid": before_release["release_gid"], "to_release_gid": after_release["release_gid"]}, evidence=(_evidence(before_release), _evidence(after_release)))


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
    return CapabilityOutput(data=activated, evidence=(_evidence(target),))


def register_ontology_release_capabilities(registry: Any) -> None:
    common = {"owner": "ontology", "plugin_callable": True, "subject_concepts": ("ontology.release",), "output_schema": {"type": "object"}, "tags": ("ontology", "release")}
    registry.register(CapabilitySpec(**common, id="ontology.release.get", description="Read one immutable or active release.", use_when="A release identity or current active release is needed.", do_not_use_when="Comparing two releases.", effects=("read:ontology.release",), input_schema={"type": "object"}), get_release)
    registry.register(CapabilitySpec(**common, id="ontology.release.search", description="Search immutable release metadata.", use_when="Release history is required.", do_not_use_when="A release identity is known.", effects=("read:ontology.release",), input_schema={"type": "object"}), search_releases)
    registry.register(CapabilitySpec(**common, id="ontology.release.diff", description="Compute a semantic stable-identity release diff.", use_when="Change impact between two releases is needed.", do_not_use_when="Raw JSON text differences are expected.", effects=("read:ontology.release",), input_schema={"type": "object", "required": ["from_release_gid", "to_release_gid"]}), diff_releases)
    registry.register(CapabilitySpec(**common, id="ontology.release.publish", description="Publish an approved proposal as a new immutable inactive release.", use_when="An exact proposal revision has independent approval.", do_not_use_when="Changing the active release.", effects=("create:ontology.release",), risk="write", confirmation="admin", idempotent=False, permissions=("ontology.publish",), input_schema={"type": "object", "required": ["proposal_gid", "proposal_revision_gid", "content_sha256"]}), publish_release)
    registry.register(CapabilitySpec(**common, id="ontology.release.activate", description="Atomically activate a verified direct forward release.", use_when="All compatibility providers report zero blockers.", do_not_use_when="Publishing or rolling back directly.", effects=("update:ontology.active_ref",), risk="write", confirmation="admin", idempotent=False, permissions=("ontology.activate",), input_schema={"type": "object", "required": ["release_gid", "release_sha256", "expected_active_release_gid", "attestations"]}), activate_release)
