from datetime import datetime, timezone

from plugins.craft.craft_backend.data.bop_fork_mysql import _utcnow


def test_fork_preview_clock_is_utc_naive_for_mysql_datetime() -> None:
    value = _utcnow()
    assert isinstance(value, datetime)
    assert value.tzinfo is None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    assert 0 <= (now - value).total_seconds() < 2
