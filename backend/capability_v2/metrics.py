"""Payload-free in-process measurements for governed Capability calls."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True, slots=True)
class CapabilityMetricRecord:
    capability_id: str
    major_version: int
    owner_domain: str
    consumer_type: str
    consumer_key_hash: str
    elapsed_ms: float
    output_bytes: int
    rss_before_bytes: int
    rss_after_bytes: int
    cgroup_ratio: float | None
    in_flight: int
    cancelled: bool
    error_code: str | None


class InMemoryCapabilityMetrics:
    def __init__(self, max_records: int = 256) -> None:
        self._records: deque[CapabilityMetricRecord] = deque(maxlen=max_records)
        self._lock = Lock()

    def record(self, value: CapabilityMetricRecord) -> None:
        with self._lock:
            self._records.append(value)

    def recent(self) -> tuple[CapabilityMetricRecord, ...]:
        with self._lock:
            return tuple(self._records)


__all__ = ["CapabilityMetricRecord", "InMemoryCapabilityMetrics"]
