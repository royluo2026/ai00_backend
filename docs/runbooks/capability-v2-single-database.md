# Capability V2 单库 DBeaver 实施手册

本流程只处理 `ai00_test` 的结构元数据和非破坏性 DDL，不读取业务行，也不保存密码或连接串。生产环境仍是单数据库逻辑领域隔离，不应描述为物理数据库隔离。

1. 在 DBeaver 连接并明确选择 `ai00_test`，执行包中的 `00-export-schema.sql`。
2. 将三个结果集按原始表头导出为 UTF-8 CSV：`ai00_test_tables.csv`、`ai00_test_columns.csv`、`ai00_test_indexes.csv`，放入 `E:/Projects/ai00_v3/.runtime/schema-audit/`。
3. 在仓库根目录执行：

   ```powershell
   python backend/scripts/plan_single_database_migration.py `
     --expected backend/governance/schema/expected-schema.json `
     --snapshot E:/Projects/ai00_v3/.runtime/schema-audit `
     --output E:/Projects/ai00_v3/.runtime/schema-audit/package
   ```

4. 退出码为 `2` 或 checklist 显示人工差异时立即停止；不得用 `IF NOT EXISTS` 绕过冲突。
5. 由 DBA/迁移身份依次执行 `01-preflight.sql`、`10-create-missing-tables.sql`、`20-add-safe-columns.sql`、`30-add-missing-indexes.sql`，任一语句报错即停止。
6. 执行 `90-verify-schema.sql`，重新导出三份 CSV，再运行规划器。
7. 只有缺失表、字段、索引和不兼容差异全部为零，才继续创建领域账号并启动 Backend、Agent、MCP 和 Local Runtime 联调。

## 五个运行账号的授权验收

DBA 创建四个开发组账号（Craft、Digital Model + Simulation、Device、其余七域）和一个共享 Runtime 账号。生成器只输出逐表 `SELECT/INSERT/UPDATE/DELETE`，DDL 始终由外部迁移身份执行：

```powershell
python backend/scripts/generate_domain_grants.py --database ai00_test `
  --account-group craft=USER_CRAFT --account-group model_simulation=USER_MODEL_SIM `
  --account-group device=USER_DEVICE --account-group shared=USER_SHARED `
  --account-group runtime=USER_RUNTIME
```

分别执行 `SHOW GRANTS FOR 'USER'@'HOST'`，将结果按 `craft`、`model_simulation`、`device`、`shared`、`runtime` 五个键保存为 JSON 数组，再运行 `verify_single_database_grants.py --input FILE`。输出只含组标签、表数量、缺失/多余表名和失败代码；任一通配授权、DDL、`ALL PRIVILEGES` 或 `GRANT OPTION` 都不通过。

首次只生成导出文件可执行：

```powershell
python backend/scripts/plan_single_database_migration.py `
  --expected backend/governance/schema/expected-schema.json `
  --output E:/Projects/ai00_v3/.runtime/schema-audit/package `
  --export-only
```
