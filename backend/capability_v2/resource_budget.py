"""Process-memory sampling and bounded Capability admission without worker threads."""
from __future__ import annotations

import asyncio
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from .contracts import ExecutionBudget, MemoryClass


PressureLevel = Literal["normal", "warning", "constrained", "reject_large", "not_ready"]


@dataclass(frozen=True, slots=True)
class MemorySnapshot:
    rss_bytes: int
    cgroup_current_bytes: int | None
    cgroup_limit_bytes: int | None
    ratio: float | None
    level: PressureLevel


class MemoryPressureSampler:
    _V2_CURRENT = "/sys/fs/cgroup/memory.current"
    _V2_LIMIT = "/sys/fs/cgroup/memory.max"
    _V1_CURRENT = "/sys/fs/cgroup/memory/memory.usage_in_bytes"
    _V1_LIMIT = "/sys/fs/cgroup/memory/memory.limit_in_bytes"

    def __init__(
        self,
        *,
        file_reader: Callable[[str], str] | None = None,
        rss_reader: Callable[[], int] | None = None,
    ) -> None:
        self._file_reader = file_reader or self._read_text
        self._rss_reader = rss_reader or _process_rss_bytes

    @staticmethod
    def _read_text(path: str) -> str:
        return Path(path).read_text(encoding="ascii")

    @staticmethod
    def level_for_ratio(ratio: float | None) -> PressureLevel:
        if ratio is None or ratio < 0.60:
            return "normal"
        if ratio < 0.75:
            return "warning"
        if ratio < 0.85:
            return "constrained"
        if ratio < 0.90:
            return "reject_large"
        return "not_ready"

    def snapshot(self) -> MemorySnapshot:
        current, limit = self._cgroup_values(self._V2_CURRENT, self._V2_LIMIT)
        if current is None:
            current, limit = self._cgroup_values(self._V1_CURRENT, self._V1_LIMIT)
        ratio = current / limit if current is not None and limit is not None else None
        return MemorySnapshot(
            rss_bytes=max(0, int(self._rss_reader())),
            cgroup_current_bytes=current,
            cgroup_limit_bytes=limit,
            ratio=ratio,
            level=self.level_for_ratio(ratio),
        )

    def _cgroup_values(self, current_path: str, limit_path: str) -> tuple[int | None, int | None]:
        try:
            current_raw = self._file_reader(current_path).strip()
            limit_raw = self._file_reader(limit_path).strip()
            current = int(current_raw)
        except (FileNotFoundError, OSError, TypeError, ValueError):
            return None, None
        if current < 0:
            return None, None
        if limit_raw == "max":
            return current, None
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            return current, None
        # cgroup v1 represents "unlimited" with a very large sentinel.
        if limit <= 0 or limit >= 1 << 60:
            return current, None
        return current, limit


class AdmissionRejected(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = True) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class AdmissionLease:
    def __init__(
        self,
        controller: "ResourceAdmissionController",
        capability_key: str,
        tenant_counter_key: tuple[str, str],
        consumer_counter_key: tuple[str, str],
    ) -> None:
        self._controller = controller
        self._capability_key = capability_key
        self._tenant_counter_key = tenant_counter_key
        self._consumer_counter_key = consumer_counter_key
        self._released = False

    async def __aenter__(self) -> "AdmissionLease":
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.release()

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        await self._controller._release(
            self._capability_key, self._tenant_counter_key, self._consumer_counter_key,
        )


class ResourceAdmissionController:
    def __init__(self, sampler: MemoryPressureSampler) -> None:
        self._sampler = sampler
        self._condition = asyncio.Condition()
        self._tenant_counts: defaultdict[tuple[str, str], int] = defaultdict(int)
        self._consumer_counts: defaultdict[tuple[str, str], int] = defaultdict(int)
        self._capability_counts: defaultdict[str, int] = defaultdict(int)

    def in_flight(self, capability_key: str) -> int:
        return self._capability_counts[capability_key]

    async def acquire(
        self,
        *,
        capability_key: str,
        tenant_key: str,
        consumer_key: str,
        budget: ExecutionBudget,
        timeout_seconds: float,
    ) -> AdmissionLease:
        snapshot = self._sampler.snapshot()
        if snapshot.level == "not_ready" or (
            snapshot.level == "reject_large" and budget.memory_class is MemoryClass.LARGE
        ):
            raise AdmissionRejected("resource_pressure")

        tenant_counter_key = (capability_key, tenant_key)
        consumer_counter_key = (capability_key, consumer_key)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(0.0, timeout_seconds)
        async with self._condition:
            while (
                self._tenant_counts[tenant_counter_key] >= budget.max_parallel_per_tenant
                or self._consumer_counts[consumer_counter_key] >= budget.max_parallel_per_consumer
            ):
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise AdmissionRejected("capacity_unavailable")
                try:
                    await asyncio.wait_for(self._condition.wait(), timeout=remaining)
                except TimeoutError as exc:
                    raise AdmissionRejected("capacity_unavailable") from exc
            self._tenant_counts[tenant_counter_key] += 1
            self._consumer_counts[consumer_counter_key] += 1
            self._capability_counts[capability_key] += 1
        return AdmissionLease(self, capability_key, tenant_counter_key, consumer_counter_key)

    async def _release(
        self,
        capability_key: str,
        tenant_counter_key: tuple[str, str],
        consumer_counter_key: tuple[str, str],
    ) -> None:
        async with self._condition:
            _decrement(self._tenant_counts, tenant_counter_key)
            _decrement(self._consumer_counts, consumer_counter_key)
            _decrement(self._capability_counts, capability_key)
            self._condition.notify_all()


def _decrement(counts: defaultdict, key: object) -> None:
    value = counts.get(key, 0)
    if value <= 1:
        counts.pop(key, None)
    else:
        counts[key] = value - 1


def _process_rss_bytes() -> int:
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return int(counters.WorkingSetSize)
        except (AttributeError, OSError):
            return 0
        return 0
    try:
        statm = Path("/proc/self/statm").read_text(encoding="ascii").split()
        return int(statm[1]) * int(os.sysconf("SC_PAGE_SIZE"))
    except (FileNotFoundError, OSError, IndexError, ValueError):
        return 0


__all__ = [
    "AdmissionLease", "AdmissionRejected", "MemoryPressureSampler", "MemorySnapshot",
    "ResourceAdmissionController",
]
