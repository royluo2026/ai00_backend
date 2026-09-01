from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
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
