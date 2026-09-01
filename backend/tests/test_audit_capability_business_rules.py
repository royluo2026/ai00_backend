from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess

import pytest
from types import SimpleNamespace


def test_cli_emits_seven_layer_json_without_writing_by_default(monkeypatch, capsys):
    from backend.scripts import audit_capability_business_rules as command

    expected = {
        "snapshot_gid": "local-snapshot",
        "source_revisions": {"backend": "a" * 40, "web": "b" * 40, "source": "a" * 40},
        "maturity_counts": {f"L{index}": 0 for index in range(7)},
        "maturity_evidence": {f"L{index}": [] for index in range(7)},
        "layer_counts": {key: 0 for key in "ABCDEFG"},
        "layer_evidence": {key: {} for key in "ABCDEFG"},
        "finding_count": 0,
        "root_cause_group_count": 0,
        "affected_capability_count": 0,
        "affected_capabilities": [],
        "affected_domains": [],
        "shared_remediation_family_count": 0,
        "shared_remediation_families": {},
        "findings": [],
        "root_causes": [],
        "relations": [],
        "unbound_entries": [],
        "review_queue": [],
        "machine_passed": True,
        "human_approved": False,
        "runtime_verified": False,
        "legacy_pending_review_count": 0,
    }
    monkeypatch.setattr(command, "build_local_report", lambda **_kwargs: expected)

    assert command.main(["--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out) == expected


def test_cli_writes_only_explicit_output(monkeypatch, tmp_path):
    from backend.scripts import audit_capability_business_rules as command

    monkeypatch.setattr(command, "build_local_report", lambda **_kwargs: {"snapshot_gid": "snap"})
    destination = tmp_path / "baseline.json"

    assert command.main(["--format", "json", "--output", str(destination)]) == 0
    assert json.loads(destination.read_text(encoding="utf-8")) == {"snapshot_gid": "snap"}


def test_local_snapshot_supplies_and_restores_the_offline_integration_factory(monkeypatch):
    from backend.scripts import audit_capability_business_rules as command
    import backend.capability_v2.bootstrap as bootstrap

    monkeypatch.delenv("AI00_INTEGRATION_ADAPTER_FACTORY", raising=False)
    monkeypatch.setattr(command, "load_catalog_release", lambda _text: object())
    monkeypatch.setattr(command, "load_domain_manifests", lambda _path: object())

    class Scanner:
        def __init__(self, *_args, **_kwargs):
            pass

        @staticmethod
        def scan(*, code_revision):
            return {"code_revision": code_revision}

    monkeypatch.setattr(command, "GovernanceScanner", Scanner)

    def registry(_root):
        assert os.environ["AI00_INTEGRATION_ADAPTER_FACTORY"] == command.OFFLINE_INTEGRATION_FACTORY
        return SimpleNamespace(snapshot=lambda: object())

    monkeypatch.setattr(bootstrap, "build_capability_registry", registry)

    assert command._snapshot("a" * 40) == {"code_revision": "a" * 40}
    assert "AI00_INTEGRATION_ADAPTER_FACTORY" not in os.environ


def test_revision_fails_closed_for_relevant_tracked_dirt(tmp_path):
    from backend.scripts import audit_capability_business_rules as command

    subprocess.run(("git", "init"), cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(("git", "config", "user.email", "audit@example.test"), cwd=tmp_path, check=True)
    subprocess.run(("git", "config", "user.name", "Audit Test"), cwd=tmp_path, check=True)
    backend = tmp_path / "backend"
    backend.mkdir()
    tracked = backend / "provider.py"
    tracked.write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(("git", "add", "backend/provider.py"), cwd=tmp_path, check=True)
    subprocess.run(("git", "commit", "-m", "fixture"), cwd=tmp_path, check=True, capture_output=True)

    assert len(command._revision(tmp_path, relevant_paths=("backend",))) == 40
    tracked.write_text("VALUE = 2\n", encoding="utf-8")
    try:
        command._revision(tmp_path, relevant_paths=("backend",))
    except RuntimeError as exc:
        assert str(exc) == "business_audit_relevant_tree_dirty"
    else:
        raise AssertionError("tracked relevant dirt must prevent false Git provenance")


def _git_fixture(root: Path) -> Path:
    subprocess.run(("git", "init"), cwd=root, check=True, capture_output=True)
    subprocess.run(("git", "config", "user.email", "audit@example.test"), cwd=root, check=True)
    subprocess.run(("git", "config", "user.name", "Audit Test"), cwd=root, check=True)
    backend = root / "backend"
    backend.mkdir()
    tracked = backend / "provider.py"
    tracked.write_text("VALUE = 1\n", encoding="utf-8")
    (root / ".gitignore").write_text("backend/.cache/\n", encoding="utf-8")
    subprocess.run(("git", "add", "backend/provider.py", ".gitignore"), cwd=root, check=True)
    subprocess.run(("git", "commit", "-m", "fixture"), cwd=root, check=True, capture_output=True)
    return tracked


@pytest.mark.parametrize("staged", (False, True))
def test_revision_rejects_staged_and_unstaged_eligible_source(tmp_path, staged):
    from backend.scripts import audit_capability_business_rules as command

    tracked = _git_fixture(tmp_path)
    expected = subprocess.run(("git", "rev-parse", "HEAD"), cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()
    assert command._revision(tmp_path, relevant_paths=("backend",)) == expected
    tracked.write_text("VALUE = 2\n", encoding="utf-8")
    if staged:
        subprocess.run(("git", "add", "backend/provider.py"), cwd=tmp_path, check=True)
    with pytest.raises(RuntimeError, match="business_audit_relevant_tree_dirty"):
        command._revision(tmp_path, relevant_paths=("backend",))


def test_revision_rejects_untracked_eligible_source_but_ignores_irrelevant_file(tmp_path):
    from backend.scripts import audit_capability_business_rules as command

    _git_fixture(tmp_path)
    eligible = tmp_path / "backend/new_provider.py"
    eligible.write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="business_audit_relevant_tree_dirty"):
        command._revision(tmp_path, relevant_paths=("backend",))
    eligible.unlink()
    (tmp_path / "backend/notes.txt").write_text("not scanned\n", encoding="utf-8")
    cache = tmp_path / "backend/.cache"
    cache.mkdir()
    (cache / "output.txt").write_text("ignored runtime output\n", encoding="utf-8")
    expected = subprocess.run(("git", "rev-parse", "HEAD"), cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()
    assert command._revision(tmp_path, relevant_paths=("backend",)) == expected


def test_revision_rejects_deleted_eligible_source(tmp_path):
    from backend.scripts import audit_capability_business_rules as command

    tracked = _git_fixture(tmp_path)
    tracked.unlink()
    with pytest.raises(RuntimeError, match="business_audit_relevant_tree_dirty"):
        command._revision(tmp_path, relevant_paths=("backend",))


def test_scan_aborts_when_backend_or_web_provenance_changes_during_scan():
    from backend.scripts import audit_capability_business_rules as command

    clean_backend = command._InputProvenance("a" * 40, "sha256:" + "1" * 64, ("backend/provider.py",))
    changed_backend = command._InputProvenance("b" * 40, "sha256:" + "2" * 64, ("backend/provider.py",))
    clean_web = command._InputProvenance("c" * 40, "sha256:" + "3" * 64, ("web/main.js",))

    backend_values = iter((clean_backend, changed_backend))
    web_values = iter((clean_web, clean_web))
    with pytest.raises(RuntimeError, match="business_audit_inputs_changed_during_scan"):
        command._stable_scan(lambda revision: {"code_revision": revision}, lambda: next(backend_values), lambda: next(web_values))

    backend_values = iter((clean_backend, clean_backend))
    changed_web = command._InputProvenance("c" * 40, "sha256:" + "4" * 64, ("web/main.js",))
    web_values = iter((clean_web, changed_web))
    with pytest.raises(RuntimeError, match="business_audit_inputs_changed_during_scan"):
        command._stable_scan(lambda revision: {"code_revision": revision}, lambda: next(backend_values), lambda: next(web_values))


def test_stable_scan_records_exact_clean_backend_and_web_revisions():
    from backend.scripts import audit_capability_business_rules as command

    backend = command._InputProvenance("a" * 40, "sha256:" + "1" * 64, ("backend/provider.py",))
    web = command._InputProvenance("b" * 40, "sha256:" + "2" * 64, ("web/main.js",))
    document, backend_revision, web_revision = command._stable_scan(
        lambda revision: {"code_revision": revision}, lambda: backend, lambda: web,
    )
    assert document["code_revision"] == backend_revision == "a" * 40
    assert web_revision == "b" * 40


def _acceptance_fixture(tmp_path: Path, *, tracked_source: bool = True):
    from backend.capability_governance_test.config import GovernanceSettings
    from backend.capability_governance_test.scanner import GovernanceScanner

    source_fixture = Path(__file__).parent / "fixtures/capability_governance_scan/valid"
    root = tmp_path / "acceptance-provenance"
    shutil.copytree(source_fixture, root)
    acceptance_source = root / "acceptance/test_external.py"
    acceptance_source.parent.mkdir()
    acceptance_source.write_text(
        "def test_success_case():\n    assert True\n", encoding="utf-8",
    )
    node_id = "acceptance/test_external.py::test_success_case[craft.bop.factory.create@1]"
    manifest = {
        "capabilities": {"craft.bop.factory.create@1": {"success": node_id}},
    }
    manifest_path = root / "acceptance.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    subprocess.run(("git", "init"), cwd=root, check=True, capture_output=True)
    subprocess.run(("git", "config", "user.email", "audit@example.test"), cwd=root, check=True)
    subprocess.run(("git", "config", "user.name", "Audit Test"), cwd=root, check=True)
    subprocess.run(("git", "add", "."), cwd=root, check=True)
    if not tracked_source:
        subprocess.run(("git", "reset", "--", "acceptance/test_external.py"), cwd=root, check=True)
    subprocess.run(("git", "commit", "-m", "fixture"), cwd=root, check=True, capture_output=True)
    scanner = GovernanceScanner(
        GovernanceSettings("test-governance", root, ("plugins",)),
        product_catalog=json.loads((root / "product_catalog.json").read_text(encoding="utf-8")),
        extension_catalog=json.loads((root / "extension_catalog.json").read_text(encoding="utf-8")),
        domain_manifests=json.loads((root / "official_domains.json").read_text(encoding="utf-8")),
        acceptance_manifest=manifest, acceptance_manifest_path="acceptance.json",
    )
    return root, scanner, acceptance_source, node_id


def test_scanner_discovery_includes_and_scan_hashes_acceptance_manifest_source(tmp_path):
    root, scanner, source, node_id = _acceptance_fixture(tmp_path)
    paths = scanner.source_input_paths()
    assert "acceptance.json" in paths
    assert "acceptance/test_external.py" in paths

    document = scanner.scan("a" * 40)
    node = next(item for item in document.nodes if item.source_symbol == node_id)
    expected = "sha256:" + hashlib.sha256(source.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    assert node.source_path == "acceptance/test_external.py"
    assert node.artifact_hash == expected


@pytest.mark.parametrize("staged", (False, True))
def test_acceptance_source_staged_and_unstaged_mutation_fail_provenance(tmp_path, staged):
    from backend.scripts import audit_capability_business_rules as command

    root, scanner, source, _node_id = _acceptance_fixture(tmp_path)
    clean = command._capture_provenance(
        root, source_roots=scanner.source_roots(), input_paths=scanner.source_input_paths(),
    )
    assert clean.revision == subprocess.run(
        ("git", "rev-parse", "HEAD"), cwd=root, check=True, capture_output=True, text=True,
    ).stdout.strip()
    source.write_text("def test_success_case():\n    assert False\n", encoding="utf-8")
    if staged:
        subprocess.run(("git", "add", "acceptance/test_external.py"), cwd=root, check=True)
    with pytest.raises(RuntimeError, match="business_audit_relevant_tree_dirty"):
        command._capture_provenance(
            root, source_roots=scanner.source_roots(), input_paths=scanner.source_input_paths(),
        )


def test_untracked_acceptance_source_fails_provenance(tmp_path):
    from backend.scripts import audit_capability_business_rules as command

    root, scanner, _source, _node_id = _acceptance_fixture(tmp_path, tracked_source=False)
    with pytest.raises(RuntimeError, match="business_audit_relevant_tree_dirty"):
        command._capture_provenance(
            root, source_roots=scanner.source_roots(), input_paths=scanner.source_input_paths(),
        )


def test_acceptance_source_mutation_between_probes_aborts_after_consuming_change(tmp_path):
    from backend.scripts import audit_capability_business_rules as command

    root, scanner, source, node_id = _acceptance_fixture(tmp_path)
    probe = lambda: command._capture_provenance(
        root, source_roots=scanner.source_roots(), input_paths=scanner.source_input_paths(),
    )
    web = command._InputProvenance("b" * 40, "sha256:" + "2" * 64, ("web/main.js",))

    def mutate_and_scan(revision):
        source.write_text("def test_success_case():\n    assert False\n", encoding="utf-8")
        document = scanner.scan(revision)
        assert any(item.source_symbol == node_id for item in document.nodes)
        return document

    with pytest.raises(RuntimeError, match="business_audit_relevant_tree_dirty"):
        command._stable_scan(mutate_and_scan, probe, lambda: web)
