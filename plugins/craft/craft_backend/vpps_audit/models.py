from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class VppsOperation:
    gid: str
    pbom_version_gid: str
    pbom_row_gid: str
    operation_type: str
    rule_no: Optional[int]
    field_name: Optional[str]
    original_value: Optional[str]
    new_value: Optional[str]
    actor_gid: str
    actor_name: Optional[str]
    created_at: datetime
    notes: Optional[str] = None
    is_active: bool = True
    reverted_at: Optional[datetime] = None
    reverted_by_gid: Optional[str] = None
    reverted_by_name: Optional[str] = None
