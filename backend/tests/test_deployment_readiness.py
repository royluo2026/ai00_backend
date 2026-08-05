from pathlib import Path

from backend.scripts.runtime_preflight import evaluate


def test_runtime_preflight_requires_modules_and_explicit_domain_urls(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            f"{name}=mysql://user:pass@db:2881/workmanship"
            for name in (
                "USERS_DB_URL",
                "AI00_CRAFT_DB_URL",
                "AI00_AGENT_DB_URL",
                "AI00_SIMULATION_DB_URL",
                "AI00_DEVICE_DB_URL",
            )
        ),
        encoding="utf-8",
    )
    assert evaluate(env_file) == []


def test_runtime_preflight_rejects_missing_domain_url(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("USERS_DB_URL=mysql://user:pass@db:2881/workmanship\n", encoding="utf-8")
    errors = evaluate(env_file)
    assert any("AI00_CRAFT_DB_URL" in error for error in errors)


def test_deploy_uses_readiness_not_liveness():
    deploy = (Path(__file__).resolve().parents[2] / "scripts" / "deploy.bat").read_text(encoding="utf-8")
    assert "runtime_preflight.py" in deploy
    assert "run_migrations.py" in deploy
    assert "http://127.0.0.1:8082/ready" in deploy
