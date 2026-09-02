# Capability V2 架构深度审核报告

**日期：** 2026-08-11  
**审核范围：** 全部 7 份设计/计划文档 + worktree 代码实态  
**审核方法：** 文档全文精读 × 代码实际阅读，交叉验证

---

## 总体评价

架构演进方向正确，Gateway 单一执行边界、领域纵切片、可信身份等核心原则一致。但在以下三个维度存在必须处理的问题：**设计层面有 4 处架构级断层**（不解决会导致实施失败）；**代码与设计有 5 处显著背离**（文档看不到，实施时才会暴露）；**实施计划有若干隐性假设和竞争条件**（已在上游设计中埋雷）。

---

## 一、架构级断层（不处理会导致实施失败）

### 1.1 Revision 内核的命运未定，已有实现将成孤岛

**原设计（doc1 §11）**：Revision & Lineage 是跨领域一级服务，有 `revision.*` 能力族，含三方合并内核、语义 Diff、Branch、Commit、Lineage。Task 14 已标记完成。

**新设计（doc5）**：Revision 被拆散进入各域——Craft 用 `craft.pbom.version.*`/`craft.bop.version.*`，Knowledge 用 `knowledge.document.revise/restore/diff`，Ontology 用 `ontology.release.*`。Roadmap 15 个 Plan 中没有独立的 Revision 计划。

**代码实态**（`backend/capability_v2/revision/`）：`RevisionService`、三方合并、`CommitRef`、`LineageEdge`、`BranchApprovalChallenge` 全部已实现，且有完整内容哈希校验。`ontology_releases_next.py` 确实通过 `get_default_revision_service()` 接入。但 **Craft BOP 完全没有接入**——`bop_writes.py` 中的 `revision` 只是 SQL 表的自增列（`WHERE gid=%s AND revision=%s`），不是 `CommitRef`，没有 `Snapshot`，没有语义 Diff。

**断层**：三方合并内核已建成，Ontology 接入，Craft 未接入。新设计又定义了独立的领域内版本模型。这意味着：
- 已建成的三方合并逻辑无法复用给 PBOM/BOP（Plan 07-08 实施时会重复造轮子）
- `system.lineage.get`（属于 Base）的数据来自哪里——Revision 内核还是各域自有版本？
- `system.change_impact.preview` 的跨域影响分析依赖共享的版本图，没有 Revision 内核就无法实现

**必须在 Plan 02 开始前明确**：Revision 内核是继续演进（各域接入）还是战略性退役（各域自建，Revision 代码最终删除）？两种选择都可以，但不能留白——否则 Plan 07 的实施者会自己做决定，产出与 Ontology 已有实现不兼容。

---

### 1.2 Base 的跨域查询能力无数据来源

**新设计 §11.2** Base 拥有：`system.search`、`system.lineage.get`、`system.change_impact.preview`。

这三个能力的语义要求聚合 Craft、Knowledge、Ontology、Digital Model、Project Management 多域数据。但设计禁止 Base 跨域 SQL、JOIN、Repository。

可行路径及其代价：

| 路径 | 问题 |
|---|---|
| DomainCapabilityClient 扇出调用各域 | 高延迟、N 次 Gateway、无法跨域排序/过滤 |
| 各域发布事件，Base 物化读模型 | 需完整事件模式、幂等消费，设计中未提 |
| 外部搜索引擎 | 引入新基础设施，设计未提 |
| `system.search` 降为各域 search 的聚合 facade | 违反设计意图 |

**`system.search` 是 Web 和 Agent 最常用的入口之一**，Plan 02（Base）实施前必须确定其数据机制，否则 Plan 02 无法完成 Provider 实现。

---

### 1.3 并行计划与"不修改同一文件"规则自相矛盾

**Roadmap**：Plans 03、04、05、06 可并行（都只依赖 01、02）。

**但以下文件在每个 Plan 中都要修改**：
- `docs/governance/domain-ownership.json`
- `backend/governance/domain_boundaries.json`
- `.github/CODEOWNERS`
- `backend/scripts/check_domain_dependencies.py`
- `backend/tests/test_domain_independence_v2.py`
- `backend/capability_v2/official_domains.json`（每域完成后需更新 artifact_hash）

**Roadmap 规则第一条**："Do not run two plans that write the same files concurrently"——与"Plans 03-06 可并行"直接矛盾。

`official_domains.json` 的 artifact_hash 是基于该域完成后的代码状态计算的，多人并行修改会产生不可机械解决的 git 冲突。

**建议**：在 Program Rules 中补充："Plans 03-06 的 governance 文件修改必须串行提交；每个 Plan 完成后运行 `freeze_official_domains.py`，由该 Plan 责任人提交，下一个 Plan 从更新后的分支开始。"

---

### 1.4 Factory 绑定校验是功能性空洞

**设计 §13.2**：Factory 明确排除 allocation/reservation。

**设计 §14.2**：`craft.bop.factory_binding.preview/apply`——Craft 在绑定时"调用 Factory Provider 校验"。

Factory 没有资源占用记录，BOP 对物理工位的绑定只能做存在性检查，无法检测冲突（同一工位被 N 个 BOP 同时绑定）。`craft.bop.factory_binding.preview` 实际上等于空操作。

在制造实际场景中，这让 Plan 08 交付的绑定功能没有业务价值——用户无法知道自己的 BOP 是否与其他 BOP 发生了物理资源冲突。

**建议**：在 Plan 04（Factory）中引入最小化的软绑定记录（记录哪些 BOP 版本绑定了某工位），不做预订调度，但至少支持冲突查询。或者在 BOP 绑定 Capability 的 `use_when` 中明确声明"不提供冲突检测"，避免用户期望落差。

---

## 二、设计决策缺失（实施前需确定）

### 2.1 三套确认/审批机制关系未定义

系统中存在三个层次：

1. **Gateway Confirmation**（§8.3）：调用安全协议，高风险写入前的挑战-响应
2. **Base Approval**（§11.2：`base.approval.request.*`）：有申请人、审批人、对象快照、正式决定
3. **Domain Proposals**（§15.2, §16.1）：Knowledge Proposal、Ontology Proposal，各自独立走 create/revise/submit/review.decide

**未定义**：Domain Proposal 是 Base Approval 的一种实例化，还是完全独立？影响：
- 通知逻辑（Base Notification 还是领域自己发）
- 审批记录出现在哪个 `system.audit` 中
- Base Approval 的 `decide` 如何触发领域侧状态迁移

Plans 05、06 会各自实现不兼容的审批通知链，除非在 Plan 02 前给出 ADR。

---

### 2.2 DomainCapabilityClient vs Application Port 无决策规则

Foundation Plan Task 7 实现了 `DomainCapabilityClient`（全 Gateway 管线）；设计 §10 也定义了轻量的 Application Port（直接同步调用）。但没有任何文档给出"何时用哪个"的决策规则。

实际面临决策的场景（Plans 03-13 都会遇到）：
- `craft.pbom.import.preview` 调 Data Exchange 解析文件
- `craft.bop.factory_binding.preview` 调 Factory 校验工位存在
- `simulation.environment.create` 需要 Craft 提供 execution_plan_ref 解析

不同实施者会做出不一致的选择，导致一些域走 Gateway（有审计、有延迟），另一些走 Port（快、无审计）。

**建议**：在 Plan 01 completion criteria 加入决策规则，例如："无副作用的存在性/权限前置校验用 Application Port；有 Outcome 记录需求、审计要求或跨 Tenant 的必须走 DomainCapabilityClient。"

---

### 2.3 审批快照与并发修改的竞争条件

设计 §8.3："审批通过后，由原领域验证对象仍与审批快照一致并继续状态转换。"

**竞争条件**：PBOM 提交审批 → 另一用户对 PBOM 做了合法修改 → 审批通过 → 领域校验"对象与快照不一致" → 审批作废，必须重新申请。在高频修改场景下，这可能导致审批永远无法完成。

**未定义**：比较的是"结构哈希等价"还是"语义等价"？如果是哈希，任何字段变化都作废审批；如果是语义，谁定义语义相等？这在 Plans 07-09（Craft BOP 发布审批）中会直接影响用户体验。

---

### 2.4 Preview 的生命周期未定义

设计 §14.2：`craft.bop.draft.change.preview/apply` 中 preview ref 是"短期、绑定调用者和 base revision 的"。

**未定义**：
- Preview TTL 是多少？
- "绑定调用者"指 Web Session？Plugin Mount Session？Agent Run？
- 用户 JWT 刷新后 preview ref 是否仍有效？
- Preview 过期时 apply 返回什么错误？能否重新生成？

这些在 Plan 08 实施时必须统一，否则 Web、Plugin、Agent 三个消费者对 preview 的生命周期有不同假设。

---

### 2.5 Domain Event Schema 版本演进策略缺失

Foundation Task 8 定义了 `DomainEventEnvelope`，有 `event_version` 字段，但没有定义：
- 消费者如何声明处理哪些 event_version？
- Breaking change（删除字段）的判定标准？
- 多版本共存时 Outbox 如何同时支持 v1、v2 消费者？

Plans 03-14 多团队并行实现不同域的事件，没有版本演进规则就会产生不兼容的事件格式。

---

### 2.6 Integration 依赖范围过于模糊

Roadmap Plan 12（Integration）依赖："01, 02 and target domain Providers"。

"target domain Providers"是哪些？Integration 的 `integration.sync.start` 要编排目标域 Capability（写入 Craft、Knowledge 等）。若依赖所有业务域，Integration 实际上排在最后但影响优先级最高的功能。

建议明确：Integration 能否先交付只依赖 Base+Knowledge 的受限版本（飞书文档同步），后续再扩展到 Craft？

---

## 三、代码实态与设计的背离（文档审核看不到）

### 3.1 `registry_next.py` 的 import-time 注册是真实存在的反模式

文件第 84-134 行：模块级 `capability_registry = CapabilityRegistry()` 紧跟 12 个立即执行的注册调用。Foundation Plan Task 4 的测试 `test_registry_module_is_empty_until_bootstrap` 会直接失败。

额外风险：`gateway.py` 第 480 行有后门回退路径：
```python
def get_default_gateway():
    if _default_gateway is None:
        from backend.capabilities.registry_next import capability_registry  # 触发全部 import-time 注册
        return configure_default_gateway(capability_registry)
```
Task 4 必须同时修改这条回退路径，否则测试通过但问题在运行时仍存在。

---

### 3.2 `system.echo` 被 5 个测试文件硬编码，删除会连锁失败

Foundation Task 4 删除 `system.echo`，但以下测试文件有硬编码依赖：

| 文件 | 依赖方式 |
|---|---|
| `test_base_capability_contracts.py:24` | hardcoded capability list 包含 `system.echo` |
| `test_capability_consumer_e2e.py:46,60` | 端到端测试调用 `/api/v1/capabilities/system.echo:invoke` |
| `test_plugin_authority_boundary.py:12` | `get("system.echo").spec.plugin_callable` 断言 |
| `test_plugin_mount_sessions_v2.py:188` | `capability_grants=("system.echo@1",)` |
| `test_plugin_platform_next.py:23` | `"permissions": ["system.echo"]` |

Task 4 步骤 6 说"如果 system.echo 在生成产物中则重新生成 Catalog"，但完全没提更新这 5 个测试文件。这是确定的实施陷阱。

---

### 3.3 Craft 全部 Capability 用 V1 `CapabilitySpec`，非 V2 原生 Descriptor

`bop_versions.py`、`bop_writes.py`、`bop_compare.py`、`bop_structure.py`、`gbop_read.py`、`pbom_read.py` 顶部全部 import：
```python
from backend.capabilities.models_next import CapabilityContext, CapabilityOutput, CapabilitySpec
```

这些 Capability 通过 `v1_adapter.py` 的桥接层运行在 Gateway 上，不是真正的 V2 原生 Descriptor。Plans 07-09 不仅要实现新 Capability，还要把已有的 18 个 Craft Capability 从 V1 适配层升级为原生 V2 Descriptor，这是计划中没有明确列出的额外工作量。

---

### 3.4 Agent 工具处理器：29 个工具绕过 Gateway，转发原始用户 Token

`craft_tools.py`（15 个工具）和 `project_tools.py`（14 个工具）全部通过 HTTP 直连 `127.0.0.1:8080`，携带原始 `X-AI00-Token`：
```python
headers = {"X-AI00-Token": auth_token} if auth_token else {}
resp = httpx.get(f"{_BASE_URL}{path}", headers=headers, timeout=30)
```

这是设计 §3 问题 2 明确要消灭的"转发原始用户 JWT"模式。这些工具在 Plan 14 之前将持续绕过 Gateway 在生产中运行，产生审计缺口。

Plan 14 之前应加入"Agent 工具冻结声明"——不接受功能演进，只做安全补丁。

---

### 3.5 `ebom` 命名在三个层次混用，改造工作量被低估

设计决策 #8 要求代码、表、API、Capability、文档中的 `eBOM` 全部改为 `PBOM`，但实际分布：

| 位置 | 当前状态 |
|---|---|
| `plugins/craft/craft_backend/routers/ebom.py` | 文件名和 URL prefix 都是 `ebom` |
| `craft_tools.py:143` | `_pbom_vpps_check` 调用 `/api/ebom/vpps_check` |
| `agreed_catalog.py` | Capability ID 已用 `craft.pbom.*`（对的） |
| 数据库表 | 需要检查，可能有 `ebom_` 前缀的表 |

这个改造跨 URL 路由、工具代码、潜在表名三个层次，需要明确在哪个 Plan（07 还是 09）中统一完成，避免 PBOM/eBOM 长期混用。

---

### 3.6 用户功能注册表的"完成"状态是虚假的

Registry 显示 753 个稳定功能全部"有状态"，看起来已完成。但分布是：

| 状态 | 数量 | 含义 |
|---|---|---|
| `proposed` | 397 | 有 target_capability 字段，但该能力尚未实现 |
| `candidate` | 139 | 待评审，不代表实现 |
| `registered` | 103 | 确实在 Catalog 中运行 |
| `excluded` | 92 | 已排除 |
| `mapped` | 16 | 切换完成 |
| `internal_protocol` | 6 | 协议内部 |

**真正有运行实现的约 119 个（15.8%）**。其余 630+ 个的 `target_capability` 字段只是"计划目标"，不是实现证明。

这意味着 Plans 02-14 的实际工作量是"从 100 个扩展到 750+"，而不是"从 87 个添加若干"。这个落差约 6 倍，在排期时需要如实体现。

---

### 3.7 292 条边界违规按旧 9 域分类，新域加入后需核对

`backend/governance/boundary_baseline.json` 确认 292 条违规全部存在，按原 9 个域分类。Foundation Plan Task 9 新增 Factory 和 Integration、重命名 Local Runtime 后，原本登记在 `Craft` 名下的部分违规（Factory 相关的 SQL 访问）应重新归属 `Factory`。

这不是简单追加，需要人工核对 262 条跨域 SQL 违规的归属，否则 Factory 域的违规计数在 baseline 中会是 0，掩盖真实债务。

---

## 四、最高优先级行动项

按必须解决的时间窗口排序：

### Plan 01 开始前（基础性决策）

1. **明确 Revision 内核角色**：继续演进（Plan 07-09 接入），还是退役（Plan 14 前删除）。写成 ADR。
2. **明确 `system.search` 数据机制**：事件驱动物化视图、DomainCapabilityClient 扇出、还是 facade。不解决 Plan 02 无法实现。
3. **在 Program Rules 中明确治理文件的串行提交协议**：Plans 03-06 并行时 `official_domains.json` 的更新机制。
4. **三套确认/审批机制的关系 ADR**：Domain Proposal 是否是 Base Approval 的子类型。

### Plan 02 开始前（影响 Base 设计）

5. **DomainCapabilityClient vs Application Port 的决策规则**：写入 Plan 01 completion criteria。
6. **审批快照竞争条件的处理策略**：版本号比较还是语义比较？多久超时？能否重触发？
7. **Factory 软绑定记录**：是否在 Plan 04 中引入最小化冲突查询？或在 BOP 绑定文档中声明限制？

### Foundation Plan Task 4 实施时（具体实施陷阱）

8. **同步修改 5 个硬编码 `system.echo` 的测试文件**：task_4 步骤应明确列出这 5 个文件。
9. **同步修改 `gateway.py` 第 480 行的回退路径**：否则 import-time 注册通过测试后仍在运行时存活。

### Plans 07-09 开始前（Craft 实施准备）

10. **Craft Capability 从 V1 到 V2 原生 Descriptor 的升级**：在 Plans 07-09 的任务列表中明确列为每个 Capability 的必做项，不能只写"实现 Descriptor"而遗漏"移除 V1 适配层"。
11. **ebom→pbom 改造的完成 Plan 指定**：明确在哪个 Plan 中统一完成 URL、代码、工具名三层改造。
12. **Preview TTL 和生命周期规则**：在 Plan 08 任务说明中写明，避免三个消费者各自实现。

---

## 五、非问题的澄清（不需要改动）

以下几点在代码层面已验证是正确的，文档审核中可能引起误解：

- **Gateway 管线顺序**：`gateway.py` 实现与设计 §7 的 11 步顺序完全一致，包括正确的 `outcome_unknown` 处理。
- **ConsumerIdentity 不接受客户端自报**：`identity.py` 正确实现了各入口的服务端构造，Web 身份忽略 `X-AI00-Source` Header。
- **Craft Capability 的边界声明**：`bop_writes.py` 只导入 `from backend.capabilities.models_next`（V1 契约），不导入 Knowledge、Ontology 或 Project Management 的实现代码，边界在 Capability 层是干净的。
- **Revision 内核的完整性**：三方合并、内容哈希、保护分支审批挑战全部实现，质量很高，应该被后续设计复用而非废弃。
