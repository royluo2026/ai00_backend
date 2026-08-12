#!/usr/bin/env python3
"""Fail before restart when a deployment cannot serve its critical routes."""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values


REQUIRED_MODULES = ("cryptography", "dbutils", "pymysql", "multipart")
REQUIRED_DB_URLS = (
    "USERS_DB_URL",
    "AI00_CRAFT_DB_URL",
    "AI00_AGENT_DB_URL",
    "AI00_SIMULATION_DB_URL",
    "AI00_LOCAL_RUNTIME_DB_URL",
    "AI00_PROJECT_MANAGEMENT_DB_URL",
    "AI00_KNOWLEDGE_DB_URL",
)


def _valid_mysql_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"mysql", "mysql+pymysql"} and bool(
        parsed.hostname and parsed.username and parsed.path.strip("/")
    )


def evaluate(env_file: Path) -> list[str]:
    errors: list[str] = []
    if not env_file.is_file():
        return [f"runtime env file does not exist: {env_file}"]
    values = {key: str(value or "").strip() for key, value in dotenv_values(env_file).items()}
    for name in REQUIRED_MODULES:
        if importlib.util.find_spec(name) is None:
            errors.append(f"required Python module is not installed: {name}")
    for name in REQUIRED_DB_URLS:
        if not _valid_mysql_url(values.get(name, "")):
            errors.append(f"{name} is missing or is not an explicit mysql URL")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args()
    errors = evaluate(args.env_file)
    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        return 2
    print("Runtime preflight passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
