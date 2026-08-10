# AI00 Capability V2、插件与 AI Agent 架构设计

> 日期：2026-08-10  
> 状态：设计已逐节确认，等待实施计划  
> 适用范围：Base、Craft、Digital Model、Simulation、Ontology、Knowledge、Revision、Plugin、Agent Runtime、MCP、Local Runtime  
> 决策级别：目标架构与迁移约束  
> 取代关系：与 `2026-08-05-capability-consensus-round-1-design.md` 冲突时以本文为准；本体治理细节继续兼容 `2026-08-05-ontology-capabilities-design.md`

## 1. 背景与结论

AI00 已经具备 Capability Registry、Catalog、部分 Provider、插件沙箱、Agent 工具适配、MCP、确认、幂等、审计和本地运行协议的基础实现，但尚不足以作为插件系统和 AI Agent 的统一业务底座。

现状的主要问题不是 Capability 数量不足，而是缺少唯一可信执行边界：HTTP、进程内 Agent、插件桥接、MCP 和 Worker 的身份、授权、结果、限流、审批、幂等与审计路径不一致。把现有业务 Capability 简单设置为 `plugin_callable=true` 会扩大越权、数据泄露、重复执行和审计缺口。

本设计采用领域纵切片方式重构。所有稳定用户业务功能必须登记、形成正式 Capability，并由 Web、插件、Agent、REST 和 MCP 通过同一个 `CapabilityGatewayService` 使用。不同入口可以具有不同授权和自动化等级，但不得拥有不同的业务实现。

## 2. 目标与非目标

### 2.1 目标

1. Base、Craft、Digital Model、Simulation、Ontology、Knowledge 和 Local Integration 的全部稳定用户业务功能都有正式 Capability。
2. 插件和 AI Agent 能发现这些能力；是否执行由消费者、租户、资源、数据范围和自动化策略决定。
3. Web 迁移到相同 Capability，旧 REST 业务实现最终退役。
4. 版本、差异、谱系和本体成为跨领域一级能力。
5. 大文件、数模和长任务使用标准引用与异步协议。
6. 插件、Agent、MCP、Worker 和本地 Runtime 使用服务端可信身份，不再自报来源。
7. 写入具备明确的审批、并发、幂等、Outcome、审计和补偿语义。
8. 建立一份覆盖全部开发者可用能力的严谨、版本化、机器可验证的开发者手册。

### 2.2 非目标

以下内容不作为普通业务 Capability 暴露：

- OceanBase SQL、Migration、备份和运维控制；
- 任意文件系统、服务器路径或对象存储凭证；
- 任意字段 Patch、任意图查询、任意 SPARQL/GraphQL；
- 领域内部 Repository、DAO、Router 和事务步骤；
- UI 临时态、纯展示逻辑和非稳定实验功能；
- 插件或 Agent 对内部实现类的直接访问。

“所有功能可用”指全部稳定用户业务功能具有可发现、可治理的正式契约，不表示所有消费者都获得无限执行权限。

## 3. 现状审计基线

本轮审计确认了以下结构性风险，实施计划必须逐项闭环：

1. HTTP Router 承担部分限流、插件授权和来源判断，但进程内 Agent SDK 可以直接调用 Registry，绕过这些门禁。
2. `X-AI00-Source`、插件 ID、插件版本和 Agent Run 等信息来自客户端 Header，不能构成可信身份。
3. Catalog 可以过滤消费者，执行路径却没有完整地强制相同暴露策略。
4. 当前 Provider 装载后的大量输入 Schema 开放或缺失，输出 Schema 普遍未封闭；部分写能力缺少明确权限或确认策略。
5. 插件 Web Bridge 截断 `CapabilityResult`，丢失版本、Evidence、Operation、审计关联和结构化错误。
6. 领域写入、幂等结果和审计不是同一可靠事务；外部操作缺少 `outcome_unknown` 语义。
7. 现有权限主要是字符串集合，无法完整表达租户、资源、数据和委托范围。
8. Agent Runtime 缺少持久化 Run、Step、Approval、Checkpoint、Budget 和恢复状态机，且存在运行时 DDL 和长期转发用户令牌的问题。
9. 插件 Manifest 缺少版本范围、资源范围、数据范围、可选权限和精确安装身份。
10. Capability 版本默认取最大值，插件和 Agent Run 没有固定不可变 Catalog Release，多实例可能出现目录漂移。
11. Simulation 只暴露少量能力，并信任调用者提供的执行计划内容或 URI，未通过正式领域引用解析。
12. Base 直接依赖 Device 实现，破坏领域边界；本地运行“入队成功”和“动作完成”语义混淆。
13. 限流主要位于 HTTP 层，不能覆盖进程内 Agent、插件、MCP、Worker 和本地操作，也没有成本权重。
14. 确认没有完整绑定消费者、Agent Run、资源、策略版本和数据范围；Worker 可绕过人类确认语义。
15. Provider 信任、动态加载、旧 Registry、双 Capability URL 和跨语言协议缺少统一发布治理。
16. 当前消费者路由表是粗粒度路由登记，不是覆盖全部用户功能的 User Function Registry。
17. JSON 响应无法承载大型 CAD、模型快照、仿真结果、截图和长时间任务。
18. Agent 工具结果缺少统一投影、脱敏、大小限制和不可信提示内容隔离。
19. Agent Runtime、MCP Gateway 和部分本地服务缺少完整版本控制、CI、制品和发布责任边界。

这些风险决定了本轮工作属于架构重构，不能通过局部开关完成。

审计日的量化基线为：官方 Provider 装载后共有 90 个 Capability（55 读、34 写、1 破坏性），其中只有 5 个允许插件调用，且没有业务领域能力；50 个输入 Schema 开放或缺失，90 个输出 Schema 均未明确封闭。9 个非读能力缺少显式权限，2 个写能力缺少确认策略。Agent Catalog 有 24 个活动工具和 32 个延迟工具，只有约 10 个业务工具实际由 Capability 支撑。

路由盘点显示 Base 约 171 条、Craft 约 372 条、Simulation 3 条，而 Web 静态扫描发现约 975 个调用引用和 540 种路由模式。上述数字不是目标 Capability 数量，但说明现有 11 项粗粒度消费者路由登记无法证明用户功能覆盖。

当前聚焦自动化测试曾达到 Backend 99 项通过（2 项因 Windows 临时目录 ACL 初始化失败，直接执行 Provider 边界用例通过）、Web 123/123、Agent Runtime 3/3、MCP 4/4；这些结果只能证明局部回归，尚未覆盖真实 OceanBase、OIS、JWT/OAuth、多实例、插件挂载、Agent 审批和本地 Runtime 端到端，因此不能作为生产就绪结论。

## 4. 架构原则

1. Capability 是稳定业务结果契约，不是 Router、表或微服务的同义词。
2. User Function Registry 是功能覆盖事实来源；Capability Descriptor 是执行契约事实来源。
3. 所有消费者只能通过统一 Gateway 执行 Capability。
4. 身份由服务端可信适配器构造，客户端不得自报来源和权限。
5. 领域拥有业务语义和不变量，Base 不代理其他领域 CRUD。
6. 查询可以安全投影；命令必须表达业务意图，禁止通用 Patch 绕过规则。
7. 版本、差异、Evidence、审批、Outcome 和审计是正式契约的一部分。
8. 大对象通过引用传递，长操作通过状态机管理。
9. AI 和插件默认最小权限；可发现不等于可自主执行。
10. 文档、SDK、Agent Tool、OpenAPI 和 MCP 描述必须从同一描述符生成。

## 5. 目标架构

```text
User Function Registry
          │
Capability Descriptor V2 + Immutable Catalog Release
          │
Transport Adapters
Web / Plugin Host / Agent Runtime / REST / MCP / Worker / Local Runtime
          │
Identity Broker
Actor + Tenant + Consumer + Delegation + Resource Scope + Data Scope
          │
CapabilityGatewayService
resolve → expose → authorize → validate → approve → quota/idempotency
        → dispatch → outcome/outbox → project → result
          │
Domain Application Ports
Base / Craft / Digital Model / Simulation / Ontology / Knowledge
Revision & Lineage / Local Integration
          │
Repositories / OceanBase / OIS / Desktop Runtime / Device Adapters
```

Registry 降级为描述符和 Provider 的内部映射表，不再是消费者可直接调用的安全边界。

## 6. 核心契约

### 6.1 UserFunctionRecord

每项稳定用户业务功能至少登记：

- 功能 ID、名称、领域和负责人；
- 当前 Web/REST/后台入口；
- 目标 Capability ID 和版本；
- Web、Plugin、Agent、API、MCP 暴露状态；
- AI 自动化等级和审批要求；
- 资源类型、数据分类和风险等级；
- 尚未开放时的原因、责任人和整改期限；
- 迁移、验证和旧入口退役状态。

稳定功能不能只存在于页面或 REST 中。例外只允许纯内部、运维或非业务实现，并必须记录分类理由。

### 6.2 CapabilityDescriptorV2

描述符至少包含：

```text
identity:
  id, major_version, owner_domain, lifecycle_status,
  catalog_release, schema_hash

semantics:
  title, description, use_when, do_not_use_when,
  side_effect_level, execution_mode

exposure:
  web, plugin, agent, api, mcp, automation_policy

security:
  authorization_policy, resource_selectors, data_classification,
  required_auth_freshness, delegation_policy

contract:
  closed_input_schema, closed_output_schema,
  artifact_policy, operation_policy, concurrency_preconditions

reliability:
  idempotency_policy, consistency_policy, timeout_policy,
  rate_limit_cost

governance:
  confirmation_policy, evidence_policy, audit_policy,
  deprecation_policy
```

`plugin_callable` 被废弃。各入口使用结构化 Exposure Policy；高风险能力可以对 Agent 可发现但禁止自主执行。

### 6.3 ConsumerIdentity

可信身份包含：

```text
actor: user_id/service_id, authentication_method, authentication_time
tenant: tenant_id, membership, active_roles
consumer: type, id, version, installation_id, mount_session_id, agent_run_id
delegation: delegated_by, capability_scopes, resource_scopes,
            data_scopes, expires_at
```

该对象只能由 Web Session、Plugin Mount、Agent Delegation、OAuth/MCP、Worker 或 Local Runtime 身份适配器构造。

### 6.4 InvocationEnvelope

```text
capability_id
major_version
payload
consumer_identity
idempotency_key
expected_resource_version
request_id
trace_id
deadline
approval_reference
```

调用者不能在 Payload 中声明来源、角色、权限或审计结果。审批引用只能由可信宿主或 Runtime 持有。

### 6.5 CapabilityResultV2

```text
ok
status: completed | accepted | rejected | failed | outcome_unknown
data
operation_ref
artifact_refs
error
evidence
warnings
correlation
```

Web、插件、Agent、REST 和 MCP 必须保留标准结果语义。入口可以投影数据，但不得重新定义业务结果或截断结构化错误。

### 6.6 标准引用

- `ArtifactRef`：大型文件、CAD、模型快照、报告和结果制品；
- `OperationRef`：异步、仿真、本地和设备操作；
- `ModelRef` / `ModelVersionRef` / `ModelSnapshotRef`：数模身份；
- `CommitRef` / `DiffRef` / `BaselineRef`：版本与差异；
- `ConceptRef` / `OntologyVersionRef`：语义身份。

云端契约禁止暴露服务器或本地绝对路径。

## 7. 唯一执行管线

`CapabilityGatewayService` 按固定顺序执行：

1. 解析并固定 Catalog Release、Capability 主版本和 Schema Hash；
2. 构造、验证 ConsumerIdentity 和授权新鲜度；
3. 检查当前入口的 Exposure Policy；
4. 执行租户、资源、数据和委托范围授权；
5. 校验封闭 Schema、业务前置条件和乐观并发版本；
6. 检查确认或持久化审批；
7. 检查幂等、配额、成本预算和并发容量；
8. 调用领域 Application Port；
9. 持久化 Outcome、Operation、领域 Commit 和 Audit Outbox；
10. 按消费者执行数据投影、脱敏和大小限制；
11. 返回 CapabilityResultV2。

HTTP Router、Agent SDK、插件桥接和 MCP 不得复制或绕过上述阶段。

## 8. Catalog、版本与发布

引入不可变 `CatalogRelease`：

```text
release_id
catalog_hash
capability_versions
schema_hashes
provider_artifacts
created_at
```

规则如下：

- 已安装插件固定 Capability 主版本和兼容范围；
- Agent Run 启动时固定 Catalog Release；
- 执行时禁止隐式选择 Registry 的最大版本；
- 多实例 Catalog Hash 不一致时禁止接收流量；
- 生命周期统一为 `experimental → stable → deprecated → retired`；
- 发布流水线执行 Schema 和语义兼容性扫描；
- Provider 制品、版本、哈希和来源进入 Release；
- 正式内置 Provider 使用构建期 Allowlist，不依赖可伪造名称前缀。

## 9. 开发者手册与机器目录

建立统一《AI00 Capability 开发者手册》，覆盖全部开发者可用能力，同时服务插件、Agent、MCP/API、Web 和内部领域开发者。

每个 Capability 文档必须包含：

- ID、版本、生命周期、owner 和业务说明；
- `use_when`、`do_not_use_when` 和反例；
- 各入口可用性和 AI 自动化等级；
- 权限、租户、资源、数据和委托范围；
- 完整输入输出 Schema、字段约束、枚举和示例；
- 同步、异步、本地模式及 Artifact/Operation 协议；
- 幂等、并发、超时、配额和重试规则；
- 审批、错误、补偿、Evidence 和审计语义；
- 数据分级、脱敏和 LLM 投影；
- 插件、Agent、REST 和 MCP 示例；
- 兼容性、弃用、迁移说明和更新日志。

单一事实来源为：

```text
CapabilityDescriptorV2
  ├── Runtime Catalog
  ├── Plugin SDK types
  ├── Agent Tool schema
  ├── OpenAPI/MCP descriptions
  ├── Contract tests
  └── Developer Manual
```

文档主体自动生成，业务说明和示例经过领域评审。任何 Capability 缺少封闭 Schema、权限、Exposure、数据分类、错误模型、有效示例、契约测试、负责人或生命周期信息，都不能进入 `stable`。

最终同时发布人类可读的版本化文档站/文档包和机器可读 Catalog。CI 检查 Registry 与文档双向缺失、示例漂移、SDK/Tool 版本漂移和破坏性变更。

## 10. 领域边界

### 10.1 Base

Base 负责身份、租户、项目/工作区、Artifact、协作、搜索、Operation、审批、审计、插件安装和 Catalog 等公共业务基础。Base 不解释工艺、数模或仿真语义，不代理其他领域 CRUD，也不直接导入 Device/Craft 实现。

### 10.2 Craft

核心能力族包括：

```text
craft.product_structure.*
craft.pbom.*
craft.bop.*
craft.routing.*
craft.operation.*
craft.workstep.*
craft.resource_requirement.*
craft.material_requirement.*
craft.process_parameter.*
craft.process_rule.*
craft.instruction.*
craft.execution_plan.*
craft.validation.*
craft.release.*
craft.change.*
craft.import.* / craft.export.* / craft.lineage.*
```

正式写入必须支持资源授权、乐观并发、幂等、变更理由、前后 Evidence、发布状态约束和领域 Commit。查询和校验通常允许 Agent 自主调用；草稿受控；发布、回滚和批量修改必须审批。

### 10.3 Digital Model

数模为独立领域，而不是文件附件。核心能力族包括模型、版本、结构、组件、几何元数据、属性、标注、视图、快照、变换、验证、谱系、导入、导出、转换和协作。

原始 CAD 和完整几何通过 ArtifactRef 和数据范围授权访问。AI 和插件默认获得结构摘要、元数据、属性、标注、轻量视图和受控局部结果，不获得服务器路径或任意原始文件访问。

### 10.4 Simulation

Simulation 负责环境、场景、输入、参数集、运行、批处理、状态、结果、指标、比较、报告、取消和归档。它不复制 Craft 或 Digital Model 数据。

创建环境使用服务端可验证的 `execution_plan_ref`、`model_snapshot_ref`、`parameter_set_ref` 和 `simulation_profile_ref`。运行返回 OperationRef，并记录输入版本、内容哈希、求解器版本和可复现 Evidence。

### 10.5 Local Integration 与 Device

本地集成为独立边界。云端提交签名 Operation Envelope，本地 Runtime 返回签名 Outcome。协议明确区分 accepted、claimed、running、completed、failed 和 outcome_unknown。调用只传 ModelRef/ArtifactRef，不接受本地 `file_path`。

### 10.6 Knowledge

Knowledge 负责文档、知识条目、规范、案例、事实、检索索引、修订和证据。Agent 默认使用带业务锚点、固定修订和检索 Evidence 的受控上下文检索，不直接获取全库内容。

### 10.7 领域协作

领域之间只允许：

1. 小型、低延迟前置校验的 Application Port；
2. Artifact/Resource Reference；
3. Domain Event 和事务 Outbox。

禁止跨领域 Repository、数据库表和实现类调用。

## 11. Revision & Lineage

版本、差异和谱系是跨领域一级服务，提供类似 Git 的业务体验，但不直接以数据库记录或 CAD 文件作为 Git 文件。

核心模型：Repository、Branch、Commit、Snapshot、Tag、Baseline、Release、ChangeSet、MergeRequest、Conflict 和 Lineage。

公共能力族：

```text
revision.repository.*
revision.branch.*
revision.commit.*
revision.snapshot.*
revision.diff.*
revision.merge.*
revision.conflict.*
revision.tag.* / revision.baseline.* / revision.release.*
revision.history.* / revision.lineage.* / revision.blame.*
revision.revert.* / revision.restore.*
```

公共版本服务负责 Commit、Branch、ChangeSet、合并编排、谱系和通用 Diff 协议；领域负责合法 ChangeSet、业务不变量、语义 Diff、冲突判断、应用和回滚。

Diff 必须是领域语义比较，而非原始 JSON Diff：

- Craft 识别工序移动、重排、参数、物料、资源、规则和发布变化；
- Digital Model 识别装配结构、组件替换、属性、坐标、几何摘要和几何变化；
- Simulation 比较输入版本、环境、参数、求解器、指标和结果；
- Ontology 比较概念、层级、属性、关系、约束、术语、映射和推理规则。

统一 `SemanticDiff` 包含 summary、统计、changes、impact、conflicts、visual_artifacts 和 evidence。大型几何 Diff 异步执行。

合并采用三方比较。受保护分支、正式基线、发布和回滚必须审批。AI 可以读取、解释、提出合并或冲突建议，但不能默认解决高风险冲突。

存储采用 OceanBase 中的不可变 Commit/索引、OIS 中的结构化 ChangeSet/Snapshot/大型 Artifact，并通过“最近 Snapshot + 后续 ChangeSet”恢复。正式基线支持内容哈希、签名和防篡改校验。

## 12. Semantic & Ontology

Ontology 是独立语义领域，不是 Base 字典或 Knowledge 附属模块。它负责概念、类型、属性、关系、约束、分类、术语、单位、映射和推理模型；Knowledge 负责具体内容和事实。

核心能力族：

```text
ontology.catalog.* / ontology.namespace.*
ontology.concept.*
ontology.relation_type.*
ontology.property_definition.*
ontology.constraint.* / ontology.taxonomy.* / ontology.term.* / ontology.unit.*
ontology.mapping.* / ontology.inference_rule.*
ontology.proposal.*
ontology.version.* / ontology.diff.* / ontology.merge.* / ontology.release.*
ontology.validation.* / ontology.inference.* / ontology.impact.*
```

业务记录使用稳定 ConceptRef，避免仅保存名称。Craft、Digital Model 和 Simulation 分别使用本体定义工艺语义、数模语义映射、参数单位和仿真对象语义。

AI 可检索概念、解释术语、查询关系、验证对象、提出映射和本体 Proposal；修改正式概念、约束、单位、关系、发布和激活必须审批。AI 不能批准自己的 Proposal。

本体变更直接接入 Revision，发布前执行引用、数据、规则、Capability、插件和 Agent 工作流影响分析。插件可以查询本体、提交 Proposal、提供受控可视化或声明式验证扩展，不能直接修改已发布本体或执行任意推理代码。

## 13. 插件宿主

### 13.1 Manifest V2

Manifest 至少声明插件身份、版本、发布者、包哈希、签名、宿主版本、必需/可选 Capability、版本范围、资源范围、数据范围、网络策略、存储策略、UI 扩展、事件订阅和升级策略。

Manifest 只声明需求。有效授权是以下交集：

```text
Capability 允许 Plugin
∩ Manifest 声明
∩ 租户管理员授权
∩ 当前用户权限
∩ 挂载会话资源范围
∩ 数据分类策略
```

### 13.2 PluginMountSession

宿主签发绑定插件 ID、版本、安装实例、包哈希、租户、用户、Capability、资源范围、数据范围、过期时间和撤销版本的挂载会话。插件不能读取长期用户 JWT。

插件通过 Host SDK 调 Gateway，获得完整 CapabilityResultV2。高风险调用返回 ApprovalChallenge，由宿主显示原生确认界面并完成受控重试，确认凭证不交给插件代码。

插件包必须经过签名、安全扫描、权限审查、安装授权、更新和撤销治理。沙箱不能替代最小数据权限：插件获得的数据仍可能被外传，因此数据分类和范围授权是主要边界。

挂载资源访问必须覆盖完整页面会话并支持实时撤销，避免短期静态资源令牌过期导致懒加载失败。宿主需要控制导航、下载、剪贴板和网络策略；即使 iframe 使用 opaque origin/CSP，也不能把沙箱视为已授权数据不会外传的保证。

## 14. AI Agent Runtime

Runtime 持久化：AgentDefinition、AgentRun、AgentRunStep、AgentRunEvent、ToolSelection、CapabilityInvocation、ApprovalRequest、DelegationGrant、BudgetState、Checkpoint 和 RunOutcome。

状态机：

```text
created → planning → running → awaiting_approval → resuming → completed
                          └→ failed / cancelled / expired / outcome_unknown
```

Runtime 不允许启动时 DDL，所有表由 Migration 管理。服务重启后必须恢复 Run。

个人会话、团队会话和群组会话需要不同的参与者模型。群组 Run 必须保存 tenant、channel、member/role 快照和授权发起者，不能仅用一个 owner user 代表所有参与者。Runtime 对外监听、服务间认证和回调端点遵循零信任边界，不允许因内网部署而省略服务身份。

### 14.1 DelegationGrant

用户启动 Run 时签发绑定用户、租户、Agent 定义、Run、Capability、资源、数据、最大副作用等级、预算和期限的委托。Runtime 不长期转发原始用户 JWT。长时间任务在高风险写入前重新验证权限和认证新鲜度。

### 14.2 Tool Selection

不能把数百项工具一次性注入模型。Runtime 根据用户目标检索 User Function Registry 和 Catalog，按领域、权限、资源、数据与自动化策略筛选本次 Run 的有限 Tool Set，并保存 Capability 版本、Catalog Release、Schema Hash 和选择理由。

### 14.3 自动化等级

- A0：仅人工直接操作；
- A1：AI 可发现但不可调用；
- A2：AI 可自主只读；
- A3：AI 可创建建议或草稿；
- A4：AI 可执行低风险、可撤销写入；
- A5：每次人工审批；
- A6：双人或管理审批。

等级可根据资源状态和数据分类动态提高，不能仅依据 HTTP 动词或读写分类。

### 14.4 审批

Gateway 返回 Challenge 后，Runtime 创建持久化 ApprovalRequest 并暂停 Run。审批绑定 Capability/版本、规范化 Payload Hash、用户、租户、Run、资源、消费者、策略版本、副作用和期限。模型不能看到或生成审批令牌，Worker 不能伪造人类确认。

### 14.5 LLM 数据投影

进入模型的数据必须按 `LLMProjectionPolicy` 做字段最小化、脱敏、长度限制、摘要化、来源保留和不可信内容标记。工具结果中的业务文本不得作为系统指令。完整 Artifact 只以引用和受控摘要进入上下文。

## 15. REST、MCP、Worker 与 Local Runtime

REST/OpenAPI 和 MCP 都是 Gateway 适配器，不拥有独立业务实现。MCP 固定 Catalog Release，不临时生成漂移目录，不转发长期用户 Token，并支持 ArtifactRef、OperationRef、分页和审批挑战。

Worker 使用服务身份和明确委托，只能执行固定任务类别，不能自行提升为用户或签发人类审批。

Local Runtime 使用设备注册身份、签名协议、重放保护、密钥轮换和受控 Outcome。云端入队不等于本地成功；设备重复执行必须有领域级去重。

跨语言签名必须规定正式的 Canonical JSON、字符编码、字段排序、数字和时间格式，并用 Python/C# 共享测试向量验证。桌面端本地 Ledger 需要容量、完整性、恢复和云端对账策略；崩溃后处于 started 状态的操作进入 outcome_unknown，不能静默重放。原始异常、文件路径、管道名和密钥材料不得返回云端消费者。

## 16. 配额、幂等、Outcome 与审计

限流和配额下沉到 Gateway，维度包括租户、用户、插件安装、Agent Run、API Client、Capability、资源和设备。Capability 使用成本权重，并限制 Agent 步骤、并发、Token、Artifact 读取、写入次数和仿真/设备容量。

幂等范围至少绑定：

```text
tenant + consumer + capability + major_version
+ idempotency_key + normalized_payload_hash
```

对外语义是可证明的 at-least-once 和领域去重，不宣称跨数据库与外部设备的 exactly-once。

关键数据库写入在同一领域事务内保存业务变更、领域 Commit/ChangeSet、Capability Outcome 和 Audit Outbox。外部操作记录 started、accepted、completed、failed、outcome_unknown 和补偿状态。高风险写入在可靠审计不可用时拒绝。

审计记录用户、消费者、插件安装/Agent Run、授权和审批决策、Schema、Payload Hash、资源、结果、投影策略、配额、Commit、Operation、异常和重试。资源引用由 Descriptor 的 Resource Selector 生成，不依赖启发式字段扫描。

## 17. 迁移策略

采用按用户功能纵切片的绞杀式迁移：

1. 冻结新架构债务：禁止新增 Web 专用业务 Router、Registry 直调、自报身份、运行时 DDL、跨域 Repository、原始路径和手工 Agent Schema。
2. 建立完整 User Function Registry，盘点 Web、REST、Capability、Job、Plugin、Agent、MCP、Local Runtime 和导入导出。
3. 建立 V2 Kernel、Identity Broker、Gateway 和标准引用；V1 仅通过临时 Adapter 接入。
4. 迁移身份授权、Artifact、Operation、Revision、Ontology、Knowledge Evidence、审批审计、Plugin Mount 和 Agent Run 等跨域基础。
5. 先迁只读/校验，再迁草稿/可撤销写入，再迁正式写入，最后迁设备和本地高风险操作。
6. Web 使用统一 Capability Client；旧 REST 只作为调用 Gateway 的兼容 Adapter。
7. 观察无消费者后停止旧写入，最终删除旧 Router、双 URL、旧 Registry 和旁路实现。

数据迁移采用扩展结构、历史回填、双读校验、新链路主写、切换读取、停止旧写和观察清理。避免长期双写；确需派生时使用唯一主写和 Outbox。

每个切片使用可按租户、用户、消费者、Capability 版本控制的 Feature Flag，支持影子只读、结果对比和快速关闭。Catalog Release 在发布前冻结，多实例 Hash 一致后才接流量。

## 18. 测试与验证

### 18.1 契约测试

验证封闭 Schema、示例、错误、标准引用、版本、Schema Hash，以及 Plugin SDK、Agent Tool、OpenAPI、MCP 和文档一致性。

### 18.2 授权矩阵

覆盖角色 × 租户 × 消费者 × 资源 × 数据分类 × Capability × 自动化等级，包含来源伪造、越租户、插件提权、委托越权、授权撤销和审批重放。

### 18.3 领域测试

覆盖 Craft 不变量、数模结构、Ontology 引用、Simulation 可复现性、Revision 三方合并、单位量纲、事件顺序和去重。

### 18.4 可靠性测试

覆盖并发幂等、提交后网络失败、Outbox 故障、Worker/Agent/Local Runtime 重启、设备离线、未知结果、多实例目录漂移和审批期间权限变化。

### 18.5 安全测试

覆盖 Schema 绕过、Artifact 猜测、供应链攻击、Prompt Injection、敏感数据进入模型、本地路径泄漏、未审批合并和设备操作重放。

### 18.6 真实端到端

至少覆盖 Web、Plugin、Agent、MCP、Local Runtime 五类入口，以及 Craft→Revision→Simulation、Digital Model→Diff、Ontology Proposal→Release。验收必须使用真实 OceanBase 兼容环境、OIS、JWT/OAuth 和多实例部署，不能只依赖内存替身。

### 18.7 必须交付的测试用例资产

本次重构的完成物不仅是实现代码，还必须包含可重复执行、可追溯到 Capability 和 Catalog Release 的测试用例系列。测试用例、Fixture、Golden File、模拟适配器、环境准备脚本和执行说明必须纳入版本控制，不能只保留人工测试记录。

每个进入 `stable` 的 Capability 至少具备：

1. 正常成功用例；
2. 输入 Schema、业务规则和前置条件失败用例；
3. 未认证、无权限、跨租户、超出资源范围和超出数据范围用例；
4. 不允许的消费者入口和自动化等级用例；
5. 输出 Schema、Evidence、Correlation 和审计记录用例；
6. Provider Contract 与各开放消费者的 Consumer Contract 用例；
7. 版本固定、Schema Hash 和兼容性用例；
8. 超时、取消和结构化错误用例。

写入 Capability 还必须具备：

- 幂等重试和不同 Payload 复用幂等键的冲突用例；
- 乐观并发、重复提交和并发竞争用例；
- 审批签发、拒绝、过期、重放和审批期间权限变化用例；
- 领域 Commit、ChangeSet、Outcome 和 Audit Outbox 一致性用例；
- 提交后响应丢失、重试和 `outcome_unknown` 用例；
- 能够补偿或 Revert 时的恢复用例。

异步、本地、设备和仿真 Capability 还必须覆盖：

- accepted、claimed、running、completed、failed、cancelled 和 outcome_unknown 状态迁移；
- Worker、Agent Runtime、Gateway 或 Local Runtime 重启恢复；
- 离线、重复领取、重复回执、乱序回执和过期操作；
- 跨语言 Canonical JSON、签名、重放保护和共享测试向量；
- Artifact 缺失、损坏、越权和内容哈希不一致。

Revision、Diff 和 Ontology 必须分别提供：

- 分支、Commit、Snapshot、Baseline 和历史恢复用例；
- 三方合并、字段/结构/顺序/语义冲突和受保护分支用例；
- Craft、Digital Model、Simulation、Ontology 的语义 Diff Golden Cases；
- 概念稳定 ID、重命名、弃用、约束变化、影响分析和 Proposal 审批用例；
- 大型模型 Diff 的异步、分页、可视化 Artifact 和资源上限用例。

插件和 Agent 测试套件必须包括：

- Manifest 权限交集、版本范围、安装身份、Mount Session 过期与实时撤销；
- 插件伪造 ID、跨安装复用令牌、结果截断回归和宿主审批闭环；
- Agent ToolSelection、Delegation、预算、暂停、恢复、取消和审批闭环；
- Prompt Injection、不可信工具结果、敏感数据投影和上下文大小限制；
- Web、Plugin、Agent、REST 和 MCP 对同一 Capability 的业务结果一致性。

### 18.8 测试分层与发布门禁

测试按以下层级运行：

```text
本地/每次提交：Schema、单元、Provider Contract、架构边界
Pull Request：消费者契约、授权矩阵、领域集成、迁移静态检查
Nightly：并发、故障注入、多实例、插件/Agent/MCP 端到端
Release Candidate：真实 OceanBase、OIS、JWT/OAuth、Local Runtime 全链路
正式发布前：目标 Catalog Release 的完整验收与安全回归
```

测试报告必须记录 Git Commit、Catalog Release、Schema Hash、数据库 Migration 版本、Provider 制品版本和测试环境。失败、跳过或未覆盖的强制用例都会阻断 Capability 进入 `stable` 或阻断对应入口开放。

破坏性、设备和大规模测试只能在明确隔离的测试租户、测试数据库和测试设备上运行；测试工具必须拒绝生产连接。性能与容量基线至少覆盖 Catalog 查询、Gateway 延迟、大型 Diff、Artifact 传输、Agent 并发、仿真队列和审计 Outbox 积压。

开发者手册中的所有示例都必须作为可执行文档测试运行。示例与实际 Schema、SDK 或结果契约不一致时，CI 直接失败。

## 19. 风险控制

| 风险 | 控制 |
| --- | --- |
| 路由一比一转换导致 Capability 膨胀 | User Function Registry、业务结果建模、领域组合能力 |
| Base 再次成为万能层 | 依赖方向规则和架构测试 |
| 插件可发现被误解为无限开放 | Manifest、租户授权、资源/数据交集 |
| AI 工具过多和误调用 | Catalog 检索、Run 级 ToolSelection、预算 |
| AI 写入失控 | 自动化等级、持久化审批、Revision 和补偿 |
| 双写造成数据分叉 | 单一主写、Outbox、明确退出期限 |
| 幂等被误认为 exactly-once | Outcome、领域去重、unknown 状态 |
| 数模/仿真结果过大 | ArtifactRef、OperationRef、分页、摘要 |
| 版本存储膨胀 | ChangeSet、Snapshot、归档和保留策略 |
| 本体变更破坏业务 | 兼容性检查和影响分析 |
| 多实例 Catalog 漂移 | 不可变 Release 和流量门禁 |
| 旧 REST 长期不退出 | 使用监测、退役期限、CI 禁增 |
| 插件供应链与数据外传 | 签名、扫描、撤销、最小数据权限 |
| Prompt Injection | 不可信内容隔离、投影和执行前策略检查 |
| 本地动作结果未知或重复 | Operation 状态机、设备去重、人工处置 |
| 外部服务无法复现发布 | 全部纳入源码、CI、制品和 owner 治理 |

## 20. 完成标准

只有同时满足以下条件，V2 重构才可视为完成：

1. 全部稳定用户业务功能进入覆盖矩阵并映射正式 Capability；
2. Base、Craft、Digital Model、Simulation、Ontology、Knowledge、Revision 和 Local Integration 的目标能力族具备 owner 和契约；
3. 插件和 Agent 能发现全部稳定能力，且每项有明确执行与自动化策略；
4. Web 已使用相同 Capability，不再依赖独立业务实现；
5. PluginMountSession、DelegationGrant 和可信服务身份取代自报来源；
6. 高风险写入经过可信审批，Agent Run 可暂停、恢复、取消和追踪；
7. 版本、语义 Diff、本体和影响分析贯穿主要业务对象；
8. 大型数据与长任务使用 ArtifactRef 和 OperationRef；
9. Outcome、领域写入和 Audit Outbox 具备可靠一致性；
10. 开发者手册与 Catalog、SDK、Agent Tool、OpenAPI 和 MCP 自动同步；
11. 每项稳定 Capability 的强制测试用例、Fixture、Golden Case 和执行说明已经纳入版本控制；
12. 真实环境契约、安全、故障恢复、性能容量和多入口端到端测试通过，并生成绑定 Catalog Release 的验收报告；
13. Registry 直调、来源 Header、插件结果截断、运行时 DDL、旧 REST 业务实现和未版本化外部服务已退出，或存在已批准的短期退役期限。

## 21. 已批准决策与实施前约束

本文已经确认以下不可逆设计方向：

- 采用领域纵切片，而非保留入口专用业务实现；
- 所有稳定用户业务功能必须 Capability 化并对插件、Agent 可发现；
- 统一 Gateway 是唯一执行安全边界；
- Revision & Lineage、Semantic & Ontology 是一级跨领域能力；
- 插件使用 Mount Session，Agent 使用持久化 Run 和 Delegation；
- 开发者手册和机器 Catalog 是 Capability 稳定发布的强制产物；
- 旧 REST、旧 Registry 直调和可信客户端 Header 最终退役。

实施计划必须以本设计为约束，先建立覆盖基线和 Kernel，再按风险递增迁移领域纵切片。未经新的架构决策，不得通过批量开放 `plugin_callable`、复制 Agent Tool 或给插件/Agent 直接数据库权限来缩短路径。
