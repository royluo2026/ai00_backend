"""Run the AI00 knowledge publication outbox worker.

Usage:
    python -m backend.scripts.capability_outbox_worker --interval 30 --batch-size 20
"""
from __future__ import annotations

import argparse
import asyncio
import logging

from backend.capabilities.outbox_worker_next import run_forever


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=20)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever(args.interval, args.batch_size))


if __name__ == "__main__":
    main()
