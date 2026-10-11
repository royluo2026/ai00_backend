from pathlib import Path
import re

import pytest

from backend.db.table_prefix import configure_table_prefix, rewrite_sql
from backend.db.versioned_migrations import strip_sql_comments


ROOT = Path(__file__).resolve().parents[2]
SOURCES = (ROOT / "backend/db/mysql_schema.sql", *sorted((ROOT / "backend/db/migrations").rglob("*.sql")))
TABLE_DECLARATIONS = re.compile(
    r"\b(?:CREATE\s+TABLE|ALTER\s+TABLE|REFERENCES)\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?`?((?:(?:test|pp)_)?workmanship_[A-Za-z0-9_]+|"
    r"(?:(?:test|pp)_)?ai00_[a-z0-9_]+_schema_migrations)\b",
    re.IGNORECASE,
)


@pytest.fixture(autouse=True)
def reset_prefix():
    configure_table_prefix("")
    yield
    configure_table_prefix("")


@pytest.mark.parametrize("prefix", ["test_", "pp_"])
@pytest.mark.parametrize("source", SOURCES, ids=lambda path: path.relative_to(ROOT).as_posix())
def test_integrated_migration_sql_rewrites_idempotently(source, prefix):
    configure_table_prefix(prefix)
    original = source.read_text(encoding="utf-8")
    rendered = rewrite_sql(original)
    assert rewrite_sql(rendered) == rendered
    assert len(rendered) >= len(original)
    expected_tables = TABLE_DECLARATIONS.findall(strip_sql_comments(original))
    rendered_tables = TABLE_DECLARATIONS.findall(strip_sql_comments(rendered))
    assert rendered_tables == [prefix + table for table in expected_tables]
