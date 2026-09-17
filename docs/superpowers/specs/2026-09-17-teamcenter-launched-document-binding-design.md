# Teamcenter 在线文档可信绑定与即时内嵌设计

## 背景

AI00 已能从仿真环境的 `teamcenter_online` 模型文件发起 `simulation.teamcenter.visualization.launch.request@1`，并让 VisMockup 打开对应在线产品结构。当前链路随后只执行普通自动连接。普通连接要求仿真环境已经存在匹配的实时文档绑定，而 `teamcenter_online` 环境尚未建立这种绑定，因此 AI00 能读取新文档身份，却不能合法显示原生三维窗口或执行节点控制。

现有 `simulation.environment.live_document.rebind@1` 只用于轮换一个已经绑定的 `live_document` 会话。把它直接用于首次绑定 `teamcenter_online` 模型会混淆业务语义，并可能覆盖在线来源身份。

## 目标

用户从当前仿真环境的 Teamcenter 在线模型选择“新文档打开”后：

1. VisMockup 打开准确的在线来源。
2. AI00 取得本次打开结果和当前 VisMockup 文档的受信身份。
3. AI00 仅在两份证据与当前环境模型文件完全匹配时建立实时文档绑定。
4. 绑定成功后立即把该 VisMockup 文档内嵌到当前 AI00 三维区域。
5. 保留 Teamcenter 在线来源、缓存结构和备选层次结构，不重建产品树。

## 非目标

- 不按窗口标题、文档显示名或零件名建立绑定。
- 不把缓存树逐节点写回 VisMockup。
- 不改变 Teamcenter 产品结构或在线来源选择器。
- 不自动刷新完整结构树。
- 不改变已有 `live_document.rebind@1` 的恢复语义。

## 方案

### 新原子能力

在 simulation 域新增 `simulation.environment.online_source.live_document.bind@1`。它只完成一个业务效果：把一次已验证的 Teamcenter 在线打开结果和当前受信 VisMockup 文档会话绑定到拥有该在线模型文件的仿真环境。

输入：

- `workspace_gid`
- `document_gid`
- `launch_operation_id`
- `identity_operation_id`
- `expected_workspace_row_version`
- `idempotency_key`

输出：

- `workspace_gid`
- `document_gid`
- `state`
- `connector_device_id`
- `document_session`
- `workspace_row_version`
- `cache_revision_hash`

该能力为 write、用户确认、幂等、web-only，Provider 归 simulation 域所有。

### 受信证据

Provider 不接受前端直接提交的来源哈希、设备 ID 或文档会话。它从 Connector Repository 读取并校验：

- `launch_operation_id` 必须是当前用户和租户发起且成功的 `teamcenter.visualization.launch@1`；
- `identity_operation_id` 必须是当前用户和租户发起且成功的 `vismockup.document.identity.read@1`；
- 两个操作必须属于同一个 Connector 设备；
- launch 结果的 `source_identity_hash` 必须等于目标 `teamcenter_online` 文档保存的 `content_sha256`；
- 目标文档必须属于当前用户、租户和 workspace，且未删除；
- workspace 版本必须与 `expected_workspace_row_version` 一致。

任何缺失、过期、跨用户、跨租户、跨设备、来源不匹配或版本冲突均拒绝绑定。

### 持久化

绑定写入现有 `workmanship_sim_live_document_bindings`，不新增业务表。首次绑定时：

- 若该环境没有活动绑定，插入一条 `bound` 记录；
- 若相同文档会话已绑定到当前环境，返回幂等结果；
- 若环境已有另一活动会话，拒绝并要求走显式恢复流程；
- 若该会话已绑定到其他环境，拒绝；
- 更新目标在线模型文档的 `connector_device_id`，但绝不覆盖它的 `source_kind`、`source_identity_hash`、`content_sha256` 或来源选择器；
- 推进 workspace `row_version` 和 `cache_revision_hash`。

使用现有 workspace 幂等日志和事务边界，数据库失败不得留下半绑定状态。

### 前端流程

“新文档打开”执行以下顺序：

1. 记录当前 workspace、模型文档和 row version。
2. 发起并等待 Teamcenter launch 完成，保留其 operation ID。
3. 以有界轮询等待 VisMockup 当前文档身份变为新的受信会话，保留 identity operation ID；轮询不依赖标题作最终判断。
4. 调用新绑定能力。
5. 仅在绑定返回的 workspace、document 和 document_session 全部匹配时，把实时文档上下文标记为可用并执行原生内嵌。
6. 如果用户中途切换环境、模型文件或页面，则停止后续提交。

失败时不重复 launch。界面保留已打开的外部 VisMockup 文档，并显示“文档已打开，绑定未完成”及可重试绑定入口。

“插入当前文档”维持现状，不使用该能力。

## 错误语义

- `online_document_not_found`
- `online_document_source_mismatch`
- `launch_evidence_unavailable`
- `document_identity_unavailable`
- `connector_device_mismatch`
- `live_document_binding_conflict`
- `live_document_already_bound`
- `version_conflict`
- `document_selection_changed`
- `native_view_attach_failed`

错误不得退化为按名称绑定或静默选择其他环境。

## 测试

后端：

- Provider 使用真实 SQL repository 测试成功首次绑定。
- 来源哈希不一致、跨设备、跨用户、跨租户、错误 workspace/document、版本冲突全部拒绝。
- 同一幂等键返回相同结果，不重复推进版本。
- 已存在其他活动绑定时拒绝。
- Teamcenter 模型来源字段在绑定后保持不变。

前端：

- launch 成功后等待新身份、调用绑定、再内嵌。
- 绑定前不显示原生窗口、不启用节点控制。
- 环境选择变化时不提交绑定。
- 超时或绑定失败时不重复 launch，并展示恢复提示。
- insert 流程不受影响。

运行态：

- 以当前测试数据库的 `test_` 表验证 launch、identity、binding 三段审计记录。
- 验证内嵌窗口出现，模型文件仍为 `teamcenter_online`，显示隐藏操作使用新 document session。

## 治理

- 变更分类：新增原子 Capability，并对现有 Teamcenter 新文档打开消费链路做兼容增强。
- Owner：simulation。
- Consumer：AI00 simulation web。
- 依赖：现有 Connector launch/identity read、workspace repository、Electron native view。
- 数据：复用现有表和事务，不新增迁移。
- `machine_passed`、`human_approved`、`runtime_verified` 独立报告；本规格和 AI 建议不构成人工治理审批。
