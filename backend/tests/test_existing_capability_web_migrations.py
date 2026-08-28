from __future__ import annotations

from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
import subprocess

from backend.capability_v2.existing_capability_migrations import (
    audit_existing_capability_migrations,
    load_existing_capability_migrations,
)
from backend.capabilities.validation_next import validate_payload


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/governance/existing-capability-web-migrations.json"
LEDGER = ROOT / "docs/governance/web-route-root-cause-ledger.json"
WEB_ROOT = Path(r"E:\Projects\ai00_v3\.worktrees\workmanship-web-capability-governance")
CATALOG = ROOT / "docs/capabilities/catalog.v2.json"


def _frontend_payloads() -> dict[str, dict[str, object]]:
    saved_view_config = {
        "columns": [{"key": "status", "visible": True, "order": 0, "width": 120}],
        "filters": [{"id": "open", "field": "status", "op": "eq", "value": "open"}],
        "filterMode": "and", "sorts": [{"field": "status", "dir": "asc"}],
        "groupBy": None, "viewType": "grid", "treeParentField": None,
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
        "migrate": 16,
        "reclassify": 37,
    }
    assert sum(
        group.occurrence_count for group in manifest.groups if group.decision == "migrate"
    ) == 24


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


def test_migrated_groups_are_only_the_provider_equivalent_families() -> None:
    manifest = load_existing_capability_migrations(MANIFEST)
    migrated = {(group.method, group.normalized_route) for group in manifest.groups if group.decision == "migrate"}

    assert migrated == {
        ("DELETE", "/api/knowledges/{dynamic}"),
        ("GET", "/api/knowledge/entries"),
        ("GET", "/api/knowledges/{dynamic}"),
        ("PATCH", "/api/knowledges/{dynamic}"),
        ("POST", "/api/knowledges"),
        ("PUT", "/api/knowledge/entries"),
        ("PUT", "/api/knowledges/{dynamic}"),
        ("GET", "/api/tasks/{dynamic}/entries"),
        ("PUT", "/api/tasks/{dynamic}/entries"),
        ("PUT", "/api/tasks"),
        ("PUT", "/api/issues"),
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
    assert sum(len(group.frontend_call_sites) for group in migrated) == 24
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
