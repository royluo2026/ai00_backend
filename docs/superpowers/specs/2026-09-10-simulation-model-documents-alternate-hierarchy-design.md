# 仿真环境多模型文档、备选层次结构与 BOP 编排设计

**日期：** 2026-09-10

**状态：** 业务方向已确认，等待用户复核本书面规格

**领域 Owner：** Simulation（仿真环境、模型文档、备选层次、放置关系）与 Craft（BOP Repository/Fork）

**适用客户端：** AI00 Windows x64 App + AI00 Connector + VisMockup 14.2
**关联规格：**

- `docs/superpowers/specs/2026-09-08-digital-simulation-environment-redesign.md`
- `docs/superpowers/specs/2026-09-09-simulation-environment-collaboration-versioning-design.md`
- `docs/superpowers/specs/2026-09-10-simulation-three-layer-cache-version-diff-design.md`

本规格取代 2026-09-08 规格第 3.1 节中“一个仿真环境只绑定一个 VM 文档、组合模型须先在 VisMockup 中形成一个文档”的限制。缓存、身份、版本差异和 Connector v2 治理链继续沿用既有规格，除非本文明确修正。

## 1. 设计结论

仿真环境是一个可持续、可复现的仿真工作上下文，不等于一份 PLMXML、不等于一个 VisMockup 窗口，也不等于一棵备选层次结构。

一个仿真环境包含：

1. 多个来源模型文档：一个主来源，以及零个或多个补充 PLMXML、JT；
2. 零个或多个可编辑备选层次结构；
3. BOP Fork 形成的工艺骨架；
4. 从 VM 产品结构或资源库放到 BOP 节点下的引用实例；
5. BOP—VM 绑定、姿态、参数、任务、结果、快照和版本。

```text
仿真环境
├─ VM 产品结构（只读来源集合）
│  ├─ 主 PLMXML
│  ├─ 补充 PLMXML
│  └─ 本地 JT
├─ 备选层次结构 A（可编辑）
│  └─ BOP Fork 骨架
│     ├─ 工序/操作节点
│     │  ├─ VM occurrence 放置引用
│     │  └─ 工具/工装/设备/套筒放置引用
│     └─ 其他 BOP 节点
└─ 备选层次结构 B（可以为空）
```

数据库是协作语义与版本的权威来源；PLMXML 是 VisMockup 兼容的交换、导入、导出和快照制品。JT/PLMXML 原始字节不复制进普通业务表。一个环境可以引用多个来源文件，但每个可复现环境版本对 VisMockup 只发布一个顶层运行 PLMXML；该文件及其已解析依赖共同构成 runtime package。

模型文档必须先形成有向依赖图。若待插入 PLMXML 已外部引用当前主文档，或其依赖闭包与当前运行文档形成回指/重复根，它不能再作为普通补充文档执行 `InsertDocument`；系统必须将它提升为新的顶层候选，或在物化时对共同依赖去重。检测到环路时以 `model_document_dependency_cycle` 拒绝同步，不能把 VisMockup 卡死或崩溃当成普通超时。

AI00 与 VisMockup 不需要拥有完全相同的对象模型，但必须对环境中“会影响数模分析执行”的部分达成可验证的一致认识。未经 VisMockup 物化、回读和控制验证的数据库状态只能是草稿，不能标记为可复现版本。

## 2. 样本证据与修正

本次有界检查了：

- `D:\Temp\vis\plmxml\W10-ENG00001-00-1-工程分支(Top Engineering) (视图).plmxml`
- `D:\Temp\vis\plmxml\W10-2.plmxml`

旧文件约 21.4 MB，包含 14,170 个 `ProductInstance`、14,171 个 `Occurrence`、4,974 个 `ProductRevisionView` 和 3,417 个 `Representation`，没有 `ProductView usage="variant"`。

新文件约 37.2 MB：

- 通过外部 `partRef` 引用旧 PLMXML 的主产品结构；
- 增加 `Pitou.jt`、`Gunattach.jt` 两个本地模型文档；
- 增加一个 `ProductView usage="variant"`，其中保存了有内容的用户备选层次 `1111`；
- 用户创建但为空的 `ALT Hier #2` 没有被写入该 PLMXML；
- VisMockup 中可见的部分 JT 内部节点也没有作为独立 PLMXML 编排节点出现。

因此：

1. 有内容的备选层次可投影成 PLMXML `ProductView usage="variant"`；
2. 空备选层次可能被 VisMockup 导出省略，不能只靠 PLMXML 保存；
3. 本地模型、外部 PLMXML 引用和 JT 内部结构必须保存独立来源身份；
4. AI00 必须保存用户命名、空结构、BOP 来源和放置关系，再按需导出为 VisMockup 可表达的 PLMXML。

## 3. 权威边界

| 对象 | 权威 Owner | 说明 |
|---|---|---|
| 项目身份 | Project Management | Simulation 只保存 `project_gid` 引用 |
| BOP Repository、团队/个人空间、BOP Fork、BOP 节点 | Craft | Simulation 不复制或直写 Craft 表 |
| 仿真环境 | Simulation | 工作上下文与生命周期 |
| 环境关联的模型文档 | Simulation | 保存来源、内容指纹、顺序、角色和版本引用 |
| VM Snapshot/Occurrence | Simulation | 从 PLMXML/VisMockup 形成的只读产品结构投影 |
| 备选层次结构 | Simulation | 包括空结构、名称、顺序、BOP 来源和版本 |
| 产品/资源放置实例 | Simulation | 引用 VM occurrence 或各资源 Owner 的稳定对象，不复制主数据 |
| 数模主数据及不可变版本 | Digital Model | Simulation 只保存带版本引用 |
| 工具、工装、设备、套筒主数据 | 对应资源 Owner | Simulation 只保存放置引用和仿真覆盖属性 |
| PLMXML/JT/manifest 字节 | Base Artifact 或本地文件 Provider | 业务表保存 ArtifactRef、hash 或本地受控 token，不保存字节 |
| VisMockup 文档插入与控制 | 本地 VisMockup Adapter | 只能执行签名 Connector plan 中的白名单 operation |

缓存不是权威来源；Connector SQLite 和前端 IndexedDB 只保存可重建投影与当前会话映射。

### 3.1 双层环境与相互认可合同

AI00 仿真环境是业务超集，VisMockup PLMXML 是其可执行投影：

| 数据类别 | AI00 保存 | 必须进入或作用于 VisMockup | 相互认可标准 |
|---|---|---|---|
| 模型文档、产品 occurrence、备选层次、姿态、显隐、颜色 | 是 | 是 | 生成 PLMXML/COM 计划后由 VisMockup 打开并回读一致 |
| BOP Fork 骨架及产品/资源放置 | 是 | 以备选层次和模型引用表达 | VisMockup 能定位对应 occurrence，AI00 能反查 BOP/资源 GID |
| 分析结论、问题、任务、审批、备注 | 是 | 否 | 继续绑定已验证的环境版本和节点身份，不要求写入 PLMXML |
| 原始 PLMXML/JT 字节与未知厂商扩展 | Artifact/受控本地来源 | 是 | 未编辑时原始字节保真；编辑后保留可识别扩展并报告不可表达项 |

相互认可不是“两个系统字段完全相同”，而是满足以下闭环：

```text
AI00 环境草稿
  -> 生成精确 PLMXML + runtime manifest
  -> VisMockup 打开/插入
  -> 回读文档、备选层次、occurrence 与场景摘要
  -> 比较预期 manifest
  -> 抽样执行显隐/选择并校验后置状态
  -> AI00 环境版本标记 runtime_verified
```

环境版本状态至少区分：

- `draft`：AI00 可实时保存，尚未证明能在 VisMockup 恢复；
- `materializing`：正在生成并装载运行投影；
- `runtime_verified`：精确生成物已被目标 VisMockup 版本打开、回读并通过控制验证；
- `runtime_drifted`：VisMockup 当前结构或场景已偏离该版本，需同步或恢复；
- `unmaterializable`：存在 VisMockup 无法表达且会影响本次分析的状态，禁止冻结为可复现版本。

`runtime_verified` 必须绑定环境 version GID/content hash、PLMXML Artifact/hash、runtime manifest hash、device/runtime generation、VisMockup 产品版本、Connector/Adapter 版本、验证 operation GID 和验证时间。它不能由前端布尔值或 AI 断言产生。

用户可以长期编辑 `draft`；但“保存可复现版本”“恢复上次分析”“开始需要精确环境的分析任务”和共享基准发布必须要求当前精确版本 `runtime_verified`。仅属于 AI00 的问题、任务和结论不参与 VisMockup 等价比较，但必须继续绑定该已验证版本和稳定节点身份。

### 3.2 实时保存与不可变版本

用户对备选层次、放置、姿态和模型关联的每次有效修改都实时写入数据库 draft head。前端防抖只减少请求次数，不是数据权威；每次写入通过 expected row version、幂等键和单个 Simulation 事务推进 draft head。冲突返回稳定错误并重新读取，不使用 last-write-wins。

实时保存不会为每次修改生成完整 PLMXML，也不会自动标记为可复现。只有用户保存版本、开始受控分析或显式验证时，才从精确 draft/version 生成顶层 PLMXML runtime package，并经过 VisMockup 相互认可闭环。已冻结版本不可修改，后续编辑产生新 draft/version。

## 4. 模型文档集合

### 4.1 文档角色与类型

每个仿真环境允许：

- 一个 `primary` 主来源文档；它可以是 PLMXML 或 JT；
- 任意数量的 `supplemental` 补充模型文档；
- 文档格式第一阶段仅允许 `.plmxml` 和 `.jt`；
- PLMXML 可直接解析结构；JT 的内部结构以 VisMockup 返回的树为准，不由 AI00 猜测。

`primary` 描述来源模型的装载起点，不等于最终发布给 VisMockup 的顶层运行 PLMXML。即使环境从单个 JT 创建，可复现版本仍由 PLMXML export Capability 生成统一顶层 PLMXML。

模型文档是逻辑身份；某次打开或插入属于 VisMockup runtime session。路径改变不应自动冒充相同文件，内容 hash 相同的移动文件可由用户确认复用逻辑身份。

文档可移植性分为：

- `device_bound`：文件只存在本机；验证结果绑定 device 和内容 hash，下一次运行必须在该设备重新校验；
- `portable`：文件字节已成为受治理不可变 Artifact，或来源系统提供可复验的不可变共享引用；可以在授权设备重新物化。

私人环境 draft 可以引用 `device_bound` 文件。跨设备恢复、共享基准和声明为“可移植可复现”的版本要求全部运行依赖为 `portable`；系统不得把仅记录本地路径的版本宣传为跨设备可复现。

### 4.2 添加模型文档

用户选择一个或多个文件后：

1. Connector 在本机校验扩展名、文件存在性和允许路径，计算 SHA-256、字节数和修改时间；
2. Connector 创建短期、一次性、绑定当前 actor/device 的 `local_file_token`；绝对路径不发送到普通日志或云端 Capability 输入；
3. Simulation Capability 校验目标环境写权限、重复内容、文档角色和 expected workspace version；
4. Simulation 持久化模型文档关联，状态为 `registered`；
5. 服务端生成绑定精确文档关联和本机 token 的 Connector execution plan；
6. 首个主模型使用 VisMockup `Documents.OpenDocument(path)`；后续模型使用活动文档 `InsertDocument(path)`；
7. Connector 返回文档句柄、插入索引、文件 hash 与实际后置状态；
8. Simulation 将同步状态推进为 `synced`，再触发受控结构采集与 occurrence 对齐。

持久化成功但本地插入失败时，文档保留为 `pending_sync`，允许对同一 operation 幂等重试，不回滚或重复创建业务关联。

### 4.3 VisMockup COM 语义

VisMockup 类型库已表明：

- `IVisDispDocList.OpenDocument(path)`：打开主文档；
- `IVisDispDoc.InsertDocument(path)`：向当前文档插入文件；
- `IVisDispDoc.NumInsertedDocuments`、`InsertedDocumentPath(index)` 和 `DeleteInsertedDocument(index)`：观察和移除插入文档。

当前 Connector 仅调用 `Documents.Open(path)`，并且只记忆一个 `_ownedDocumentId`，不足以支持本设计。实施前阶段 0 必须用真实 PLMXML 和 JT 对 `InsertDocument` 做一次最小 COM 探针，验证：

- 正确的 raw IDispatch 对象和 DISPID；
- PLMXML、单零件 JT、装配 JT 的插入结果；
- `NumInsertedDocuments` 和 `InsertedDocumentPath` 后置条件；
- 插入后 ActiveDocument 不漂移；
- 重复插入、路径失效和长时间调用的稳定错误。

探针通过前，不得用连续 `OpenDocument` 假装插入成功，也不得把 `ActiveView.AddModel` 等不同效果冒充文档插入。

### 4.4 已打开文件与恢复

- Connector 先按当前文档及 inserted-document 列表核对规范化路径和文件指纹；已存在时建立关联，不重复插入。
- VisMockup 未运行或未连接时仍可登记文件，状态为 `pending_sync`。
- Connector 恢复后按主文档优先、补充文档顺序执行缺失同步。
- 同一路径内容 hash 改变时标记 `version_changed`，不得命中旧缓存或静默替换。
- 从环境移除关联默认不关闭 VisMockup 文档；“同时从 VisMockup 移除”是独立显式动作。
- AI00 App 退出不关闭 VisMockup 或其文档。

## 5. VM 产品结构

“VM 结构树”重新定义为当前仿真环境全部模型文档的只读产品结构集合：

```text
VM 产品结构
├─ 主产品结构
│  └─ W10 工程分支.plmxml
├─ 补充模型
│  ├─ 辅助装配.plmxml
│  ├─ Pitou.jt
│  └─ Gunattach.jt
└─ 待同步/失效文件
```

页面先显示最后一次完整缓存；每个文档根显示 `registered | opening | inserting | synced | pending_sync | version_changed | failed`。显示层级只控制渲染，不控制采集、缓存或持久化深度。

PLMXML 结构由安全流式解析器建立 Snapshot；JT 插入成功后由 VisMockup 结构读取建立 Snapshot。不同文档中的 occurrence 必须保留 `document_gid`，不能只按名称合并。

## 6. 备选层次结构

### 6.1 定义

备选层次结构是仿真环境中的可编辑装配/工艺视图。一个环境可以有多个备选层次，也允许空层次。名称由用户定义，不能依赖 VisMockup 的 `ALT Hier #n` 临时显示名作为身份。

每个备选层次至少保存：

- 服务端雪花 `hierarchy_gid`；
- `workspace_gid`；
- 名称、同环境排序和状态；
- 可选 `source_bop_repository_gid/source_bop_version_gid`；
- 可选 `source_bop_fork_run_gid`；
- 根节点、row version、创建人和审计信息；
- PLMXML variant 投影标识，但该标识不是主键。

空层次保存在数据库；导出 PLMXML 若无法表达空 variant，必须在导出结果中报告 `omitted_empty_hierarchy`，不能假装完整保真。

### 6.2 BOP Fork 创建初始层次

用户在仿真环境中执行 BOP Fork 时，产品体验上是一个动作，领域执行上是可恢复的两步 workflow：

1. Craft `repository/space fork preview → apply` 创建精确 BOP Fork 和不可变来源证据；
2. Simulation 使用 Craft 返回的 fork/version/node 投影创建一个备选层次，并把 BOP 节点作为可编辑工艺骨架。

Simulation 不直写 Craft 表，Craft 也不直写 Simulation 表。若 Craft 已成功而 Simulation 创建失败，BOP Fork 保留，workflow 标记 `hierarchy_materialization_failed`，允许按同一 correlation/idempotency 重试第二步；不得重复 Fork BOP。

每个由 BOP Fork 生成的层次必须绑定精确来源版本。用户需要另一种方案时，再创建一个新的备选层次或从已保存层次版本派生，不原地改变历史来源。

## 7. 从 VM/资源库拖入 BOP

拖放不是复制模型或资源主数据，而是在备选层次中创建“放置实例”：

- 拖 VM occurrence：保存 `document_gid + snapshot_gid + occurrence_gid`；
- 拖产品/资源库对象：保存 owner domain、source GID、精确版本/状态证据；
- 目标必须是当前备选层次中的 BOP 节点；
- 同一来源对象可放置到多个 BOP 节点；
- 删除放置只解除当前环境关系，不删除来源对象或文件；
- 放置实例可保存仿真覆盖属性，如姿态、显隐、角色和备注，但不改来源主数据。

拖入一个 VM 总成节点时，默认引用该节点及其可折叠子树，不复制每个模型字节。绑定固定根 occurrence 及当时 Snapshot；展开时读取该 Snapshot 的后代。来源版本变化后标记放置为 `stale` 并生成重映射候选，不自动错误迁移。

产品/资源放置在 UI 中显示为 BOP 节点的子行，但数据库中是独立关系对象，不伪装成 Craft BOP node。

## 8. 最小数据模型调整

优先复用现有表：

- `workmanship_sim_vm_documents` 已允许一个 Workspace 对应多个来源文档；补充角色、显示名、顺序、media type、当前内容 hash 和移除状态即可；
- `workmanship_sim_vm_snapshots/occurrences/observations` 继续按文档保存结构版本；
- `workmanship_sim_workspace_nodes` 继续保存 Simulation 自有层次节点或 BOP 节点投影，但必须显式归属 `hierarchy_gid`；
- `workmanship_sim_workspace_bindings` 保留既有 VM occurrence 绑定，不静默扩大为所有资源类型。

新增最少对象：

1. `workmanship_sim_workspace_hierarchies`：备选层次身份、名称、BOP Fork 来源和 head；
2. `workmanship_sim_workspace_placements`：目标层次/BOP 节点到 VM occurrence 或资源版本的放置关系；
3. `workmanship_sim_vm_session_documents`：一个 VisMockup runtime session 中的主文档与 inserted documents 及其实际句柄/索引；
4. Connector 本地短期 token 表：只在本机保存绝对路径、hash、actor/device、expiry 和一次性状态。

所有服务端业务实体使用后端雪花 GID。绝对本地路径不进入共享业务表；服务端保存内容 hash、可显示文件名、ArtifactRef 或脱敏来源身份。本地文件若要在其他电脑复现，必须另行上传为受治理 Artifact 或由用户在目标机器重新映射；第一阶段不建设自动文件云盘。

## 9. Capability 与 Adapter 边界

### 9.1 优先复用

- `simulation.environment.workspace.get@1`
- `simulation.environment.structure_node.create/move/remove@1`，仅在现有契约能表达 `hierarchy_gid` 时复用；否则不得扩写 stable 语义
- `simulation.environment.binding.create/remove@1`，继续处理其已声明的 VM occurrence 绑定
- `simulation.document_snapshot.*`
- `simulation.environment.bop_vm_binding_draft.preview@1`
- Craft 现有 Repository/space Fork Preview—Apply 链
- Base Artifact 导入/读取能力

### 9.2 新增或升版候选

实施前必须从运行 Registry/Catalog 重新做精确复用扫描。当前候选为 advisory：

| 业务效果 | 候选 Capability |
|---|---|
| 在环境登记一个本地或 Artifact 模型文档 | `simulation.environment.model_document.add@1` |
| 分页读取环境模型文档 | `simulation.environment.model_document.search@1` |
| 从环境解除模型文档关联 | `simulation.environment.model_document.remove@1` |
| 创建含 BOP Fork 骨架或空白的备选层次 | `simulation.environment.alternate_hierarchy.create@1` |
| 查询/读取备选层次 | `simulation.environment.alternate_hierarchy.search/get@1` |
| 重命名/归档备选层次 | `simulation.environment.alternate_hierarchy.update/archive@1` |
| 在 BOP 节点下创建 VM/资源放置 | `simulation.environment.placement.create@1` |
| 移动/移除放置实例 | `simulation.environment.placement.move/remove@1` |
| 读取 BOP Fork + 层次创建 workflow | `simulation.environment.bop_fork_workflow.get@1` |
| 从 PLMXML Artifact 导入并投影环境结构 | `simulation.plmxml.environment.import@1` |
| 从精确环境版本生成 VisMockup PLMXML | `simulation.plmxml.environment.export@1` |

本地 Adapter 新增技术 operation `vismockup.model.insert@1`，与已有 `vismockup.model.open@1` 分开，因为二者后置状态、目标文档和失败恢复不同。Adapter operation 不因为是 COM 方法就自动成为用户 Capability；用户业务动作仍通过 Simulation Capability 准备并签发 Connector plan。

PLMXML import 与 export 由同一个 Simulation PLMXML Provider 实现，但保持两个原子 Capability：两者授权、输入、失败、幂等和审计不同，不能合并成带 `mode` 的万能转换能力。未编辑来源可直接返回原始 Artifact 以实现字节一致；编辑后的环境生成新 Artifact，并以 VisMockup 语义回读一致为验收标准，不承诺 XML ID、属性顺序、时间戳和压缩块逐字节相同。

Export 输出不是一个裸路径，而是不可变 runtime package manifest：一个顶层 PLMXML Artifact、其引用的 PLMXML/JT 依赖、每项 hash/byte size/media type/portability、环境 version/content hash、转换算法版本和不可表达项。Connector 物化到本机临时目录后必须复验全部 hash，再只用顶层 PLMXML 启动 VisMockup。`device_bound` 依赖只能在绑定设备从本地 token 映射；`portable` 依赖从受治理 Artifact/共享引用解析。依赖缺失、路径无法解析或 hash 不符时禁止打开并返回稳定错误。

Import 必须同时保存原始不可变 Artifact、规范化数据库投影和无法解释但需保真的厂商扩展证据。原文件无修改时 export 复用原始字节；有修改时以规范化语义等价为验收，任何未知扩展无法安全保留时必须进入 export report，不能静默丢弃。

写操作必须包含 trusted actor、资源 selector、expected row version、唯一 idempotency key 和审计；本地插入计划还必须绑定 device、session、active document、file token/hash、expiry 和后置校验。

## 10. 权限与交互

- VM 产品结构读取继承环境可见性；本地绝对路径仅文件所属用户和 Connector 可见。
- 向环境添加/移除文档、创建层次和放置实例需要环境写权限。
- Project/team 范围的 BOP Fork 继续遵守 Craft 的项目管理/super-admin 权限；Simulation 不放宽。
- 受管个人空间只允许 owner 编辑；项目经理和 super-admin 的额外能力由现有项目规则决定。
- 读取、树展开、选择、高亮不弹额外确认。
- 选择本地文件是用户对“登记并同步插入”的明确发起，但最终 confirmation receipt 仍由服务端 Descriptor 策略决定。
- 同步状态显示在页内，不使用循环弹窗。

## 11. 稳定错误与恢复

至少覆盖：

- `model_document_duplicate`
- `model_document_format_unsupported`
- `model_document_version_changed`
- `model_document_dependency_cycle`
- `local_file_token_expired`
- `local_file_hash_mismatch`
- `vismockup_active_document_missing`
- `vismockup_document_insert_unsupported`
- `vismockup_document_insert_timeout`
- `vismockup_document_insert_postcondition_failed`
- `alternate_hierarchy_not_found`
- `alternate_hierarchy_name_conflict`
- `placement_source_not_found`
- `placement_target_not_bop_node`
- `placement_source_version_stale`
- `hierarchy_materialization_failed`
- `operation_outcome_unknown`

COM 超时或网络中断不能盲目重放插入。先读取 VisMockup inserted-document 列表和服务端 operation 状态；能够证明文件已插入时收敛为成功，否则进入人工重试。

## 12. 页面设计

第二列保持两个上下折叠区：

1. 上部“仿真环境库”；
2. 下部“当前仿真环境”，显示 BOP Fork 生成的备选层次。

“产品 · VM 结构”区域显示多模型文档集合。底部原 `PLMXML` 按钮改为“添加模型文档”，文件选择器允许 `.plmxml,.jt` 和多选。每个文档根提供状态、版本变化提示、重试同步和解除关联入口。

拖放交互：

- VM 文档节点/资源库行可拖到当前备选层次中的 BOP 节点；
- 不允许拖到空白区或非 BOP 关系目标；
- 成功后立即显示放置子行；
- 写失败恢复原 UI，不保留假成功节点；
- 拖总成默认引用整棵子树，UI 懒展开。

## 13. 分阶段实施

### 阶段 0：真实 COM 与 PLMXML 往返探针

用当前 W10 主 PLMXML、`W10-2.plmxml`、一个单件 JT 和一个装配 JT 验证 `InsertDocument`、后置查询、重复插入和移除；同时验证有内容 variant、空备选层次、外部 PLMXML/JT 引用和未知扩展的 import/export 可表达范围。只产出测试证据，不先改产品语义。

### 阶段 1：PLMXML 双向转换与数据库规范模型

先完成 PLMXML import/export Provider、runtime package manifest、数据库迁移、实时 draft 保存和规范化语义往返测试。该阶段不能通过真实 VisMockup 回读时，后续编排实现保持关闭。

### 阶段 2：模型文档集合与 VisMockup 同步

完成文档 add/search/remove、Connector 本地文件 token、`vismockup.model.insert@1`、多文件 UI 和状态恢复。保留旧单 PLMXML 入口的读取兼容，但新写全部进入模型文档集合。

### 阶段 3：备选层次与 BOP Fork

完成 hierarchy 数据模型、空层次保存、BOP Fork workflow 第二步物化、读取和 UI。既有 Workspace 节点按可验证规则映射到默认层次；无法判断的进入 quarantine，不按名称猜测。

### 阶段 4：VM/资源放置与整体相互认可

完成 placement 能力、拖放、整棵子树引用、资源引用、版本失效提示和 BOP—VM 初版绑定；把非空备选层次投影成 `ProductView usage="variant"`，执行顶层 PLMXML 生成、真实 VisMockup 回读和控制验证。自动绑定只生成 candidate，不能静默替代人工确认。

## 14. 验收场景

1. 在空环境添加主 PLMXML，AI00 登记并驱动 VisMockup 打开，VM 树显示主结构。
2. 再添加补充 PLMXML，VisMockup 在当前活动文档插入，AI00 树新增独立文档根。
3. 再添加 JT，单件和装配 JT 均同步插入；装配结构由 VisMockup 返回。
4. 重复选择同一 hash 文件不会重复插入。
5. 同一路径文件内容变化时提示版本变化，不错误命中缓存。
6. VisMockup 离线时文档为 `pending_sync`，恢复后可幂等补插。
7. BOP Fork 成功后立即出现以精确 BOP Fork 为骨架的备选层次。
8. 第二步失败不会重复 Fork BOP，重试只补建层次。
9. 空 `ALT Hier #2` 等用户层次刷新后仍存在。
10. 从 VM 树拖总成到 BOP 工序，创建一个引用实例并可折叠查看子树。
11. 从资源库拖工具/工装/设备/套筒到 BOP 节点，创建引用而不复制主数据。
12. 删除放置不会删除原 VM 节点、JT、资源或 Craft BOP 节点。
13. App 退出不关闭 VisMockup；重新进入环境能够核对并恢复模型文档关联。
14. 非授权用户只能查看可见环境，不能添加文档、修改层次或放置资源。
15. 精确环境版本生成 PLMXML 后，VisMockup 能打开/插入全部文档，并回读相同的模型集合、非空备选层次、occurrence 和场景摘要。
16. 验证流程能够通过显隐或选择抽样证明关键 occurrence 可控；仅“文件打开成功”不能产生 `runtime_verified`。
17. VisMockup 中手工改变结构后，原环境版本转为 `runtime_drifted`，不会继续伪报与 AI00 一致。
18. 存在会影响分析但 VisMockup 无法表达的编排时，版本为 `unmaterializable`，冻结/复现流程失败并报告具体对象。
19. 环境引用多个 PLMXML/JT 时只从 runtime package 的一个顶层 PLMXML 打开；所有依赖 hash 完整且在 VisMockup 中可定位。
20. 页面刷新或 App 重启后数据库 draft 恢复到最后一次已确认写入，不能依赖浏览器内存保存环境状态。
21. 仅含本地文件的私人环境可以在原设备恢复并重新校验，但不能标为跨设备 portable；共享/跨设备版本的所有依赖必须为不可变 Artifact 或受控共享引用。

## 15. 明确不做

- 不建设通用 CAD 格式转换器；
- 不自动上传所有本地 JT/PLMXML 到云端；
- 不由 Simulation 修改 Craft BOP 或资源主数据；
- 不把连续 Open 多个 VisMockup MDI 文档当成 Insert；
- 不按文件名、树节点名称或 `ALT Hier #n` 猜测稳定身份；
- 不在本阶段实现任意 PLMXML 编辑器；
- 不承诺空备选层次能被 VisMockup PLMXML 原样表达；数据库负责保真。
- 不把“数据库保存成功”或“VisMockup 文件打开成功”单独当成相互认可或运行验证证据。

## 16. Capability 治理记录

### Change classification

- 类型：新 Capability + experimental 合同的兼容/主版本调整候选；是否升 major 由真实 Registry/Descriptor 差距决定。
- 原因：把单文档仿真环境扩展为多模型文档集合，并新增备选层次和通用放置业务效果。

### Reuse、atomicity 与 ownership

- 复用现有 Workspace、VM Snapshot、Connector plan、BOP Fork、Artifact 和 VM binding 能力。
- 模型登记、VisMockup 插入、层次创建、放置创建分别可独立授权、失败、重试和审计，不能合并为一个万能 Capability。
- BOP Fork 属于 Craft；备选层次物化属于 Simulation，使用可恢复 workflow，不做跨域直表和伪单事务。
- 现有 `simulation.vismockup.model.open.request@1` 的输入面向 Artifact/open，不能在未核对合同前静默扩成 local-file/insert。

### Verification evidence

- 已执行：两份真实 PLMXML 元素计数、`ProductView usage="variant"` 与外部模型引用检查；VisMockup 类型库 `OpenDocument/InsertDocument/InsertedDocumentPath` 静态检查；现有 migrations、Provider、Connector Adapter 和前端 PLMXML 入口静态检查。
- 未执行：真实 `InsertDocument` COM 调用、数据库迁移、Capability 测试、App 端到端测试和运行 Registry Snapshot。

### Governance status

- `machine_passed`: `unverified`
- `human_approved`: `unverified`
- `runtime_verified`: `unverified`
- `advisory`: `true`

### Findings and unresolved risks

1. 当前 Connector 只有 open，没有受测的 insert 实现；阶段 0 未通过前实施被该技术事实阻断。
2. 现有 2026-09-08 规格的单 VM 文档限制与本次已确认业务需求冲突，本文明确取代该限制。
3. 现有 Workspace/BOP Fork 相关工作树有未提交改动；进入实现前必须先建立精确变更基线，避免覆盖其他改动。
4. 运行 Registry/Catalog 的真实 version GID、lifecycle、business-definition hash 与 human approval 尚未读取，所有新增 ID 仅为候选。
5. VisMockup 导出会省略空备选层次，数据库必须承担空结构保真。
6. “字节完全一致”和“VisMockup 语义一致”是两个证据等级；编辑后的文件只能以语义往返和真实控制验证声明可复现。
