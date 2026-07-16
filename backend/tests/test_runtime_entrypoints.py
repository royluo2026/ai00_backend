from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_start_backend_uses_env_file_host_and_port():
    text = (REPO_ROOT / 'scripts' / 'start_backend.sh').read_text(encoding='utf-8')
    assert 'while IFS= read -r raw || [[ -n "$raw" ]]; do' in text
    assert "line=\"${raw%$'\\r'}\"" in text
    assert 'export "${key}=${value}"' in text
    assert '--host "$HOST" --port "$PORT"' in text
    assert 'PROBE_HOST="$HOST"' in text
    assert 'if [[ "$HOST" == "0.0.0.0" || "$HOST" == "::" ]]; then' in text
    assert 'http://${PROBE_HOST}:${PORT}/health' in text
    assert 'VENV_PY="$ROOT_DIR/.venv/Scripts/python.exe"' in text
    assert 'elif [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then' in text


def test_dockerfile_requires_runtime_env_file_in_container():
    text = (REPO_ROOT / 'backend' / 'Dockerfile').read_text(encoding='utf-8')
    assert 'ENV ENV_FILE=' not in text
    assert 'SERVICE_PORT' not in text
    assert "assert env_file, 'ENV_FILE is required for container runtime'" in text
    assert 'load_dotenv(env_file, override=True)' in text
    assert "uvicorn.run('backend.main:app'" in text


def test_prepare_test_runtime_env_generates_placeholder_runtime_env():
    text = (REPO_ROOT / 'scripts' / 'prepare_test_runtime_env.sh').read_text(encoding='utf-8')
    assert 'TARGET_ENV="$ROOT_DIR/backend/.env.test.runtime"' in text
    assert 'if [[ -f "$TARGET_ENV" ]]; then' in text
    assert 'FEISHU_REDIRECT_URI=https://workmanship-backend-test.chehejia.com/auth/feishu/callback' in text
    assert 'PUBLIC_URL=https://workmanship-backend-test.chehejia.com' in text
    assert 'CORS_ALLOW_ORIGINS=https://workmanship-web-test.chehejia.com,http://127.0.0.1:5173,http://localhost:5173,app://root,null' in text
    assert 'OIS_IDAAS_CLIENT_SECRET=' in text
    assert 'sed -i "s|^JWT_SECRET=.*|JWT_SECRET=你的真实密钥|" "$TARGET_ENV"' in text
    assert 'ENV_FILE=$TARGET_ENV gunicorn backend.main:app -c backend/gunicorn.conf.py' in text


def test_patch_test_runtime_env_supports_flag_based_secret_updates():
    text = (REPO_ROOT / 'scripts' / 'patch_test_runtime_env.sh').read_text(encoding='utf-8')
    assert 'TARGET_ENV="$ROOT_DIR/backend/.env.test.runtime"' in text
    assert 'if [[ ! -f "$TARGET_ENV" ]]; then' in text
    assert '--jwt-secret VALUE' in text
    assert '--users-db-url VALUE' in text
    assert '--ois-idaas-client-secret VALUE' in text
    assert 'sed -i "s|^${key}=.*|${key}=${escaped}|" "$TARGET_ENV"' in text
    assert 'patch_key JWT_SECRET "$2"' in text
    assert 'patch_key USERS_DB_URL "$2"' in text
    assert 'patch_key OIS_IDAAS_CLIENT_SECRET "$2"' in text
    assert '已更新运行时配置文件' in text


def test_bootstrap_skips_unusable_python_shims_and_checks_python():
    text = (REPO_ROOT / 'scripts' / 'bootstrap.sh').read_text(encoding='utf-8')
    assert 'for candidate in python3.12 python3.11 python3.10 python3 python; do' in text
    assert 'if VER="$($candidate -c' not in text
    assert 'if VER="$("$candidate" -c ' in text
    assert '2>/dev/null' in text
    assert 'VENV_PY="$VENV_DIR/Scripts/python.exe"' in text
    assert 'elif [[ -x "$VENV_DIR/bin/python" ]]; then' in text
    assert 'source "$VENV_DIR/bin/activate"' not in text
    assert '"$VENV_PY" -m pip install --upgrade pip >/dev/null' in text
    assert '"$VENV_PY" -m pip install -r backend/requirements.txt' in text
