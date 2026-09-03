from __future__ import annotations

from collections import Counter
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess

import backend.capability_v2.existing_capability_migrations as migration_audit
from backend.capability_v2.existing_capability_migrations import (
    audit_existing_capability_migrations,
    load_existing_capability_migrations,
)
from backend.capabilities.validation_next import validate_payload


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/governance/existing-capability-web-migrations.json"
LEDGER = ROOT / "docs/governance/web-route-root-cause-ledger.json"
WEB_ROOT = Path(
    os.environ.get(
        "AI00_WEB_ROOT",
        r"E:\Projects\ai00_v3\.worktrees\workmanship-web-capability-governance",
    )
)
CATALOG = ROOT / "docs/capabilities/catalog.v2.json"


def test_migration_source_hashes_are_newline_invariant():
    assert migration_audit._sha256_bytes(b"first\nsecond\n") == migration_audit._sha256_bytes(
        b"first\r\nsecond\r\n"
    )


def _frontend_payloads() -> dict[str, dict[str, object]]:
    saved_view_config = {
        "field_gids": ["status"],
        "filters": [{"field_gid": "status", "operator": "eq", "value": "open"}],
        "sort": [{"field_gid": "status", "direction": "asc"}],
        "page_size": 200,
        "presentation": "table",
    }
    cases = {
        "knowledge.search": {"listGid": "list-1"},
        "knowledge.get": {"gid": "knowledge-1"},
        "knowledge.create": {"record": {"title": "New"}},
        "knowledge.update": {"gid": "knowledge-1", "updates": {"title": "Changed"}},
        "knowledge.delete": {"gid": "knowledge-1"},
        "project.task.update": {"gid": "task-1", "updates": {"status": "completed"}},
        "project.issue.update": {"gid": "issue-1", "updates": {"status": "closed"}},
        "project.itemEntries.get": {"itemGid": "task-1"},
        "project.itemEntries.replace": {"itemGid": "task-1", "entries": [{"gid": "entry-2"}]},
        "base.savedViews.search": {"module": "task", "listGid": "list-1"},
        "base.savedViews.create": {"name": "Open", "module": "task", "listGid": "list-1", "config": saved_view_config, "shareScope": "private"},
        "base.savedViews.update": {"viewGid": "view-1", "expectedRevision": 1, "name": "Open", "module": "task", "listGid": "list-1", "config": saved_view_config, "shareScope": "private"},
        "base.savedViews.copy": {"viewGid": "view-1", "name": "Copy"},
        "base.savedViews.delete": {"viewGid": "view-1", "expectedRevision": 1},
    }
    script = r"""
const fs = require('fs');
const { createExistingCapabilityClient } = require(process.argv[1]);
const cases = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
  const output = {};
  for (const [operation, args] of Object.entries(cases)) {
    let firstInvoke;
    const client = createExistingCapabilityClient(async (path, options) => {
      if (path.endsWith(':invoke') && !firstInvoke) {
        firstInvoke = { path, body: JSON.parse(options.body) };
      }
      return { success: true, data: { ok: true, data: {} } };
    });
    await client.call(operation, args, { confirm: async () => true });
    output[operation] = firstInvoke;
  }
  process.stdout.write(JSON.stringify(output));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        ["node", "-e", script, str(WEB_ROOT / "web/core/existing_capability_client.js")],
        input=json.dumps(cases), text=True, capture_output=True, check=True,
    )
    return json.loads(result.stdout)


def _replace_group(manifest, replacement):
    return replace(
        manifest,
        groups=tuple(
            replacement if group.key == replacement.key else group
            for group in manifest.groups
        ),
    )


def test_manifest_accounts_for_all_53_groups_and_80_occurrences() -> None:
    manifest = load_existing_capability_migrations(MANIFEST)

    assert len(manifest.groups) == 53
    assert sum(group.occurrence_count for group in manifest.groups) == 80
    assert Counter(group.decision for group in manifest.groups) == {
        "migrate": 22,
        "reclassify": 31,
    }
    assert sum(
        group.occurrence_count for group in manifest.groups if group.decision == "migrate"
    ) == 32


def test_all_migrated_frontend_operation_payloads_pass_production_catalog_validation() -> None:
    payloads = _frontend_payloads()
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    descriptors = {
        item["id"]: item
        for item in catalog["capabilities"]
        if item["major_version"] == 1
    }
    failures = {}
    for operation, request in payloads.items():
        capability_id = request["path"].removeprefix("/api/v1/capabilities/").removesuffix(":invoke")
        try:
            validate_payload(descriptors[capability_id]["input_schema"], request["body"]["payload"])
        except ValueError as exc:
            failures[operation] = str(exc)

    assert set(payloads) == {
        "knowledge.search", "knowledge.get", "knowledge.create", "knowledge.update",
        "knowledge.delete", "project.task.update", "project.issue.update",
        "project.itemEntries.get", "project.itemEntries.replace",
        "base.savedViews.search", "base.savedViews.create", "base.savedViews.update",
        "base.savedViews.copy", "base.savedViews.delete",
    }
    assert failures == {}


def test_manifest_targets_are_stable_owned_and_decisions_have_evidence() -> None:
    manifest = load_existing_capability_migrations(MANIFEST)

    assert audit_existing_capability_migrations(
        ROOT, manifest, web_root=WEB_ROOT, ledger_path=LEDGER
    ) == ()
    assert all(group.request_transform and group.response_transform for group in manifest.groups)
    assert all(group.transport_evidence for group in manifest.groups)
    assert all(
        group.equivalence_evidence if group.decision == "migrate" else group.reclassification
        for group in manifest.groups
    )


def test_later_source_proved_remediation_may_close_a_reclassified_occurrence() -> None:
    """Breaks if the historical migration audit ignores a later exact owner-capability closure."""
    manifest = load_existing_capability_migrations(MANIFEST)

    issues = audit_existing_capability_migrations(ROOT, manifest, web_root=WEB_ROOT)

    assert "migration_final_reclassification_mismatch:POST:/api/approval/orders/{dynamic}/reject" not in issues

    remediation = json.loads((ROOT / "docs/governance/craft-agent-project-structural-web-remediation.json").read_text(encoding="utf-8"))
    approval = next(
        item for item in remediation["entries"]
        if (item["method"], item["normalized_route"])
        == ("POST", "/api/approval/orders/{dynamic}/reject")
    )
    approval["final_disposition"] = "unresolved"
    issues = audit_existing_capability_migrations(
        ROOT, manifest, web_root=WEB_ROOT, remediation_document=remediation,
    )
    assert "migration_final_reclassification_mismatch:POST:/api/approval/orders/{dynamic}/reject" in issues


def test_later_remediation_is_rebuilt_without_a_stored_generated_manifest(monkeypatch) -> None:
    """Breaks if clean replay requires a previously generated remediation artifact."""
    manifest = load_existing_capability_migrations(MANIFEST)
    monkeypatch.setattr(migration_audit, "STRUCTURAL_REMEDIATION_PATH", "does/not/exist.json")

    issues = audit_existing_capability_migrations(ROOT, manifest, web_root=WEB_ROOT)

    assert "migration_final_reclassification_mismatch:POST:/api/approval/orders/{dynamic}/reject" not in issues


def test_later_remediation_rejects_forged_and_stale_documents() -> None:
    """Breaks if plausible self-declared JSON can silence a historical migration mismatch."""
    manifest = load_existing_capability_migrations(MANIFEST)
    stored = json.loads(
        (ROOT / "docs/governance/craft-agent-project-structural-web-remediation.json").read_text(
            encoding="utf-8"
        )
    )
    approval = next(
        item for item in stored["entries"]
        if (item["method"], item["normalized_route"])
        == ("POST", "/api/approval/orders/{dynamic}/reject")
    )
    forged = {
        "schema_version": stored["schema_version"],
        "frontend_revision": stored["frontend_revision"],
        "content_sha256": stored["content_sha256"],
        "entries": [approval],
    }
    stale = json.loads(json.dumps(stored))
    stale["frontend_revision"] = "0" * 40
    without_hash = {key: value for key, value in stale.items() if key != "content_sha256"}
    import hashlib
    stale["content_sha256"] = "sha256:" + hashlib.sha256(
        (json.dumps(without_hash, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    ).hexdigest()

    for document in (forged, stale):
        issues = audit_existing_capability_migrations(
            ROOT, manifest, web_root=WEB_ROOT, remediation_document=document,
        )
        assert any(issue.startswith("migration_structural_remediation_invalid:") for issue in issues)
        assert "migration_final_reclassification_mismatch:POST:/api/approval/orders/{dynamic}/reject" in issues


def test_later_remediation_rejects_explicit_empty_document() -> None:
    """Breaks if a falsey supplied candidate is replaced by the canonical rebuild."""
    manifest = load_existing_capability_migrations(MANIFEST)

    issues = audit_existing_capability_migrations(
        ROOT, manifest, web_root=WEB_ROOT, remediation_document={},
    )

    assert "migration_structural_remediation_invalid:canonical_document_mismatch" in issues
    assert (
        "migration_final_reclassification_mismatch:POST:/api/approval/orders/{dynamic}/reject"
        in issues
    )


def test_migrated_groups_are_only_the_provider_equivalent_families() -> None:
    manifest = load_existing_capability_migrations(MANIFEST)
    migrated = {(group.method, group.normalized_route) for group in manifest.groups if group.decision == "migrate"}

    assert migrated == {
        ("DELETE", "/api/plugin/uninstall/{dynamic}"),
        ("DELETE", "/api/knowledges/{dynamic}"),
        ("GET", "/api/knowledge/entries"),
        ("GET", "/api/knowledges/{dynamic}"),
        ("GET", "/api/self_ann/list"),
        ("GET", "/api/self_ann/{dynamic}"),
        ("GET", "/api/users/me"),
        ("PATCH", "/api/knowledges/{dynamic}"),
        ("POST", "/api/knowledges"),
        ("POST", "/api/plugin/install"),
        ("PUT", "/api/knowledge/entries"),
        ("PUT", "/api/knowledges/{dynamic}"),
        ("GET", "/api/tasks/{dynamic}/entries"),
        ("PUT", "/api/tasks/{dynamic}/entries"),
        ("PUT", "/api/tasks"),
        ("PUT", "/api/issues"),
        ("PUT", "/api/self_ann/{dynamic}"),
        ("DELETE", "/api/views/{dynamic}"),
        ("GET", "/api/views"),
        ("PATCH", "/api/views/{dynamic}"),
        ("POST", "/api/views"),
        ("POST", "/api/views/{dynamic}/copy"),
    }


def test_manifest_independently_binds_pinned_baseline_frontend_and_ledger() -> None:
    manifest = load_existing_capability_migrations(MANIFEST)

    assert manifest.baseline_revision == "2c17617c28e0bed2411763e9ae5520128f2804e0"
    assert manifest.frontend_revision
    migrated = [group for group in manifest.groups if group.decision == "migrate"]
    assert all(group.frontend_operation and group.frontend_call_sites for group in migrated)
    assert sum(len(group.frontend_call_sites) for group in migrated) == 32
    reclassified = [group for group in manifest.groups if group.decision == "reclassify"]
    assert all(group.reclassification["legacy_contract"] for group in reclassified)
    assert all(group.reclassification["candidate_contracts"] for group in reclassified)
    assert all(group.reclassification["contract_mismatch"] for group in reclassified)


def test_independent_audit_rejects_every_mutation_boundary() -> None:
    manifest = load_existing_capability_migrations(MANIFEST)
    migrated = next(group for group in manifest.groups if group.decision == "migrate")

    wrong_target = replace(
        migrated, target_capability_id="knowledge.get"
    )
    issues = audit_existing_capability_migrations(
        ROOT, _replace_group(manifest, wrong_target),
        web_root=WEB_ROOT, ledger_path=LEDGER,
    )
    assert any("reviewed_target_mismatch" in issue for issue in issues)

    altered_decision = replace(migrated, decision="reclassify")
    issues = audit_existing_capability_migrations(
        ROOT, _replace_group(manifest, altered_decision),
        web_root=WEB_ROOT, ledger_path=LEDGER,
    )
    assert any("reviewed_decision_mismatch" in issue for issue in issues)

    occurrence = dict(migrated.occurrences[0])
    occurrence["source"] = "web/not-the-pinned-source.js"
    altered_occurrence = replace(migrated, occurrences=(occurrence,))
    issues = audit_existing_capability_migrations(
        ROOT, _replace_group(manifest, altered_occurrence),
        web_root=WEB_ROOT, ledger_path=LEDGER,
    )
    assert any("pinned_occurrence_mismatch" in issue for issue in issues)

    source = "web/components/list_shell.js"
    missing_call = (WEB_ROOT / source).read_text(encoding="utf-8").replace(
        ".call('knowledge.delete'", ".call('knowledge.remove'", 1
    )
    issues = audit_existing_capability_migrations(
        ROOT, manifest, web_root=WEB_ROOT, ledger_path=LEDGER,
        frontend_source_overrides={source: missing_call},
    )
    assert any("frontend_call_site_mismatch" in issue for issue in issues)

    raw = json.loads(LEDGER.read_text(encoding="utf-8"))
    key = (migrated.method, migrated.normalized_route)
    entry = next(item for item in raw["entries"] if (item["method"], item["normalized_route"]) == key)
    entry["disposition_details"]["target_capability"] = "knowledge.get@1"
    issues = audit_existing_capability_migrations(
        ROOT, _replace_group(manifest, wrong_target),
        web_root=WEB_ROOT, ledger_document=raw,
    )
    assert any("reviewed_target_mismatch" in issue for issue in issues)
