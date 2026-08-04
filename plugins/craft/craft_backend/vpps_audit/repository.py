from abc import ABC, abstractmethod
from typing import Optional

from .models import VppsOperation


class VppsOperationRepository(ABC):
    @abstractmethod
    def save(self, op: VppsOperation) -> None: ...

    @abstractmethod
    def save_batch(self, ops: list[VppsOperation]) -> None: ...

    @abstractmethod
    def get_active_by_version(
        self, pbom_version_gid: str, operation_type: Optional[str] = None,
    ) -> list[VppsOperation]: ...

    @abstractmethod
    def revert(
        self, gid: str, reverted_by_gid: str, reverted_by_name: str,
    ) -> Optional[VppsOperation]: ...

    @abstractmethod
    def get_active_rule4_ignores(self, pbom_version_gid: str) -> set[str]: ...
