# 按需打开并执行数模操作设计

## 1. 用户目标与成功标准

用户选择仿真环境后，应直接在模型树点击显示、隐藏、高亮等操作。系统自行判断对应 VisMockup 运行文档是否已经存在：存在则切换到该文档并立即执行；不存在则只启动一次“打开 → 建立本次运行关联 → 内嵌 → 执行原操作”。右键“打开新文档”保留为高级操作，不再是日常显隐的前置步骤。

成功标准：

- 切换环境只加载环境与模型树状态，不主动打开模型。
- 已建立且仍有效的运行关联上，热操作只走本地交互通道，不访问 TC、不查询历史结果、不重新绑定。
- 没有运行关联时，第一次模型操作隐式打开目标文档；打开完成后自动继续执行用户原操作。
- 同一文档并发的首次操作共用一次打开，不产生重复窗口。
- “模型已打开但绑定/内嵌失败”只续接本次打开，不重复打开文档。
- 文档、窗口或进程失效后，旧关联立即作废；下一次操作重新建立本次运行关联。
- 同名模型、同一零件的多个装配实例以及同进程多文档不能串控。

## 2. 范围与约束

本设计复用既有 Teamcenter 在线来源、`launch@2` 打开回执、`bind@3` 原子完成、交互授权、本地命名管道和 Adapter 白名单操作。它不新增通用 COM 接口、不新增 localhost 服务、不把 TC 凭据或签名授权交给 iframe，也不允许页面提供 PID、HWND 或文档身份作为可信输入。

首期覆盖显示、隐藏、高亮、取消高亮。后续全显、全隐、隔离、视图适配等操作接入同一编排器，不能为显隐建立专线。TC 查询、来源解析、业务保存、截图上传和 BOP 回写仍走既有受治理路径。

性能目标分开统计：已有有效运行关联的热操作 P95 不高于 500ms；首次操作的打开耗时按 TC 来源解析、文件获取、VisMockup 加载、运行关联、内嵌和首次操作分别记录。大模型流式加载不伪装成控制延迟。

## 3. 方案比较与选择

### 方案 A：环境选择时预先打开

切换环境即打开模型，后续点击直接控制。它表面简单，但会打开用户未必使用的模型，大装配切换代价高，也会再次把“选环境”等同于“建立运行文档”。不采用。

### 方案 B：首次操作按需打开并建立运行关联（采用）

模型操作统一进入 `ensureReadyAndExecute`。已有精确本地关联则激活并执行；没有关联则共用一次打开任务，建立准确运行关联后继续原操作。此方案符合用户操作习惯，并复用现有 Capability 和本地通道，改动最少。

### 方案 C：每个环境使用独立 VisMockup 进程

一个进程只承载一个文档，身份最简单，但进程和内存成本高，破坏用户现有多文档使用方式，也不能自然接管已有窗口。仅作为未来隔离模式，不进入本期。

## 4. 核心状态模型

每个在线模型文档只有一个桌面运行槽 `DocumentRuntimeSlot`，由 Electron 主进程拥有，iframe 只能持有不透明引用：

```text
idle
  └─ 首次操作 ─> opening ─> associating ─> attaching ─> ready ─> executing
                       │          │             │          │
                       └──────────┴─────────────┴───────> recoverable
                                                          │
                                              续接本次回执 ┘

ready ── 进程/文档/窗口失效 ─> invalid
invalid ── 下一次操作 ─> opening
任意已派发写操作超时 ─> outcome_unknown（禁止自动重放）
```

槽键为 `{owner, tenant, workspace_gid, document_gid, source_identity_hash}`。运行值至少包含：

```text
process_id + process_started_utc_ticks
document_handle + document_session
document_window + window_token
runtime_instance_id + source_association_id
structure_epoch + interaction_id
launch_operation_id + open_completion_idempotency_key
```

环境切换不销毁其他有效槽，只切换当前槽。VisMockup 进程退出、文档关闭、窗口销毁、来源变化、Connector runtime 变化或注销时，使受影响槽失效。页面刷新可以恢复展示状态，但不能凭历史数据库记录重造 HWND；窗口关联只能来自本机仍有效的运行槽或一次新的受控打开。

## 5. 精确窗口关联

当前实测证明：在现有多文档 VisMockup 进程中，COM `View.Title` setter 返回成功但标题不改变，不能继续依赖标题挑战识别窗口。也不能按文件名、窗口标题或 PID 猜测。

新的建立方式只发生在受控打开或受控激活的临界区内：

1. Connector 取得 VisMockup 交互执行门，记录精确进程实例和目标主 MDI 容器的窗口快照。
2. 执行 TC 来源打开。无论 VisMockup 新建窗口还是复用并激活已有文档，都读取签名的 opened-source 回执。
3. 在同一 STA 上读取活动文档句柄 A，读取该 MDI 容器的 `WM_MDIGETACTIVE` 子窗口，再读取活动文档句柄 B。
4. 只有 A、B 与打开回执的文档会话一致，子窗口属于同一精确进程且是该 MDI 容器直属子窗口时，才为窗口设置随机 OS 属性并形成 `{document_window, window_token}`。
5. 若新窗口集合恰好增加一个，可作为辅助证据；它不能代替活动文档双读。出现多个候选、活动文档变化或用户并发切换时失败关闭，不猜测。
6. 后续激活使用已保存 HWND/token，发送 `WM_MDIACTIVATE` 后再次双读活动文档；验证通过才允许内嵌或控制。

这一关联回答“本次运行文档由哪个窗口承载”，不是再次判断 TC 模型是谁。TC 来源身份由模型树和签名打开回执确定；窗口关联是本机运行态事实，建立一次、持续复用。

## 6. 按需操作数据流

模型树、工具栏和后续所有人工控制统一调用：

```text
executeModelIntent(document, targets, absoluteAction)
  -> Electron ensureReadyAndExecute(intent)
     -> 有效槽：activate + local execute
     -> 无槽：single-flight open
          -> launch@2
          -> 捕获本次 document/window
          -> bind@3（绑定、来源关联、授权一次提交）
          -> install grant
          -> native attach（先离屏，复核后显示）
          -> resolve targets
          -> execute original action
```

页面的第一次点击本身就是明确的“若需要则打开并执行”用户意图；选择环境本身不是打开确认。现有服务端确认和权限机制仍须保留，不能由客户端伪造确认。若产品策略要求显式提示，应在第一次点击旁显示一次轻量说明，而不是恢复“先右键打开”的强制步骤。

同一槽在 `opening/associating/attaching` 时只允许一个 single-flight 任务。随后到达的操作等待该任务；绝对状态操作按 `{target, state-family}` 合并为最后意图，例如同一节点连续“隐藏、显示”最终只执行显示。不同节点和不同状态族保持提交顺序。进入 `ready` 后全部走本地队列。

右键“打开/切换到文档”调用同一个 `ensureReady`，仅不附带后续模型操作。它不拥有另一套打开代码。

## 7. 失败与恢复语义

- `open_not_started`：未产生副作用，可以由同一次用户意图安全重试。
- `open_outcome_unknown`：可能已打开，不得再次启动；进入核对流程。
- `opened_binding_pending`：已有有效 opened-source 回执，仅重试 `bind@3`/授权/内嵌，不重复打开。
- `window_association_unavailable`：保留已打开文档和回执，提示继续关联；不得退回文件名匹配。
- `mapping_pending`：运行槽有效但目标节点尚未映射，执行一次有界局部解析，不全树扫描。
- `busy`：VisMockup 自动任务占用执行门，短暂排队或明确返回忙碌，不另开文档。
- `outcome_unknown`：COM 写入已派发但结果未知，暂停该槽后续写操作，不切换旧云路径重放。
- `runtime_invalid`：精确进程、文档或窗口证据失效；撤销槽和交互会话，下一次用户操作重新打开。

恢复记录属于当前本地运行，不把历史成功结果当作当前窗口证据。页面重载后若 Electron 主进程仍持有有效槽，可重新取得不透明引用；若主进程也重启，则不能靠页面缓存恢复 HWND。

## 8. 组件边界

### 前端 iframe

- 将模型树操作从“必须已有 `_localViewerInteraction`”改为提交操作意图。
- 展示当前文档的 opening、loading、ready、busy、outcome_unknown 状态。
- 不持有授权、PID、HWND，不决定是否复用历史身份。

### Electron 主进程

- 新增最小的 `DocumentRuntimeSlot` 管理和 `ensureReadyAndExecute` 编排。
- 复用现有 `openFromLaunch`、授权续期、native attach 和本地 execute，不新增第二套传输。
- 将页面导航、窗口销毁、注销和 Connector runtime 变化统一接入槽失效。

### Connector / VisMockup Adapter

- 用“活动文档双读 + `WM_MDIGETACTIVE` + OS marker”替代标题挑战作为生产窗口关联。
- 提供 `activate_document_window` 和 `prepare_document_window` 两个受限本地操作；均只接受当前授权会话，不接受页面传入 HWND。
- 节点映射继续以 document_session、source_association_id、structure_epoch 为边界。

### Simulation Provider

- 继续使用 `simulation.teamcenter.visualization.launch.request@2` 和 `simulation.environment.online_source.live_document.bind@3`。
- `bind@3` 保持来源关联、工作区版本、交互授权和幂等结果的单事务语义。
- 热操作不新增服务端 Capability；授权续期仍用 `simulation.viewer.interaction.authorize@1`。

## 9. Capability 治理记录

### Change classification

- Type: compatible consumer-flow change plus implementation fix.
- Reason: 不改变既有 Capability 的业务效果、输入输出、权限或稳定错误；改变桌面消费者的调用顺序，并修复本地文档窗口关联实现。若实施中必须修改 Descriptor 投影、错误合同或 `bind@3` schema，应升级为正式 Capability 兼容/破坏性变更并重新评审。

### Authoritative context inspected

- `simulation.teamcenter.visualization.launch.request@2`, GID `cv2_cce43b004671f2f8e0b4edfd`, experimental, Provider `simulation.provider`。
- `simulation.environment.online_source.live_document.bind@3`, GID `cv2_1f92da28d1c518cd7ca6b230`, experimental, Provider `simulation.provider`。
- `simulation.viewer.interaction.authorize@1`, GID `cv2_59f6ec1e05ca6e2b8fdef576`, experimental, Provider `simulation.provider`。
- `simulation.viewer.interaction.scope.get@1`, GID `cv2_9509e285182305b014d86540`, experimental, Provider `simulation.provider`；新主路径不逐次调用，旧兼容路径保留。
- Provider、Descriptor、前端消费者、Electron bridge、Connector pipe/Adapter、来源关联与交互授权表和现有测试已检查。

### Reuse, atomicity, ownership

- 复用 launch@2、bind@3 和 authorize@1，不新增重复 Capability。
- Simulation 域继续拥有来源绑定、授权和审计；Electron 只编排本机运行槽；Connector 只执行受限本地操作。
- `bind@3` 的服务端事务边界不变；窗口捕获属于本机运行态，不能伪装成数据库原子事务。绑定前后均验证当前文档，失败不提交虚假关联。
- 无数据库迁移。现有来源关联、授权和证据表继续由 Simulation 域拥有。

### Governance status

- `machine_passed`: unverified
- `human_approved`: unverified
- `runtime_verified`: false
- `advisory`: true

本设计获得用户交互方向确认，不等同于受信 `super_admin` 对精确 Capability hash 的批准。正式发布仍需独立机器门禁、受信人工批准和受控运行证据。

## 10. 测试与验收

单元与合同测试必须覆盖：

- 已有有效槽直接执行，不调用 launch/bind/scope.get。
- 无槽时一次点击只触发一次 launch，成功后自动执行原操作。
- 同一文档并发点击共用 single-flight；绝对状态合并后的最终状态正确。
- 打开成功、响应丢失、绑定失败、内嵌失败时均不重复打开。
- 新建窗口、VisMockup 复用已有文档窗口两种情况都能通过活动文档双读建立关联。
- 多 MDI 容器、用户并发切换、活动文档 A/B 不一致、同名窗口、旧 PID 复用、marker 被替换全部拒绝。
- 环境 A/B 切换复用各自有效槽；关闭 A 不影响 B。
- 页面刷新可复用 Main 有效槽；Main/Connector 重启后页面缓存不能恢复控制权。
- 同一零件不同 occurrence_path 不串控；首次映射仅有界解析目标路径。
- 已派发操作超时不自动重放；审计仍区分 completed、busy、rejected、outcome_unknown。

受控运行验收只使用诊断小螺栓和用户明确允许的局部装配，不打开整车、不关闭其他模型。分别测量冷打开、已有窗口切换、首次映射和至少 100 次热显隐/高亮。必须以实际画面变化及目标正确性为准，不能只以按钮状态或 RPC 返回成功为准。

## 11. 实施边界与回退

实施优先修改现有编排器与窗口定位器，避免新建平行框架。功能开关仅覆盖新的“按需操作编排”；关闭后恢复现有显式打开入口，但绝不在未知结果后自动重发同一操作。保留当前 Connector/native/frontend 构建和 dist 备份。部署时核对进程实际路径、二进制 hash、页面实际加载 URL 和脚本版本，不以“构建成功”代替部署验证。

本规格不授权提交、发布或正式批准。实施计划须在用户审阅本文件后编写。
