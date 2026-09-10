"""Bounded, non-resolving PLMXML projection for Simulation snapshots."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
import time
from typing import BinaryIO
from xml.parsers import expat


class PlmxmlError(ValueError):
    """Base error with a stable machine-readable reason in the message."""


class PlmxmlSecurityError(PlmxmlError):
    pass


class PlmxmlLimitError(PlmxmlError):
    pass


class PlmxmlStructureError(PlmxmlError):
    pass


@dataclass(frozen=True)
class PlmxmlLimits:
    max_bytes: int = 64 * 1024 * 1024
    max_elements: int = 750_000
    max_depth: int = 160
    max_string_length: int = 1_048_576
    max_references: int = 2_000_000
    max_attributes_per_element: int = 64
    max_inbound_references: int = 100_000
    max_projected_instances: int = 250_000
    max_parse_seconds: float = 30.0
    chunk_bytes: int = 64 * 1024


@dataclass(frozen=True)
class PlmxmlInstance:
    instance_id: str
    name: str
    bom_line: str
    item_id: str
    revision: str
    part_ref: str
    parent_instance_id: str | None
    parent_path: tuple[str, ...]
    application_label: str
    catia_occurrence_name: str
    transform_raw: tuple[str, ...]
    normalized_transform: tuple[str, ...]
    representation_locations: tuple[str, ...]
    pdm_occurrence_uid: str = ""
    absolute_occurrence_uid: str = ""
    clone_stable_chain: tuple[str, ...] = ()
    occurrence_path: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlmxmlProjection:
    schema_version: str
    author: str
    root_instance_ids: tuple[str, ...]
    instances: tuple[PlmxmlInstance, ...]
    algorithm_version: str
    stats: "PlmxmlParseStats"

    def by_bom_line(self, bom_line: str) -> tuple[PlmxmlInstance, ...]:
        return tuple(item for item in self.instances if item.bom_line == bom_line)


@dataclass(frozen=True)
class PlmxmlParseStats:
    total_bytes: int
    element_count: int
    reference_count: int
    maximum_depth: int


_BOM_LINE = re.compile(r"^(.+?/[^/;\s]+;\d+)(?:-|$)")
_REF_ATTRIBUTES = {
    "attributeRefs",
    "defaultProductViewRef",
    "instanceRefs",
    "partRef",
    "rootRefs",
}
_XINCLUDE_NAMESPACE = "http://www.w3.org/2001/XInclude"


def _application_payload(label: str, function: str) -> str:
    prefix = f"#PLMXML(PS_API-doc/{function}('"
    suffix = "'))"
    return label[len(prefix):-len(suffix)] if label.startswith(prefix) and label.endswith(suffix) else ""


def _current_state_path(label: str) -> tuple[str, ...]:
    values = tuple(value for value in _application_payload(label, "JT_PROP_NAME").split("\\0") if value)
    return values[1:] if values and values[0].startswith("CHLD") else values


def _clone_stable_chain(label: str) -> tuple[str, ...]:
    marker = '$$NGID<chain>="__PLM_CLONE_STABLE_INST_UID"'
    values = _application_payload(label, "NGID").split("\\0")
    try:
        start = values.index(marker) + 1
    except ValueError:
        return ()
    result: list[str] = []
    for value in values[start:]:
        if value.startswith("$$NGID<"):
            break
        if value:
            result.append(value)
    return tuple(result)


def _item_revision_from_path(value: str) -> tuple[str, str]:
    match = re.match(r"^([^/]+)/([^;]+);", value)
    return (match.group(1), match.group(2)) if match else ("", "")


def _local_name(name: str) -> tuple[str, str]:
    if "}" in name:
        namespace, local = name.rsplit("}", 1)
        return namespace, local
    return "", name


def _ref(value: str) -> str:
    return value.lstrip("#")


def _refs(value: str) -> tuple[str, ...]:
    return tuple(_ref(item) for item in value.split() if item)


def _normalize_number(value: str) -> str:
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise PlmxmlStructureError("invalid_transform") from exc
    if not number.is_finite():
        raise PlmxmlStructureError("invalid_transform")
    if number == 0:
        return "0"
    return format(number.normalize(), "f")


def _bom_line(name: str) -> str:
    match = _BOM_LINE.match(name.strip())
    return match.group(1) if match else ""


def parse_plmxml(
    stream: BinaryIO,
    limits: PlmxmlLimits | None = None,
    algorithm_version: str = "plmxml-projection.v1",
) -> PlmxmlProjection:
    """Parse a PLMXML byte stream without DTD, entity, XInclude, or external I/O."""
    limits = limits or PlmxmlLimits()
    started = time.monotonic()
    if limits.max_parse_seconds <= 0:
        raise PlmxmlLimitError("max_parse_seconds")

    document: dict[str, str] = {}
    instances: dict[str, dict[str, object]] = {}
    revisions: dict[str, dict[str, object]] = {}
    occurrences: list[dict[str, object]] = []
    current_instance: dict[str, object] | None = None
    current_revision: dict[str, object] | None = None
    current_occurrence: dict[str, object] | None = None
    transform_parts: list[str] | None = None
    element_text_lengths: list[int] = []
    depth = element_count = reference_count = total_bytes = maximum_depth = 0

    def check_time() -> None:
        if time.monotonic() - started > limits.max_parse_seconds:
            raise PlmxmlLimitError("max_parse_seconds")

    def start_element(name: str, attrs: dict[str, str]) -> None:
        nonlocal depth, element_count, reference_count, maximum_depth
        nonlocal current_instance, current_revision, current_occurrence, transform_parts
        check_time()
        depth += 1
        maximum_depth = max(maximum_depth, depth)
        element_count += 1
        if depth > limits.max_depth:
            raise PlmxmlLimitError("max_depth")
        if element_count > limits.max_elements:
            raise PlmxmlLimitError("max_elements")
        element_text_lengths.append(0)
        if len(attrs) > limits.max_attributes_per_element:
            raise PlmxmlLimitError("max_attributes_per_element")
        namespace, local = _local_name(name)
        if namespace == _XINCLUDE_NAMESPACE or local.lower() == "include" and "href" in attrs:
            raise PlmxmlSecurityError("xinclude_forbidden")
        for key, value in attrs.items():
            if len(key) > limits.max_string_length or len(value) > limits.max_string_length:
                raise PlmxmlLimitError("max_string_length")
            _, attr_local = _local_name(key)
            if attr_local in _REF_ATTRIBUTES:
                reference_count += len(value.split())
                if reference_count > limits.max_references:
                    raise PlmxmlLimitError("max_references")

        if local == "PLMXML":
            document.update(schema_version=attrs.get("schemaVersion", ""), author=attrs.get("author", ""))
        elif local == "InstanceGraph":
            document["root_refs"] = attrs.get("rootRefs", "")
        elif local == "ProductInstance":
            current_instance = {
                "id": attrs.get("id", ""),
                "name": attrs.get("name", ""),
                "part_ref": _ref(attrs.get("partRef", "")),
                "application_label": "",
                "transform": (),
            }
            instances[str(current_instance["id"])] = current_instance
            if len(instances) > limits.max_projected_instances:
                raise PlmxmlLimitError("max_projected_instances")
        elif local == "ProductRevisionView":
            current_revision = {
                "id": attrs.get("id", ""),
                "instance_refs": _refs(attrs.get("instanceRefs", "")),
                "user_values": {},
                "representations": [],
            }
            revisions[str(current_revision["id"])] = current_revision
        elif local == "Occurrence":
            current_occurrence = {
                "id": attrs.get("id", ""),
                "instance_refs": _refs(attrs.get("instanceRefs", "")),
                "user_values": {},
                "application_refs": {},
            }
            occurrences.append(current_occurrence)
        elif local == "ApplicationRef":
            if current_occurrence is not None:
                refs = current_occurrence["application_refs"]
                assert isinstance(refs, dict)
                refs[attrs.get("application", "")] = attrs.get("label", "")
            elif current_instance is not None:
                current_instance["application_label"] = attrs.get("label", "")
        elif local == "UserValue":
            target = current_occurrence or current_revision
            if target is not None:
                values = target["user_values"]
                assert isinstance(values, dict)
                values[attrs.get("title", "")] = attrs.get("value", "")
        elif local == "Representation" and current_revision is not None:
            values = current_revision["representations"]
            assert isinstance(values, list)
            values.append(attrs.get("location", ""))
        elif local == "Transform" and current_instance is not None:
            transform_parts = []

    def character_data(value: str) -> None:
        nonlocal transform_parts
        if not element_text_lengths:
            return
        element_text_lengths[-1] += len(value)
        if element_text_lengths[-1] > limits.max_string_length:
            raise PlmxmlLimitError("max_string_length")
        if transform_parts is not None:
            transform_parts.append(value)

    def end_element(name: str) -> None:
        nonlocal depth, current_instance, current_revision, current_occurrence, transform_parts
        _, local = _local_name(name)
        if local == "Transform" and current_instance is not None and transform_parts is not None:
            values = tuple("".join(transform_parts).split())
            if values and len(values) != 16:
                raise PlmxmlStructureError("invalid_transform")
            current_instance["transform"] = values
            transform_parts = None
        elif local == "ProductInstance":
            current_instance = None
        elif local == "ProductRevisionView":
            current_revision = None
        elif local == "Occurrence":
            current_occurrence = None
        element_text_lengths.pop()
        depth -= 1

    def forbidden(*_args: object) -> None:
        raise PlmxmlSecurityError("dtd_or_entity_forbidden")

    parser = expat.ParserCreate(namespace_separator="}")
    parser.StartElementHandler = start_element
    parser.EndElementHandler = end_element
    parser.CharacterDataHandler = character_data
    parser.StartDoctypeDeclHandler = forbidden
    parser.EntityDeclHandler = forbidden
    parser.UnparsedEntityDeclHandler = forbidden
    parser.ExternalEntityRefHandler = lambda *_args: forbidden()

    try:
        while True:
            chunk = stream.read(limits.chunk_bytes)
            if not chunk:
                break
            if not isinstance(chunk, (bytes, bytearray)):
                raise TypeError("PLMXML stream must yield bytes")
            total_bytes += len(chunk)
            if total_bytes > limits.max_bytes:
                raise PlmxmlLimitError("max_bytes")
            check_time()
            parser.Parse(chunk, False)
        parser.Parse(b"", True)
    except (PlmxmlError, TypeError):
        raise
    except expat.ExpatError as exc:
        raise PlmxmlStructureError("malformed_xml") from exc

    parents: dict[str, str] = {}
    for parent_id, instance in instances.items():
        revision = revisions.get(str(instance["part_ref"]))
        if revision is None:
            raise PlmxmlStructureError("unresolved_part_ref")
        for child_id in revision["instance_refs"]:  # type: ignore[index]
            if child_id not in instances:
                raise PlmxmlStructureError("unresolved_instance_ref")
            prior = parents.setdefault(child_id, parent_id)
            if prior != parent_id:
                raise PlmxmlStructureError("ambiguous_parent_ref")
    inbound_counts: dict[str, int] = {}
    for revision in revisions.values():
        for child_id in revision["instance_refs"]:  # type: ignore[index]
            inbound_counts[child_id] = inbound_counts.get(child_id, 0) + 1
            if inbound_counts[child_id] > limits.max_inbound_references:
                raise PlmxmlLimitError("max_inbound_references")

    occurrence_values: dict[str, str] = {}
    occurrence_paths: dict[str, tuple[str, ...]] = {}
    occurrence_metadata: dict[str, dict[str, object]] = {}
    for occurrence in occurrences:
        path = occurrence["instance_refs"]
        if not path:
            continue
        assert isinstance(path, tuple)
        if any(item not in instances for item in path):
            raise PlmxmlStructureError("unresolved_occurrence_ref")
        leaf = path[-1]
        values = occurrence["user_values"]
        assert isinstance(values, dict)
        catia_name = str(values.get("catiaOccurrenceName", ""))
        if catia_name:
            occurrence_values[leaf] = catia_name
        occurrence_paths[leaf] = path[:-1]
        occurrence_metadata[leaf] = occurrence

    def parent_path(instance_id: str) -> tuple[str, ...]:
        if instance_id in occurrence_paths:
            return occurrence_paths[instance_id]
        result: list[str] = []
        seen = {instance_id}
        current = instance_id
        while current in parents:
            current = parents[current]
            if current in seen:
                raise PlmxmlStructureError("cyclic_instance_ref")
            seen.add(current)
            result.append(current)
        result.reverse()
        return tuple(result)

    projected: list[PlmxmlInstance] = []
    for instance_id, instance in instances.items():
        revision = revisions[str(instance["part_ref"])]
        values = revision["user_values"]
        assert isinstance(values, dict)
        transform = instance["transform"]
        assert isinstance(transform, tuple)
        representations = revision["representations"]
        assert isinstance(representations, list)
        occurrence = occurrence_metadata.get(instance_id, {})
        occurrence_user_values = occurrence.get("user_values", {})
        assert isinstance(occurrence_user_values, dict)
        projected.append(
            PlmxmlInstance(
                instance_id=instance_id,
                name=str(instance["name"]),
                bom_line=_bom_line(str(instance["name"])),
                item_id=str(values.get("__PLM_ITEM_ID", "")),
                revision=str(values.get("__PLM_REVISION_ID", "")),
                part_ref=str(instance["part_ref"]),
                parent_instance_id=parents.get(instance_id),
                parent_path=parent_path(instance_id),
                application_label=str(instance["application_label"]),
                catia_occurrence_name=occurrence_values.get(instance_id, ""),
                transform_raw=transform,
                normalized_transform=tuple(_normalize_number(item) for item in transform),
                representation_locations=tuple(str(item) for item in representations if item),
                pdm_occurrence_uid=str(occurrence_user_values.get("__PLM_OCC_PDM_UID", "")),
                absolute_occurrence_uid=str(occurrence_user_values.get("__PLM_ABSOCC_UID", "")),
            )
        )

    current_state: list[tuple[tuple[str, ...], dict[str, object]]] = []
    for occurrence in occurrences:
        refs = occurrence["application_refs"]
        assert isinstance(refs, dict)
        path = _current_state_path(str(refs.get("__TC-VIS_APP", "")))
        if path:
            current_state.append((path, occurrence))

    if current_state:
        root_by_bom_line = {item.bom_line: item for item in projected if item.instance_id in _refs(document.get("root_refs", ""))}
        path_to_instance: dict[tuple[str, ...], str] = {}
        pdm_uids: set[str] = set()
        for path, occurrence in sorted(current_state, key=lambda value: (len(value[0]), value[0], str(value[1]["id"]))):
            if path in path_to_instance:
                raise PlmxmlStructureError("duplicate_occurrence_path")
            values = occurrence["user_values"]
            refs = occurrence["application_refs"]
            assert isinstance(values, dict) and isinstance(refs, dict)
            pdm_uid = str(values.get("__PLM_OCC_PDM_UID", ""))
            if pdm_uid and pdm_uid in pdm_uids:
                raise PlmxmlStructureError("duplicate_pdm_occurrence_uid")
            if pdm_uid:
                pdm_uids.add(pdm_uid)

            root = root_by_bom_line.get(_bom_line(path[0]))
            if root is None:
                raise PlmxmlStructureError("unresolved_current_state_root")
            if len(path) == 1:
                path_to_instance[path] = root.instance_id
                continue
            parent_id = root.instance_id if len(path) == 2 else path_to_instance.get(path[:-1])
            if parent_id is None:
                raise PlmxmlStructureError("unresolved_current_state_parent")
            instance_id = "occ:" + str(occurrence["id"])
            ancestor_ids = [root.instance_id]
            for depth_index in range(2, len(path)):
                ancestor = path_to_instance.get(path[:depth_index])
                if ancestor is None:
                    raise PlmxmlStructureError("unresolved_current_state_parent")
                ancestor_ids.append(ancestor)
            item_id, revision = _item_revision_from_path(path[-1])
            projected.append(PlmxmlInstance(
                instance_id=instance_id,
                name=path[-1],
                bom_line=_bom_line(path[-1]),
                item_id=item_id,
                revision=revision,
                part_ref="",
                parent_instance_id=parent_id,
                parent_path=tuple(ancestor_ids),
                application_label=str(refs.get("__TC-VIS_APP", "")),
                catia_occurrence_name=str(values.get("catiaOccurrenceName", "")),
                transform_raw=(),
                normalized_transform=(),
                representation_locations=(),
                pdm_occurrence_uid=pdm_uid,
                absolute_occurrence_uid=str(values.get("__PLM_ABSOCC_UID", "")),
                clone_stable_chain=_clone_stable_chain(str(refs.get("__TC-VIS_NGID", ""))),
                occurrence_path=path,
            ))
            path_to_instance[path] = instance_id
            if len(projected) > limits.max_projected_instances:
                raise PlmxmlLimitError("max_projected_instances")

    return PlmxmlProjection(
        schema_version=document.get("schema_version", ""),
        author=document.get("author", ""),
        root_instance_ids=_refs(document.get("root_refs", "")),
        instances=tuple(projected),
        algorithm_version=algorithm_version,
        stats=PlmxmlParseStats(
            total_bytes=total_bytes,
            element_count=element_count,
            reference_count=reference_count,
            maximum_depth=maximum_depth,
        ),
    )
