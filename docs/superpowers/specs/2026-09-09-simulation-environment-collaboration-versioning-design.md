# 项目 BOP Repository、Fork、VPPS 与变更提案设计

**日期：** 2026-09-09
**状态：** 业务设计已确认，等待架构复审
**基础设计：** `docs/superpowers/specs/2026-09-08-digital-simulation-environment-redesign.md`

## 1. 设计结论

项目级管理对象由“仿真环境仓库”调整为 **BOP Repository**。一个 Project Management 权威项目（知识库页面入口）只维护一个 BOP Repository；BOP 的线体、工位、岗位、工序、操作及其零件和资源绑定是项目协作主结构，Simulation Context、任务、问题和后续领域对象都引用该结构。

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

逐对象规则如下；“复制”仍受 portability plan 和目标权限约束：

| 对象 | 全部复制 | 到操作 | 到工序 | 到岗位 | 到工位 |
|---|---|---|---|---|---|
| BOP nodes | 全部复制 | 线体至操作 | 线体至工序 | 线体至岗位 | 线体至工位 |
| portable 节点属性 | 随已复制节点复制 | 随已复制节点复制 | 随已复制节点复制 | 随已复制节点复制 | 随已复制节点复制 |
| 零件/资源/Load/Operate binding | 经逐引用授权后复制 | 清空实例，转 reference VPPS | 清空 | 清空 | 清空 |
| reference VPPS group | 保存完整来源证据 | 保存绑定层参考 | 保存操作以下参考 | 保存工序以下参考 | 保存岗位以下参考 |
| 截图和既有 Artifact | 不复制，只保留允许的 source evidence ref | 同左 | 同左 | 同左 | 同左 |
| Simulation Context | 不由 Craft Fork 复制；另走 Simulation Capability | 同左 | 同左 | 同左 | 同左 |
| 任务、问题 | 永不复制；只由 owner impact 查询说明影响 | 同左 | 同左 | 同左 | 同左 |
| ACL、owner、项目角色 | 永不复制；按目标项目重新解析 | 同左 | 同左 | 同左 | 同左 |

portable 属性白名单由 Craft owner 版本化；项目专属审批、执行状态、任务引用、用户字段和运行证据不在白名单内。

## 5. 实例身份、血缘与 VPPS 类型

VPPS 表达“该位置承担什么工艺职责”，类似跨项目稳定的业务类型；BOP node 表达该职责在具体项目中的实例。两者不能混用。

| 标识 | 语义 |
|---|---|
| `vpps_gid` | Knowledge 拥有的稳定 VPPS 身份 |
| `bop_node_gid` | 当前项目中的具体 BOP 实例 |
| `lineage_gid` | 具体实例跨版本的逻辑延续 |
| `derived_from_node_gid` | 本次 Fork 的直接来源实例 |
| `source_repository_gid/version_gid` | Fork 的 Repository 级来源 |

### 5.1 Repository 内身份不变量

| 场景 | node GID 与 revision 规则 |
|---|---|
| 团队节点进入个人空间 | 复用同一 `bop_node_gid`，个人 space head 引用自己的 immutable node revision，不复制逻辑实例 |
| 个人修改既有节点 | 保持 node GID，追加 personal-space revision；团队 revision 不变 |
| 个人新增节点 | 生成新 node GID，`lineage_gid=self`；接受到团队时保留该 node GID，并把已接受 revision 写入 team head |
| 个人删除节点 | 个人 head 写空间内 tombstone；团队节点在提案接受前不受影响 |
| 同一 Repository 提案应用 | 既有/新增 node GID 均保留；只推进 team-space revision/membership，不创建映射替身 |
| 跨 Repository Fork | 所有复制的正式节点生成新 node GID，继承来源 `lineage_gid` 并记录 `derived_from_node_gid` |

任务、问题和 Simulation Context 只能把 team-space 已存在节点作为正式项目引用。个人新增节点在被团队接受前只能由个人空间内对象引用；接受后因 node GID 保留，无需重写引用身份。

仅保留 VPPS 的蓝图成员不预先生成 BOP node GID；后续实例化时生成新 GID，并记录来源 blueprint member。相同 VPPS 不等于同一实例。

### 5.2 VPPS 组的空间作用域

每个 `(space_gid, boundary_node_gid)` 最多绑定一个 `vpps_group_gid`。团队空间和各个人空间拥有不同 group GID、reference/current pointer 和 revision，不能共享一个可变 current pointer。每个组保存 `group_lineage_gid` 与 `derived_from_group_gid`：

- 团队组进入个人空间时创建个人 group GID，继承 group lineage 和 direct derivation；
- 个人调整不会推进团队 current；
- 提案接受个人 VPPS 调整时，在团队 group 下创建新的 immutable team version，记录 `derived_from_personal_group_version_gid`，再由项目管理者推进团队 current；
- 个人新增边界节点被接受后，团队为该 node 建立独立 team group GID，继承个人 group lineage，不复用个人 current pointer；
- 跨 Repository Fork 创建新 group GID，保留 group lineage、来源 group/version 和 source Repository。

## 6. 有序 VPPS 组

### 6.1 结构

一个蓝图节点或已实例化边界节点只能绑定一个 VPPS 组；reference/current 是该组的版本指针，不是多个并列组。一个组包含多个有层级、同层有顺序的成员。相同 `vpps_gid` 可以在同一组出现多次，由不同 member GID 区分。

```text
vpps_group
├─ space_gid / boundary_node_gid
├─ group_lineage_gid / derived_from_group_gid
├─ reference_group_version_gid
├─ current_group_version_gid
└─ vpps_group_version
   └─ ordered_member
      ├─ member_gid
      ├─ vpps_gid
      ├─ parent_scope_gid (NOT NULL)
      ├─ node_level
      ├─ order_key
      ├─ source_bop_node_gid
      └─ source_node_lineage_gid
```

同一版本内以 `(group_version_gid, parent_scope_gid, order_key)` 唯一。`parent_scope_gid` 不可为 null：根成员统一使用该 group version 的 `root_scope_gid`，子成员使用父 member GID，避免 MySQL/OceanBase 中 nullable unique 允许多个根顺序冲突。顺序只在同一父 scope 下比较；canonical 序列化按根 sibling order，再递归按各层 sibling order 输出，并以 member GID 作为检测非法重复 order 后的稳定诊断证据，不允许相同 order 静默共存。写入提交 expected group current version 做 CAS。

`order_key` 使用可插入的稳定有序键，不使用全局连续序号。键空间不足时生成包含完全相同语义顺序的新 adjustment/rebalance 版本；canonical semantic hash 按成员相对顺序计算，单纯 rebalance 不产生业务顺序变化。组版本固定后不可修改。

### 6.2 版本生命周期

操作者类型与版本生命周期分离：

| `version_kind` | 含义 |
|---|---|
| `reference` | Fork 保存的来源 VPPS 结构，永不覆盖 |
| `generated_initial` | 自动匹配生成的目标初版 |
| `adjustment` | 用户、Agent 或确定性自动化产生的后续调整版 |

每个版本保存 `parent_version_gid`、actor GID/type、原因、evidence refs、算法或 Agent 版本、Catalog Release 和 content hash。组保存：

- `reference_group_version_gid`：不可覆盖的来源参考；
- `current_group_version_gid`：当前采用的初版或调整版；Fork 核心刚 ready 时允许为 null，UI 以 reference 灰色预览但不得当成正式 current。

原设计中的 proposed/assigned 双字段取消。是否生效由 current pointer 表达，不由“是不是人工操作”决定。

### 6.3 自动生成与调整

- Fork 核心完成后异步生成 `generated_initial`，状态为 pending/ready/failed；同一 `(target_group_gid, reference_version_gid, matcher_policy_hash)` 只有一个稳定 operation/outcome，避免同一参考版本派生到多个目标组时误复用结果。失败可幂等重试且不破坏 Repository、空间或 reference group。
- 自动匹配只能建议成员对应关系并继承参考层级和顺序，不能静默重排。
- 用户、Agent 和自动化调整均追加 `adjustment` 版本，不原地覆盖。
- 团队空间的 generated_initial 和 Agent adjustment 都只是 candidate，项目管理者接受后才推进 current pointer。
- 受管个人空间和私人环境可由 owner 的有效 policy/delegation 自动推进 ready 的 generated_initial 或 adjustment；无授权时 current 保持不变并显示候选。
- current group 与 reference group 不同时是正常项目差异，Diff 标为 VPPS 重新归类、移动或重排，并保留两边。

## 7. Fork 类型与规则

### 7.0 空白 Repository 与不可变来源

新项目不要求必须从其他项目 Fork。项目管理者通过显式 Craft Repository Create 能力，在目标项目唯一槽位内原子创建空 Repository、团队空间和初始 mutable head；Project Management 只提供项目身份/授权，Craft 不由跨域事件暗中自动建库。

团队或个人 mutable head 只有通过受治理的 space-version save/freeze 能力才能形成 Fork 来源。版本 manifest 固定 space、head revision、节点/绑定/VPPS membership、source refs、算法、Capability version 和 Artifact hash。Fork 只接受这些能力产出的 immutable version GID，不允许 Provider 内部临时直写快照。

### 7.1 团队空间 Fork

- 从任意可读项目团队空间的精确不可变版本创建目标项目的唯一 Repository 和团队空间。
- 目标项目已有未删除 Repository 时返回 `target_repository_exists`，不得覆盖。
- 发起人必须有来源版本读取权、独立 fork/export 权和目标项目 Repository 创建/管理权；第一阶段只允许同租户 Fork。
- 项目派生原因可以是换代、年款、车型、基地或其他业务原因，系统不硬编码类型。

### 7.2 受管个人空间 Fork

- 用户只能创建自己的目标个人空间，不能复制他人的个人空间。
- 目标个人空间不存在时，从来源的精确不可变版本和个人 Diff 创建。
- 目标个人空间已存在时返回 `managed_personal_space_exists`，UI 转入三方 Diff 和选择性导入，不覆盖。
- 当来源和目标团队空间具有共同 base 时，只迁移个人 Diff；没有共同 base 时按 lineage、VPPS 和 source refs 做三方映射。
- 用户可在一次向导中同时选择“Fork 目标团队空间”和“迁移自己的个人空间”。`repository.fork.preview` 接受 `include_personal_migration` 和可选的来源个人空间，创建并返回共享 workflow/correlation GID；`repository.fork.apply` 在该 workflow 下创建团队 Fork 与个人迁移两个有序 child step。团队 Fork 成功而个人迁移失败时保留团队 Repository；个人步骤以原 workflow GID、固定来源和稳定 step idempotency key 重试，客户端只通过 workflow get 恢复状态，不能依赖浏览器内存重新拼装请求。

### 7.3 私人仿真环境 Fork

- 数量不限，目标容器默认 private。
- 私人环境 Fork 后仍为 private；第一阶段不把它转换为团队或公共空间。
- 来源删除后，既有 Fork 继续通过自身 immutable fork-base 和 ArtifactRef 使用。

### 7.4 Fork Preview—Apply 流程

1. Preview 固定来源不可变版本、复制深度、目标项目/空槽 expected version、可选来源个人空间和 `include_personal_migration`，校验 read 与 fork/export 两种授权并拒绝跨租户来源。
2. Preview 逐项调用 Project、Knowledge、Digital Model、Artifact、Teamcenter/JT 等 source owner 的可复用/再分发判断，生成 `copy/reference/unresolved/redacted/reject` portability plan；Renderer 只能选择 owner 已允许的处理项，不能提交或伪造 owner verdict。
3. Preview 默认对正式结构、绑定和安全敏感引用 fail-closed；只有 owner 合同明确允许且用户在预览中接受时才能采用 unresolved/redacted reference。Preview 返回 `preview_gid`、`workflow_gid`、plan hash、固定输入 hash、过期时间和有界 evidence，不创建目标 Repository。
4. Apply 只接受 `preview_gid`、plan hash、用户在允许集合内的显式 decisions、expected target slot、receipt/idempotency。Provider 重新读取 preview，复验过期时间、来源授权、owner portability verdict、目标唯一槽位和 plan hash；任何漂移都要求重新 Preview。
5. Apply 在 workflow 下创建幂等 fork run。深度以内生成目标实例、GID、lineage 与 derivation；深度以下生成 immutable、有序 reference VPPS group。
6. Apply 校验节点数、引用、hash 和权限后，将核心 Fork 置为 `ready`；若请求包含个人迁移，则随后执行独立 child step，并保留各自 outcome。
7. 核心 Fork ready 后异步生成 `generated_initial`；状态独立为 pending/ready/failed，可幂等重试。

Fork 失败不得发布部分 Repository。相同幂等键和 payload 返回原 outcome；不同 payload 返回幂等冲突。自动匹配失败不回滚已经 ready 的核心 Fork。

## 8. Diff、同步与选择性导入

### 8.1 两层 Diff

Craft Repository Diff 只覆盖 Craft 拥有的节点新增/删除/移动/排序、portable 属性、Load/Operate、零件和资源绑定，以及 VPPS reference/generated_initial/adjustment/current 之间的成员新增/删除/替换、跨父移动、同级重排、实例化状态及 provenance。它不读取或复制任务、问题、Simulation Context 等其他领域的入向引用。

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

没有个人修改时允许快进。存在修改时必须完成三方 Diff，保留用户视点和未提交意图。客户端只提交 `personal_space_gid`、选择单元和预期 personal/team head version；Provider 根据受信空间记录解析 Base/Ours/当前 Theirs 和个人 Diff，拒绝客户端拼接跨 Repository、跨 owner 或任意 version 的三方输入。

### 8.3 私人环境导入

私人环境到受管个人空间只允许从用户主动保存的不可变私人版本选择原子变更单元导入，不能读取不断漂移的 workspace head。Simulation 先通过 `workspace_version.export_for_import` 对 source workspace/version 授权，生成 opaque export ref；签名内容固定 caller actor、tenant、target personal space/repository、允许的 consumer Capability ID/major、source workspace/version、content hash 和有效期。原始私人 manifest、base/head 和 owner 判定不能由 Renderer 提交，同一个 export ref 不能跨目标、跨调用者或跨用途重放。

Craft import Preview 只接受该 export ref、`personal_space_gid`、expected personal head 和 limits，通过 Gateway 向 Simulation 解析并复验 immutable source，再以其 fork-base、固定 source version 和个人 head 做三方比较。Apply 只接受 Preview ref、选择单元、expected personal head 和幂等键，并重新验证 Preview 未过期、source hash 未变且权限仍有效。冲突在个人空间解决；导入不创建团队提案，也不绕过 Craft Provider。

## 9. 变更提案

提案唯一流向为受管个人空间 → 同 Repository 团队空间。评审与执行是两个正交状态：

- `review_status`：`draft/submitted/reviewing/accepted/partially_accepted/rejected/withdrawn/cancelled/superseded`；
- `apply_status`：`not_started/applying/partially_applied/applied/apply_failed/reconciling`。

提案固定个人 version、团队 base version、Diff hash 和原子变更单元。提交后个人后续修改不自动进入该提案。

原子变更单元至少包括：节点新增、移动或删除；单个属性变更；单条绑定变化；一个 VPPS 组 adjustment；一段 VPPS 子树实例化。Create/Preview 阶段输出显式 closure graph，把用户选择项、自动发现的 required 依赖和依赖原因分别展示。项目管理者必须明确接受一个完整依赖连通分量；不得因勾选一个单元而隐式带入未展示或未接受的父节点、绑定或 VPPS 变化。

应用原子边界固定为“一个依赖连通分量”：同一分量在一个 Craft 单库事务/CAS 中全部成功或全部失败，不同分量可独立应用，因此允许 `partially_applied`。每个分量使用稳定 operation GID，记录全部 unit outcome 与 Craft audit ref，不得重复应用。团队 head 前进后原 preview/review 失效，必须重新生成 closure/conflict 预览并由项目管理者再次接受。

允许的状态组合与转换固定如下，其他组合由数据库约束或 Provider 拒绝：

| 当前组合 | 允许转换 | 是否终态 |
|---|---|---|
| `draft/not_started` | submit → `submitted/not_started`；cancel → `cancelled/not_started` | 否；cancel 后是 |
| `submitted/not_started` | review → `reviewing/not_started`；withdraw → `withdrawn/not_started` | 否；withdraw 后是 |
| `reviewing/not_started` | review decision → `accepted/not_started`、`partially_accepted/not_started` 或 `rejected/not_started` | 否；rejected 后是 |
| `accepted/not_started`、`partially_accepted/not_started` | apply → 对应 review status + `applying` | 否 |
| accepted/partially_accepted + `applying` | component success → `partially_applied` 或 `applied`；失败 → `apply_failed`；不确定 → `reconciling` | 否；`applied` 见下述终态规则 |
| accepted/partially_accepted + `partially_applied` | apply remaining、supersede remaining 或 reconcile | 否 |
| accepted/partially_accepted + `apply_failed` | retry 或 reconcile | 否 |
| accepted/partially_accepted + `reconciling` | 回到 `partially_applied`、`apply_failed` 或 `applied` | 否 |
| 任意无 active apply/reconcile 的非终态 | supersede → 无应用结果时 `superseded/not_started`；已有部分结果时 `superseded/partially_applied` 并关闭 remaining set | 是，既有 outcome 保留 |

终态谓词固定为：`cancelled/not_started`、`withdrawn/not_started`、`rejected/not_started`；或 `apply_status=applied` 且所有已接受分量均有成功 outcome；或 `review_status=superseded` 且没有 applying/reconciling 分量、remaining set 已明确关闭。`partially_applied` 本身永远不是终态；当部分接受的提案中所有 accepted 分量均已应用、其余分量已被拒绝时，状态收敛为 `partially_accepted/applied`。accepted/partially_accepted 后禁止 withdraw；停止剩余工作必须 supersede，并保留既有应用结果。

Draft 可由 owner cancel；submitted 且尚未接受/应用的提案可 withdraw。个人空间删除只被所有不满足终态谓词的提案阻止；draft 可先 cancel，未评审 submitted 可先 withdraw。Agent 可解释和推荐，不能代表项目管理者接受团队提案。

## 10. Simulation Context、任务与问题

仿真环境不再作为项目 Repository。团队或个人空间可挂接一个或多个版本化 Simulation Context，保存 VM snapshot、occurrence、pose、截图和 VisMockup session 映射，并引用精确 repository/space/version/node/lineage。

任务、问题和其他未来对象由各自 owner 保存，只引用 `project_gid`、`repository_gid`、可选 `bop_node_gid`、`lineage_gid` 和创建时 version ref。节点升版、移动或删除时，引用仍可通过 lineage 和 tombstone 解释；不得把任务或问题复制进 BOP 表。

跨域影响分析由 `task.bop_repository_assistant` 组合查询：先读取 Craft Diff 的稳定 node/lineage mapping，再调用 Simulation、任务和问题各 owner 的只读 impact Capability，最后生成有界汇总。任何 owner 尚未提供受治理 impact Capability 时，只显示“该域影响未验证”，不得由 Craft/Simulation 直表补齐，也不得在团队 Fork 中复制这些对象。

## 11. 状态、删除与保留

Repository/space lifecycle、archive、delete 和 row version 正交。团队空间不能单独脱离 Repository 删除；当前项目管理者可归档/恢复 Repository。Repository 存在未删除受管个人空间、未终结提案、active run、未收敛对账或 legal hold 时必须拒绝删除。清理完这些阻塞后，当前项目删除权限主体可写 Repository tombstone 并释放项目唯一槽位。

Repository tombstone 永远不级联 Project、VPPS、Artifact、Simulation Context、任务、问题或 VisMockup，也不物理删除 BOP/version。旧 Repository、team/personal head、proposal 和 lineage 永远绑定旧 `repository_gid`；同一项目以后建立的新 Repository 生成新 GID，旧子对象不得重新挂到新 root。

个人空间和私人环境 owner 可逻辑删除自己的空间；个人空间有未收敛提案时拒绝删除。不可变 Fork base、提案证据、audit 和最小 lineage tombstone 保留。Archive/Delete 与 active run lease 在同一 guard/行锁串行化；有活动运行返回 `active_run_exists`，tombstone 后禁止新运行。第一阶段不实现物理 purge。

## 12. 数据模型

使用 Craft `0010_bop_repositories.sql` 和 Simulation `0012_simulation_contexts.sql` 等新增迁移扩展，不修改已执行的 `0011_simulation_workspaces.sql` 或其他历史迁移。最终物理表遵循现有前缀：Craft 使用 `workmanship_craft_bop_*`，Simulation 使用 `workmanship_sim_*`；下表的逻辑对象名必须映射到这些物理名。

建议新增或扩展：

| 表 | 作用 |
|---|---|
| `workmanship_craft_bop_repositories` | project 唯一 Repository、lifecycle、baseline pointer、tombstone；baseline 只能指向同 Repository team space 的 immutable version |
| `workmanship_craft_bop_spaces` | team/managed_personal、owner、fork base、mutable head row version；team 的 `frozen_version_gid` 固定在此，不放在 Repository |
| `workmanship_craft_bop_space_versions` | `space_gid`、`version_kind`、immutable manifest、source refs、算法和 ArtifactRef |
| `workmanship_craft_bop_nodes` | Repository 内稳定逻辑 node GID、lineage、direct source 和 created provenance，不承载可变内容 |
| `workmanship_craft_bop_node_revisions` | immutable node revision GID、node GID、portable 属性、parent/order、content hash 和 actor/evidence |
| `workmanship_craft_bop_bindings` | Repository 内稳定 logical binding GID、binding lineage 与 created provenance，不承载可变内容 |
| `workmanship_craft_bop_binding_revisions` | immutable binding revision GID、稳定 binding GID、source/target node/resource ref、语义和 content hash |
| `workmanship_craft_bop_space_heads` | 每个 space 当前 mutable head、CAS row version、node/binding/VPPS head refs |
| `workmanship_craft_bop_space_head_members` | 当前 head 的 node/binding revision membership 与 `is_tombstone`；同一 node 在不同空间可指向不同 revision |
| `workmanship_craft_bop_space_version_members` | immutable space version 的完整 node/binding/VPPS membership；创建后禁止更新/删除 |
| `workmanship_craft_bop_fork_workflows/runs/plans` | workflow 与团队/个人 child step、来源、目标、复制深度、plan/input hash、expiry、幂等、状态、owner portability verdict 和 evidence |
| `workmanship_craft_bop_fork_blueprint_nodes` | reference blueprint member 的物理投影；深度以下唯一蓝图事实和 materialized node ref |
| `workmanship_craft_bop_vpps_groups/versions/members` | 有序组、版本链、space-scoped current/reference pointer 和成员树 |
| `workmanship_craft_bop_change_proposals/units/conflicts` | 三方 Diff、closure graph、review/apply 状态和 component outcome |
| `workmanship_craft_bop_personal_import_operations` | 私人环境到个人空间的导入与对账 |
| `workmanship_sim_contexts` | 对 Repository/space/version 的 Simulation 扩展引用 |
| `workmanship_sim_environment_vpps_groups/versions/members` | 私人环境独立的有序 VPPS 组、版本和 space-scoped pointer |

同域可使用受控 FK，跨域不建 FK/cascade，只保存 GID/ref/hash。OceanBase/MySQL 唯一性使用 guard/lock 表或可验证生成键，不依赖 partial unique index。

旧 `workmanship_bop_bop_versions` 是以 version row 表达 BOP 快照/工作版本，`workmanship_bop_bop_entries` 的 entry GID 直接从属于 `version_gid` 并混合身份与内容，`workmanship_bop_bop_entry_links` 又直接从属于 entry；它们缺少 space、稳定 logical node、独立 revision、space head membership 和 space tombstone 语义。因此新模型采用 additive 表，不原地重释旧 GID：迁移为每个旧 entry 建立确定性 mapping，生成 logical node GID 与 immutable node revision；同一 lineage 可被确认映射时复用 logical node，否则 quarantine，禁止按名称猜测。旧 link 同样映射为稳定 binding GID + immutable binding revision。team/personal head 和每个 immutable space version 只通过 membership 表选择 revision；删除节点写 space-scoped tombstone membership，不删除 logical node 或其他空间的 revision。每个 `(space_head_gid, member_kind, logical_gid)` 只有一个有效 membership；所有 head membership 变更与 head row-version CAS 在同一 Craft 事务中提交，immutable version membership 创建后禁止更新和删除。

`workmanship_craft_bop_space_versions` 的 `space_gid` 不可为空，`version_kind` 至少区分 `saved/frozen/fork_base/proposal_base`。团队 freeze 只能 CAS 更新对应 team space 的 `frozen_version_gid`；Repository baseline set 必须由 Provider 验证目标 version 属于同一 Repository 的 team space 且 immutable，不能指向 personal/private/跨 Repository version。

### 12.1 旧数据迁移与切换

| 现有数据 | 新归属/处理 |
|---|---|
| 当前 Craft BOP 及其项目引用 | 按 Project Management `project_gid` 归并为每项目一个 Repository/team space；活动 draft 成为 team head，历史稳定版本映射为 Repository versions |
| 同一项目多个活动 BOP 候选 | 不自动挑选，进入 quarantine，项目管理者处理后才能切换 |
| 缺失或无权读取 project ref 的 Craft BOP | 进入 quarantine，不生成伪项目或 Repository |
| `0011` Simulation private workspaces/versions/nodes/bindings | 保持 Simulation owner 和原 GID，作为不限数量私人环境；补可选 Repository source ref，不迁入 Craft space |
| `0011` publish plan/map/outbox | 冻结新写入；保留历史只读和 audit，不转成 change proposal |

迁移采用受控维护写隔离，不做业务双写：

1. 创建 guard、新表和只读 mapping 工具；可记录一个仅用于 bulk snapshot 优化的 preliminary high-water，但它不是切换边界。
2. 通过一个受控原子 guard 步骤启用覆盖旧 Craft BOP 修改、旧 publish plan/map/outbox 和受影响 Simulation workspace/version 写入的 maintenance write fence；新写返回稳定 `migration_write_fenced`，不进入旧表或新表。该步骤同时记录 fence activation token。
3. 等待 fence 前已获 lease 的 in-flight operation 排空；排空后记录唯一权威的 final high-water。按 operation ledger 对账到 final high-water；preliminary high-water 与 final high-water 之间的全部 delta 必须进入回填。无法确定 outcome 时停止切换并 reconcile，不能继续回填。
4. 回填 Repository/team/space version、node/binding identity/revision/membership 与 ID mapping；若先做 bulk snapshot，则显式重放 `(preliminary, final]` delta。0011 私人环境保持原 GID。对账项目数、BOP/节点/绑定计数、tombstone 和 manifest hash，异常进入 quarantine。
5. 在 fence 持有期间切换读消费者，再原子切换写路由到新 Capability/表；执行一次 fence-window 增量检查，期望 delta 为零。
6. 开放新写，旧表进入只读兼容。开放后禁止回退到旧写路径，只能前滚修复并保留 operation ledger；开放前可撤销新读路由并释放 fence。

迁移测试覆盖空库、真实样本、重复运行、断点恢复、冲突项目、缺 project、计数/hash 不符、OceanBase DDL、fence 前并发写、fence 后拒绝写、in-flight drain、切换瞬间请求和零丢失写入。测试必须注入“preliminary high-water 后、fence 生效前提交”和“fence 前已获 lease、fence 后才提交”两类写；验收必须证明它们进入 final high-water 及新 membership/hash，或获得明确失败 outcome。每个 fence 后新请求必须明确拒绝或只落新表，不存在成功但未迁移的窗口。

## 13. Capability 边界

本节 ID 均为 `not_registered` 设计候选，除非 G0 从真实 Registry 证明已有等价能力。不得将候选称为 experimental 或直接加入产品 release。每个能力实施前必须由 owner 完成 definition、Descriptor、Provider、Schema、selector、confirmation、幂等、审计、consumer contract、测试、真实 capability version GID 和 lifecycle 决策。

| 候选精确 ID | 闭合输入/输出 | 权限、事务、审计与消费者 |
|---|---|---|
| `craft.bop.repository.search@1` | project/filter/cursor/page size → authorized repository summaries | 项目权限；只读稳定分页；Desktop/Agent |
| `craft.bop.repository.get@1` | repository selector → metadata、team space、head/baseline refs | 项目读权限；只读分页；Desktop/Agent |
| `craft.bop.repository.create@1` | target project、metadata、expected empty slot、idempotency → repository/team space/initial head | 当前项目管理/创建权限；guard 锁内 Craft 单事务；Desktop；Project ref 校验失败不留部分 root |
| `craft.bop.space.search@1` | repository/type/owner/cursor/page size → authorized spaces | team 项目权限；personal 仅 owner；Desktop/Agent |
| `craft.bop.space.get@1` | space selector + projection page → head、nodes、VPPS group refs | team 项目权限或 personal owner；只读；Desktop/Agent |
| `craft.bop.space_version.get@1` | version + projection page → immutable space manifest、source refs/hash | 来源权限；只读；Desktop/Agent |
| `craft.bop.space_version.search@1` | space/cursor/page size/kind → immutable version summaries | space 权限；只读；Desktop/Agent |
| `craft.bop.space_version.save@1` | space、expected head、source refs、idempotency → immutable version/manifest/hash | team 项目管理或 personal owner；Artifact+Craft saga；Desktop/Task Tool |
| `craft.bop.space_version.freeze@1` | team space、expected head、source refs、idempotency → frozen version/frozen pointer | 项目管理者；Artifact+Craft saga；Desktop；冻结版本不可写 |
| `craft.bop.repository_baseline.set@1` | repository、space version、expected repository row、idempotency → baseline pointer | 项目管理者；单库 CAS；Desktop；版本内容不变 |
| `craft.bop.repository.fork.preview@1` | source immutable version、target project、fork_depth、`include_personal_migration`、可选 source personal space、expected target slot、limits、idempotency → preview/workflow GID、owner portability outcomes、allowed decisions、plan/input hash、expiry/evidence | 同租户；来源 read + fork/export + 目标项目管理；逐 owner 再分发校验；只读持久化 plan；Desktop 不能提交 owner verdict |
| `craft.bop.repository.fork.apply@1` | preview GID、plan hash、allowed decisions、expected target slot、receipt/idempotency → repository/team space/fork run、可选 personal child outcome、copied/unresolved/redacted evidence | 复验 preview 未过期、授权/verdict/target slot 未漂移；guard 锁创建，跨 Artifact 用 saga；Desktop |
| `craft.bop.repository.archive@1` | repository、expected row、idempotency → archived_at/row version | 当前项目管理者；guard 锁拒绝 active run；Desktop；不改变不可变版本 |
| `craft.bop.repository.restore@1` | repository、expected row、idempotency → archived_at=null/row version | 当前项目管理者；guard 锁与唯一性校验；Desktop |
| `craft.bop.repository.delete@1` | repository、expected row、reason、idempotency → deletion GID/time/保留引用摘要 | 当前项目删除权限；tombstone、legal hold/run guard；不级联 Project/Knowledge/Simulation/Artifact/任务/问题 |
| `craft.bop.managed_personal_space.fork.preview@1` | source immutable team version、target repository、可选本人 source personal space、可选 existing workflow GID、expected personal slot、limits、idempotency → preview、Provider-created/resolved workflow GID、personal Diff/portability plan、hash、expiry | 仅当前 actor；workflow 缺省时 Provider 创建，传入时只接受 repository Fork workflow 的固定 personal child；Provider 解析共同 base，拒绝跨 owner 拼接；跨 Repository 引用逐 owner 校验；Desktop |
| `craft.bop.managed_personal_space.fork.apply@1` | preview、plan hash、allowed decisions、expected personal slot、workflow/step receipt、idempotency → personal space/fork-base/step outcome | 复验 preview、来源权限和目标空槽；guard 锁；可作为 Repository Fork workflow 的第二 child step 幂等重试；Desktop |
| `craft.bop.managed_personal_space.delete@1` | personal space、expected row、idempotency → tombstone/保留提案摘要 | 当前 owner；有未收敛提案或 run 时拒绝；Desktop；团队不受影响 |
| `craft.bop.managed_personal_space.sync.preview@1` | personal space、expected personal/team heads、limits → 服务端解析的 Base/Ours/Theirs Diff/conflicts/input hash | owner；拒绝跨 repository/owner version；只读任务；Desktop/Agent；记录算法版本 |
| `craft.bop.managed_personal_space.sync.apply@1` | preview ref、selected units、expected heads、idempotency → new personal head/unit outcomes | owner；单库 CAS；Desktop；依赖闭包与 before/after audit |
| `simulation.environment.workspace.fork.preview@1` | source immutable version、target metadata、expected target state、limits、idempotency → preview、portability plan/hash/expiry | 来源读 + fork/export；逐 owner 校验外部 refs；只读持久化 plan；Desktop；数量不限 |
| `simulation.environment.workspace.fork.apply@1` | preview、plan hash、allowed decisions、expected target state、receipt/idempotency → private workspace/fork-base | 复验 preview/授权/verdict；Simulation saga；Desktop；数量不限 |
| `simulation.environment.workspace_version.get@1` | workspace/version selector、projection limits → immutable manifest metadata/content hash/source refs | workspace owner；只读、有界；Desktop/Agent |
| `simulation.environment.workspace_version.export_for_import@1` | workspace/version selector、target personal space/repository、consumer Capability ID/major、expiry ceiling、idempotency → opaque export ref、content hash、signed scope、expiry | workspace owner；签名绑定可信 caller actor/tenant、精确目标、consumer、source/hash/expiry；只允许已保存 immutable version；不能导出 drifting head 或信任 Renderer manifest |
| `simulation.environment.workspace.delete@1` | private workspace、expected row、idempotency → tombstone/保留引用摘要 | 当前 owner；guard 锁；Desktop；既有 Fork 和 Artifact refs 保持 |
| `simulation.environment.vpps_group.get@1` | private workspace/group/version → ordered group/version | workspace owner；只读分页；Desktop/Agent Tool |
| `simulation.environment.vpps_group.initial.generate@1` | private workspace/reference version/policy/idempotency → generated_initial/candidates/confidence | owner policy/delegation；Simulation+Artifact saga；Task Tool/scheduler |
| `simulation.environment.vpps_group.adjustment.create@1` | private group/base/ordered ops/reason/evidence/expected current/idempotency → adjustment version | owner 或有效 Agent/system delegation；Simulation CAS；Desktop/Agent Tool |
| `simulation.environment.vpps_group.current.set@1` | private group/version/expected current/idempotency → current pointer/row version | owner 或有效 Agent/system delegation；Simulation CAS；Desktop/Agent Tool |
| `craft.bop.managed_personal_space.import.preview@1` | Simulation opaque export ref、personal space、expected personal head、limits → typed Diff/conflicts、input hash、expiry | personal owner；经 Gateway 调用 Simulation 复验 caller/tenant/target/consumer ID-major/source/hash/expiry/immutable；Craft 不接受 Renderer manifest/base/head；Desktop/Agent |
| `craft.bop.managed_personal_space.import.apply@1` | preview ref、selected units、expected personal head、idempotency → new head/unit outcomes | personal owner；复验 preview 及 export 的 caller/tenant/target/consumer/source/hash/expiry 未漂移；Craft 单库 CAS；Desktop |
| `craft.bop.fork_run.get@1` | fork run selector → bounded status/plan/evidence/errors | 发起人或目标项目权限；只读；Desktop/scheduler |
| `craft.bop.vpps_group.initial.generate@1` | fork run/reference group/target project/policy/idempotency → generated_initial version/candidates/confidence | Task Tool/scheduler delegation；Artifact + Craft saga；不推进 team current；记录模型、Tool、Catalog、hash |
| `craft.bop.vpps_group.adjustment.create@1` | group/base version/ordered operations/reason/evidence/expected current/idempotency → immutable adjustment version | team 项目管理候选或 personal owner/Agent delegation；CAS；Desktop/Agent Tool |
| `craft.bop.vpps_group.current.set@1` | group/version/expected current/idempotency → current pointer/row version | team 仅项目管理者；personal 可由 owner/明确 Agent delegation；单库 CAS；审计决定主体 |
| `craft.bop.change_proposal.create@1` | personal space/selected units/expected heads/idempotency → draft proposal、服务端解析的 Diff hash、显式 closure graph/required units | personal owner；Provider 解析 personal version/team base；单库事务；Desktop；固定输入版本 |
| `craft.bop.change_proposal.submit@1` | draft/expected proposal version/idempotency → submitted proposal | personal owner；CAS；Desktop；提交后内容不可原地改 |
| `craft.bop.change_proposal.get@1` | proposal/projection page → status、units、conflicts、outcomes | owner、项目评审者；只读；Desktop/Agent |
| `craft.bop.change_proposal.review@1` | proposal/每个完整 closure component 的决定/expected team+proposal versions/idempotency → review status、accepted components | 当前项目管理者；禁止接受不完整闭包；CAS；Desktop；记录逐项理由和依赖诊断 |
| `craft.bop.change_proposal.apply@1` | reviewed proposal/accepted closure component/expected team head/idempotency → new team head/component outcome refs | 项目管理者或其显式调度任务；每个依赖连通分量一个 Craft 单事务/CAS；不重放已完成分量 |
| `craft.bop.change_proposal.cancel@1` | draft proposal/expected version/idempotency → cancelled | personal owner；仅 draft；单库 CAS；Desktop |
| `craft.bop.change_proposal.withdraw@1` | un-applied submitted proposal/expected version/idempotency → withdrawn | personal owner；单库 CAS；Desktop |
| `craft.bop.change_proposal.supersede@1` | old proposal/new proposal/expected versions/idempotency → superseded link | personal owner + 项目可见；保留旧 applied outcome；Desktop |
| `craft.bop.repository_diff.start@1` | left/right/base refs、algorithm、limits、idempotency → Diff run/input hash | 两侧读取权；只读任务；Desktop/Agent |
| `craft.bop.repository_diff.get@1` | Diff run/cursor/page size → BOP+VPPS typed results/next cursor/result hash | 调用者读取权；只读分页；Desktop/Agent |
| `craft.bop.operation.get@1` | operation/correlation selector → fork/proposal/import state、owner outcomes、errors | 相关资源权限；只读；Desktop/scheduler |
| `craft.bop.operation.reconcile@1` | operation、expected state、idempotency → deterministic terminal/reconciling result | scheduler 或授权用户；只根据已完成 owner outcome 收敛，不盲目重放 |
| `craft.bop.fork_workflow.get@1` | workflow correlation GID → team fork 与 personal migration 两步状态 | 发起人/目标项目权限；只读；Desktop/scheduler；支持第二步幂等重试 |

每个 ID 只表达一个 effect。所有写入都使用服务端资源 selector、expected version、稳定 operation GID 和幂等键；读取有 cursor、page size、max nodes/depth 和字段裁剪。现有 Craft draft preview/apply 只能在合同足以表达依赖闭包、原子应用和 outcome 时复用；不得把新 Repository 语义静默塞入旧 @1。Simulation 不直接写 Craft 表，Task Tool 和 Agent 也只能调用 pinned Catalog Release 中明确 exposure 的能力。

Simulation、任务和问题的 impact read Capability ID 由各 owner 在 G0 决定；它们是跨域影响分析进入实现的 blocker，不能由 Craft 命名或代实现。`base.project.search@1` 继续提供项目候选，但不作为写授权；G0 必须绑定 Project Management owner 的项目 get/authorize 合同，若不存在则由该 owner 新增候选。Repository create/fork 在获得服务端授权结果前不得写入。

## 14. Agent 与自动化

Agent 使用 Task Tool 编排确定性 Capability。模型可以解释 Diff、建议 VPPS 匹配、生成 adjustment 内容和风险摘要；Provider 决定 Schema、权限、依赖、幂等和是否可推进 current pointer。

当前 Agent 运行时只能从 pinned Catalog Release 将 `exposure.agent=true` 的精确 Capability 1:1 投影为工具；现有 Task Tool registry 没有 BOP Repository/Fork/VPPS/提案编排工具，现有系统工程 Skill 也不提供该业务流程。因此这部分属于待治理的新能力，不能调用 legacy 手写 `tool_registry.py` 或假设工具已经存在。

新增一个由 Agent Platform owner 管理、登记在 Task Tool registry 的 `task.bop_repository_assistant`。输入只接受 container ref、task kind、policy/delegation ref、expected version、limits 和 correlation；输出为有界的 outcome refs、候选摘要、稳定错误和实际 Capability outcomes，不返回完整 PLMXML/BOP 大树。失败语义至少包括 profile unavailable、delegation expired/revoked、catalog mismatch、limit exceeded 和 downstream outcome unknown。

第一阶段只注册两个固定 profile：`craft_repository` 调用第 13 节 Craft ID/major，`simulation_private_environment` 调用 Simulation 私人环境 ID/major。Tool 用显式 container kind 选择 profile，不按名称猜测，不实现动态 DSL。配套薄 Skill 只说明何时调用、如何解释结果和何时交给项目管理者；权限、状态转换和写入仍由 Provider 决定。

三类 actor 必须区分：user actor 来自交互身份；agent service actor 来自 Agent runtime；deterministic system actor 来自固定 scheduler/service identity。Agent 与 system 自动推进都需要 owner policy/delegation，固定空间、actor、允许的 Capability ID/major、策略 hash、Catalog Release、有效期和撤销状态。团队空间中的 Agent/system 只能产生 candidate，不能推进 current、接受提案或写正式 BOP。

每次生成记录输入 version/hash、模型和 Tool 版本、候选、置信度、调整原因、Capability outcome 和审计引用。自动化不得覆盖 reference 或历史 group version。

## 15. 稳定失败与恢复

至少定义：`target_repository_exists`、`managed_personal_space_exists`、`source_version_not_immutable`、`source_reference_denied`、`fork_export_denied`、`cross_tenant_fork_denied`、`source_not_portable`、`fork_depth_invalid`、`fork_preview_expired`、`fork_plan_changed`、`private_export_invalid`、`private_export_expired`、`vpps_group_generation_failed`、`team_head_advanced`、`proposal_conflict`、`proposal_state_invalid`、`dependency_closure_not_accepted`、`proposal_not_withdrawable`、`repository_children_active`、`lineage_resolution_failed`、`resource_version_conflict`、`project_permission_denied`、`active_run_exists`、`migration_write_fenced`、`reconciliation_required`。

核心 Fork 失败不能发布部分 Repository；generated_initial 失败允许独立重试。Craft 写入成功而投影或提案记录失败时，以 Craft outcome 为权威，进入 reconciliation，不盲目重放。所有重试使用稳定 operation GID 和幂等键。

## 16. 验收场景

1. 同一 Project Management 权威项目不能创建两个有效 BOP Repository，也不能有两个团队空间。
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
19. 团队节点进入个人空间复用 node GID；个人新增节点接受到团队后保留 GID；跨 Repository Fork 生成新 GID 并继承 lineage。
20. 团队与两个个人空间可同时拥有同一 group lineage 的不同 group/current pointer，互不覆盖。
21. 私人环境 VPPS 初版、adjustment 和 current 全部通过 Simulation Capability，Task Tool 按 container profile 路由。
22. 空白 Repository 能显式创建；所有团队/个人 Fork 来源均由受治理 space-version save/freeze 产生。
23. 提案 required closure 在评审前完整展示；未明确接受完整连通分量时无法应用，分量失败不产生半个 BOP 变更。
24. review/apply 状态独立；draft cancel、未应用 submitted withdraw、已有应用结果 supersede 均保留正确审计。
25. Craft Diff 不包含任务、问题或 Simulation 入向数据；Task Tool 只通过各 owner impact read 汇总。
26. 只有 read 无 fork/export 权时跨项目 Fork 被拒绝；跨租户拒绝；unresolved/redacted 引用必须在 plan 中明确接受。
27. Repository 有个人空间、未终结提案、active run 或 reconciliation 时拒绝删除；新 Repository 不复用旧 root 的子对象。
28. 0011 私人环境保留原 GID，旧 publish 表冻结；Craft BOP 回填按 project 对账，冲突或缺 project 进入 quarantine，切换期无双写。
29. VPPS sibling 并发写使用 current CAS；rebalance 不改变 canonical semantic order hash。
30. 团队+个人联合 Fork 通过 workflow correlation 查询部分成功，并可幂等重试个人步骤。
31. 同一 logical node 在 team/personal head 可指向不同 immutable revision；空间删除只产生该空间 tombstone，其他空间和历史 version membership 不变。
32. 旧 entry/link 回填生成可对账的 node/binding identity、revision 和 membership；歧义 lineage 被 quarantine，不按名称合并。
33. Fork Preview 固定 plan hash、owner verdict 和 expiry；伪造 verdict、过期 plan、授权/目标槽位漂移均令 Apply 失败且不创建部分 Repository。
34. 私人导入只接受 Simulation 为已保存 immutable version 签发的 export ref；Renderer manifest、漂移 head、过期或 hash 不符均被拒绝。
35. proposal 状态只出现允许组合；`partially_applied` 非终态，所有 accepted 分量完成后收敛为 `applied`，accepted 后不能 withdraw。
36. VPPS 根成员使用非空 root scope，同父 scope 顺序唯一；多个目标 group 从同一 reference 生成初版时不会误复用 operation。
37. preliminary high-water 后至 fence 生效前的写，以及 fence 前获 lease、fence 后完成的写，全部纳入 drain 后的 final high-water 和新 hash/membership；fence 后新请求明确拒绝或只写新表，切换窗口零丢失且无业务双写。
38. Repository baseline 只能指向本 Repository team space 的 immutable version；freeze pointer 只属于 team space。
39. 已有 Repository 且当前用户没有个人空间时，独立 personal Fork Preview 由 Provider 创建 workflow；客户端无需也不能伪造持久 workflow GID。
40. 私人 export ref 绑定 caller、tenant、精确 personal/repository target、consumer Capability ID/major、source hash 和 expiry，任何维度变化均拒绝。

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
