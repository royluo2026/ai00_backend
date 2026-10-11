from pathlib import Path
import os
import subprocess
import sys

MAIN_FILE = Path(__file__).resolve().parents[2] / 'backend' / 'main.py'


def test_backend_main_uses_absolute_static_path():
    text = MAIN_FILE.read_text(encoding='utf-8')
    assert 'Path(__file__).parent / "static"' in text
    assert 'StaticFiles(directory=str(_STATIC_DIR), check_dir=False)' in text


def test_explicit_profiles_never_mount_legacy_browser_dist(tmp_path):
    from backend.frontend_static import legacy_browser_dist

    legacy_dist = tmp_path / "dist"
    (legacy_dist / "web").mkdir(parents=True)
    assert legacy_browser_dist(tmp_path, "") == legacy_dist
    assert legacy_browser_dist(tmp_path, "test") is None
    assert legacy_browser_dist(tmp_path, "production") is None
    assert "legacy_browser_dist(Path(__file__).parent.parent" in MAIN_FILE.read_text(encoding="utf-8")


def test_managed_backend_rejects_production_cors_before_plugin_registration(tmp_path):
    env_file = tmp_path / "runtime.env"
    env_file.write_text("AI00_DEPLOY_PROFILE=production\nTABLE_PREFIX=pp_\n"
                        "PUBLIC_URL=https://workmanship-backend.chehejia.com\n"
                        "CORS_ALLOW_ORIGINS=*\nJWT_SECRET=private-fixture\n", encoding="utf-8")
    environment = os.environ.copy()
    environment["ENV_FILE"] = str(env_file)
    result = subprocess.run([sys.executable, "-B", "-c", "from backend.main import app"],
                            cwd=MAIN_FILE.parents[1], env=environment,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert "managed_runtime_preflight_failed" in result.stderr
    assert "production CORS origins" in result.stderr
    assert "private-fixture" not in result.stderr


def test_test_profile_requires_managed_env_file_before_plugin_registration():
    environment = os.environ.copy()
    environment.pop("ENV_FILE", None)
    environment.update({"AI00_DEPLOY_PROFILE": "test", "TABLE_PREFIX": "test_",
                        "PUBLIC_URL": "http://127.0.0.1:8080"})
    result = subprocess.run([sys.executable, "-B", "-c", "from backend.main import app"],
                            cwd=MAIN_FILE.parents[1], env=environment,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert "managed_deployment_requires_env_file" in result.stderr
