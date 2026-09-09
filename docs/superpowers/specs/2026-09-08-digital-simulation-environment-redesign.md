# 数模仿真环境与 VisMockup 协同重构设计

**日期：** 2026-09-08
**状态：** 业务方向已确认，技术验证和 Capability 审批尚未完成
**适用客户端：** AI00 Windows x64 App
**相关既有设计：** `docs/superpowers/specs/2026-09-03-simulation-ai00-connector-governance-design.md`

**协作与版本细化：** `docs/superpowers/specs/2026-09-09-simulation-environment-collaboration-versioning-design.md`。该细化设计取代本文关于“仅私人工作区”、复杂选择性合并和后续才支持共享/Fork 的旧假设。

## 1. 设计结论

数模仿真页面应成为一个可持久化、可版本化的“仿真环境编排器”。它不保存或修改 Teamcenter 数模链接本身，也不替代 VisMockup 加载和显示数模。它保存用户如何引用、分类、排列、绑定和使用这些不可变链接，并通过 App 内置的 VisMockup Adapter 驱动 VisMockup 完成选择、高亮、显隐、着色和截图。

核心分层如下：

```text
Teamcenter / PLMXML 不可变数模链接
               |
               v
VisMockup 文档中的数模实例与结构
               |
               v
AI00 仿真环境中的引用、排列、绑定、版本和姿态
               |
               v
VisMockup COM 选择 / 高亮 / 显隐 / 着色 / 截图
               |
               v
项目主环境的在线 BOP 与版本基线
```

这一区分是系统长期扩展的基础：来源链接不可变，AI00 拥有的编排关系和版本可以变化，VisMockup 是实际数模加载与图形执行引擎。

### 1.1 App/Connector v2 唯一执行链

本设计服从 `docs/superpowers/specs/2026-09-07-governed-electron-app-migration-design.md`。所有 ExportEx、选择、高亮、显隐、着色、截图以及其他 VisMockup COM 业务操作都必须经过以下唯一链路：

```text
Electron Renderer
  -> Capability Gateway InvocationEnvelope
  -> Cloud Simulation Provider
  -> 已签名 ai00.connector.execution-plan.v2
  -> ConnectorHost lease / durable journal / Adapter
  -> VisMockup STA COM
  -> 已签名 Outcome v2
  -> Cloud Provider 状态投影与审计
  -> Renderer 查询结果
```

Renderer、preload、Electron IPC、Electron main、AppHost、named pipe 和 WebSocket 均不能直接授权或携带 VisMockup 业务命令。Electron main 只管理平台能力和 ConnectorHost 生命周期；named pipe 只承载健康与非敏感状态；WebSocket 只负责唤醒。ConnectorHost 只执行通过设备、actor、Catalog Release、Capability version、business-definition hash、confirmation receipt、幂等键、runtime generation、adapter contract 和有效期校验的 v2 plan。

运行必须执行 generation fencing、签名验证、过期拒绝和重放拒绝。传输失败不能当作业务失败；无法证明副作用结果时记录 `outcome_unknown` 或 `manual_review_required`，先根据服务端 OperationRef、lease 和本地 journal 对账，禁止盲目重试。

## 2. 已确认的业务规则

### 2.1 页面布局

页面采用四列结构：

1. **仿真环境记录列**：项目主环境、私人环境和共享池，按活动/基线/冻结/归档分组，并提供搜索、Fork、版本和同步状态。
2. **当前仿真环境树**：引用既有 BOP，也允许在末端增加临时线体、工位、工序和操作。
3. **VM 结构树**：展示当前 VisMockup 文档的结构化快照，并与 VisMockup 双向选择和高亮。
4. **右侧工作区**：一期保留，用于详情、差异、冲突、截图预览和未来高级仿真工具。

工具和状态入口集中在对应列头及统一状态区，不能散落在大空白画布中。

### 2.2 BOP 引用与仿真覆盖层

- 节点评审的项目主环境直接跟随在线活动 BOP。项目管理者可修改全部区域，工程师可修改获授权线体；BOP 写入始终由 Craft Capability 执行。
- 零散评审的私人/共享环境保存 BOP 引用和仿真覆盖层，不直接修改来源 BOP。
- 临时层级节点拥有 Simulation GID，不预占 Craft/BOP GID。
- 同一个 VM 实例可以在多个工序或操作中以关系投影出现，底层实例只有一份。
- 工具、设备、工装、套筒等需求关系可显示为虚拟关系组或关系行，不伪装成 BOP 结构节点。

### 2.3 主环境在线协作

- 一个主项目最多有一个活动主环境，不提供 pull、push、merge、rebase 或日常工程师分支。
- 项目管理者直接修改主环境；工程师直接修改获授权线体；跨线体调整由项目管理者处理。
- 线体范围授权是目标；在 `G-Craft-Collab` 通过前仍使用整 BOP CAS。跨线体移动由项目管理者执行，并要求 Craft 提供完整 checkpoint 和双线体原子合同。
- 主环境用 Simulation 拥有的 `environment_anchor` 关联两域不可变引用；只有锚点 saga 达到 `ready` 才显示为同一评审版本。

### 2.4 私人环境、共享池、Fork 与手动版本

- 零散环境创建和 Fork 后固定 private；Share/Unshare 是独立操作，且必须验证所有底层引用的再分发权限。
- 私人环境仅 owner 可读写；共享池环境在同租户及底层授权允许时可读、可用、可 Fork，但仍只有 owner 可修改。
- Fork 从已保存版本或活动环境的自动 fork-base 派生，不改变来源状态，也不回写来源；不可变来源复用 Artifact/ref，不复制字节。
- 私人和共享环境只保留当前状态、Fork 起点和用户主动保存的不可变版本，不保存每次自动保存的完整 BOP/VM 历史。
- 同一环境任意两个手动保存版本必须支持完整结构化 Diff，包括 BOP、绑定、VM 版本、BOM 行、`catiaOccurrenceName`、坐标和姿态。
- 生命周期仅为 active/frozen；baseline 是版本类型和指针，archive 是正交可恢复字段。owner 可逻辑删除自己的 private/shared 环境；project_main 删除要求当前项目管理/删除权限，且只删除 Simulation 扩展。

## 3. VisMockup 文档、窗口与同步

### 3.1 文档演进链

一个仿真环境绑定一条 VM 文档演进链：

- `vm_document_gid`：逻辑文档身份；
- `vm_session_gid`：一次 VisMockup 窗口连接会话；
- `vm_snapshot_gid`：一次用户接受的同步快照；
- `snapshot_sequence`：文档内单调递增序号；
- `opened_at_server` / `opened_at_local`：服务器与工作站观察时间。

同一环境版本不能混合多个 VisMockup 窗口。需要组合多个模型时，先在 VisMockup 中形成一个文档，再同步到 AI00。重新打开相同文档创建新 session，但继续同一 document 演进链；显式“创建新环境/新文档”才创建新 document GID。

### 3.2 打开方式

工程师可以：

- 从 Teamcenter 在线打开车型数模；
- 打开本地 PLMXML/JT；
- 仅上传 PLMXML 做离线结构评估。

PLMXML 是 AI00 的交换、快照和审计介质，不强制成为工程师启动 VisMockup 的唯一方式。在线打开后，目标能力是由 App 对活动文档执行 `ExportEx`，导出当前窗口的瞬时 PLMXML；该目标受下面的 COM 附着门槛约束。

现有探索记录已经验证：`VFFrame.Application` 的 `GetActiveObject` 返回 `MK_E_UNAVAILABLE`，而 `Dispatch`/`CoCreateInstance` 会创建新的 VisView/VisMockup 自动化实例，不能可靠附着 Teamcenter 已经在线打开的实例。因此当前 Connector 只能把“进程已运行”和“自动化已连接”作为两个独立状态，进程存在时不得伪报已连接。Teamcenter 在线窗口的 `ExportEx`、高亮、显隐、着色和截图必须先通过 G3，验证一个受 Connector v2 计划约束的官方附着接口或进程内 Adapter。该路径未通过前，用户手动导出并上传 PLMXML 只能用于云端结构评估，不能宣称在线窗口控制。

### 3.3 增量同步

VisMockup 窗口内可持续加入、删除或替换数模。同步采用“轻量观察 + 显式接受”的方式：

1. AppHost 轻量观察活动文档和结构摘要，发现变化后标记“结构已变化”。
2. 页面可以显示运行时变化提示，但不因每次插入都导出大型 PLMXML。
3. 用户点击“同步数模”后只执行一次 `ExportEx`，合并此前多次变化。
4. 原始 PLMXML 上传为不可变 OIS Artifact。
5. 云端解析并与最后接受快照比较，生成新增、删除、升版、移动和歧义候选。
6. 用户接受后形成新的 `vm_snapshot_gid` 和当前结构投影。

初次同步建立完整基线；后续保存增量事件，同时维护可直接读取的当前投影。不得每次页面加载都重新解析整个源文件。

### 3.4 断线恢复

- VisMockup 关闭或 COM 断开时 session 标记为 `detached`，不删除任何环境数据。
- 重新连接创建新 session 并恢复原 document 演进链。
- 只有一个明确匹配窗口时自动连接；多个候选在页面内选择。
- 重连后导出当前 PLMXML，与最后接受快照核对实例身份。
- 无法唯一恢复的实例标记为“待确认”，不得自动错误绑定。
- 截图、版本固定或可复现运行前必须处理影响本次范围的待确认项。

## 4. PLMXML 结构投影

### 4.1 已验证的样本文档事实

对 `D:\Temp\vis\plmxml\W10-ENG00001-00-1-工程分支(Top Engineering) (视图).plmxml` 进行了有界读取。样本由 Teamcenter Visualization 14.2.0 使用 PLM XML SDK 7 生成，包含大量 `ProductInstance`、`Occurrence`、`ProductRevisionView` 和 `Transform`。

关键关联包括：

- `Occurrence.instanceRefs` 指向从根到目标的 ProductInstance 路径；
- `ProductInstance.partRef` 指向 `ProductRevisionView`；
- `ProductRevisionView.__PLM_ITEM_ID` 提供物料/数模号；
- `ProductRevisionView.__PLM_REVISION_ID` 提供版本；
- `ProductRevisionView.Representation.location` 提供 JT/模型位置；
- `ProductInstance.name` 可包含完整 BOM 行号，例如 `W01-89184128/00;1`；
- `Occurrence.UserData.catiaOccurrenceName` 是实例映射的重要字段；
- `Occurrence.UserData.C9_bl_vpps` 可作为业务辅助信息；
- `Transform` 的 16 个数值表达旋转和平移，必须完整保留。

样本中同一物料/版本存在多个 ProductInstance，且姿态不同，因此 VPPS、物料号或数模号均不能单独作为实例唯一键。

### 4.2 原始文件与结构化数据

- 原始 PLMXML：存 OIS，保存 ArtifactRef、SHA-256、字节数、生成来源和时间。
- 结构化投影：存数据库，供页面、匹配、版本比较和截图计划直接查询。
- 投影必须能从原始 Artifact 重建；原始文件不能成为每次查询的在线数据源。
- 所有 PLMXML 均必须流式解析，不能按文件大小选择构造整棵 DOM；20MB 只作为当前真实样本和最低规模测试门槛。
- XML 解析必须关闭 DTD、外部实体、参数实体、XInclude 和解析时的外部资源加载。
- `Representation.location`、JT、Teamcenter、UNC、`file:`、`http:` 和 `https:` 只作为不透明来源字符串投影；解析器不得自动访问。
- 上传和解析设置版本化硬上限：压缩前后字节数、元素数、嵌套深度、单元素属性数、单字符串长度、引用边数、单节点入边数、解析时长和内存预算。阶段 0 用真实样本确定数值，数值未固定前阶段 1 被阻断。
- 循环引用、断链、重复 ID、引用爆炸、超限和超时返回稳定结构化错误，不生成部分“成功”快照。
- 原始 Artifact 必须绑定 tenant、actor、owner 和访问策略；本地路径、Teamcenter 链接、JT 链接及 BOM 业务标识按敏感数据处理，不进入普通日志或未授权 UI。
- 仅上传 PLMXML 的模式是“无 VisMockup 的云端结构评估”，不能执行 COM、高亮、截图或版本固定前运行验证，也不能宣传为离线业务模式。

### 4.3 阶段 0 工程样本证据（2026-09-09）

以 21,415,803 字节真实 PLMXML 样本执行只读流式解析：共 214,205 个元素、138,791 条引用、最大深度 7、14,170 个 ProductInstance；其中 BOM 行 `W01-89184128/00;1` 有 6 个不同实例。单次解析耗时 7.032 秒，Python `tracemalloc` 峰值 53.0 MiB。实施时必须把样本 SHA-256、执行命令、解析器代码 revision 和完整结果保存为工程证据；本段事实不能替代 `runtime_verified`。

`plmxml-projection.v1` 当前硬上限固定为：输入 64 MiB、750,000 个元素、深度 160、单元素 64 个属性、单字符串 1 MiB、2,000,000 条引用、单节点 100,000 条入边、250,000 个投影实例、30 秒解析时长，分块大小 64 KiB。DTD、通用/参数/外部实体和 XInclude 直接拒绝；Representation location 保持不透明且解析器没有外部 I/O 入口。实测样本峰值低于阶段 0 的 256 MiB worker 内存预算；部署解析任务还必须配置进程/容器内存上限，避免仅依赖应用层计数。

每次快照至少投影：

- 文档、快照、父快照 GID；
- PLMXML 内部 ID 和父子路径；
- 完整 BOM 行号、item ID、revision ID；
- `catiaOccurrenceName`、VPPS、JT/Teamcenter 模型引用；
- 原始 16 值矩阵、规范化矩阵、位置和旋转摘要；
- 分类状态、实例状态和与上一快照的差异类型。

### 4.4 坐标规范化

- 原始矩阵字符串完整保留，用于审计和重新计算。
- 位置按 0.001 mm 规范化。
- 旋转使用固定容差和稳定摘要；具体容差在真实样本验证后固化为版本化算法参数。
- 原始浮点变化但规范化后相等，记录为数值漂移，不形成新实例或业务变更。
- 来源装配姿态、仿真阶段姿态和当前运行姿态分别保存，避免仿真移动污染来源身份。

## 5. GID 与实例身份

### 5.1 GID 规则

- 所有持久业务实体使用 `backend.platform_sdk.ids.next_gid()` 生成的雪花 GID。
- 数据库存有符号 `BIGINT`；Python 使用 `int`；JSON 和 JavaScript 使用十进制字符串。
- Electron renderer、AppHost 和 VisMockup Adapter 不生成持久业务 GID。
- `window_handle`、进程 ID、COM handle、PLMXML `instNN` 和 VM `node_key` 都是瞬时技术标识。

需要 GID 的实体包括环境、环境版本、环境节点、VM 文档、会话、快照、实例、实例观察、姿态、绑定、绑定修订、跨域操作、复合锚点、比较运行、截图运行和截图步骤。

### 5.2 完全相同与逻辑延续

只有完整 BOM 行号和规范化完整坐标都一致，才标记为“完全相同”。其中完整 BOM 行号必须保留类似 `W01-89184128/00;1` 的版本和行号部分。

“完全相同”与“逻辑上同一实例发生变化”是两个概念：

- 完全相同：身份和姿态均未变化；
- 已移动：逻辑实例延续，但姿态改变；
- 已升版：由旧实例指向新不可变数模引用；
- 新增/删除：实例生命周期变化；
- 待确认：证据不足或候选不唯一。

### 5.3 零件身份

- BOM 行号、`catiaOccurrenceName` 和父级结构路径能证明连续时，坐标变化保留原 occurrence GID，并新增姿态版本，标记“已移动”。
- 这覆盖用户做动态仿真后忘记还原零件位置的情况。
- 证据不能唯一对应时不自动复用 GID。

### 5.4 资源实例身份

工具、设备、工装、套筒可能重复加载且经常移动：

- 同一数模号在同一快照中位于不同位置，默认是不同实例，各有 GID。
- 同一 live occurrence 在一次会话内移动，保留 GID并新增姿态版本。
- 跨会话只有实例链路明确连续时才复用 GID。
- 删除后再次加载，即使数模号和位置相同也创建新 GID，并以 `predecessor_gid` 关联旧实例。

### 5.5 数模升版

- 新 Teamcenter/数模版本创建新的不可变模型引用和实例 GID。
- 新实例以 `predecessor_gid` 指向旧实例。
- 系统基于物料号、`catiaOccurrenceName`、父级路径和坐标提出绑定迁移候选。
- 用户选择继承、替换、保留旧版本、解除或重新绑定。
- 历史环境版本和截图始终引用旧数模，不能被新版本覆盖。

## 6. 知识库反查与分类

### 6.1 分类原则

不能根据用户把 VM 节点拖到哪个树位置来猜测类型，因为需求工具、需求工装、需求设备和需求套筒是 BOP 关系，未必作为结构节点出现。

正确流程是：

```text
VM 实例 -> 数模号/BOM 信息 -> Knowledge 批量反查 -> 资源类型与知识对象候选 -> 用户绑定
```

自动分类只允许规范化后的精确数模号匹配。模糊搜索仅用于用户手动查找候选。无匹配或多匹配时在页面内显示“待确认”，不得静默猜测，也不得弹出重复 Capability 确认窗口。

### 6.2 Capability 边界

现有 `knowledge.resource_model_mapping.resolve@1` 的方向是“类型化资源编码 -> 数模引用”，可复用其映射数据，但不足以完成“数模号 -> 类型和资源对象”的批量反查。需要由 Knowledge owner 定义新的原子只读能力，暂定候选为：

`knowledge.resource_model_mapping.reverse_resolve@1`

输入应为有界的数模号数组和可选上下文，输出每个输入的精确候选、未找到或歧义状态。Knowledge 负责的类型至少覆盖 `tool`、`fixture`、`equipment`、`socket`，是否包含 `extension` 由知识域确认。零件身份应由 Teamcenter/产品 BOM、当前 VM 结构和 BOP 产品绑定共同确认，不能因为知识库未命中资源就自动推断成零件。

Simulation 只能通过 Gateway/SDK 消费该能力，不能直接查询 VPPS 或 Knowledge 表。

## 7. Load 零件与作业关系

### 7.1 两种零件关系

一个零件可能在某工位上车，并在后续工位或工序被紧固。因此需要区分：

- `load`：零件进入装配状态的唯一装载关系；
- `operate`：后续紧固、检查等步骤对已装载零件的作业引用。

一个零件实例在一个环境中原则上只有一个 load 点，但可以有多个 operate 关系。选定截图范围内找不到 load 点时，按“范围开始前已装载”处理。

### 7.2 BOP 属性来源

2026-09-09 对运行中的 `test_` 数据表、本体类与属性定义、Craft Schema 和现有导入/导航代码做了只读核对。权威字段是 Craft BOP 的 `part_feed`：

- `workmanship_bop_bop_entries.part_feed`、`workmanship_bop_bop_process.part_feed` 和 `workmanship_bop_bop_steps.part_feed` 均为非空布尔字段，默认值为 `false`；
- 标准操作导入把 `match_tag=part_feed` 规范化为 `part_feed=true`，现有界面称其为“零件投料”；
- 工序与操作可以各自持有该字段，工序级截图计划按被绑定零件所在的工序/操作读取值，操作值不覆盖同工序内其他操作；
- `false` 同时覆盖“明确不投料”和历史未标注。冻结版本必须保存读取的 BOP revision、字段值与投影算法版本，不能事后重解释历史值；
- 运行本体中没有另一个等价的 Load 布尔属性，`critical_process` 与此语义无关。

Craft 的执行结构投影对外规范化为 `parameters.is_load_part`，Simulation 不直接读取 Craft 表。后续 owner 复审仍需确认同一零件被多处标记时的诊断规则、历史 `false` 是否要区分“未标注”，以及正式 Capability 版本。

## 8. 倒序截图状态模型

### 8.1 基本规则

- 每个工序一张图。
- 操作参与装载、作业和顺序计算，但默认不单独截图。
- 工序图片表示该工序所有操作完成后的状态，并汇总高亮本工序涉及的零件。
- 工具、设备、工装和套筒按当前工序需要显示或着色。
- 选中较大节点时，对其范围内的工序按确定顺序生成截图。

### 8.2 正向状态与倒序执行

先根据 BOP 顺序计算每个工序完成后的累计装配状态，再按倒序驱动 VisMockup：

1. 将场景设置为选定范围结束时的累计状态。
2. 当前工序涉及的零件着色。
3. 截图并上传，一张图关联一个工序。
4. 清除当前着色。
5. 仅当倒退越过某零件的 load 点时隐藏该零件。
6. 普通紧固、检查等 operate 关系不会导致零件隐藏。

截图运行绑定冻结的环境版本、VM 快照、BOP 来源版本、capture profile 和有序步骤哈希。任一输入发生变化必须创建新运行。

### 8.3 场景保护与失败语义

运行开始前，Connector 必须读取并持久化可恢复的场景状态，至少包含 visibility、color、selection、camera 以及活动文档身份；如 VisMockup API 无法完整读取某类状态，阶段 0 必须记录缺口，并在截图前向用户明确显示可恢复范围。

场景 baseline 存入 ConnectorHost 的 durable local journal，并使用当前 Windows 用户的 DPAPI 或等价安装态密钥加密。记录必须同时绑定 tenant、actor、device、plan、document、runtime generation、runtime instance 和 journal sequence；不得写入普通日志，也不得把完整本地场景无界上传云端。journal 对单记录字节数、节点/条目数和保留期设置硬上限。运行到达确定终态且云端确认场景恢复后受控清理；处于 `outcome_unknown` 或 `manual_review_required` 时保留至对账完成或保留期截止，截止清理也要留下不含场景内容的审计摘要。

每个截图步骤严格执行：

1. 校验活动文档、冻结环境版本、VM 快照和 baseline hash；
2. 应用该工序的期望可见集、颜色和相机；
3. 读取场景摘要并验证 post-condition；
4. 调用 VisMockup 内部截图；
5. 校验 Artifact hash、MIME、尺寸和字节数并完成上传；
6. 通过 Craft Capability 幂等关联工序；
7. 只有关联结果确定后才清除本步着色，并在越过 Load 点时隐藏零件；
8. 写入签名 step outcome 和 journal sequence。

单步失败、上传失败、取消、App/ConnectorHost/VisMockup 崩溃时停止后续步骤，并 best-effort 恢复运行前场景。恢复本身也要记录 outcome；不能证明截图或恢复结果时进入 `outcome_unknown` / `manual_review_required`。再次操作前先对账，不得通过重复截图猜测结果。成功、失败、取消和恢复都不能永久污染工程师原有场景。

## 9. 项目主环境与正式 BOP 边界

### 9.1 同一项目版本

节点评审主环境直接绑定项目在线活动 BOP。项目管理者和获授权工程师的结构、零件 load/operate 及资源需求修改由 Craft Capability 写入当前活动 BOP；Simulation 同步保存 VM 实例、姿态、截图和 VisMockup 映射。普通协作不经过私人环境合并或发布流程。

建立基线或冻结时，由 Simulation 拥有的 `environment_anchor` 通过可对账 saga 关联 Craft 不可变 snapshot ref、精确 capability version/content hash 与 Simulation canonical manifest。锚点经历 `preparing/ready/failed/reconciling`；只有两侧重新校验完成的 `ready` 锚点可对用户表示为同一评审版本。它不是 Project Management 的“正式项目版本”，也不构成跨域数据库事务。该锚点对 project_main 强制；无 Craft 来源的空白或纯 VM ad_hoc 版本只走 Artifact + Simulation saga。

### 9.2 不写入 BOP 主结构的内容

- VisMockup 的窗口、进程和 COM 标识；
- 资源实例的运行位置和移动轨迹；
- 交互选择、高亮和临时显隐状态；
- PLMXML 内部瞬时 ID；
- 未被用户选择的临时节点和关系。

坐标、轨迹、差异和截图过程归 Simulation；BOP 表达工艺结构、装载、作业和资源需求。

### 9.3 并发与冲突

- 在 `G-Craft-Collab` 通过前，所有结构修改继续使用 Craft 整 BOP revision/CAS，不承诺不同线体永不阻塞。
- 目标线体独立协作依赖 Craft owner 提供线体授权、线体 revision 或安全可交换 rebase、完整 checkpoint、双线体原子移动、幂等与审计合同。
- 跨线体移动仅项目管理者可执行；若当前 Craft 合同不能原子保护来源与目标线体，则阻止操作。
- revision 冲突时只重新读取受影响线体，保留用户视点和未提交意图，禁止覆盖或盲目重试。
- 私人和共享池环境不回写项目主环境，不提供 merge、pull 或 push。

## 10. 建议的数据模型

以下名称为实施设计候选，最终迁移前需核对现有表：

协作、共享、Fork 和手动版本的实际扩展表及字段以 2026-09-09 细化设计为准；下表保留原始核心对象边界。

| 表 | Owner | 作用 |
|---|---|---|
| `workmanship_sim_environment_workspaces` | simulation | 用户可变仿真环境及 draft head |
| `workmanship_sim_environment_versions` | simulation | 冻结版本、来源 BOP 和 manifest hash |
| `workmanship_sim_environment_nodes` | simulation | 临时节点与 BOP 引用节点的覆盖投影 |
| `workmanship_sim_vm_documents` | simulation | VM 文档演进链 |
| `workmanship_sim_vm_sessions` | simulation | VisMockup 窗口连接会话 |
| `workmanship_sim_vm_snapshots` | simulation | 已接受快照与原始 ArtifactRef |
| `workmanship_sim_vm_occurrences` | simulation | 逻辑实例身份及 predecessor |
| `workmanship_sim_vm_occurrence_observations` | simulation | 每快照观察与分类状态 |
| `workmanship_sim_vm_poses` | simulation | 来源、阶段及运行姿态 |
| `workmanship_sim_environment_bindings` | simulation | load、operate、resource_use 等绑定 |
| `workmanship_sim_environment_anchors` | simulation | Craft snapshot 与 Simulation manifest 的复合锚点和 saga 状态 |
| `workmanship_sim_main_projection_operations` | simulation | Craft 操作引用、Simulation 投影和对账状态 |

现有环境 manifest、snapshot request、capture run 和 Connector 表继续复用。新增表不复制 Craft、Knowledge、Digital Model 或 Teamcenter 的可写主数据，仅保存带版本的引用和快照事实。

### 10.1 冻结版本与可复现性

冻结版本不是只保存一个 `manifest_hash`。每个 `environment_version_gid` 必须绑定一个不可变 canonical manifest Artifact 及其 SHA-256，并在数据库中保留可查询的 version membership/projection。manifest 使用 owner/source 列表，只固定实际存在的来源；project_main 强制 Craft snapshot，ad_hoc 的 Craft source 可选。canonical manifest 至少固定：

- 环境节点集合、父子关系、顺序和来源类型；
- 每条绑定及 binding revision，包括 load、operate、resource_use；
- 来源装配姿态和被截图使用的阶段姿态；
- `source_bop_version_gid`、BOP content hash 和 Load 属性投影版本；
- `vm_document_gid`、`vm_snapshot_gid`、原始 PLMXML ArtifactRef 和 snapshot hash；
- Knowledge、Craft、Digital Model 的不可变引用与版本；
- 身份匹配、坐标规范化、diff 和截图计划算法版本；
- capture profile、创建者、冻结时间和敏感级别。

所有历史 capture run、Diff 和可复现运行只能引用不可变 `environment_version_gid`，不能引用可变 draft head。

### 10.2 关系与并发约束

- 所有表必须包含 `tenant_gid`，用户对象包含 `owner_user_gid`，写入同时校验 tenant 和 owner selector。
- GID 唯一且永不复用。workspace 使用与 lifecycle/archive 正交的 `deleted_at/deleted_by/deletion_gid` tombstone；默认查询排除 deleted，审计查询可显式包含。
- draft head 使用 `row_version` 和 compare-and-swap；客户端提交 `expected_resource_version`，冲突后重新读取，禁止 last-write-wins。
- 自动保存每次编辑使用稳定 operation ID 和唯一幂等键；相同 key + 相同 payload 返回原结果，不同 payload 返回幂等冲突。
- version membership、binding revision、snapshot sequence、实例观察和环境锚点设置域内唯一键及同租户约束；跨域只保存 GID/ref/hash，不建立跨域外键或 cascade。
- 冻结采用跨资源 saga，不能把 Base Platform Artifact Capability 和 Simulation 数据库描述成一个事务：先通过受治理 Base Platform Artifact Capability 以 operation/idempotency 创建并 finalize 不可变 Artifact；再校验 ArtifactRef、hash、tenant 和访问范围；随后在 Simulation 单库事务中写入 version、membership、ArtifactRef/hash 和审计，提交后才令版本可见。OIS 只是 Artifact 字节存储的 Provider 实现，不是并列业务 owner。
- Simulation 数据库失败时将已完成 Artifact 标记为 orphan，交由 Base Platform Artifact Capability 的受控保留/回收流程处理；数据库成功但 Artifact 暂时不可读时将版本标记为 unavailable 并对账，禁止用重新序列化的不同 bytes 替换原 Artifact。
- archive/delete 与 capture/materialize/snapshot/comparison/reconciliation 的 run-lease 获取在同一 workspace guard/行锁上串行化；有活动 lease 返回 `active_run_exists`，archive/tombstone 落库后禁止新 lease。
- archived active project_main 仍占唯一槽位；只有 frozen 或 deleted 释放槽位，避免 archive→create→restore 产生两个 active main。
- 使用新增 `0012` 迁移增加状态维度、版本种类、锚点、lineage 与 tombstone；不得修改已执行的 `0011_simulation_workspaces.sql`。0011 的 publish plan/map/outbox 停止新写入和新消费者，仅保留历史只读兼容。
- archive 可恢复且不改变 active/frozen；delete 只写 tombstone，不删除不可变版本、Fork base、Diff、审计或其他领域数据。第一阶段不实现物理 purge。

### 10.3 大树读取与算法版本

- VM 树、环境树、候选搜索和 diff 均使用 cursor 分页或有界 lazy-load，并强制 `max_depth`、`max_nodes`、`page_size` 和稳定排序。
- PLMXML 解析和大型 diff 在后台任务中执行；页面轮询/订阅状态，不能阻塞 Gateway 请求。
- 坐标规范化、实例匹配、diff 和截图计划算法各自有稳定 `algorithm_id` 与版本，并写入 snapshot、frozen manifest 和 run input hash。
- 历史版本按其原算法读取；升级算法必须显式重算为新快照或新环境版本，不能让相同历史版本得出不同结果。

## 11. Capability 治理结论

### 11.1 权威现状与复用差距

以下现状来自当前受检 Catalog/Descriptor/Provider 代码；实施时仍须从运行 Registry 和当前 Catalog Release 重新读取并绑定真实 version GID。表内新 ID 和升版判断均为 advisory 候选。

| 业务效果 | 现有能力 | 静态 Catalog 生命周期 | 判定 | 主要差距与处理 |
|---|---|---|---|---|
| 通用可复现仿真环境 CRUD | `simulation.environment.create/get/search/archive@1` | stable | 保持兼容，不改变语义 | 现有环境由四个不可变引用组成，不承载用户可变工作区；不能复用为 draft。 |
| 从固定来源生成 Connector manifest | `simulation.environment.compose@1/@2` | `@1 stable`；`@2 experimental` | 优先复用，先做契约差距检查 | `@2` 可用于受控开发验证；若无法绑定 frozen workspace、load/operate、算法版本和完整 VM snapshot，则新增后续主版本，不得扩写旧输出。 |
| manifest 读取、查询、归档 | `simulation.environment.manifest.get/search/archive@1` | stable | 复用 | 查询增加 cursor/max_nodes 若属兼容可选参数；改变默认边界则升主版本。 |
| 活动 VM 文档快照两阶段流程 | `simulation.document_snapshot.request@1/@2`、`get/action.get/dispatch@1` | `request@1 deprecated`；`request@2 experimental`；配套 get/action/dispatch experimental | 复用工作流，快照契约预计升主版本 | 新契约需绑定原始 PLMXML Artifact、文档/session、解析任务、上限、算法版本和差异；建议后续主版本，最终由 owner 差距评审决定。 |
| 环境预检与物化 | `simulation.environment.preflight@1`、`simulation.environment.materialize@1`、`simulation.environment.materialize@2`、`simulation.environment.materialization_run.action.get@1`、`simulation.environment.materialization_run.action.dispatch@1` | preflight stable；materialize@1 deprecated；materialize@2 及 action get/dispatch experimental | 复用两阶段模式 | 物化输入必须固定 frozen version 和 scene baseline；若现有 Schema 不可表达则升主版本。 |
| 倒序截图运行 | `simulation.capture_run.start@1/@2`、`get/action.get/dispatch/cancel@1`、`capture_step.retry@1` | `start@1 deprecated`；`start@2` 与 action/dispatch experimental；get/cancel/retry stable | 复用状态机，`start` 预计升主版本 | 新语义是每工序一图、Load 边界隐藏、场景备份/恢复和严格 outcome 对账；不得在 `start@2` 静默改义。 |
| VM 应用、模型、树、选择、高亮、显隐和截图 | `simulation.vismockup.*@1`、Connector binding/health 相关能力 | 当前所查 `vismockup.*@1` 均 experimental；binding/health 状态由 G0 校正 | 仅用于受控开发验证并做逐项差距检查 | 全部必须改走 execution-plan/outcome v2 唯一路径；不能保留 renderer/IPC/bridge 旁路。 |
| Artifact 导入与读取 | `base.artifact.import/get/bytes.get@1` | 当前所查均 experimental | 仅用于受控开发验证并做差距检查 | 冻结需要“创建/finalize 不可变 Artifact”的明确效果；若 import 不能保证该效果，由 Base Platform owner 新增能力，Simulation 禁止直连 OIS。 |
| 资源编码解析数模 | `knowledge.resource_model_mapping.resolve@1` | stable | 复用映射数据，不复用方向 | 现有方向为资源编码到数模引用，不能冒充反查。 |
| 数模号反查资源 | 无已验证同义能力 | not applicable | 新 Capability 候选 | `knowledge.resource_model_mapping.reverse_resolve@1`；Knowledge owner 审批前不得实现或注册。 |
| BOP 草稿预览和应用 | `craft.bop.draft.change.preview/apply@1` | stable | 优先复用 | 若无法表达父依赖、load/operate、资源需求或结构化冲突，由 Craft owner 决定 compatible change 或 new major。 |
| 工序截图关联 | `craft.process_screenshot.attach@1` | stable | 复用 | 保持 Craft owner 和幂等关联，不由 Simulation 写 Craft 表。 |
| 不可变数模版本读取 | `digital_model.version.get@1` | stable | 复用 | VM snapshot 保存版本引用，不复制 Digital Model 主数据。 |

G0 必须用运行 Snapshot 校正所有 version GID 和 lifecycle status。产品和正式发布路由只能固定到 `stable`；`experimental` 仅用于隔离的开发验证，在完成晋升、精确 hash 人工审批和运行证据前不能成为 release target；`deprecated` 不得成为新消费者依赖。

#### 11.1.1 业务 Capability 到 Adapter operation 映射

| 用户业务意图/Capability | v2 plan 中的 Adapter operation | 当前状态与边界 |
|---|---|---|
| 识别并挂接已打开 VisMockup | `vismockup.application.attach@1` | 现有 `simulation.vismockup.application.attach.request@1` 为 experimental；Adapter 缺口由阶段 0 验证，不能用 IPC 直连替代 |
| 启动 VisMockup | `vismockup.application.launch@1` | 现有 request 为 experimental；必须校验签名安装路径，VisMockup 独立于 App Job 生命周期 |
| 打开/关闭模型 | `vismockup.model.open@1` / `vismockup.model.close@1` | 现有 request 为 experimental。AI00 App 退出永远不关闭 VisMockup 进程或文档；用户显式调用 close/unload Capability 时，可作用于当前已批准并绑定的 VisMockup session 中的既有文档，不限于 AI00 打开的模型。操作必须绑定精确 session/document、当前 actor/device、confirmation receipt 和 post-condition，不能误关其他窗口或文档；结果不确定时先对账。删除 AI00 binding 不等于卸载模型。 |
| 读取有界 VM 树 | `vismockup.document.tree.read@1` | 现有 tree request 为 experimental；必须分页/lazy-load、max_depth/max_nodes |
| 导出当前 PLMXML | `vismockup.document.export_plmxml@1` | Adapter operation 缺口；作为 document snapshot 计划中的白名单步骤，不单独升格为用户 Capability |
| 选择/高亮实例 | `vismockup.selection.highlight@1` | 现有业务能力 experimental；写 COM 但无持久业务修改，仍走 plan v2 |
| 应用显隐/颜色/相机 | `vismockup.scene.apply@1` | 现有 visibility 仅覆盖部分效果；场景操作是 materialize/capture 的受控步骤，不开放任意 COM |
| 校验场景 | `vismockup.scene.verify@1` | Adapter operation；无独立用户业务效果，用于 post-condition |
| 内部截图 | `vismockup.view.capture@1` | 现有 capture 能力 experimental；由 capture run 计划调用并产出本地 Artifact |
| Connector 状态/设备绑定 | 无 COM operation | 复用 Connector pairing/binding/health Capability；只管理设备和运行状态，不携带业务命令 |

Adapter operation 只描述受签名 plan 调用的本地白名单技术效果。没有独立授权、业务结果和消费者的 operation 不注册为用户 Capability。

### 11.2 新业务效果到 Capability 候选矩阵

以下矩阵受 2026-09-09 协作版本细化设计约束。只有已注册且 Registry lifecycle 为 experimental 的能力可称为 experimental；其余均为 `not_registered` 设计项。最终命名、confirmation 和生命周期由 owner 基于业务风险与当前 Registry 决定。Gateway/Provider 根据资源 GID 和可信上下文在服务端解析 tenant/owner/project scope；客户端不得提交授权结论。

| 原子业务效果 | advisory Capability 候选 | Owner / Provider / 消费者 | 权限、确认与并发 | 事务、稳定错误和审计 |
|---|---|---|---|---|
| 创建私人零散工作区 | `simulation.environment.workspace.create@1` | Simulation / Simulation Provider / Desktop cad_sim | 创建后固定 private；confirmation 待风险评审；幂等 | 已有 experimental 候选需做定义变更、重建 hash 和迁移消费者 |
| 创建项目主环境 | `simulation.environment.project_main.create@1` | 同上 | 当前项目管理权限；服务端锁定唯一槽位 | not_registered；只引用 Craft mutable draft/head |
| 查询当前用户可见的工作区列表 | `simulation.environment.workspace.search@1` | 同上 | 私人 owner、同租户共享、项目可见；`confirmation=none`；cursor/page_size | 只读；稳定分页和查询摘要审计 |
| 读取一个可见工作区及 draft head | `simulation.environment.workspace.get@1` | 同上 | 服务端可见范围 selector；`confirmation=none`；有界 projection | 只读；not found/resource denied |
| 修改名称或非语义元数据 | `simulation.environment.workspace.metadata.update@1` | 同上 | owner；项目主环境允许项目管理者；CAS + 幂等 | 单库 CAS；metadata revision 审计 |
| 共享工作区 | `simulation.environment.workspace.share@1` | 同上 | owner；逐引用验证再分发权；CAS + 幂等 | not_registered；与 create/fork/metadata update 分离 |
| 取消共享工作区 | `simulation.environment.workspace.unshare@1` | 同上 | owner；CAS + 幂等 | not_registered；既有 Fork 不失效 |
| 归档工作区 | `simulation.environment.workspace.archive@1` | 同上 | private/shared owner；project_main 当前项目管理者；guard 锁与 run lease 串行 | not_registered；不改变 active/frozen lifecycle |
| 恢复工作区 | `simulation.environment.workspace.restore@1` | 同上 | 原授权主体；CAS + 幂等 | not_registered；archived active main 一直占唯一槽位 |
| 删除工作区 | `simulation.environment.workspace.delete@1` | 同上 | private/shared owner；project_main 当前项目管理/删除权限；CAS + 幂等 | tombstone；不含 purge，不级联其他领域或关闭 VisMockup |
| 创建一个临时结构节点 | `simulation.environment.structure_node.create@1` | 同上 | 私人/共享 owner；主环境获授权线体；CAS + 幂等 | parent/type/limit 校验；create 审计 |
| 移动一个临时结构节点 | `simulation.environment.structure_node.move@1` | 同上 | 私人/共享 owner；主环境线体权限；跨线体仅项目管理者 | parent/cycle 校验；from/to 审计 |
| 软删除一个临时结构节点 | `simulation.environment.structure_node.remove@1` | 同上 | 私人/共享 owner；主环境获授权线体；CAS + 幂等 | 依赖校验；remove 审计 |
| 调整同父节点下一个节点的顺序 | `simulation.environment.structure_node.reorder@1` | 同上 | 私人/共享 owner；主环境获授权线体；CAS + 幂等 | 稳定 order key；before/after 审计 |
| 创建一条 load/operate/resource_use 绑定 | `simulation.environment.binding.create@1` | 同上 | 私人/共享 owner；主环境获授权线体；CAS + 幂等 | load 唯一性和引用校验；create 审计 |
| 修改一条绑定的角色或目标 | `simulation.environment.binding.update@1` | 同上 | 私人/共享 owner；主环境获授权线体；binding CAS + 幂等 | 追加 revision；before/after 审计 |
| 解除一条绑定 | `simulation.environment.binding.remove@1` | 同上 | 私人/共享 owner；主环境获授权线体；CAS + 幂等 | 软删除 revision；remove 审计 |
| 保存一个不可变手动版本 | `simulation.environment.workspace.version.save@1` | Simulation / Simulation Provider / Desktop、capture | owner/项目管理者；CAS + 幂等 | Base Artifact + Simulation DB saga；完整 BOP/VM 锚点 |
| Fork 一个可见环境状态 | `simulation.environment.workspace.fork@1` | Simulation / Simulation Provider / Desktop | 来源及底层引用可读；新环境固定 private；幂等 | not_registered；活动来源先建 fork-base；复用 immutable Artifact 并保留 lineage |
| 冻结 draft 为不可变版本 | `simulation.environment.version.freeze@1` | Simulation / Simulation Provider / Desktop、capture | owner/项目管理者；CAS + 幂等；confirmation 待评审 | Base Platform Artifact Capability + Simulation DB saga；version/hash 审计 |
| 读取一个不可变版本 | `simulation.environment.version.get@1` | Simulation / Simulation Provider / Desktop | 按来源环境可见范围；`confirmation=none`；有界 projection | 只读；not found/resource denied |
| 查询手动版本历史 | `simulation.environment.version.search@1` | 同上 | 按来源环境可见范围；`confirmation=none`；cursor/page_size | 只读；稳定排序 |
| 启动两个版本的大型比较 | `simulation.environment.version_compare.start@1` | Simulation / Simulation Provider / Desktop | 左右版本均可读；confirmation 待评审；幂等；max_nodes | 创建只读计算任务；input/algorithm hash 审计 |
| 读取比较进度和分页结果 | `simulation.environment.version_compare.get@1` | 同上 | 比较任务可读；`confirmation=none`；cursor/page_size | 只读；algorithm unavailable/limit exceeded |
| 建立复合锚点 | `simulation.environment.environment_anchor.create@1` | Simulation / Simulation Provider / Desktop、scheduler | project_main 或含 Craft source 的 ad_hoc；两域精确版本和 hash；幂等 | not_registered；创建 preparing saga |
| 读取复合锚点 | `simulation.environment.environment_anchor.get@1` | 同上 | 授权只读 | not_registered；只有 ready 可作成功版本使用 |
| 对账复合锚点 | `simulation.environment.environment_anchor.reconcile@1` | 同上 | expected state；幂等 | not_registered；收敛 ready/failed/reconciling |
| 读取主环境投影操作 | `simulation.environment.main_projection_operation.get@1` | Simulation / Simulation Provider / Desktop、scheduler | 授权只读 | not_registered；返回 Craft outcome ref 与投影状态 |
| 对账主环境投影操作 | `simulation.environment.main_projection_operation.reconcile@1` | 同上 | expected state；幂等 | not_registered；只修复 Simulation 投影，不重放 Craft 写入 |
| 启用版本策略 | `simulation.environment.version_policy.enable@1` | Simulation / Simulation Provider / Task Tool | shared owner delegation；CAS + 幂等 | not_registered；固定 Catalog release 与 Capability majors |
| 更新版本策略 | `simulation.environment.version_policy.update@1` | 同上 | shared owner；CAS + 幂等 | not_registered；新 policy hash/version |
| 停用版本策略 | `simulation.environment.version_policy.disable@1` | 同上 | shared owner；CAS + 幂等 | not_registered；撤销 delegation，版本不变 |
| 读取版本策略 | `simulation.environment.version_policy.get@1` | 同上 | owner/Task Tool 只读 | not_registered；敏感字段裁剪 |
| 评估版本策略 | `simulation.environment.version_policy.evaluate@1` | 同上 | Task Tool；确定性只读 | not_registered；LLM 不参与创建决定 |
| 接受一次已解析 VM 快照差异 | `simulation.document_snapshot.change.accept@1` | Simulation / Simulation Provider / Desktop | owner only；expected head + 幂等；confirmation 待评审 | 单库 CAS；accepted/rejected diff 审计 |
| 接受数模升版后的绑定迁移 | `simulation.environment.binding_migration.accept@1` | Simulation / Simulation Provider / Desktop | owner only；expected draft + 幂等；confirmation 待评审 | 单库 CAS；predecessor/target 审计 |
| 按数模号批量精确反查知识资源 | `knowledge.resource_model_mapping.reverse_resolve@1` | Knowledge / Knowledge Provider / Simulation | `knowledge.read`；tenant 来自可信上下文；`confirmation=none`；有界批量 | 逐项 resolved/not_found/ambiguous；查询摘要审计 |

每个候选在进入代码前必须使用治理变更记录模板补齐真实 `capability_version_gid`、business effect/invariants、闭合输入输出、Provider、Gateway exposure、消费者、表/迁移、测试和当前 Snapshot。上表不能作为注册或审批依据。

#### 11.2.1 候选契约闭合边界

| Capability | 闭合输入 | 闭合输出 | 副作用/补偿 | 必须建立的测试证据 |
|---|---|---|---|---|
| `simulation.environment.workspace.create@1` | name、可选 source refs、幂等键 | private ad_hoc workspace/head GID、row version、来源摘要 | 创建私有 workspace；失败回滚；不得同时共享 | 成功、幂等冲突、来源不可见、跨租户、Schema |
| `simulation.environment.project_main.create@1` | project、Craft draft ref、expected slot、幂等键 | project_main workspace/head、row version | guard 锁内占唯一槽位；失败回滚 | 项目权限、并发唯一、archived 占位、frozen/deleted 释放 |
| `simulation.environment.workspace.search@1` | cursor、page_size、允许的状态/名称筛选 | summaries、next_cursor | 无 | owner 隔离、分页稳定、筛选、上限 |
| `simulation.environment.workspace.get@1` | workspace GID、projection page selector | workspace、draft head、有限节点/绑定页 | 无 | owner 隔离、not found、分页、Schema |
| `simulation.environment.workspace.metadata.update@1` | workspace、允许字段 patch、expected row version、幂等键 | 新 row version、metadata revision | 单库 CAS | 字段 allowlist、CAS、幂等、跨 owner |
| `simulation.environment.workspace.archive@1` | workspace、expected row version、幂等键 | archived status、row version | 软归档；历史保留 | 活跃运行阻止、重复归档、CAS、历史读取 |
| `simulation.environment.workspace.restore@1` | workspace、expected row version、幂等键 | archived_at=null、原 lifecycle、row version | guard 锁内恢复 | 权限、CAS、active main 唯一、重复恢复 |
| `simulation.environment.workspace.share@1` | workspace、expected row、幂等键 | shared visibility、row version、引用授权摘要 | 校验全部来源再分发权；必要时受控脱敏 | owner、租户、分类、底层 Artifact/source 策略 |
| `simulation.environment.workspace.unshare@1` | workspace、expected row、幂等键 | private visibility、row version、Fork 摘要 | 停止新共享访问；既有 Fork 保持 | owner、CAS、租户、既有 Fork |
| `simulation.environment.workspace.delete@1` | workspace、expected row version、幂等键 | deletion GID、deleted_at、保留引用摘要 | tombstone；无跨域级联；不关闭 VisMockup | owner/项目权限、运行阻塞、legal hold、CAS、幂等、Fork 仍可读、槽位释放 |
| `simulation.environment.structure_node.create@1` | workspace、parent、node type、初始字段、expected row version、幂等键 | node GID/revision、新 row version | 单库 CAS | 类型/父级/上限、幂等、跨 owner |
| `simulation.environment.structure_node.move@1` | workspace、node、new parent/position、expected row version、幂等键 | node revision、新 row version、局部 patch | 单库 CAS | 环/父缺失/非法层级、CAS、局部刷新 |
| `simulation.environment.structure_node.remove@1` | workspace、node、明确依赖策略、expected row version、幂等键 | removed revision、新 row version、影响摘要 | 软删除；失败回滚 | 子节点/绑定依赖、重复删除、CAS、历史不变 |
| `simulation.environment.structure_node.reorder@1` | workspace、node、同父目标位置、expected row version、幂等键 | order revision、新 row version、局部 patch | 单库 CAS | 跨父拒绝、边界位置、并发、稳定排序 |
| `simulation.environment.binding.create@1` | workspace、node、occurrence/resource ref、单一 role、expected row version、幂等键 | binding GID/revision、新 row version | 单库 CAS | load 唯一、多个 operate、资源多实例、未解析、幂等 |
| `simulation.environment.binding.update@1` | workspace、binding、允许字段 patch、expected binding/workspace version、幂等键 | 新 binding revision、row version | 追加 revision | role/target、load 冲突、CAS、旧 revision 不变 |
| `simulation.environment.binding.remove@1` | workspace、binding、expected binding/workspace version、幂等键 | removed revision、row version | 软删除 revision | 重复解除、CAS、冻结引用保护 |
| `simulation.environment.workspace.version.save@1` | workspace、expected row、实际 source list、算法版本、幂等键 | version、manifest ArtifactRef/hash、可选 anchor | Artifact+Simulation saga；有跨域来源才建 anchor | 空白、纯 VM、Craft overlay、并发、orphan、hash |
| `simulation.environment.workspace.fork@1` | source version 或 active workspace、expected source、幂等键 | private workspace、fork-base、lineage | 活动源先固定；复用 immutable Artifact/ref | 三类来源、权限、幂等、源删除后仍可读 |
| `simulation.environment.baseline.set@1` | workspace、version/snapshot request、expected row、幂等键 | baseline version/pointer、row version | 只改 pointer，不改 lifecycle | 历史不变、替换 pointer、CAS、权限 |
| `simulation.environment.version.freeze@1` | workspace、expected draft、snapshot/source refs、算法版本、幂等键 | environment version GID、canonical ArtifactRef/hash | Artifact finalize + DB saga；DB 失败标 orphan；Artifact 暂不可读则 unavailable 并对账 | membership/hash、并发、两侧失败、orphan、不可变、算法绑定 |
| `simulation.environment.version.get@1` | version selector、projection page | canonical metadata、projection page、next_cursor | 无 | 历史读取、owner、分页、Artifact unavailable |
| `simulation.environment.version.search@1` | workspace、cursor/page_size | version summaries、next_cursor | 无 | owner、分页、稳定排序、归档策略 |
| `simulation.environment.version_compare.start@1` | left/right version、algorithm version、max_nodes、幂等键 | comparison GID、input hash、status | 创建计算任务，不修改环境 | 幂等、算法缺失、节点上限、owner、input hash |
| `simulation.environment.version_compare.get@1` | comparison GID、cursor/page_size | 状态、摘要、分页差异、result hash | 无 | unchanged/moved/upgraded/added/removed、分页/hash |
| `simulation.environment.environment_anchor.create@1` | project_main、Craft expected revision/hash、Simulation expected row、幂等键 | anchor GID、preparing | 启动跨域 saga | 权限、并发、双侧故障、只有 ready 可用 |
| `simulation.environment.environment_anchor.get@1` | anchor GID | source refs/hash/state | 无 | 授权、裁剪、各终态 |
| `simulation.environment.environment_anchor.reconcile@1` | anchor、expected state、幂等键 | ready/failed/reconciling、evidence refs | 重校验两侧，不盲目重写 | 幂等、过期状态、Artifact/Craft 故障 |
| `simulation.environment.main_projection_operation.get@1` | operation GID | Craft outcome ref、projection state、audit | 无 | 授权、裁剪、稳定终态 |
| `simulation.environment.main_projection_operation.reconcile@1` | operation、expected state、幂等键 | projection terminal state、row/audit | 只投影既有 Craft outcome，不重放 Craft 写入 | 幂等、过期、Craft outcome 不可读、DB 故障 |
| `simulation.environment.version_policy.enable@1` | workspace、policy、delegation、expected row、幂等键 | policy GID/version/hash | 单库事务 | owner、Catalog pin、Capability majors、有效期 |
| `simulation.environment.version_policy.update@1` | policy、expected version、patch、幂等键 | 新 version/hash | 单库 CAS | allowlist、并发、审计 |
| `simulation.environment.version_policy.disable@1` | policy、expected version、幂等键 | disabled_at | 撤销 delegation，版本不变 | 幂等、权限、运行竞态 |
| `simulation.environment.version_policy.get@1` | workspace/policy | 裁剪的 policy/delegation | 无 | owner/Task Tool、敏感裁剪 |
| `simulation.environment.version_policy.evaluate@1` | policy、resource hash、Diff 摘要、trigger | deterministic create/skip 及原因 | 只读，不创建版本 | 相同输入同结果、阈值、频率、LLM 不参与 |
| `simulation.document_snapshot.change.accept@1` | document、candidate、accepted/rejected diff IDs、expected head、幂等键 | 新 head/sequence、未解决摘要 | 单库 CAS | 全部 diff 类型、过期候选、并发、幂等、跨文档拒绝 |
| `simulation.environment.binding_migration.accept@1` | workspace、candidate IDs、逐项 decision、expected draft、幂等键 | binding revisions、row version、剩余歧义 | 单库 CAS | inherit/replace/keep/unbind/rebind、过期、歧义、CAS |
| `knowledge.resource_model_mapping.reverse_resolve@1` | model numbers、允许的有效期/业务 selector、batch limit；无 tenant/actor payload | 输入逐项 resolved/not_found/ambiguous 与不可变 refs | 无 | 各资源类型、精确/非模糊、歧义、上限、敏感裁剪 |
| `craft.bop.draft.change.apply` 复用/升版 | Craft preview ref、expected BOP version、opaque client/correlation ref、receipt、幂等键 | Craft draft revision、Craft 节点/关系 GID、原样 opaque client_ref、Craft audit ref | Craft 只写自有草稿；不写 Simulation map | consumer contract、关系、CAS、receipt、client_ref 原样、重复 outcome |

所有输入 Schema `additionalProperties=false`，GID 在 JSON 中使用十进制字符串；数组、字符串、树深和分页均有硬上限。tenant 和 actor identity 来自可信 InvocationContext；payload 只提供闭合的 workspace_gid、binding_gid、version_gid 等资源标识。Gateway/Provider 根据资源标识在服务端解析规范 resource selector、tenant/owner scope 并授权，不接受 renderer 提供的 tenant、owner identity、预计算授权 selector 或“已有权限”的结论。输出不得包含原始凭据、本地绝对路径、未授权 Teamcenter/JT 链接或完整 PLMXML 内容。

候选能力的测试文件在实施计划中按 owner 放置：Simulation 放入 `plugins/simulation/tests/` 与 `backend/tests/test_simulation_*`，Knowledge 放入 `plugins/knowledge/tests/`，Craft 放入 `plugins/craft/tests/` 和 `backend/tests/test_craft_simulation_contract.py`，Connector v2 放入 `local-runtime/tests/Ai00.Connector.Tests/`。每个能力还必须进入强制 acceptance 的 success、invalid input、unauthenticated、resource denied、output contract、consumer contract 和 version pin 用例；这里列出的路径是计划，不是已通过证据。

### 11.3 固定所有权

| 对象或规则 | Owner |
|---|---|
| 仿真环境、绑定、姿态、截图计划、复合锚点和对账编排 | Simulation |
| BOP 结构、Load 属性解释、资源需求和草稿写入 | Craft |
| 数模号到知识资源的映射和反查 | Knowledge |
| 可复用不可变 model-reference identity/version | Digital Model |
| PLMXML、截图和 canonical manifest 的字节对象、hash、MIME 与 ArtifactRef | Base Platform（Artifact Capability）；OIS 仅为 Provider 存储实现 |
| VisMockup COM、窗口、ExportEx、选择和截图 | 本地 VisMockup Adapter Provider |

跨域只能调用明确的 Capability：Simulation 通过 Craft 读取 BOP/Load 投影和提交草稿变更，通过 Knowledge 反查资源，通过 Digital Model 读取模型版本，通过 Base Platform Artifact Capability 创建或读取 ArtifactRef。任何 owner 未批准的新契约都是对应阶段的 blocker，不能以跨域直表临时补偿。

### 11.4 交互确认

- 读取、搜索、高亮、显隐、拖放后的可撤销自动保存不弹额外确认框。
- `confirmation_required` 只由当前 Descriptor 和服务端策略决定。Gateway 为精确 operation、payload hash、resource selector 和有效期产生 challenge/receipt；Renderer 不能生成、伪造或缓存为其他操作复用 receipt。
- “同步数模”“保存版本”“开始截图”“删除环境”和“关闭/卸载模型”分别使用各自 Capability 的 confirmation 策略。按钮点击可以作为确认流程的起点，但只有服务端返回的精确 receipt 才能授权后续 dispatch。
- UI 可将 challenge 呈现在用户已经发起的同一动作流中，避免没有新增信息的第二个通用弹窗；只有契约允许且该交互满足服务端确认语义时才能无额外弹窗。
- 自动保存、读取、搜索、高亮和显隐可定义 `confirmation=none`，仍须经过 Gateway、权限、幂等、v2 plan 和审计。
- Provider 的 prepare/action/dispatch 两阶段不能因 UX 简化而折叠；Renderer 不能直接要求 ConnectorHost 执行。

### 11.5 当前治理状态

- `machine_passed`: `unverified`
- `human_approved`: `unverified`
- `runtime_verified`: `unverified`
- `advisory`: `true`

本设计不构成 Capability 批准或运行证据。每个新增/升版能力必须在实施前建立独立变更记录，绑定真实 capability_version_gid、Provider、Schema、消费者、迁移和测试。

## 12. 技术验证清单

实施数据结构前必须在真实 Windows x64 + Teamcenter + VisMockup 14.2 环境完成：

1. 枚举多个 VisMockup 窗口和文档，并可靠选中目标窗口。
2. 验证由 Teamcenter 在线启动的 VisMockup 附着路径；当前已知 `GetActiveObject` 不可用且 `Dispatch` 创建新实例，必须验证官方接口或受治理的进程内 Adapter，不能把进程探测等同于连接成功。
3. 对当前活动文档执行 `ExportEx`，验证生成的 PLMXML 可读取。
4. 在窗口内加入数模后再次导出，确认新增实例和层级进入文件。
5. 验证完整 BOM 行号、revision、`catiaOccurrenceName`、父路径、JT 引用和 16 值矩阵。
6. 验证同数模号多实例、资源移动、零件动态仿真未还原、删除后重载。
7. 通过稳定实例引用完成 VisMockup 选择、高亮、显隐和着色。
8. 验证本地 PLMXML 打开与 Teamcenter 在线打开所得字段的等价范围。
9. 验证 VisMockup 关闭、COM 断开、App 重启和多窗口切换后的恢复。
10. 从运行 BOP Schema/本体确认“是否 Load 零件”的权威属性编码和语义。

任何未通过项必须记录真实失败和环境信息，不能以 mock 测试替代 `runtime_verified`。

### 12.1 阶段 Gate

| Gate | 进入条件 | 阻断范围 |
|---|---|---|
| G0 Capability 权威上下文 | 从运行 Registry/Catalog Release/Snapshot 读取全部复用和候选能力，完成逐能力差距记录、owner 决定及真实 GID/Provider/consumer 绑定 | 未通过时只能做只读研究和规格修订，不能定义或实现新 Capability |
| G1 App/Connector v2 路径 | execution-plan/outcome v2、签名、generation fencing、lease/journal/reconciliation 已通过 Python/.NET golden vectors 和实际 App 调用证明；无 renderer/IPC/loopback 业务旁路 | 未通过时禁止任何新的 COM 业务操作进入产品路径 |
| G2 PLMXML 安全与规模 | XML 安全设置和所有资源上限已确定；21MB 样本及恶意/超限夹具均有可复现工程证据 | 未通过时禁止持久化解析服务和阶段 1 交付 |
| G3 文档/COM 实机 | Teamcenter 在线打开、多窗口、ExportEx、增量加入、实例字段、高亮和断线恢复均完成实机验证 | 未通过时禁止宣称在线文档支持或 `runtime_verified=true` |
| G4 Craft Load 契约 | Craft owner 确认权威属性编码、空值、工序/操作优先级、版本兼容和规范化输出 Capability | 未通过时禁止实现阶段 3 的 load binding 业务规则、阶段 4 的 Load 隐藏规则和阶段 5 的主环境写入 |
| G5 跨域 owner | Simulation、Craft、Knowledge、Digital Model、Base Platform Artifact owner 分别批准其契约；不存在跨域直表 | 未通过时阻断对应阶段写入 |
| G6 冻结可复现性 | canonical manifest、membership、CAS、幂等、算法版本和 Base Platform Artifact/Simulation saga 故障与对账测试通过 | 未通过时禁止截图或运行引用环境版本 |
| G-Craft-Collab 线体协作 | Craft owner 提供线体授权、线体 revision 或安全 rebase、完整 checkpoint、双线体原子移动、幂等、审计和恢复测试 | 未通过时使用整 BOP CAS，禁止宣称不同线体互不阻塞 |

这些 Gate 是工程进入条件，不代表 Capability 人工批准或生产运行验证；三类治理状态继续独立记录。

## 13. 分期交付

### 阶段 0：技术探针

完成窗口识别、在线文档 ExportEx、字段验证、实例高亮和异常恢复。该阶段不改变正式业务表。

### 阶段 1：文档与快照基础

实现 VM document/session/snapshot、OIS 原件、流式解析、当前投影和差异引擎。

### 阶段 2：仿真环境工作区

实现项目主环境、私人环境、共享池、项目关联、临时树、自动保存、手动版本、Fork、冻结和四列页面骨架。

其中 project_main、Share、Fork、版本保存和 Freeze 只有在各自前置 Gate 通过、精确 Capability 完成注册并成为允许的 stable release target 后才能开放业务入口；此前只允许数据/UI 骨架和隔离验证，不得由产品路由调用 experimental 或 not_registered 合同。

### 阶段 3：绑定与知识分类

实现拖放绑定、双向高亮、Knowledge 批量反查、待确认面板和 load/operate/resource_use 语义。

### 阶段 4：倒序截图

实现每工序一图、累计装配状态、越过 load 点隐藏、运行恢复、Artifact 上传及工序图片关联。

### 阶段 5：项目主环境协同

实现项目管理者全局编辑、工程师线体授权编辑、局部冲突恢复以及 BOP 与 Simulation 项目版本锚点。

### 阶段 6：升版与高级处理

实现 Teamcenter 升版比较、绑定迁移、姿态对比、环境 Fork/版本 Diff 以及后续基于不可变链接的高级 VisMockup COM 操作。

每个阶段必须能独立演示和回滚；阶段 0 结论会修正规格中的未验证字段和 Adapter 操作合同。

## 14. 验收主场景

1. 用户打开已有 BOP 和 Teamcenter 在线 VisMockup 文档，App 自动识别唯一窗口。
2. 用户同步当前文档，系统保存 PLMXML Artifact 和结构投影。
3. VM 树选中零件时 VisMockup 高亮；环境树选择绑定关系时高亮相同实例。
4. 同一工具数模加载两次得到两个 GID；移动其中一个只更新该实例姿态。
5. 零件动态仿真后未还原，下一快照识别为原实例已移动。
6. 用户将资源拖入关系组，系统通过 Knowledge 精确反查；歧义项在面板中解决。
7. 用户为零件建立 load 和后续 operate 关系，保存后重开环境仍保持。
8. 倒序截图每工序生成一图，零件只在越过 load 点后隐藏。
9. 项目管理者和工程师直接修改主环境的授权区域，BOP 与 Simulation 扩展保持同一项目版本锚点。
10. 同一线体并发修改返回 revision 冲突并局部恢复；G-Craft-Collab 未通过时不同线体也遵循整 BOP CAS，通过后才验证线体独立并发。
11. VisMockup/App 重启后重新连接文档，恢复实例映射和未完成环境。
12. 数模升版时旧版本保持可复现，新版本迁移必须经用户接受。
13. 大树读取始终分页或 lazy-load；超出 max_depth/max_nodes 时返回稳定错误，不拖死 Renderer 或 Gateway。
14. 恶意 XML、外部实体、XInclude、循环引用、断链和引用爆炸均被拒绝，解析期间没有网络或本地文件访问。
15. 同一自动保存请求重复提交只产生一次修订；过期 row_version 返回冲突并保持视点和本地未提交状态。
16. 截图成功后恢复 visibility、color、selection 和 camera；截图、上传、关联、取消或崩溃任一失败时停止后续步骤并执行可验证恢复。
17. Outcome 不确定时进入 `outcome_unknown`/`manual_review_required`，对账前不能重试或生成第二张截图。
18. Renderer、Electron IPC、named pipe、WebSocket 和 legacy bridge 扫描均不存在可绕过 Gateway/plan v2 的业务执行路径。
19. 私有环境不能被同租户其他普通用户读取；共享池环境可读、可用、可 Fork但仅 owner 可修改；跨租户访问始终拒绝。
20. 私人环境任意两个手动保存版本可以比较 BOP、绑定、VM 版本、BOM 行、`catiaOccurrenceName`、坐标和姿态。
21. 相同冻结环境版本在其绑定算法版本下重复生成截图计划，得到相同有序输入 hash。
22. private/shared owner 可逻辑删除环境，非 owner 被拒绝；project_main 删除按当前项目管理/删除权限执行，只删除 Simulation 扩展。
23. 删除在活动运行、legal hold 或 row_version 冲突时被阻止；重复调用幂等；源环境删除后既有 Fork 仍可读。
24. 删除不级联 Craft、Project、Digital Model、Knowledge 或 Artifact，不关闭 VisMockup，并释放项目活动主环境槽位。
25. 空白 ad_hoc、纯 VM ad_hoc 和带 Craft overlay 的 ad_hoc 都能保存及 Fork；仅存在跨域 source 时创建 environment anchor。
26. Archived active main 继续占唯一槽位；archive、delete 和新 run lease 在同一 guard 上串行化。
27. Craft 已成功但 Simulation 投影失败时进入 projection_pending，并通过受治理的 projection operation reconcile 收敛，不重放 Craft 写入。

## 15. 明确不做

- 不修改 Teamcenter 数模链接或源 BOM。
- 不在 AI00 中复制一套 VisMockup 图形引擎。
- 不把 PLMXML 内部 ID 当作长期业务身份。
- 不让 Simulation 直接查询 Craft、Knowledge 或 Digital Model 领域表。
- 不按拖放目标猜测资源类型。
- 不为每次轻微结构变化立即导出完整 PLMXML。
- 不在一个环境版本中混合多个 VM 窗口。
- 不把 BOP `data_stage` 用作 VM 快照版本轴。
- 不让 renderer 或 AppHost 生成持久业务 GID。
- 不在现有 Capability 上静默改变业务含义。
- 不使用 Git 软件存储仿真业务数据，也不提供 pull、push、merge 或 rebase。
- 不为私人和共享环境的每次自动保存生成完整 BOP/VM 历史。
- 不让旧 publish plan/map/outbox 接收新写入；它们只保留历史只读兼容。
- 第一阶段不物理 purge workspace、版本或 Artifact。
