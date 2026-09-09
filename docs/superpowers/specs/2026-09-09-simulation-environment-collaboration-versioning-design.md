# 仿真环境协作、Fork 与版本差异设计

**日期：** 2026-09-09
**状态：** 业务设计已确认，等待规格复核
**基础设计：** `docs/superpowers/specs/2026-09-08-digital-simulation-environment-redesign.md`

## 1. 设计结论

仿真评审分为节点评审和零散评审。节点评审围绕一个主项目的在线活动 BOP 协作，不引入 pull、push、merge、rebase 或工程师日常分支。零散评审使用轻量的私人或共享仿真环境，可以从空环境、项目活动环境、项目基线或共享环境 Fork。

Git 只作为概念参考：保留 Fork 和结构化 Diff。系统仍使用 MySQL 事务、雪花 GID、不可变 Artifact、Capability Gateway 和领域 Provider，不使用 Git 软件保存业务数据，也不实现通用 Git。

## 2. 核心对象

### 2.1 节点评审主环境

一个主项目最多对应一个活动主环境。主环境直接引用项目当前在线活动 BOP，并把 VM 实例、姿态、截图和 VisMockup 映射作为同一业务版本的 Simulation 扩展。

- 主项目必填且唯一；参考项目可以多选。
- 项目管理者可以直接修改全部主环境内容。
- 工程师直接修改获授权线体内的 BOP 节点、关系和 Simulation 扩展。
- 不同线体独立授权和保存；跨线体移动由项目管理者执行。
- BOP 结构和关系仍由 Craft 拥有；VM、姿态和截图仍由 Simulation 拥有。两域通过精确 BOP version/revision/hash 和环境版本绑定，对用户表现为同一项目版本。
- 主环境不使用 Fork/合并完成普通协作，不存在 pull 或 push。

### 2.2 零散评审环境

零散评审环境是 owner 管理的轻量工作区：

- 可以从空环境创建，也可以从项目活动环境、项目基线、私人环境的已保存版本或共享环境 Fork。
- `private` 仅 owner 可见、可用、可改。
- `shared` 对同租户用户可见、可用、可 Fork，但仍只有 owner 可修改。
- 共享环境进入共享池，不设置维护者、审批人或合并流程，只作为参考方案。
- 私人和共享环境不会自动修改正式项目 BOP，也不提供 merge/pull/push。

### 2.3 环境、工作状态和版本

仿真环境是数据库中的可变工作状态，不是单独文档。用户主动“保存版本”时生成不可变 canonical manifest Artifact。

环境状态为：

- `active`：可编辑工作状态；
- `baseline`：当前内容已建立基线，后续编辑继续形成新的工作状态；
- `frozen`：不可逆只读，任何元数据、节点、绑定和姿态写入均由 Provider 拒绝；
- `archived`：退出日常列表，可由 owner 恢复为活动状态，冻结环境归档后仍不可修改内容。

私人和共享环境不记录每次自动保存的完整历史。它们只保留当前状态、Fork 起点、用户主动保存的版本以及必要的审计/恢复信息。主项目环境额外保留项目基线、冻结版本、线体 checkpoint 和操作历史。

## 3. 新建与编辑字段

新建弹窗和环境详情包含：

| 字段 | 规则 |
|---|---|
| 环境名称 | 必填，可由有权用户编辑 |
| 评审类型 | `node_review` 或 `ad_hoc_review` |
| 主项目 | 节点评审必填且只能一个；零散评审可空 |
| 参考项目 | 可多选；通过 `base.project.search@1` 按名称或编码模糊搜索 |
| 环境版本标签 | 用户填写；不替代内部 `version_gid` |
| 状态 | 活动、基线、冻结、归档 |
| 可见范围 | 私人或共享；项目主环境按项目可见规则读取 |
| 更新时间 | 数据库自动生成，客户端只读 |

项目候选只通过 Project Management owner 的 `base.project.search@1` 获取。Simulation 只保存项目 GID、显示名称快照、主项目/参考项目角色和排序，不直接查询其他领域表。

## 4. 在线主环境的版本引用

主环境允许引用和修改活动 BOP，因此不能只保存一个会漂移的“当前 BOP”引用，也不能要求工程师只能从基线开始。

系统保存：

- 活动引用：`bop_version_gid` 和当前 `revision`，用于在线编辑；
- 观察锚点：每次成功写入后的 `revision` 和 `content_hash`；
- 线体恢复点：首次修改、删除和跨线体移动前由 Craft 保存线体 checkpoint；
- 项目版本锚点：建立基线、冻结或保存项目版本时，固定完整 BOP 快照及 Simulation manifest。

页面发现 BOP revision 变化时自动读取受影响线体并更新局部视图，不让用户执行 pull/rebase。相同线体出现 revision 冲突时保留本地视点和未提交意图，重新读取该线体后由用户重试。不同线体的修改互不阻塞。

## 5. Fork

Fork 是独立的原子业务效果：从一个当前可读的精确来源状态创建新的 owner 工作区。

1. 来源是已保存版本时直接使用该不可变版本。
2. 来源是活动环境时，系统在事务一致的读取点生成不可变 `fork-base` 快照，但不改变来源环境状态。
3. Fork 使用最近一次已持久化的 VM 快照；不会读取其他用户工作站上未同步的 VisMockup 临时状态。
4. 新工作区生成新的 workspace、version、node 和 binding GID，并保留 `forked_from_workspace_gid`、`forked_from_version_gid` 和实体 `lineage_gid`。
5. 用户在 Fork 时选择新环境为私人或共享。
6. 来源后续变化不会自动进入 Fork；Fork 也不会回写来源。

## 6. 手动版本与 Diff

用户每次主动“保存版本”都固定以下内容：

- 环境元数据、主项目和参考项目；
- BOP version/revision/content hash、结构节点、顺序和关系；
- load、operate 和资源需求绑定；
- `vm_document_gid`、`vm_snapshot_gid` 和 PLMXML ArtifactRef；
- VM occurrence GID、数模版本、BOM 行、`catiaOccurrenceName` 和父路径；
- 原始坐标、规范化坐标、姿态和表示位置；
- 身份匹配、坐标规范化和 Diff 算法版本。

支持三种比较：

1. 当前环境与最近一次已保存版本或基线；
2. Fork 当前状态与 `fork-base`；
3. 同一私人、共享或项目环境的任意两个已保存版本。

Diff 输出至少包括：元数据变化、项目变化、BOP 节点新增/删除/改名/移动/排序、绑定新增/删除/目标或角色变化、VM 实例新增/删除、数模升版、BOM 行变化、`catiaOccurrenceName` 变化、父路径变化、坐标变化和姿态变化。

实例匹配遵守既定规则：零件 BOM 行和实例血缘一致时，坐标变化标记为移动/姿态变化，不生成新 occurrence GID；版本变化建立 predecessor 血缘。工具、设备、工装和套筒允许相同数模号存在多个实例，使用实例路径、`catiaOccurrenceName` 和坐标区分。

大型 Diff 使用后台任务和分页结果，小型摘要可以同步读取。结果绑定左右版本 GID、输入 hash 和算法版本，历史结果可复现。

## 7. 数据持久化

在现有 Simulation workspace 表上兼容迁移：

| 表 | 持久化内容 |
|---|---|
| `workmanship_sim_workspaces` | 名称、评审类型、版本标签、状态、可见范围、owner、主项目、Fork 来源、更新时间 |
| `workmanship_sim_workspace_projects` | 多项目关联、主/参考角色、项目名称快照和排序 |
| `workmanship_sim_workspace_versions` | 手动版本、父版本、fork-base、BOP 锚点、VM snapshot、manifest/hash 和状态 |
| `workmanship_sim_workspace_nodes` | 当前节点投影、来源 BOP GID 和稳定 lineage GID |
| `workmanship_sim_workspace_bindings` | 当前绑定投影和稳定 lineage GID |
| `workmanship_sim_environment_version_comparisons` | Diff 任务、左右版本、算法、状态、摘要和结果 ArtifactRef |

主项目和参考项目的权威数据仍归 Project Management；BOP 权威数据仍归 Craft；Simulation 表不复制这些领域的可写主数据。

## 8. 权限

| 对象 | 读取/使用 | 修改 |
|---|---|---|
| 私人零散环境 | owner | owner |
| 共享池环境 | 同租户用户 | owner |
| 项目主环境 | 有项目读取权限的用户 | 项目管理者全局；工程师仅获授权线体 |
| 冻结环境/版本 | 按环境可见范围 | 无人可修改内容 |

所有权限由 Gateway/Provider 根据可信 InvocationContext、workspace、项目和线体授权解析。Renderer 不能提交 owner、tenant 或“已经授权”的结论。

## 9. 内置 Agent 版本管家

### 9.1 现有能力与缺口

内置 Agent 已经能够从一个固定 Catalog Release 中，把 `exposure.agent=true` 的 Capability 按精确 ID、主版本和闭合 Schema 自动投影成工具，并通过 DomainCapabilityClient/Gateway 执行。旧的手写工具执行入口已经退役，不能把新版本逻辑加入 legacy `tool_registry.py`。现有六个系统工程 Skill 不包含版本管理；`docs/governance/task_tool_registry.json` 当前也没有通用版本管理 Task Tool。

BOP、PBOM 和部分其他领域已经有各自的版本、快照或比较 Capability，但没有统一的 Agent 编排工具。Simulation 的保存版本、Fork 和完整环境 Diff 仍是 experimental 候选。

### 9.2 通用 Task Tool

新增 `task.version_steward.evaluate`，作为可跨域复用的 Task Tool。它只编排受信任 Catalog 中明确登记的版本操作，不成为业务数据 owner，也不直接读取领域表。

输入至少包含：

- `resource_ref`：待管理资源的规范引用；
- `policy_gid`：owner 已启用的版本策略；
- `trigger`：idle、before_fork、material_change、scheduled 或 user_requested；
- `expected_resource_version` 和幂等键；
- 固定 Catalog Release、Agent run 和 correlation identity，由可信运行时提供而非 Renderer payload 提供。

每种资源类型通过受治理的静态 profile 声明 search/get/diff/snapshot Capability 及字段映射。Task Tool 只能使用 profile 中的精确 Capability ID 和主版本，禁止按命名规律猜测、访问未发布能力或直接调用 Provider 内部函数。

Task Tool 的确定性步骤为：读取策略和当前资源版本、读取最近保存版本、计算或读取结构化 Diff、校验变化阈值/时间窗口/数量上限/content hash、创建版本或返回稳定的跳过原因、保存运行和结果引用。相同内容 hash 不重复创建版本。

### 9.3 薄 Skill

新增系统 Skill“版本管理”，只提供选择和解释规则：

- 何时调用版本管家；
- 如何解释不同领域的结构化 Diff；
- 如何生成版本标签、变更摘要和风险提示；
- 如何推荐共享池的参考版本；
- 如何回答版本间变化和来源血缘问题。

Skill 不包含数据库操作、权限判断、冻结规则或 Capability 实现。所有执行仍通过 Task Tool 和 Gateway。

### 9.4 共享池自动版本策略

共享环境默认不强制开启版本管家，由 owner 在每个环境上主动启用并设置策略。策略至少包括空闲合并窗口、最小有效变化、每小时/每日上限、普通版本保留期和长期保留条件。

共享环境版本分为：

1. owner 持续编辑的当前状态；
2. Agent 按策略创建的普通自动版本；
3. owner 手动命名、标记推荐、建立基线或冻结的长期版本。

被 Fork、标记推荐、建立基线或冻结的版本不得由保留策略自动清理。Agent 可以生成标签、摘要、异常提示和推荐，但不能自行冻结、发布、删除受保护版本、修改可见范围、改变 owner 或完成业务审批。普通版本创建必须记录 Agent run GID、触发原因、策略版本、输入 Diff hash、Catalog Release 和实际 Capability outcome。

私人环境仍只保存用户主动版本；项目主环境仍由项目管理者建立基线和冻结。通用 Task Tool 可被其他域复用，但每个域必须先有稳定、已发布且允许 Agent exposure 的领域 Capability profile。

## 10. Capability 边界

候选能力保持 experimental，按此前决定暂不请求单项人工审批：

- `simulation.environment.workspace.create@1`
- `simulation.environment.workspace.metadata.update@1`
- `simulation.environment.workspace.search/get@1`
- `simulation.environment.workspace.version.save@1`
- `simulation.environment.workspace.fork@1`
- `simulation.environment.version.search/get@1`
- `simulation.environment.version_compare.start/get@1`
- `simulation.environment.version.freeze@1`

项目候选复用 `base.project.search@1`。主环境的 BOP 写入、线体 checkpoint、版本快照和权限由 Craft owner Capability 提供；Simulation 不直接写 Craft 表。Fork、保存版本和冻结使用幂等键、CAS、不可变 Artifact 和可对账 saga。

## 11. 验收场景

1. 节点评审必须选择一个主项目，可选择多个参考项目；同一主项目只能有一个活动主环境。
2. 项目管理者直接编辑主环境全部线体，工程师只能编辑已授权线体。
3. 两名工程师修改不同线体时互不覆盖；跨线体移动只允许项目管理者执行。
4. 私人环境只有 owner 可见；共享环境同租户可见、可用、可 Fork，但非 owner 不能修改。
5. 活动环境 Fork 自动生成精确 fork-base，且不改变来源状态。
6. 私人环境连续自动保存不生成完整历史；两次手动保存生成两个不可变版本。
7. 任意两个手动版本可比较 BOP、绑定、VM 版本、BOM 行、`catiaOccurrenceName`、坐标和姿态。
8. 冻结后所有写入在 Provider 层被拒绝；归档环境可以按权限恢复。
9. 项目、环境字段和更新时间重启后仍从数据库正确恢复。
10. 页面按活动、基线、冻结和归档分组，局部冲突不重置视点或刷新整个页面。
11. owner 可为单个共享环境启用版本策略；相同内容不会产生重复自动版本，达到频率上限后返回可解释的跳过原因。
12. Agent 自动版本记录策略、Diff hash、Catalog Release、Agent run 和 Capability outcome；Agent 不能冻结或删除受保护版本。
13. 同一 Task Tool 通过显式 profile 编排不同领域版本 Capability，不根据名称猜测，也不直连领域表。

## 12. 明确不做

- 不使用 Git 软件保存仿真业务数据。
- 不提供 pull、push、merge、rebase 或 Pull Request。
- 不要求工程师为日常线体工作创建分支。
- 不为私人或共享环境的每次自动保存生成完整 BOP/VM 历史。
- 不让共享池环境自动影响项目主环境。
- 不读取其他用户工作站中尚未同步的 VisMockup 状态。
- 不改变 Teamcenter 数模链接本身。
- 不在退役的 legacy Agent 手写工具执行器中增加版本逻辑。
- 不让 Agent 的自然语言判断替代确定性版本策略、权限或领域 Capability。
