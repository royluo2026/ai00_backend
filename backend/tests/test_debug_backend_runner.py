import os
from pathlib import Path

from scripts.run_debug_backend import prepare_environment


def test_prepare_environment_removes_all_proxy_variants(monkeypatch, tmp_path: Path) -> None:
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        monkeypatch.setenv(name, "http://127.0.0.1:9")

    prepare_environment(tmp_path)

    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        assert name not in os.environ
    assert os.environ["NO_PROXY"] == "127.0.0.1,localhost"
    assert os.environ["no_proxy"] == "127.0.0.1,localhost"
    assert os.environ["ENV_FILE"] == str(tmp_path / "backend" / ".env")
