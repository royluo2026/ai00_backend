# 数模仿真环境与 VisMockup 协同重构设计

**日期：** 2026-09-08
**状态：** 业务方向已确认，技术验证和 Capability 审批尚未完成
**适用客户端：** AI00 Windows x64 App
**相关既有设计：** `docs/superpowers/specs/2026-09-03-simulation-ai00-connector-governance-design.md`

**Repository、Fork 与版本细化：** `docs/superpowers/specs/2026-09-09-simulation-environment-collaboration-versioning-design.md`。该细化设计将项目管理聚合根固定为 Craft 拥有的 BOP Repository，并取代本文旧的“Simulation 项目主环境/共享池”模型；本文继续定义 VM、PLMXML、实例、姿态、截图和 Connector 边界。

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
AI00 BOP Repository 与 Simulation Context 中的引用、绑定、版本和姿态
               |
               v
VisMockup COM 选择 / 高亮 / 显隐 / 着色 / 截图
               |
               v
项目唯一 BOP Repository 的团队空间与版本基线
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

1. **项目与空间列**：项目 BOP Repository、团队空间、当前用户受管个人空间和私人仿真环境，并提供 Fork、版本、同步和提案状态。
2. **当前 BOP/仿真树**：显示团队、个人或私人空间的 BOP 结构、VPPS 蓝图和 Simulation overlay。
3. **VM 结构树**：展示当前 VisMockup 文档的结构化快照，并与 VisMockup 双向选择和高亮。
4. **右侧工作区**：一期保留，用于详情、差异、冲突、截图预览和未来高级仿真工具。

工具和状态入口集中在对应列头及统一状态区，不能散落在大空白画布中。

### 2.2 BOP Repository 与仿真覆盖层

- 一个 Project Management 权威项目（知识库页面入口）只有一个 Craft BOP Repository 和一个团队空间；每个用户在该项目最多一个受管个人空间。
- 团队和个人空间的 BOP 写入始终由 Craft Capability 执行；Simulation Context 只保存 VM、姿态、截图和映射扩展。
- 用户可创建不限数量的私人仿真环境；它们保存 BOP 引用和仿真覆盖层，不直接修改来源 BOP。
- 临时层级节点拥有 Simulation GID，不预占 Craft/BOP GID。
- 同一个 VM 实例可以在多个工序或操作中以关系投影出现，底层实例只有一份。
- 工具、设备、工装、套筒等需求关系可显示为虚拟关系组或关系行，不伪装成 BOP 结构节点。

### 2.3 团队与受管个人空间协作

- 一个项目最多一个 Repository/团队空间，一个用户最多一个受管个人空间；不提供通用 pull、push、merge、rebase 或日常分支。
- 项目管理者直接修改团队空间；工程师在受管个人空间设计，并可按授权直接处理团队线体；跨线体调整由项目管理者处理。
- 线体范围授权是目标；在 `G-Craft-Collab` 通过前仍使用整 BOP CAS。跨线体移动由项目管理者执行，并要求 Craft 提供完整 checkpoint 和双线体原子合同。
- 个人空间与团队空间使用 fork-base 和三方 Diff；正式变更提案只允许个人 → 团队，项目管理者按原子变更单元接受。

### 2.4 私人环境、Fork 与版本

- 私人环境仅 owner 可读写，数量不限；需要正式提交时先选择性导入受管个人空间。
- 团队空间、受管个人空间和私人环境均保留 Fork 能力。Fork 从精确不可变版本派生，不改变来源状态；不可变来源复用 Artifact/ref，不复制字节。
- 私人环境只保留当前状态、Fork 起点和用户主动保存的少量版本，不保存每次自动保存的完整 BOP/VM 历史。
- 同一环境任意两个手动保存版本必须支持完整结构化 Diff，包括 BOP、绑定、VM 版本、BOM 行、`catiaOccurrenceName`、坐标和姿态。
- 跨项目 Fork 不绑定年度或换代规则。团队 Fork 只创建空目标项目的 Repository；目标个人空间已存在时使用三方 Diff 导入，不覆盖。

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

## 9. BOP Repository 与 Simulation Context 边界

### 9.1 Repository 版本及扩展

团队空间和受管个人空间的结构、零件 load/operate 及资源需求由 Craft Capability 写入对应 mutable head。Simulation Context 引用精确 Repository、space、version、node/lineage，并保存 VM 实例、姿态、截图和 VisMockup 映射。

Repository 版本 manifest 由 Craft 拥有，并列出实际存在的跨域扩展 source refs。Simulation Context 生成自己的 immutable manifest Artifact；Craft 版本只保存其 GID/ref/hash，不复制 Simulation 主数据，也不宣称跨域数据库事务。

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
- 私人环境不回写团队空间，只能选择性导入受管个人空间；个人到团队使用受治理的变更提案，不提供通用 merge、pull 或 push。

## 10. 建议的数据模型

以下名称为实施设计候选，最终迁移前需核对现有表：

Repository、空间、Fork、VPPS 组和提案表以 2026-09-09 细化设计为准；下表只列 Simulation 自有对象。

| 表 | Owner | 作用 |
|---|---|---|
| `workmanship_sim_environment_workspaces` | simulation | 不限数量的私人仿真环境及 draft head |
| `workmanship_sim_environment_versions` | simulation | 私人环境手动版本、来源 Repository ref 和 manifest hash |
| `workmanship_sim_environment_nodes` | simulation | 私人环境临时节点与 BOP 引用投影 |
| `workmanship_sim_vm_documents` | simulation | VM 文档演进链 |
| `workmanship_sim_vm_sessions` | simulation | VisMockup 窗口连接会话 |
| `workmanship_sim_vm_snapshots` | simulation | 已接受快照与原始 ArtifactRef |
| `workmanship_sim_vm_occurrences` | simulation | 逻辑实例身份及 predecessor |
| `workmanship_sim_vm_occurrence_observations` | simulation | 每快照观察与分类状态 |
| `workmanship_sim_vm_poses` | simulation | 来源、阶段及运行姿态 |
| `workmanship_sim_environment_bindings` | simulation | 私人 overlay 中的 load、operate、resource_use 候选 |
| `simulation_contexts` | simulation | Repository/space/version/node/lineage 的 VM、姿态和截图扩展引用 |

现有环境 manifest、snapshot request、capture run 和 Connector 表继续复用。新增表不复制 Craft、Knowledge、Digital Model 或 Teamcenter 的可写主数据，仅保存带版本的引用和快照事实。

### 10.1 冻结版本与可复现性

可复现版本不能只保存一个 `manifest_hash`。每个 Simulation environment/context version 必须绑定不可变 canonical manifest Artifact 及 SHA-256，并在数据库中保留可查询 projection。团队/个人的 BOP Repository manifest 由 Craft 拥有；Simulation manifest 使用实际 source refs 引用它。Simulation canonical manifest 至少固定：

- 私人环境 overlay 节点或 Repository node/lineage 引用、顺序和来源类型；
- 每条绑定及 binding revision，包括 load、operate、resource_use；
- 来源装配姿态和被截图使用的阶段姿态；
- 可选 `source_bop_repository/version_gid`、BOP content hash 和 Load 属性投影版本；纯 VM 私人环境可以没有 Craft source；
- `vm_document_gid`、`vm_snapshot_gid`、原始 PLMXML ArtifactRef 和 snapshot hash；
- Knowledge、Craft、Digital Model 的不可变引用与版本；
- 身份匹配、坐标规范化、diff 和截图计划算法版本；
- capture profile、创建者、冻结时间和敏感级别。

所有历史 capture run、Diff 和可复现运行只能引用不可变 Repository/Simulation version，不能引用可变 head。

### 10.2 关系与并发约束

- 所有表必须包含 `tenant_gid`，用户对象包含 `owner_user_gid`，写入同时校验 tenant 和 owner selector。
- GID 唯一且永不复用。workspace 使用与 lifecycle/archive 正交的 `deleted_at/deleted_by/deletion_gid` tombstone；默认查询排除 deleted，审计查询可显式包含。
- draft head 使用 `row_version` 和 compare-and-swap；客户端提交 `expected_resource_version`，冲突后重新读取，禁止 last-write-wins。
- 自动保存每次编辑使用稳定 operation ID 和唯一幂等键；相同 key + 相同 payload 返回原结果，不同 payload 返回幂等冲突。
- version membership、binding revision、snapshot sequence、实例观察和环境锚点设置域内唯一键及同租户约束；跨域只保存 GID/ref/hash，不建立跨域外键或 cascade。
- 冻结采用跨资源 saga，不能把 Base Platform Artifact Capability 和 Simulation 数据库描述成一个事务：先通过受治理 Base Platform Artifact Capability 以 operation/idempotency 创建并 finalize 不可变 Artifact；再校验 ArtifactRef、hash、tenant 和访问范围；随后在 Simulation 单库事务中写入 version、membership、ArtifactRef/hash 和审计，提交后才令版本可见。OIS 只是 Artifact 字节存储的 Provider 实现，不是并列业务 owner。
- Simulation 数据库失败时将已完成 Artifact 标记为 orphan，交由 Base Platform Artifact Capability 的受控保留/回收流程处理；数据库成功但 Artifact 暂时不可读时将版本标记为 unavailable 并对账，禁止用重新序列化的不同 bytes 替换原 Artifact。
- archive/delete 与 capture/materialize/snapshot/comparison/reconciliation 的 run-lease 获取在同一 workspace guard/行锁上串行化；有活动 lease 返回 `active_run_exists`，archive/tombstone 落库后禁止新 lease。
- Project Management 权威项目（由 Knowledge UI 展示/选择）只允许一个有效 Craft Repository；Repository 只允许一个 team space，且每用户只允许一个 managed personal space。私人 Simulation workspace 不受数量限制。
- 使用新增迁移建立 Craft Repository/space/Fork/VPPS/proposal 数据；不得修改已执行的 `0011_simulation_workspaces.sql`。迁移按 2026-09-09 细化设计使用 maintenance write fence、in-flight drain、high-water 对账和零丢失验证，不做业务双写。0011 的 project-main/publish plan/map/outbox 停止新写入和新消费者，仅保留历史只读兼容。
- archive 可恢复且不改变 active/frozen；delete 只写 tombstone，不删除不可变版本、Fork base、Diff、审计或其他领域数据。第一阶段不实现物理 purge。

### 10.3 大树读取与算法版本

- VM 树、环境树、候选搜索和 diff 均使用 cursor 分页或有界 lazy-load，并强制 `max_depth`、`max_nodes`、`page_size` 和稳定排序。
- PLMXML 解析和大型 diff 在后台任务中执行；页面轮询/订阅状态，不能阻塞 Gateway 请求。
- 坐标规范化、实例匹配、diff 和截图计划算法各自有稳定 `algorithm_id` 与版本，并写入 snapshot、frozen manifest 和 run input hash。
- 历史版本按其原算法读取；升级算法必须显式重算为新快照或新环境版本，不能让相同历史版本得出不同结果。

## 11. Capability 治理结论

### 11.1 权威现状与复用差距

以下现状来自当前受检 Catalog/Descriptor/Provider 代码；实施时仍须从运行 Registry 和当前 Catalog Release 重新读取并绑定真实 version GID。表内用逗号、`@1/@2` 或 `*` 表示的内容只是多个现有能力的展示分组，不是可注册或可调用的 Capability ID；G0 inventory 必须把它们逐项展开为精确 ID、major、version GID 和 lifecycle。表内新 ID 和升版判断均为 advisory 候选。

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

项目 BOP Repository、团队/受管个人空间、复制深度、有序 VPPS 组、三方 Diff 和变更提案的 canonical Capability 清单，以 2026-09-09 细化设计第 13 节为准。旧的 `simulation.environment.project_main.*`、project-main environment anchor 和 publish plan/map/outbox 不得成为新消费者依赖。

本规格继续负责 Simulation/VM 边界：

| 原子业务效果 | 精确 Capability | 状态与边界 |
|---|---|---|
| 创建私人仿真环境 | `simulation.environment.workspace.create@1` | 现有 experimental 若变更 source/权限必须重建 definition hash、迁移消费者或按 owner 判断升 major |
| 查询/读取私人环境 | `simulation.environment.workspace.search@1`、`simulation.environment.workspace.get@1` | 逐项核对真实 Registry；默认只返回授权私人环境，不冒充 Craft Repository space |
| Fork 私人仿真环境 | `simulation.environment.workspace.fork.preview@1`、`simulation.environment.workspace.fork.apply@1` | not_registered 设计候选；目标固定 private，数量不限；Preview 固定 owner portability verdict/hash/expiry，Apply 复验后发布 |
| 保存私人环境版本 | `simulation.environment.workspace.version.save@1` | not_registered 设计候选；固定实际 source refs、VM snapshot 和 canonical manifest |
| 读取不可变私人版本 | `simulation.environment.workspace_version.get@1` | not_registered 设计候选；只读、有界，只返回已保存 immutable version |
| 为 Craft 导入签发来源 | `simulation.environment.workspace_version.export_for_import@1` | not_registered 设计候选；Simulation 校验 owner，并将 caller/tenant/精确 personal 或 repository target/consumer ID-major/source hash/expiry 写入签名 scope；不接受漂移 head或跨用途重放 |
| 读取/生成/调整私人 VPPS 组 | `simulation.environment.vpps_group.get@1`、`simulation.environment.vpps_group.initial.generate@1`、`simulation.environment.vpps_group.adjustment.create@1`、`simulation.environment.vpps_group.current.set@1` | 均为逐项 not_registered 候选；Simulation owner；Agent/Task Tool 必须使用 private-environment 固定 profile 与 owner delegation |
| 私人环境到受管个人空间导入 | 由 Craft owner 的 `craft.bop.managed_personal_space.import.preview@1` 与 `craft.bop.managed_personal_space.import.apply@1` 执行 | Simulation 只通过上述 export Capability 提供 opaque immutable source ref；Craft 经 Gateway 复验，不信任 Renderer manifest，不写 Simulation 表 |
| 接受 VM 快照差异 | `simulation.document_snapshot.change.accept@1` | 新合同需固定 document/snapshot、expected head、幂等和差异集合 |
| 接受数模升版绑定迁移 | `simulation.environment.binding_migration.accept@1` | 新合同需固定 workspace/version/candidate、CAS 和逐项决定 |
| 按数模号反查知识资源 | `knowledge.resource_model_mapping.reverse_resolve@1` | Knowledge owner 的 not_registered 候选；精确批量匹配，模糊搜索只用于人工候选 |

每个 ID 只表达一个原子效果。候选不是 experimental，只有真实 Registry 中已注册且 lifecycle=experimental 的版本才能使用该状态。所有输入 Schema 必须闭合，数组、树深、字符串和分页有上限；tenant/actor 来自可信 InvocationContext，Provider 根据资源 GID 解析权限。写操作使用 expected resource version、稳定 operation GID、幂等键和审计；跨 Craft/Simulation/Artifact 只能使用可对账 saga，不能宣称单事务。

现有 experimental Capability 若扩大到新的 selector、消费者、权限或副作用，必须逐项完成 Descriptor/Provider gap、重建 definition hash、重新审批和 consumer migration；不兼容时升 major。正式产品路由只能指向 stable release target。

### 11.3 固定所有权

| 对象或规则 | Owner |
|---|---|
| 私人仿真环境及其 VPPS 组、VM 实例、姿态、截图计划和 Simulation Context | Simulation |
| BOP Repository、团队/受管个人空间及其 VPPS 组、BOP 结构、提案、Load 和资源需求 | Craft |
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
| G4 Craft Load 契约 | Craft owner 确认权威属性编码、空值、工序/操作优先级、版本兼容和规范化输出 Capability | 未通过时禁止实现阶段 3 的 load binding 业务规则、阶段 4 的 Load 隐藏规则和阶段 5 的 Repository 写入 |
| G5 跨域 owner | Simulation、Craft、Knowledge、Digital Model、Base Platform Artifact owner 分别批准其契约；不存在跨域直表 | 未通过时阻断对应阶段写入 |
| G6 冻结可复现性 | canonical manifest、membership、CAS、幂等、算法版本和 Base Platform Artifact/Simulation saga 故障与对账测试通过 | 未通过时禁止截图或运行引用环境版本 |
| G-Craft-Collab 线体协作 | Craft owner 提供线体授权、线体 revision 或安全 rebase、完整 checkpoint、双线体原子移动、幂等、审计和恢复测试 | 未通过时使用整 BOP CAS，禁止宣称不同线体互不阻塞 |

这些 Gate 是工程进入条件，不代表 Capability 人工批准或生产运行验证；三类治理状态继续独立记录。

## 13. 分期交付

### 阶段 0：技术探针

完成窗口识别、在线文档 ExportEx、字段验证、实例高亮和异常恢复。该阶段不改变正式业务表。

### 阶段 1：文档与快照基础

实现 VM document/session/snapshot、OIS 原件、流式解析、当前投影和差异引擎。

### 阶段 2：Repository 与空间骨架

实现项目唯一 BOP Repository、团队空间、每用户一个受管个人空间、不限私人环境、项目关联、自动保存和四列页面骨架。

其中 Repository/space 创建、Fork、版本保存和 Freeze 只有在各自前置 Gate 通过、精确 Capability 完成注册并成为 stable release target 后才能开放业务入口；此前只允许数据/UI 骨架和隔离验证。

### 阶段 3：绑定与知识分类

实现拖放绑定、双向高亮、Knowledge 批量反查、待确认面板和 load/operate/resource_use 语义。

### 阶段 4：倒序截图

实现每工序一图、累计装配状态、越过 load 点隐藏、运行恢复、Artifact 上传及工序图片关联。

### 阶段 5：BOP Repository Fork 与协同

实现复制深度、有序 VPPS 组、自动生成初版、用户/Agent adjustment、个人三方同步、私人选择性导入和个人到团队变更提案。

### 阶段 6：升版与高级处理

实现 Teamcenter 升版比较、绑定迁移、姿态对比、Repository/空间/私人环境 Fork 与版本 Diff，以及后续基于不可变链接的高级 VisMockup COM 操作。

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
9. 一个 Project Management 权威项目只有一个 BOP Repository/团队空间，每用户最多一个受管个人空间，但私人仿真环境数量不限。
10. 同一线体并发修改返回 revision 冲突并局部恢复；G-Craft-Collab 未通过时不同线体也遵循整 BOP CAS，通过后才验证线体独立并发。
11. VisMockup/App 重启后重新连接文档，恢复实例映射和未完成环境。
12. 数模升版时旧版本保持可复现，新版本迁移必须经用户接受。
13. 大树读取始终分页或 lazy-load；超出 max_depth/max_nodes 时返回稳定错误，不拖死 Renderer 或 Gateway。
14. 恶意 XML、外部实体、XInclude、循环引用、断链和引用爆炸均被拒绝，解析期间没有网络或本地文件访问。
15. 同一自动保存请求重复提交只产生一次修订；过期 row_version 返回冲突并保持视点和本地未提交状态。
16. 截图成功后恢复 visibility、color、selection 和 camera；截图、上传、关联、取消或崩溃任一失败时停止后续步骤并执行可验证恢复。
17. Outcome 不确定时进入 `outcome_unknown`/`manual_review_required`，对账前不能重试或生成第二张截图。
18. Renderer、Electron IPC、named pipe、WebSocket 和 legacy bridge 扫描均不存在可绕过 Gateway/plan v2 的业务执行路径。
19. 私人环境不能被其他普通用户读取，也不能直接提交团队提案；只能选择性导入当前用户的受管个人空间。
20. 私人环境任意两个手动保存版本可以比较 BOP、绑定、VM 版本、BOM 行、`catiaOccurrenceName`、坐标和姿态。
21. 相同冻结环境版本在其绑定算法版本下重复生成截图计划，得到相同有序输入 hash。
22. 团队 Fork、受管个人空间 Fork 和私人环境 Fork 遵守各自唯一约束，目标已有数据时不覆盖。
23. 五种复制深度生成正确的正式节点边界；深度以下只显示有序 reference VPPS 蓝图，不进入正式 BOP 查询。
24. 自动匹配生成 `generated_initial`，用户或 Agent 生成 `adjustment`；reference 永不覆盖，团队 current pointer 只由项目管理者接受后推进。
25. 个人空间以团队 base、个人 head、团队 head 做三方 Diff，并支持依赖闭合的部分变更提案。
26. 私人环境删除不影响 Craft Repository；Repository/空间删除只写 tombstone，不级联 Project、Knowledge、Digital Model、Artifact、Simulation Context、任务或问题，也不关闭 VisMockup。
27. Craft 已成功但跨域投影失败时以 Craft outcome 为权威并受治理对账，不重放 Craft 写入。

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
- 不为私人环境的每次自动保存生成完整 BOP/VM 历史。
- 不让旧 publish plan/map/outbox 接收新写入；它们只保留历史只读兼容。
- 第一阶段不物理 purge workspace、版本或 Artifact。
