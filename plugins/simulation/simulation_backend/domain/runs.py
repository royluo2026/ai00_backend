from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SimulationRun:
    run_ref: str
    operation_ref: str
    environment_ref: str
    input_refs: tuple[str, ...]
    result_refs: tuple[str, ...] = ()
    status: str = "queued"

