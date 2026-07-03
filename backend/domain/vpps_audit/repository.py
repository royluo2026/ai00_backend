"""
backend/domain/vpps_audit/repository.py
────────────────────────────────────────
IVppsOperationRepository — 抽象接口（Domain 层）
"""
from abc import ABC, abstractmethod
from typing import Optional

from backend.domain.vpps_audit.models import VppsOperation


class IVppsOperationRepository(ABC):

    @abstractmethod
    def save(self, op: VppsOperation) -> None:
        """保存单条操作记录。"""
        ...

    @abstractmethod
    def save_batch(self, ops: list[VppsOperation]) -> None:
        """单事务批量保存操作记录。"""
        ...

    @abstractmethod
    def get_active_by_version(
        self,
        pbom_version_gid: str,
        operation_type: Optional[str] = None,
    ) -> list[VppsOperation]:
        """返回指定 PBOM 版本的 is_active=TRUE 操作记录（可按 operation_type 过滤）。"""
        ...

    @abstractmethod
    def revert(
        self,
        gid: str,
        reverted_by_gid: str,
        reverted_by_name: str,
    ) -> Optional[VppsOperation]:
        """将指定 gid 的操作标记为已撤销（is_active=FALSE）；返回更新后的对象，不存在则 None。"""
        ...

    @abstractmethod
    def get_active_rule4_ignores(self, pbom_version_gid: str) -> set[str]:
        """返回该 PBOM 版本中所有 is_active=TRUE 的 rule4_bulk_ignore pbom_row_gid 集合。"""
        ...
