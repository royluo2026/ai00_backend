# TC 来源驱动的本地数模交互通道设计

## 1. 状态与目标

2026-09-22，用户在本设计交付后回复“go”，确认本地交互架构及 60 秒 TTL / 30 秒续期取舍，进入详细实施计划编写。此确认不等于 Catalog 发布、生产权限审批或运行验收。本阶段只编写文档，不部署、不重启、不操作模型。

目标：保留“模型来源 → 打开 → 取得本次运行身份 → 内嵌与控制 → 更新运行关联”，使已加载模型的交互不再每次经过服务端任务往返。TC 决定来源、版本、装配实例；VisMockup 加载和渲染；当前本地会话持有运行句柄与节点映射。环境历史文档身份不得作为新文档打开成功的前提。

## 2. 代码依据与实测边界

- 老项目 `E:/Projects/ai00/backup/AI00_root_01_dev_pure app version/packages/sim-plugin/web/cad_sim/cad_sim.js`：`_visNodeAction` 经本机 Bridge 一次请求直接返回。
- 老项目 `vis_mockup/bridge.py`：`vis_node_action` 使用 `GetNodeFromKey`，通过 DISPID 9 设置 Visible；`get_vis_tree` 缓存结构，展开时按需取子节点。点击显隐不重新解析 PLMXML。`_ensure_view` 每次获取当前视图，说明便宜的本地有效性检查与快速响应并不矛盾。
- 老项目 `vis_mockup/server.py`：本机 HTTP 无鉴权、反射分派方法，不能照搬这一权限边界；活动文档选择方式也不能照搬。
- 当前前端 `packages/sim-plugin/web/cad_sim/cad_sim.js`：`_requestVisMockupCommand` 提交能力请求后，通过 `_waitVisMockupCommand` 查询结果；`live_document_adoption.js` 对部分 TC 单零件根节点重复发起读树请求。
- 当前 Electron `connector_host_manager.js` 已有随机命名管道、双向进程 PID 校验、请求关联；`main.js` 使用 `capability_client.isTrustedSender` 校验 IPC 来源。
- 当前后端 `local-runtime/src/Ai00.Connector.AppHost/TeamcenterControlPipeHost.cs` 是独立凭据通道，不能混入渲染交互；`DiagnosticPipeHost.cs` 仅诊断，不能变成执行入口。
- 当前 `VisMockupAdapter.cs` 已有 STA 调度、运行会话检查和 `_sessionNodeKeys` 缓存。优先复用，而不是再造一个 Python Bridge。
- 2026-09-22 10:13–10:14 六次显隐：适配器执行约 25–152ms；读树签发到显隐完成约 5.7–7.2s，签发时间只有秒级精度。另一次只读身份请求：提交 2145ms，总耗时 4036ms，适配器执行约 20ms。它们证明公共往返显著，但不是新通道性能证据。

## 3. 决策：授权与即时交互分离

```text
低频：TC 来源解析 / 模型打开 / 业务结果保存
      前端 → Capability Gateway → 签名计划 → Connector → TC / VisMockup
                                         ↓ 建立本次运行关联
低频：服务端授权/续期 → Connector 安装限定范围的交互授权

高频：模型树 / 视图工具栏
      → 受信 Electron IPC → 专用命名管道 → 本地交互调度 → 现有 STA / Adapter
      ← 同一请求返回状态与耗时             ← 本地检查、定位、COM 执行

异步：本地交互日志 → 服务端审计接收（不逐次阻塞界面）
```

不新增 localhost HTTP 服务，不向浏览器或远程网页开放通道，不提供任意 COM/脚本/文件调用。普通 Web 继续使用已有受治理路径，不获得桌面权限。

这不是传输实现的透明替换。现有 `2026-09-03-simulation-ai00-connector-governance-design.md` 的“只执行签名不可变计划”需要明确扩展为“签名计划，以及在限定交互授权内的白名单操作”。新授权契约及消费端必须显式登记、评审与测试，不能以修改绕过检测的测试来宣称合规。服务端仍拥有授权决定，Connector 不自行授予权限。

## 4. 操作分层

| 范围 | 路径 | 一期边界 |
|---|---|---|
| 显示、隐藏、高亮、取消高亮 | 本地交互 | 首批接入；共用协议、调度、映射，不做显隐专线 |
| 全显、全隐、隔离、选中/取消、视图复位/适配 | 同一本地框架 | 逐项加入白名单与合同测试，不自动暴露 Adapter 所有方法 |
| 旋转、缩放、平移鼠标交互 | 内嵌原生视图 | 原生可完成就不增加指令协议 |
| 本地节点映射与必要的局部状态读取 | 本地交互 | 有界、按需；不得在点击热路径全树扫描、导出或加载全部几何 |
| TC 查询、来源解析、打开/插入/关闭模型 | 原服务端路径 | 这些会改变会话/结构，统一使本地映射失效 |
| 截图业务任务、上传、保存环境、回写 BOP、TC 写入 | 原服务端路径 | 本地通道不得替代业务授权和结果提交 |

复用同一 Adapter 白名单操作实现。服务端自动任务与本地人工操作共用执行互斥边界；自动批处理占用模型期间，本地请求快速返回 busy，不插入到业务步骤中间。

## 5. 会话与授权

### 5.1 一次建立、限时复用

打开完成后，Connector 取得当前专用 VisMockup 进程及文档身份。服务端通过新授权能力核准 actor、tenant、device、workspace、已验证来源和运行关联，签发限时交互授权。建议新增能力名 `simulation.viewer.interaction.authorize@1`，属于待登记的新契约，不是现有能力。

授权包含 grant_id、actor/tenant/device、runtime_instance_id、document_session、source_association_id、允许的 operation IDs/合同版本、policy_version、issued_at/expires_at、audience、签名。不得包含 TC 密码、会话票据、FMS URL。source_association_id 引用本次打开建立的关联，不匹配环境历史文档身份。

Connector 验证签名并核对本次运行上下文；授权不交给渲染页面持有，页面仅持有 Electron 管理的不可转移会话引用。每次 IPC 校验受信窗口/页面、窗口所属交互会话与白名单；每次执行在本地检查授权期限、文档会话与节点范围。不查服务端历史结果。

建议初始 TTL 60 秒，第 30 秒后台续期；续期仍由服务端核权，但不重新打开或遍历模型。失联时只允许未过期授权，过期停止新交互；注销、明确撤销、窗口销毁、进程重启立即失效。服务端不可达期间，未知撤销的最长滞后约为剩余 TTL；这是需评审的明确取舍，不能声称断网仍能即时感知撤权。用单调时钟限制作业期限，避免系统时间回拨延长授权。

### 5.2 运行上下文

Connector 持有 process instance、document_session、structure_epoch 和 source_association_id。structure_epoch 是进程内结构代次，不是 TC 来源版本。新进程必须重新建会话，绝不恢复旧数值节点 key。

本地请求建议形状：`{version, request_id, interaction_id, sequence, structure_epoch, operation_id, targets, arguments}`。targets 使用已登记的 opaque node_ref，不接受任意原始 COM key、进程号、路径或任意方法名。响应：`{request_id,status,result,error_code,timings}`；status 明确区分 completed、rejected、busy、outcome_unknown。

专用 `.ViewerInteraction` 命名管道复用当前用户 ACL、校验 Electron 父 PID 与 Connector 子 PID；会话引用绑定窗口实例，不只校验域名。诊断与 Teamcenter 凭据管道保持原用途。

## 6. 节点映射与结构变化

- 映射保存在 Connector，前端缓存只是加速，不是权威。复用现有 `_sessionNodeKeys` 的解析能力，统一生命周期。
- 键为运行会话 + 结构代次 + 完整来源实例路径；值为 opaque node_ref 对应的当前 runtime node key 和必要的局部校验信息。
- TC Item/Revision UID 不是装配实例 key。同一零件的两个实例必须分别映射；不得靠显示名称或同名猜测。
- 单零件根只做一次有界根解析；装配随 TC 展开/用户选择按需解析目标路径。不为首个点击预扫整车，不要求先下载全部几何。
- 若缺少可证明的实例映射，返回 mapping_pending 或 unmapped，由独立有界解析流程补齐；不能悄悄全树扫描，也不能反复自动打开模型。
- 打开、插入、关闭、切换、结构刷新、进程重启、模型源变更，都在统一入口提升代次/撤销相关映射。排队请求执行前再核对代次，旧请求不落到新文档。
- 外部 VisMockup 手工结构修改：先验证可用的文档/结构事件；事件不能覆盖时，以局部节点存在性和已缓存的实例标识校验补足，发现不一致立即失效。若某类编辑无法可靠识别，不启用该场景的缓存快路径；不能用每次全树指纹代替事件。
- COM 对象只在同一 STA 使用；跨线程只传不可变数据和节点引用，不共享 pywin32/COM 指针。

## 7. 调度、失败与审计

- 服务端 PlanExecutionWorker 与本地交互使用同一执行门；仅共用 STA 队列不足以防止多步骤任务被交互插入。自动任务取得独占运行权，普通本地请求在未取得运行权时迅速返回 busy。
- 初始边界：请求上限 64KiB、单批最多 256 个 node_ref、每会话最多 32 个待处理请求。批量操作显式返回逐项结果；不是原子事务，不伪造整批成功。
- 一期使用绝对状态命令（visible=true/false、selected=true/false）。避免重试 toggle 反转两次。成功响应只表示确认完成，不采用立即改图标掩盖失败。
- 同会话 request_id + 请求内容摘要用于去重：重复同内容返回已知结果，冲突内容拒绝。只对已知结果去重，不盲目重放未知写操作。
- 超时区分“未派发”与“已调用 COM、结果未知”。后者暂停相应会话写入并进行本地有界状态核对；无法确认则要求恢复。切换本地/服务端路径不能自动重发这次操作。
- 使用独立、访问受限的交互日志；不重用签名计划的 journal_sequence。执行前记录 admission，完成后记录 outcome，再应答；批量后台上传，服务端按 grant/request 去重。日志无法持久化时拒绝新写操作，不悄悄丢审计。
- 日志仅记录授权引用、会话、操作类型、脱敏目标引用、结果和阶段时间，不记录 TC 凭据、源下载地址或完整签名授权。上传滞后不阻塞当次交互；本地队列达到容量上限时明确停止新写入，不能无限积压。

## 8. 交付阶段与责任文件

以下是设计阶段路线，不是已经批准的逐步实施计划。正式实现前需把授权合同、现有防绕过规则变更和验收测试写入详细计划。

### A. 契约和可测基线

数模仿真域定义交互授权、操作白名单、审计接收契约；桌面域定义 IPC 来源与会话归属。对比同一诊断小零件，记录点击、IPC、排队、节点解析、COM、响应和实际可见变化。分别报告冷启动、冷映射、热操作，不能混为一个平均值。

涉及：后端 `plugins/simulation/simulation_backend/capabilities/`、协议 contracts、Catalog/Provider 与 `backend/tests/`；前端 `scripts/test_no_desktop_business_bypass.js` 必须验证授权交互例外仍拒绝未授权调用，不简单删除原断言。

### B. 通用本地通道与执行门

新增 AppHost 的 `ViewerInteractionProtocol.cs`、`ViewerInteractionPipeHost.cs`、`ViewerInteractionSession.cs`，在 `Program.cs` 注册。复用现有 Adapter/STA。为 `PlanExecutionWorker.cs` 和本地执行器接入共同的运行门；超时未知操作不得释放可继续写的假安全状态。

Electron 新增 `viewer_interaction_client.js` 管理连接/请求/窗口生命周期，由 `connector_host_manager.js` 关联子进程；`main.js`、`preload.js` 仅暴露固定的本地交互接口，不暴露通用 pipe/COM。

测试：伪造进程、非受信页面、错窗口会话、篡改/过期授权、重复消息、请求超限、断管道、COM 未知结果、自动任务互斥、注销失效。先做无模型的协议/调度测试，不打开整车。

### C. 映射和四种操作端到端

在 `VisMockupAdapter.cs` 统一节点映射与代次。前端新增 `viewer_interaction.js`，让 `live_document_adoption.js`、`live_document_bootstrap.js` 和模型树统一走它；底层仍复用 Adapter 的显隐/选中逻辑。

首批四种操作：显示、隐藏、高亮、取消高亮。验证同名不同实例、多次插入、文档切换后旧请求、结构更新、首次映射失败、重复操作。热路径网络记录必须证明没有逐点击 command.get、读树和服务端租约请求。

### D. 扩展、部署和回退

同一框架逐项接入全显/全隐/隔离/视图操作；保持业务保存和自动任务走原路径。以进程/前端实际加载的版本和文件摘要确认部署，不只确认构建成功。先在诊断小零件，再在已有局部装配验证；未经明确授权不打开整车或其他文档。

使用显式功能开关切换，默认旧路径。禁用新通道时先停止入队、处理未决结果、撤销交互会话，再允许新命令走旧路径。严禁因本地超时自动退回旧路径重发同一控制。文件备份可回滚；运行中的未知操作不靠回滚代码宣告完成。

## 9. 性能与正确性验收

设计目标（非已实现承诺）：已加载几何、映射就绪且无独占任务时，单节点点击到确认响应 P50 ≤100ms、P95 ≤300ms；实际画面变化 P95 ≤500ms，以可观察画面而非图标变化判定。若 VisMockup 尚在流式加载，单独报告等待加载时间，不能混入热操作统计。

- 小零件和已有局部装配各至少 100 次热操作，显隐/选中类分别统计；记录样本数、P50/P95/最大值、错误数。
- 每次目标必须正确，零跨文档/跨实例误控；快速重复点击最终状态按被接受请求的序列一致。
- 热请求不访问 TC，不逐次请求服务端授权，不重读全树，不读取历史结果档案；本地局部校验耗时单列。
- 慢网络/断网、授权过期、文档切换、结构修改、Connector 崩溃、审计上传失败分别验证；TTL 内断网行为和撤权窗口按第五节明确呈现。
- 界面显示 mapping_pending/loading/busy/authorization_expired/outcome_unknown 等实际状态，不把空白页面或通用连接报错当恢复策略。

## 10. 已有优化如何衔接

上一阶段已写但未完成部署验证的前端映射缓存，以及 lease 重复鉴权/唤醒阻塞优化，保留为待评审改动，不当作新通道已完成。前端临时缓存最终由 Connector 权威映射替代或降为辅助；服务端小优化继续惠及低频任务，但不是本地交互达标的前提。

当前测试记录：后端相关测试 25 passed、15 skipped；前端适配器 25 passed、读队列 5 passed；bootstrap 行为测试 4 passed，原有资源版本断言仍失败。它们均不是新通道验收。工作区存在大量既有修改及暂存内容，实施不得整体提交、清理或覆盖。

## 11. 待评审的明确决策

1. 接受“限定交互授权 + 本地执行 + 异步审计”，替代交互操作逐条签名计划；业务写入仍不变。
2. 接受初始 60 秒 TTL、30 秒后台续期及相应断网撤权窗口。
3. 接受先四种操作证明通用通道和映射正确，再接入其余交互；不以一次性铺开所有命令替代端到端验证。

批准本设计后，再编写可执行的任务/测试/文件清单计划并提交评审；本设计本身不触发部署。
