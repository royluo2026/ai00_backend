# 仿真环境协作、Fork 与版本差异设计

**日期：** 2026-09-09
**状态：** 已按深度评审修订，等待复审
**基础设计：** `docs/superpowers/specs/2026-09-08-digital-simulation-environment-redesign.md`

## 1. 设计结论

仿真评审分为节点评审和零散评审。节点评审围绕一个主项目的在线活动 BOP 协作，不引入 pull、push、merge、rebase 或工程师日常分支。零散评审使用轻量的私人或共享环境，可以从空环境或一个可读的不可变版本 Fork。

Git 只作为 Fork 和结构化 Diff 的概念参考。业务数据继续使用 OceanBase/MySQL、雪花 GID、不可变 Artifact、Capability Gateway 和领域 Provider，不使用 Git 软件，也不建设通用版本 DAG 或合并引擎。

## 2. 核心对象与状态

### 2.1 节点评审主环境

项目主环境 `workspace_kind=project_main`、`visibility=project`。它引用 Craft 当前可变 draft/head，并保存 VM 实例、姿态、截图和 VisMockup 映射等 Simulation 扩展。

- 主项目必填且唯一，参考项目可多选。
- 项目管理者可编辑全部区域；工程师只能编辑获授权线体。
- BOP 结构、Load/Operate 和资源需求由 Craft 拥有，必须调用 Craft Capability；Simulation 不复制 Craft 操作历史，只保存自己的扩展历史和 Craft operation/audit/checkpoint 引用。
- 项目主环境不保存“尚待发布到 BOP”的临时 BOP 结构。每次结构编辑直接落到 Craft 当前可变 draft/head；稳定、基线或 released BOP 永远不可写。
- Simulation 扩展写入失败时，Craft 已成功的业务结果仍是权威结果；操作进入待投影/对账，不能向用户伪报整体成功或盲目重试 Craft 写入。

同一项目最多存在一个未删除且 `workspace_lifecycle=active` 的主环境；归档的 active main 仍占用槽位。冻结后如需继续协作，由项目管理者从 `final_freeze` 版本创建后继主环境；旧环境保持 frozen，可归档，新环境取得活动主环境槽位。

### 2.2 零散评审环境

零散环境 `workspace_kind=ad_hoc`，创建和 Fork 后一律默认为 `visibility=private`：

- 私人环境仅 owner 可读、使用、修改、归档和删除。
- owner 可通过独立的 Share 操作将其变为共享；共享环境进入同租户共享池。
- 共享环境可被获准用户读取、比较、Fork，并可物化到调用者自己的本地会话；仍只有 owner 可修改、取消共享、归档和删除。
- 共享环境不设置维护者、审批人或合并流程，不会自动影响项目主环境。
- 私人和共享环境可保存 BOP 引用及 Simulation overlay；overlay 不能写回项目主环境。

### 2.3 正交状态模型

环境的不同性质不得塞进一个枚举：

| 维度 | 值与含义 |
|---|---|
| `workspace_kind` | `project_main` / `ad_hoc` |
| `visibility` | `project` / `private` / `shared`；project_main 固定为 project |
| `workspace_lifecycle` | `active` / `frozen` |
| `archived_at/by` | 与生命周期正交；归档前的 active/frozen 不变，恢复只清空归档字段 |
| `deleted_at/by/deletion_gid/reason` | tombstone；与前述字段正交，默认查询排除 |
| `row_version` | 可变 head 的 CAS 版本，不是业务版本 |

不可变版本另有 `version_kind`：`manual`、`baseline`、`fork_base`、`final_freeze`、`agent_auto`。环境通过 `baseline_version_gid` 和 `frozen_version_gid` 指向对应版本；建立或更换基线不改变生命周期。

| 动作 | 前置 | 结果 |
|---|---|---|
| 保存版本 | active、未删除 | 创建 immutable manual version，head 仍 active |
| 设置基线 | active、未删除 | 创建或选择 baseline version，更新 pointer，head 仍 active |
| 冻结 | active、未删除、无阻塞运行 | 创建 final_freeze，设置 frozen pointer，生命周期变为 frozen |
| 归档 | active/frozen、未删除、无活动 run lease | 在 workspace guard/行锁内设置 archived_at，生命周期不变并禁止新 lease |
| 恢复 | 已归档、未删除 | 清空 archived_at，恢复原 active/frozen 生命周期 |
| 删除 | active/frozen、可归档、无阻塞运行 | 写 tombstone，禁止后续编辑、使用、Fork、版本和 Connector 运行 |

## 3. 新建与编辑字段

| 字段 | 规则 |
|---|---|
| 环境名称 | 必填，可由有权用户编辑 |
| 评审类型 | `node_review` 或 `ad_hoc_review` |
| 主项目 | 节点评审必填且一个；零散评审可空 |
| 参考项目 | 可多选；通过 Project owner Capability 按名称或编码模糊搜索 |
| 版本标签 | 用户填写；不替代内部 version GID |
| 生命周期 | 活动/冻结；基线、归档和删除使用独立动作表达 |
| 可见范围 | 主环境固定项目可见；零散环境创建/Fork 后固定私人，再独立共享 |
| 更新时间 | 数据库自动生成，客户端只读 |

`visibility`、owner、workspace kind、主项目和生命周期不得通过通用 metadata patch 修改。Simulation 保存项目 GID、显示名称快照、角色和排序，不直查 Project 表。

## 4. Craft 在线协作与门槛

### 4.1 当前可保证行为

当前 `craft.bop.draft.change.preview/apply@1` 使用整个 BOP 的 `expected_revision`；现有 checkpoint 契约不足以证明完整线体恢复和双线体原子移动。因此，在 `G-Craft-Collab` 通过前：

- 所有主环境结构编辑继续使用整 BOP CAS；
- revision 冲突时保留视点和用户意图，刷新受影响投影后重试；
- 不承诺不同线体修改永不阻塞；
- 跨线体移动使用 Craft 当前可证明的原子合同，否则阻止操作。

### 4.2 目标行为与 G-Craft-Collab

不同线体独立保存只能在 Craft owner 提供并验证以下合同后启用：线体范围服务端授权；线体 revision 或已证明安全的可交换 rebase；包含节点、关系、顺序和引用的完整 checkpoint；来源与目标两线体原子移动；幂等 outcome、审计和恢复测试。通过后，UI 才可声明线体修改独立。

普通跨域编辑使用 operation ledger，至少记录 correlation GID、idempotency key、Craft request/result/audit ref、Simulation expected row_version、投影状态和对账结果。Craft 成功而 Simulation 失败时状态为 `projection_pending`，由确定性 reconciliation 修复。

## 5. 跨域项目版本锚点

canonical manifest 使用 owner/source 列表，只固定当前环境实际存在的来源。`project_main` 必须包含 Craft immutable snapshot；`ad_hoc` 的 Craft source 可选，允许空白环境和纯 VM 环境保存版本。

存在 Craft 等跨域来源时，复合版本锚点由 Simulation 拥有，命名为 `environment_anchor`，不冒充 Project Management 的正式项目版本。它只关联各 owner 已生成的不可变引用，不宣称跨域数据库事务。纯 Simulation 版本直接使用 Artifact + Simulation saga，不创建空的跨域锚点。

创建锚点使用可对账 saga：

1. 固定预期 Craft version/revision/content hash 和 Simulation head row_version；
2. 通过 Craft Capability 获取不可变 BOP snapshot ref；
3. 生成 Simulation canonical manifest Artifact；
4. 重新校验两侧 revision/hash/权限；
5. 所有引用及 hash 完整后将锚点从 `preparing` 置为 `ready`。

失败进入 `failed` 或 `reconciling`；只有 `ready` 可显示为成功并用于基线、冻结、Fork 或可复现运行。不得把 Craft、Simulation 与 Artifact 描述为一个事务。

## 6. Fork、共享与引用权限

Fork 只复制，不同时扩大可见性：

1. 来源为已保存版本时复用原 immutable Artifact/ref，不重复复制字节。
2. 来源为活动环境时先建立 immutable `fork_base`；只有实际包含 Craft source 时才通过第 5 节 saga 建立 ready anchor，空白或纯 VM 环境走 Artifact + Simulation saga。
3. 使用最近一次已持久化 VM snapshot，不读取其他工作站未同步状态。
4. 新 workspace/node/binding/version 生成新 GID；继承根 `lineage_gid`，无来源的新实体以自身 GID 作为 lineage。
5. 新环境固定 private；需要共享时另行调用 Share。
6. 来源后续变化不会进入 Fork，Fork 不回写来源。

Share 必须逐项验证 owner 对 Project、Craft、Digital Model、Artifact 和 Teamcenter 引用的再分发权限、数据分级及租户范围。缺少权限时拒绝，或由明确合同生成受控脱敏快照。共享读取不能绕过底层来源和 Artifact 策略。Unshare 只阻止新的共享访问，不破坏已合法创建的 Fork。

“使用共享环境”严格限于读取树/版本/Diff、Fork，以及在调用者自己的本地 session/run 中 materialize、capture；这些运行及 Artifact 归调用者范围，不得写入共享 workspace。

## 7. 版本、Canonical Manifest 与 Diff

每个不可变版本固定：

- workspace 元数据、项目引用、node/binding GID 与 lineage GID；
- 每个来源实体的 owner、GID、revision；
- 精确 Craft immutable snapshot ArtifactRef、content hash 和 `capability_version_gid`；
- VM document/snapshot GID、PLMXML ArtifactRef、模型版本、BOM 行、`catiaOccurrenceName` 和父路径；
- occurrence GID、predecessor、原始/规范化变换；
- 坐标系、长度/角度单位、handedness、矩阵布局/乘法约定、规范化算法及版本；
- identity matching 和 Diff 算法版本。

支持当前 head 对最近版本/基线、Fork 对 fork-base、任意两版本比较。Diff 至少覆盖 BOP 结构和绑定、VM 模型版本、BOM 行、`catiaOccurrenceName`、父路径、坐标和姿态。零件同 BOM 行和 lineage 下的位姿变化视为移动；工具、设备、工装和套筒允许同数模号多实例。

大型 Diff 使用后台任务与分页结果，绑定左右 version GID、输入 hash 和算法版本。版本内容永远不变；推荐标签、说明等可变建议存独立 annotation，不进入 manifest hash。

## 8. 删除、归档与保留

Archive 可恢复；Delete 是 owner 发起的逻辑删除；Purge/GC 是独立的特权后台动作，第一阶段不实现物理清理。

- private/shared 由当前 owner 删除。shared 删除前停止发放新 lease，并展示影响摘要。
- project_main 由当前项目管理/删除权限主体删除 Simulation 扩展；创建者若已失去项目管理权无权删除。删除不触碰 Craft BOP 或 Project，并释放有效主环境槽位。
- frozen/archived 可以删除，但不改写历史内容。
- Archive/Delete 与 capture/materialize/snapshot/comparison/reconciliation 的 run-lease 获取必须在同一 workspace guard/行锁上串行化。有活动 lease 时返回 `active_run_exists`；写入 archived_at 或 tombstone 后拒绝新 lease，消除“先检查、后启动”的竞争。
- Delete 还需处理 `legal_hold`、`resource_version_conflict`、`resource_denied` 和 `already_deleted`。
- 删除后禁止编辑、使用、Fork、保存版本和 Connector run；现有 Fork 继续依赖自身 fork-base/ArtifactRef 使用。
- tombstone、audit 和最小 lineage metadata 永久保留。version payload、Artifact、baseline、fork-base、final-freeze、Diff 和 anchor 受 retention、reference graph 与 legal hold 约束；第一阶段不 purge。源引用可指向 tombstone，并保留源 GID、lineage、hash、deleted time 和 audit。
- 不得级联删除 Craft、Project、Digital Model、Knowledge、Base Artifact、VisMockup 文档或进程。
- 将来 GC 必须确认无 version/Fork/capture/comparison/anchor 引用、保留期已满且无法律保留；Renderer、owner 和 Agent 均不能直接 purge。

## 9. 权限矩阵

| 对象/动作 | 读取和使用 | 修改 | 归档/恢复 | 删除 |
|---|---|---|---|---|
| private ad_hoc | owner | owner | owner | owner |
| shared ad_hoc | 同租户且底层引用授权通过 | owner | owner | owner |
| project_main | 项目读权限 | 管理者全局；工程师在 Craft 合同允许范围内 | 当前项目管理者 | 当前项目管理/删除权限主体，仅 Simulation 扩展 |
| frozen workspace | 按环境和引用策略 | 无内容修改；独立 version annotation 按策略 | 按 workspace 规则 | 只 tombstone workspace，版本本身无 delete |

所有权限由 Gateway/Provider 使用可信 InvocationContext 和服务端资源解析判定。Renderer 不提交 tenant、owner 或预计算授权结论。Agent 不能删除、冻结、改 visibility/owner 或完成业务审批。

## 10. 数据模型与迁移

使用新增 `0012` 迁移，不修改已经执行的 `0011_simulation_workspaces.sql`：

| 表/变更 | 内容 |
|---|---|
| `workmanship_sim_workspaces` | kind、visibility、lifecycle、row_version、baseline/frozen pointer、archive/delete tombstone |
| `workmanship_sim_workspace_projects` | 主/参考项目、名称快照、顺序 |
| `workmanship_sim_workspace_versions` | version_kind、父版本、lineage、canonical manifest/hash、source refs |
| `workmanship_sim_environment_anchors` | Craft snapshot + Simulation manifest 复合锚点及 saga 状态 |
| `workmanship_sim_main_projection_operations` | 跨域 operation/correlation/idempotency ledger 与 reconciliation |
| `workmanship_sim_environment_version_comparisons` | Diff 任务、算法、输入和结果 ArtifactRef |
| `workmanship_sim_version_annotations` | 不进入 content hash 的标签、摘要和推荐信息 |
| `workmanship_sim_version_policies/delegations` | 确定性策略、owner 授权和 Agent 范围 |

现有行回填为 `workspace_kind=ad_hoc`、`visibility=private`、`workspace_lifecycle=active`，保留原 owner 和 GID。OceanBase/MySQL 不依赖 partial unique index；使用 guard/lock 表或可验证的生成唯一键保证每项目一个未删除的 active main。Archived active main 继续占位，只有 frozen 或 deleted 环境释放 active 槽位。

`0011` 中的 publish plan/map/outbox 仅保留历史兼容读取：停止新增消费者和写入，不删除旧数据；后续单独迁移受控清理。项目主环境的新流程不产生 publish plan，ad_hoc overlay 也没有写回 BOP 的入口。无跨域外键和跨域 cascade，只保存 GID/ref/hash。

迁移验证必须覆盖前向迁移、回填、幂等重跑、失败后前滚/回滚策略及 OceanBase DDL；不得用修改历史迁移规避兼容问题。

## 11. 内置 Agent 版本管家

第一版只注册显式 Simulation profile，不建设动态 DSL，其他领域等出现第二个已批准需求后再抽取。

Simulation Provider 提供五个确定性策略能力：`simulation.environment.version_policy.enable@1`、`simulation.environment.version_policy.update@1`、`simulation.environment.version_policy.disable@1`、`simulation.environment.version_policy.get@1`、`simulation.environment.version_policy.evaluate@1`。evaluate 判断是否达到内容 hash、时间窗、变化阈值和频率上限；Task Tool `task.version_steward.evaluate` 只按结果编排，LLM 不决定“实质变更”。第一阶段不自动清理普通版本。

调用链为：scheduler/Agent 调用 Task Tool → Tool 通过固定 Catalog Release 调用 policy.evaluate → 若结果要求创建，再调用 version.save → 可选写入独立 annotation。label/summary 必须有长度和敏感信息裁剪上限，不参与内容 hash 或创建决策。

delegation 记录必须固定 workspace、owner grant、Agent service actor、允许的 Capability ID/major、policy hash、有效期/撤销和 Catalog Release。普通自动版本记录 Agent run、触发原因、policy version、input Diff hash 和实际 Capability outcome。

旧手写 `tool_registry.py` 不增加逻辑；Task Tool registry 当前没有该工具，必须按治理流程新增。Agent 可用工具只能从 pinned Catalog Release 中 `exposure.agent=true` 的 Capability 1:1 投影。

## 12. Capability 状态与边界

所有 ID 必须逐项注册，一个 ID 只表达一个原子效果。下表中的 `not_registered` 只是设计候选，不能称为 experimental，也不能被消费者调用。所有能力 owner 均为 Simulation、Provider 均为 Simulation Provider；消费者按表限定。confirmation 最终由 Descriptor 风险评审确定，读取能力默认 none，写入能力不得因“用户点了按钮”而绕过 Gateway receipt 规则。

| 精确 Capability ID | 当前状态 | 闭合合同摘要 |
|---|---|---|
| `simulation.environment.workspace.create@1` | experimental，需定义变更 | 输入 name/source refs/idempotency；输出 private ad_hoc workspace/head/row_version；source 可空；Desktop 消费；单库事务；验证跨租户、幂等与 schema；重建 definition hash 并迁移消费者 |
| `simulation.environment.workspace.search@1` | experimental，需定义变更 | 输入 filter/cursor/page_size；输出授权 summaries/next_cursor；Desktop/Agent 只读；默认排除 deleted；范围从 private 扩到 shared/project 且新增 Agent consumer，须重建 definition hash、审批证据并迁移消费者，是否升 major 由 G0 owner 判定 |
| `simulation.environment.workspace.get@1` | experimental，需定义变更 | 输入 workspace/projection page；输出 metadata/head/有界投影；Desktop/Agent 只读；范围从 private 扩到 shared/project 且新增 Agent consumer，须重建 definition hash、审批证据并迁移消费者，是否升 major 由 G0 owner 判定 |
| `simulation.environment.project_main.create@1` | not_registered | 输入 project/source Craft draft/ref projects/expected slot/idempotency；输出 main workspace/head；当前项目管理权限；guard 锁内单库创建；验证并发唯一、archived active 占位和 frozen/deleted 释放 |
| `simulation.environment.workspace.metadata.update@1` | not_registered | 输入 allowlisted patch/expected row/idempotency；输出 revision/row_version；Desktop；单库 CAS；禁止改 kind/visibility/owner/project/lifecycle；审计 before/after |
| `simulation.environment.workspace.share@1` | not_registered | 输入 workspace/expected row/idempotency；输出 shared visibility/row_version/引用授权摘要；owner；逐引用再分发校验或受控脱敏；验证拒绝与租户边界 |
| `simulation.environment.workspace.unshare@1` | not_registered | 输入 workspace/expected row/idempotency；输出 private visibility/row_version/现有 Fork 摘要；owner；单库 CAS；既有 Fork 不失效 |
| `simulation.environment.workspace.archive@1` | not_registered | 输入 workspace/expected row/idempotency；输出 archived_at/row_version；owner 或项目管理者；guard 锁内拒绝 active lease 并阻止新 lease；验证 active/frozen 生命周期保持 |
| `simulation.environment.workspace.restore@1` | not_registered | 输入 workspace/expected row/idempotency；输出 archived_at=null/原 lifecycle/row_version；原授权主体；guard 锁内 CAS；archived active main 原本已占槽位 |
| `simulation.environment.workspace.delete@1` | not_registered | 输入 workspace/expected row/idempotency；输出 deletion GID/deleted_at/保留引用摘要；owner 或项目删除权限；guard 锁内 tombstone；稳定错误和非级联测试见第 8 节 |
| `simulation.environment.workspace.version.save@1` | not_registered | 输入 workspace/expected row/source list/algorithm versions/idempotency；输出 version/manifest ArtifactRef/hash/可选 anchor；Desktop/Task Tool；Artifact+Simulation saga，只有存在跨域 source 才建 anchor |
| `simulation.environment.workspace.fork@1` | not_registered | 输入 source version 或 active workspace/expected source/idempotency；输出 private workspace/fork-base/lineage；授权读者；活动源先固定 fork-base；验证空白、纯 VM、Craft overlay 和源删除后可读 |
| `simulation.environment.version.freeze@1` | experimental，需定义变更 | 输入 workspace/expected row/source list/算法/idempotency；输出 final-freeze version/frozen pointer/row_version；owner 或项目管理者；新增 guard + Artifact saga；须重建 definition hash、审批证据并迁移消费者，是否升 major 由 G0 owner 判定 |
| `simulation.environment.version.get@1` | not_registered | 输入 version/projection page；输出 canonical metadata/source list/page；Desktop/Agent 只读；按版本和 Artifact 策略授权 |
| `simulation.environment.version.search@1` | not_registered | 输入 workspace/cursor/page_size；输出版本摘要；Desktop/Agent 只读；稳定排序，版本不因 workspace tombstone 消失 |
| `simulation.environment.version_compare.start@1` | not_registered | 输入 left/right/algorithm/max_nodes/idempotency；输出 comparison/input hash/status；读权限；创建 caller-scoped 任务；审计算法和输入 |
| `simulation.environment.version_compare.get@1` | not_registered | 输入 comparison/cursor/page_size；输出状态/摘要/分页差异/result hash；任务 owner 只读；验证移动、升版、新增、删除和限制 |
| `simulation.environment.baseline.set@1` | not_registered | 输入 workspace/version 或 snapshot request/expected row/idempotency；输出 baseline version/pointer/row_version；owner 或项目管理者；不改变 lifecycle；验证替换 pointer 和历史不变 |
| `simulation.environment.environment_anchor.create@1` | not_registered | 输入 workspace/version source set、Craft expected revision/hash、Simulation expected row/idempotency；kind=project_main 或 ad_hoc 实际含 Craft source；project_main 强制 Craft，ad_hoc 无 Craft 时禁止创建；输出 anchor GID/preparing state；Desktop/scheduler；启动第 5 节 saga |
| `simulation.environment.environment_anchor.get@1` | not_registered | 输入 anchor；输出 owner/source refs/hash/state；Desktop/Agent 只读；只有 ready 可作成功版本使用 |
| `simulation.environment.environment_anchor.reconcile@1` | not_registered | 输入 anchor/expected state/idempotency；输出 ready/failed/reconciling 和 evidence refs；scheduler/受权用户；重校验双方，不盲目重做写入 |
| `simulation.environment.main_projection_operation.get@1` | not_registered | 输入 operation；输出 Craft outcome ref/Simulation projection state/审计；Desktop/scheduler 只读；与 anchor 对账分离 |
| `simulation.environment.main_projection_operation.reconcile@1` | not_registered | 输入 operation/expected state/idempotency；输出确定终态/投影 row/audit；scheduler；只依据既有 Craft outcome 修复 Simulation 投影，不重放 Craft 写入 |
| `simulation.environment.version_policy.enable@1` | not_registered | 输入 workspace/policy/delegation/expected row/idempotency；输出 policy/version/hash；shared owner；单库事务；验证允许的 Capability major、Catalog release 和有效期 |
| `simulation.environment.version_policy.update@1` | not_registered | 输入 policy/expected policy version/patch/idempotency；输出新 policy version/hash；shared owner；CAS 与审计 |
| `simulation.environment.version_policy.disable@1` | not_registered | 输入 policy/expected version/idempotency；输出 disabled_at；shared owner；撤销 delegation，既有版本不变 |
| `simulation.environment.version_policy.get@1` | not_registered | 输入 workspace/policy；输出策略和 delegation 摘要；owner/Task Tool 只读，敏感字段裁剪 |
| `simulation.environment.version_policy.evaluate@1` | not_registered | 输入 policy/resource hash/diff summary/trigger；输出 deterministic create/skip 决定及原因；Task Tool 只读；相同输入同结果，LLM 不参与决定 |

现有 `simulation.environment.structure_node.create@1`、`simulation.environment.structure_node.move@1`、`simulation.environment.structure_node.remove@1`、`simulation.environment.binding.create@1`、`simulation.environment.binding.remove@1` 为 experimental。它们从 private workspace 扩展到 project_main 线体权限会改变 selector、授权和副作用合同，必须逐项做 Descriptor/Provider 差距判断、重建 definition hash、重新审批/生成证据并迁移消费者；治理规则要求不兼容升版时必须使用新 major。`simulation.environment.structure_node.reorder@1` 和 `simulation.environment.binding.update@1` 为 not_registered。Craft 线体协作能力仍是 `not_registered/owner decision required`，由 `G-Craft-Collab` 阻塞。旧 Simulation publish plan/map/outbox 能力标为 deprecated compatibility，禁止新消费者和新写入。

每项实现前还须在治理变更记录中补齐真实 `capability_version_gid`、完整 Schema（`additionalProperties=false` 和大小上限）、resource selector、confirmation、审计字段、迁移、consumer contract 与 acceptance tests。上表是设计输入，不是注册、稳定性或审批证据。

## 13. 验收场景

1. 状态维度可独立组合；baseline 不锁定 head，archive/restore 不改变 active/frozen。
2. freeze 创建 final-freeze；冻结主环境的后继取得唯一活动槽位。
3. G-Craft-Collab 未通过时使用整 BOP CAS，产品不宣称线体互不阻塞。
4. 复合锚点只有两侧 hash/ref 完整且复核成功后为 ready；任一失败可对账。
5. Fork 默认 private；Share 单独执行并验证全部引用的再分发权限。
6. 两个手动版本可比较 BOP、绑定、VM 版本、BOM 行、`catiaOccurrenceName`、坐标和姿态。
7. private/shared owner 可删除；非 owner 拒绝；project_main 按当前项目管理/删除权限。
8. expected version 冲突、活动运行、legal hold 阻止删除；重复请求幂等返回既有 tombstone。
9. 删除不级联其他领域，释放主环境槽位；删除源 workspace 后既有 Fork 仍可读。
10. 所有默认查询排除 deleted；审计查询可显式包含；archive 后仍可 delete。
11. Agent 只按 Provider 的确定性 evaluate 结果保存普通版本，不能删除、冻结、共享或审批。
12. 迁移在 OceanBase 前向、回填和幂等重跑通过；0011 历史数据保持可读。
13. 空白 ad_hoc、纯 VM ad_hoc 和带 Craft overlay 的 ad_hoc 均可保存版本及 Fork；只有第三类创建 environment anchor。
14. Archived active main 仍占唯一槽位；archive→create 被拒绝，restore 不会产生两个 active main；frozen 或 deleted 后可创建后继。
15. Archive/Delete 与 run-lease 并发时由同一 guard 串行化，不出现归档/删除后新增运行。
16. `projection_pending` 只能通过受治理的 main projection get/reconcile 能力对账，不重放 Craft 写入。

## 14. 明确不做

- 不使用 Git 软件、通用版本 DAG、pull、push、merge、rebase 或 PR。
- 不把 Simulation 描述为 Craft BOP 或 Project 正式版本的 owner。
- 不跨域直表、外键、级联删除或伪造跨域事务。
- 不让 ad_hoc overlay 写回项目主环境。
- 不让 Agent/LLM 决定版本创建、权限、冻结、删除或业务审批。
- 第一阶段不做物理 purge、自动版本清理或多域动态 profile DSL。
- 不修改 Teamcenter 数模链接，也不读取其他工作站未同步的 VisMockup 状态。
