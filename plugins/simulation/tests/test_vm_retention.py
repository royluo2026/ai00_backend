from datetime import UTC, datetime, timedelta

from plugins.simulation.simulation_backend.application.vm_retention import VmRetentionService


NOW = datetime(2026, 9, 10, tzinfo=UTC)


class Snapshots:
    def __init__(self, rows, protected=()): self.rows, self.protected, self.pruned = rows, set(protected), []
    def list_retention_candidates(self, **scope): return list(self.rows)
    def protected_snapshot_gids(self, **scope): return set(self.protected)
    def prune_snapshot_payload(self, snapshot_gid, **scope): self.pruned.append(snapshot_gid)


class Reports:
    def __init__(self): self.compacted = []
    def compact_automatic_reports_for_snapshot(self, snapshot_gid, **scope): self.compacted.append(snapshot_gid)


def row(gid, days, sequence): return {"snapshot_gid": str(gid), "captured_at": NOW - timedelta(days=days), "sequence": sequence}


def test_retention_keeps_twenty_recent_unreferenced_snapshots():
    snapshots = Snapshots([row(index, 1, index) for index in range(1, 23)])
    reports = Reports(); result = VmRetentionService(snapshots, reports, clock=lambda: NOW).run(document_gid="1", tenant_gid="2", owner_gid="3")
    assert snapshots.pruned == ["2", "1"]
    assert reports.compacted == ["2", "1"]
    assert result["pruned"] == 2


def test_retention_prunes_old_snapshot_even_within_count_limit():
    snapshots = Snapshots([row("1", 31, 1), row("2", 2, 2)])
    VmRetentionService(snapshots, Reports(), clock=lambda: NOW).run(document_gid="1", tenant_gid="2", owner_gid="3")
    assert snapshots.pruned == ["1"]


def test_governed_checkpoint_and_manual_report_references_are_never_pruned():
    snapshots = Snapshots([row("1", 90, 1), row("2", 90, 2)], protected=("1", "2"))
    result = VmRetentionService(snapshots, Reports(), clock=lambda: NOW).run(document_gid="1", tenant_gid="2", owner_gid="3")
    assert snapshots.pruned == [] and result["protected"] == 2


def test_cleanup_is_bounded_and_idempotent():
    snapshots = Snapshots([row(index, 90, index) for index in range(1, 250)])
    service = VmRetentionService(snapshots, Reports(), clock=lambda: NOW, batch_size=40)
    assert service.run(document_gid="1", tenant_gid="2", owner_gid="3")["pruned"] == 40
