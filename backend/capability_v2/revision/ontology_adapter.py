"""Ontology-owned semantic adapter for the shared Revision kernel."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from backend.domain_ports.ontology import ConceptRef, OntologyVersionRef
from backend.ontology.canonical import normalize_release_objects

from .models import BranchRef, Change, RepositoryRef
from .service import RevisionNotFoundError, RevisionService


ONTOLOGY_REVISION_REPOSITORY = RepositoryRef(
    tenant_id="global",
    repository_id="ontology.default",
    owner_domain="ontology",
    resource_id="ontology.default",
)


def _objects(content: Mapping[str, Any]) -> list[dict[str, Any]]:
    if set(content) != {"objects"}:
        raise ValueError("ontology revision root requires only objects")
    return normalize_release_objects(content["objects"])


def _constraint_tightened(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    if not bool(before.get("required")) and bool(after.get("required")):
        return True
    old_min, new_min = before.get("minimum"), after.get("minimum")
    if new_min is not None and (old_min is None or new_min > old_min):
        return True
    old_max, new_max = before.get("maximum"), after.get("maximum")
    if new_max is not None and (old_max is None or new_max < old_max):
        return True
    old_enum, new_enum = before.get("enum"), after.get("enum")
    if isinstance(old_enum, list) and isinstance(new_enum, list) and not set(old_enum) <= set(new_enum):
        return True
    return before.get("pattern") != after.get("pattern") and after.get("pattern") is not None


class OntologyRevisionAdapter:
    def __init__(self, *, version_ref: OntologyVersionRef) -> None:
        self._version_ref = version_ref

    def normalize(self, content: Mapping[str, Any]) -> dict[str, Any]:
        return {"objects": _objects(content)}

    def validate_changeset(self, before: Mapping[str, Any], after: Mapping[str, Any]) -> None:
        self.normalize(before)
        self.normalize(after)

    def diff(self, before: Mapping[str, Any], after: Mapping[str, Any]) -> tuple[Change, ...]:
        old = {(item["kind"], item["stable_gid"]): item for item in _objects(before)}
        new = {(item["kind"], item["stable_gid"]): item for item in _objects(after)}
        changes: list[Change] = []
        for kind, stable_gid in sorted(old.keys() | new.keys()):
            prior, current = old.get((kind, stable_gid)), new.get((kind, stable_gid))
            ref = ConceptRef(
                concept_id=stable_gid,
                kind=kind,
                ontology_version=self._version_ref,
            )
            path = f"/objects/{kind}/{stable_gid}"
            if prior is None:
                breaking = kind == "constraint" and bool(current.get("required"))
                changes.append(Change(
                    change_type="add", path=path, after=current, identity=stable_gid,
                    resource_ref=ref, breaking=breaking,
                ))
            elif current is None:
                changes.append(Change(
                    change_type="remove", path=path, before=prior, identity=stable_gid,
                    resource_ref=ref, breaking=True,
                ))
            elif prior != current:
                if not prior.get("deprecated") and current.get("deprecated"):
                    change_type, breaking = "deprecate", True
                elif kind == "concept" and prior.get("name") != current.get("name"):
                    other_fields = (set(prior) | set(current)) - {"name", "label", "display_name"}
                    only_name_changed = all(prior.get(field) == current.get(field) for field in other_fields)
                    change_type, breaking = ("rename", False) if only_name_changed else ("modify", True)
                elif kind == "constraint":
                    change_type, breaking = "constraint_change", _constraint_tightened(prior, current)
                else:
                    change_type, breaking = "modify", kind in {"property", "relation"}
                changes.append(Change(
                    change_type=change_type, path=path, before=prior, after=current,
                    identity=stable_gid, resource_ref=ref, breaking=breaking,
                ))
        return tuple(changes)

    def apply_changeset(self, before: Mapping[str, Any], changes: Sequence[Change]) -> dict[str, Any]:
        objects = {(item["kind"], item["stable_gid"]): item for item in _objects(before)}
        for change in changes:
            ref = change.resource_ref
            kind = ref.kind if isinstance(ref, ConceptRef) else str(ref["kind"])
            stable_gid = ref.concept_id if isinstance(ref, ConceptRef) else str(ref["concept_id"])
            key = (kind, stable_gid)
            if change.change_type == "remove":
                if key not in objects:
                    raise ValueError("ontology changeset removes a missing object")
                del objects[key]
            elif change.change_type in {"add", "rename", "deprecate", "modify", "constraint_change"}:
                if not isinstance(change.after, Mapping):
                    raise ValueError("ontology changeset requires an object result")
                objects[key] = deepcopy(dict(change.after))
            else:
                raise ValueError(f"unsupported ontology change type: {change.change_type}")
        return {"objects": normalize_release_objects(list(objects.values()))}

    def classify_conflict(self, path: str, base: Any, ours: Any, theirs: Any) -> str:
        return "ontology_object"


def record_ontology_release(
    *,
    service: RevisionService,
    base_version: OntologyVersionRef,
    base_objects: Sequence[Mapping[str, Any]],
    target_version: OntologyVersionRef,
    target_objects: Sequence[Mapping[str, Any]],
    actor_id: str,
) -> tuple[OntologyVersionRef, OntologyVersionRef]:
    """Bind an immutable ontology release pair to the shared commit graph.

    The caller owns transaction composition when the release and Revision stores
    share a database. Stale bases are rejected by the Revision branch CAS.
    """
    branch = BranchRef(repository=ONTOLOGY_REVISION_REPOSITORY, name="main")
    base_content = {"objects": normalize_release_objects(base_objects)}
    target_content = {"objects": normalize_release_objects(target_objects)}
    try:
        current = service.head(branch)
    except RevisionNotFoundError:
        initialized = service.initialize(
            repository=ONTOLOGY_REVISION_REPOSITORY,
            branch="main",
            content=base_content,
            author_id=actor_id,
            message=f"Import ontology baseline {base_version.release_gid}",
        )
        base_commit = initialized.commit
    else:
        if current.snapshot.content == target_content:
            if len(current.parent_ids) != 1:
                raise ValueError("ontology target revision has an invalid parent graph")
            parent = service.get_commit(current.parent_ids[0], repository=ONTOLOGY_REVISION_REPOSITORY)
            if parent.snapshot.content != base_content:
                raise ValueError("ontology target revision does not descend from the requested base")
            return (
                base_version.model_copy(update={"revision_ref": parent.ref}),
                target_version.model_copy(update={"revision_ref": current.ref}),
            )
        if current.snapshot.content != base_content:
            raise ValueError("ontology base release does not match the Revision branch head")
        if base_version.revision_ref is not None and base_version.revision_ref != current.ref:
            raise ValueError("ontology base RevisionRef is stale or belongs to another repository")
        base_commit = current
    recorded_base = base_version.model_copy(update={"revision_ref": base_commit.ref})
    committed = service.commit(
        branch=branch,
        content=target_content,
        expected_head=base_commit.commit_id,
        author_id=actor_id,
        message=f"Publish ontology release {target_version.release_gid}",
    )
    recorded_target = target_version.model_copy(update={"revision_ref": committed.commit.ref})
    return recorded_base, recorded_target
