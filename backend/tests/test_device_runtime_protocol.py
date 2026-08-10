"""HTTP adapter and migration checks for Local Operation V2."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.domain_ports.local_integration import LocalOperationOutcome, sign_operation_outcome
from backend.routers.device_runtime import CompleteBody
from backend.routers import device_runtime
from plugins.device.device_backend import control_plane


def test_completion_http_body_requires_signed_closed_outcome():
    outcome = LocalOperationOutcome(
        protocol="ai00.local-operation.v2", operation_id="operation-1", status="failed",
        error_code="local_execution_failed", reported_at=datetime.now(timezone.utc),
    )
    body = CompleteBody(
        lease_id="lease-1", outcome=outcome,
        signature=sign_operation_outcome(outcome, "device-token-at-least-thirty-two-bytes-long"),
    )
    assert body.outcome.status == "failed"
    with pytest.raises(ValidationError):
        CompleteBody.model_validate({**body.model_dump(), "success": True})


def test_protocol_migration_does_not_mix_non_resumable_data_backfill():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    migration = (root / "backend/db/migrations/202608100011_device_operation_protocol_v2.sql").read_text(encoding="utf-8")
    assert "UPDATE workmanship_runtime_commands" not in migration
    assert "ADD COLUMN IF NOT EXISTS protocol_version" in migration
    assert "succeeded" in migration
    assert "lease_retry_limit_reached" in migration


def test_get_command_projects_legacy_terminal_values(monkeypatch):
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, *_args): return None
        def fetchone(self):
            return {
                "gid": "operation-1", "status": "succeeded",
                "error": "lease retry limit reached", "result": "{}",
            }

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()

    monkeypatch.setattr(control_plane, "get_device_conn", lambda: Connection())
    result = control_plane.get_command("operation-1", "user-1")

    assert result["status"] == "completed"
    assert result["error"] == "lease_retry_limit_reached"


def test_pending_device_outcome_is_reconciled_idempotently(monkeypatch):
    calls = []

    class Reconciler:
        def reconcile(self, operation_id, target, error_code=None):
            calls.append(("operation", operation_id, target.value, error_code))

    monkeypatch.setattr(device_runtime, "pending_reconciliations", lambda device_id: [
        {"gid": "operation-1", "status": "pending_outcome_unknown", "error": "session_host_unavailable"}
    ])
    monkeypatch.setattr(device_runtime, "_operation_reconciler", lambda: Reconciler())
    monkeypatch.setattr(device_runtime, "mark_command_reconciled", lambda device_id, operation_id, status: calls.append(("command", device_id, operation_id, status)))
    device_runtime._reconcile_pending("device-1")
    assert calls == [
        ("operation", "operation-1", "outcome_unknown", "session_host_unavailable"),
        ("command", "device-1", "operation-1", "pending_outcome_unknown"),
    ]


def test_device_completion_is_persisted_as_pending_before_base_reconciliation(monkeypatch):
    statements = []

    class Cursor:
        rowcount = 1
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, statement, params): statements.append((statement, params))
        def fetchone(self): return None

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def cursor(self): return Cursor()
        def commit(self): statements.append(("COMMIT", ()))

    monkeypatch.setattr(control_plane, "get_device_conn", lambda: Connection())
    control_plane.complete_command(
        "device-1", "operation-1", "lease-1", "completed",
        result={"opened": True},
    )
    assert statements[0][1][0] == "pending_completed"
    assert statements[-1][0] == "COMMIT"
