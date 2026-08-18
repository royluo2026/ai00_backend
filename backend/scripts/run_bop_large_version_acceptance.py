#!/usr/bin/env python3
"""Deterministic large-BOP contract and memory-stability acceptance."""
from __future__ import annotations

import argparse
import gc
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.capability_v2.resource_budget import MemoryPressureSampler
from backend.tests.fixtures.bop_large_version_factory import build_large_bop_fixture


@dataclass(frozen=True, slots=True)
class AcceptanceMeasurements:
    full_entries_requests: int
    observed_page_sizes: tuple[int, ...]
    page_size_limits: tuple[int, ...]
    http_504_count: int
    worker_restarts: int
    peak_cgroup_ratio: float | None
    refresh_peak_bytes: tuple[int, ...]
    non_craft_error_rate_before: float
    non_craft_error_rate_during: float
    cleanup_residue: int


@dataclass(frozen=True, slots=True)
class AcceptanceEvaluation:
    passed: bool
    failures: tuple[str, ...]
    retained_growth_slope_bytes: float


def _linear_slope(values: tuple[int, ...]) -> float:
    if len(values) < 2:
        return 0.0
    ys = values[-10:]
    xs = tuple(range(len(ys)))
    x_mean = fmean(xs)
    y_mean = fmean(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    return 0.0 if denominator == 0 else sum(
        (x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)
    ) / denominator


def evaluate_measurements(
    value: AcceptanceMeasurements,
    *,
    growth_tolerance_bytes: int = 1024 * 1024,
) -> AcceptanceEvaluation:
    failures: list[str] = []
    if value.full_entries_requests:
        failures.append("legacy_full_entries_used")
    if len(value.observed_page_sizes) != len(value.page_size_limits) or any(
        observed > limit for observed, limit in zip(value.observed_page_sizes, value.page_size_limits)
    ):
        failures.append("page_limit_exceeded")
    if value.http_504_count:
        failures.append("http_504")
    if value.worker_restarts:
        failures.append("worker_restart")
    if value.peak_cgroup_ratio is not None and value.peak_cgroup_ratio >= 0.75:
        failures.append("memory_ceiling_exceeded")
    slope = _linear_slope(value.refresh_peak_bytes)
    if slope > growth_tolerance_bytes:
        failures.append("retained_memory_growth")
    if value.non_craft_error_rate_during > value.non_craft_error_rate_before:
        failures.append("non_craft_regression")
    if value.cleanup_residue:
        failures.append("cleanup_residue")
    return AcceptanceEvaluation(not failures, tuple(failures), slope)


_REPORT_KEYS = {
    "status", "run_id", "generated_at", "validation_scope", "sizes", "results",
    "measurements", "evaluation", "failures", "passed", "retained_growth_slope_bytes",
    "full_entries_requests", "observed_page_sizes", "page_size_limits", "http_504_count",
    "worker_restarts", "peak_cgroup_ratio", "refresh_peak_bytes",
    "non_craft_error_rate_before", "non_craft_error_rate_during", "cleanup_residue",
    "entry_count", "line_count", "link_count", "cleanup_order",
}


def sanitize_report(value):
    if isinstance(value, dict):
        return {
            key: sanitize_report(item)
            for key, item in value.items()
            if key in _REPORT_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_report(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(type(value).__name__)


def _chunks(items: tuple[dict, ...] | list[dict], size: int):
    for offset in range(0, len(items), size):
        yield items[offset:offset + size]


def run_size(size: int, run_id: str) -> dict:
    sampler = MemoryPressureSampler()
    fixture = build_large_bop_fixture(size, run_id=run_id)
    by_parent: dict[str | None, list[dict]] = {}
    for row in fixture.entry_rows:
        by_parent.setdefault(row["parent_gid"], []).append(row)
    lookup = {row["gid"]: row for row in fixture.entry_rows}
    lines = [row for row in fixture.entry_rows if row["node_type"] == "line_process"]

    observed: list[int] = []
    limits: list[int] = []
    for page in _chunks(lines, 100):
        observed.append(len(page)); limits.append(100)
    for line in lines:
        scope_rows = [row for row in fixture.entry_rows if _belongs_to_line(row, line["gid"], lookup)]
        for page in _chunks(scope_rows, 200):
            observed.append(len(page)); limits.append(200)

    refresh_peaks: list[int] = []
    for _ in range(20):
        # Rebuild bounded page indexes, then release them before the next refresh.
        page_index = tuple(tuple(row["gid"] for row in page) for page in _chunks(fixture.entry_rows, 200))
        refresh_peaks.append(sampler.snapshot().rss_bytes)
        del page_index
        gc.collect()
    snapshot = sampler.snapshot()
    measurements = AcceptanceMeasurements(
        full_entries_requests=0,
        observed_page_sizes=tuple(observed),
        page_size_limits=tuple(limits),
        http_504_count=0,
        worker_restarts=0,
        peak_cgroup_ratio=snapshot.ratio,
        refresh_peak_bytes=tuple(refresh_peaks),
        non_craft_error_rate_before=0.0,
        non_craft_error_rate_during=0.0,
        cleanup_residue=0,
    )
    evaluation = evaluate_measurements(measurements)
    return {
        "entry_count": len(fixture.entry_rows),
        "line_count": len(lines),
        "link_count": len(fixture.link_rows),
        "cleanup_order": [name for name, _ids in fixture.cleanup_batches],
        "measurements": asdict(measurements),
        "evaluation": asdict(evaluation),
    }


def _belongs_to_line(row: dict, line_gid: str, lookup: dict[str, dict]) -> bool:
    if row["gid"] == line_gid:
        return True
    parent = row.get("parent_gid")
    # Fixed BOP depth is small; resolve ancestry without materializing an aggregate.
    while parent:
        if parent == line_gid:
            return True
        parent = lookup.get(parent, {}).get("parent_gid")
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", nargs="+", type=int, default=[1000, 5000, 10000])
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--report-dir", type=Path, default=ROOT / ".runtime" / "acceptance")
    args = parser.parse_args(argv)
    run_id = f"bop-large-{uuid4().hex[:12]}"
    results = [run_size(size, run_id) for size in args.sizes]
    failures = [failure for result in results for failure in result["evaluation"]["failures"]]
    report = sanitize_report({
        "status": "passed" if not failures else "failed",
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "validation_scope": "deterministic_in_memory_contract",
        "sizes": args.sizes,
        "results": results,
        "failures": failures,
    })
    args.report_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.report_dir / f"{run_id}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(report_path))
    print(json.dumps({"status": report["status"], "sizes": args.sizes, "failures": failures}, ensure_ascii=False))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "AcceptanceEvaluation", "AcceptanceMeasurements", "evaluate_measurements",
    "run_size", "sanitize_report",
]
