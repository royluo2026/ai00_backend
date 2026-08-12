from __future__ import annotations

import secrets
from collections.abc import Callable, Iterable

from ..domain.runs import SimulationRun


class SimulationRunService:
    def __init__(self, runs: Iterable[SimulationRun] = (), *, id_factory: Callable[[], str] | None = None):
        self._runs = {run.run_ref: run for run in runs}
        self._id_factory = id_factory or (lambda: secrets.token_hex(16))

    def replay(self, run_ref: str) -> SimulationRun:
        source = self._runs[run_ref]
        replay = SimulationRun(
            run_ref="simulation-run:" + self._id_factory(),
            operation_ref="operation:" + self._id_factory(),
            environment_ref=source.environment_ref,
            input_refs=source.input_refs,
        )
        self._runs[replay.run_ref] = replay
        return replay

