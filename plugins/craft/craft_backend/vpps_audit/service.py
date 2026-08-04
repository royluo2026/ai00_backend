from datetime import datetime, timezone
from typing import Optional

from backend.platform_sdk.ids import next_gid

from .models import VppsOperation
from .repository import VppsOperationRepository


class VppsAuditService:
    def __init__(self, repo: VppsOperationRepository) -> None:
        self._repo = repo

    def bulk_ignore_rule4(
        self, pbom_version_gid: str, rows: list[dict], actor_gid: str,
        actor_name: Optional[str] = None,
    ) -> list[VppsOperation]:
        existing = self._repo.get_active_rule4_ignores(pbom_version_gid)
        now = datetime.now(tz=timezone.utc)
        operations: list[VppsOperation] = []
        for row in rows:
            row_gid = str(row.get("pbom_row_gid") or "").strip()
            if not row_gid or row_gid in existing:
                continue
            operations.append(VppsOperation(
                gid=str(next_gid()), pbom_version_gid=pbom_version_gid,
                pbom_row_gid=row_gid, operation_type="rule4_bulk_ignore",
                rule_no=4, field_name="vpps_desc",
                original_value=row.get("original_vpps_desc"), new_value=None,
                actor_gid=actor_gid, actor_name=actor_name, created_at=now,
                notes=row.get("notes"), is_active=True,
            ))
        if operations:
            self._repo.save_batch(operations)
        return operations

    def revert_operation(
        self, op_gid: str, reverted_by_gid: str,
        reverted_by_name: Optional[str] = None,
    ) -> Optional[VppsOperation]:
        return self._repo.revert(op_gid, reverted_by_gid, reverted_by_name or "")

    def get_active_rule4_ignores(self, pbom_version_gid: str) -> set[str]:
        return self._repo.get_active_rule4_ignores(pbom_version_gid)

    def get_active_operations(
        self, pbom_version_gid: str, operation_type: Optional[str] = None,
    ) -> list[VppsOperation]:
        return self._repo.get_active_by_version(pbom_version_gid, operation_type)
