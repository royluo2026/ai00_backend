from __future__ import annotations

import json
from dataclasses import replace

from backend.scripts.run_bop_large_version_acceptance import (
    AcceptanceMeasurements,
    evaluate_measurements,
    sanitize_report,
)
from backend.tests.fixtures.bop_large_version_factory import build_large_bop_fixture


class _Ids:
    def __init__(self):
        self.value = 10_000_000_000_000_000

    def __call__(self):
        self.value += 1
        return self.value


def test_fixture_counts_snowflake_gids_and_cleanup_order_are_exact():
    fixture = build_large_bop_fixture(10_000, run_id="run-1", gid_factory=_Ids())
    assert len(fixture.entry_rows) == 10_000
    all_gids = [fixture.root_gid, fixture.version_gid, *fixture.identity_gids]
    all_gids += [row["gid"] for row in fixture.entry_rows]
    all_gids += [row["gid"] for row in fixture.link_rows]
    assert len(all_gids) == len(set(all_gids))
    assert all(value.isdigit() and int(value) > 0 for value in all_gids)
    assert [name for name, _ids in fixture.cleanup_batches] == [
        "links", "entries", "versions", "bop_roots", "identities",
    ]
    assert fixture.cleanup_batches[1][1][0] == fixture.entry_rows[-1]["gid"]


def test_acceptance_pass_fail_calculation_covers_memory_and_contract_limits():
    good = AcceptanceMeasurements(
        full_entries_requests=0,
        observed_page_sizes=(100, 200, 200),
        page_size_limits=(100, 200, 200),
        http_504_count=0,
        worker_restarts=0,
        peak_cgroup_ratio=0.70,
        refresh_peak_bytes=(100, 101, 99, 100, 100, 101, 100, 99, 100, 100),
        non_craft_error_rate_before=0.0,
        non_craft_error_rate_during=0.0,
        cleanup_residue=0,
    )
    assert evaluate_measurements(good).passed is True
    bad = replace(good, full_entries_requests=1, peak_cgroup_ratio=0.80, cleanup_residue=2)
    result = evaluate_measurements(bad)
    assert result.passed is False
    assert {"legacy_full_entries_used", "memory_ceiling_exceeded", "cleanup_residue"} <= set(result.failures)


def test_report_redaction_is_allowlist_based():
    report = sanitize_report({
        "status": "passed",
        "sizes": [1000, 5000, 10000],
        "database_url": "mysql://user:secret@host/db",
        "jwt": "secret-token",
        "payload": {"entry_name": "sensitive"},
        "measurements": {"peak_cgroup_ratio": 0.7},
    })
    text = json.dumps(report).lower()
    assert report["status"] == "passed"
    assert report["sizes"] == [1000, 5000, 10000]
    for forbidden in ("mysql://", "secret", "jwt", "payload", "entry_name"):
        assert forbidden not in text
