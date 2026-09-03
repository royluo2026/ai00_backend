# 数模仿真域与 AI00 Connector Capability 治理设计

## 1. 文档状态

- 设计路径：架构级新子系统与跨域契约调整。
- 变更分类：新 Capability 为主；现有 `simulation.environment.create@1` 的语义不足以覆盖真实环境搭建，采用并行新能力而不是静默改义；现有 `vismockup.*@1` 直出能力需要兼容收口与后续退役。
- 当前结论：AI 建议稿，等待领域负责人和可信 `super_admin` 对精确业务定义作出决定。
- 基线：`b6586353a9ded5329c3d06240713baa1d19e2983`。
- 非目标：本文不授权实现、发布、生产安装、生产数据写入或 Capability 审批。

治理状态保持独立：

- `machine_passed`: `unverified`
- `human_approved`: `false`
- `runtime_verified`: `false`
- `advisory`: `true`

## 2. 目标和一期范围

本设计建立两部分系统：

1. **AI00 内部数模仿真域**：拥有环境定义、跨域编排、任务状态、权限、审计和结果关联。
2. **AI00 Connector**：安装在用户 Windows 工作站上的受治理本地执行 Provider，负责连接 VisMockup 以及未来的本地软件、内网系统或经批准的 MCP Server。

一期交付只完成：

- 从工艺域取得受治理、不可变的工艺执行结构树；
- 从当前 VisMockup 文档取得已打开 BOM 的结构快照及其 Teamcenter/数模链接标识；
- 根据工艺中的工具、设备、工装代码解析对应数模号和可加载数模制品；
- 将产品 BOM、工具、设备、工装绑定成可复现的仿真环境；
- 按工艺顺序倒序驱动 VisMockup 内部视图；
- 使用 VisMockup `ActiveView.CaptureImage` 生成截图；
- 上传截图制品，并通过工艺域 Capability 关联到对应工序截图区。

所有其他数模分析均不在一期实现，但扩展接口必须支持未来按独立、版本化操作增加分析能力。不得以一个任意方法调用接口代替未来治理。

## 3. 核心架构原则

### 3.1 云端编排，本地执行

AI00 决定“为什么做、对什么业务对象做、按什么顺序做、谁有权做、结果归属哪里”。AI00 Connector 决定“如何在这台机器上安全、稳定地调用目标软件”。

Capability 定义、业务规则、授权、审批、任务编排、审计和最终业务写入均留在 AI00。COM 生命周期、用户会话、STA 串行化、VisMockup 进程连接、内部截图、文件暂存和本机恢复均留在 AI00 Connector。

### 3.2 Connector 是 Provider，不是第二个业务中心

AI00 Connector 不保存工艺、BOM、知识库或仿真环境的可写主数据副本，不自行决定工艺顺序，不自行匹配业务代码，不直接写工艺域数据库，也不批准 Capability。

Connector 只执行 AI00 下发的、已授权且签名的不可变执行计划。它可以进行技术校验和安全拒绝，但不能改变计划的业务含义。

### 3.3 不开放任意 COM、脚本或 MCP 调用

禁止提供 `execute_com(method, args)`、`run_script(text)`、任意 `getattr` 或不经映射的 MCP `tools/call`。每个可执行操作必须在 Adapter 清单中有固定 ID、版本、输入输出 Schema、超时、并发模型、幂等语义和错误映射，并由 AI00 侧受治理 Capability 或受治理执行计划引用。

### 3.4 不修改 Teamcenter/BOM 权威数据

一期仿真环境只在当前 VisMockup 会话中装配和控制场景，不向 Teamcenter 主 BOM 回写。任何未来的 Teamcenter 写入必须由 Teamcenter/数模权威域新增独立 Capability，不得复用 Connector 场景操作绕过治理。

## 4. 总体组件

```text
Web 用户
   |
   v
AI00 Capability Gateway
   |
   +-- 工艺域：工艺执行计划、工序截图关联
   +-- 知识域：资源代码 -> 数模引用解析
   +-- 数模域：数模版本和制品解析
   +-- 数模仿真域：环境编排、运行、证据与审计
   +-- 设备域：设备注册、租约、Connector 健康与命令传输
   |
   | 出站 HTTPS 轮询/长连接；签名计划与限时制品地址
   v
AI00 Connector（单工作站、单绑定用户）
   +-- Windows Service：认证、心跳、租约、上传、升级
   +-- SessionHost：登录用户会话、单 STA 执行队列
   +-- Adapter Host：清单、版本和白名单分派
   +-- VisMockup Adapter：COM 与内部截图
   +-- MCP Adapter：未来连接获准的本地/内网 MCP Server
```

## 5. 第一部分：AI00 内部数模仿真域

### 5.1 领域职责

数模仿真域拥有：

- 仿真环境 Manifest 的身份、版本、哈希和生命周期；
- 工艺操作与产品/资源数模的绑定结果；
- 环境预检、物化任务、倒序截图任务和步骤状态；
- Connector 目标设备选择和兼容性要求；
- 跨域调用编排、补偿、重试判定和结果证据；
- 截图与环境、工序、运行之间的追溯关系。

数模仿真域不拥有：

- 工艺顺序和工序截图区，归工艺域；
- Teamcenter/BOM 与数模版本主数据，归数模/集成权威域；
- 工具、设备、工装业务代码的知识映射，按本设计归知识域；
- 工作站身份、Connector 租约和设备密钥，归设备域；
- VisMockup COM 实现，归 AI00 Connector Provider。

### 5.2 环境 Manifest

一期环境必须由不可变 `SimulationEnvironmentManifestV1` 表示，至少包含：

- `environment_id`、`environment_version`、`manifest_hash`；
- 工艺来源：`bop_version_gid`、revision、content hash、execution-plan URI；
- 当前 BOM 来源：文档标识、根节点标识、结构快照 hash、Teamcenter/数模引用；
- `product_bindings[]`：工艺产品引用到已打开 BOM 节点的确定绑定；
- `resource_bindings[]`：工具、设备、工装代码到数模版本/制品的确定绑定；
- `operations[]`：稳定工序 ID、sequence、前驱、当前资源和期望场景状态；
- Connector 约束：协议主版本、Adapter ID/主版本、操作合同 hash；
- 创建者、租户、创建时间、敏感等级和审计引用。

环境一经发布不可原位修改。工艺、BOM、知识映射或数模制品发生变化时创建新环境版本并重新计算 hash。

### 5.3 一期业务 Capability

#### 5.3.1 复用现有能力

- `digital_model.version.get@1`
- `digital_model.component.search@1`
- 设备注册、读取和撤销能力

现有 `simulation.environment.create/get/search/archive@1` 只表达由工艺计划、数模快照、参数集和求解器配置组成的旧环境，不能表达当前 VisMockup BOM、资源数模绑定或 Connector 兼容约束。不得在 `@1` 上静默改变业务语义或输出 Schema。

#### 5.3.2 新增或补齐能力

| Capability | 所有者 | 原子业务效果 |
|---|---|---|
| `simulation.environment.compose@1` | simulation | 从已固定的工艺、BOM 和资源数模解析结果生成一个不可变环境版本，或返回完整未解析项而不创建环境。 |
| `simulation.environment.manifest.get@1` | simulation | 读取一个可见的、不可变 Connector 环境 Manifest 版本。 |
| `simulation.environment.manifest.search@1` | simulation | 有界查询调用者可见的 Connector 环境 Manifest。 |
| `simulation.environment.manifest.archive@1` | simulation | 归档一个 Connector 环境身份，不修改其历史 Manifest 版本。 |
| `simulation.environment.preflight@1` | simulation | 验证指定环境在目标 Connector/VisMockup 上可物化，并返回无副作用的兼容性报告。 |
| `simulation.environment.materialize@1` | simulation | 创建一次异步物化运行，使指定环境在目标 VisMockup 会话中成为已验证场景。 |
| `simulation.capture_run.start@1` | simulation | 为一个已物化环境创建倒序工艺截图运行。 |
| `simulation.capture_run.get@1` | simulation | 读取运行及逐工序状态、制品和错误。 |
| `simulation.capture_run.cancel@1` | simulation | 请求停止尚未开始的步骤，不撤销已经完成并关联的截图。 |
| `simulation.capture_step.retry@1` | simulation | 在输入版本未变化且结果可判定时，为一个失败步骤创建新尝试。 |
| `knowledge.resource_model_mapping.resolve@1` | knowledge | 将一组类型化资源代码解析为确定、版本固定的数模引用，并显式返回未找到或歧义项。 |
| `craft.process_screenshot.attach@1` | craft | 幂等地将一个验证过的截图 ArtifactRef 关联到指定工艺版本和工序截图区。 |

工艺执行树应复用或补齐 `craft.execution_plan.get@1`。如果运行 Registry 中没有该能力或其输出不含稳定工序 ID、顺序、依赖、产品和资源代码，则这是工艺域阻断 Finding，不能由 simulation 直查 `workmanship_bop_*` 补偿。

从 VisMockup 读取当前 BOM 是 Connector 的受控 Provider 操作，不是 AI00 服务端读取本地状态的数据库 Capability。它只能在环境 compose 的预检会话或显式设备操作中执行，并把带 hash 的快照回传给 simulation。

### 5.4 原子性决定

环境 compose 是一个业务效果，因为只有“全部确定绑定并产生不可变 Manifest”才有业务价值；存在歧义或缺失时必须整体不创建。它不负责打开软件或修改本地场景。

环境 materialize 与截图运行必须分开：二者权限、失败、重试和审计均可独立发生。单张内部截图是 Connector 原子操作；一次倒序截图运行是 simulation 管理的长事务/工作流，不伪装成单数据库事务。

工序截图关联归工艺域且逐张幂等提交。某一步关联成功后，即使后续步骤失败也不删除已成功结果；重新运行产生新截图版本，由工艺域决定当前展示指针和历史保留策略。

### 5.5 环境搭建数据流

1. 用户选择工艺版本和目标 Connector，提交唯一幂等键。
2. simulation 调用工艺域取得不可变执行计划，不读取工艺表。
3. simulation 请求目标 Connector 通过 VisMockup Adapter 取得当前活动文档 BOM 快照。
4. simulation 验证 BOM 根标识、结构 hash、节点上限和来源标识。
5. simulation 从工艺操作收集产品引用和类型化资源代码。
6. 产品引用通过数模域/当前 BOM 快照解析；资源代码通过知识域能力解析成不可变数模引用。
7. 任一引用未找到或歧义时返回完整问题列表，不创建半成品环境。
8. 全部确定后，simulation 生成、hash 并持久化 Manifest。
9. materialize 能力生成签名 Connector ExecutionPlan；Connector 校验并在本地会话中挂接缺失资源数模、建立节点绑定并验证最终场景 hash。
10. Connector 回报签名结果；simulation 将运行状态更新为 `materialized` 或明确失败状态。

### 5.6 倒序截图语义

一期使用确定规则：按 `(sequence DESC, operation_id DESC)` 遍历工序；不按数据库物理顺序或树展示顺序推断。

每个工序的期望场景由 Manifest 显式给出：

- 产品可见集为 sequence 小于等于当前工序的累计产品绑定；
- 工具、设备、工装只显示当前工序绑定；
- 未绑定节点保持环境基线状态，不允许 Adapter 自行猜测；
- 相机、背景、分辨率和图像格式来自版本化 capture profile；
- 每次设置场景后读取并校验场景摘要，再调用 VisMockup 内部 `CaptureImage`。

每张截图的业务键为 `(environment_version, capture_run_id, operation_id, attempt)`。上传完成后，AI00 调用 `craft.process_screenshot.attach@1`，工艺域以 `(bop_version_gid, operation_id, capture_run_id)` 作为关联幂等范围。

### 5.7 状态机

环境：

```text
draft -> composed -> materializing -> materialized
                    -> materialize_failed
composed/materialized -> archived
```

截图运行：

```text
queued -> preflighting -> running -> completed
                      \-> blocked
running -> partially_completed | failed | cancelling -> cancelled
```

`outcome_unknown` 是独立状态，必须查询 Connector 本地账本和服务端 OperationRef 后再决定，禁止盲目重试。

### 5.8 持久化边界

simulation 领域在现有 `workmanship_sim_*` 所有权内新增版本化表或等价结构：

- environment manifest/version；
- product/resource binding；
- materialization run；
- capture run、step attempt 和 artifact reference。

设备域继续拥有 `workmanship_runtime_*` 的设备、命令、租约和回执。工艺、知识和数模数据只保留不可变引用、版本和 hash，不复制为可写主数据。

## 6. 第二部分：AI00 Connector

### 6.1 产品定位

安装包和用户可见名称统一为 **AI00 Connector**。它不是桌面版 AI00，也不是独立业务应用。管理员可安装；一期每台工作站只允许绑定一个 AI00 用户和一个活动 SessionHost。

Connector 由以下最小组件组成：

- `Connector Service`：Windows Service，负责出站认证、心跳、租约、制品下载/上传、更新与恢复；
- `SessionHost`：在绑定用户的登录会话中自动启动，维护单一 STA 队列；
- `Adapter Host`：校验 Adapter 清单和合同 hash，分派白名单操作；
- `VisMockup Adapter`：唯一的一期业务 Adapter；
- 简单托盘：配对、连接状态、版本、诊断和解绑，不承载业务编排。

不开放 localhost HTTP 端口。Service 与 SessionHost 仅通过限当前用户的 named pipe 通信。

### 6.2 单用户和并发模型

- 一个设备只绑定一个 AI00 用户；绑定变更必须先撤销旧设备凭据并重新配对。
- 同时只允许一个活动 SessionHost；第二个用户会话或第二实例返回 `interactive_session_conflict`。
- 每个 VisMockup Adapter 只有一个串行写队列，不并行驱动 COM。
- 可并行的未来 Adapter 必须在自己的清单中声明并发上限，不能继承 VisMockup 的假设。

### 6.3 VisMockup 运行条件

截图使用 VisMockup 内部 `ActiveView.CaptureImage`，不是 Windows 屏幕抓取。因此：

- 允许 Windows 锁屏和显示器关闭；
- 必须保持绑定用户已登录、SessionHost 存活、VisMockup 进程存活且系统未睡眠/休眠；
- 活跃任务期间 Connector 使用 Windows 原生 Power Request 临时阻止系统睡眠，结束、取消和异常退出路径均释放；
- 不永久修改用户电源计划；
- 正式发布前必须在真实 VisMockup 机器验证锁屏、显示器关闭和 RDP 断开场景。未经实机验证不得设置 `runtime_verified=true`。

心跳报告 `user_session_present`、`session_host_ready`、`system_awake`、`vismockup_process_ready` 和 `document_ready`，不把 `screen_unlocked` 当作健康条件。

### 6.4 Adapter 扩展接口

每个 Adapter 发布签名清单：

- `adapter_id`、语义版本、发行者和签名；
- 支持的 Connector protocol 范围；
- 目标产品名称、检测方式和已验证版本范围；
- operation ID、主版本、输入/输出 Schema hash；
- 是否要求交互用户会话、管理员权限或本机文件；
- 串行/并行模型、超时、取消和幂等语义；
- Artifact 输入输出策略、数据分类和日志脱敏策略；
- 规范化错误代码映射。

一期内置 operation：

| Operation | 效果 |
|---|---|
| `vismockup.application.probe@1` | 返回进程、COM、文档和产品版本健康状态。 |
| `vismockup.document.snapshot@1` | 读取当前活动文档的有界 BOM 结构、节点稳定标识和来源引用。 |
| `vismockup.model.attach@1` | 把已校验的数模制品挂接到当前场景并返回节点绑定。 |
| `vismockup.scene.apply@1` | 将完整期望可见集、当前资源集和 capture profile 应用到场景。 |
| `vismockup.scene.verify@1` | 读取场景摘要并与期望 hash 比较，无业务副作用。 |
| `vismockup.view.capture@1` | 调用内部 CaptureImage，产生本地截图 Artifact。 |

`launch`、连接 COM、下载文件、AllNodesOn/Off、选择节点和重试 COM 调用属于 Adapter 内部实现步骤，不分别上升为用户可见业务 Capability，除非以后证明它们具有独立业务效果、授权和消费者。

### 6.5 MCP 扩展

Connector 预留 `McpAdapter`，使其可以作为 AI00 与经批准 MCP Server 之间的本地执行桥，但边界如下：

- Connector 可作为 MCP Client 连接本机 stdio、受控本机端口或获准的内网 MCP Server；
- MCP `tools/list` 只用于发现候选工具，不能自动获得 AI00 Capability 身份或权限；
- 每个工具必须经过管理员 allowlist，并映射到固定 AI00 Capability/Connector operation、主版本和 Schema hash；
- MCP 工具返回仍需通过 AI00 的输出 Schema、敏感数据和 Artifact 校验；
- 禁止把任意 MCP 工具列表直接暴露给网页、插件或 Agent；
- 凭据按 Adapter 隔离，使用 DPAPI/Windows Credential Manager 或组织证书，不进入配置文件、日志、计划或截图。

飞书等纯云 SaaS 默认由 AI00 服务端集成/MCP Provider 连接，以获得集中授权、稳定运行和多用户隔离。仅当飞书连接明确依赖用户本机登录态、桌面客户端或客户内网出口时，才使用 AI00 Connector 的 MCP Adapter；该部署仍需独立 Capability、凭据和审计设计。

### 6.6 Connector ExecutionPlan 协议

AI00 下发 `ai00.connector.execution-plan.v1`，至少包括：

- `plan_id`、`operation_id`、tenant/user/device；
- 业务 Capability ID、版本 GID、business-definition hash；
- Connector protocol、Adapter ID/版本范围、operation contract hash；
- 有序步骤、显式依赖、每步 payload hash 和最大执行时间；
- 输入 ArtifactRef、期望输出、上传授权和大小限制；
- 幂等键、签发时间、过期时间、租约和取消策略；
- AI00 服务端签名和 key ID。

Connector 必须先完整校验计划，再开始任何副作用。Adapter 不支持版本、合同 hash 不一致、用户/设备不一致、计划过期或签名失败时必须 fail closed。

每一步回执包含开始/结束时间、状态、规范错误、结果 hash、Artifact 元数据、Adapter/产品版本和本地账本序号，并由设备密钥签名。日志不得包含模型文件内容、凭据或未脱敏路径。

### 6.7 文件和截图上传

截图先写入 Connector 管理的临时目录，计算 SHA-256、MIME、尺寸和字节数。Connector 使用 AI00 下发的一次性限时上传地址直传 Artifact 存储，成功后回报 ArtifactRef；它不直接调用工艺数据库或决定工序关联。

上传未确认时保留本地文件和账本，状态为 `outcome_unknown`。服务端通过 upload session 查询确认后再补交回执；禁止重新截图来猜测结果。保留期到达后按受控清理策略删除，不进入回收站或用户目录。

### 6.8 安装、升级和凭据

- 提供签名 MSI；管理员安装 Service，绑定用户登录时自动启动 SessionHost。
- 设备密钥使用 DPAPI 或证书库保护；示例 JSON 永不存储真实密钥。
- Connector、Adapter 和 manifest 均校验 Authenticode/组织签名。
- 更新采用签名 manifest、SHA-256、drain、切换、健康检查和失败回滚；正在执行的计划不能被强制替换。
- 升级后重新广告完整版本矩阵；AI00 不向不兼容设备派发任务。

## 7. 跨域所有权和契约

| 数据/效果 | 权威所有者 | 消费方式 |
|---|---|---|
| 工艺结构、顺序、工序截图区 | craft | Gateway Capability |
| 资源代码到数模引用知识 | knowledge | `knowledge.resource_model_mapping.resolve@1` |
| 数模身份、版本、结构和制品 | digital_model | Gateway Capability / ArtifactRef |
| 环境 Manifest、物化和截图运行 | simulation | simulation Capability |
| 设备、租约、命令传输和 Connector 健康 | device | device Capability/受控 runtime transport |
| VisMockup 现场副作用 | AI00 Connector Provider | 签名 ExecutionPlan 内的白名单 operation |

跨域失败不得退化为直接 SQL、内部 Provider 调用或浏览器直连 Connector。所有版本引用必须带稳定 ID 与 hash。

## 8. 权限、确认和审计

- compose：要求读取指定工艺、数模、知识映射和目标设备快照的权限；创建环境需要 simulation write 权限和幂等键。
- materialize：要求环境、设备和本地执行权限；首次或高风险数模加载需要用户确认。
- capture run：要求读取环境、执行 Connector 操作及向目标工艺版本附图的权限。
- attach screenshot：由工艺域重新校验调用者对目标版本/工序的写权限，不能信任 simulation 的声明。
- Connector 本地设备凭据只证明设备身份，不替代最终用户授权或 Delegation。
- 审计链串联 user request、Capability OperationRef、Connector plan/step、ArtifactRef 和工艺关联事件。

## 9. 稳定错误模型

除 Gateway 通用错误外，至少定义：

- `execution_plan_unavailable`
- `active_document_unavailable`
- `bom_identity_mismatch`
- `bom_snapshot_limit_exceeded`
- `product_binding_not_found`
- `product_binding_ambiguous`
- `resource_model_not_found`
- `resource_model_ambiguous`
- `environment_source_changed`
- `connector_offline`
- `connector_version_incompatible`
- `adapter_unavailable`
- `adapter_contract_mismatch`
- `interactive_session_missing`
- `interactive_session_conflict`
- `vismockup_unavailable`
- `vismockup_document_changed`
- `scene_verification_failed`
- `capture_failed`
- `artifact_upload_unconfirmed`
- `craft_screenshot_attach_failed`
- `local_execution_outcome_unknown`

每个错误必须声明 retryable。版本/身份/合同/权限冲突不可自动重试；网络超时、设备离线可按退避重试；任何 `outcome_unknown` 必须先对账。

## 10. 可靠性和恢复

- AI00 是业务任务状态权威，Connector 本地账本是本机副作用对账证据。
- 每个步骤开始前持久化 `started`，完成后持久化结果 hash，再回报服务端。
- Service 重启后先恢复/对账未完成计划，不直接领取新计划。
- SessionHost 或 VisMockup 退出后当前步骤转 `outcome_unknown`；只有可证明无副作用的步骤可以自动重试。
- 场景 apply 使用完整期望状态而不是增量猜测，使同一环境步骤具备可验证的幂等收敛属性。
- 截图不视为天然幂等；重试创建新 attempt，但工艺关联幂等键防止重复展示。

## 11. 验证策略

### 11.1 机器验证

- Catalog、Descriptor、Provider、API、consumer、domain dependency 和 migration ownership 检查；
- 每个新 Capability 的有效、无效、空值、边界、重复、版本、输出、错误、权限和幂等合同测试；
- Manifest canonical JSON/hash 与跨语言测试向量；
- ExecutionPlan 签名、过期、篡改、重放、版本和合同 hash 拒绝测试；
- Connector 单用户、单 SessionHost、单 STA 串行测试；
- Artifact 大小、hash、上传对账和清理测试；
- MCP 工具发现不等于授权、未映射工具拒绝和凭据隔离测试。

### 11.2 真实运行验证

必须在安装真实 VisMockup 的试点机执行：

- 连接已打开 VisMockup，而不是误启第二实例；
- 读取真实 BOM 大小和深度边界；
- 加载工具、设备、工装数模并验证节点绑定；
- 倒序场景、内部 CaptureImage 和图片完整性；
- 锁屏、显示器关闭、任务期间防睡眠；
- RDP 断开；
- COM 异常、VisMockup 崩溃、SessionHost 重启、网络中断与上传对账；
- 真实工艺域截图关联的权限、幂等和历史行为。

模拟 Adapter、空列表 HTTP 200、离线 acceptance 或 AI 声明均不能替代 `runtime_verified`。

## 12. 迁移和发布顺序

1. 先补齐权威跨域读取和写入 Capability，不接 Connector 副作用。
2. 发布 Environment Manifest 和 ExecutionPlan v1 合同及测试向量。
3. 将现有 Local Runtime 产品化为 AI00 Connector，完成安装、配对、SessionHost 和密钥安全。
4. 实现 VisMockup Adapter 新 operation，并在真实试点机验证。
5. 接入环境 compose/preflight/materialize。
6. 接入倒序截图和工艺关联，先单用户灰度。
7. 完成受控运行证据后，再由可信流程决定 stable 发布。
8. 最后收口现有 `vismockup.*@1` 的 web/plugin/agent/api/mcp 直接暴露；提供兼容期并迁移到 simulation 业务 Capability，不原地破坏调用方。

MCP Adapter 只交付扩展合同和拒绝默认值，不在一期连接飞书或其他软件。新增每个 Adapter 时单独做 Capability、权限、凭据和运行验证。

## 13. 当前仓库复用结果与 Findings

### 13.1 可复用

- simulation 已有环境、运行、数模版本固定和来源 hash 基础；
- device runtime 已有注册、心跳、租约、命令完成和 Artifact 传输基础；
- Local Runtime 已有 Service/SessionHost/named pipe/STA、命令签名、payload hash、过期和重放账本；
- VisMockup Adapter 已有 status、launch、open、tree、highlight、visibility 和内部 capture 的代码样本；
- Craft 已有不可变 execution-plan 合同方向；
- Digital Model 已有版本和组件查询；
- Craft resource requirement 已出现部分 CAD/模型字段，可作为迁移输入但不能替代已确认的知识域所有权决定。

### 13.2 Findings

1. **业务语义缺口**：现有 `simulation.environment.create@1` 不表示当前业务所需的 BOM/资源绑定和现场物化。
2. **跨域能力缺口**：运行 Catalog 是否真实提供完整 `craft.execution_plan.get@1` 尚未由运行 Snapshot 证实。
3. **知识所有权冲突**：用户要求映射来自知识库，但当前 Craft resource requirement 也持有 CAD/模型字段。正式实现前必须确定权威源和迁移/投影关系，禁止双写。
4. **Connector 操作缺口**：当前只有 open/tree/visibility/capture 等低级操作，没有 document snapshot、model attach、完整 scene apply/verify 合同。
5. **暴露过宽**：现有 `vismockup.*@1` 标记为 stable 且对 web/plugin/agent/api/mcp 广泛开放，与“通过 simulation 编排、Connector 受控执行”的目标边界冲突。
6. **连接语义风险**：当前 COM `Activator.CreateInstance` 尚未证明总能附着用户已打开实例，可能误启新实例。
7. **产品化缺口**：签名 MSI、Service 安装、SessionHost 用户自启、DPAPI/证书密钥和托盘诊断尚未闭环。
8. **兼容握手缺口**：当前心跳未完整绑定 protocol、Adapter、目标产品版本和每个 operation 的合同 hash。
9. **运行证据缺口**：锁屏、RDP 断开、防睡眠和真实内部截图尚未形成绑定当前版本的运行证据。
10. **文档漂移**：Local Runtime README 的能力广告描述与代码中的 Allowed 集合不一致。

## 14. 必须由人确认的业务决定

- 本设计规定资源代码到数模引用的权威映射归知识域；Craft 中已有 CAD 字段作为输入投影或迁移源，不再作为并列权威源。
- 一期截图场景采用“累计产品、仅当前工序资源”的倒序规则。
- 工艺域截图区采用逐工序幂等关联并保留历史，当前展示指针由工艺域决定。
- 现有 `vismockup.*@1` 进入兼容收口而非继续扩大直接消费者。
- 飞书等云 SaaS 默认走 AI00 服务端连接；Connector 只为本机/内网依赖提供 MCP Adapter。

这些决定必须绑定正式 Capability version GID、business-definition hash、Snapshot 和理由。AI 不代替领域负责人或 `super_admin` 批准。

## 15. 完成定义

一期只有在以下条件同时满足时才算交付完成：

- 两部分边界和跨域契约进入受治理 Catalog；
- 环境可从真实工艺、真实 VisMockup BOM 和真实资源数模映射组成；
- Connector 在单用户工作站稳定物化环境；
- 锁屏且系统不睡眠时可完成倒序内部截图；
- 每张截图可追溯并幂等关联到正确工艺版本和工序；
- 失败、取消、重启和结果未知均可对账；
- `machine_passed`、`human_approved` 和 `runtime_verified` 分别由可信证据得出，不互相替代。
