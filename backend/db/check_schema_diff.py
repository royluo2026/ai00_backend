"""
backend/db/check_schema_diff.py
────────────────────────────────
比对 PG 实际 schema 与 mysql_schema.sql + migrate.py 的差异。

用法：
  python backend/db/check_schema_diff.py

在脚本开头的 PG_DUMP 变量里粘贴从 information_schema 查出来的数据。
"""
import re
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# PG 实际 schema（表.列 结构，用户从 information_schema 查出）
# schema 前缀 → workmanship_<prefix>_<table> 的映射规则
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA_PREFIX_MAP = {
    "app":         "workmanship_app_",
    "auth":        "workmanship_auth_",
    "bop":         "workmanship_bop_",
    "factory":     "workmanship_factory_",
    "integration": "workmanship_int_",
    "knowledge":   "workmanship_",      # know_ / onto_ 需要特判
    "proj":        "workmanship_proj_",
    "template":    "workmanship_tpl_",
    "work":        "workmanship_work_",
}

KNOWLEDGE_PREFIX = {
    "knowledge_entries":    "workmanship_know_entries",
    "knowledge_folders":    "workmanship_know_folders",
    "knowledge_items":      "workmanship_know_items",
    "knowledge_favorites":  "workmanship_know_favorites",
    "knowledge_recent":     "workmanship_know_recent",
    "craft_rules":          "workmanship_know_craft_rules",
    "onto_classes":         "workmanship_onto_classes",
    "onto_properties":      "workmanship_onto_properties",
    "onto_relations":       "workmanship_onto_relations",
    "onto_axioms":          "workmanship_onto_axioms",
}


def pg_to_mysql_table(schema: str, table: str) -> str:
    if schema == "knowledge":
        return KNOWLEDGE_PREFIX.get(table, f"workmanship_know_{table}")
    prefix = SCHEMA_PREFIX_MAP.get(schema, f"workmanship_{schema}_")
    return prefix + table


# ─────────────────────────────────────────────────────────────────────────────
# 解析 mysql_schema.sql + migrate.py 得到 MySQL 已有表/列
# ─────────────────────────────────────────────────────────────────────────────

REPO = Path(__file__).resolve().parent.parent.parent  # AI00_root_web/

def _extract_create_cols(text: str) -> dict:
    """从 SQL 文本中提取 CREATE TABLE 块的列名。"""
    tables = {}
    for m in re.finditer(
        r'CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\)\s*ENGINE=InnoDB',
        text, re.DOTALL | re.IGNORECASE
    ):
        tbl = m.group(1)
        body = m.group(2)
        cols = set()
        for line in body.splitlines():
            s = line.strip().rstrip(',')
            if not s:
                continue
            up = s.upper()
            if any(up.startswith(k) for k in ('PRIMARY', 'UNIQUE', 'INDEX', 'KEY',
                                               'CONSTRAINT', '--', '/*', 'ENGINE')):
                continue
            # 第一个词是列名
            tok = re.match(r'`?(\w+)`?', s)
            if tok:
                cols.add(tok.group(1))
        tables[tbl] = cols
    return tables


def load_mysql_tables() -> dict:
    """合并 mysql_schema.sql + migrate.py 中的所有建表定义。"""
    schema_sql  = (REPO / "backend" / "db" / "mysql_schema.sql").read_text(encoding="utf-8")
    migrate_py  = (REPO / "backend" / "db" / "migrate.py").read_text(encoding="utf-8")
    all_tables  = {}
    all_tables.update(_extract_create_cols(schema_sql))
    all_tables.update(_extract_create_cols(migrate_py))
    return all_tables


# ─────────────────────────────────────────────────────────────────────────────
# 运行对比
# ─────────────────────────────────────────────────────────────────────────────

def main():
    mysql_tables = load_mysql_tables()
    print(f"[MySQL] 共 {len(mysql_tables)} 张表（schema.sql + migrate.py）\n")

    # PG dump 文件路径（用户把内容存在这里）
    dump_file = Path(__file__).parent / "pg_dump.txt"
    if not dump_file.exists():
        print(f"请把 PG dump 粘贴到: {dump_file}")
        return

    # 解析 PG dump
    pg_tables: dict = {}   # mysql_table_name -> set of col names
    for line in dump_file.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if len(parts) < 3:
            continue
        full_table = parts[0]         # e.g. "app.ai_audit_logs"
        col_name   = parts[1]
        if "." not in full_table:
            continue
        schema, table = full_table.split(".", 1)
        mysql_name = pg_to_mysql_table(schema, table)
        pg_tables.setdefault(mysql_name, set()).add(col_name)

    print(f"[PG]    共 {len(pg_tables)} 张表\n")
    print("=" * 70)

    # 1. PG 有，MySQL 没有 → 缺表
    missing_tables = sorted(set(pg_tables) - set(mysql_tables))
    if missing_tables:
        print(f"\n❌ 缺少 {len(missing_tables)} 张表（PG 有，MySQL 无）:")
        for t in missing_tables:
            pg_name = next((k for k, v in pg_tables.items() if k == t), t)
            cols = sorted(pg_tables[t])
            print(f"  {t}  [{len(cols)} 列]: {', '.join(cols[:6])}{'...' if len(cols)>6 else ''}")
    else:
        print("\n✅ 所有 PG 表在 MySQL 中都有对应")

    # 2. 逐表对比列差异
    print(f"\n{'=' * 70}")
    col_issues = []
    for pg_tbl, pg_cols in sorted(pg_tables.items()):
        if pg_tbl not in mysql_tables:
            continue  # 已在上面报缺表
        my_cols = mysql_tables[pg_tbl]
        missing_cols = sorted(pg_cols - my_cols)
        extra_cols   = sorted(my_cols - pg_cols)
        if missing_cols or extra_cols:
            col_issues.append((pg_tbl, missing_cols, extra_cols))

    if col_issues:
        print(f"\n⚠️  {len(col_issues)} 张表存在列差异:")
        for tbl, missing, extra in col_issues:
            print(f"\n  [{tbl}]")
            if missing:
                print(f"    缺列（PG 有 MySQL 无）: {', '.join(missing)}")
            if extra:
                print(f"    多列（MySQL 有 PG 无）: {', '.join(extra)}")
    else:
        print("\n✅ 所有已对应表的列完全一致")

    print(f"\n{'=' * 70}")
    print("对比完成")


if __name__ == "__main__":
    main()
