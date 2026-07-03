"""
backend/utils/gid.py
────────────────────
雪花算法 GID 生成器（backend 包内独立副本，不依赖 app/）

64位标准分配：
  符号位(1bit) | 时间戳(41bit) | 机器ID(10bit) | 序列号(12bit)

起始时间戳：2025-01-01 00:00:00 UTC
"""
import time
import threading
from typing import Final


class SnowflakeGID:
    _instance: "SnowflakeGID" = None
    _lock: threading.Lock = threading.Lock()

    EPOCH: Final[int] = 1735689600000
    SEQUENCE_BITS: Final[int] = 12
    MACHINE_ID_BITS: Final[int] = 10
    MAX_MACHINE_ID: Final[int] = -1 ^ (-1 << MACHINE_ID_BITS)
    MAX_SEQUENCE: Final[int] = -1 ^ (-1 << SEQUENCE_BITS)
    MACHINE_ID_SHIFT: Final[int] = SEQUENCE_BITS
    TIMESTAMP_SHIFT: Final[int] = SEQUENCE_BITS + MACHINE_ID_BITS

    def __new__(cls, machine_id: int = 1) -> "SnowflakeGID":
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, machine_id: int = 1):
        if hasattr(self, '_initialized'):
            return
        if machine_id < 0 or machine_id > self.MAX_MACHINE_ID:
            raise ValueError(f"机器ID必须在 0 ~ {self.MAX_MACHINE_ID} 之间")
        self.machine_id: int = machine_id
        self.last_timestamp: int = -1
        self.sequence: int = 0
        self._thread_lock: threading.Lock = threading.Lock()
        self._initialized: bool = True

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


gid_generator: SnowflakeGID = SnowflakeGID(machine_id=1)
next_gid = gid_generator.next_id

__all__ = ["next_gid", "gid_generator", "SnowflakeGID"]
