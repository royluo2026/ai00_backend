import os
import stat
import subprocess
import socket
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from dotenv import dotenv_values

from backend.db.table_prefix import validate_runtime_profile
from backend.scripts.runtime_preflight import REQUIRED_DB_URLS, evaluate, read_controlled_values


def profile_values(profile: str = "test") -> dict[str, str]:
    values = {
        name: f"mysql://account_{index}:secret@db.example:2881/workmanship"
        for index, name in enumerate(REQUIRED_DB_URLS)
    }
    values.update({
        "AI00_DEPLOY_PROFILE": profile,
        "TABLE_PREFIX": "pp_" if profile == "production" else "test_",
        "PUBLIC_URL": "https://workmanship-backend.chehejia.com" if profile == "production"
                      else "http://127.0.0.1:8080",
        "PORT": "8080",
        "BACKEND_BASE_URL": "https://workmanship-backend.chehejia.com" if profile == "production"
                            else "http://127.0.0.1:8080",
        "FEISHU_REDIRECT_URI": ("https://workmanship-backend.chehejia.com" if profile == "production"
                                else "http://127.0.0.1:8080") + "/auth/feishu/callback",
        "FEISHU_APP_ID": "fixture-app", "FEISHU_APP_SECRET": "fixture-secret", "JWT_SECRET": "fixture-jwt",
    })
    if profile == "production":
        values.update({"AI00_REQUIRE_MIGRATIONS": "1", "DEBUG": "false",
                       "CORS_ALLOW_ORIGINS": "https://workmanship-web.chehejia.com,app://root"})
    return values


def write_profile(path: Path, values: dict[str, str]) -> Path:
    path.write_text("\n".join(f"{key}={value}" for key, value in values.items()), encoding="utf-8")
    return path


@pytest.mark.parametrize("profile", ["test", "production"])
def test_managed_profile_templates_are_complete_but_not_runnable(profile: str):
    template = Path(__file__).resolve().parents[1] / f".env.{profile}.template"
    values = dotenv_values(template, interpolate=False)
    assert set(REQUIRED_DB_URLS) <= set(values)
    assert values["AI00_DEPLOY_PROFILE"] == profile
    assert values["TABLE_PREFIX"] == ("test_" if profile == "test" else "pp_")
    assert all(str(values[name]).startswith("REQUIRED_") for name in REQUIRED_DB_URLS)
    assert values["FEISHU_APP_SECRET"].startswith("REQUIRED_")
    errors = evaluate(template)
    assert any("USERS_DB_URL" in error for error in errors)
    assert any("FEISHU_APP_SECRET" in error for error in errors)
    if profile == "production":
        assert any("production CORS origins" in error for error in errors)


@pytest.mark.parametrize("profile", ["test", "production"])
def test_runtime_preflight_requires_modules_and_explicit_domain_urls(tmp_path: Path, profile: str):
    assert evaluate(write_profile(tmp_path / ".env", profile_values(profile))) == []


def test_runtime_preflight_rejects_missing_domain_url(tmp_path: Path):
    values = profile_values()
    values.pop("AI00_CRAFT_DB_URL")
    env_file = write_profile(tmp_path / ".env", values)
    errors = evaluate(env_file)
    assert any("AI00_CRAFT_DB_URL" in error for error in errors)


def test_runtime_preflight_rejects_duplicate_profile_before_database_access(tmp_path: Path):
    env_file = write_profile(tmp_path / ".env", profile_values())
    env_file.write_text(env_file.read_text(encoding="utf-8") + "\nAI00_DEPLOY_PROFILE=production",
                        encoding="utf-8")
    assert any("duplicate" in error for error in evaluate(env_file))


def test_runtime_preflight_refuses_linked_env_file(tmp_path: Path, monkeypatch):
    env_file = write_profile(tmp_path / ".env", profile_values())
    original = Path.lstat
    monkeypatch.setattr(Path, "lstat", lambda path: SimpleNamespace(st_mode=stat.S_IFLNK, st_size=1)
                        if path == env_file else original(path))
    assert any("missing or invalid" in error for error in evaluate(env_file))


def test_runtime_preflight_refuses_env_file_replaced_between_check_and_open(tmp_path: Path, monkeypatch):
    env_file = write_profile(tmp_path / ".env", profile_values())
    replacement = write_profile(tmp_path / "replacement", profile_values("production"))
    original_open = Path.open
    swapped = False

    def replace_before_open(path, *args, **kwargs):
        nonlocal swapped
        if path == env_file and not swapped:
            swapped = True
            os.replace(replacement, env_file)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", replace_before_open)
    with pytest.raises(ValueError, match="changed|invalid"):
        read_controlled_values(env_file)
    assert swapped


def test_runtime_preflight_refuses_env_file_grown_between_check_and_open(tmp_path: Path, monkeypatch):
    env_file = write_profile(tmp_path / ".env", profile_values())
    original_open = Path.open
    grown = False

    def grow_before_open(path, *args, **kwargs):
        nonlocal grown
        if path == env_file and not grown:
            grown = True
            with original_open(path, "ab") as stream:
                stream.write(b"\n#" + b" " * 65536)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", grow_before_open)
    with pytest.raises(ValueError, match="changed|invalid"):
        read_controlled_values(env_file)
    assert grown


@pytest.mark.parametrize("key", ["AI00_DEPLOY_PROFILE", "TABLE_PREFIX", "PUBLIC_URL",
                                 "BACKEND_BASE_URL", "AI00_DDL_DB_URL", "AI00_CRAFT_DDL_DB_URL",
                                 "AI00_LOCAL_INTEGRATION_DB_URL", "CORS_ALLOW_ORIGINS",
                                 "FEISHU_APP_SECRET", *REQUIRED_DB_URLS])
def test_runtime_preflight_rejects_loaded_process_drift(tmp_path: Path, key: str):
    values = profile_values()
    env_file = write_profile(tmp_path / ".env", values)
    process = {**values, key: "different-secret-or-address"}
    errors = evaluate(env_file, process_env=process)
    assert errors == ["managed runtime process configuration differs from ENV_FILE"]
    assert "different-secret-or-address" not in repr(errors)


def test_runtime_preflight_accepts_matching_loaded_process(tmp_path: Path):
    values = profile_values("production")
    env_file = write_profile(tmp_path / ".env", values)
    assert evaluate(env_file, process_env=values) == []


def test_managed_startup_checks_loaded_process_against_file():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "_runtime_preflight(_env_file, process_env=os.environ)" in source


@pytest.mark.parametrize(("change", "expected"), [
    ({"CORS_ALLOW_ORIGINS": ""}, "production CORS origins"),
    ({"CORS_ALLOW_ORIGINS": "*"}, "production CORS origins"),
    ({"CORS_ALLOW_ORIGINS": "http://127.0.0.1:5173"}, "production CORS origins"),
    ({"FEISHU_REDIRECT_URI": "http://127.0.0.1:8080/auth/feishu/callback"}, "Feishu redirect"),
    ({"AI00_REQUIRE_MIGRATIONS": "0"}, "requires AI00_REQUIRE_MIGRATIONS"),
    ({"DEBUG": "true"}, "requires DEBUG=false"),
    ({"PORT": ""}, "PORT"),
])
def test_production_preflight_rejects_insecure_runtime_exposure(tmp_path: Path, change, expected):
    errors = evaluate(write_profile(tmp_path / ".env", {**profile_values("production"), **change}))
    assert any(expected in error for error in errors), errors


@pytest.mark.parametrize("public_url", [
    "https://another-backend.example.com",
    "http://127.0.0.1:8082",
])
def test_test_preflight_requires_local_public_origin(tmp_path: Path, public_url: str):
    values = {**profile_values(), "PUBLIC_URL": public_url}
    errors = evaluate(write_profile(tmp_path / ".env", values))
    assert any("test PUBLIC_URL" in error for error in errors), errors
    with pytest.raises(ValueError, match="test profile requires local backend URL"):
        validate_runtime_profile("test", "test_", public_url)


def test_test_preflight_accepts_current_pc_host_on_8080(tmp_path: Path):
    public_url = f"http://{socket.gethostname().lower()}:8080"
    values = {**profile_values(), "PUBLIC_URL": public_url}
    assert evaluate(write_profile(tmp_path / ".env", values)) == []
    validate_runtime_profile("test", "test_", public_url)


@pytest.mark.parametrize(("change", "expected"), [
    ({"AI00_DEPLOY_PROFILE": ""}, "profile"),
    ({"AI00_DEPLOY_PROFILE": "prod"}, "profile"),
    ({"TABLE_PREFIX": "pp_"}, "prefix"),
    ({"PUBLIC_URL": "https://workmanship-backend.chehejia.com"}, "URL"),
    ({"AI00_LOCAL_INTEGRATION_DB_URL": "mysql://legacy:secret@db.example/workmanship"}, "legacy"),
    ({"AI00_FACTORY_DB_URL": "mysql://account_9:secret@other.example:2881/workmanship"}, "same"),
    ({"AI00_FACTORY_DB_URL": "mysql://account_9:secret@db.example:2881/other_database"}, "same"),
    ({"AI00_FACTORY_DB_URL": "mysql://account_9:secret@db.example:2881/workmanship?charset=utf8"}, "AI00_FACTORY_DB_URL"),
    ({"AI00_FACTORY_DB_URL": "mysql://account_9:secret@db.example:0/workmanship"}, "AI00_FACTORY_DB_URL"),
    ({"AI00_FACTORY_DB_URL": "mysql://account_9:secret@db.example:2881/workmanship/other"}, "AI00_FACTORY_DB_URL"),
    ({"AI00_FACTORY_DB_URL": "mysql://${DB_USER}:secret@db.example:2881/workmanship"}, "AI00_FACTORY_DB_URL"),
])
def test_runtime_preflight_refuses_cross_profile_or_ambiguous_account_before_connecting(
    tmp_path: Path, change: dict[str, str], expected: str,
):
    values = {**profile_values(), **change}
    errors = evaluate(write_profile(tmp_path / ".env", values))
    assert any(expected.lower() in error.lower() for error in errors), errors


def test_runtime_preflight_does_not_interpolate_parent_environment(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DB_USER", "account_9")
    values = profile_values()
    values["AI00_FACTORY_DB_URL"] = "mysql://${DB_USER}:secret@db.example:2881/workmanship"
    errors = evaluate(write_profile(tmp_path / ".env", values))
    assert any("AI00_FACTORY_DB_URL" in error for error in errors)


def test_runtime_preflight_cli_is_independent_of_import_mode(tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    env_file = write_profile(tmp_path / ".env", profile_values())
    command = [sys.executable, "-B", str(root / "backend/scripts/runtime_preflight.py"),
               "--env-file", str(env_file)]
    good = subprocess.run(command, capture_output=True, text=True, cwd=root)
    assert good.returncode == 0, good.stderr
    bad_values = profile_values("production")
    bad_values["TABLE_PREFIX"] = "test_"
    write_profile(env_file, bad_values)
    bad = subprocess.run(command, capture_output=True, text=True, cwd=root)
    assert bad.returncode == 2 and "TABLE_PREFIX" in bad.stdout


def test_legacy_deploy_refuses_before_copy_migration_or_restart():
    deploy = (Path(__file__).resolve().parents[2] / "scripts" / "deploy.bat").read_text(encoding="utf-8")
    lines = [line.strip().lower() for line in deploy.splitlines() if line.strip() and not line.startswith("@echo")]
    assert lines[-1] == "exit /b 2"
    assert "legacy deployment is disabled" in deploy.lower()
    for command in ("robocopy", "run_migrations.py", "nssm", "taskkill", "8082", "ai00-v2"):
        assert command not in deploy.lower()


def test_legacy_v2_setup_refuses_before_service_or_directory_changes():
    setup = (Path(__file__).resolve().parents[2] / "scripts" / "setup-deploy-v2.ps1").read_text(encoding="utf-8")
    assert "legacy v2 setup is disabled" in setup.lower()
    assert setup.strip().endswith("exit 2")
    for command in ("nssm", "get-service", "stop-service", "net stop", "remove-item",
                    "new-item", "robocopy", "run_migrations.py", "8082", "ai00-v2"):
        assert command not in setup.lower()
