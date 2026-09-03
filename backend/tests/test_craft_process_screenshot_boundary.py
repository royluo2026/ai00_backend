from __future__ import annotations

import pytest

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext
from plugins.craft.craft_backend.capabilities.process_screenshot import (
    ProcessScreenshotProvider,
    register_process_screenshot_capability,
)
from plugins.craft.craft_backend.services.execution_structure import BopAggregate, _normalize


ARTIFACT = {
    "artifact_id": "artifact_capture_1",
    "media_type": "image/png",
    "sha256": "a" * 64,
    "byte_size": 2048,
    "version": 1,
}


def test_execution_plan_projects_products_and_typed_resource_codes():
    aggregate = BopAggregate(
        version={"gid": "bop-1", "project_gid": "project-1", "revision": 7},
        entries=({
            "gid": "op-10", "parent_gid": None, "node_type": "operation",
            "sort_order": 10, "title": "Install", "meta": {},
        },),
        links=(
            {
                "entry_gid": "op-10", "link_type": "pbom_part", "entity_gid": "part-1",
                "entity_data": {"part_no": "P-01", "action": "install"},
            },
            {
                "entry_gid": "op-10", "link_type": "tool", "entity_gid": "tool-1",
                "entity_data": {"code": "T-01"},
            },
        ),
    )

    operation = _normalize(aggregate)["operations"][0]

    assert operation["products"] == [{"product_ref": "P-01", "action": "install"}]
    assert operation["resources"] == [{"resource_type": "tool", "code": "T-01"}]


def test_execution_structure_repository_reads_codes_from_craft_resource_authority():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "plugins/craft/craft_backend/services/execution_structure.py"
    ).read_text(encoding="utf-8")

    assert "LEFT JOIN workmanship_craft_resource_requirements" in source
    assert "r.code AS resource_code" in source


class ScreenshotRepository:
    def __init__(self):
        self.rows = {}

    def attach(self, *, bop_version_gid, operation_id, capture_run_id, artifact_ref, actor_gid):
        key = bop_version_gid, operation_id, capture_run_id
        current = self.rows.get(key)
        if current and current["artifact_ref"]["sha256"] != artifact_ref["sha256"]:
            raise CapabilityBusinessError("idempotency_conflict", "different artifact")
        if current:
            return current
        row = {
            "screenshot_gid": "shot-1",
            "bop_version_gid": bop_version_gid,
            "operation_id": operation_id,
            "capture_run_id": capture_run_id,
            "artifact_ref": artifact_ref,
        }
        self.rows[key] = row
        return row


def context():
    return CapabilityContext(user_gid="user-1", team_gid="team-1")


def payload(artifact=ARTIFACT):
    return {
        "bop_version_gid": "bop-1",
        "operation_id": "op-10",
        "capture_run_id": "run-1",
        "artifact_ref": artifact,
    }


def test_attach_same_run_operation_is_idempotent_and_artifact_is_verified():
    repository = ScreenshotRepository()
    verified = []

    def require_artifact(ref, _context, *, resource_refs):
        verified.append((ref, resource_refs))
        return ref

    provider = ProcessScreenshotProvider(repository, require_artifact)
    first = provider.attach(payload(), context())
    second = provider.attach(payload(), context())

    assert second.data["screenshot_gid"] == first.data["screenshot_gid"]
    assert verified == [
        (ARTIFACT, ("craft-bop-version:bop-1",)),
        (ARTIFACT, ("craft-bop-version:bop-1",)),
    ]
    assert first.evidence[0].digest == "sha256:" + ARTIFACT["sha256"]


def test_attach_rejects_non_image_and_conflicting_retry():
    repository = ScreenshotRepository()
    provider = ProcessScreenshotProvider(repository, lambda ref, *_args, **_kwargs: ref)

    with pytest.raises(CapabilityBusinessError) as invalid:
        provider.attach(payload({**ARTIFACT, "media_type": "text/plain"}), context())
    assert invalid.value.code == "screenshot_artifact_invalid"

    provider.attach(payload(), context())
    with pytest.raises(CapabilityBusinessError) as conflict:
        provider.attach(payload({**ARTIFACT, "sha256": "b" * 64}), context())
    assert conflict.value.code == "idempotency_conflict"


def test_attach_rejects_an_artifact_resolver_that_does_not_confirm_the_exact_ref():
    replacement = {**ARTIFACT, "sha256": "c" * 64}
    provider = ProcessScreenshotProvider(
        ScreenshotRepository(), lambda _ref, *_args, **_kwargs: replacement
    )

    with pytest.raises(CapabilityBusinessError) as invalid:
        provider.attach(payload(), context())

    assert invalid.value.code == "screenshot_artifact_invalid"


def test_attach_translates_artifact_lookup_failure_to_a_stable_domain_error():
    def unavailable(*_args, **_kwargs):
        raise LookupError("artifact_not_found")

    provider = ProcessScreenshotProvider(ScreenshotRepository(), unavailable)
    with pytest.raises(CapabilityBusinessError) as invalid:
        provider.attach(payload(), context())

    assert invalid.value.code == "screenshot_artifact_invalid"


def test_screenshot_attach_contract_is_closed_and_governed():
    class Registry:
        def register(self, spec, handler, *, descriptor):
            self.spec = spec
            self.descriptor = descriptor

    registry = Registry()
    register_process_screenshot_capability(
        registry, ScreenshotRepository(), lambda ref, *_args, **_kwargs: ref
    )

    assert registry.spec.id == "craft.process_screenshot.attach"
    assert registry.spec.input_schema["additionalProperties"] is False
    assert registry.spec.output_schema["additionalProperties"] is False
    assert registry.descriptor.idempotency_policy == "required"
    assert registry.descriptor.evidence_policy == "required"
