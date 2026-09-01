from __future__ import annotations

from types import SimpleNamespace


def _audit_types():
    from backend.capability_governance_test.business_audit import (
        AuditCapability,
        AuditEvidence,
        audit,
        collect_business_audit,
        root_cause_key,
    )

    return AuditCapability, AuditEvidence, audit, collect_business_audit, root_cause_key


def test_root_cause_key_is_exact_and_rule_specific():
    *_, root_cause_key = _audit_types()
    assert root_cause_key("business_rules_missing", "person.height.write", 1, None) == "business_rules_missing:person.height.write@1"
    assert root_cause_key("rule_test_ref_unresolved", "person.height.write", 1, "person.height.range") == "rule_test_ref_unresolved:person.height.write@1:person.height.range"


def test_evidence_rows_and_root_causes_are_counted_separately():
    _, AuditEvidence, audit, _, _ = _audit_types()
    evidence = tuple(AuditEvidence(
        reason_code="business_rules_missing", capability_id="person.height.write",
        major_version=1, domain="person", layer="C", evidence_ref=f"person/provider.py:{line}",
        remediation_family="declare_business_rule",
    ) for line in (10, 20))
    report = audit(evidence, snapshot_gid="snap-1")
    assert report.finding_count == 2
    assert report.root_cause_group_count == 1
    assert report.affected_capabilities == ("person.height.write@1",)
    assert report.shared_remediation_families == {"declare_business_rule": 2}


def test_cross_domain_conflict_is_one_group_with_all_capabilities_and_domains():
    _, AuditEvidence, audit, _, _ = _audit_types()
    keys = ("ergonomics.height.validate@1", "person.height.write@1")
    evidence = tuple(AuditEvidence(
        reason_code="cross_domain_conflict", capability_id=capability.rsplit("@", 1)[0],
        major_version=1, domain=domain, layer="F", evidence_ref=f"{domain}.height.range",
        remediation_family="resolve_formal_conflict", related_capability_keys=keys,
        related_domains=("ergonomics", "person"),
    ) for capability, domain in zip(reversed(keys), ("person", "ergonomics")))
    report = audit(evidence, snapshot_gid="snap-1")
    assert report.root_cause_group_count == 1
    assert report.root_causes[0].root_cause_key == "cross_domain_conflict:ergonomics.height.validate@1"
    assert report.root_causes[0].capability_keys == keys
    assert report.root_causes[0].domains == ("ergonomics", "person")


def test_report_keeps_all_seven_layers_and_l0_l6_evidence():
    AuditCapability, _, audit, _, _ = _audit_types()
    capabilities = tuple(AuditCapability(
        capability_id=f"example.level{index}", major_version=1, domain="example",
        maturity=f"L{index}", layer_evidence={chr(ord("A") + index): (f"evidence-{index}",)},
    ) for index in range(7))
    report = audit((), capabilities=capabilities, snapshot_gid="snap-1")
    assert report.maturity_counts == {f"L{index}": 1 for index in range(7)}
    assert report.maturity_evidence["L6"] == ("example.level6@1",)
    assert report.layer_counts == {chr(ord("A") + index): 1 for index in range(7)}
    assert report.layer_evidence["G"] == {"example.level6@1": ("evidence-6",)}


class _PagedAuditService:
    def __init__(self) -> None:
        self.registry_offsets: list[int] = []
        self.finding_offsets: list[int] = []

    @staticmethod
    def business_audit_snapshot_projection(snapshot_gid: str) -> dict[str, object]:
        assert snapshot_gid == "42"
        types = (
            ("rest_route", "REST route", "api.py", "create_height", "POST", "/people/{id}/height"),
            ("provider", "Provider", "provider.py", "HeightProvider", None, None),
            ("worker", "worker", "worker.py", "height_worker", None, None),
            ("mcp_tool", "MCP", "mcp.py", "get_height", None, None),
            ("agent_tool", "Agent Tool", "agent.py", "set_height", None, None),
        )
        return {
            "snapshot_gid": "42", "source_revision": "a" * 40,
            "nodes": tuple({
                "canonical_key": f"{node_type}:person:{path}:{symbol}", "owner_domain": "person",
                "node_type": node_type, "source_path": f"person/{path}", "source_symbol": symbol,
                "http_method": method, "route_path": route,
                "metadata": {"authorization": "secret-value", "public": True} if node_type == "rest_route" else {},
            } for node_type, _label, path, symbol, method, route in types),
            "bindings": (),
            "relation_candidates": (
                {
                    "candidate_hash": "sha256:" + "b" * 64, "relation_type": "boundary_overlap",
                    "source": "advisory", "capability_keys": ("example.cap0@1", "example.cap1@1"),
                    "evidence": {"token": "secret", "safe": "kept"}, "status": "pending_review",
                },
                {
                    "candidate_hash": "sha256:" + "d" * 64, "relation_type": "conflict",
                    "source": "deterministic", "capability_keys": ("example.cap0@1", "example.cap1@1"),
                    "evidence": {"field": "height"}, "status": "pending_review",
                },
            ),
        }

    def base_capability_registry_search(self, payload, _context):
        assert payload["snapshot_gid"] == "42" and payload["limit"] <= 200
        offset = payload["offset"]
        self.registry_offsets.append(offset)
        items = tuple({
            "capability_id": f"example.cap{index}", "major_version": 1,
            "capability_version_gid": str(index + 1), "owner_domain": "example", "semantic_class": "read",
            "contract": {"business_maturity": {"level": "L3", "reason_codes": ()}, "business_layer_evidence": {"A": ("purpose",)}},
        } for index in range(offset, min(offset + payload["limit"], 205)))
        return {"items": items, "total": 205}

    def base_capability_finding_search(self, payload, _context):
        assert payload["target_gid"] == "42" and payload["limit"] <= 200
        offset = payload["offset"]
        self.finding_offsets.append(offset)
        findings = tuple({
            "reason_code": "business_rules_missing", "subject_version_gids": (str(index + 1),),
            "domains": ("example",), "evidence": (f"provider.py:{index}",),
            "remediation_boundary": "declare_business_rule", "severity": "warning",
        } for index in range(offset, min(offset + payload["limit"], 205)))
        return {"findings": findings, "total": 205}


def test_collection_pages_to_total_and_keeps_exact_snapshot_redacted_projection():
    _, _, _, collect_business_audit, _ = _audit_types()
    service = _PagedAuditService()
    gate = SimpleNamespace(machine_passed=True, human_approved=False, runtime_verified=False,
                           legacy_pending_review_count=205, capabilities=())
    report = collect_business_audit(
        service, snapshot_gid="42",
        source_revisions={"backend": "a" * 40, "web": "c" * 40, "source": "a" * 40},
        gate_result=gate,
    )
    assert service.registry_offsets == [0, 200]
    assert service.finding_offsets == [0, 200]
    assert report.finding_count == 207
    assert (report.machine_passed, report.human_approved, report.runtime_verified) == (True, False, False)
    assert report.legacy_pending_review_count == 205
    assert {entry.entry_type for entry in report.unbound_entries} == {"REST route", "Provider", "worker", "MCP", "Agent Tool"}
    assert {entry.source_path for entry in report.unbound_entries} == {"person/api.py", "person/provider.py", "person/worker.py", "person/mcp.py", "person/agent.py"}
    assert report.relations[0].evidence == {"token": "[REDACTED]", "safe": "kept"}
    conflict = next(item for item in report.root_causes if item.reason_code == "cross_domain_conflict")
    assert conflict.capability_keys == ("example.cap0@1", "example.cap1@1")
    assert conflict.finding_count == 2
    assert "secret" not in str(report.to_dict())


def test_collection_rejects_stale_snapshot_source_revision():
    _, _, _, collect_business_audit, _ = _audit_types()
    try:
        collect_business_audit(
            _PagedAuditService(), snapshot_gid="42",
            source_revisions={"backend": "a" * 40, "web": "c" * 40, "source": "d" * 40},
        )
    except ValueError as exc:
        assert str(exc) == "business_audit_source_revision_mismatch"
    else:
        raise AssertionError("stale snapshot binding must fail closed")


def test_service_projects_the_requested_snapshot_and_redacts_relation_evidence():
    from backend.capability_governance_test.service import CapabilityGovernanceService

    def snapshot(gid, capability_id, revision):
        entry = SimpleNamespace(
            capability_id=capability_id, major_version=1, capability_version_gid=gid,
            owner_domain="example", semantic_class="read", business_effect="purpose",
        )
        capability = SimpleNamespace(
            capability_id=capability_id, major_version=1, business_rules=(), fingerprint=None,
            business_layer_evidence={"A": ("purpose",)},
            business_maturity=SimpleNamespace(level="L3", reason_codes=()),
        )
        document = SimpleNamespace(
            code_revision=revision, capabilities=(capability,), nodes=(), bindings=(), relations=(),
        )
        return SimpleNamespace(snapshot_gid=gid, entries=(entry,), document=document)

    old, current = snapshot(1, "example.old", "a" * 40), snapshot(2, "example.current", "b" * 40)
    relation = SimpleNamespace(
        candidate_hash="sha256:" + "c" * 64, relation_type="boundary_overlap", source="advisory",
        capability_keys=("example.old@1", "example.current@1"),
        evidence={"password": "secret", "shared_field": "height"}, status="pending_review",
    )

    class Store:
        def get_snapshot(self, gid):
            return {1: old, 2: current}.get(int(gid))

        def latest_snapshot(self):
            return current

        def list_entries(self, gid=None):
            return (current if gid is None else self.get_snapshot(gid)).entries

        @staticmethod
        def list_relation_candidates(gid):
            return (relation,) if int(gid) == 1 else ()

    service = CapabilityGovernanceService(Store(), analysis_runner=None, worker=None)

    registry = service.base_capability_registry_search({"snapshot_gid": "1", "limit": 200, "offset": 0}, None)
    projection = service.business_audit_snapshot_projection("1")

    assert [item["capability_id"] for item in registry["items"]] == ["example.old"]
    assert projection["snapshot_gid"] == "1"
    assert projection["source_revision"] == "a" * 40
    assert projection["relation_candidates"][0]["evidence"] == {"password": "[REDACTED]", "shared_field": "height"}
