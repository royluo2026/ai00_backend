# Capability V2 单库 DBeaver 实施手册

本流程只处理 `ai00_test` 的结构元数据和非破坏性 DDL，不读取业务行，也不保存密码或连接串。生产环境仍是单数据库逻辑领域隔离，不应描述为物理数据库隔离。

> **当前状态（2026-08-13）：** 仓库已经具备
> `single_database_domain_tables` 部署配置、逐表 Owner、确定性 Schema 编译、
> Schema 差异规划、DBeaver 执行包和五组授权校验器。当前冻结 Schema 包含
> 204 张表、2307 个字段、535 个索引，零不支持 DDL。上述结果是仓库工具证据，
> 不是 `ai00_test` 现场验收结果。当前 Gitea Capability RC 工作流仍对应多库强化
> 隔离配置；在单库 RC 工作流补齐前，本文的人工现场步骤和保存的证据是公司环境
> 数据库门禁，不能用旧多库 RC 报告替代。

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

这里的四个开发账号组是数据库授权分组，不等同于四人团队的产品职责划分。团队可以按领域和消费者层分工，但每个人访问测试库时仍必须使用与当前任务匹配的最小权限账号。

首次只生成导出文件可执行：

```powershell
python backend/scripts/plan_single_database_migration.py `
  --expected backend/governance/schema/expected-schema.json `
  --output E:/Projects/ai00_v3/.runtime/schema-audit/package `
  --export-only
```

## 测试环境运行验收

Schema 和 Grant 验证通过后，再启动 Backend、Agent Runtime、MCP Gateway 和
Device Local Runtime。测试记录必须绑定同一个 Git Commit、Catalog Release、
`isolation_profile=single_database_domain_tables` 和测试环境 ID，至少覆盖：

1. Backend health、Catalog、未认证拒绝、授权调用和审计记录；
2. 11 个 Domain 各一项 manifest-owned smoke Capability；
3. Plugin 的 Catalog、允许、拒绝和审批路径；
4. Agent 的工具发现、允许、拒绝、审批、幂等和恢复路径；
5. MCP initialize、工具发现、允许和拒绝路径；
6. Local Runtime 主动出站 heartbeat、lease、操作回执；
7. OIS、JWT/OAuth discovery、飞书回调、CORS 和浏览器可访问对象 URL；
8. 共享 Runtime 账号无 DDL，四个开发组账号与逐表授权矩阵一致；
9. 运行日志、审计和输出 Artifact 不包含密码、Token、连接串或私钥。

任何必测项失败、跳过或缺少当前运行证据时，结论只能是“测试环境验收未通过”。

## 从测试晋级生产

生产发布遵循“同一制品晋级”，不在生产服务器重新拉取不同 Commit 或重新构建：

1. 冻结测试通过的 Git Commit、Catalog Release、前后端制品 Hash 和 Migration 包 Hash；
2. 由业务负责人和发布负责人审核测试证据；
3. 在生产只读采集 Schema 元数据，使用相同 `expected-schema.json` 生成生产差异包；
4. 对生产差异进行人工审核和备份/恢复准备；
5. DBA 或临时迁移身份分阶段执行非破坏性 DDL，每阶段失败立即停止；
6. 使用生产专属 `ENV_FILE` 和 Secrets 启动同一应用制品；
7. 执行 health、登录、Catalog、只读 Capability 和一项受控写入冒烟；
8. 检查错误率、审计、数据库连接、OIS 和消费者调用；
9. 应用异常时回退上一制品；Schema 问题使用新的向前修复 Migration，不执行破坏性自动回滚。

测试和生产必须使用不同的数据库/租户、OAuth 回调、域名、CORS、OIS 空间、
JWT、插件、Agent、设备及服务密钥。生产密钥不得复制到测试机，`.runtime/*.env`
不得提交 Git 或上传为构建 Artifact。
