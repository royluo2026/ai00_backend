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


def test_registry_search_supports_offset_and_domain_filter() -> None:
    entries = tuple(
        SimpleNamespace(
            capability_id=capability_id,
            capability_version_gid=index,
            owner_domain=domain,
            major_version=1,
        )
        for index, (capability_id, domain) in enumerate(
            (("craft.one", "craft"), ("craft.two", "craft"), ("digital_model.one", "digital_model")),
            start=100,
        )
    )

    class Store:
        def list_entries(self):
            return entries

    result = CapabilityGovernanceService(Store()).base_capability_registry_search(
        {"limit": 1, "offset": 1, "domain": "craft"}, _context(),
    )

    assert result["total"] == 2
    assert [item.capability_id for item in result["items"]] == ["craft.two"]
    assert result["offset"] == 1


def test_findings_group_root_cause_by_reason_and_capability_and_page_server_side() -> None:
    snapshot = SimpleNamespace(
        snapshot_gid=100,
        entries=(
            SimpleNamespace(capability_id="craft.bop.read", major_version=1, capability_version_gid=501, owner_domain="craft"),
            SimpleNamespace(capability_id="digital_model.model.read", major_version=1, capability_version_gid=502, owner_domain="digital_model"),
        ),
        document=SimpleNamespace(nodes=()),
    )
    subjects = lambda capability_id: (SimpleNamespace(capability_id=capability_id, major_version=1, evidence_key=""),)
    findings = (
        SimpleNamespace(code="gap", severity="blocking", fingerprint="fp-1", subjects=subjects("craft.bop.read"), evidence_keys=()),
        SimpleNamespace(code="gap", severity="blocking", fingerprint="fp-2", subjects=subjects("craft.bop.read"), evidence_keys=()),
        SimpleNamespace(code="gap", severity="warning", fingerprint="fp-3", subjects=subjects("digital_model.model.read"), evidence_keys=()),
    )

    class Store:
        def latest_snapshot(self):
            return snapshot

        def get_findings(self, snapshot_gid):
            return findings

        def get_snapshot(self, snapshot_gid):
            return snapshot if snapshot_gid == 100 else None

    result = CapabilityGovernanceService(Store()).base_capability_finding_search(
        {"limit": 1, "offset": 1, "domain": "craft", "reason_code": "gap"}, _context(),
    )

    assert result["total"] == 2
    assert result["root_cause_total"] == 1
    assert result["findings"][0]["root_cause_key"] == "gap:craft.bop.read@1"
    assert result["findings"][0]["root_cause_count"] == 2
    assert result["offset"] == 1


def test_snapshot_summary_returns_bounded_root_cause_groups_for_agent() -> None:
    snapshot = SimpleNamespace(
        snapshot_gid=100,
        document=SimpleNamespace(product_release_id="catalog-r1", snapshot_hash="snapshot-hash"),
        entries=(
            SimpleNamespace(capability_id="craft.bop.read", major_version=1, capability_version_gid=501, owner_domain="craft"),
            SimpleNamespace(capability_id="digital_model.model.read", major_version=1, capability_version_gid=502, owner_domain="digital_model"),
        ),
    )
    findings = (
        {"finding_gid": "1", "code": "gap", "reason_code": "gap", "root_cause_key": "gap:craft.bop.read@1", "root_cause_label": "缺少实现绑定 · craft.bop.read@1", "root_cause_count": 2, "severity": "blocking", "status": "open", "domains": ("craft",), "evidence": ("provider:craft",)},
        {"finding_gid": "2", "code": "gap", "reason_code": "gap", "root_cause_key": "gap:craft.bop.read@1", "root_cause_label": "缺少实现绑定 · craft.bop.read@1", "root_cause_count": 2, "severity": "blocking", "status": "open", "domains": ("craft",), "evidence": ("provider:craft",)},
        {"finding_gid": "3", "code": "provider_missing", "reason_code": "provider_missing", "root_cause_key": "provider_missing:digital_model.model.read@1", "root_cause_label": "缺少 Provider · digital_model.model.read@1", "severity": "warning", "status": "open", "domains": ("digital_model",), "evidence": ("provider:digital",)},
    )

    class Store:
        def latest_snapshot(self):
            return snapshot

        def get_findings(self, snapshot_gid):
            return findings

        def get_snapshot(self, snapshot_gid):
            return snapshot if snapshot_gid == 100 else None

    result = CapabilityGovernanceService(Store()).base_capability_governance_snapshot_summary_get(
        {"limit": 1}, _context(),
    )

    assert result["snapshot_gid"] == "100"
    assert result["catalog_release"] == "catalog-r1"
    assert result["capability_total"] == 2
    assert result["finding_total"] == 3
    assert result["root_cause_total"] == 2
    assert result["blocking_total"] == 2
    assert len(result["root_causes"]) == 1
    assert result["root_causes"][0]["root_cause_key"] == "gap:craft.bop.read@1"
    assert result["root_causes"][0]["finding_count"] == 2
    assert result["next_offset"] == 1
