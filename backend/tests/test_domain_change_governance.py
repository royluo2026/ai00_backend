from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OWNERSHIP = ROOT / "docs" / "governance" / "domain-ownership.json"
TABLE_OWNERSHIP = ROOT / "backend" / "governance" / "domain_table_ownership.json"
CHECKER = ROOT / "backend" / "scripts" / "check_domain_change_governance.py"
CI_WORKFLOWS = (
    ROOT / ".gitea" / "workflows" / "domain-boundaries.yml",
    ROOT / ".github" / "workflows" / "capability-v2-pr.yml",
)


def test_ownership_manifest_is_the_complete_domain_entry_point() -> None:
    document = json.loads(OWNERSHIP.read_text(encoding="utf-8"))
    table_document = json.loads(TABLE_OWNERSHIP.read_text(encoding="utf-8"))

    assert document["schema_version"] == 2
    assert document["table_ownership_source"] == (
        "backend/governance/domain_table_ownership.json"
    )
    assert document["shared_paths"]

    table_owners = {row["owner"] for row in table_document["tables"]}
    declared_ids = set()
    declared_table_owners = set()
    for descriptor in document["domains"].values():
        declared_ids.add(descriptor["domain_id"])
        declared_table_owners.add(descriptor["table_owner"])
        assert descriptor["maintainers"]
        assert descriptor["capability_prefixes"]
        assert "frontend_paths" in descriptor

    assert len(declared_ids) == len(document["domains"])
    assert declared_table_owners == table_owners


def test_shared_paths_declare_platform_review_and_affected_domain_tests() -> None:
    document = json.loads(OWNERSHIP.read_text(encoding="utf-8"))

    for rule in document["shared_paths"]:
        assert rule["path"]
        assert "@ai00/base-maintainers" in rule["maintainers"]
        assert rule["review_policy"] == "platform_and_affected_domains"
        assert rule["required_checks"]

    assert document["frontend_shared_paths"]
    for rule in document["frontend_shared_paths"]:
        assert "@ai00/base-maintainers" in rule["maintainers"]
        assert rule["review_policy"] == "platform_and_affected_domains"
        assert rule["required_checks"]


def test_repository_ownership_checker_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Domain change governance check passed" in result.stdout


def test_pull_request_gates_run_domain_change_governance() -> None:
    for workflow in CI_WORKFLOWS:
        content = workflow.read_text(encoding="utf-8")
        assert "python backend/scripts/check_domain_change_governance.py --check" in content


def test_checker_rejects_shared_path_without_platform_codeowner(tmp_path: Path) -> None:
    (tmp_path / "docs" / "governance").mkdir(parents=True)
    (tmp_path / "backend" / "governance").mkdir(parents=True)
    (tmp_path / ".github").mkdir()
    ownership = {
        "schema_version": 2,
        "table_ownership_source": "backend/governance/domain_table_ownership.json",
        "shared_paths": [
            {
                "path": "backend/core/**",
                "maintainers": ["@ai00/base-maintainers"],
                "review_policy": "platform_and_affected_domains",
                "required_checks": ["backend regression"],
            }
        ],
        "domains": {
            "Base Platform": {
                "domain_id": "base",
                "table_owner": "base",
                "capability_prefixes": ["base."],
                "frontend_paths": [],
                "maintainers": ["@ai00/base-maintainers"],
                "code_paths": ["backend/base/**"],
                "migration_paths": [],
            }
        },
    }
    table_ownership = {"tables": [{"table": "workmanship_base_item", "owner": "base"}]}
    (tmp_path / "docs" / "governance" / "domain-ownership.json").write_text(
        json.dumps(ownership), encoding="utf-8"
    )
    (tmp_path / "backend" / "governance" / "domain_table_ownership.json").write_text(
        json.dumps(table_ownership), encoding="utf-8"
    )
    (tmp_path / ".github" / "CODEOWNERS").write_text(
        "/backend/base/** @ai00/base-maintainers\n", encoding="utf-8"
    )

    result = subprocess.run(
        [sys.executable, str(CHECKER), "--check", "--root", str(tmp_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "shared path backend/core/**" in result.stdout


def test_checker_validates_frontend_domain_owners(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend-repository"
    frontend_root = tmp_path / "frontend-repository"
    (backend_root / "docs" / "governance").mkdir(parents=True)
    (backend_root / "backend" / "governance").mkdir(parents=True)
    (backend_root / ".github").mkdir()
    (frontend_root / ".github").mkdir(parents=True)
    ownership = {
        "schema_version": 2,
        "table_ownership_source": "backend/governance/domain_table_ownership.json",
        "shared_paths": [],
        "frontend_shared_paths": [],
        "domains": {
            "Craft": {
                "domain_id": "craft",
                "table_owner": "craft",
                "capability_prefixes": ["craft."],
                "frontend_paths": ["packages/craft-plugin/**"],
                "maintainers": ["@ai00/craft-maintainers"],
                "code_paths": ["plugins/craft/**"],
                "migration_paths": [],
            }
        },
    }
    table_ownership = {"tables": [{"table": "workmanship_craft_item", "owner": "craft"}]}
    (backend_root / "docs" / "governance" / "domain-ownership.json").write_text(
        json.dumps(ownership), encoding="utf-8"
    )
    (backend_root / "backend" / "governance" / "domain_table_ownership.json").write_text(
        json.dumps(table_ownership), encoding="utf-8"
    )
    (backend_root / ".github" / "CODEOWNERS").write_text(
        "/plugins/craft/** @ai00/craft-maintainers\n", encoding="utf-8"
    )
    (frontend_root / ".github" / "CODEOWNERS").write_text(
        "/packages/craft-plugin/** @ai00/base-maintainers\n", encoding="utf-8"
    )

    result = subprocess.run(
        [
            sys.executable,
            str(CHECKER),
            "--check",
            "--root",
            str(backend_root),
            "--frontend-root",
            str(frontend_root),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "frontend path packages/craft-plugin/**" in result.stdout
