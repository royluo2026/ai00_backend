from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_start_backend_uses_env_file_host_and_port():
    text = (REPO_ROOT / 'scripts' / 'start_backend.sh').read_text(encoding='utf-8')
    assert 'python - "$ENV_FILE" <<\'PY\'' in text
    assert '--host "$HOST" --port "$PORT"' in text
    assert 'PROBE_HOST="$HOST"' in text
    assert 'if [[ "$HOST" == "0.0.0.0" || "$HOST" == "::" ]]; then' in text
    assert 'http://${PROBE_HOST}:${PORT}/health' in text


def test_dockerfile_uses_tracked_runtime_env_file():
    text = (REPO_ROOT / 'backend' / 'Dockerfile').read_text(encoding='utf-8')
    assert 'ENV ENV_FILE=/chj/app/backend/.env.test.example' in text
    assert 'SERVICE_PORT' not in text
    assert 'load_dotenv(env_file, override=True)' in text
    assert "uvicorn.run('backend.main:app'" in text


def test_gunicorn_bind_reads_host_and_port_from_env_file():
    text = (REPO_ROOT / 'backend' / 'gunicorn.conf.py').read_text(encoding='utf-8')
    assert 'import os' in text
    assert 'from dotenv import load_dotenv' in text
    assert 'env_file = os.getenv("ENV_FILE", "").strip()' in text
    assert 'load_dotenv(env_file, override=False)' in text
    assert 'host = os.getenv("HOST", "0.0.0.0")' in text
    assert 'port = int(os.getenv("PORT", "8080") or "8080")' in text
    assert 'bind             = f"{host}:{port}"' in text
