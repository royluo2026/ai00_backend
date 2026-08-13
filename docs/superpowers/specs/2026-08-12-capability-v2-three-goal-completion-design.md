# Capability V2 三目标差量完成设计

**日期：** 2026-08-12

**状态：** 三目标代码与治理基线已实施；数据库完成定义由 2026-08-13 单库设计修订，待现场验收

**上位设计：** `docs/superpowers/specs/2026-08-11-capability-v2-domain-rearchitecture-design.md`

**实施路线图：** `docs/superpowers/plans/2026-08-11-capability-v2-domain-rearchitecture-roadmap.md`

**已完成基础计划：** `docs/superpowers/plans/2026-08-11-capability-v2-domain-foundation-implementation.md`

**后续修订：** 公司环境采用 `single_database_domain_tables`。本文中“独立数据库、十一域 Runtime/DDL 双账号”的表述是强化隔离配置，不再是公司环境唯一完成条件。公司配置以逐表唯一 Owner、独立领域 Migration、共享 Runtime 最小 DML、无 DDL、Gateway-only 跨域访问和静态边界审计作为完成证据。

## 1. 文档目的

本文不是新一轮 Capability 梳理，也不替代已经审核的领域重构详细设计。本文把既有设计、覆盖审计和已完成的 Domain Foundation 作为冻结输入，只定义完成剩余实施工作时不可降级的三项目标、差量范围、执行约束和 Release Candidate 验收合同。

三项目标必须同时达成：

1. 插件和 Agent 能够发现、获得授权并调用统一 Capability；
2. 十一个一级领域能够独立开发代码和数据库；
3. 领域之间能够通过正式契约共享 Capability，而不共享内部实现或数据库。

任何单项通过都不能替代另外两项。只有三项目标及其零债务门禁全部通过，Capability V2 才能宣布完成。

## 2. 冻结输入与范围保护

### 2.1 冻结审计结论

以下文件是本轮实施的事实输入，不重新盘点或重新分类：

- `docs/governance/capability-coverage-review/generated/summary.json`
- `docs/governance/capability-coverage-review/generated/function-dispositions.md`
- `docs/governance/capability-coverage-review/generated/capability-candidates.md`
- `docs/governance/capability-coverage-review/generated/consumer-exposure.md`
- `docs/governance/capability-coverage-review/generated/code-ownership-extractions.md`
- `docs/governance/capability-coverage-review/generated/database-ownership-migrations.md`
- `backend/governance/boundary_baseline.json`
- `backend/capability_v2/official_domains.json`

当前治理快照记录：

- 11 个一级领域；
- 844 个稳定用户功能，0 个未评审项；
- 743 个功能处置到既有 Capability，101 个功能明确排除，无待新增候选；
- 当前 Catalog 有 267 个 Descriptor，其中 264 个为稳定 Capability；
- 58 项代码归属迁移；
- 当前生成证据中的跨领域 SQL、内部实现导入和边界违规均为 0；单库 Schema 为 204 张表、2307 个字段和 535 个索引。

上述数字是当前生成产物中的可追溯快照，不是用来限制正确实现的配额。后续实施不得为了降低数量而合并权限、风险、状态机或业务结果不同的 Capability，也不得把一个 Capability 拆成路由形状的伪能力。

### 2.2 冻结语义

既有和已评审候选 Capability 的 ID、业务结果、owner、消费者暴露结论和稳定性处置全部冻结。领域计划只能实现这些结论，不能在开发过程中自行改名、重新归域、复制或废弃。

只有出现以下情况时才能提出变更：

- 冻结证据存在可证明的事实错误；
- 两个冻结契约存在无法同时满足的冲突；
- 契约在目标架构下不可实现，且不存在兼容实现。

变更必须形成独立决策记录，列明受影响的 function ID、Capability ID、消费者、owner、迁移和兼容策略，并在修改生成物之前获得书面确认。普通实现困难不构成重新梳理的理由。

### 2.3 明确不做

本轮不做以下工作：

- 重新扫描产品以发起新一轮能力发现；
- 改变已经确认的十一个一级领域；
- 新增与三项目标无关的业务功能；
- 重做已经由 Foundation Plan 01 交付的机制；
- 以共享数据库、共享 ORM、内部模块导入或复制代码代替 Capability 共享；
- 用长期双写、永久兼容层或豁免清单掩盖未完成迁移。

## 3. 固定领域模型

十一个一级领域固定为：

1. Base Platform
2. Project Management
3. Factory
4. Craft
5. Knowledge
6. Ontology
7. Agent
8. Integration
9. Local Runtime
10. Digital Model
11. Simulation

Plugin Platform 是 Base Platform 下的消费者平台与治理子系统，不是第十二个业务领域。它可以托管插件生命周期、授权和调用入口，但不能拥有其他领域的业务结果或数据库表。

## 4. 目标一：向插件和 Agent 提供统一能力

### 4.1 唯一业务执行路径

插件和 Agent 的业务调用必须遵循：

`Consumer -> Catalog discovery -> authorization -> Capability Gateway -> owning Provider -> owning domain database`

Catalog 是能力发现和 Descriptor 的唯一事实源；Gateway 是消费者执行 Capability 的唯一治理入口；Provider 是业务结果的唯一实现入口。消费者不能自行维护第二份业务工具清单、权限表或实现映射。

### 4.2 插件消费合同

插件平台必须基于 Catalog 的消费者暴露声明提供发现结果，只返回对当前插件、租户和主体可见的 Capability。插件调用必须携带受验证的插件身份、租户、主体、Capability ID、major version、授权范围和调用关联 ID，并由 Gateway 统一处理：

- 身份与租户绑定；
- Capability 暴露和授权判断；
- 风险等级与审批要求；
- 输入输出契约校验；
- 幂等键、超时预算和错误映射；
- 审计、Trace 和调用结果记录。

插件业务 handler 只能是调用 Gateway 的薄适配器。包含业务规则、直接调用具体领域 Service/Repository、导入具体 Provider 或访问领域数据库的插件 handler 必须迁移并删除。

### 4.3 Agent 消费合同

Agent 工具必须从 Catalog Descriptor 确定性生成或装配。工具名、描述、参数模式、风险、审批和返回投影来自同一个 Descriptor，不维护手写业务工具定义。

Agent 执行工具时必须通过 Gateway，并携带 Agent、Run、Session、租户、主体和 Trace 上下文。Gateway 仍然执行完整授权；Agent 的规划结果不能视为权限授予。需要审批的 Capability 在批准前不得执行，取消 Run 时必须取消该 Run 的全部 pending ApprovalRequest。

遗留 Agent handler、token 转发和直接领域导入必须在 Plan 14 和 Plan 15 中移除。保留的兼容适配器只能做协议转换并调用 Gateway。

### 4.4 统一错误合同

插件与 Agent 接收同一套公开错误类别，至少覆盖：

- capability not found/version unsupported；
- exposure denied/authorization denied/approval required；
- invalid input/conflict/idempotency conflict；
- deadline exceeded/dependency unavailable；
- internal provider failure。

错误响应不得泄露 Provider 堆栈、内部模块、数据库名、表名、SQL 或凭据。所有拒绝和失败都必须与审计记录、Trace ID 和调用关联 ID 对应。

## 5. 目标二：领域代码和数据所有权独立

### 5.1 独立交付单元

每个一级领域必须拥有：

- 明确且可扫描的代码根目录及 ownership；
- 可加载的正式 Provider 和 DomainManifest；
- 领域模型、应用服务、Repository、Provider Adapter 和领域内测试；
- 独立表所有权、migration 目录和 ledger；数据库与账号隔离由部署配置提供；
- 独立构建、领域测试、部署、升级和回滚步骤；
- 对外版本化 Capability 契约及领域事件契约。

领域可以在不修改其他领域内部代码和表定义的情况下开发、测试和发布。共享平台库只能提供无业务归属的基础类型、协议和基础设施适配，不能承载跨领域业务规则。

### 5.2 数据库所有权

一张业务表只能归属一个一级领域。所有代码路径必须通过绑定领域身份的数据访问端口访问 Owner 表；Migration 只能修改所属领域表。强化隔离配置使用每域 Runtime/DDL 账号；公司单库配置使用四个开发组账号、一个共享 Runtime 账号和外部 DBA/临时迁移身份。

强化隔离配置允许采用独立实例或独立数据库，并应同时具备：

- 独立连接配置和凭据；
- 数据库侧权限隔离，而非仅依赖代码约定；
- 独立 migration 目录、版本序列和 ledger；
- 禁止跨库 JOIN、外键和事务；
- 可独立升级与回滚。

公司单库配置不声称数据库账号级领域隔离。其完成条件改为：逐表唯一 Owner、跨域 SQL/外键/Repository 导入为零、Runtime 无 DDL、开发组授权与职责矩阵一致、Migration 由外部身份执行，并在报告中明确 `isolation_profile=single_database_domain_tables`。共享 Runtime 凭据泄露的影响面覆盖整个业务数据库，是必须保留在风险登记中的剩余风险。

### 5.3 依赖边界

领域之间禁止：

- 跨领域 SQL、JOIN、外键和 ORM relation；
- 导入其他领域的 Router、Repository、ORM、数据库连接、具体 Service 或 Provider 实现；
- 通过共享可变表交换状态；
- 在本领域持久化其他领域对象的可变副本。

跨领域只保存不透明 ResourceRef、ArtifactRef、OperationRef 和不可变版本引用。需要对方最新状态时必须调用 Capability 或消费版本化事件。

### 5.4 完成定义

一个领域只有在代码归属、Provider、数据库权限、migration、契约、独立测试、部署与回滚全部通过，且该领域对应的旧实现和边界债务已删除后才能标记完成。仅创建目录、Manifest 或空 Provider 不算完成。

## 6. 目标三：领域间共享能力

### 6.1 同步协作

跨领域同步业务请求统一通过：

`calling domain -> DomainCapabilityClient -> Capability Gateway -> owning Provider`

`DomainCapabilityClient` 负责传播租户、主体、调用方领域、Trace、deadline 和幂等上下文，但不能绕过 Gateway 授权。调用方只依赖 Capability ID、major version 和公开输入输出契约，不依赖 Provider 类型或数据库结构。

同步调用必须：

- 设置总 deadline 和单次调用预算；
- 仅对明确幂等且错误类别可重试的请求执行有界重试；
- 传播并记录调用链；
- 对冲突、拒绝、超时和不可用作确定性错误映射；
- 避免形成必须同步发布多个领域的循环依赖。

Public Port 可以定义稳定值类型、领域内部依赖倒置接口和基础设施协议，但不能成为第二条跨领域业务执行路径。

### 6.2 异步协作

异步跨领域协作统一使用版本化领域事件和真实 Outbox/Inbox：

`owning domain transaction -> Outbox -> transport -> consumer Inbox -> consumer-local transaction`

强制要求：

- 业务状态变更和 Outbox 写入处于 owner 领域同一本地事务；
- 事件包含 event ID、event type、schema version、producer、tenant、subject/resource ref、occurred-at 和 Trace 信息；
- Consumer 在本地事务中写 Inbox 去重记录并更新本地状态；
- 按 event ID 去重，处理器可以安全重放；
- 失败采用有界重试并进入可审计的失败恢复流程；
- 订阅及支持的版本范围登记在正式 DomainManifest；
- 事件只传递稳定事实和必要引用，不传递数据库行或内部对象图。

Foundation 中已有事件契约和 Manifest 字段只是机制。至少一个真实生产链路完成发布、传输、消费、去重、重放和恢复，才能证明异步共享目标完成。

### 6.3 共享能力的完成定义

最终验收必须选取冻结清单中的真实业务链路，分别证明：

- 至少一条跨领域同步链路真实经过 `DomainCapabilityClient` 和 Gateway；
- 至少一条跨领域异步链路真实经过 Outbox、transport 和 Inbox。

链路选择在实施计划中根据依赖顺序确定，不为测试新增虚构 Capability，也不能使用只存在于测试中的示例 Provider 代替生产实现。

## 7. 计划承接与迁移顺序

Foundation Plan 01 已完成，后续直接承接既有路线图 Plan 02–15：

| Plan | 交付范围 |
|---|---|
| 02 | Base Platform |
| 03 | Project Management |
| 04 | Factory |
| 05 | Knowledge |
| 06 | Ontology |
| 07 | Craft PBOM |
| 08 | Craft BOP |
| 09 | Craft GBOP 与 Rules |
| 10 | Digital Model |
| 11 | Simulation |
| 12 | Integration |
| 13 | Local Runtime |
| 14 | Agent |
| 15 | Consumer cutover、旧路径删除和 RC 验收 |

每个领域计划执行同一垂直切片：

1. 读取冻结的功能处置、Capability、消费者和归属清单；
2. 以测试固定该领域契约和当前待迁移边界；
3. 建立或补全正式 Provider 并接入 Catalog/Gateway；
4. 建立独立代码边界、数据库、账号和 migration；
5. 把跨领域 SQL、内部导入改为 Capability 调用或领域事件；
6. 先切换受控读路径并进行影子比对，再切换写路径；
7. 运行领域契约、数据库权限、迁移、回滚和消费者测试；
8. 删除被替代的实现、表、路由或适配器；
9. 更新债务台账和中央冻结产物；
10. 通过领域门禁后进入下一依赖计划。

### 7.1 迁移纪律

- 同一业务结果在任何时刻只能有一个权威实现和一个当前事实源。
- 允许受控影子读和结果比对，不允许把长期双写作为迁移或回滚机制。
- 回滚只能回退流量或部署版本，不能恢复跨领域 SQL、共享账号或第二套业务实现。
- 删除旧路径必须在对应新路径的真实测试通过后立即完成，不能统一遗留到未来未定义阶段。
- 中央治理文件继续采用路线图定义的单一集成者串行冻结协议。
- Plan 15 只完成全消费者切换、全局删除和 RC 验收，不替 Plans 02–14 补做领域数据库或 Provider。

## 8. 验收矩阵

| 目标 | 强制证据 | 通过门槛 |
|---|---|---|
| 插件获得能力 | Catalog 发现、授权调用、拒绝、审计和错误映射 E2E | 全部通过，无业务旁路 |
| Agent 获得能力 | Catalog 工具装配、授权调用、拒绝、审批、取消、超时和审计 E2E | 全部通过，无手写业务工具和直接领域调用 |
| 领域代码独立 | ownership、依赖扫描、Provider 加载、独立构建和领域测试 | 11/11 通过 |
| 领域数据库独立 | 独立账号、最小权限、migration ownership、越权拒绝、升级与回滚 | 11/11 通过 |
| 同步共享 | 真实生产链路经过 DomainCapabilityClient 和 Gateway | 调用、鉴权、超时、Trace 和错误映射通过 |
| 异步共享 | 真实生产链路经过 Outbox、transport 和 Inbox | 发布、订阅、重试、去重、重放和恢复通过 |
| 历史债务 | 边界扫描和旧路径扫描 | 跨领域 SQL、内部导入及消费者业务旁路全部为零 |
| 发布就绪 | 全量测试、strict acceptance、真实数据库与进程边界 E2E、迁移回滚演练 | RC 报告无失败、无跳过 |

### 8.1 证据规则

- 单元测试可以使用 fake 或 mock，但最终 RC 不能用 mock-only 证据证明系统边界完成。
- RC 必须运行真实数据库权限隔离，并让消费者、Gateway 和 Provider 跨真实进程边界执行。
- 不得通过扩大豁免、白名单、忽略目录或降低扫描口径把债务归零。
- Catalog 声明对 Plugin 或 Agent 可见的 Capability 必须实际可发现、可授权和可调用。
- 跳过、xfail、未配置和仅生成报告都不计为通过。
- 每份最终证据记录 Git commit、Catalog release、DomainManifest digest、migration 版本、测试环境和 report ID。

## 9. 失败与恢复合同

### 9.1 同步调用

Gateway 对 Provider 失败进行统一分类，隐藏内部异常。每次调用必须有 deadline；只有契约声明为幂等且错误可重试时才允许有界重试。超出预算、授权拒绝或契约不匹配必须失败关闭，不能回退到直接 Service 或数据库调用。

### 9.2 异步事件

Outbox 投递和 Inbox 消费均保留可审计状态。Consumer 失败不得回滚 Producer 已提交的领域事实；通过重试、去重和人工可触发的受控重放恢复。无法处理的 schema version 必须进入明确失败状态，不能静默丢弃或按未知结构处理。

### 9.3 迁移与发布

领域 migration、权限验证或切换验证失败时，停止该领域切换并回退到最近已验证版本。旧路径只能在新路径所有强制证据通过后删除；一旦删除，不以重新引入边界违规作为回滚方案。

## 10. Program 完成条件

Capability V2 Program 只有在以下条件全部满足时完成：

1. Plan 02–15 全部完成并各自通过领域门禁；
2. 十一个正式领域均有可加载 Provider、独立代码 ownership、逐表唯一 ownership 和独立 migration 流；数据库权限与选定 isolation profile 一致；
3. Plugin 和 Agent 的全部已声明业务 Capability 只通过 Catalog + Gateway 执行；
4. 至少一条真实同步跨领域链路和一条真实异步跨领域链路通过 RC；
5. `backend/governance/boundary_baseline.json` 中跨领域 SQL 和内部导入均为零；
6. 消费者旁路、旧 Provider 路径、永久兼容业务 handler 和共享领域账号均为零；
7. 全量测试和 release-candidate strict acceptance 无失败、无跳过；
8. 生成可复现的 RC 报告，完整记录代码、Catalog、Manifest、数据库和测试证据。

其中任何条件未满足时，Program 状态只能是进行中或失败，不能以“Foundation 已完成”“Catalog 已生成”或“主要链路可用”宣告三项目标达成。
