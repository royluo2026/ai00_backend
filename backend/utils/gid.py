"""
backend/utils/gid.py
────────────────────
雪花算法 GID 生成器（backend 包内独立副本，不依赖 app/）

64位标准分配：
  符号位(1bit) | 时间戳(41bit) | 机器ID(10bit) | 序列号(12bit)

起始时间戳：2025-01-01 00:00:00 UTC
"""
import os
import time
import threading
from collections.abc import Mapping
from typing import Final


class SnowflakeGID:
    EPOCH: Final[int] = 1735689600000
    SEQUENCE_BITS: Final[int] = 12
    MACHINE_ID_BITS: Final[int] = 10
    MAX_MACHINE_ID: Final[int] = -1 ^ (-1 << MACHINE_ID_BITS)
    MAX_SEQUENCE: Final[int] = -1 ^ (-1 << SEQUENCE_BITS)
    MACHINE_ID_SHIFT: Final[int] = SEQUENCE_BITS
    TIMESTAMP_SHIFT: Final[int] = SEQUENCE_BITS + MACHINE_ID_BITS

    def __init__(self, machine_id: int = 1):
        if machine_id < 0 or machine_id > self.MAX_MACHINE_ID:
            raise ValueError(f"机器ID必须在 0 ~ {self.MAX_MACHINE_ID} 之间")
        self.machine_id: int = machine_id
        self.last_timestamp: int = -1
        self.sequence: int = 0
        self._thread_lock: threading.Lock = threading.Lock()

    def _get_current_timestamp(self) -> int:
        return int(time.time() * 1000)

    def _wait_next_millis(self, last_timestamp: int) -> int:
        timestamp = self._get_current_timestamp()
        while timestamp <= last_timestamp:
            timestamp = self._get_current_timestamp()
        return timestamp

    def next_id(self) -> int:
        with self._thread_lock:
            timestamp = self._get_current_timestamp()
            if timestamp < self.last_timestamp:
                raise RuntimeError("系统时间回拨，无法生成GID")
            if timestamp == self.last_timestamp:
                self.sequence = (self.sequence + 1) & self.MAX_SEQUENCE
                if self.sequence == 0:
                    timestamp = self._wait_next_millis(self.last_timestamp)
            else:
                self.sequence = 0
            self.last_timestamp = timestamp
            new_id = (
                ((timestamp - self.EPOCH) << self.TIMESTAMP_SHIFT)
                | (self.machine_id << self.MACHINE_ID_SHIFT)
                | self.sequence
            )
            return new_id


def machine_id_from_environment(environ: Mapping[str, str]) -> int:
    profile = str(environ.get("AI00_DEPLOYMENT_PROFILE", "local")).strip()
    raw = str(environ.get("AI00_GID_MACHINE_ID", "")).strip()
    if not raw and profile in {"test-governance", "production"}:
        raise RuntimeError("AI00_GID_MACHINE_ID is required")
    try:
        machine_id = int(raw or "1")
    except ValueError as exc:
        raise RuntimeError("AI00_GID_MACHINE_ID must be in 0..1023") from exc
    if not 0 <= machine_id <= SnowflakeGID.MAX_MACHINE_ID:
        raise RuntimeError("AI00_GID_MACHINE_ID must be in 0..1023")
    return machine_id


def gid_to_json(value: int) -> str:
    if not 0 < value < 2**63:
        raise ValueError("gid_out_of_signed_bigint_range")
    return str(value)


def configure_gid_generator(machine_id: int) -> SnowflakeGID:
    """Configure the module default without sharing ordinary generator instances."""
    global gid_generator
    gid_generator = SnowflakeGID(machine_id=machine_id)
    return gid_generator


def next_gid() -> int:
    """Return an ID from the process-level configured generator."""
    return gid_generator.next_id()


gid_generator: SnowflakeGID = SnowflakeGID(
    machine_id=machine_id_from_environment(os.environ)
)

__all__ = [
    "SnowflakeGID",
    "configure_gid_generator",
    "gid_generator",
    "gid_to_json",
    "machine_id_from_environment",
    "next_gid",
]
