# 组织管理人工维护树设计（test 基线修订版）

日期：2026-09-09  
状态：待指定 Codex 任务复审；复审通过前禁止业务实现  
实现基线：backend `test` (`3affc4e7c`)，web `test` (`f2818cca`)

## 1. 目标与范围

管理中心“组织管理”收敛为两棵只由超管维护的责任树：

1. 组织架构树列出现有组织，按 `parent_team_gid` 展示；不再从飞书同步整棵组织或成员。新增人员时才调用现有飞书人员搜索。
2. 项目责任树一次列出全部未删除项目，固定为“项目 → 项目经理 → 人工线体”。人工线体由超管命名、指定负责人，并可在 BOP 建立后映射到明确选择的 BOP 线体节点。
3. 映射使用 BOP entry GID，不按名称匹配。映射和负责人同时存在时，负责人自动获得该 BOP 线体的编辑权限。
4. 项目经理、人工线体名称、负责人和 BOP 映射均保留显式编辑、更换、清空或删除入口。
5. 保留单项目“责任矩阵”：只展示项目经理与人工线体负责人，不把普通项目成员混入该矩阵。

不在本次范围：组织拖拽或换父级、整树飞书同步、按名称自动匹配 BOP、自动迁移到新 BOP 版本、从现有 BOP/项目成员批量生成项目人工线体、普通项目成员 CRUD、跨项目总矩阵。

## 2. 已确认交互

### 2.1 组织树

- 飞书来源和手工来源的现有组织合并显示为一棵树；历史 `feishu_dept_id` 保留但不决定只读或分组。
- 超管可新增根/子组织、重命名、删除、加人、移人。项目经理或团队管理员不能写。
- 新增人员打开飞书搜索；选择结果后沿用 Base 的本地身份解析/创建流程。把已有人员加入另一组织等同于换组。
- 删除组织时若仍有直接子组织或成员，返回 `organization_not_empty`，页面提示先迁移或移除；不级联删除。
- 本期不修改父级。服务端仍校验父组织存在且未删除；渲染时用 visited 集合防循环，孤儿/循环节点进入“异常节点”分组，不让整树消失。
- 页面移除组织同步与成员同步按钮；兼容接口不能再成为绕过超管策略的可写入口。

### 2.2 项目责任树

- 服务端按游标分页返回项目；前端逐页加载后合并为一棵树，每次请求 `page_size <= 100`，避免无界响应。
- 项目下恰有一个项目经理槽位；人工线体均位于该槽位下。
- 项目经理支持设置、更换、清空。人工线体支持新增、重命名、设置/更换/清空负责人、映射/重映射/清空 BOP、删除。
- 人员选择只列 Base 中已注册的有效用户；新人员先在组织树通过飞书搜索加入组织，再进入项目责任选择器。
- BOP 选择器按游标读取当前项目 `status='active'` 的 BOP 版本，只显示未删除 `line_process` 节点，并显示“版本 / 祖先 / 线体”路径。
- 映射节点不存在、被删除、版本不再 active 或归属其他项目时，人工线体和负责人仍保留并标记 `stale`；只能由超管手工重映射或清空。
- 删除已投影的线体前说明会撤销“本人工线体来源”的授权；浏览器确认不替代 Gateway capability confirmation token。

### 2.3 单项目责任矩阵

- 选择一个项目后切换到“责任矩阵”。列为项目经理和该项目人工线体，行为这些槽位中出现的去重人员。
- 单元格只表示责任角色；线体列同时显示 `mapped`、`unmapped` 或 `stale`。
- 普通 `members.list` 结果不进入此矩阵，旧项目详情成员查看能力保持只读兼容。

## 3. 现有 test 基线与边界

- Web 组织页已通过 `AI00Business` / `ExistingCapabilityClient` 调用 Capability；不得改回直接 REST 写入。
- Project Management 已有 `project.project.read`、`project.project.change.apply`、`project.member.read`、`project.member.change.apply` 及其 atomic children、Provider、Descriptor、Catalog 与 Gateway 兼容适配器。
- Base 已有 `base.team.create/update/archive/member.add/member.remove@1`，但 v1 写权限语义仍允许非超管路径；本变更属于破坏性权限收紧。
- `backend/platform_sdk/project_access.py::replace_section_leads` 会按线体 GID 删除所有 grant/member，无法区分来源，禁止用于本功能。
- Craft 拥有 BOP 状态与节点；Project 不得直接查询 Craft 表来验证映射。Base 拥有用户、组织、项目成员和权限投影表。

## 4. 领域数据与并发

Project Management 在 `workmanship_proj_projects.meta.org_management` 保存配置真相：

```json
{
  "schema_version": 1,
  "revision": 7,
  "manager_user_gid": "user-gid-or-null",
  "lines": [
    {
      "gid": "stable-manual-line-gid",
      "name": "底盘线",
      "leader_user_gid": "user-gid-or-null",
      "bop_line_gid": "bop-entry-gid-or-null"
    }
  ]
}
```

规则：

- 缺少配置按 revision 0、空线体读取；不从 BOP 自动生成线体。现有项目经理可作为 `legacy` 只读回退显示，首次超管保存后由配置接管。
- 人工线体 GID 创建后稳定；名称 trim 后非空、同项目唯一；非空 BOP GID 同项目唯一；负责人必须是 Base 中有效用户。
- 所有写请求同时携带 body `expected_revision`、body `idempotency_key`，且 Gateway envelope 使用相同 idempotency key。revision 不匹配返回 `version_conflict`；同 key 不同 payload 返回 `idempotency_conflict`。
- POST 也必须幂等；重放返回同一人工线体/operation，不生成第二条。
- PATCH 只修改 `org_management`，保留其他 `meta` 键。`null` 表示清空，字段缺省表示不变。

Project Management 新增持久操作/投递箱表，原子保存：配置 CAS、操作记录、审计事件与待投影事件。操作状态为 `pending_projection | completed | failed_retryable | failed_terminal`，保存响应返回 `operation_gid`、新 revision 与状态。

## 5. 来源隔离的 Base 权限投影

Base 新增来源台账与投影状态表，不修改/清扫无来源历史数据：

- 来源键：`source_type='project_org_management' + source_gid`；经理来源使用项目配置固定 GID，线体来源使用人工线体 GID。
- 期望目标：`project_manager(project_gid,user_gid)` 或 `bop_line_leader(project_gid,bop_line_gid,user_gid)`。
- 每个 apply 带 `operation_gid`、`source_revision`、幂等键。旧 revision/重复 operation 不倒退状态；同 revision 不同 payload 冲突。
- Base 在同一事务内锁来源与目标，更新来源台账，再计算目标的有效引用数。
- 首次投影若目标有效 member/grant 已存在，将它标记为 `baseline_present` 并复用，不声称拥有；最后一个本功能来源移除时保留 baseline。
- 若目标由本投影创建，保存精确 effective row GID；仅当引用数归零且 `baseline_present=false` 时按该 GID 删除。绝不按 line GID 批量删 grant/member。
- 多个人工线体指向同一 `(user,bop_line)` 时使用引用计数；删除一个来源不会撤销另一个来源需要的权限。
- BOP 编辑权限的有效投影为 `section_lead` grant；项目经理有效投影为现有 project member。旧写入口退役后只有 Base 投影 Capability 可创建本功能来源。

Project 操作提交后通过 Gateway 调用 Base 投影 Capability。同步完成则操作变为 completed；失败保持 durable pending，由 worker/reconciliation 重试。UI 只有读取到 completed 才显示“保存成功”；pending 显示“正在同步权限”，terminal failure 显示可重试/修复，不回滚已经提交的配置或伪造原子跨库事务。

## 6. Capability、Provider、Catalog 与兼容策略

所有 ID/版本是本变更需要实现并由治理检查固定的契约：

### Project Management（owner）

- `project.org_management.read@1`
  - `.atomic.responsibility_tree_search`
  - `.atomic.responsibility_matrix_get`
  - `.atomic.operation_get`
- `project.org_management.change.apply@1`
  - `.atomic.manager_replace`
  - `.atomic.managed_line_create`
  - `.atomic.managed_line_update`
  - `.atomic.managed_line_delete`
  - `.atomic.projection_retry`

读 Capability 使用 `project.view`，但 Provider 对全量管理树额外验证服务器身份为 `super_admin`。写 Capability 使用 `system.user.manage`、`confirmation='user'`、required idempotency、expected revision、稳定错误；Provider 再执行 `_super`，不能仅靠前端隐藏。

### Craft（BOP owner）

- `craft.bop.active_line.search@1`：输入 `project_gid,cursor,page_size<=100`，仅返回 `status='active'` 且未删除的 `line_process` 与路径。
- `craft.bop.active_line.validate@1`：输入 `project_gid,bop_line_gid`，返回 active/归属/节点类型的封闭判定。

Project 通过受治理 domain capability client/Gateway 调用，禁止 Craft SQL 泄漏到 Project repository。

### Base（组织与授权 owner）

- 组织写 Capability 发布 breaking major v2：`base.team.create/update/archive/member.add/member.remove@2`，只允许超管；Web 消费者迁移到 v2。
- `base.project_responsibility.projection.apply@1` 与 `.get@1`：仅允许受信 Project Management provider 调用，承载来源台账与有效 grant/member 投影。用户发起的上游 Project 写必须带精确 Gateway confirmation token；内部重放携带已记录的 parent operation/confirmation evidence，不能由浏览器直接调用。

旧 `base.team.*@1` 写版本、`project.member.change.apply.atomic.members_line_assignment_replace@1` 和 `/line-assignment` 写适配器进入 deprecation/retirement 清单。所有已知 Web 消费者先迁移，再使旧 major 返回稳定 `capability_retired`；REST 只可作为同一 Gateway Capability 的兼容绑定，不能直调 router/SDK 绕过。项目详情保留矩阵/成员读取，旧线体写控件移除或引导到管理中心。

稳定错误至少包括：`permission_denied`、`confirmation_required`、`invalid_input`、`resource_not_found`、`organization_not_empty`、`version_conflict`、`idempotency_conflict`、`bop_line_inactive`、`bop_line_wrong_project`、`projection_pending`、`projection_failed`、`capability_retired`、`provider_unavailable`。

## 7. 组织不变量与审计

- create：父组织存在、active、同 tenant；禁止 self parent。update 本期只允许名称/active，不接受 parent 变更。
- archive：有未归档直接子组织或直接成员时拒绝；重复 archive 幂等。
- add member：目标组织存在且 active，人员有效；移动用户与审计同事务。remove 不删除用户身份。
- 每个权限改变操作由 Gateway confirmation 绑定到 capability id/version、actor、exact payload；浏览器 `confirm()` 只能是 UX 提示。
- 审计记录 actor、tenant、capability/version、resource GID、old/new revision、operation/idempotency、结果和错误码；不记录邮箱、飞书 open ID、搜索词或令牌。

## 8. 前端状态与失败语义

- 页面只使用 Capability client。读请求按 cursor 拉取；写请求生成一个稳定 key，先请求 confirmation token，再以同 payload/key 重试一次。
- 每个节点独立 busy，防重复提交；不乐观改本地树。completed 后按服务端返回或重读替换；pending 轮询 operation（退避、有上限）并保留编辑禁用状态。
- stale mapping 清晰显示原 GID/历史路径（若有），不猜名称；编辑按钮始终保留。
- 加载失败保留已渲染数据并提供重试。版本冲突重读节点并提示用户重新提交。

## 9. 发布、迁移与验收

- schema migration 新增 Project operation/outbox/audit 表和 Base source/effective projection 表，并同步 `domain_table_ownership.json`、`table_inventory.json`、迁移校验。
- 不删除既有组织、项目、用户、成员、grant、BOP 或历史飞书字段；不自动导入现有 BOP 线体。旧项目经理仅作 legacy 回退，人工保存后迁移到新来源。
- 发布顺序：表结构 → Craft/Base provider capability → Project capability/saga → Web 消费者 → 观测一轮 → retire 旧写 major/route。任一阶段可暂停；新 UI feature flag 可关闭，已提交操作由 reconciliation 继续收敛。
- 机器验收必须覆盖真实 repository transaction、CAS 并发、同/异 payload 幂等、来源引用计数、baseline 保留、投影重试、Craft active 校验、Gateway confirmation、Catalog/Descriptor/Provider 快照、REST compatibility、旧消费者迁移、前端 jsdom 与构建。
- `machine_passed`、`human_approved`、`runtime_verified` 分开报告；没有受信记录不得伪造。

## 10. 治理记录

- Change classification: breaking（组织与旧线体写权限收紧、旧 major 退役）+ additive（新责任配置与投影能力）。
- Owners: Project Management 持有项目责任配置/操作；Craft 持有 BOP 查询验证；Base 持有组织、身份、成员与授权投影。
- Consumers: 管理中心组织页为新写能力消费者；项目详情只保留读兼容。
- Sensitive data: 姓名、邮箱、头像、飞书身份仅用于选择展示，不进入 URL、幂等哈希明文或日志。
- 当前证据：以上基于两个 test commit 的静态检查；Snapshot GID、精确哈希人审与运行时验证仍为 unverified。

