# Capability V2 原子业务能力治理深度审计（test 基线）

- **审计日期：** 2026-08-21
- **规范版本：** 《原子业务能力开发治理规范 V2.1》（本地文件：`docs/governance/atomic-capability-spec-v2.md`；V1 飞书 wiki `UA1pwx3iZisRCMkmWgTcsI4MnKf`）
- **结论：** **不可发布（BLOCKED）**
- **审计方式：** 静态审计、只读命令与聚焦测试；未修改业务代码、Git 历史、分支、远端或数据库。
- **后端基线：** `E:\Projects\ai00_v3\.worktrees\capability-v2-implementation`，`test...devteam/test`，`697aac1810f0cf3f99dee887557c081eabfc01ca`
- **前端基线：** `E:\Projects\ai00\workmanship-web`，`test...devteam/test`，`10948bb597671c4251fe4aac237753012589310d`
- **工作树状态：** 两个工作树均有既存未跟踪产物；未清理、改写或纳入本次结论。后端包括 `.runtime/`、`.superpowers/` 等，前端包括 `dist-production/`、`dist-test-governance/`。

## 1. 审计依据与范围

### 1.1 上位需求

| 文档 | Wiki token | 本次用于判定的要求 |
|---|---|---|
| 《总装业务智能化四层治理指南》 | `Kmhowf4BiimR5mkWRZqc12Nvnve` | 业务全景 → 编排原语（Task Tool、Capability Pack、Skill、Workflow）→ 受治理 Capability → 技术落地；UI、插件、Agent 经受控入口；真实消费者、测试与业务观测闭环。 |
| 《总装柔性智能基座协作开发规范 V1.0》 | `My2FwMxp9i82QkkvhqkcmcFknwe` | 领域路径、表、迁移、CODEOWNERS 所有权；跨域统一 Gateway；禁止跨域 SQL、共享 ORM、内部 import、临时 REST 与复制连接；单库仍须保持逻辑所有权。 |
| 《原子业务能力开发治理规范 V2.1》 | 本地 `docs/governance/atomic-capability-spec-v2.md`（V1 飞书 `UA1pwx3iZisRCMkmWgTcsI4MnKf`） | Capability 原子性、版本/GID、登记字段（七个字段的结构约束）、Provider/Gateway/事务/幂等/审计、消费者边界、真实 Registry 快照、测试证据与服务端发布门禁；**V2/V2.1 新增：** Task Tool/Pack/Skill/Workflow 治理、全景节点台账与度量、遗留 UI 迁移策略与 BFF 边界、Release Gate 原子性 blocking 条件。 |

### 1.2 范围和排除项

本报告评审指定 test 基线的 Capability V2 实现、其 Web/插件/Agent 相关静态消费者、官方 Provider/Catalog/Registry、领域边界与治理发布机制。没有启动业务服务、访问生产 API、迁移数据库或验证远端分支保护、CODEOWNERS 平台配置和真实生产部署。

`满足` 仅表示在指定静态/测试证据范围内满足；`未验证` 不代表通过。历史、离线或未绑定本基线的报告不得作为本次运行时通过证据。

## 2. 对规范本身的评审（V1 → V2 → V2.1 升级）

### 2.1 结论

《原子业务能力开发治理规范 V2.1》完整继承 V1.0 全部约束，并在 V2.0 基础上补充字段语义、权限和迁移口径，现可作为覆盖两份上位文档核心要求的**完整审计基线**。V1 遗留的规范缺口已在 V2/V2.1 中补齐。

该规范可作为 **Capability 核心治理的严格审计基线**，没有发现会使其无法执行的内在矛盾。它对一个主要业务效果、单一领域 owner/数据边界/授权意图/审计事件、Provider 与 Gateway、事务与幂等、跨域禁止路径、插件与 Agent 边界、真实 Registry 快照、证据可追溯和服务端重新读取发布证据均有明确且可审计的约束。

V1.0 遗留的规范缺口已在 V2.0/V2.1 中补齐（第三节字段强化、第十八至二十节新增及 V2.1 澄清）。以下评审矩阵基于 V2.1 进行。

### 2.2 规范评审矩阵（基于 V2.1）

| 维度 | V1 判定 | V2 判定 | 说明 |
|---|---|---|---|
| 原子性、授权、失败/重试、审计边界 | 满足 | 满足 | 规范对”一个主要业务效果”及可独立授权、失败、重试、消费者使用时应拆分的规则清晰。 |
| Provider/Gateway/领域数据边界 | 满足 | 满足 | 明确要求正式 Gateway、领域仓储或数据端口，禁止跨域 SQL、内部 ORM/import 和临时 REST。 |
| 版本、GID、不可变快照、测试/发布证据 | 满足 | 满足（强化） | V2 在字段层级补充了 GID 必须同时出现在 Catalog 投影层和持久化存储的约束，V2.1 明确了新发布/stable 与历史 deprecated/retired descriptor 的门禁范围。 |
| Plugin/Agent 安全边界 | 满足 | 满足 | 要求 SDK Mount/Gateway，禁止 REST/数据库/Cookie/Electron IPC/内部模块绕过。 |
| 七个正式登记字段结构约束 | 规范缺口（已提及但无结构约束） | **满足（V2/V2.1）** | 第三节明确了 error_schema、transaction_policy、consumer_refs、provider_ref、api_refs、test_refs、capability_version_gid 的 JSON Schema 约束及层级要求，V2.1 补充了 error_schema 与现有 domain_errors 的字段映射。 |
| 四层编排原语契约 | 规范缺口 | **满足（V2/V2.1）** | 第十八节规定 Task Tool、Pack、Skill、Workflow 骨架的登记字段、版本规则、权限边界和门禁要求；V2.1 增加 Schema 适配边界。 |
| 业务全景与结果度量 | 规范缺口 | **满足（V2 新增）** | 第十九节规定全景节点台账字段、绿黄红状态定义、八条完成标准和生产可观测要求。 |
| Web 渐进迁移与 BFF 边界 | 规范缺口 | **满足（V2/V2.1）** | 第二十节规定遗留路由合规条件、新代码禁止规则、BFF 允许范围和退役验证标准；V2.1 进一步澄清直接 REST、截止日期和 BFF 分母；Release Gate 追加原子性 blocking 条件。 |
| Device 域与 Local Runtime 关系 | 部分满足 | 部分满足 | 规范可约束 Capability 边界，但未独立定义离线部署验收，仍需依赖 Device 域运行证据补充。 |

V2.1 已覆盖两份上位文档的核心审计要求，可作为完整发布基线。以下代码审计结论依据 V2.1 执行，新增 Finding N-01a、N-01b、N-02 至 N-04。

## 3. 总体审计结论

Capability V2 具备受控 Provider 加载、不可变 Catalog 版本、领域 owner/CODEOWNERS 静态治理、跨域 Gateway 抽象、事件/Outbox/Inbox 接口，以及 test-governance 的快照与 fail-closed 发布门禁设计。这些是可复用的积极基础。

但当前 test 基线存在直接违反 V2.1 规范（含 V1 核心条款 + V2/V2.1 新增条款）的遗留实现，且正式 Release Gate 当前不通过。因此不得发布。Finding 共 **10 项**，分级如下：

- **7 项 Blocking（必须在发布前消除）：** B-01、B-02、B-03、B-04、B-05、N-01a、N-04
- **3 项 P1（发布后第一迭代内完成）：** N-01b、N-02、N-03

## 4. 关键 Finding

### B-01：`craft.ebom.change.apply` 不是原子业务能力

- **严重级别：** Blocking
- **依据：** 原子规范要求一个 Capability 只有一个主要业务效果；可分别授权、失败、重试或由不同消费者使用的动作必须拆分。
- **证据：** `plugins/craft/craft_backend/capabilities/ebom_change.py:14-23` 将以下操作注册到同一写能力：
  - `snapshot.delete`、`snapshot.patch`、`snapshot.status.patch`、`snapshot.vpps_stats.patch`；
  - `part.add`、`part.add_batch`、`part.update`、`part.delete`。
- **实现细节：** 同文件 `:78-197` 为各操作执行不同 SQL 写入、资源检查和提交；`:200-210` 将其统一注册为 `craft.ebom.change.apply`，仅使用 `craft.write` 权限和单一 `confirmation="user"`。
- **影响：** 删除 PBOM 快照、修改状态、记录 VPPS 统计、增加/批量增加/更新/删除零件具有不同业务效果、影响范围和重试/审计语义。一个宽泛权限无法支持最小授权，单一审计事件也无法解释真实业务动作。
- **最小整改方向：** 按业务效果拆成如 `craft.pbom.version.delete`、`craft.pbom.version.update`、`craft.pbom.version.status.update`、`craft.pbom.part.create`、`craft.pbom.part.batch_create`、`craft.pbom.part.update`、`craft.pbom.part.delete`；为每项建立独立 schema、权限、幂等策略、事务/并发与审计事件。保留遗留适配器只能作为临时 Facade，并须有明确退役期限且不得伪装为单一原子 Capability。
- **复验条件：** Descriptor、Provider、Consumer 和测试均按拆分后的 capability/version 绑定；不存在通过 `operation` 再分派多个独立业务写效果的 facade。

### B-02：Knowledge 与 Project Management 已实现多业务效果的合并 Capability

- **严重级别：** Blocking
- **依据：** 同 B-01；Catalog 的闭合 schema 不能替代原子业务效果边界。
- **证据（Knowledge）：**
  - `plugins/knowledge/knowledge_backend/capabilities/reviewed.py:71-103` 定义：`knowledge.entry.change.apply` 包含 create/update/delete，`knowledge.hub.change.apply` 同时包含 folder 和 item 的 create/update/delete，`knowledge.hub.read` 同时包含 folder list、item list/get/history；
  - `plugins/knowledge/knowledge_backend/application/outcomes.py:17-42` 按 operation 分派至不同 repository 动作；
  - `plugins/knowledge/knowledge_backend/api/knowledge_hub_legacy.py:79-154` 将旧 API 操作映射到这些合并 Capability。
- **证据（Project Management）：** `plugins/project_management/project_management_backend/application/service.py:117-159` 的 `_OPERATIONS` 表显示一个 Capability 会承载多个独立动作。例如：
  - `project.list.change.apply`：replace/delete item、create/update/delete/retarget list；
  - `project.approval.change.apply`：create/start/approve/reject/withdraw/scope upgrade；
  - `project.project.change.apply`：项目和车型的 create/update/delete；
  - `project.task.change.apply`：task 与 dependency 的 create/update/delete。
  同时 `plugins/project_management/tests/test_project_capabilities.py:79-93` 明确测试“consolidated ... operation envelope”。
- **范围：** Catalog 审计统计有 **34** 个 stable descriptor 使用 `operation + arguments`；并非每一项均已逐条判定为违规，但上述样本已经证明该模式承载多个独立业务效果。
- **影响：** 状态转移、审批决定、创建/删除和不同资源的动作被压缩为单一 capability/version、单一策略与审计名义，不满足最小授权、可追溯性和精确 consumer 契约。
- **最小整改方向：** 以操作语义而不是实体大类拆分 descriptor；尤其先拆审批决定、删除、状态转移、批处理与跨资源动作。若某个保留的参数化能力确为一个业务效果，需提供每种 operation 的授权、失败、幂等、事务、审计和消费者无法独立划分的证据，并由 owner 批准。
- **复验条件：** Catalog audit 和 Release Gate 新增“多 operation 语义原子性”规则；对所有 34 项输出显式 disposition（拆分、退役或有证据的例外）。

### B-03：Web/插件消费者绕过 Capability Gateway 调用遗留 REST

- **严重级别：** Blocking
- **依据：** 原子规范及协作规范要求 UI、插件、Agent 经 SDK Mount/Gateway 调用已声明 Capability；禁止临时 REST 绕过边界。
- **证据：** 前端 test 基线中至少有以下明确调用：
  - `packages/craft-plugin/web/ebom/ebom.js:268,286-350,588,761,790,804,1389-1443,1569,1631-1773,1904` 调用 `/api/projects`、`/api/ebom/*`、`/api/vpps-operations/*`、`/api/craft_lib/*`；
  - `packages/craft-plugin/web/pbom_check/pbom_check.js:86,140,211-212,303-342,538-566,728-751` 同样直连 `/api/ebom`、`/api/vpps-operations`、`/api/craft_lib`；
  - `packages/craft-plugin/web/project/project.js:173-403` 直连 `/api/projects/*`；
  - `plugins/craft/craft_backend/routers/ebom.py` 的 Router 前缀为 `/api/ebom`。
- **数量证据：** 用 `backend.capability_v2.consumer_routes.scan_web_routes()` 对前端 `packages`/`web` 源目录扫描：默认 legacy prefix 得 **392** 条 legacy 字面量、3 条 capability、6 条 allowlist；将遗漏的 `/api/ebom` 加入 prefix 后为 **433** 条 legacy 字面量。**注：这是静态路由字面量出现次数，同一路由可在多个文件、多处重复引用；可行动问题应按唯一 `(route_path, method, owner_module, migration_target)` 四元组归一化后统计，整改也应按路由族分配，不应逐字面量派工。** 即便如此，433 条 legacy 字面量中至少覆盖数十条独立路由路径，足以证明路径没有收敛，结论不变。
- **影响：** 真实 Web 消费者可跳过统一 Capability 契约、版本、授权、幂等、审计与弃用治理；`/api/ebom` 仍让 B-01 的非原子 facade 暴露给前端。
- **最小整改方向：** 以 Capability Gateway/BFF 投影逐步替换遗留客户端调用；为每条遗留路由建立 owner、迁移目标、截止日期、允许消费者和 410 退役条件。新 UI/插件入口不得增加旧 REST 调用。
- **复验条件：** 源目录扫描为零未授权 legacy 路由，或仅剩明示、时间受限、审计批准的 allowlist；真实浏览器/插件 E2E 覆盖迁移后的能力调用。

### B-04：Release Gate 的 Web consumer 检查既有漏检又受构建产物污染

- **严重级别：** Blocking（门禁证据不足）；同时是治理实现缺陷。
- **依据：** 原子规范要求治理结论来自真实、完整、可追溯证据；不能因扫描盲区而把绕过判为通过。
- **证据：**
  - `backend/capability_v2/consumer_routes.py:73` 仅跳过名为 `dist` 的目录；前端 test 工作树的未跟踪构建目录为 `dist-production/`、`dist-test-governance/`，不在跳过名单中；
  - `consumer_routes.py:142-151` 只把配置的 legacy prefix 识别为 legacy；当前 `backend/governance/capability_v2_completion.json:46-50` 的 allowlist 不包含 `/api/ebom`，而 `/api/ebom` 已在真实消费者中使用；
  - 针对整个前端根目录的当前 Release Gate 报告为 `passed: false`，失败项为 `web_consumer_bypasses:1176` 和 `web_route_inventory_drift:1`；1176 包含未跟踪构建产物，不能用作源代码问题的精确数量；
  - `backend/capability_v2/release_gate.py:17-23` 仅检查 completion、Web bypass、open arguments 与 default-all exposure，并不将 `generic_operation_count` 纳入放行条件。
- **影响：** 当前 Gate 正确地没有放行，但其计数不具有可行动的源代码精度，并且默认配置遗漏 `/api/ebom`，可能在构建产物被排除后低估真正绕过。
- **最小整改方向：** 扫描器按构建目录模式/配置排除（至少 `dist-*`），只扫描版本控制的指定源根；将所有受治理 legacy API prefix（包括 `/api/ebom`）纳入失败规则；将原子性审计（而不仅是 arguments 是否 closed）纳入 Gate。
- **复验条件：** 可复现的 source-only inventory 与 Gate inventory 一致；构建产物不会影响计数；遗漏的 legacy prefix 有测试；Gate 能因 B-01/B-02 类合并语义阻止发布。

**B-04 V2 追加子项：** V2 第二十节第 20.5 条要求 Release Gate **MUST** 将 `generic_operation_count > 0 and not justified` 纳入 blocking 条件。当前 `backend/capability_v2/release_gate.py:17-23` 不包含此检查，属于门禁实现未对齐 V2 规范的独立 blocking 子项（V2 新要求）。

### B-05：当前基线缺少可验证的真实发布证据

- **严重级别：** Blocking（发布阻塞，不一定是代码实现缺陷）
- **依据：** 原子规范要求治理扫描使用实际官方 Registry 快照；测试证据绑定 capability version GID、snapshot GID、code revision、test-run GID、结果 hash；发布门禁须服务端重新读取权威证据，不接受自报状态。
- **说明：** 本项 Finding 不断言代码存在实现错误，而是指在对 `697aac…` 提交进行独立可验证评估时，缺乏可追溯的权威运行证据链；持有运行环境访问权限的团队通过受控 CI/CD 执行所需步骤即可消除本项阻塞。
- **证据：**
  - 已有离线 acceptance 文件 `.runtime/capability-v2-acceptance-after-continuous-final.json` 生成于 `2026-08-20`，绑定旧提交 `e03db08de9a95ff0429eda445d659c7db1d1fcea`，而不是本审计基线；`mode` 为 `offline`，`runtime_evidence_hash` 为 `null`，且 `agent`、`backend_gateway`、`local_runtime`、`mcp`、`plugin` 都是 `not_run`；尽管文件 `status: passed`，不能作为本基线真实运行通过证据；
  - `.runtime/capability-governance-acceptance-final.json` 为 unit/test-governance 演练，标明 `execution_mode: unit` 与 profile `test-governance`；它验证治理扩展机制而非正式生产 Registry/消费者运行；
  - `backend/capability_v2/bootstrap.py:75-110` 显示正式 registry 与 `test-governance` 扩展分离；test profile 仅在显式 `AI00_DEPLOYMENT_PROFILE=test-governance` 时装入；
  - `backend/capability_governance_test/service.py:986-1086` 的发布证据读取设计为服务端 authority port、完整字段和 pinned snapshot 校验，缺失则 fail-closed；这是正确设计，但当前审计未取得对 `697aac…` 的权威 release-evidence 记录；
  - `backend/capability_governance_test/store.py:188-226,555-585` 支持 SQL 持久化 snapshot、code revision、catalog release、version GID 与 hash，但源码存在不等于当前发布环境已执行。
- **影响：** 不能证明本次基线的 11 域官方 Registry、Provider 绑定、Web/Plugin/Agent/MCP/Local Runtime 真实调用、测试结果、审批、签名 release report 和部署制品是一致的。
- **最小整改方向：** 在受控环境对当前提交生成并持久化官方 Registry snapshot，运行真实消费者和 E2E，保存 `snapshot_gid/snapshot_hash/code_revision/test_run_gid/result_hash`，并由服务端 release-evidence port 重新读取、签名后再构建生产制品。
- **复验条件：** 所有证据字段等于 `697aac…` 所属构建；组件结果不含 `not_run`/`skipped`；release report 的签名、输入和权威存储可复验。

## 5. V2.1 新增 Finding

### N-01a：Catalog descriptor 缺少七个结构化治理字段（Blocking）

- **严重级别：** Blocking（V2.1 第三节约束）
- **依据：** V2.1 第三节要求以下七个字段 MUST 同时出现在 Registry snapshot entry、Catalog descriptor 可查询投影层和持久化记录。
- **证据：** 对 `docs/capabilities/catalog.v2.json` 的静态统计（333 条 descriptor）显示以下字段全部缺失于已发布 Catalog 可查询层：`capability_version_gid`（333 条）、`error_schema`（333 条）、`transaction_policy`（333 条）、`consumer_refs`（333 条）、`provider_ref`（333 条）、`api_refs`（333 条）、`test_refs`（333 条）。test-governance 的 SQL projection 存储了部分字段，但其为 `test-governance` profile 专属，不等于正式生产 Catalog 投影。
- **影响：** 任何消费者、Agent 或审计工具无法通过正式 Catalog 查询 Provider 绑定、错误契约、事务边界、消费者关系或测试证明，违反 V2.1 规范的可审计性要求。
- **最小整改方向：** 将上述七个字段纳入 Catalog descriptor 的已发布字段；在 `release_gate.py` 中新增字段完整性 blocking 检查；`catalog_audit.py` 增加必填字段缺失统计。
- **复验条件：** 所有 stable descriptor 均含七个字段；Catalog audit 通过；`test_refs` 中无 `result=not_run` 作为发布证据。

### N-01b：`business_effect` / `side_effects` 字段命名与现有实现不一致（P1）

- **严重级别：** P1（V2.1 澄清后产生的映射缺口）
- **依据：** V2.1 第三节明确：`side_effect_level`（枚举）与 `side_effects`（叙述）须分别登记；`business_effect` 须独立于 `description`/`title` 单独填写，不得混用。
- **证据：**
  - 代码中 `CapabilityDescriptorV2` 使用 `side_effect_level: SideEffectLevel`（枚举），无单独的 `side_effects` 叙述字段；当前 Catalog 中无此字段；
  - `business_effect` 在 test-governance 的 SQL projection 中存在，但在正式 Catalog descriptor 中对应的是 `description`，二者语义不完全等价；
  - V2.1 规范将这两对字段拆开定义后，现有实现存在命名/语义映射盲区，若不明确绑定关系，整改人员可能产生歧义。
- **影响：** 整改 N-01a 时，若未同时处理命名不一致，可能出现字段"名义上填写但语义不符"的情况，导致后续审计无法可靠判断合规性。
- **最小整改方向：** 在 `CapabilityDescriptorV2` 或 Catalog schema 中明确：① `side_effect_level` = 枚举分类，② `side_effects` = 叙述型字段（说明实际写入表/事件/外部调用）；`business_effect` 不等于 `description`，须独立维护。可用 SHOULD 等级先补充，P0 整改 N-01a 时同步落地。
- **复验条件：** Catalog schema 包含 `side_effect_level` 和 `side_effects` 两个独立字段，且字段说明区分二者语义；`business_effect` 有独立字段并在 Catalog 投影中可查询。

### N-02：无 Task Tool、Capability Pack、Skill 治理登记（V2 P1）

- **严重级别：** P1（V2 第十八节新增要求）
- **依据：** V2 第十八节要求 Task Tool、Pack、Skill 和 Workflow 骨架均需有唯一 ID、owner、版本、`consumed_capabilities`（绑定 stable Capability ID + major 版本）、lifecycle 和 Gateway/SDK 路由。
- **证据：** 静态扫描未发现 `task_tool_registry`、`capability_pack_registry`、`skill_registry` 或等价治理登记文件；代码库中无符合 V2 要求的 Task Tool/Pack/Skill 定义。现有编排（如 `/api/flows/`）属于 Agent runtime 代理路由，不等于已登记的 Task Tool 契约。
- **影响：** 插件和 Agent 目前直接调用 Capability 或遗留 REST，缺少中间的任务级抽象层。底层 Capability 升级时插件需全量适配，不符合四层指南"由 Task Tool 和兼容映射吸收变化"的设计目标。
- **最小整改方向：** 为高频稳定调用组合创建 Task Tool 登记（至少覆盖工艺规划和 PBOM 相关的核心操作）；为 Agent 的工具投影建立 Capability Pack；发布门禁增加 Task Tool 消费者绑定检查。
- **复验条件：** 至少 3 个 Task Tool 完成 V2 格式登记；Gate 新增 Task Tool `consumed_capabilities` 为 stable 的检查。

### N-03：无业务全景节点台账（V2 P1）

- **严重级别：** P1（V2 第十九节新增要求）
- **依据：** V2 第十九节要求每个全景业务节点在治理台账中维护 `node_id`、`business_objective`、`owner`、`mapped_capabilities`、`status`（基于代码和运行证据的绿黄红）、`quality_metrics`、`efficiency_metrics` 等字段。
- **证据：** 静态扫描未发现 `business_panorama.json`、`node_ledger.json` 或等价台账文件；`docs/governance/` 目录下无全景节点状态记录。现有的 capability coverage review 只记录 Capability 覆盖情况，不记录业务节点的绿黄红状态、可量化指标和生产可观测性。
- **影响：** 无法判断哪些业务节点已完全完成（绿色）、哪些仍在收敛（黄色）、哪些仍依赖人工（红色）；发布决策缺少业务维度的验收证据；无法衡量 Capability V2 对质量/效率/返工的改善效果。
- **最小整改方向：** 建立 `docs/governance/business_panorama_ledger.json`，先对已有 UI 覆盖的核心业务节点标注状态和 `mapped_capabilities`；治理扫描增加"节点状态未验证"的警告项。
- **复验条件：** 台账文件存在且有 ≥ 5 个节点的记录；每个 `green` 节点有对应 stable Capability 和生产观测指标。

### N-04：无 legacy_route_inventory 台账（V2 Blocking）

- **严重级别：** Blocking（V2 第二十节第 20.1 条新增要求）
- **依据：** V2 第二十节要求遗留路由必须在 `legacy_route_inventory` 中登记，含 `owner`、`migration_target_capability`、`migration_deadline`（绝对日期）；否则视为不合规路由，属于 blocking。
- **证据：** 静态扫描未发现 `legacy_route_inventory.json` 文件。源目录扫描显示至少 **392 条** legacy 路由字面量（含 `/api/ebom` 后为 433 条）未经过正式台账登记，无 owner、无迁移目标、无截止日期（注：这是字面量出现次数，唯一路由路径数更少，但台账为零的事实不受此影响）。同时 `bff_route_inventory.json` 亦不存在。这意味着即使某些遗留路由是"有意保留的过渡入口"，也缺乏可审计的合规证据。
- **影响：** 无法区分"有计划迁移的临时路由"与"无人维护的遗留入口"；Release Gate 无法执行 V2 第 20.5 条的逾期路由 blocking 检查；遗留路由治理状态对审计和监管完全不透明。
- **最小整改方向：** 创建 `docs/governance/legacy_route_inventory.json`，为当前静态扫描到的遗留路由**按唯一 `(route_path, method)` 归一化后**逐条登记 `owner`、`migration_target_capability`、`migration_deadline`（不超过 2026-11-21）和 `allowed_consumers`；Release Gate 增加逾期路由 blocking 检查；将优先级最高的 `/api/ebom` 路由标记为关联 B-01 整改。
- **复验条件：** 台账文件存在且包含所有 legacy 路由；无逾期未迁移路由；Gate 的 `legacy_route_inventory` 检查通过。

## 6. 重要但非阻塞的正向证据

| 项目 | 结果 | 边界 |
|---|---|---| | 通过；hash `sha256:914a9bf9e343b23b45e25ecb78b052da321c6b27948c1f551a96a91255d8ce99` | 证明清单未漂移，不证明所有消费者受控。 |
| Catalog release 构建检查 | 通过；`rel_3010694218f96365eda536567f35d198`、333 descriptors | Catalog 可构建，不证明每个 descriptor 原子或有真实运行证据。 |
| 领域所有权/CODEOWNERS 静态一致性 | `Domain change governance check passed` | 不证明远端分支保护、团队成员或真实审批配置。 |
| 跨域 import 静态检查 | `0 reviewed violations, no new dependencies` | 不覆盖动态 import、未登记目录、SQL/HTTP/前端运行路径。 |
| Registry/Provider/Catalog/Gate 初步单测 | 9 passed | 仅为聚焦单测，非端到端/生产证明。 |
| 治理 snapshot / store / evidence / release-gate 设计 | 支持不可变 snapshot、GID、hash、证据 authority、fail-closed | 主实现置于 `backend/capability_governance_test`，需要真实部署和权威存储证据。 |
| 跨域同步/异步示例 | `backend/governance/capability_v2_production_paths.json` 登记 1 条 sync、1 条 async | 仅证明两条示例路径，不能推导全仓库跨域调用已覆盖。 |

## 7. 合同登记、生命周期与治理证据评审

### 7.1 Catalog 与正式登记投影

`docs/capabilities/catalog.v2.json` 的 333 条记录均可见 id、major version、owner、lifecycle、schema、授权、幂等与 catalog release 等字段；当前有 317 stable、16 deprecated。`backend/capability_v2/contracts.py` 也具备 owner、lifecycle、exposure、authorization、idempotency、consistency、confirmation、evidence、audit 和 `domain_errors` 等契约字段。

但产品 Catalog 记录未直接登记以下字段（对应 N-01a/N-01b）：七个结构化治理字段（`capability_version_gid` 等，见 N-01a）；以及 `business_effect`（独立字段，当前以 `description` 代替）、`side_effect_level`（代码中已有枚举，Catalog 投影未导出）、`side_effects`（叙述型，当前无此字段）（见 N-01b）。test-governance 的 SQL projection 可存储其中部分，但不等于正式发布的权威登记层。

**判定：部分满足 / 证据不足（N-01a Blocking，N-01b P1）。**

### 7.2 Lifecycle

存在 lifecycle 枚举和 compatibility 校验，但本次未获得每个 deprecated capability 的消费者迁移、最后支持日期、旧路由/Mount 退役和不可变历史 descriptor 的完整证据。因此 deprecated 生命周期治理为 **未验证**。

### 7.3 Device 与 Local Runtime

官方 manifest 将 `device` 作为正式 domain；`docs/governance/domain-ownership.json` 将 `plugins/device/**`、`local-runtime/**` 和 `backend/domain_ports/local_integration.py` 归为 Device，方向上符合“Device 为领域、Local Runtime 为组件”。但当前没有本基线的 Local Runtime runtime E2E（历史 acceptance 亦为 `not_run`），故部署、离线可用性和真实边界为 **未验证**。

## 8. 消费者与跨域边界评审

| 维度 | 判定 | 证据与限制 |
|---|---|---|
| 官方 Registry 构建 | 静态满足 | `backend/capability_v2/bootstrap.py:75-110` 由 official manifest 和 `DomainProviderLoader` 构造，在锁中完整发布。 |
| 同步跨域 Gateway 抽象 | 静态满足 | `backend/capability_v2/domain_client.py` 保留 identity、correlation、idempotency、resource version 等调用上下文。 |
| 异步 Outbox/Inbox 契约 | 静态满足 | `backend/capability_v2/domain_events.py` 有事件版本、Outbox transaction 与 Inbox deduplication 协议。 |
| 所有跨域调用均受控 | 未验证 | 静态 import 检查通过且有两条生产路径示例，但未证明动态/HTTP/SQL/前端全部覆盖。 |
| Web/插件入口均经 Gateway | 不满足 | B-03。 |
| Agent 均经 SDK Mount/Gateway | 未验证 / 高风险 | Agent 目录存在 `/api/ai` 兼容 Router 和 `httpx` 外部调用（如 `plugins/agent/agent_backend/routers/agent_runtime_proxy_next.py`）；本次未运行真实 Agent 并逐条建立 tool-to-capability 证据。不得据此推断合规。 |
| MCP 均经 Gateway | 未验证 | 未取得实际 MCP consumer/runtime 证据。 |
| Local Runtime 均经 Gateway | 未验证 | 未取得本基线 runtime E2E 证据。 |

## 9. 验证命令与实际结果

以下命令均为只读检查或测试；pytest 临时目录仅在既有未跟踪的后端 `.runtime/` 下。

```text
python backend/scripts/freeze_official_domains.py --check
# passed; sha256:914a9bf9e343b23b45e25ecb78b052da321c6b27948c1f551a96a91255d8ce99

python backend/scripts/build_capability_catalog.py --check
# Catalog release check passed: rel_3010694218f96365eda536567f35d198, 333 descriptors

python backend/scripts/check_domain_change_governance.py --check --frontend-root E:\Projects\ai00\workmanship-web
# Domain change governance check passed

python backend/scripts/check_domain_dependencies.py
# Domain dependency check passed: 0 reviewed violations, no new dependencies

python -m pytest -p no:cacheprovider --basetemp ...\pytest-audit-contracts-pypath \
  backend/tests/test_capability_bootstrap.py \
  backend/tests/test_capability_provider_loading.py \
  backend/tests/test_capability_v2_catalog_audit.py \
  backend/tests/test_capability_v2_release_gate.py -q
# 9 passed in 4.25s
```

进一步的治理聚焦集（store、evidence、release gate、workflow、scanner、production exclusion）结果为 **56 passed, 1 failed**。失败不是断言结果：`test_retired_promotion_placeholders_are_not_public_exposure_findings` 在从主会话工作目录启动时，把相对 `.runtime/promotion-retirement-scan.json` 解析为 `E:\Projects\ai00_v3\.runtime`，而实现要求其处于指定 worktree，故报 `output_path_not_in_repository`。该结果不能当作该用例通过；也不能归因于治理规则本身失败。应在该 worktree 作为进程 cwd 的受控 CI 环境重跑。

Release Gate 对完整前端根目录的实际结果为：

```json
{
  "passed": false,
  "failed": [
    "web_consumer_bypasses:1176",
    "web_route_inventory_drift:1"
  ]
}
```

因此无论计数污染如何处理，当前 Gate 都不允许发布。

## 10. 按优先级的整改建议（基于 V2.1）

### P0：发布前必须完成（7 项 Blocking）

1. 拆分 B-01 的 PBOM/EBOM facade（`craft.ebom.change.apply`），并替换其 `/api/ebom` 调用消费者。
2. 对 34 个 `operation + arguments` stable descriptor 进行原子性 disposition；先拆 Knowledge 与 Project Management 中已证实的 create/update/delete、审批决定、状态转移、跨资源和批处理动作（B-02）。
3. **[N-01a]** 补齐 Catalog descriptor 七个结构化治理字段（`capability_version_gid`、`error_schema`、`transaction_policy`、`consumer_refs`、`provider_ref`、`api_refs`、`test_refs`）至可查询投影层；在 Release Gate 增加字段完整性 blocking 检查。
4. **[N-04]** 创建 `docs/governance/legacy_route_inventory.json`，为所有遗留路由按唯一 `(route_path, method)` 归一化后登记 owner、迁移目标、截止日期和允许消费者；Release Gate 增加逾期路由 blocking 检查（V2.1 第 20.5 条）。
5. 修复 Web inventory 扫描：限制到版本控制源目录，排除 `dist-*`，将 `/api/ebom` 纳入 legacy prefix；Release Gate 增加 `generic_operation_count > 0 and not justified` 的 blocking 条件（B-04 V2.1 子项）。
6. 将 Web/Plugin consumer 迁移到 Gateway/SDK/BFF projection，并收敛到零未批准的遗留 REST 调用（B-03）。
7. 对当前提交生成权威正式 Registry snapshot、真实测试运行、证据 hash 和签名 release report；组件不得 `not_run`（B-05）。服务端必须从权威存储重新加载证据再发布。

### P1：P0 后完成（3 项 P1 Finding，7 项 P1 行动项）

1. **[N-01b]** 在 `CapabilityDescriptorV2` 或 Catalog schema 中明确 `side_effect_level`（枚举）、`side_effects`（叙述）和 `business_effect`（独立于 `description`）三个字段的定义和映射。
2. 将每项 deprecated capability 的迁移指南、最后支持日期、消费者迁移状态、旧入口退役证据纳入 Gate。
3. 扩展跨域扫描与运行验证，覆盖动态 import、跨域 HTTP、SQL、Agent、MCP、Local Runtime 和全部声明的生产路径。
4. 在 CI 的正确 worktree cwd 下修复并重跑 scanner 相关测试。
5. **[N-02]** 为高频稳定操作组合创建 Task Tool 登记（至少 3 个）；为 Agent 工具投影建立 Capability Pack。
6. **[N-03]** 建立 `docs/governance/business_panorama_ledger.json`，为核心业务节点标注绿黄红状态、`mapped_capabilities`、质量/效率指标和可观测性状态。
7. 创建 `docs/governance/bff_route_inventory.json`，登记所有 BFF 路由。

### P2：中长期对齐

1. 为全景业务图所有节点完成台账记录，建立生产可观测性闭环（V2.1 第十九节八条完成标准）。
2. 为 Skill 和 Workflow 骨架建立正式登记；补充上下文工具投影机制。
3. 为所有遗留路由完成 Capability 迁移，清零 `legacy_route_inventory` 中逾期项。

## 11. 发布判定

**不通过。**

本基线共 **10 项 Finding**：7 项 Blocking（B-01～B-05、N-01a、N-04），3 项 P1（N-01b、N-02、N-03）。即使先忽略 Gate 的计数污染，B-01、B-02、B-03、N-01a、N-04 均各自足以阻止依据《原子业务能力开发治理规范 V2.1》发布。

完成 P0 的全部 7 项、在当前提交上重新生成权威运行证据、并由修正后的服务器端 Gate（含 V2.1 新增的原子性 blocking 条件、`legacy_route_inventory` 检查和字段完整性检查）验证通过后，才能进入发布审批。
