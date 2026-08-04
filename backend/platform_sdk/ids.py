"""Public Base identifier allocation surface for official domains."""

from backend.utils.gid import next_gid
from backend.db.sequences import next_display_id

__all__ = ["next_display_id", "next_gid"]
