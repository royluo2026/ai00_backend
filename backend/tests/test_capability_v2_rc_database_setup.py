from __future__ import annotations

from pathlib import Path

import pytest

from backend.capability_v2.domain_manifest import load_domain_manifests
from backend.capability_v2.rc_database_bootstrap import (
    BootstrapRequest,
    build_bootstrap_plan,
    render_bootstrap_env,
)
from backend.scripts.run_capability_v2_rc_database_setup import (
    RcDatabaseSetupError,
    main,
)


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "backend/capability_v2/official_domains.json"


def _write_env(tmp_path: Path) -> tuple[Path, object]:
    request = BootstrapRequest(
        environment_id="capability-v2-local-rc",
        host="127.0.0.1",
        url_tenant="capability_test",
    )
    plan = build_bootstrap_plan(
        ROOT,
        request,
        tenant="capability_test",
        port=2881,
    )
    path = tmp_path / "capability-v2-rc.env"
    path.write_text(render_bootstrap_env(plan), encoding="utf-8")
    return path, plan


def _database_env_names() -> set[str]:
    manifests = load_domain_manifests(MANIFEST)
    return {
        name
        for manifest in manifests.domains
        for name in (
            manifest.database.runtime_url_env,
            manifest.database.ddl_url_env,
        )
    }


def test_setup_applies_all_eleven_domain_migrations_in_stable_order(tmp_path, capsys):
    env_file, _plan = _write_env(tmp_path)
    manifests = load_domain_manifests(MANIFEST)
    calls = []
    base_environment = {"PATH": "safe", "UNRELATED": "preserved"}

    def migrate(domain_id, environment):
        calls.append((domain_id, dict(environment)))
        return 0

    assert main(
        ["--env-file", str(env_file)],
        root=ROOT,
        environ=base_environment,
        migrate=migrate,
    ) == 0

    domain_ids = sorted(domain.domain_id for domain in manifests.domains)
    assert [domain_id for domain_id, _environment in calls] == domain_ids
    for _domain_id, environment in calls:
        assert set(environment) == {"PATH", "UNRELATED", *_database_env_names()}
        assert environment["PATH"] == "safe"
    assert base_environment == {"PATH": "safe", "UNRELATED": "preserved"}
    captured = capsys.readouterr()
    assert '"domains": 11' in captured.out
    assert '"status": "migrated"' in captured.out
    assert "mysql+pymysql://" not in captured.out + captured.err


def test_setup_stops_after_first_domain_migration_failure(tmp_path):
    env_file, _plan = _write_env(tmp_path)
    calls = []

    def migrate(domain_id, _environment):
        calls.append(domain_id)
        return 1 if domain_id == "knowledge" else 0

    with pytest.raises(RcDatabaseSetupError, match="migration_failed:knowledge"):
        main(
            ["--env-file", str(env_file)],
            root=ROOT,
            environ={},
            migrate=migrate,
        )

    assert "ontology" not in calls
    assert calls[-1] == "knowledge"


def test_setup_exports_only_exact_database_urls_to_runner_environment(tmp_path):
    env_file, _plan = _write_env(tmp_path)
    job_env = tmp_path / "gitea-job.env"
    job_env.write_text("PREEXISTING=safe\n", encoding="utf-8")

    assert main(
        [
            "--env-file",
            str(env_file),
            "--export-job-env",
            str(job_env),
        ],
        root=ROOT,
        environ={"UNRELATED": "not-exported"},
        migrate=lambda _domain, _environment: 0,
    ) == 0

    records = dict(line.split("=", 1) for line in job_env.read_text().splitlines())
    assert records["PREEXISTING"] == "safe"
    assert set(records) == {"PREEXISTING", *_database_env_names()}
    assert "AI00_RC_ENVIRONMENT_ID" not in records
    assert "UNRELATED" not in records


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda text: text.replace("AI00_AGENT_DB_URL=", "AI00_UNKNOWN_DB_URL=", 1),
            "env_keys_mismatch",
        ),
        (
            lambda text: text + text.splitlines()[5] + "\n",
            "env_duplicate_key",
        ),
        (
            lambda text: text + "UNRELATED_OVERRIDE=bad\n",
            "env_keys_mismatch",
        ),
        (
            lambda text: text.replace(
                "AI00_RC_ENVIRONMENT_ID=capability-v2-local-rc",
                "AI00_RC_ENVIRONMENT_ID=production",
            ),
            "production_environment_forbidden",
        ),
    ],
)
def test_setup_rejects_invalid_or_injected_env_document(
    tmp_path, mutation, message
):
    env_file, _plan = _write_env(tmp_path)
    env_file.write_text(
        mutation(env_file.read_text(encoding="utf-8")),
        encoding="utf-8",
    )

    with pytest.raises(RcDatabaseSetupError, match=message):
        main(
            ["--env-file", str(env_file)],
            root=ROOT,
            environ={},
            migrate=lambda *_args: pytest.fail("invalid env must fail before migration"),
        )
