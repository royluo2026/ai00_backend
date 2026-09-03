"""Recoverable worker for projecting Connector outcomes through the Gateway."""
from __future__ import annotations

import argparse
import asyncio
import os
import socket
import uuid

from backend.capability_v2.gateway import get_default_gateway
from backend.domain_ports.simulation_runtime import GovernedSimulationRuntimeClient
from plugins.simulation.simulation_backend.data.connector_repository import (
    SimulationConnectorRepository,
)


class ConnectorProjectionWorker:
    def __init__(self, repository, projector, *, owner: str, lease_seconds: int = 60):
        self.repository = repository
        self.projector = projector
        self.owner = owner
        self.lease_seconds = lease_seconds

    async def run_once(self) -> bool:
        self.repository.reclaim_stale_projections()
        lease = self.repository.claim_projection(self.owner, self.lease_seconds)
        if lease is None:
            return False
        try:
            plan, outcome = self.repository.read_projection_payload(lease)
            target = self.projector.target(plan)
            if target != lease.target_capability:
                raise RuntimeError("projection_target_mismatch")
            await self.projector.apply(plan, outcome, attempt=lease.attempt)
        except Exception as exc:
            self.repository.fail_projection(
                lease.plan_id, lease.owner,
                error_code=str(exc)[:128],
                retryable=bool(getattr(exc, "retryable", True)),
            )
        else:
            self.repository.finish_projection(lease.plan_id, lease.owner)
        return True


async def run_forever(worker: ConnectorProjectionWorker, *, idle_seconds: float = 1.0) -> None:
    while True:
        if not await worker.run_once():
            await asyncio.sleep(idle_seconds)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lease-seconds", type=int, default=60)
    parser.add_argument("--idle-seconds", type=float, default=1.0)
    args = parser.parse_args(argv)
    owner = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex}"
    worker = ConnectorProjectionWorker(
        SimulationConnectorRepository(),
        GovernedSimulationRuntimeClient(get_default_gateway()),
        owner=owner,
        lease_seconds=args.lease_seconds,
    )
    try:
        asyncio.run(run_forever(worker, idle_seconds=max(0.1, args.idle_seconds)))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["ConnectorProjectionWorker", "main", "run_forever"]
