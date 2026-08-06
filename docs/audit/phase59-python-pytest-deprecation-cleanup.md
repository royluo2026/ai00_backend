# Phase 59 — Python / pytest 弃用清理

日期：2026-08-06
分支：`codex/capability-wave-a`

## 改动

- 从外部数据源安全表达式 AST 白名单移除已弃用的 `ast.Num`；Python 3.8+ 数字字面量由 `ast.Constant` 覆盖。
- 将 `test_mysql_migration.py` 两个无状态只读 fixture 从类级实例方法改为函数级 fixture，消除 pytest 10 兼容警告。
- 没有修改 Capability 注册、权限、数据库 Schema 或领域行为。

## 验证

- 聚焦回归：`97 passed`。
- Python 编译检查：通过。
- 完整后端离线回归：`575 passed in 13.45s`，0 warning。
- `git diff --check`：通过。
- 没有连接真实数据库、push 或部署。
