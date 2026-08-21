from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityOutput, CapabilitySpec, EvidenceRef
from backend.platform_sdk.ids import next_gid

from ..application.pbom import PbomService
from ..domain.pbom import PbomVersion, PbomVersionStatus
from ..infrastructure.repositories.pbom import SqlPbomRepository


PBOM_CAPABILITY_IDS = (
    "craft.pbom.version.create", "craft.pbom.version.get", "craft.pbom.version.search",
    "craft.pbom.version.submit", "craft.pbom.version.publish", "craft.pbom.version.archive",
    "craft.pbom.version.compare", "craft.pbom.draft.change.preview",
    "craft.pbom.draft.change.apply", "craft.pbom.part.search", "craft.pbom.import.preview",
)

repository = SqlPbomRepository()
service = PbomService(repository)


def _get(payload: dict, _context: CapabilityContext) -> CapabilityOutput:
    version = service.get(str(payload["version_gid"]))
    return CapabilityOutput(data=asdict(version))


def _search(payload: dict, _context: CapabilityContext) -> CapabilityOutput:
    rows = repository.search_versions(payload.get("project_ref"), int(payload.get("limit", 50)))
    return CapabilityOutput(data={"items": [asdict(row) for row in rows]})


def _create(payload: dict, _context: CapabilityContext) -> CapabilityOutput:
    version = PbomVersion(
        gid=str(next_gid()), project_ref=str(payload.get("project_ref") or payload.get("project_gid") or ""), version_tag=str(payload["version_tag"]),
        name=str(payload.get("name") or payload["version_tag"]), source_type=str(payload.get("source_type") or "native"),
        knowledge_revision_ref=payload.get("knowledge_revision_ref"), ontology_release_ref=payload.get("ontology_release_ref"),
        revision_commit_ref=payload.get("revision_commit_ref"),
    )
    repository.create_version(version)
    return CapabilityOutput(data=asdict(version), evidence=(EvidenceRef(kind="craft.pbom.version", reference=f"craft://pbom/version/{version.gid}"),))


def _transition(target: PbomVersionStatus):
    def handler(payload: dict, _context: CapabilityContext) -> CapabilityOutput:
        return CapabilityOutput(data=service.transition(str(payload["version_gid"]), target))
    return handler


def _parts(payload: dict, _context: CapabilityContext) -> CapabilityOutput:
    version_gid = str(payload["version_gid"])
    service.get(version_gid)
    return CapabilityOutput(data={"version_gid": version_gid, "items": repository.list_parts(version_gid, payload.get("query"), int(payload.get("limit", 50)))})


def _compare(payload: dict, _context: CapabilityContext) -> CapabilityOutput:
    before = repository.list_parts(str(payload["from_version_gid"]), limit=10000)
    after = repository.list_parts(str(payload["to_version_gid"]), limit=10000)
    key = lambda row: str(row.get("component_id") or row.get("part_no") or row["gid"])
    left, right = {key(row): row for row in before}, {key(row): row for row in after}
    return CapabilityOutput(data={
        "added": [right[item] for item in sorted(set(right) - set(left))],
        "removed": [left[item] for item in sorted(set(left) - set(right))],
        "changed": [{"identity": item, "before": left[item], "after": right[item]} for item in sorted(set(left) & set(right)) if left[item] != right[item]],
    })


def _preview(payload: dict, _context: CapabilityContext) -> CapabilityOutput:
    version = service.get(str(payload["version_gid"])); version.require_mutable()
    canonical = json.dumps(payload.get("changes", []), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return CapabilityOutput(data={"preview_gid": f"pbom_preview_{hashlib.sha256(canonical.encode()).hexdigest()[:24]}", "version_gid": version.gid, "changes": payload.get("changes", [])})


def _apply(payload: dict, _context: CapabilityContext) -> CapabilityOutput:
    version_gid = str(payload["version_gid"])
    results = [service.change_part(version_gid, change) for change in payload.get("changes", [])]
    return CapabilityOutput(data={"version_gid": version_gid, "applied": len(results), "results": results})


def _import_preview(payload: dict, _context: CapabilityContext) -> CapabilityOutput:
    document = payload["document"]
    raw = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    rows = document.get("parts", []) if isinstance(document, dict) else []
    return CapabilityOutput(data={"import_preview_gid": f"pbom_import_{hashlib.sha256(raw).hexdigest()[:24]}", "content_sha256": hashlib.sha256(raw).hexdigest(), "part_count": len(rows)})


def register_pbom_capabilities(registry: Any) -> None:
    handlers = {
        "craft.pbom.version.create": _create, "craft.pbom.version.get": _get, "craft.pbom.version.search": _search,
        "craft.pbom.version.submit": _transition(PbomVersionStatus.SUBMITTED),
        "craft.pbom.version.publish": _transition(PbomVersionStatus.PUBLISHED),
        "craft.pbom.version.archive": _transition(PbomVersionStatus.ARCHIVED),
        "craft.pbom.version.compare": _compare, "craft.pbom.draft.change.preview": _preview,
        "craft.pbom.draft.change.apply": _apply, "craft.pbom.part.search": _parts,
        "craft.pbom.import.preview": _import_preview,
    }
    writes = {item for item in PBOM_CAPABILITY_IDS if item not in {"craft.pbom.version.get", "craft.pbom.version.search", "craft.pbom.version.compare", "craft.pbom.part.search", "craft.pbom.import.preview", "craft.pbom.draft.change.preview"}}
    for capability_id in PBOM_CAPABILITY_IDS:
        registry.register(CapabilitySpec(
            id=capability_id, owner="craft", description=capability_id,
            use_when="A PBOM version is the explicit business subject.", do_not_use_when="The subject is BOP or GBOP.",
            risk="write" if capability_id in writes else "read", confirmation="user" if capability_id in writes else "none",
            idempotent=capability_id.endswith("apply") or capability_id.endswith("archive"), permissions=("craft.pbom.write",) if capability_id in writes else (),
            plugin_callable=True, input_schema={"type": "object"}, output_schema={"type": "object"},
            effects=(("write" if capability_id in writes else "read") + ":craft.pbom",), tags=("craft", "pbom"),
        ), handlers[capability_id])


__all__ = ["PBOM_CAPABILITY_IDS", "register_pbom_capabilities"]
