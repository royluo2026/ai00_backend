"""Pure live-document model projection; no native calls or persistence.

The provider must persist the result transactionally with its observation cursor
and idempotency record. Native keys must identify insertion occurrences, not paths
or collection offsets. An absent instance is a reconciliation candidate, not a
delete instruction, even when enumeration reports complete.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from uuid import uuid4

from .live_hierarchy_sync import HierarchyNode, validate_hierarchy_nodes


@dataclass(frozen=True)
class ModelObservation:
    native_instance_id: str
    source_kind: str
    source_identity: str
    display_name: str
    content_fingerprint: str | None = None
    # Only populate from native insertion-time evidence, never collection time.
    inserted_at: datetime | None = None


@dataclass(frozen=True)
class ModelInsertion(ModelObservation):
    insertion_instance_id: str = ""
    first_seen_at: datetime | None = None


@dataclass(frozen=True)
class ModelImportProjection:
    document_session: str
    observed_at: datetime
    complete: bool
    instances: tuple[ModelInsertion, ...]
    unobserved_instance_ids: tuple[str, ...]
    missing_from_complete_observation: tuple[str, ...] = ()


def _time(value: datetime, error: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)
    return value.astimezone(timezone.utc)


def project_model_insertions(*, document_session: str, observed_at: datetime,
                             models: tuple[ModelObservation, ...], complete: bool,
                             previous: ModelImportProjection | None = None) -> ModelImportProjection:
    if not isinstance(document_session, str) or not document_session.strip() or len(document_session) > 2048:
        raise ValueError("document_session_invalid")
    observed_at = _time(observed_at, "observation_time_invalid")
    if type(complete) is not bool or not isinstance(models, tuple) or len(models) > 1_000_000:
        raise ValueError("model_observation_invalid")
    if previous is not None:
        if previous.document_session != document_session:
            raise ValueError("document_session_changed")
        if observed_at < previous.observed_at:
            raise ValueError("observation_time_regressed")
    retained = {row.native_instance_id: row for row in previous.instances} if previous else {}
    disappeared = set(previous.missing_from_complete_observation) if previous else set()
    seen: set[str] = set()
    for model in models:
        if not isinstance(model, ModelObservation):
            raise ValueError("model_observation_invalid")
        if any(not isinstance(value, str) or not value.strip() or len(value) > 4096
               for value in (model.native_instance_id, model.source_identity)):
            raise ValueError("model_identity_invalid")
        if model.source_kind not in {"online", "local_file"}:
            raise ValueError("model_source_kind_invalid")
        if not isinstance(model.display_name, str) or len(model.display_name) > 16384:
            raise ValueError("model_name_invalid")
        if model.content_fingerprint is not None and (
            not isinstance(model.content_fingerprint, str) or not model.content_fingerprint
            or len(model.content_fingerprint) > 4096
        ):
            raise ValueError("model_fingerprint_invalid")
        key = model.native_instance_id
        if key in seen:
            raise ValueError("model_instance_duplicate")
        seen.add(key)
        inserted_at = None if model.inserted_at is None else _time(model.inserted_at, "model_inserted_at_invalid")
        if inserted_at is not None and inserted_at > observed_at:
            raise ValueError("model_inserted_at_invalid")
        old = retained.get(key)
        if old is not None:
            if old.insertion_instance_id in disappeared:
                raise ValueError("model_instance_reappeared")
            if (old.source_kind, old.source_identity) != (model.source_kind, model.source_identity):
                raise ValueError("model_instance_identity_changed")
            if old.inserted_at is not None and inserted_at is not None and old.inserted_at != inserted_at:
                raise ValueError("model_instance_identity_changed")
            retained[key] = replace(old, display_name=model.display_name,
                                    content_fingerprint=model.content_fingerprint,
                                    inserted_at=inserted_at or old.inserted_at)
        else:
            retained[key] = ModelInsertion(
                native_instance_id=key, source_kind=model.source_kind,
                source_identity=model.source_identity, display_name=model.display_name,
                content_fingerprint=model.content_fingerprint, inserted_at=inserted_at,
                insertion_instance_id=str(uuid4()), first_seen_at=observed_at,
            )
        if len(retained) > 1_000_000:
            raise ValueError("model_instance_limit_exceeded")
    unobserved = tuple(row.insertion_instance_id for key, row in retained.items() if key not in seen)
    if complete:
        disappeared.update(unobserved)
    return ModelImportProjection(document_session, observed_at, complete, tuple(retained.values()), unobserved,
                                 tuple(row.insertion_instance_id for row in retained.values()
                                       if row.insertion_instance_id in disappeared))


@dataclass(frozen=True)
class NativeProductReference:
    node_id: str
    native_instance_id: str
    occurrence_id: str


@dataclass(frozen=True)
class HierarchyImportProjection:
    nodes: tuple[HierarchyNode, ...]
    complete: bool
    unresolved_references: tuple[NativeProductReference, ...]


class HierarchyReferenceProjector:
    """One immutable inventory revision; reuse across all AH in a batch."""

    def __init__(self, models: ModelImportProjection):
        self._models = models
        absent = set(models.unobserved_instance_ids)
        self._instances = {row.native_instance_id: row for row in models.instances
                           if row.insertion_instance_id not in absent}

    def project(self, *, document_session: str, nodes: tuple[HierarchyNode, ...],
                references: tuple[NativeProductReference, ...], complete: bool) -> HierarchyImportProjection:
        return _project_hierarchy_references(document_session=document_session, nodes=nodes,
            references=references, models=self._models, instances=self._instances, complete=complete)


def project_hierarchy_references(*, document_session: str, nodes: tuple[HierarchyNode, ...],
                                 references: tuple[NativeProductReference, ...],
                                 models: ModelImportProjection, complete: bool) -> HierarchyImportProjection:
    """Single-AH convenience; batches must reuse HierarchyReferenceProjector."""
    return HierarchyReferenceProjector(models).project(document_session=document_session,
        nodes=nodes, references=references, complete=complete)


def _project_hierarchy_references(*, document_session: str, nodes: tuple[HierarchyNode, ...],
                                  references: tuple[NativeProductReference, ...],
                                  models: ModelImportProjection, instances: dict[str, ModelInsertion],
                                  complete: bool) -> HierarchyImportProjection:
    """Resolve native links against one observed model-instance inventory.

    Unresolved links stay attached to their raw observation, and prevent a merge
    baseline. Consumers must stage the whole projection, never only its nodes.
    This resolves insertion identity, not proof of occurrence residency/existence;
    native observation completeness must cover the latter before passing True.
    """
    if document_session != models.document_session:
        raise ValueError("document_session_changed")
    if type(complete) is not bool or not isinstance(references, tuple) or len(references) > 1_000_000:
        raise ValueError("hierarchy_observation_invalid")
    indexed = validate_hierarchy_nodes(nodes)
    if any(row.source_identity is not None for row in nodes):
        raise ValueError("hierarchy_observation_already_resolved")
    seen: set[str] = set()
    unresolved = []
    for reference in references:
        if not isinstance(reference, NativeProductReference) or any(
            not isinstance(value, str) or not value.strip() or len(value) > 4096
            for value in (reference.node_id, reference.native_instance_id, reference.occurrence_id)
        ):
            raise ValueError("hierarchy_reference_invalid")
        if reference.node_id not in indexed or reference.node_id in seen:
            raise ValueError("hierarchy_reference_target_invalid")
        seen.add(reference.node_id)
        instance = instances.get(reference.native_instance_id)
        if instance is None:
            unresolved.append(reference)
            continue
        indexed[reference.node_id] = replace(indexed[reference.node_id],
            source_identity=instance.source_identity, insertion_instance_id=instance.insertion_instance_id,
            occurrence_id=reference.occurrence_id)
    return HierarchyImportProjection(tuple(indexed.values()),
                                     complete and models.complete and not unresolved, tuple(unresolved))
