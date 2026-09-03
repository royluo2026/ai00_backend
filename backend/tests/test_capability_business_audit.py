from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest


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


def test_gate_definition_blockers_become_exact_audit_root_causes():
    from backend.capability_v2.release_gate import (
        BusinessGateCapability,
        evaluate_business_governance_gate,
    )

    AuditCapability, _, audit, _, _ = _audit_types()
    key = "project.task.read@1"
    digest = "sha256:" + "a" * 64
    gate = evaluate_business_governance_gate((BusinessGateCapability(
        capability_key=key,
        capability_version_gid="1",
        definition_hash=digest,
        change_kind="material_change",
        deterministic_blockers=(f"business_effect_invalid:{key}",),
    ),))
    report = audit((), capabilities=(AuditCapability(
        capability_id="project.task.read",
        major_version=1,
        domain="project_management",
        maturity="L3",
        capability_version_gid="1",
        snapshot_capability_version_gid="1",
        business_definition_hash=digest,
    ),), snapshot_gid="snap-1", gate_result=gate)

    assert report.finding_count == 1
    assert report.root_cause_group_count == 1
    assert report.root_causes[0].root_cause_key == f"business_effect_invalid:{key}"
    assert report.root_causes[0].severity == "blocking"
    assert report.review_queue[0].governance_status == "blocked"


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
                "metadata": {"authorization": "secret-value", "public_entry": True, "source_line": 12},
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
            "contract": {"business_maturity": {"level": "L3", "reason_codes": ()}, "business_layer_evidence": {"A": ("purpose",)}, "business_rules": (), "business_definition_hash": "sha256:" + "a" * 64},
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
    report = collect_business_audit(
        service, snapshot_gid="42",
        source_revisions={"backend": "a" * 40, "web": "c" * 40, "source": "a" * 40},
    )
    assert service.registry_offsets == [0, 200]
    assert service.finding_offsets == [0, 200]
    assert report.finding_count == 207
    assert (report.machine_passed, report.human_approved, report.runtime_verified) == (False, False, False)
    assert report.legacy_pending_review_count == 0
    assert {entry.entry_type for entry in report.unbound_entries} == {"REST route", "Provider", "worker", "MCP", "Agent Tool"}
    assert {entry.source_path for entry in report.unbound_entries} == {"person/api.py", "person/provider.py", "person/worker.py", "person/mcp.py", "person/agent.py"}
    assert {entry.location for entry in report.unbound_entries} == {
        "person/api.py:12", "person/provider.py:12", "person/worker.py:12", "person/mcp.py:12", "person/agent.py:12",
    }
    assert {entry["location"] for entry in report.to_dict()["unbound_entries"]} == {
        "person/api.py:12", "person/provider.py:12", "person/worker.py:12", "person/mcp.py:12", "person/agent.py:12",
    }
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
            descriptor={"business_definition_hash": "sha256:" + "d" * 64},
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


def _trusted_gate_context(*, changed: bool = False):
    from backend.capability_v2.catalog import build_catalog_entry, build_release, load_catalog_release
    from backend.capability_v2.release_gate import evaluate_catalog_business_governance
    from pathlib import Path
    import json

    root = Path(__file__).resolve().parents[2]
    source = json.loads((root / "docs/governance/capability-catalog-release.json").read_text(encoding="utf-8"))
    descriptor = load_catalog_release(source).descriptors[0]
    descriptor = descriptor.model_copy(update={
        "business_effect": "Operators receive one exact governed result." + (" Changed." if changed else ""),
        "business_acceptance_criteria": ("The declared result is schema-valid.",),
        "business_invariants": (),
        "no_business_invariant_reason": "No additional invariant applies.",
    })
    release = build_release((descriptor,), created_at=datetime(2026, 9, 2, tzinfo=UTC))
    catalog = release.model_dump(mode="json")
    catalog["descriptors"] = [build_catalog_entry(descriptor)]
    row = catalog["descriptors"][0]
    key = f"{row['id']}@{row['major_version']}"
    baseline = {key: row["business_definition_hash"]}
    gate = evaluate_catalog_business_governance(
        catalog, baseline, business_review_lookup={}, runtime_verification={}, deterministic_blockers={},
    )
    return catalog, baseline, gate


class _ExactGateService:
    def __init__(self, catalog):
        self.catalog = catalog

    def business_audit_snapshot_projection(self, snapshot_gid):
        return {
            "snapshot_gid": str(snapshot_gid), "source_revision": "a" * 40,
            "catalog_release_id": self.catalog["release_id"], "nodes": (), "bindings": (), "relation_candidates": (),
        }

    def base_capability_registry_search(self, payload, _context):
        row = self.catalog["descriptors"][0]
        item = {
            "capability_id": row["id"], "major_version": row["major_version"],
            "capability_version_gid": row["capability_version_gid"], "owner_domain": row["owner_domain"],
            "semantic_class": row["side_effect_level"],
            "contract": {"business_maturity": {"level": "L3", "reason_codes": ()},
                         "business_layer_evidence": {}, "business_rules": row["business_invariants"],
                         "business_definition_hash": row["business_definition_hash"]},
        }
        return {"items": (item,), "total": 1}

    def base_capability_finding_search(self, payload, _context):
        return {"findings": (), "total": 0}


def _collect_exact(service, gate, catalog, baseline):
    _, _, _, collect_business_audit, _ = _audit_types()
    return collect_business_audit(
        service, snapshot_gid="1", source_revisions={"backend": "a" * 40, "web": "b" * 40, "source": "a" * 40},
        gate_result=gate, business_catalog=catalog, legacy_baseline=baseline, business_review_lookup={},
    )


def test_gate_is_rederived_only_after_exact_catalog_and_capability_binding():
    catalog, baseline, gate = _trusted_gate_context()
    report = _collect_exact(_ExactGateService(catalog), gate, catalog, baseline)
    assert report.machine_passed is True
    assert report.legacy_pending_review_count == 1

    stale_catalog, stale_baseline, stale_gate = _trusted_gate_context(changed=True)
    corruptions = []
    for mutate in ("empty", "omitted", "extra", "wrong_hash", "wrong_gid"):
        document = deepcopy(gate.serialized())
        if mutate == "empty": document["capabilities"] = []
        elif mutate == "omitted": document["capabilities"] = document["capabilities"][:-1]
        elif mutate == "extra": document["capabilities"].append(deepcopy(document["capabilities"][0]))
        elif mutate == "wrong_hash": document["capabilities"][0]["definition_hash"] = "sha256:" + "f" * 64
        else: document["capabilities"][0]["capability_version_gid"] = "999999"
        corruptions.append(document)
    corruptions.append(stale_gate)
    for candidate in corruptions:
        with pytest.raises(Exception, match="business_governance_invalid"):
            _collect_exact(_ExactGateService(catalog), candidate, catalog, baseline)
    with pytest.raises(Exception, match="business_governance_invalid"):
        _collect_exact(_ExactGateService(catalog), gate, stale_catalog, stale_baseline)


def test_rule_specific_evidence_groups_by_exact_rule_only():
    AuditCapability, _, _, collect_business_audit, _ = _audit_types()
    del AuditCapability

    class Service(_ExactGateService):
        def __init__(self):
            self.catalog = {"release_id": "rel_test"}

        def base_capability_registry_search(self, payload, _context):
            rules = (
                {"rule_id": "height.min", "enforcement_ref": "provider.py:enforce_min", "test_refs": ("tests/test_height.py::test_min",)},
                {"rule_id": "height.max", "enforcement_ref": "provider.py:enforce_max", "test_refs": ("tests/test_height.py::test_max",)},
            )
            return {"items": ({"capability_id": "person.height.write", "major_version": 1, "capability_version_gid": "1",
                               "owner_domain": "person", "semantic_class": "write",
                               "contract": {"business_maturity": {"level": "L2", "reason_codes": ()}, "business_layer_evidence": {},
                                            "business_rules": rules, "business_definition_hash": "sha256:" + "a" * 64}},), "total": 1}

        def base_capability_finding_search(self, payload, _context):
            refs = ("provider.py:enforce_min", "tests/test_height.py::test_min", "provider.py:enforce_max", "capability:person.height.write@1")
            return {"findings": ({"reason_code": "rule_evidence_missing", "subject_version_gids": ("1",), "evidence": refs,
                                   "remediation_boundary": "map_rule_enforcement", "severity": "warning"},), "total": 1}

    report = collect_business_audit(Service(), snapshot_gid="1", source_revisions={"backend": "a" * 40, "web": "b" * 40, "source": "a" * 40})
    assert [item.root_cause_key for item in report.root_causes] == [
        "rule_evidence_missing:person.height.write@1",
        "rule_evidence_missing:person.height.write@1:height.max",
        "rule_evidence_missing:person.height.write@1:height.min",
    ]
    assert [item.finding_count for item in report.root_causes] == [1, 1, 2]


def test_unbound_entries_require_public_projection_metadata_for_every_kind():
    class Service(_PagedAuditService):
        @staticmethod
        def business_audit_snapshot_projection(snapshot_gid):
            kinds = ("rest_route", "provider", "worker", "mcp_tool", "agent_tool")
            nodes = []
            private_names = {
                "rest_route": "_route_helper", "provider": "_UnavailableProviderRegistry",
                "worker": "_worker_error", "mcp_tool": "_mcp_helper", "agent_tool": "_agent_helper",
            }
            for index, kind in enumerate(kinds, 1):
                for public, prefix in ((True, "public"), (False, private_names[kind])):
                    nodes.append({"canonical_key": f"{kind}:x:{prefix}", "owner_domain": "x", "node_type": kind,
                                  "source_path": f"x/{kind}.py", "source_symbol": prefix,
                                  "metadata": {"public_entry": public, "source_line": index}})
            return {"snapshot_gid": "42", "source_revision": "a" * 40, "nodes": tuple(nodes), "bindings": (), "relation_candidates": ()}

    _, _, _, collect_business_audit, _ = _audit_types()
    report = collect_business_audit(Service(), snapshot_gid="42", source_revisions={"backend": "a" * 40, "web": "b" * 40, "source": "a" * 40})
    assert len(report.unbound_entries) == 5
    assert all("public" in item.canonical_key for item in report.unbound_entries)
    assert all(item.source_line > 0 and item.location.endswith(f":{item.source_line}") for item in report.unbound_entries)


def test_scanner_public_entry_classification_keeps_explicit_routes_and_excludes_helpers():
    import ast
    from backend.capability_governance_test.scanner import _AstUnit, _is_public_entry

    def unit(kind, symbol, source="def entry():\n    pass\n"):
        tree = ast.parse(source).body[0]
        return _AstUnit("x", f"x/{kind}.py", symbol, kind, tree, "sha256:" + "a" * 64)

    explicit_route = unit("rest_route", "_internal_name", "@router.get('/public')\ndef entry():\n    pass\n")
    assert _is_public_entry(explicit_route) is True
    pairs = (
        (unit("provider", "PublicProvider"), unit("provider", "_UnavailableProviderRegistry")),
        (unit("worker", "PublicWorker"), unit("worker", "_worker_envelope_bytes")),
        (unit("mcp_tool", "public_tool"), unit("mcp_tool", "_mcp_helper")),
        (unit("agent_tool", "public_tool"), unit("agent_tool", "_agent_helper")),
    )
    assert all(_is_public_entry(public) and not _is_public_entry(private) for public, private in pairs)


def test_nested_relation_evidence_is_recursively_immutable_and_serializable():
    from backend.capability_governance_test.business_audit import AuditRelation, audit

    report = audit((), snapshot_gid="1", relations=(AuditRelation(
        "sha256:" + "a" * 64, "overlap", "advisory", ("x.read@1",),
        {"nested": {"rows": [{"value": "safe"}]}}, "pending_review",
    ),))
    with pytest.raises(TypeError):
        report.relations[0].evidence["nested"]["rows"][0]["value"] = "mutated"
    assert report.to_dict()["relations"][0]["evidence"]["nested"]["rows"][0]["value"] == "safe"
