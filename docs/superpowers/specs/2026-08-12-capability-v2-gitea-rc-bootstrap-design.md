# Capability V2 Gitea RC 与测试数据库 Bootstrap 设计

**日期：** 2026-08-12  
**状态：** 已批准方案的书面化设计  
**关联设计：** `2026-08-12-capability-v2-three-goal-completion-design.md`  
**关联计划：** `2026-08-12-capability-v2-three-goal-completion-implementation.md`

## 1. 背景与目标

Capability V2 的代码、离线验收和边界门禁已经完成，但真实 RC 执行链仍有两个环境缺口：

1. 仓库实际托管于 Gitea，Gitea 当前只发现 `.gitea/workflows`；Capability V2 RC 工作流只存在于 `.github/workflows`，因此远端无法触发。
2. 本地 OceanBase `demo` 测试集群仍使用旧单库和少量领域账号，不能证明十一领域数据库、账号和权限独立。

本设计补齐可执行的 Gitea RC 入口和安全、可重复的测试数据库引导流程。完成后，受保护 runner 可以在当前 Git commit 上创建或复用隔离的十一领域测试数据库，运行真实进程与数据库证据生成器，并产出无失败、无跳过的 RC 报告。

## 2. 非目标

- 不从 shell 历史、PowerShell 历史、桌面保存配置或其他非标准位置探测管理员凭据。
- 不读取、复制或修改生产数据库凭据。
- 不把密码、完整连接串或运行证据写入 Git、控制台日志或测试快照。
- 不把普通 `test-server` runner 直接视为受保护 RC runner。
- 不用 MySQL、SQLite、mock 或旧单库账号替代 OceanBase 4.3.5+ 的真实十一域隔离证据。
- 不在 bootstrap 中伪造 Provider CRUD、Gateway、Plugin、Agent、MCP 或 Local Runtime 结果。

## 3. 选定方案

采用“Gitea 原生工作流 + 专用 runner 标签 + 显式管理员 URL bootstrap”方案。

### 3.1 双工作流来源

- `.github/workflows/capability-v2-release.yml` 继续服务 GitHub 兼容环境。
- 新增 `.gitea/workflows/capability-v2-release.yml`，作为当前 Gitea 的真实 RC 入口。
- 两份文件允许 runner 标签和平台必要语法不同，但以下发布门禁必须一致：
  - Provider 制品冻结检查；
  - Catalog、文档、User Function Registry 和 acceptance manifest 漂移检查；
  - 领域依赖与边界审计；
  - `backend/tests plugins` 全量 Python 测试；
  - Agent、MCP 和 Local Runtime 测试；
  - 实时数据库隔离验证；
  - 当前运行 RC evidence 组装；
  - strict release-candidate acceptance；
  - 对最终报告再次执行 strict completion 检查；
  - 无论成功或失败均上传通过 schema/secret 扫描的 Provider、runtime、数据库、assembled RC evidence 和最终报告。

测试通过解析 YAML 后比较规范化步骤，不通过脆弱的全文比较实现一致性。

### 3.2 受保护 runner

Gitea RC job 使用标签：

```yaml
runs-on: [self-hosted, test-server, capability-v2-rc]
```

现有 runner 只有在明确加入 `capability-v2-rc` 标签后才能领取该 job。标签配置属于运维状态，不由仓库测试自动放宽。工作流继续使用 `capability-v2-release-candidate` environment 名称和显式 `environment_id` 输入；RC evidence 必须绑定 Gitea run ID、attempt、Git commit 和 environment ID。

Gitea bootstrap 模式只从受保护 secret 注入 `AI00_RC_ADMIN_DB_URL`。二十二个领域 URL 由 bootstrap 写入受 ACL 保护的临时 env 文件，再由同一 job 导入后续 migration、Provider 和 verifier 步骤；它们不是二十二个长期 Gitea secrets。GitHub 工作流可以继续使用预配的二十二个领域 secrets，但两种凭据来源最终必须提供相同的十一域环境变量集合，且不得改变发布门禁。

### 3.3 十一域数据库 Bootstrap

新增 CLI：

```powershell
python backend/scripts/bootstrap_capability_v2_rc_databases.py `
  --admin-url-env AI00_RC_ADMIN_DB_URL `
  --environment-id capability-v2-local-rc `
  --output-env .runtime/capability-v2-rc.env
```

管理员连接只能通过命名环境变量提供，不能作为命令行明文参数。CLI 必须：

1. 在执行任何 `CREATE` 前完成全部安全校验：目标必须是 OceanBase 4.3.5+、MySQL 模式和严格 SQL 模式。
2. 管理员必须连接到名称包含 `test` 或 `rc` 的专用测试租户；明确拒绝 `sys` 租户、无法确认租户身份的连接以及生产租户。数据库 URL 中的租户身份与服务器查询结果必须一致。
3. 默认只接受 loopback 主机；非 loopback 必须显式传入 `--allow-host <exact-host>`，且该参数不能绕过测试租户校验。
4. 要求 `--environment-id` 包含 `test` 或 `rc`，并拒绝 `prod`、`production`。
5. 从 `official_domains.json` 读取且只读取十一领域数据库声明，不维护第二份领域清单。
6. 为每个领域创建其声明数据库、一个 DDL 用户和一个 runtime 用户。
7. DDL 用户仅拥有自己数据库执行既有 migration 所需的对象创建、变更、删除及 DML 权限，不拥有用户管理、授权、跨库或全局权限；runtime 用户仅拥有自己数据库的 `SELECT/INSERT/UPDATE/DELETE`，无 DDL、授权、跨库或全局权限。
8. 使用密码学安全随机密码；不在标准输出中打印密码或完整 URL。
9. 原子写入输出 env 文件，并在 Windows 上把 ACL 收紧到当前用户和 SYSTEM。
10. 对已存在的数据库/用户失败关闭。仅当 `--reuse-env` 指向由本工具生成且结构、环境 ID、租户、host 和域集合完全匹配的既有文件，并且工具能够以文件内账号重新连接及复核 grants 时，才允许无创建地复用；复用不会重置密码或修改权限。
11. 输出中生成十一组 runtime URL、十一组 DDL URL，以及不含密码的 bootstrap 摘要。

Bootstrap 只建立数据库和账号。之后由现有 `run_domain_migrations.py --apply` 逐域应用 migration，再由 `verify_domain_database_isolation.py` 验证 owner 操作、运行账号 DDL 拒绝以及全部 110 个跨域读写拒绝。

## 4. 数据与执行流

```text
显式 AI00_RC_ADMIN_DB_URL
        │
        ▼
bootstrap CLI ──验证 OceanBase/test 环境──► 11 databases + 22 users
        │                                      │
        └──原子输出 .runtime RC env────────────┘
                                               │
                                               ▼
                                  11× domain migration apply
                                               │
                                               ▼
Provider/Gateway/consumer harness ─────► runtime/provider evidence
                                               │
数据库隔离 verifier ───────────────────► database-isolation.json
                                               │
evidence assembler ────────────────────► capability-v2-rc-evidence.json
                                               │
strict RC acceptance ──────────────────► capability-v2-release-candidate.json
                                               │
strict completion report check ────────► 发布允许或失败关闭
```

## 5. Secret 与日志边界

- 管理员 URL 只存在于 runner 的受保护 secret 和子进程环境中。
- 生成的 22 个 URL 只存在于 runner workspace 的 `.runtime`/`artifacts` 临时文件和当前 job 环境中。
- 日志只允许打印环境 ID、域 ID、数据库名、用户名、步骤状态和哈希；禁止打印 URL、密码、Authorization、证书私钥或 secret 值。
- Gitea secrets 由运维步骤显式写入；仓库代码不调用历史文件或凭据存储器自动发现 secret。
- 上传 artifact 前必须验证文件 schema；包含管理员 URL 或密码的 env 文件不得上传。

## 6. 失败与恢复

- OceanBase 版本、模式、SQL mode、host、租户或环境 ID 不符合要求：创建任何对象前退出。
- 任一数据库或账号创建失败：停止后续创建，并输出不含 secret 的已创建对象清单；不自动删除已有对象。
- migration 失败：停止 RC，不生成 passed evidence。
- 权限矩阵任一 owner 操作失败、runtime DDL 成功或跨域访问成功：RC 失败关闭。
- runtime/provider evidence 与 environment、run 或 commit 不一致：assembler 拒绝。
- Gitea/GitHub 工作流门禁漂移：仓库测试失败。
- 清理由单独的显式运维命令完成；bootstrap 不提供隐式 `--force` 或自动 drop。

## 7. 测试设计

### 7.1 工作流测试

- Gitea RC 文件存在且 YAML 可解析。
- runner 标签包含 `capability-v2-rc`，不能只有 `test-server`。
- GitHub/Gitea 两份 RC 工作流的强制门禁集合和顺序一致。
- Gitea 工作流必须只把管理员 URL 作为数据库 secret 输入，并从 bootstrap 输出导入全部十一域 runtime/DDL 环境变量；测试要拒绝缺域、长期保存生成 URL或上传 env 文件。
- acceptance 后必须执行 report completion 复核，并上传五份可独立审计且不含 secret 的 Provider、runtime、数据库、assembled RC 和最终报告证据。

### 7.2 Bootstrap 单元测试

使用记录 SQL 的 fake connection 验证：

- 从 `official_domains.json` 得到准确十一域；
- 生成准确 11 个数据库和 22 个不同用户；
- runtime/DDL grants 不跨库且 runtime 无 DDL；
- 非 OceanBase、低版本、非 MySQL、非严格模式、`sys`/非测试租户、production 环境、未授权远程 host 全部失败；
- 已存在对象和不匹配的 reuse env 失败关闭；
- 控制台和异常中不含密码；
- env 原子写入，URL 可解析且 key 集合准确。

### 7.3 集成验证

- 在本地 `demo` 测试租户中使用显式管理员 URL运行 bootstrap。
- 应用十一域 migration。
- 运行数据库隔离 verifier，证明 11 个 owner 操作、runtime DDL 拒绝和 110 个跨域凭据对读写拒绝。
- 运行真实 Gateway/Provider/Plugin/Agent/MCP/Local Runtime harness。
- Gitea workflow 最终报告必须 `status: passed`、`validation_scope: runtime_e2e`、1848/1848、失败 0、跳过 0。

## 8. 完成条件

本设计只有在以下条件同时满足时完成：

1. Gitea 能发现并调度专用 RC workflow；
2. runner 带 `capability-v2-rc` 标签，且管理员、身份、服务健康检查等所需受保护 secrets 已配置；
3. 十一数据库和二十二账号由 bootstrap 建立并通过 live grant verifier；
4. 所有 migration ledger 与当前 Git commit 的冻结清单一致；
5. 真实进程 evidence 绑定当前 environment/run/commit；
6. strict RC 报告通过并由 completion CLI 再次验证；
7. 最终 RC artifact 可下载、可复核，且不包含 secret；
8. 用户未跟踪交接/审核文件保持原样。
