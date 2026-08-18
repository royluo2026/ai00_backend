"""Selection-only retention planning for expirable governance technical detail."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable


@dataclass(frozen=True)
class RetentionRecord:
    record_type: str
    record_gid: str | int
    created_at: datetime
    release_referenced: bool = False
    expires_at: datetime | None = None


@dataclass(frozen=True)
class RetentionPlan:
    records: tuple[RetentionRecord, ...]


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def plan_retention(records: Iterable[RetentionRecord], *, now: datetime) -> RetentionPlan:
    """Choose only permitted old detail; this module intentionally performs no cleanup."""
    moment = _utc(now)
    selected: list[RetentionRecord] = []
    for record in records:
        created = _utc(record.created_at)
        if record.record_type == "snapshot_detail" and not record.release_referenced and created < moment - timedelta(days=180):
            selected.append(record)
        elif record.record_type == "test_result_detail" and created < moment - timedelta(days=180):
            selected.append(record)
        elif record.record_type == "health_rollup" and created < moment - timedelta(days=365):
            selected.append(record)
        elif record.record_type == "ai_summary" and record.expires_at is not None and _utc(record.expires_at) <= moment:
            selected.append(record)
    return RetentionPlan(tuple(selected))


__all__ = ["RetentionPlan", "RetentionRecord", "plan_retention"]
