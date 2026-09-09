# 项目 BOP Repository、Fork、VPPS 与变更提案设计

**日期：** 2026-09-09
**状态：** 业务设计已确认，等待架构复审
**基础设计：** `docs/superpowers/specs/2026-09-08-digital-simulation-environment-redesign.md`

## 1. 设计结论

项目级管理对象由“仿真环境仓库”调整为 **BOP Repository**。一个知识库项目只维护一个 BOP Repository；BOP 的线体、工位、岗位、工序、操作及其零件和资源绑定是项目协作主结构，Simulation Context、任务、问题和后续领域对象都引用该结构。

Repository 内固定一个团队空间和每用户一个受管个人空间。用户还可以创建不限数量的私人仿真环境。正式变更提案只在受管个人空间与团队空间之间流转；私人环境先选择性导入个人空间，不能直接修改或提交团队空间。

Git 只作为 Fork、三方 Diff 和变更提案的概念参考。系统继续使用 OceanBase/MySQL、雪花 GID、不可变 Artifact、Capability Gateway 和领域 Provider，不使用 Git 软件，不实现通用分支、merge、pull、push、rebase 或版本 DAG。

## 2. 项目、Repository 与三类空间

### 2.1 项目身份

项目使用用户在知识库页面看到的现有项目定义；其权威查询继续由 Project Management 的 `base.project.search@1` 提供 `project_gid`、名称、年份、车型、基地等字段。Craft 和 Simulation 不复制这些字段为可写主数据。Fork 不根据项目名称、年份或车型推断派生关系，用户必须明确选择来源项目、来源不可变版本和目标项目。

### 2.2 BOP Repository

- 一个有效 `project_gid` 最多对应一个未删除 BOP Repository。
- Repository 由 Craft 拥有，承载 BOP 主结构、正式绑定、版本、基线、Fork 血缘和提案结果。
- 一个 Repository 固定一个团队空间；团队空间是项目正式协作主干。
- 项目管理者可修改全部区域，工程师按线体授权修改。
- 在 `G-Craft-Collab` 通过前仍使用整 BOP CAS，不宣称不同线体永不阻塞。
- 稳定、基线、冻结和 released 版本不可写，所有在线编辑作用于当前 mutable head。

### 2.3 受管个人空间

- `(repository_gid, owner_user_gid)` 最多一个未删除的受管个人空间。
- 它是用户对该项目进行正式设计、三方同步和提交变更提案的唯一个人入口。
- 保存 fork-base、当前 head、必要的手动检查点、提案引用和审计，不为每次自动保存生成完整历史。
- 没有本地修改时可快进到团队最新版本；存在修改时以 fork-base、个人 head、团队 head 做三方 Diff。
- 目标项目已有该用户个人空间时，跨项目 Fork 不覆盖，改为选择性 Diff 导入。

### 2.4 私人仿真环境

- 每个用户可按项目创建任意数量，也可以不绑定项目。
- 可以从空白、团队版本、自己的个人版本或其他可读不可变版本 Fork。
- 用于方案探索、布局比较和零散评审，只保留当前状态、fork-base、用户主动保存的少量版本和必要审计。
- 可以在不同项目间自由 Fork，但不能直接提交团队变更提案。
- 需要进入正式协作时，先通过受治理的选择性导入写入该项目的受管个人空间。

## 3. 领域所有权

| 对象 | 权威 Owner |
|---|---|
| 项目身份、名称、年份、车型、基地 | Project Management；知识库页面只是现有用户入口 |
| 单个 VPPS 身份和基础信息 | Knowledge |
| BOP Repository、团队空间、受管个人空间 | Craft |
| BOP 节点、顺序、属性、Load/Operate 和正式资源绑定 | Craft |
| 团队/个人空间的有序 VPPS 组及版本 | Craft |
| 私人仿真环境及其 VPPS 调整版本 | Simulation |
| VM 实例、PLMXML、姿态、截图、VisMockup 映射 | Simulation |
| 任务、问题 | 各自业务域，通过 project/repository/node/lineage 引用 |
| manifest、Diff 和截图的不可变字节 | Base Platform Artifact；OIS 仅为存储实现 |

第一阶段不建设全局可复用 VPPS 组模板。单个 VPPS 仍是 Knowledge 的全局身份；有序组合先属于具体 Repository Fork 或私人环境。多个项目反复验证后，另行设计提升为知识模板的治理流程。

## 4. BOP 层级与复制深度

规范层级为：线体 → 工位 → 岗位 → 工序 → 操作 → 绑定。实现需映射现有 Craft node type，例如 `line_process`、`station_process`、`operator_process`、`process`、`operation`，不得由 Renderer 自行猜测。

Fork 必须选择一个复制深度：

| 复制深度 | 生成目标项目正式 BOP 实例 | 深度以下处理 |
|---|---|---|
| 全部复制 | 全部节点、允许复制的属性和绑定 | 无蓝图余项 |
| 复制到操作 | 线体至操作 | 零件、工具、设备、工装、套筒等实例和项目数据清空，只保留有序参考 VPPS |
| 复制到工序 | 线体至工序 | 操作及以下不生成正式实例，只保留有序参考 VPPS |
| 复制到岗位 | 线体至岗位 | 工序及以下不生成正式实例，只保留有序参考 VPPS |
| 复制到工位 | 线体至工位 | 岗位及以下不生成正式实例，只保留有序参考 VPPS |

复制深度是 Fork plan 的必填枚举。深度以内的目标节点生成新 `bop_node_gid`；深度以下的源实例不进入正式 BOP 表，也不被正式查询、统计或资源关系识别。

## 5. 实例身份、血缘与 VPPS 类型

VPPS 表达“该位置承担什么工艺职责”，类似跨项目稳定的业务类型；BOP node 表达该职责在具体项目中的实例。两者不能混用。

| 标识 | 语义 |
|---|---|
| `vpps_gid` | Knowledge 拥有的稳定 VPPS 身份 |
| `bop_node_gid` | 当前项目中的具体 BOP 实例 |
| `lineage_gid` | 具体实例跨版本的逻辑延续 |
| `derived_from_node_gid` | 本次 Fork 的直接来源实例 |
| `source_repository_gid/version_gid` | Fork 的 Repository 级来源 |

完整复制的目标实例继承来源 lineage 并记录 direct derivation。仅保留 VPPS 的蓝图成员不预先生成 BOP node GID；后续实例化时生成新 GID，并保留它来自哪个蓝图成员。相同 VPPS 不等于同一实例。

## 6. 有序 VPPS 组

### 6.1 结构

一个蓝图节点或已实例化边界节点只能绑定一个 VPPS 组；reference/current 是该组的版本指针，不是多个并列组。一个组包含多个有层级、同层有顺序的成员。相同 `vpps_gid` 可以在同一组出现多次，由不同 member GID 区分。

```text
vpps_group
└─ vpps_group_version
   └─ ordered_member
      ├─ member_gid
      ├─ vpps_gid
      ├─ parent_member_gid
      ├─ node_level
      ├─ order_key
      ├─ source_bop_node_gid
      └─ source_node_lineage_gid
```

顺序只在同一 `parent_member_gid` 下比较，整树顺序由父子结构和 sibling `order_key` 得出。不使用全局连续序号，避免插入导致整组重排。组版本固定后不可修改，成员、层级或顺序变化都生成新 `vpps_group_version_gid`。

### 6.2 版本生命周期

操作者类型与版本生命周期分离：

| `version_kind` | 含义 |
|---|---|
| `reference` | Fork 保存的来源 VPPS 结构，永不覆盖 |
| `generated_initial` | 自动匹配生成的目标初版 |
| `adjustment` | 用户、Agent 或确定性自动化产生的后续调整版 |

每个版本保存 `parent_version_gid`、actor GID/type、原因、evidence refs、算法或 Agent 版本、Catalog Release 和 content hash。组保存：

- `reference_group_version_gid`：不可覆盖的来源参考；
- `current_group_version_gid`：当前采用的初版或调整版。

原设计中的 proposed/assigned 双字段取消。是否生效由 current pointer 表达，不由“是不是人工操作”决定。

### 6.3 自动生成与调整

- Fork 核心完成后异步生成 `generated_initial`，失败不破坏 Repository、空间或 reference group。
- 自动匹配只能建议成员对应关系并继承参考层级和顺序，不能静默重排。
- 用户、Agent 和自动化调整均追加 `adjustment` 版本，不原地覆盖。
- 团队空间中 Agent 只能产生候选 adjustment，项目管理者接受后才推进 current pointer。
- 受管个人空间和私人环境可以由 owner 明确授权 Agent 自动推进 current pointer。
- current group 与 reference group 不同时是正常项目差异，Diff 标为 VPPS 重新归类、移动或重排，并保留两边。

## 7. Fork 类型与规则

### 7.1 团队空间 Fork

- 从任意可读项目团队空间的精确不可变版本创建目标项目的唯一 Repository 和团队空间。
- 目标项目已有未删除 Repository 时返回 `target_repository_exists`，不得覆盖。
- 发起人必须有来源版本读取权和目标项目 Repository 创建/管理权。
- 项目派生原因可以是换代、年款、车型、基地或其他业务原因，系统不硬编码类型。

### 7.2 受管个人空间 Fork

- 用户只能创建自己的目标个人空间，不能复制他人的个人空间。
- 目标个人空间不存在时，从来源的精确不可变版本和个人 Diff 创建。
- 目标个人空间已存在时返回 `managed_personal_space_exists`，UI 转入三方 Diff 和选择性导入，不覆盖。
- 当来源和目标团队空间具有共同 base 时，只迁移个人 Diff；没有共同 base 时按 lineage、VPPS 和 source refs 做三方映射。
- 用户可在一次向导中同时选择“Fork 目标团队空间”和“迁移自己的个人空间”；后端仍产生两个独立、可对账、幂等的业务 outcome。团队 Fork 成功而个人迁移失败时保留团队 Repository，并允许个人步骤重试。

### 7.3 私人仿真环境 Fork

- 数量不限，目标容器默认 private。
- 私人环境 Fork 后仍为 private；第一阶段不把它转换为团队或公共空间。
- 来源删除后，既有 Fork 继续通过自身 immutable fork-base 和 ArtifactRef 使用。

### 7.4 Fork 准备—发布流程

1. 固定并授权来源不可变版本及 source manifest。
2. 校验目标项目、目标空间唯一约束和复制深度。
3. 创建幂等 fork run 和 plan。
4. 深度以内生成目标实例、GID、lineage 与 derivation。
5. 深度以下生成 immutable、有序 reference VPPS group。
6. 校验节点数、引用、hash 和跨域权限后，将核心 Fork 置为 `ready`。
7. 异步生成 `generated_initial` 版本；状态独立为 pending/ready/failed，可幂等重试。

Fork 失败不得发布部分 Repository。相同幂等键和 payload 返回原 outcome；不同 payload 返回幂等冲突。自动匹配失败不回滚已经 ready 的核心 Fork。

## 8. Diff、同步与选择性导入

### 8.1 两层 Diff

正式 BOP Diff 覆盖节点新增/删除/移动/排序、属性、Load/Operate、零件和资源绑定，以及任务、问题、Simulation Context 引用。VPPS Diff 覆盖 reference、generated_initial、任意 adjustment 和 current BOP 之间的成员新增/删除/替换、跨父移动、同级重排、实例化状态及 provenance。

Diff 固定左右 version GID、manifest hash、算法版本和输入 source refs。节点匹配先用 lineage 和 direct derivation，再使用 VPPS、结构路径及明确规则；不能只按名称匹配。

### 8.2 个人空间三方同步

```text
Base   = 个人空间创建或上次同步时的团队版本
Ours   = 个人空间当前 head
Theirs = 团队空间当前 head
```

- 仅个人修改：形成提案候选。
- 仅团队修改：自动同步。
- 双方不冲突：自动组合并记录算法与结果 hash。
- 同一节点、绑定或 VPPS member 被双方改变：产生显式冲突。
- 来源删除或 lineage 无法定位：进入重新映射，不静默猜测。

没有个人修改时允许快进。存在修改时必须完成三方 Diff，保留用户视点和未提交意图。

### 8.3 私人环境导入

私人环境到受管个人空间只允许选择原子变更单元导入。导入时以私人 fork-base、私人 head 和个人 head 做三方比较；冲突在个人空间解决。导入不创建团队提案，也不绕过 Craft Provider。

## 9. 变更提案

提案唯一流向为受管个人空间 → 同 Repository 团队空间。状态为 `draft/submitted/reviewing/accepted/partially_accepted/rejected/superseded`。

提案固定个人 version、团队 base version、Diff hash 和原子变更单元。提交后个人后续修改不自动进入该提案。

原子变更单元至少包括：节点新增、移动或删除；单个属性变更；单条绑定变化；一个 VPPS 组 adjustment；一段 VPPS 子树实例化。用户可逐项选择，Provider 自动补齐必要父节点、依赖关系和引用闭包；缺少依赖时返回明确诊断，不能生成不完整 BOP。

项目管理者接受时重新比较当前团队 head。无冲突单元通过 Craft Capability 应用；冲突单元留在提案中。每个已应用单元记录 Craft operation/audit ref 和确定 outcome，不得重复应用。Agent 可解释和推荐，不能代表项目管理者接受团队提案。

## 10. Simulation Context、任务与问题

仿真环境不再作为项目 Repository。团队或个人空间可挂接一个或多个版本化 Simulation Context，保存 VM snapshot、occurrence、pose、截图和 VisMockup session 映射，并引用精确 repository/space/version/node/lineage。

任务、问题和其他未来对象由各自 owner 保存，只引用 `project_gid`、`repository_gid`、可选 `bop_node_gid`、`lineage_gid` 和创建时 version ref。节点升版、移动或删除时，引用仍可通过 lineage 和 tombstone 解释；不得把任务或问题复制进 BOP 表。

## 11. 状态、删除与保留

Repository/space lifecycle、archive、delete 和 row version 正交。团队空间不能单独脱离 Repository 删除；当前项目管理者可归档/恢复 Repository，具备当前项目删除权限的主体可执行受限 tombstone 删除并释放项目唯一槽位。删除永远不级联知识项目、VPPS、Artifact、Simulation Context、任务、问题或 VisMockup；存在 legal hold、active run 或未收敛的跨域对账时拒绝。

个人空间和私人环境 owner 可逻辑删除自己的空间；个人空间有未收敛提案时拒绝删除。不可变 Fork base、提案证据、audit 和最小 lineage tombstone 保留。Archive/Delete 与 active run lease 在同一 guard/行锁串行化；有活动运行返回 `active_run_exists`，tombstone 后禁止新运行。第一阶段不实现物理 purge。

## 12. 数据模型

使用 Craft `0010_bop_repositories.sql` 和 Simulation `0012_simulation_contexts.sql` 等新增迁移扩展，不修改已执行的 `0011_simulation_workspaces.sql` 或其他历史迁移。旧 Simulation project-main/publish plan/map/outbox 进入 deprecated compatibility：停止新写入和新消费者，历史只读。

建议新增或扩展：

| 表 | 作用 |
|---|---|
| `craft_bop_repositories` | project 唯一 Repository、lifecycle、head/baseline/frozen pointer、tombstone |
| `craft_bop_spaces` | team/managed_personal、owner、fork base、row version |
| `craft_bop_repository_versions` | immutable manifest、source refs、算法和 ArtifactRef |
| `craft_bop_fork_runs/plans` | 来源、目标、复制深度、幂等、状态和 evidence |
| `craft_bop_fork_blueprint_nodes` | 深度以下的灰色蓝图节点和 materialized node ref |
| `craft_bop_vpps_groups/versions/members` | 有序组、版本链、current/reference pointer 和成员树 |
| `craft_bop_change_proposals/units/conflicts` | 三方 Diff、选择单元、冲突和应用 outcome |
| `craft_bop_personal_import_operations` | 私人环境到个人空间的导入与对账 |
| `simulation_contexts` | 对 Repository/space/version 的 Simulation 扩展引用 |

跨域不建外键和 cascade，只保存 GID/ref/hash。OceanBase/MySQL 唯一性使用 guard/lock 表或可验证生成键，不依赖 partial unique index。迁移测试覆盖前向迁移、回填、幂等重跑、失败前滚/回滚、并发唯一和 OceanBase DDL。

## 13. Capability 边界

本节 ID 均为 `not_registered` 设计候选，除非 G0 从真实 Registry 证明已有等价能力。不得将候选称为 experimental 或直接加入产品 release。每个能力实施前必须由 owner 完成 definition、Descriptor、Provider、Schema、selector、confirmation、幂等、审计、consumer contract、测试、真实 capability version GID 和 lifecycle 决策。

| 候选精确 ID | 闭合输入/输出 | 权限、事务、审计与消费者 |
|---|---|---|
| `craft.bop.repository.get@1` | repository selector → metadata、team space、head/baseline refs | 项目读权限；只读分页；Desktop/Agent |
| `craft.bop.space.get@1` | space selector + projection page → head、nodes、VPPS group refs | team 项目权限或 personal owner；只读；Desktop/Agent |
| `craft.bop.repository_version.get@1` | version + projection page → immutable manifest、source refs/hash | 来源权限；只读；Desktop/Agent |
| `craft.bop.repository.fork@1` | source immutable version、target project、fork_depth、expected empty slot、idempotency → repository/team space/fork run | 来源读 + 目标项目管理；guard 锁内创建，跨 Artifact 用 saga；Desktop；审计 source/target/plan/hash |
| `craft.bop.repository.archive@1` | repository、expected row、idempotency → archived_at/row version | 当前项目管理者；guard 锁拒绝 active run；Desktop；不改变不可变版本 |
| `craft.bop.repository.restore@1` | repository、expected row、idempotency → archived_at=null/row version | 当前项目管理者；guard 锁与唯一性校验；Desktop |
| `craft.bop.repository.delete@1` | repository、expected row、reason、idempotency → deletion GID/time/保留引用摘要 | 当前项目删除权限；tombstone、legal hold/run guard；不级联 Project/Knowledge/Simulation/Artifact/任务/问题 |
| `craft.bop.managed_personal_space.fork@1` | source version/personal Diff、target repository、expected empty personal slot、idempotency → personal space/fork-base | 仅当前 actor 的空间；guard 锁；Desktop；已有空间稳定拒绝 |
| `craft.bop.managed_personal_space.delete@1` | personal space、expected row、idempotency → tombstone/保留提案摘要 | 当前 owner；有未收敛提案或 run 时拒绝；Desktop；团队不受影响 |
| `craft.bop.managed_personal_space.sync.preview@1` | personal、base、ours、theirs、limits → Diff/conflicts/input hash | owner；只读任务；Desktop/Agent；记录算法版本 |
| `craft.bop.managed_personal_space.sync.apply@1` | preview ref、selected units、expected heads、idempotency → new personal head/unit outcomes | owner；单库 CAS；Desktop；依赖闭包与 before/after audit |
| `simulation.environment.workspace.fork@1` | source immutable refs、target metadata、idempotency → private workspace/fork-base | 来源读 + 新 workspace owner；Simulation saga；Desktop；数量不限 |
| `simulation.environment.workspace.delete@1` | private workspace、expected row、idempotency → tombstone/保留引用摘要 | 当前 owner；guard 锁；Desktop；既有 Fork 和 Artifact refs 保持 |
| `craft.bop.managed_personal_space.import.preview@1` | private manifest、private base/head、personal head、limits → typed Diff/conflicts | personal owner 且 source 可读；只读；Desktop/Agent |
| `craft.bop.managed_personal_space.import.apply@1` | preview ref、selected units、expected personal head、idempotency → new head/unit outcomes | personal owner；Craft 单库 CAS，只消费 immutable Simulation refs；Desktop |
| `craft.bop.fork_run.get@1` | fork run selector → bounded status/plan/evidence/errors | 发起人或目标项目权限；只读；Desktop/scheduler |
| `craft.bop.vpps_group.initial.generate@1` | fork run/reference group/target project/policy/idempotency → generated_initial version/candidates/confidence | Task Tool/scheduler delegation；Artifact + Craft saga；不推进 team current；记录模型、Tool、Catalog、hash |
| `craft.bop.vpps_group.adjustment.create@1` | group/base version/ordered operations/reason/evidence/expected current/idempotency → immutable adjustment version | team 项目管理候选或 personal owner/Agent delegation；CAS；Desktop/Agent Tool |
| `craft.bop.vpps_group.current.set@1` | group/version/expected current/idempotency → current pointer/row version | team 仅项目管理者；personal 可由 owner/明确 Agent delegation；单库 CAS；审计决定主体 |
| `craft.bop.change_proposal.create@1` | personal version/team base/selected units/Diff hash/idempotency → draft proposal | personal owner；单库事务；Desktop；固定输入版本 |
| `craft.bop.change_proposal.submit@1` | draft/expected proposal version/idempotency → submitted proposal | personal owner；CAS；Desktop；提交后内容不可原地改 |
| `craft.bop.change_proposal.get@1` | proposal/projection page → status、units、conflicts、outcomes | owner、项目评审者；只读；Desktop/Agent |
| `craft.bop.change_proposal.review@1` | proposal/unit decisions/expected team+proposal versions/idempotency → reviewed units/status | 当前项目管理者；CAS；Desktop；记录逐项理由和依赖诊断 |
| `craft.bop.change_proposal.apply@1` | reviewed proposal/accepted units/expected team head/idempotency → new team head/per-unit Craft outcome refs | 项目管理者或其显式调度任务；Craft 原子批次/CAS；不重放已完成单元 |
| `craft.bop.repository_diff.start@1` | left/right/base refs、algorithm、limits、idempotency → Diff run/input hash | 两侧读取权；只读任务；Desktop/Agent |
| `craft.bop.repository_diff.get@1` | Diff run/cursor/page size → BOP+VPPS typed results/next cursor/result hash | 调用者读取权；只读分页；Desktop/Agent |

每个 ID 只表达一个 effect。所有写入都使用服务端资源 selector、expected version、稳定 operation GID 和幂等键；读取有 cursor、page size、max nodes/depth 和字段裁剪。现有 Craft draft preview/apply 只能在合同足以表达依赖闭包、原子应用和 outcome 时复用；不得把新 Repository 语义静默塞入旧 @1。Simulation 不直接写 Craft 表，Task Tool 和 Agent 也只能调用 pinned Catalog Release 中明确 exposure 的能力。

## 14. Agent 与自动化

Agent 使用 Task Tool 编排确定性 Capability。模型可以解释 Diff、建议 VPPS 匹配、生成 adjustment 内容和风险摘要；Provider 决定 Schema、权限、依赖、幂等和是否可推进 current pointer。

当前 Agent 运行时只能从 pinned Catalog Release 将 `exposure.agent=true` 的精确 Capability 1:1 投影为工具；现有 Task Tool registry 没有 BOP Repository/Fork/VPPS/提案编排工具，现有系统工程 Skill 也不提供该业务流程。因此这部分属于待治理的新能力，不能调用 legacy 手写 `tool_registry.py` 或假设工具已经存在。

新增一个显式的 Simulation/Craft profile Task Tool `task.bop_repository_assistant`，第一阶段只编排第 13 节列出的固定 ID/major，用于生成初版、解释 Diff、创建 adjustment 和准备提案材料。它不成为数据 owner，不直接查表，也不实现动态 DSL。配套薄 Skill 只说明何时调用、如何解释结果和何时交给项目管理者；权限、状态转换和写入仍由 Provider 决定。

个人/私人自动推进需要 owner delegation，固定空间、Agent actor、允许的 Capability ID/major、策略 hash、Catalog Release、有效期和撤销状态。团队空间不允许 Agent 直接推进 current VPPS 组、接受提案或写正式 BOP。

每次生成记录输入 version/hash、模型和 Tool 版本、候选、置信度、调整原因、Capability outcome 和审计引用。自动化不得覆盖 reference 或历史 group version。

## 15. 稳定失败与恢复

至少定义：`target_repository_exists`、`managed_personal_space_exists`、`source_version_not_immutable`、`source_reference_denied`、`fork_depth_invalid`、`vpps_group_generation_failed`、`team_head_advanced`、`proposal_conflict`、`dependency_not_selected`、`lineage_resolution_failed`、`resource_version_conflict`、`project_permission_denied`、`active_run_exists`。

核心 Fork 失败不能发布部分 Repository；generated_initial 失败允许独立重试。Craft 写入成功而投影或提案记录失败时，以 Craft outcome 为权威，进入 reconciliation，不盲目重放。所有重试使用稳定 operation GID 和幂等键。

## 16. 验收场景

1. 同一知识项目不能创建两个有效 BOP Repository，也不能有两个团队空间。
2. 同一用户在同一 Repository 最多一个受管个人空间，但可以创建多个私人仿真环境。
3. 团队 Fork 支持任意项目派生原因，不依赖年份或车型命名。
4. 目标已有 Repository 时整体 Fork 被拒绝且不覆盖数据。
5. 五种复制深度分别生成正确的正式节点边界和 reference VPPS 组。
6. 深度以下节点不进入正式 BOP 查询、统计和资源关系。
7. VPPS 组保留层级、重复成员和 sibling 顺序；插入成员不重排整组。
8. reference 永不覆盖；自动生成初版和用户/Agent adjustment 形成可追溯版本链。
9. Agent 在个人/私人空间按 delegation 自动推进，在团队空间只能产生候选。
10. 个人无修改时快进，有修改时正确计算 Base/Ours/Theirs 和冲突。
11. 私人环境只能先导入个人空间，再由个人空间提交团队提案。
12. 项目管理者可部分接受原子单元，依赖闭包完整，已应用单元不会重复执行。
13. 团队、个人、私人三种 Fork 共用身份、manifest、Diff 和幂等规则，不复制跨域主数据。
14. 来源删除后既有 Fork 仍可读取自身 fork-base 和历史 Diff。
15. Fork 核心成功但自动 VPPS 生成失败时，参考蓝图可见且重试不重复创建 Repository。
16. 任务、问题和 Simulation Context 在 BOP 升版、移动或 tombstone 后仍能通过 lineage 解释。
17. G-Craft-Collab 未通过时使用整 BOP CAS，UI 不宣称线体独立并发。
18. 候选 Capability 未达到 stable release target 前，产品路由不可调用。

## 17. 明确不做

- 不把仿真环境作为项目主 Repository。
- 不限制用户创建私人仿真环境的数量。
- 不允许私人环境直接向团队空间提交提案。
- 不允许目标 Repository 或个人空间被 Fork 覆盖。
- 不根据项目名称、年份、车型或基地自动推断 Fork 关系。
- 不把相同 VPPS 当作相同 BOP 实例。
- 不把 reference VPPS 蓝图成员写成正式 BOP 节点或正式资源关系。
- 不让自动化静默重排 VPPS 组或覆盖历史版本。
- 第一阶段不建设全局 VPPS 组模板、通用 merge 引擎或物理 purge。
- 不跨域直表、外键、级联删除或伪造跨域事务。
