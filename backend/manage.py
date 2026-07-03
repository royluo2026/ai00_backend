"""
backend/manage.py
─────────────────
AI00 后端管理 CLI

用法：
  # 将指定邮箱用户提升为超管（需先用飞书登录过一次）
  python -m backend.manage create-superadmin --email your@email.com

  # 查看当前超管列表
  python -m backend.manage list-superadmins

适用场景：
  - 本地开发：跳过 FIRST_SUPER_ADMIN_EMAIL 自举，直接提权
  - 生产恢复：所有超管意外失效时的应急手段
"""
import argparse
import sys
from pathlib import Path

# 确保 backend/ 父目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent.parent))


def _init_settings():
    """加载 .env，初始化数据库连接池。"""
    from backend.db.connection import init_pool
    init_pool()


def create_superadmin(email: str) -> None:
    _init_settings()
    from backend.db.connection import get_conn
    email = email.strip().lower()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid, name, system_role FROM workmanship_auth_users WHERE email = %s", (email,)
            )
            row = cur.fetchone()
            if not row:
                print(
                    f"❌ 用户不存在（email={email}）\n"
                    f"   请先用飞书登录一次，再执行此命令。"
                )
                sys.exit(1)
            if row["system_role"] == "super_admin":
                print(f"ℹ️  {row['name']} ({email}) 已经是 super_admin，无需操作。")
                return
            cur.execute(
                "UPDATE workmanship_auth_users SET system_role='super_admin', updated_at=NOW() "
                "WHERE email=%s",
                (email,),
            )
    print(f"✅ 已将 {row['name']} ({email}) 的角色设置为 super_admin")


def list_superadmins() -> None:
    _init_settings()
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name, email, created_at FROM workmanship_auth_users "
                "WHERE system_role='super_admin' AND is_active=TRUE "
                "ORDER BY created_at"
            )
            rows = cur.fetchall()
    if not rows:
        print("（当前没有超级管理员）")
        return
    print(f"超级管理员列表（共 {len(rows)} 人）：")
    for r in rows:
        print(f"  · {r['name']}  <{r['email']}>  注册于 {r['created_at']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AI00 后端管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    p_sa = subparsers.add_parser(
        "create-superadmin",
        help="将指定邮箱用户提升为 super_admin",
    )
    p_sa.add_argument("--email", required=True, help="目标用户的飞书邮箱")

    subparsers.add_parser("list-superadmins", help="列出所有超级管理员")

    args = parser.parse_args()

    if args.command == "create-superadmin":
        create_superadmin(args.email)
    elif args.command == "list-superadmins":
        list_superadmins()
    else:
        parser.print_help()
