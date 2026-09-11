"""Bounded semantic PLMXML document and alternate-hierarchy projection."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import posixpath
import time
from typing import BinaryIO, Mapping
from urllib.parse import urlsplit
from xml.parsers import expat
from xml.etree import ElementTree

from .plmxml_projection import PlmxmlLimitError, PlmxmlLimits, PlmxmlSecurityError, PlmxmlStructureError


class EnvironmentDocumentDependencyError(ValueError):
    pass


@dataclass(frozen=True)
class EnvironmentDependency:
    location: str
    media_type: str


@dataclass(frozen=True)
class EnvironmentModelDocument:
    document_gid: str
    role: str
    display_name: str
    media_type: str
    artifact_ref: Mapping[str, object] | None
    source_identity_hash: str
    content_sha256: str
    portability: str
    connector_device_id: str | None = None


@dataclass(frozen=True)
class EnvironmentPlacementProjection:
    projection_identity: str
    stable_identity: str
    name: str
    parent_identity: str | None
    child_identities: tuple[str, ...]
    visible: bool


@dataclass(frozen=True)
class AlternateHierarchyProjection:
    name: str
    projection_identity: str
    root_refs: tuple[str, ...]
    root_placement_identity: str | None = None
    placements: tuple[EnvironmentPlacementProjection, ...] = ()


@dataclass(frozen=True)
class EnvironmentImportProjection:
    hierarchies: tuple[AlternateHierarchyProjection, ...]
    dependencies: tuple[EnvironmentDependency, ...]
    original_sha256: str
    algorithm_version: str


@dataclass(frozen=True)
class EnvironmentRuntimeModel:
    environment_gid: str
    documents: tuple[EnvironmentDependency | EnvironmentModelDocument, ...]
    hierarchies: tuple[AlternateHierarchyProjection, ...]


@dataclass(frozen=True)
class EnvironmentExportResult:
    content: bytes
    semantic_hash: str
    report: Mapping[str, object]


def runtime_model_to_dict(model: EnvironmentRuntimeModel) -> dict[str, object]:
    return {
        "environment_gid": model.environment_gid,
        "documents": [dict(item.__dict__) for item in model.documents if isinstance(item, EnvironmentModelDocument)],
        "hierarchies": [{
            "name": item.name,
            "projection_identity": item.projection_identity,
            "root_refs": list(item.root_refs),
            "root_placement_identity": item.root_placement_identity,
            "placements": [{**dict(placement.__dict__), "child_identities": list(placement.child_identities)} for placement in item.placements],
        } for item in model.hierarchies],
    }


def runtime_model_from_dict(value: Mapping[str, object]) -> EnvironmentRuntimeModel:
    try:
        documents = tuple(EnvironmentModelDocument(**dict(item)) for item in value.get("documents", ()))
        hierarchies = tuple(AlternateHierarchyProjection(
            name=str(item["name"]), projection_identity=str(item["projection_identity"]),
            root_refs=tuple(str(ref) for ref in item.get("root_refs", ())),
            root_placement_identity=(str(item["root_placement_identity"]) if item.get("root_placement_identity") is not None else None),
            placements=tuple(EnvironmentPlacementProjection(
                projection_identity=str(placement["projection_identity"]),
                stable_identity=str(placement["stable_identity"]), name=str(placement.get("name") or ""),
                parent_identity=(str(placement["parent_identity"]) if placement.get("parent_identity") is not None else None),
                child_identities=tuple(str(child) for child in placement.get("child_identities", ())),
                visible=bool(placement.get("visible", True)),
            ) for placement in item.get("placements", ())),
        ) for item in value.get("hierarchies", ()))
        model = EnvironmentRuntimeModel(environment_gid=str(value["environment_gid"]), documents=documents, hierarchies=hierarchies)
    except (KeyError, TypeError, ValueError) as exc:
        raise EnvironmentDocumentDependencyError("frozen_runtime_model_invalid") from exc
    if not model.environment_gid or not model.documents:
        raise EnvironmentDocumentDependencyError("frozen_runtime_model_invalid")
    return model


def _local_name(value: str) -> str:
    return value.rsplit("}", 1)[-1]


def _dependency(location: str) -> EnvironmentDependency | None:
    clean = location.split("#", 1)[0].strip()
    parsed = urlsplit(clean)
    if parsed.scheme:
        raise PlmxmlSecurityError("unsupported_external_uri_scheme")
    lower = clean.casefold()
    if lower.endswith((".plmxml", ".xml")):
        return EnvironmentDependency(clean, "application/plmxml+xml")
    if lower.endswith(".jt"):
        return EnvironmentDependency(clean, "model/vnd.jt")
    return None


def import_environment_plmxml(
    stream: BinaryIO, *, limits: PlmxmlLimits, algorithm_version: str
) -> EnvironmentImportProjection:
    started = time.monotonic()
    digest = hashlib.sha256()
    hierarchies: list[AlternateHierarchyProjection] = []
    dependencies: list[EnvironmentDependency] = []
    seen_dependencies: set[tuple[str, str]] = set()
    total_bytes = elements = depth = projected_instances = 0
    hierarchy: dict[str, object] | None = None
    occurrence: dict[str, object] | None = None

    def start(name: str, attrs: dict[str, str]) -> None:
        nonlocal elements, depth, hierarchy, occurrence
        depth += 1
        elements += 1
        if depth > limits.max_depth:
            raise PlmxmlLimitError("max_depth")
        if elements > limits.max_elements:
            raise PlmxmlLimitError("max_elements")
        if len(attrs) > limits.max_attributes_per_element:
            raise PlmxmlLimitError("max_attributes_per_element")
        local = _local_name(name)
        if local == "include" and "href" in attrs:
            raise PlmxmlSecurityError("xinclude_forbidden")
        if local == "ProductView" and attrs.get("usage") == "variant":
            root_refs = tuple(item.lstrip("#") for item in attrs.get("rootRefs", "").split())
            primary = attrs.get("primaryOccurrenceRef", "").lstrip("#")
            hierarchy = {
                "name": attrs.get("name", ""), "id": attrs.get("id", ""),
                "root_refs": root_refs, "primary": primary, "occurrences": [],
            }
        elif local == "Occurrence" and hierarchy is not None:
            occurrence = {
                "id": attrs.get("id", ""), "name": attrs.get("name", ""),
                "children": tuple(item.lstrip("#") for item in attrs.get("occurrenceRefs", "").split()),
                "visible": attrs.get("visible", "true").casefold() != "false", "ngid": "",
            }
            hierarchy["occurrences"].append(occurrence)  # type: ignore[union-attr]
        elif local == "ApplicationRef" and occurrence is not None:
            if attrs.get("application") == "__TC-VIS_NGID" and attrs.get("label"):
                occurrence["ngid"] = attrs["label"]
        values = []
        if local == "ProductInstance":
            values.append(attrs.get("partRef", ""))
        if local == "Representation":
            values.append(attrs.get("location", ""))
        for value in values:
            item = _dependency(value)
            if item is None:
                continue
            if len(dependencies) >= limits.max_references:
                raise PlmxmlLimitError("max_external_references")
            key = (item.location.casefold().replace("\\", "/"), item.media_type)
            if key not in seen_dependencies:
                seen_dependencies.add(key)
                dependencies.append(item)

    def end(name: str) -> None:
        nonlocal depth, hierarchy, occurrence, projected_instances
        local = _local_name(name)
        if local == "Occurrence":
            occurrence = None
        elif local == "ProductView" and hierarchy is not None:
            rows = hierarchy["occurrences"]  # type: ignore[assignment]
            parent_by_child = {
                child: str(row["id"])
                for row in rows
                for child in row["children"]
            }
            placements = tuple(
                EnvironmentPlacementProjection(
                    projection_identity=str(row["id"]),
                    stable_identity=("ngid:" + hashlib.sha256(str(row["ngid"]).encode()).hexdigest()
                                     if row["ngid"] else "occurrence:" + str(row["id"])),
                    name=str(row["name"]),
                    parent_identity=parent_by_child.get(str(row["id"])),
                    child_identities=tuple(row["children"]),
                    visible=bool(row["visible"]),
                )
                for row in rows
            )
            projected_instances += len(placements)
            if projected_instances > limits.max_projected_instances:
                raise PlmxmlLimitError("max_projected_instances")
            primary = str(hierarchy["primary"])
            root_refs = tuple(hierarchy["root_refs"])
            hierarchies.append(AlternateHierarchyProjection(
                name=str(hierarchy["name"]), projection_identity=str(hierarchy["id"]),
                root_refs=root_refs, root_placement_identity=primary or (root_refs[0] if root_refs else None),
                placements=placements,
            ))
            hierarchy = None
        depth -= 1

    def forbidden(*_args: object) -> None:
        raise PlmxmlSecurityError("dtd_or_entity_forbidden")

    parser = expat.ParserCreate(namespace_separator="}")
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.StartDoctypeDeclHandler = forbidden
    parser.EntityDeclHandler = forbidden
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
            if time.monotonic() - started > limits.max_parse_seconds:
                raise PlmxmlLimitError("max_parse_seconds")
            digest.update(chunk)
            parser.Parse(chunk, False)
        parser.Parse(b"", True)
    except (PlmxmlLimitError, PlmxmlSecurityError, TypeError):
        raise
    except expat.ExpatError as exc:
        raise PlmxmlStructureError("malformed_xml") from exc
    return EnvironmentImportProjection(
        tuple(hierarchies), tuple(dependencies), "sha256:" + digest.hexdigest(), algorithm_version
    )


_PLMXML_NS = "http://www.plmxml.org/Schemas/PLMXMLSchema"


def _semantic_payload(model: EnvironmentRuntimeModel) -> dict[str, object]:
    return {
        "environment_gid": model.environment_gid,
        "documents": [item.__dict__ for item in model.documents],
        "hierarchies": [
            {
                "name": item.name,
                "projection_identity": item.projection_identity,
                "root_placement_identity": item.root_placement_identity,
                "placements": [placement.__dict__ for placement in item.placements],
            }
            for item in model.hierarchies
        ],
    }


def _document_location(document: EnvironmentDependency | EnvironmentModelDocument) -> str:
    return document.location if isinstance(document, EnvironmentDependency) else document.display_name


def export_environment_plmxml(model: EnvironmentRuntimeModel) -> EnvironmentExportResult:
    """Generate a deterministic VisMockup-readable semantic PLMXML package."""
    ElementTree.register_namespace("", _PLMXML_NS)
    root = ElementTree.Element(f"{{{_PLMXML_NS}}}PLMXML", {
        "schemaVersion": "6", "author": "AI00", "environmentGid": model.environment_gid,
    })
    for index, document in enumerate(model.documents, start=1):
        location = _document_location(document)
        if document.media_type == "model/vnd.jt":
            view = ElementTree.SubElement(root, f"{{{_PLMXML_NS}}}ProductRevisionView", {
                "id": f"document-view-{index}", "name": posixpath.basename(location),
            })
            ElementTree.SubElement(view, f"{{{_PLMXML_NS}}}Representation", {
                "id": f"document-representation-{index}", "format": "JT", "location": location,
            })
        else:
            graph = ElementTree.SubElement(root, f"{{{_PLMXML_NS}}}InstanceGraph", {
                "id": f"document-graph-{index}", "rootRefs": f"document-instance-{index}",
            })
            ElementTree.SubElement(graph, f"{{{_PLMXML_NS}}}ProductInstance", {
                "id": f"document-instance-{index}", "name": posixpath.basename(location),
                "partRef": location,
            })
    for hierarchy in model.hierarchies:
        attrs = {
            "id": hierarchy.projection_identity,
            "name": hierarchy.name,
            "usage": "variant",
        }
        if hierarchy.root_placement_identity:
            attrs["primaryOccurrenceRef"] = hierarchy.root_placement_identity
        view = ElementTree.SubElement(root, f"{{{_PLMXML_NS}}}ProductView", attrs)
        for placement in hierarchy.placements:
            occurrence_attrs = {
                "id": placement.projection_identity,
                "name": placement.name,
                "visible": "true" if placement.visible else "false",
            }
            if placement.child_identities:
                occurrence_attrs["occurrenceRefs"] = " ".join(placement.child_identities)
            ElementTree.SubElement(view, f"{{{_PLMXML_NS}}}Occurrence", occurrence_attrs)
    content = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True, short_empty_elements=True)
    semantic_json = json.dumps(_semantic_payload(model), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    semantic_hash = "sha256:" + hashlib.sha256(semantic_json.encode("utf-8")).hexdigest()
    placement_count = sum(len(item.placements) for item in model.hierarchies)
    report: Mapping[str, object] = {
        "semantic_hash": semantic_hash,
        "document_count": len(model.documents),
        "hierarchy_count": len(model.hierarchies),
        "placement_count": placement_count,
        "unresolved_refs": [],
        "omitted_ai00_only_records": [],
        "original_artifact_passthrough_eligible": False,
    }
    return EnvironmentExportResult(content=content, semantic_hash=semantic_hash, report=report)


def _identity(value: str) -> str:
    return posixpath.normpath(value.replace("\\", "/")).casefold()


def resolve_package_reference(reference: str, *, package_root: str) -> str:
    """Resolve only package-relative references; never escape into the host filesystem."""
    raw = str(reference or "").replace("\\", "/")
    parsed = urlsplit(raw)
    if parsed.scheme or raw.startswith("/"):
        raise PlmxmlSecurityError("external_reference_outside_package")
    root = posixpath.normpath(str(package_root or "").replace("\\", "/")).strip("/")
    candidate = posixpath.normpath(posixpath.join(root, raw))
    if not root or candidate == ".." or candidate.startswith("../") or not (candidate == root or candidate.startswith(root + "/")):
        raise PlmxmlSecurityError("external_reference_outside_package")
    return candidate


def validate_document_dependency_graph(
    *, primary: str, supplements: Mapping[str, tuple[str, ...]]
) -> dict[str, tuple[str, ...]]:
    primary_key = _identity(primary)
    names = {primary_key: primary, **{_identity(name): name for name in supplements}}
    graph: dict[str, tuple[str, ...]] = {primary_key: ()}
    for name, raw_dependencies in supplements.items():
        key = _identity(name)
        graph[key] = tuple(dict.fromkeys(_identity(item) for item in raw_dependencies))
        if primary_key in graph[key]:
            raise EnvironmentDocumentDependencyError("model_document_dependency_cycle")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise EnvironmentDocumentDependencyError("model_document_dependency_cycle")
        if node in visited:
            return
        visiting.add(node)
        for child in graph.get(node, ()):
            if child in graph:
                visit(child)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)
    return {names[key]: tuple(names.get(child, child) for child in deps) for key, deps in graph.items()}


__all__ = [
    "AlternateHierarchyProjection", "EnvironmentDependency", "EnvironmentDocumentDependencyError",
    "EnvironmentExportResult", "EnvironmentImportProjection", "EnvironmentModelDocument", "EnvironmentPlacementProjection",
    "EnvironmentRuntimeModel", "export_environment_plmxml", "import_environment_plmxml",
    "resolve_package_reference", "runtime_model_from_dict", "runtime_model_to_dict", "validate_document_dependency_graph",
]
