import json
import io
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

from backend.governance import load_registry
from backend.scripts.generate_domain_grants import (
    GrantPolicyError, build_domain_grant_plan, parse_accounts, render_domain_grants,
    require_current_source_inventory, validate_grant_profile,
)
from backend.scripts import verify_single_database_grants
from backend.scripts import generate_domain_grants
from backend.scripts.verify_domain_db_isolation import URLS


ROOT = Path(__file__).resolve().parents[2]
INVENTORY = json.loads((ROOT / "backend/governance/table_inventory.json").read_text(encoding="utf-8"))
DOMAINS = tuple(load_registry().product_domains)
ACCOUNTS = {domain: f"account_{domain}" for domain in DOMAINS}


def profile_environment(prefix):
    profile = "test" if prefix == "test_" else "production"
    return {
        "AI00_DEPLOY_PROFILE": profile, "TABLE_PREFIX": prefix,
        "PUBLIC_URL": "http://127.0.0.1:8080" if profile == "test"
                      else "https://workmanship-backend.chehejia.com",
        **{variable: f"mysql://{ACCOUNTS[domain]}:fixture@db.example:2881/workmanship"
           for domain, variable in URLS.items()},
    }


@pytest.mark.parametrize("prefix", ["test_", "pp_"])
def test_proposal_grants_only_owned_tables_in_selected_prefix(prefix):
    plan = build_domain_grant_plan(ACCOUNTS, INVENTORY)
    assert len(plan.accounts) == 11
    assert sum(len(item.tables) for item in plan.accounts) == 383
    sql = render_domain_grants(INVENTORY, database="workmanship", table_prefix=prefix,
                               host="%", accounts=ACCOUNTS, include_revokes=True)
    grant_lines = [line for line in sql.splitlines() if line.startswith("GRANT ")]
    assert len(grant_lines) == 383
    for item in plan.accounts:
        own_lines = [line for line in grant_lines if f"TO '{item.account}'@'%'" in line]
        assert len(own_lines) == len(item.tables)
        assert all(f"`workmanship`.`{prefix}{table}`" in own_lines[index]
                   for index, table in enumerate(item.tables))
    opposite = "pp_" if prefix == "test_" else "test_"
    assert all(f"`{opposite}" not in line for line in grant_lines)
    assert f"REVOKE ALL PRIVILEGES ON `workmanship`.`{opposite}" in sql
    assert not any(keyword in line for line in grant_lines for keyword in (" CREATE ", " ALTER ", " DROP "))


@pytest.mark.parametrize("bad", ["", "workmanship_", "other_", "test_`"])
def test_unapproved_prefix_cannot_render_grants(bad):
    with pytest.raises(GrantPolicyError, match="table prefix"):
        render_domain_grants(INVENTORY, database="workmanship", table_prefix=bad,
                             host="%", accounts=ACCOUNTS)


def test_shared_runtime_account_is_accepted_but_duplicate_domain_is_rejected():
    shared={domain:'shared' for domain in DOMAINS}
    values=[f'{domain}=shared' for domain in DOMAINS]
    assert parse_accounts(values,set(DOMAINS))==shared
    with pytest.raises(GrantPolicyError,match='duplicate'):
        parse_accounts(values+[values[0]],set(DOMAINS))
    plan=build_domain_grant_plan(shared,INVENTORY)
    tables={row['table'] for row in INVENTORY['tables']}
    assert all(set(item.tables)==tables for item in plan.accounts)
    sql=render_domain_grants(INVENTORY,database='workmanship',table_prefix='test_',host='%',accounts=shared,include_revokes=True)
    assert 'REVOKE' not in sql


@pytest.mark.parametrize("mutation", [
    lambda data: data.update(table_count=382),
    lambda data: data["tables"].__setitem__(0, {**data["tables"][0], "runtime_domain": "craft"}),
    lambda data: data["tables"].__setitem__(0, data["tables"][1]),
    lambda data: data["tables"].__setitem__(0, {**data["tables"][0], "table": "unknown_table"}),
])
def test_inventory_drift_is_rejected_before_sql(mutation):
    inventory = json.loads(json.dumps(INVENTORY))
    mutation(inventory)
    with pytest.raises(GrantPolicyError):
        build_domain_grant_plan(ACCOUNTS, inventory)


def test_cli_requires_prefix_and_refuses_legacy_grouped_policy():
    base = [sys.executable, "-B", str(ROOT / "backend/scripts/generate_domain_grants.py"),
            "--database", "workmanship"]
    no_prefix = subprocess.run(base, capture_output=True, text=True, cwd=ROOT)
    assert no_prefix.returncode != 0 and not no_prefix.stdout
    grouped = subprocess.run(base + ["--table-prefix", "pp_", "--account-group", "runtime=shared"],
                             capture_output=True, text=True, cwd=ROOT)
    assert grouped.returncode != 0 and not grouped.stdout
    assert "shared usernames are allowed" in grouped.stderr


@pytest.mark.parametrize("prefix", ["test_", "pp_"])
def test_grant_cli_is_bound_to_explicit_profile_file(monkeypatch, capsys, tmp_path, prefix):
    environment = profile_environment(prefix)
    env_file = tmp_path / "profile.env"
    env_file.write_text("\n".join(f"{key}={value}" for key, value in environment.items()), encoding="utf-8")
    command = [sys.executable, "-B", str(ROOT / "backend/scripts/generate_domain_grants.py"),
               "--database", "workmanship", "--table-prefix", prefix, "--env-file", str(env_file)]
    for domain, account in ACCOUNTS.items():
        command.extend(("--account", f"{domain}={account}"))
    monkeypatch.setattr(generate_domain_grants, "audit_repository",
                        lambda root, registry: ([], sorted(row["table"] for row in INVENTORY["tables"])))
    monkeypatch.setattr(sys, "argv", command[2:])
    assert generate_domain_grants.main() == 0
    assert capsys.readouterr().out.count("GRANT ") == 383
    wrong_command = command.copy()
    wrong_command[4] = "other_database"
    wrong = subprocess.run(wrong_command,
                           capture_output=True, text=True, cwd=ROOT)
    assert wrong.returncode != 0 and not wrong.stdout


def test_grant_proposal_refuses_duplicate_profile_assignment(tmp_path):
    env_file = tmp_path / "profile.env"
    env_file.write_text("\n".join(f"{key}={value}" for key, value in
                                  profile_environment("test_").items()) +
                        "\nAI00_REQUIRE_MIGRATIONS=0\nAI00_REQUIRE_MIGRATIONS=0\n", encoding="utf-8")
    command = [sys.executable, "-B", str(ROOT / "backend/scripts/generate_domain_grants.py"),
               "--database", "workmanship", "--table-prefix", "test_", "--env-file", str(env_file)]
    for domain, account in ACCOUNTS.items():
        command.extend(("--account", f"{domain}={account}"))
    result = subprocess.run(command, capture_output=True, text=True, cwd=ROOT)
    assert result.returncode != 0 and not result.stdout and "duplicate" in result.stderr


def test_show_grants_refuses_duplicate_profile_assignment(monkeypatch, tmp_path, capsys):
    env_file = tmp_path / "profile.env"
    env_file.write_text("\n".join(f"{key}={value}" for key, value in
                                  profile_environment("test_").items()) +
                        "\nAI00_REQUIRE_MIGRATIONS=0\nAI00_REQUIRE_MIGRATIONS=0\n", encoding="utf-8")
    argv = ["verify_single_database_grants.py", "--database", "workmanship",
            "--table-prefix", "test_", "--env-file", str(env_file)]
    for domain, account in ACCOUNTS.items():
        argv.extend(("--account", f"{domain}={account}"))
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({domain: [] for domain in DOMAINS})))
    with pytest.raises(ValueError, match="duplicate"):
        verify_single_database_grants.main()
    assert not capsys.readouterr().out


@pytest.mark.parametrize("module", [generate_domain_grants, verify_single_database_grants])
def test_grant_cli_refuses_linked_profile_before_output(monkeypatch, tmp_path, capsys, module):
    env_file = tmp_path / "profile.env"
    env_file.write_text("\n".join(f"{key}={value}" for key, value in
                                  profile_environment("test_").items()), encoding="utf-8")
    import stat
    from types import SimpleNamespace
    original = type(env_file).lstat
    monkeypatch.setattr(type(env_file), "lstat", lambda path: SimpleNamespace(st_mode=stat.S_IFLNK, st_size=1) if path == env_file else original(path))
    argv = ["grant-cli", "--database", "workmanship", "--table-prefix", "test_",
            "--env-file", str(env_file)]
    for domain, account in ACCOUNTS.items():
        argv.extend(("--account", f"{domain}={account}"))
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({domain: [] for domain in DOMAINS})))
    with pytest.raises(ValueError, match="missing or invalid"):
        module.main()
    assert not capsys.readouterr().out


@pytest.mark.parametrize("prefix", ["test_", "pp_"])
def test_grant_profile_rejects_cross_environment_or_cross_domain_target(prefix):
    values = profile_environment(prefix)
    validate_grant_profile(values, database="workmanship", table_prefix=prefix, accounts=ACCOUNTS)
    for change in (
        {"TABLE_PREFIX": "pp_" if prefix == "test_" else "test_"},
        {"AI00_DEPLOY_PROFILE": "production" if prefix == "test_" else "test"},
        {"AI00_AGENT_DB_URL": "mysql://account_agent:fixture@other.example:2881/workmanship"},
        {"AI00_AGENT_DB_URL": "mysql://account_agent:fixture@db.example:2881/other_database"},
        {"AI00_LOCAL_INTEGRATION_DB_URL": "mysql://other:fixture@db.example/workmanship"},
    ):
        with pytest.raises(GrantPolicyError):
            validate_grant_profile({**values, **change}, database="workmanship",
                                   table_prefix=prefix, accounts=ACCOUNTS)
    with pytest.raises(GrantPolicyError, match="account identity"):
        validate_grant_profile(values, database="workmanship", table_prefix=prefix,
                               accounts={**ACCOUNTS, "agent": "other"})


@pytest.mark.parametrize("prefix", ["test_", "pp_"])
def test_show_grants_verifier_checks_eleven_account_and_prefix_scopes(monkeypatch, capsys, tmp_path, prefix):
    monkeypatch.setattr(verify_single_database_grants, "require_current_source_inventory",
                        lambda inventory, registry: None)
    sql = render_domain_grants(INVENTORY, database="workmanship", table_prefix=prefix,
                               host="%", accounts=ACCOUNTS)
    document = {domain: ["GRANT USAGE ON *.* TO '" + account + "'@'%'"]
                for domain, account in ACCOUNTS.items()}
    for line in sql.splitlines():
        if line.startswith("GRANT "):
            domain = next(domain for domain, account in ACCOUNTS.items()
                          if line.endswith(f"TO '{account}'@'%';"))
            document[domain].append(line)
    argv = ["verify_single_database_grants.py", "--database", "workmanship",
            "--table-prefix", prefix]
    env_file = tmp_path / "profile.env"
    env_file.write_text("\n".join(f"{key}={value}" for key, value in profile_environment(prefix).items()),
                        encoding="utf-8")
    argv.extend(("--env-file", str(env_file)))
    for domain, account in ACCOUNTS.items():
        argv.extend(("--account", f"{domain}={account}"))

    def check(rows):
        monkeypatch.setattr(sys, "argv", argv)
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(rows)))
        result = verify_single_database_grants.main()
        return result, json.loads(capsys.readouterr().out)

    result, report = check(document)
    assert result == 0 and report["passed"] is True
    assert len(report["accounts"]) == 11
    opposite = "pp_" if prefix == "test_" else "test_"
    tampered = json.loads(json.dumps(document))
    tampered["base"].append(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON `workmanship`.`{opposite}workmanship_auth_users` "
        f"TO '{ACCOUNTS['base']}'@'%';"
    )
    result, report = check(tampered)
    assert result == 1 and report["passed"] is False
    assert any(row["account_label"] == "base" and row["extra_tables"] for row in report["accounts"])

    tampered = json.loads(json.dumps(document))
    tampered["base"][0] = "GRANT USAGE ON *.* TO 'other_account'@'%'"
    result, report = check(tampered)
    assert result == 1 and any("account_identity_mismatch" in row["failures"] for row in report["accounts"])


def test_current_source_inventory_drift_refuses_grant_cli_and_verifier(monkeypatch, capsys, tmp_path):
    source_tables = sorted(row["table"] for row in INVENTORY["tables"])
    monkeypatch.setattr(generate_domain_grants, "audit_repository",
                        lambda root, registry: ([], source_tables + ["workmanship_sim_unowned_new"]))
    with pytest.raises(GrantPolicyError, match="current source table inventory"):
        require_current_source_inventory(INVENTORY)
    monkeypatch.setattr(generate_domain_grants, "audit_repository",
                        lambda root, registry: ([SimpleNamespace(category="unowned_table")], source_tables))
    with pytest.raises(GrantPolicyError, match="current source table inventory"):
        require_current_source_inventory(INVENTORY)
    environment = profile_environment("test_")
    env_file = tmp_path / "profile.env"
    env_file.write_text("\n".join(f"{key}={value}" for key, value in environment.items()), encoding="utf-8")
    argv = ["grant-cli", "--database", "workmanship", "--table-prefix", "test_",
            "--env-file", str(env_file)]
    for domain, account in ACCOUNTS.items():
        argv.extend(("--account", f"{domain}={account}"))
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(GrantPolicyError, match="current source table inventory"):
        generate_domain_grants.main()
    assert not capsys.readouterr().out
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({domain: [] for domain in DOMAINS})))
    monkeypatch.setattr(verify_single_database_grants, "require_current_source_inventory",
                        require_current_source_inventory)
    with pytest.raises(GrantPolicyError, match="current source table inventory"):
        verify_single_database_grants.main()
    assert not capsys.readouterr().out
