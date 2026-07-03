"""
backend/scripts/migrate_to_minio.py
────────────────────────────────────
一次性迁移：将 backend/static/uploads/ 中的本地文件上传到 MinIO，
然后更新 PostgreSQL 各表中 JSONB 附件列的 URL。

用法
────
  python -m backend.scripts.migrate_to_minio [--dry-run]

  --dry-run   只打印将要做什么，不写入 MinIO 和 DB。

环境
────
  从 backend/.env.dev 或 backend/.env 读取 MINIO_* 和 USERS_DB_URL。
  运行前需先启动 MinIO 并确保后端服务可连接数据库。
"""
from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import sys
from pathlib import Path
from urllib.parse import urlparse

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s %(message)s",
)
_log = logging.getLogger(__name__)

# ── 需要更新 URL 的表和列 ─────────────────────────────────────────────────────
# is_obj_array=True  → [{name, url, mime}, ...]  更新 item["url"]
# is_obj_array=False → ["http://...", ...]        更新数组元素本身
_ATTACHMENT_COLS = [
    ("work.tasks",                  "attachments",       True),
    ("work.issues",                 "attachments",       True),
    ("proj.tasks",                  "attachments",       True),
    ("proj.issues",                 "attachments",       True),
    ("knowledge.knowledge_entries", "attachments",       True),
    ("bop.bop_entries",             "process_flow_pic",  False),
    ("bop.bop_entries",             "process_chart_pic", False),
]


def _load_env():
    """加载 .env.dev 或 .env（与 config.py 保持相同优先级）。"""
    here = Path(__file__).parent.parent  # backend/
    for fname in (".env.dev", ".env"):
        p = here / fname
        if p.exists():
            try:
                from dotenv import load_dotenv
                load_dotenv(p, override=False, encoding="utf-8")
            except UnicodeDecodeError:
                from dotenv import load_dotenv
                load_dotenv(p, override=False, encoding="gbk")
            _log.info("已加载配置文件：%s", p)
            break


def _old_url_to_relative(url: str) -> str:
    """
    将旧 URL 标准化为相对路径，方便查表替换。
    "/static/uploads/foo.png"         → "/static/uploads/foo.png"
    "http://host/static/uploads/foo"  → "/static/uploads/foo"
    """
    if url.startswith("http"):
        return urlparse(url).path
    return url


def _build_url_map(uploads_dir: Path, storage) -> dict[str, str]:
    """
    遍历 uploads_dir，将每个文件上传到 MinIO，构建 {相对旧URL: 新MinIO URL} 映射。
    """
    url_map: dict[str, str] = {}
    all_files = [f for f in uploads_dir.rglob("*") if f.is_file()]
    _log.info("待迁移文件数：%d", len(all_files))

    for f in all_files:
        ext  = f.suffix.lower() or ".bin"
        mime, _ = mimetypes.guess_type(str(f))
        mime = mime or "application/octet-stream"
        data = f.read_bytes()

        # 子目录 bop_pics 对应 MinIO prefix
        rel   = f.relative_to(uploads_dir)
        parts = rel.parts
        prefix = "bop_pics" if (len(parts) > 1 and parts[0] == "bop_pics") else ""

        new_url = storage.upload(data, ext, mime, prefix=prefix)
        if not new_url:
            _log.error("上传失败：%s，终止迁移", f)
            sys.exit(1)

        if prefix:
            old_rel = f"/static/uploads/bop_pics/{f.name}"
        else:
            old_rel = f"/static/uploads/{f.name}"

        url_map[old_rel] = new_url
        _log.info("  ✓  %s\n     → %s", old_rel, new_url)

    return url_map


def _update_obj_array_col(conn, table: str, col: str,
                          url_map: dict, dry_run: bool) -> int:
    """更新 [{name, url, mime}, ...] 结构的 JSONB 列。"""
    updated = 0
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT gid, {col} FROM {table} "
            f"WHERE {col} IS NOT NULL AND {col}::text LIKE '%/static/uploads/%'"
        )
        rows = cur.fetchall()

    for row in rows:
        gid   = row["gid"]
        items = row[col]
        if isinstance(items, str):
            try:
                items = json.loads(items)
            except Exception:
                continue
        if not isinstance(items, list):
            continue

        changed = False
        for item in items:
            if not isinstance(item, dict) or "url" not in item:
                continue
            rel = _old_url_to_relative(item["url"])
            if rel in url_map:
                item["url"] = url_map[rel]
                changed = True

        if changed:
            _log.info("  [%s.%s] gid=%s → %d 个附件 URL 已更新", table, col, gid, len(items))
            if not dry_run:
                with conn.cursor() as cur:
                    cur.execute(
                        f"UPDATE {table} SET {col} = %s::jsonb WHERE gid = %s",
                        (json.dumps(items, ensure_ascii=False), gid),
                    )
                conn.commit()
            updated += 1

    return updated


def _update_str_array_col(conn, table: str, col: str,
                          url_map: dict, dry_run: bool) -> int:
    """更新 ["http://...", ...] 结构的 JSONB 列。"""
    updated = 0
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT gid, {col} FROM {table} "
            f"WHERE {col} IS NOT NULL AND {col}::text LIKE '%/static/uploads/%'"
        )
        rows = cur.fetchall()

    for row in rows:
        gid   = row["gid"]
        items = row[col]
        if isinstance(items, str):
            try:
                items = json.loads(items)
            except Exception:
                continue
        if not isinstance(items, list):
            continue

        new_items = []
        changed = False
        for item in items:
            if isinstance(item, str):
                rel = _old_url_to_relative(item)
                if rel in url_map:
                    new_items.append(url_map[rel])
                    changed = True
                    continue
            new_items.append(item)

        if changed:
            _log.info("  [%s.%s] gid=%s → URL 已更新", table, col, gid)
            if not dry_run:
                with conn.cursor() as cur:
                    cur.execute(
                        f"UPDATE {table} SET {col} = %s::jsonb WHERE gid = %s",
                        (json.dumps(new_items, ensure_ascii=False), gid),
                    )
                conn.commit()
            updated += 1

    return updated


def main():
    parser = argparse.ArgumentParser(description="迁移本地附件到 MinIO")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印操作，不实际写入")
    args = parser.parse_args()

    if args.dry_run:
        _log.info("=== DRY-RUN 模式，不写入任何数据 ===")

    _load_env()

    # 导入后端模块（必须在加载 env 之后）
    from backend.core import storage
    from backend.db.connection import init_pool, get_conn

    storage.init_storage()
    if not storage._is_ready():
        _log.error("MinIO 初始化失败，检查 MINIO_* 环境变量并确保 MinIO 服务已启动。")
        sys.exit(1)

    init_pool()

    uploads_dir = Path(r"E:\Data\test\attachments\uploads")
    if not uploads_dir.exists() or not any(uploads_dir.rglob("*")):
        _log.info("本地上传目录为空或不存在，无需迁移。")
        sys.exit(0)

    # ── Phase 1：上传文件到 MinIO ──────────────────────────────────────────────
    _log.info("=== Phase 1：上传本地文件到 MinIO ===")
    if args.dry_run:
        files = [f for f in uploads_dir.rglob("*") if f.is_file()]
        for f in files:
            _log.info("  [dry-run] 将上传：%s", f)
        url_map = {}
    else:
        url_map = _build_url_map(uploads_dir, storage)
    _log.info("Phase 1 完成：%d 个文件已上传", len(url_map))

    if not url_map and not args.dry_run:
        _log.warning("没有文件被上传，跳过 DB 更新。")
        sys.exit(0)

    # ── Phase 2：更新数据库 JSONB 中的 URL ────────────────────────────────────
    _log.info("=== Phase 2：更新数据库 URL ===")
    total = 0
    with get_conn() as conn:
        for (table, col, is_obj) in _ATTACHMENT_COLS:
            try:
                if is_obj:
                    n = _update_obj_array_col(conn, table, col, url_map, args.dry_run)
                else:
                    n = _update_str_array_col(conn, table, col, url_map, args.dry_run)
                _log.info("  %s.%s：%d 行已更新", table, col, n)
                total += n
            except Exception as e:
                _log.warning("  %s.%s：跳过（%s）", table, col, e)

    _log.info("=== 迁移完成：共更新 %d 行 ===", total)
    if args.dry_run:
        _log.info("=== DRY-RUN，未写入任何数据 ===")
    else:
        _log.info("建议：保留 backend/static/uploads/ 目录几天，确认无问题后可手动清理。")


if __name__ == "__main__":
    main()
