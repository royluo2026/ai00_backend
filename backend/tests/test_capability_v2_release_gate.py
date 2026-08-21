from __future__ import annotations

from backend.capability_v2.catalog_audit import CatalogAuditReport
from backend.capability_v2.completion import CompletionReport
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
