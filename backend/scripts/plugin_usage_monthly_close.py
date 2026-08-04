#!/usr/bin/env python3
"""Idempotently close the previous plugin-usage month for every active tenant."""
from __future__ import annotations

import argparse
import json
from datetime import date

from backend.plugin_platform.metrics import close_previous_month_all_tenants


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--today", help="Acceptance-only date override in YYYY-MM-DD format.")
    args = parser.parse_args()
    today = date.fromisoformat(args.today) if args.today else None
    result = close_previous_month_all_tenants(today=today)
    print(json.dumps({"ok": True, **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())