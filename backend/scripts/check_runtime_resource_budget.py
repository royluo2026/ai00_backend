"""Validate and print only sanitized runtime pool-budget aggregates."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.capability_v2.domain_resource_config import validate_aggregate_pool_budget


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    parser.parse_args()
    try:
        result = validate_aggregate_pool_budget()
    except ValueError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({
        "status": "passed",
        "workers": result.workers,
        "per_worker_max_connections": result.per_worker_max_connections,
        "total_max_connections": result.total_max_connections,
        "deployment_ceiling": result.deployment_ceiling,
        "domains": [
            {"domain": item.domain, "minimum": item.minimum, "maximum": item.maximum}
            for item in result.domains
        ],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
