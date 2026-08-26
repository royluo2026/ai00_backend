from __future__ import annotations

import json
from pathlib import Path

from backend.capability_v2.catalog_audit import CatalogAuditReport
from backend.capability_v2.completion import CompletionReport
from backend.capability_v2 import release_gate
from backend.capability_v2.release_gate import ReleaseGateReport


def test_release_gate_fails_when_web_bypasses_or_contract_debt_exists() -> None:
    completion = CompletionReport(
        domains=(), plugin_agent_gateway_only=True, independent_domains=11,
        sync_production_paths=1, async_production_paths=1, cross_domain_sql=0,
        internal_imports=0, consumer_bypasses=0, catalog_capabilities=1,
        failed=("web_consumer_bypasses:1",), web_consumer_bypasses=1,
    )
    audit = CatalogAuditReport(
        stable_count=1, generic_operation_count=1, open_arguments_count=1,
        default_all_exposure_count=1, generic_operation_ids=("base.change.apply",),
    )

    result = ReleaseGateReport(completion=completion, audit=audit)

    assert result.passed is False
    assert result.completion.web_consumer_bypasses == 1
    assert result.audit.open_arguments_count == 1
    assert result.audit.default_all_exposure_count == 1


def test_release_gate_fails_when_generic_operations_are_not_atomicity_governed() -> None:
    completion = CompletionReport(
        domains=(), plugin_agent_gateway_only=True, independent_domains=11,
        sync_production_paths=0, async_production_paths=0, cross_domain_sql=0,
        internal_imports=0, consumer_bypasses=0, catalog_capabilities=1,
        failed=(), web_consumer_bypasses=0,
    )
    audit = CatalogAuditReport(
        stable_count=1, generic_operation_count=1, open_arguments_count=0,
        default_all_exposure_count=0, generic_operation_ids=("project.change.apply",),
    )

    assert ReleaseGateReport(completion=completion, audit=audit).passed is False


def test_release_gate_blocks_replaced_orchestration_target(tmp_path: Path, monkeypatch) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps({"capabilities": [
        {"id": "base.old", "major_version": 1, "lifecycle_status": "stable", "owner_domain": "base"},
        {"id": "base.new", "major_version": 1, "lifecycle_status": "stable", "owner_domain": "base"},
    ]}), encoding="utf-8")
    atomicity_path = tmp_path / "atomicity.json"
    atomicity_path.write_text(json.dumps({"dispositions": [{
        "capability_id": "base.old", "major_version": 1, "disposition": "split",
        "replacement_capabilities": ["base.new"], "evidence_refs": ["review.md"],
    }]}), encoding="utf-8")
    governance = tmp_path / "docs" / "governance"
    governance.mkdir(parents=True)
    for name, document in {
        "task_tool_registry.json": {"registry_kind": "task_tool", "entries": [
            {"task_id": "task.old", "capability_id": "base.old", "owner_domain": "base"},
        ]},
        "bff_capability_registry.json": {"registry_kind": "bff_capability", "entries": []},
        "business_capability_ledger.json": {"registry_kind": "business_capability", "entries": []},
    }.items():
        (governance / name).write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(release_gate, "evaluate_completion", lambda *args, **kwargs: CompletionReport(
        domains=(), plugin_agent_gateway_only=True, independent_domains=0,
        sync_production_paths=0, async_production_paths=0, cross_domain_sql=0,
        internal_imports=0, consumer_bypasses=0, catalog_capabilities=0, failed=(),
    ))
    monkeypatch.setattr(release_gate, "audit_catalog", lambda _path: CatalogAuditReport(
        stable_count=2, generic_operation_count=0, open_arguments_count=0,
        default_all_exposure_count=0, generic_operation_ids=(),
    ))

    report = release_gate.evaluate_release_gate(
        tmp_path, web_root=tmp_path, catalog_path=catalog_path, atomicity_path=atomicity_path,
    )

    assert report.orchestration[0].serialized()["target_failures"][0]["reason_code"] == "target_replaced"
