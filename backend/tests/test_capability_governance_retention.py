from datetime import datetime, timedelta, timezone

from backend.capability_governance_test.retention import RetentionRecord, plan_retention


NOW = datetime(2026, 8, 18, tzinfo=timezone.utc)


def test_retention_plan_selects_only_expired_technical_detail():
    records = (
        RetentionRecord("snapshot_detail", "snap-old", NOW - timedelta(days=181), release_referenced=False),
        RetentionRecord("snapshot_detail", "snap-release", NOW - timedelta(days=400), release_referenced=True),
        RetentionRecord("test_result_detail", "test-old", NOW - timedelta(days=181)),
        RetentionRecord("health_rollup", "health-old", NOW - timedelta(days=366)),
        RetentionRecord("ai_summary", "ai-expired", NOW - timedelta(days=1), expires_at=NOW - timedelta(seconds=1)),
        RetentionRecord("proposal", "proposal-old", NOW - timedelta(days=999)),
        RetentionRecord("review", "review-old", NOW - timedelta(days=999)),
        RetentionRecord("waiver", "waiver-old", NOW - timedelta(days=999)),
        RetentionRecord("release_report", "report-old", NOW - timedelta(days=999)),
        RetentionRecord("audit_event", "audit-old", NOW - timedelta(days=999)),
        RetentionRecord("entry", "entry-old", NOW - timedelta(days=999)),
        RetentionRecord("version", "version-old", NOW - timedelta(days=999)),
        RetentionRecord("finding_history", "finding-old", NOW - timedelta(days=999)),
    )

    plan = plan_retention(records, now=NOW)

    assert {record.record_gid for record in plan.records} == {"snap-old", "test-old", "health-old", "ai-expired"}
    assert not hasattr(plan, "cleanup")
