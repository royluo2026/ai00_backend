"""Start the local backend without inheriting workstation proxy settings."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


_PROXY_VARIABLES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


def prepare_environment(repo_root: Path) -> None:
    """Bind the process to this checkout and disable inherited outbound proxies."""
    for name in _PROXY_VARIABLES:
        os.environ.pop(name, None)

    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    os.environ["no_proxy"] = "127.0.0.1,localhost"
    os.environ["ENV_FILE"] = str(repo_root / "backend" / ".env")
    os.environ.setdefault(
        "AI00_INTEGRATION_ADAPTER_FACTORY",
        "integration_backend.infrastructure.production_adapters:build",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    prepare_environment(repo_root)
    sys.path.insert(0, str(repo_root))

    import uvicorn

    uvicorn.run("backend.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
