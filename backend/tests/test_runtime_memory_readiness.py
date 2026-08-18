from __future__ import annotations

from dataclasses import asdict
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.capability_v2.metrics import CapabilityMetricRecord
from backend.capability_v2.resource_budget import MemorySnapshot
from backend.routers import health


class _Sampler:
    def __init__(self, ratio: float | None):
        self.ratio = ratio

    def snapshot(self):
        level = "not_ready" if self.ratio is not None and self.ratio >= 0.90 else "reject_large"
        return MemorySnapshot(
            rss_bytes=123,
            cgroup_current_bytes=None if self.ratio is None else int(self.ratio * 1000),
            cgroup_limit_bytes=None if self.ratio is None else 1000,
            ratio=self.ratio,
            level=level,
        )


@pytest.mark.parametrize(("ratio", "expected"), [(0.8999, True), (0.90, False), (None, True)])
def test_memory_readiness_changes_only_at_ninety_percent(ratio, expected):
    result = health.memory_readiness(_Sampler(ratio))
    assert result.ready is expected
    assert result.snapshot.ratio == ratio


def test_runtime_diagnostics_requires_super_admin():
    from backend.routers.runtime_diagnostics import require_runtime_admin

    with pytest.raises(HTTPException) as denied:
        require_runtime_admin({"system_role": "engineer", "org_role": "member"})
    assert denied.value.status_code == 403
    assert require_runtime_admin({"system_role": "super_admin"})["system_role"] == "super_admin"


def test_runtime_diagnostics_is_aggregate_and_payload_free(monkeypatch):
    from backend.routers import runtime_diagnostics

    metric = CapabilityMetricRecord(
        capability_id="craft.bop.work_package.get",
        major_version=2,
        owner_domain="craft",
        consumer_type="web",
        consumer_key_hash="sha256:abc",
        elapsed_ms=12.5,
        output_bytes=2048,
        rss_before_bytes=100,
        rss_after_bytes=120,
        cgroup_ratio=0.5,
        in_flight=1,
        cancelled=False,
        error_code=None,
    )
    gateway = SimpleNamespace(recent_metrics=lambda: (metric,))
    monkeypatch.setattr(runtime_diagnostics, "get_default_gateway", lambda: gateway)
    monkeypatch.setattr(runtime_diagnostics, "MemoryPressureSampler", lambda: _Sampler(0.5))
    monkeypatch.setenv("AI00_WEB_WORKERS", "1")

    payload = runtime_diagnostics.runtime_diagnostics({"system_role": "super_admin"})
    text = str(payload).lower()
    assert payload["worker_count"] == 1
    assert payload["memory"]["level"] == "reject_large"
    assert payload["capabilities"][0]["capability_id"] == "craft.bop.work_package.get"
    for forbidden in ("payload", "password", "database_url", "jwt", "entry_name"):
        assert forbidden not in text
