from __future__ import annotations

import json
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path

from backend.governance import load_registry as load_runtime_domain_registry
from backend.scripts import check_domain_dependencies as dependency_checker


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OWNERSHIP_PATH = REPOSITORY_ROOT / "docs" / "governance" / "domain-ownership.json"
BASELINE_PATH = REPOSITORY_ROOT / "docs" / "governance" / "domain-dependency-baseline.json"
CHECKER_PATH = REPOSITORY_ROOT / "backend" / "scripts" / "check_domain_dependencies.py"
CODEOWNERS_PATH = REPOSITORY_ROOT / ".github" / "CODEOWNERS"
EXPECTED_DOMAINS = {
    "Base Platform",
    "Agent",
    "Craft",
    "Digital Model",
    "Factory",
    "Integration",
    "Project Management",
    "Simulation",
    "Ontology",
    "Knowledge",
    "Local Runtime",
}
DOMAIN_SLUGS = {
    "Base Platform": "base",
    "Agent": "agent",
    "Craft": "craft",
    "Digital Model": "digital_model",
    "Factory": "factory",
    "Integration": "integration",
    "Project Management": "project_management",
    "Simulation": "simulation",
    "Ontology": "ontology",
    "Knowledge": "knowledge",
    "Local Runtime": "local_runtime",
}


def _ownership() -> dict:
    return json.loads(OWNERSHIP_PATH.read_text(encoding="utf-8"))


def test_every_first_class_domain_has_an_independent_release_owner():
    document = _ownership()

    assert document["schema_version"] == 1
    assert set(document["domains"]) == EXPECTED_DOMAINS
    for name, domain in document["domains"].items():
        assert domain["maintainers"], name
        assert domain["artifact"], name
        assert domain["provider_paths"], name
        assert domain["test_paths"], name
        assert domain["documentation_paths"], name


def test_owned_code_patterns_are_unique_and_project_management_overrides_craft_legacy_paths():
    document = _ownership()
    claims: dict[str, str] = {}
    for domain, descriptor in document["domains"].items():
        for pattern in descriptor["code_paths"]:
            assert pattern not in claims, f"{pattern} is claimed by {claims[pattern]} and {domain}"
            claims[pattern] = domain

    project_patterns = set(document["domains"]["Project Management"]["code_paths"])
    assert "plugins/craft/craft_backend/routers/projects.py" in project_patterns
    assert "plugins/craft/craft_backend/routers/workbench_home.py" in project_patterns


def test_factory_and_integration_reserve_unique_foundation_paths():
    document = _ownership()
    expected = {
        "Factory": {
            "code_paths": "plugins/factory/**",
            "migration_paths": "plugins/factory/migrations/**",
            "provider_paths": "plugins/factory/factory_backend/capabilities/**",
            "test_paths": "plugins/factory/tests/**",
            "documentation_paths": "docs/capabilities/factory/**",
        },
        "Integration": {
            "code_paths": "plugins/integration/**",
            "migration_paths": "backend/db/migrations/domains/integration/**",
            "provider_paths": "plugins/integration/integration_backend/capabilities/**",
            "test_paths": "plugins/integration/tests/**",
            "documentation_paths": "docs/capabilities/integration/**",
        },
    }

    for domain_name, paths in expected.items():
        descriptor = document["domains"][domain_name]
        for field, path in paths.items():
            assert path in descriptor[field], (domain_name, field, path)


def test_every_versioned_migration_has_exactly_one_domain_owner():
    document = _ownership()
    migrations = {
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in (REPOSITORY_ROOT / "backend" / "db" / "migrations").glob("*.sql")
    }
    claims = {
        domain: descriptor["migration_paths"]
        for domain, descriptor in document["domains"].items()
    }

    for migration in migrations:
        owners = [domain for domain, patterns in claims.items() if any(fnmatch(migration, p) for p in patterns)]
        assert len(owners) == 1, f"{migration}: owners={owners}"
    declared = {pattern for patterns in claims.values() for pattern in patterns if "*" not in pattern}
    assert declared <= migrations


def test_runtime_database_governance_uses_the_same_first_class_domains():
    registry = load_runtime_domain_registry()

    assert set(registry.product_domains) == set(DOMAIN_SLUGS.values())
    assert registry.data_owners["knowledge"]["runtime_domain"] == "knowledge"
    assert registry.table_owner("workmanship_proj_tasks").owner == "project_management"
    assert registry.table_owner("workmanship_onto_concepts").owner == "ontology"
    assert registry.table_owner("workmanship_know_documents").owner == "knowledge"
    assert registry.migration_owner("202608050002", "craft") == "project_management"
    assert registry.migration_owner("202608050003", "craft") == "project_management"
    assert registry.migration_owner("202608060003", "base") == "ontology"
    assert registry.migration_allows_table("202608030005", "workmanship_work_task_dependencies")
    for exception in registry.migration_table_exceptions.values():
        assert exception["tables"]
        assert all("*" not in table for table in exception["tables"])
        assert len(exception["reason"].strip()) >= 40


def test_dependency_baseline_is_exact_and_checker_rejects_new_violations():
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    assert baseline["schema_version"] == 1
    for violation in baseline["violations"]:
        assert set(violation) == {"source", "imported_module", "source_domain", "target_domain", "reason"}
        assert "*" not in violation["source"]
        assert "*" not in violation["imported_module"]

    result = subprocess.run(
        [sys.executable, str(CHECKER_PATH), "--check"],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_dependency_checker_rejects_private_cross_domain_imports(tmp_path, monkeypatch):
    source = tmp_path / "plugins" / "craft" / "consumer.py"
    target = (
        tmp_path
        / "plugins"
        / "factory"
        / "factory_backend"
        / "infrastructure"
        / "database.py"
    )
    source.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    source.write_text(
        "import plugins.factory.factory_backend.infrastructure.database\n",
        encoding="utf-8",
    )
    target.write_text("DATABASE = object()\n", encoding="utf-8")
    ownership = {
        "shared_import_prefixes": [
            "backend.capability_v2",
            "backend.contracts",
            "backend.domain_ports",
            "backend.platform_sdk",
        ],
        "domains": {
            "Craft": {
                "module_prefixes": ["plugins.craft"],
                "code_paths": ["plugins/craft/**"],
            },
            "Factory": {
                "module_prefixes": ["plugins.factory.factory_backend"],
                "code_paths": ["plugins/factory/**"],
            },
        },
    }
    monkeypatch.setattr(dependency_checker, "REPOSITORY_ROOT", tmp_path)

    violations, errors = dependency_checker.discover_violations(ownership)

    assert errors == []
    assert [(row["source_domain"], row["target_domain"]) for row in violations] == [
        ("Craft", "Factory")
    ]


def test_dependency_checker_allows_shared_domain_ports(tmp_path, monkeypatch):
    source = tmp_path / "plugins" / "craft" / "consumer.py"
    source.parent.mkdir(parents=True)
    source.write_text("import backend.domain_ports.factory\n", encoding="utf-8")
    ownership = {
        "shared_import_prefixes": [
            "backend.capability_v2",
            "backend.contracts",
            "backend.domain_ports",
            "backend.platform_sdk",
        ],
        "domains": {
            "Craft": {
                "module_prefixes": ["plugins.craft"],
                "code_paths": ["plugins/craft/**"],
            }
        },
    }
    monkeypatch.setattr(dependency_checker, "REPOSITORY_ROOT", tmp_path)

    violations, errors = dependency_checker.discover_violations(ownership)

    assert errors == []
    assert violations == []


def test_codeowners_names_every_domain_maintainer_group():
    document = _ownership()
    rules = {
        (parts[0], owner)
        for line in CODEOWNERS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
        for parts in [line.split()]
        for owner in parts[1:]
    }

    for domain_name, domain in document["domains"].items():
        for owned_path in domain["code_paths"] + domain["migration_paths"]:
            assert any((f"/{owned_path}", maintainer) in rules for maintainer in domain["maintainers"]), (
                domain_name,
                owned_path,
            )
