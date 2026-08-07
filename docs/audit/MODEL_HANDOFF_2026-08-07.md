# AI00 v3 模型交接说明

交接日期：2026-08-07
当前工作主题：Capability 架构治理与首批能力实施
交接状态：本地功能分支已保存；未 push、未部署、未连接真实数据库

## 0. 新模型先读什么

按以下顺序阅读，后面的新决策覆盖前面的历史结论：

1. 本文。
2. `E:\Projects\ai00_v3\.worktrees\capability-wave-a\SYSTEM_OPTIMIZATION_BACKLOG.md`。
3. `E:\Projects\ai00_v3\.worktrees\capability-wave-a\docs\audit\phase63-defer-immature-vpps-rules.md`。
4. `E:\Projects\ai00_v3\.worktrees\capability-wave-a\docs\audit\phase62-knowledge-web-acl-retirement.md`。
5. `E:\Projects\ai00_v3\.worktrees\capability-wave-a\docs\audit\phase61-tasks-6-14-completion-audit.md`，只用于实施证据；其中 Task 13 的阻塞结论已被 Phase 63 修正。
6. `E:\Projects\ai00_v3\CAPABILITY_CROSS_DOMAIN_SPEC.md`、`DEVELOPMENT_COLLABORATION_SPEC.md`、`ADR-007_SYSTEM_AGENT_RUNTIME_HARNESS_BOUNDARIES.md`。
7. `E:\Projects\ai00_v3\.worktrees\capability-wave-a\docs\oceanbase-mysql-compatibility.md`。

以下文件是历史材料，不是当前状态权威来源：

- `E:\Projects\ai00_v3\V3_AUDIT_HANDOFF.md`：主要停留在 Phase 32 左右。
- `E:\Projects\ai00_v3\SYSTEM_OPTIMIZATION_BACKLOG.md`：根目录副本未同步 Phase 60–63。
- Phase 60/61 中“Web ACL 尚未处理”“四项 VPPS 阻塞整个 Task 13”等结论，分别已被 Phase 62/63 覆盖。

## 1. 用户的稳定要求

- 以长期可维护、可扩展为第一目标，不要给中庸架构答案。
- Web 是主产品入口，不回退到 Electron 主应用；Electron 只保留 legacy 壳。
- 需要本地能力时安装独立 Local Runtime，并具有独立升级机制。
- Agent Runtime 默认在云端或客户私有云，不放入 Local Runtime；Pi 只能作为可替换 Harness Adapter。
- 基座、工艺、数模、Agent、生产设备严格分开；数据库平台由基座治理，但领域仍拥有本域表、Repository、SQL 和数据语义。
- OceanBase 使用 MySQL 模式、单业务库、没有独立 schema；靠表 owner、领域账号、集中 migration 和精确表级授权隔离。
- 禁止新增跨域 SQL、JOIN、外键和内部模块导入。
- Web、Agent、插件、Public REST、MCP 必须复用同一受治理 Capability，不各建一套业务接口。
- 插件平台优先级较高；系统插件与 Agent Skill 分层，不建设第二套 Agent 插件市场。
- 团队知识载体是 Markdown，正文进入 OIS；同 tenant 认证成员均可查看和修改，空间不作为 ACL 边界，每次修改必须留下不可变归因。
- Agent 会话默认个人私有；群聊是独立 channel session，不读取成员私人记忆。
- PBOM 与 GBOP 没有业务关系；遗留 PBOM→GBOP 匹配模型是错误模型，不得 Capability 化。
- EBOM 产品称谓统一改为 PBOM；历史文件名或表名可兼容保留，但新契约使用 PBOM。
- Local Runtime、VisMockup 软件集成、生产设备 Equipment 是三个不同责任边界。VisMockup 不能因为在客户电脑运行就归入生产设备。
- 不向 GitLab 推送。除非用户再次明确要求，不 push、不部署；若以后要求推送，只核对并使用指定 Gitea 测试分支。
- 不接触生产数据库。浏览器当前环境曾连接生产库，测试必须保持离线或使用用户明确授权的测试 OceanBase。
- 用户不喜欢“做一点就停”；获准实施后应持续推进到真实阻塞，同时持续记录审计材料。

## 2. 目标架构

架构是“六层技术边界 × 五个纵向产品域 × 两个横切面”：

| 技术层 | 责任 |
| --- | --- |
| 入口体验层 | Web、飞书、Public API、MCP、插件 UI Slot |
| 应用编排层 | Use Case、BFF、Agent Skill、跨域流程编排 |
| 能力契约层 | Capability Gateway、版本、Schema、鉴权、确认、审计、证据、限流 |
| 领域服务层 | Base/Craft/Simulation/Agent/Equipment 的业务逻辑与 Repository |
| 集成协作层 | Event、Outbox、Projection、Saga、Plugin Runtime |
| 基础设施层 | OceanBase、OIS、Queue、Local Runtime 和外部软件适配 |

五域是 Base、Craft、Simulation、Agent、Equipment。横切面是安全治理与插件扩展。

关键公式：

```text
Agent = LLM + 按需上下文 + 受控工具 + Harness循环 + Runtime持久状态
```

Capability 是跨域主动调用的唯一稳定业务契约，不是 API 路由别名、微服务同义词、数据库 CRUD 或 MCP Tool。API、MCP、Agent Tool 和插件 SDK 都只是 Capability 的适配面。

## 3. 当前工作区与 Git 状态

| 用途 | 路径 | 分支/提交 | 状态 |
| --- | --- | --- | --- |
| 后端主检出 | `E:\Projects\ai00_v3\workmanship-backend` | `deploy` / `b0473c3` | 不要直接修改 |
| Capability 功能工作树 | `E:\Projects\ai00_v3\.worktrees\capability-wave-a` | `codex/capability-wave-a` / `e0044ce` | 当前权威后端增量，干净 |
| Web 主检出 | `E:\Projects\ai00_v3\workmanship-web` | `deploy` / `aa80a18` | 不要直接修改，干净 |
| Knowledge Web 功能工作树 | `E:\Projects\ai00_v3\.worktrees\knowledge-open-web` | `codex/knowledge-open-collaboration-web` / `a71a401` | ACL 死入口修正，干净，待集成 |
| Agent Runtime | `E:\Projects\ai00_v3\services\agent-runtime` | 不在 Git 仓库 | Phase 57 外部增量，靠 Hash 对账 |
| MCP Gateway | `E:\Projects\ai00_v3\services\mcp-gateway` | 不在 Git 仓库 | Phase 57 外部增量，靠 Hash 对账 |

两个功能分支都没有 upstream。远端名称为 `devteam`，本文故意不记录 URL 或凭据。

Capability 分支最近关键提交：

| 提交 | 内容 |
| --- | --- |
| `e0044ce` | 四项不完善 VPPS 规则降为候选待办；拆分 Task 13 |
| `d7f331e` | 记录 Knowledge Web ACL 退役并删除过时跨仓库正向断言 |
| `4566df5` | Tasks 6–14 完成度审计与 Task 13 输入模板 |
| `8455b4d` | Knowledge 同 tenant 开放协作，正常路径停止 ACL SQL |
| `0c5b521` | 清理 Python/pytest deprecation |
| `879890d` | pytest 默认离线，避免继承桌面数据库配置 |
| `9a676bc` | 首批 Web/Agent/API/MCP 受治理消费者迁移 |
| `6ef2d39` | Craft Validation Policy 技术框架与候选盘点 |
| `d1fab14` | System/Semantic/Base 共享 Capability |
| `983a40c` | Ontology release publish/diff/activate |
| `6743839` | Ontology proposal/review 治理 |
| `f5cb13c` | Ontology concept resolve/get/mapping assess |
| `a970d06` | Ontology 不可变 release 存储 |
| `1c5372c` | Knowledge revision/context Capability |

## 4. 已完成的 Capability 实施范围

- Kernel 契约：输入输出 Schema、标准错误、风险/确认、证据、审计、插件开放标志和服务端 Catalog 过滤。
- 官方领域 Provider：Base 不直接导入 Craft 实现；第三方插件不能注入 Python provider。
- Craft 读取：BOP version get/list、execution structure get/preview、linked parts、work package、version compare、PBOM snapshot/part reads、活动 GBOP reads。
- Knowledge：space/document/revision/context、OIS Hash、乐观并发、不可变归因、同 tenant 开放协作。
- Ontology：不可变 release 存储、concept resolve/get、mapping assess、change proposal/review、release publish/search/get/diff/activate。
- System：search、activity、job、identity、lineage、change impact、semantic context、project search 等受治理共享能力。
- 消费者：首批 Web BOP 读取、Agent Knowledge/BOP/Ontology、Agent Runtime Catalog、MCP Gateway Catalog/Result/evidence。
- 插件边界：新增能力默认 `plugin_callable=false`；第三方插件只能调用显式开放且通过安装授权交集的能力。

“代码与离线测试完成”不等于生产验收完成。旧领域 router 仍存在，不能因为已有 Capability 就直接删除。

## 5. Phase 63 对 Task 13 的最终决策

四项现有 VPPS 检查不完善，全部降为 P2 候选规则待办：

- `vpps.master_data`
- `vpps.parent`
- `vpps.hierarchy_prefix`
- `vpps.fastener_main_part`

当前不要求业务 Owner 填写，不把它们包装成权威规则，也不让它们阻塞安全写能力。

暂缓且保持未注册：

- `craft.bop.version.validate`
- `craft.bop.version.publish`
- `craft.pbom.vpps.validate`

下一批允许实施：

- `craft.bop.draft.change.preview`
- `craft.bop.draft.change.apply`
- `craft.bop.version.create`
- `craft.bop.version.archive`
- `craft.bop.import.preview`

不能走两个捷径：不能用不完善规则阻断发布，也不能在没有成熟发布 Policy 时实现“无校验发布”。

## 6. 下一模型的建议起点

用户尚未在本轮明确要求立即继续编码。若用户说“继续/执行”，按以下顺序持续推进：

1. 在现有 Capability 工作树中写一份 Task 13A 实施计划；不要创建第三个后端工作树。
2. 先审计 `_bop/entries.py`、`versions.py`、`fork.py`、`lifecycle.py`、`staging.py` 和现有 Repository，提炼领域命令，不把旧 router 原样包装成 Capability。
3. 用 TDD 先写 `backend/tests/test_craft_write_capabilities.py`，明确观察 RED。
4. 先实现 `draft.change.preview/apply`：类型化命令、无副作用 preview、服务端 preview GID/Hash、过期时间、expected revision、幂等键、一次性确认、单事务、revision 原子递增、before/after Hash 和审计。
5. 再实现 `version.create`：来源只能是 `empty|bop_version|template|import_preview`；不要另建 clone Capability。
6. 实现 `version.archive`：非破坏性、内容 Hash 和引用保持不变；不要提供物理删除。
7. 最后实现 `import.preview`：解析与校验无副作用；当前不提供 `import.apply`，应用走受治理 create/change 能力。
8. 更新 `plugins/craft/craft_backend/capabilities/__init__.py`、官方 provider、`backend/capabilities/agreed_catalog.py`、消费者矩阵和审计记录。
9. 聚焦测试通过后，执行 OceanBase 静态兼容、领域边界、Kernel、Catalog 和完整离线回归；只提交本地分支。

不要在这一批实现 validate、publish、VPPS waiver、任意 JSON Patch、SQL、字段路径 patch、物理删除或模糊 `command.execute`。

## 7. Capability 不变量

- 一个 Capability 只承诺一个稳定业务结果；稳定读写能力才治理，不追求所有内部函数 Capability 化。
- 语义归领域，信封治理归 Base；每项只有一个 owner。
- Web、Agent、插件、API、MCP 是平等消费者。
- 输入身份、tenant、权限、插件身份必须来自可信 `CapabilityContext`，不能让客户端覆盖。
- 写能力必须声明 risk、confirmation、idempotency、副作用、失败语义和审计证据。
- 跨域返回稳定 refs、版本、Hash、证据或有界摘要，不返回数据库行。
- 插件提供的新能力只有在经过 owner、Schema、安全和隔离 Runtime 审核后，才可能成为新 Capability；Web 插件不能成为后端权威 provider。
- Skill 只描述如何组合能力，不承载正式业务逻辑、规则或新权限。

## 8. OceanBase 与测试安全

正式目标是 OceanBase 4.3.5+、MySQL 模式、严格 SQL。必须遵守：

- 新 DDL 只进 `backend/db/migrations`；运行时无 DDL。
- migration 必须可重放；不依赖 DDL 事务回滚。
- 禁止 `::type`、`ILIKE`、`JSONB`、`ON CONFLICT`、`RETURNING`、`SERIAL`、`NULLS FIRST/LAST`。
- TEXT/BLOB 不得有任何 DEFAULT，包括 `DEFAULT NULL`。
- 不使用 `CREATE SCHEMA`；单库内按表 owner 和账号隔离。
- 新表要登记 owner，并重新生成表级 GRANT/REVOKE。
- 不连接真实数据库，除非用户明确授权测试租户、凭据和写入范围。

后端测试必须使用工作树虚拟环境：

```powershell
.\.venv\Scripts\python.exe -m pytest <tests> -q -p no:cacheprovider
```

`backend/tests/conftest.py` 默认设置 `AI00_PYTEST_OFFLINE=1` 并清除领域 DB URL。只有真实数据库验收被明确授权时才可设置 `AI00_ALLOW_LIVE_DB_TESTS=1`。

系统 Python 没有 pytest。当前 Windows 沙箱还存在 pytest 临时目录 ACL 问题：完整套件可能出现 12 个 `tmp_path` fixture setup error；不要把它误报成产品断言失败。`E:\Projects\ai00_v3\.pytest-basetemp-phase60-20260806` 是本轮 pytest 生成但因 ACL 无法删除的临时目录，不属于项目或 Git。

## 9. 最近验证证据与复跑入口

交接日新鲜证据（2026-08-07）：

- Tasks 6–12 + Task 14 聚合后端契约：153 passed in 5.23s。
- Knowledge Web：核心 123/123，web-only defaults/docs/entrypoints/fixture paths/runtime resolution 和开放协作契约全部通过。
- Agent Runtime：TypeScript build 通过，3 tests / 0 fail。
- MCP Gateway：TypeScript build 通过，2 tests / 0 fail。

历史证据：

- Phase 60 完整后端离线套件：`579 passed in 13.57s`，0 warning。
- Phase 61 Tasks 6–12 + Task 14 聚合：`153 passed in 5.23s`。
- Agent Runtime：3 项通过；MCP Gateway：2 项通过。
- Phase 62 Web：核心 `123/123`，全部静态守卫和 Knowledge 新契约通过。

外部 TypeScript 对账 Hash：

| 文件 | SHA-256 |
| --- | --- |
| `services/agent-runtime/src/capability-client.ts` | `BD638E46C1CC841FF014738CED4AC21FBDD8BE75983C8BDC147E9B0A11D347F7` |
| `services/agent-runtime/test/runtime-policy.test.ts` | `120F5A89D9AAC793C604D17A7DBB88C25BFB2EA2412B91F1BF77824E281E5A66` |
| `services/mcp-gateway/src/capability-client.ts` | `DDD966A14B1D2CC4D24CC14E6A612497084D17EFC8352B373D5427ECFCE2D91D` |
| `services/mcp-gateway/test/schema.test.ts` | `4F0C0E18FECF2EBDA959A05DAFD931C9B370503B5E2A58D0091E093F6DDB7341` |

上述是历史阶段证据；新模型在声称新状态前必须执行新鲜验证。

## 10. 当前未完成与真实外部门槛

- `CRAFT-004/005` 安全写入、创建、归档尚未实现。
- Knowledge Web ACL 修正在独立分支，尚未集成到 `deploy` 或同步构建产物。
- Knowledge ACL helper、历史 ACL 数据和旧表尚未盘点或删除；不得直接做破坏性 DDL。
- 真实 OceanBase migration、OIS snapshot/Hash、JWT 权限、Public API、MCP 和插件全生命周期 E2E 未执行。
- Agent 仍有内部 REST 旁路待按 `API_CAPABILITY_AUDIT.md` 逐项治理。
- Simulation、Rule、Equipment 的完整 Capability 目录仍待后续逐项审议。
- `services/*` 不在 Git 仓库，后续必须先决定版本控制和发布归属，不能靠长期 Hash 手工管理。
- 根目录 `CAPABILITY_CROSS_DOMAIN_SPEC.md` 的“当前注册规模”等快照可能早于 Phase 45–63；其设计原则仍有效，实现状态以当前分支代码、Catalog 测试和后期审计为准。

## 11. 交接时禁止执行的动作

- 不要 push 到 GitLab，也不要猜测远端用途。
- 不要 merge/cherry-pick 到两个 `deploy` 分支，除非用户明确授权。
- 不要启动部署、重启生产服务或使用浏览器验证生产数据。
- 不要设置 `AI00_ALLOW_LIVE_DB_TESTS=1`。
- 不要删除旧 router、ACL 表、历史迁移或兼容 ID。
- 不要把 Phase 63 暂缓的校验/发布 Capability 加回 Catalog。
- 不要因为插件声明权限就把 Craft/Ontology/System 新能力设为 `plugin_callable=true`。

## 12. 给新模型的最短继续指令

```text
先阅读 E:\Projects\ai00_v3\.worktrees\capability-wave-a\docs\audit\MODEL_HANDOFF_2026-08-07.md。
继续时只在现有 capability-wave-a 工作树实施 Phase 63 解锁的 CRAFT-004/005；先写修订计划并按 TDD 执行。
不要实现 validate/publish/VPPS，不连接数据库，不 push，不部署，不修改 deploy 分支。
全过程维护审计记录并持续推进到真实阻塞。
```
