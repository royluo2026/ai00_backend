from __future__ import annotations

import asyncio

import pytest

from backend.capability_v2.contracts import ExecutionBudget
from backend.capability_v2.resource_budget import (
    AdmissionLease,
    AdmissionRejected,
    MemoryPressureSampler,
    MemorySnapshot,
    ResourceAdmissionController,
)


def test_admission_release_can_retry_after_transient_cleanup_failure():
    class Controller:
        calls = 0
        async def _release(self, *_args):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("transient cleanup failure")

    async def scenario():
        controller = Controller()
        lease = AdmissionLease(controller, "agent.chat@2", ("t", "a"), ("c", "a"))
        with pytest.raises(RuntimeError, match="transient"):
            await lease.release()
        await lease.release()
        assert controller.calls == 2

    asyncio.run(scenario())


def _reader(values: dict[str, str]):
    def read(path: str) -> str:
        if path not in values:
            raise FileNotFoundError(path)
        return values[path]
    return read


@pytest.mark.parametrize(
    ("ratio", "level"),
    [
        (0.59, "normal"),
        (0.60, "warning"),
        (0.75, "constrained"),
        (0.85, "reject_large"),
        (0.90, "not_ready"),
    ],
)
def test_sampler_assigns_exact_memory_pressure_levels(ratio, level):
    limit = 1000
    sampler = MemoryPressureSampler(
        file_reader=_reader({
            "/sys/fs/cgroup/memory.current": str(int(limit * ratio)),
            "/sys/fs/cgroup/memory.max": str(limit),
        }),
        rss_reader=lambda: 123,
    )

    snapshot = sampler.snapshot()

    assert snapshot.ratio == pytest.approx(ratio)
    assert snapshot.level == level
    assert snapshot.rss_bytes == 123


def test_sampler_supports_cgroup_v1_and_unlimited_fallback():
    v1 = MemoryPressureSampler(
        file_reader=_reader({
            "/sys/fs/cgroup/memory/memory.usage_in_bytes": "400",
            "/sys/fs/cgroup/memory/memory.limit_in_bytes": "1000",
        }),
        rss_reader=lambda: 200,
    ).snapshot()
    unlimited = MemoryPressureSampler(
        file_reader=_reader({
            "/sys/fs/cgroup/memory.current": "800",
            "/sys/fs/cgroup/memory.max": "max",
        }),
        rss_reader=lambda: 321,
    ).snapshot()

    assert (v1.cgroup_current_bytes, v1.cgroup_limit_bytes, v1.ratio) == (400, 1000, 0.4)
    assert unlimited.rss_bytes == 321
    assert unlimited.cgroup_limit_bytes is None
    assert unlimited.ratio is None
    assert unlimited.level == "normal"


class _StaticSampler:
    def __init__(self, ratio: float | None = None):
        self.ratio = ratio

    def snapshot(self) -> MemorySnapshot:
        return MemorySnapshot(
            rss_bytes=100,
            cgroup_current_bytes=int(self.ratio * 1000) if self.ratio is not None else None,
            cgroup_limit_bytes=1000 if self.ratio is not None else None,
            ratio=self.ratio,
            level=MemoryPressureSampler.level_for_ratio(self.ratio),
        )


def test_admission_is_keyed_by_tenant_and_consumer_and_times_out_cleanly():
    async def scenario():
        controller = ResourceAdmissionController(_StaticSampler())
        budget = ExecutionBudget(max_parallel_per_consumer=1, max_parallel_per_tenant=1)
        first = await controller.acquire(
            capability_key="craft.large@1", tenant_key="t1", consumer_key="c1",
            budget=budget, timeout_seconds=0.05,
        )
        independent = await controller.acquire(
            capability_key="craft.large@1", tenant_key="t2", consumer_key="c2",
            budget=budget, timeout_seconds=0.05,
        )

        with pytest.raises(AdmissionRejected, match="capacity_unavailable") as tenant_error:
            await controller.acquire(
                capability_key="craft.large@1", tenant_key="t1", consumer_key="c2",
                budget=budget, timeout_seconds=0.01,
            )
        with pytest.raises(AdmissionRejected, match="capacity_unavailable"):
            await controller.acquire(
                capability_key="craft.large@1", tenant_key="t2", consumer_key="c1",
                budget=budget, timeout_seconds=0.01,
            )
        assert tenant_error.value.retryable is True

        await first.release()
        replacement = await controller.acquire(
            capability_key="craft.large@1", tenant_key="t1", consumer_key="c1",
            budget=budget, timeout_seconds=0.05,
        )
        await replacement.release()
        await independent.release()
        assert controller.in_flight("craft.large@1") == 0

    asyncio.run(scenario())


def test_cancelled_lease_releases_both_admission_counters_once():
    async def scenario():
        controller = ResourceAdmissionController(_StaticSampler())
        budget = ExecutionBudget(max_parallel_per_consumer=1, max_parallel_per_tenant=1)

        async def hold():
            lease = await controller.acquire(
                capability_key="craft.large@1", tenant_key="t1", consumer_key="c1",
                budget=budget, timeout_seconds=0.05,
            )
            async with lease:
                await asyncio.Event().wait()

        task = asyncio.create_task(hold())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert controller.in_flight("craft.large@1") == 0
        lease = await controller.acquire(
            capability_key="craft.large@1", tenant_key="t1", consumer_key="c1",
            budget=budget, timeout_seconds=0.05,
        )
        await lease.release()
        await lease.release()
        assert controller.in_flight("craft.large@1") == 0

    asyncio.run(scenario())


def test_large_capability_is_rejected_at_eighty_five_percent_memory():
    async def scenario():
        controller = ResourceAdmissionController(_StaticSampler(0.85))
        budget = ExecutionBudget(memory_class="large")

        with pytest.raises(AdmissionRejected, match="resource_pressure") as raised:
            await controller.acquire(
                capability_key="craft.large@1", tenant_key="t1", consumer_key="c1",
                budget=budget, timeout_seconds=0.05,
            )

        assert raised.value.retryable is True
        assert controller.in_flight("craft.large@1") == 0

    asyncio.run(scenario())
