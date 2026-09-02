# Capability V2 领域重构设计复核报告（R2）

**日期：** 2026-08-11  
**复核对象：** `docs/superpowers/specs/2026-08-11-capability-v2-domain-rearchitecture-design.md`  
**对应提交：** 0ddaa6f docs: resolve capability architecture review findings  
**基准：** 首轮审核报告 `docs/superpowers/reviews/2026-08-11-capability-v2-architecture-review.md`

---

## 总体评价

首轮审核的主要问题已基本落地。Revision 内核定位、system.search 数据机制、三套审批体系关系、Preview 生命周期、Event 版本演进、DomainCapabilityClient 决策规则、Integration 分层交付、并行计划治理、Agent 工具冻结声明——这 11 项均已在本次修订中给出明确设计。

仍有 1 个 P0 和 4 个 P1 需要处理。

---

## 已修复问题确认

| 原问题 | 修复位置 | 验收 |
|---|---|---|
| Revision 内核命运未定 | §10.3 | 定位为"共享版本算法+跨域引用图基础设施"，不强制各域接入，可选 Adapter，通过 ✅ |
| system.search 无数据源 | §11.4 | Phase 1 扇出 + Phase 2 事件物化，两阶段机制明确，通过 ✅ |
| 三套审批机制关系未定义 | §8.3 | Confirmation/Approval/Proposal 职责边界清晰，不互替，通过 ✅ |
| 审批快照竞争条件 | §8.3 | "提交后内容冻结，始终用精确 hash 比较，approval_stale 明确处理"，通过 ✅ |
| Preview 生命周期未定义 | §14.6 | TTL 15 分钟、绑定字段、消费一次语义、各类错误码全部明确，通过 ✅ |
| Event Schema 版本演进缺失 | §9.4 | expand/contract 演进模式、breaking change 判定、消费者版本声明，通过 ✅ |
| DomainCapabilityClient vs Port 无决策规则 | §10.2 | "存在性检查也必须走 DomainCapabilityClient"，Public Port 只允许两类场景，通过 ✅ |
| 并行计划修改同一文件 | §27 | "中央治理文件通过串行集成队列提交"，原则确立，通过（细节见 P0） |
| Factory 绑定是空操作 | §13.3 | "不表达占用，不执行冲突检查"语义明确，通过 ✅ |
| Integration 依赖范围模糊 | §18 | Core/Adapter 分离，首个交付只需 Base+Knowledge，通过 ✅ |
| Agent 工具 Token 转发 | §25 阶段 8 | 冻结声明完整，通过 ✅ |

---

## P0 问题

### P0-1：§27 "串行集成队列"无操作定义

**原文**（§27）：
> 中央治理文件、CODEOWNERS、Capability Ledger、official_domains.json、Catalog Release 和 artifact hash 必须通过串行集成队列提交。每个领域合入前从最新集成基线重新生成并校验冻结产物；后一个领域不得基于过期 central manifest 计算 hash。

规则表述正确，但"串行集成队列"是一个尚未定义的操作机制。在多人并行推进 Plans 03-06 的真实场景中，没有具体机制约束，冲突会直接发生：

- Person A 完成 Plan 03，运行 `freeze_official_domains.py`，得到 hash H-A
- Person B 同时完成 Plan 04，基于旧 manifest 计算 hash H-B
- 两者合并时 `official_domains.json` 产生无法机械解决的冲突（每方的 hash 都是基于自己代码状态算的）

**必须在本文或 Program Rules 中明确操作机制**，例如：

> Plans 03-06 在各自独立 worktree 开发，但只有一条 `integration` 分支承载中央治理文件。每个 Plan 完成后，责任人向 `integration` 提交包含以下操作的单次 PR：① 运行 `freeze_official_domains.py` 重新计算当前全量 hash；② 运行 `build_capability_catalog.py --check` 验证 Catalog 无漂移；③ 更新 `domain-ownership.json`、`CODEOWNERS` 和 `boundary_baseline`。后一个 Plan 必须先拉取已合入的 `integration` 基线，不得基于过期状态开始集成步骤。

---

## P1 问题

### P1-1：search "已登记领域"的注册机制未定义

**§11.4**：
> Base 并行调用已登记的领域 search Capability，每域有独立 deadline、最大结果数和稳定游标。

"已登记"在哪里登记、格式是什么、谁负责维护，文档没有说明。Plan 02（Base）实施时，开发者不知道从哪里读取这个列表，会自行发明不兼容的机制。

**建议在 §11.4 或 Foundation Plan Task 的 completion criteria 中明确**，例如：各域 Provider Manifest（`official_domains.json` 中的 DomainManifest）通过 `search_capability` 字段声明该域暴露的 search Capability ID 和 major；Base 在启动时读取全局 manifest 构建搜索域列表。或者明确说这是 Plan 02 内部实现细节，由 Base 负责维护一份配置文件。

---

### P1-2：§9.4 "部署清单"是新概念，未映射到已有文件

**§9.4**：
> 消费者在部署清单中声明可处理的最小和最大版本；收到不支持的版本时不得确认 Inbox 完成，而是进入 dependency_unavailable/dead-letter 并报警。

"部署清单"未定义其格式和物理位置。它与已有的 `domain_manifest.py`（Provider 制品清单）是同一个文件，还是新文件？Foundation Plan Task 8 定义了 `DomainEventEnvelope`、`OutboxWriter`、`InboxDeduplicator`，但没有包含消费者版本声明结构。

若无统一格式，各域会各自实现不兼容的版本范围声明，运行时无法做统一版本检查。

**建议**：在 §9.4 中补充一句说明，例如"消费者通过其 DomainManifest 的 `event_subscriptions` 数组声明"，或者指向 Foundation Plan 中待定义的新字段，并在 Plan 01 Task 8 的交付物中包含该结构。

---

### P1-3：Craft BOP/PBOM Revision Adapter 在实施计划中缺失

**§10.3**：
> Ontology、Craft、Knowledge、Digital Model 和 Simulation 的接入都必须使用各自 Adapter。

代码中已存在 `digital_model_adapter.py`、`simulation_adapter.py`、`ontology_adapter.py`。但在 Roadmap 的 Plans 07-09（Craft PBOM/BOP/GBOP）中没有"建立 CraftRevisionAdapter"的任务。

如果 `system.change_impact.preview` 需要追踪"BOP Version V2 引用了 PBOM Version X3"这类跨域 Lineage，这条 LineageEdge 必须通过 CraftRevisionAdapter 写入 Revision Kernel。没有 Adapter，§11.4 中承诺的 `system.change_impact.preview` 对 Craft 数据将不可用。

**建议**：在 Plans 07（Craft PBOM）或 08（Craft BOP）中增加任务："实现 CraftPbomRevisionAdapter 和 CraftBopRevisionAdapter，在版本发布/归档时写入 LineageEdge，接入 §10.3 定义的 Revision Kernel Adapter 协议。"

---

### P1-4：Agent Run 取消时孤立 ApprovalRequest 无生命周期处理

§17.2 说明 Run 取消通过 `system.job.cancel`，§8.3 描述了审批生命周期，但两者交叉的场景未定义：

**场景**：Run 在 `awaiting_approval` 状态时被 `system.job.cancel` 取消。  
此时审批人界面仍显示该 ApprovalRequest。如果审批人批准，Gateway 将执行对应 Capability——但 Run 已不存在，执行结果无法回传给 Run，产生悬空执行；如果不处理，ApprovalRequest 等待超时（可能数小时）才消失。

**需要明确的规则**：Run 取消时，Runtime 必须同步调用 `base.approval.request.cancel` 撤销所有与该 Run 关联的待决 ApprovalRequest，ApprovalRequest 进入 `cancelled` 状态，审批人界面提示已取消。

这个规则影响 **Plan 02（Base Approval 设计需要支持外部取消）** 和 **Plan 14（Agent Run 取消逻辑）**，应在 §8.3 或 §17 中补充，确保两个 Plan 的实施者都能看到。

---

## 不需要改动的澄清

**原审核提到"审批永远 stale"**：已确认是误判。§8.3 的"提交后内容冻结"结合版本化模型（BOP/PBOM 每次草稿是独立版本），审批针对不可变 Submitted Revision，并发写只会创建新版本而不覆盖已提交内容，设计正确无需修改。

**BOP "Operation" 术语冲突**（BOP 层级叶节点 vs OperationRef）：这是文档和沟通层面的歧义，不是实现冲突。Capability ID 不冲突（`craft.*` vs `OperationRef` 类型），可在开发者手册中加一条术语说明，无需修改设计文档。

---

## 汇总

| 级别 | 问题 | 涉及章节 | 建议处理时机 |
|---|---|---|---|
| **P0** | "串行集成队列"无操作定义，多人并行开发立刻冲突 | §27 | 本文修订时补充，或写入 Program Rules |
| P1 | search "已登记"注册机制未定义 | §11.4 | Plan 01 Foundation Task completion criteria |
| P1 | "部署清单"未映射到具体文件格式 | §9.4 | Plan 01 Task 8 交付物补充 |
| P1 | Craft Revision Adapter 在 Plans 07-09 中缺失对应任务 | §10.3 + Roadmap | Plans 07/08 任务列表补充 |
| P1 | Agent Run 取消时孤立 ApprovalRequest 生命周期未定义 | §8.3 / §17 | 本文 §8.3 或 §17 补充一条规则 |
