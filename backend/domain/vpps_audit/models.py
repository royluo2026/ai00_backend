"""
backend/domain/vpps_audit/models.py
────────────────────────────────────
VppsOperation 纯 Python 数据类（Domain 层，无任何外部依赖）
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class VppsOperation:
    gid: str
    pbom_version_gid: str
    pbom_row_gid: str
    operation_type: str          # rule4_bulk_ignore | rule1_alias | rule1_suggestion | rule2_suggestion | manual_note
    rule_no: Optional[int]
    field_name: Optional[str]    # 'vpps' | 'vpps_desc' | 'parent_vpps'
    original_value: Optional[str]
    new_value: Optional[str]     # 忽略类操作为 None
    actor_gid: str
    actor_name: Optional[str]
    created_at: datetime
    notes: Optional[str] = None
    is_active: bool = True
    reverted_at: Optional[datetime] = None
    reverted_by_gid: Optional[str] = None
    reverted_by_name: Optional[str] = None
