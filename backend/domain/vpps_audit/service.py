"""
backend/domain/vpps_audit/service.py
──────────────────────────────────────
VppsAuditService — 业务逻辑层（只依赖 Domain 接口）
"""
from datetime import datetime, timezone
from typing import Optional

from backend.domain.vpps_audit.models import VppsOperation
from backend.domain.vpps_audit.repository import IVppsOperationRepository
from backend.utils.gid import next_gid


class VppsAuditService:

    def __init__(self, repo: IVppsOperationRepository) -> None:
        self._repo = repo

    # ── 一键忽略规则4 ──────────────────────────────────────────────────────────

    def bulk_ignore_rule4(
        self,
        pbom_version_gid: str,
        rows: list[dict],        # [{pbom_row_gid, original_vpps_desc?, notes?}, ...]
        actor_gid: str,
        actor_name: Optional[str] = None,
    ) -> list[VppsOperation]:
        """
        为每个 rule4 错误行创建一条 rule4_bulk_ignore 操作记录。
        rows 中已存在 is_active ignore 的行会被跳过（幂等）。
        """
        existing = self._repo.get_active_rule4_ignores(pbom_version_gid)
        now = datetime.now(tz=timezone.utc)
        ops: list[VppsOperation] = []
        for row in rows:
            row_gid = row.get("pbom_row_gid", "")
            if not row_gid or row_gid in existing:
                continue          # 已忽略，跳过
            ops.append(VppsOperation(
                gid=str(next_gid()),
                pbom_version_gid=pbom_version_gid,
                pbom_row_gid=row_gid,
                operation_type="rule4_bulk_ignore",
                rule_no=4,
                field_name="vpps_desc",
                original_value=row.get("original_vpps_desc"),
                new_value=None,
                actor_gid=actor_gid,
                actor_name=actor_name,
                created_at=now,
                notes=row.get("notes"),
                is_active=True,
            ))
        if ops:
            self._repo.save_batch(ops)
        return ops

    # ── 撤销操作 ────────────────────────────────────────────────────────────────

    def revert_operation(
        self,
        op_gid: str,
        reverted_by_gid: str,
        reverted_by_name: Optional[str] = None,
    ) -> Optional[VppsOperation]:
        """将指定操作标记为已撤销；返回更新后的 VppsOperation，不存在则 None。"""
        return self._repo.revert(op_gid, reverted_by_gid, reverted_by_name or "")

    # ── 查询 ────────────────────────────────────────────────────────────────────

    def get_active_rule4_ignores(self, pbom_version_gid: str) -> set[str]:
        """返回该版本已忽略的 pbom_row_gid 集合。"""
        return self._repo.get_active_rule4_ignores(pbom_version_gid)

    def get_active_operations(
        self,
        pbom_version_gid: str,
        operation_type: Optional[str] = None,
    ) -> list[VppsOperation]:
        return self._repo.get_active_by_version(pbom_version_gid, operation_type)
