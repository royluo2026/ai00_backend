from __future__ import annotations

from types import SimpleNamespace

from backend.capability_governance_test.service import CapabilityGovernanceService


def _context():
    return SimpleNamespace(user_gid="admin", governance_permissions=("system.capability.read",))


def test_registry_search_reports_full_totals_separately_from_page() -> None:
    entries = tuple(
        SimpleNamespace(
            capability_id=capability_id,
            capability_version_gid=index,
            owner_domain="base" if capability_id.startswith("base.capability_") else "craft",
            major_version=1,
        )
        for index, capability_id in enumerate(
            ("craft.one", "base.capability_health.get", "craft.two", "craft.three"),
            start=100,
        )
    )

    class Store:
        def list_entries(self):
            return entries

    result = CapabilityGovernanceService(Store()).base_capability_registry_search({"limit": 2}, _context())

    assert len(result["items"]) == 2
    assert result["total"] == 4
    assert result["product_capability_total"] == 3
    assert result["governance_extension_capability_total"] == 1


def test_finding_search_reports_full_total_before_returning_page() -> None:
    snapshot = SimpleNamespace(snapshot_gid=100, entries=(), document=SimpleNamespace(nodes=()))
    findings = tuple(
        {"finding_gid": str(index), "code": "gap", "severity": "warning", "fingerprint": f"fp-{index}"}
        for index in range(3)
    )

    class Store:
        def latest_snapshot(self):
            return snapshot

        def get_findings(self, snapshot_gid):
            return findings

        def get_snapshot(self, snapshot_gid):
            return snapshot if snapshot_gid == 100 else None

    result = CapabilityGovernanceService(Store()).base_capability_finding_search({"limit": 1}, _context())

    assert len(result["findings"]) == 1
    assert result["total"] == 3
