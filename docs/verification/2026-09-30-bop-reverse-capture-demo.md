# BOP 逆序截图演示：实现与验证

## 1. Change classification

2026-09-30，implementation fix + additive Connector operation。用户明确要求在自己的 test 分支实现；未切换分支、提交、推送或发布。

- 前端：`E:/Projects/ai00_v3/.worktrees/orchestration-merge-frontend-20260905`，HEAD 83260f6b + 工作区改动。
- 后端/运行端：`E:/Projects/ai00_v3/.worktrees/orchestration-merge-backend-20260905`，HEAD 488dd7c69 + 工作区改动。
- 原先 deploy 目录中的规划基线已作废，不作为本轮实现依据。

## 2. Authoritative context inspected

已读当前 test 的 Simulation Manifest、CaptureWorkflow、Connector V1/V2 派发与结果投影、仿真插件声明、simulation.capture_run.start@2 文档、现有测试和 C# Adapter/SceneController/InternalCapture。参考外部 yinyueceshi2/test 的灰蓝差分方案，参考提交 d585bb99c0a7c43e9b2cd608140a8f96eadf40bb；没有整套复制旧 Python Bridge。

本机 VisAutomation.tlb 只读核对了 CaptureImage、FitAll、BasicMaterial 和 MMVUpdate 的真实接口。未连接或改变真实 VisMockup 文档。

## 3. Reuse, atomicity, and ownership result

继续使用 simulation.environment.compose@2、simulation.environment.materialize@2、simulation.capture_run.start@2 及其 action/dispatch/get/cancel/retry 路径，图片仍经既有认证上传和 craft.process_screenshot.attach@1。

新增 adapter operation `vismockup.scene.render@1`，而不是重复建立截图 Capability。Simulation 负责场景/队列，Connector 执行 COM，Craft 保持图片持久化所有权。精确确认、签名、设备/运行实例绑定及副作用分类不绕过。正式 GID/审批依运行时已发布 Catalog，未伪造或替换生产声明。

## 4. Implementation boundary

- 前端只允许明确线体范围，可从选中工位/工序向上解析线体；防止 MouseEvent 被误用为身份及重复启动；更换环境/设备会清除旧物化状态。任务失败、取消和重试保持服务端状态。
- 初始化显示线体 BOP 已完整解析绑定的全部产品并灰化；映射缺失/歧义沿用 compose 的失败规则，不通过模糊匹配补图。
- 按既有 Craft 层级顺序整体逆序，每个工序执行：render 蓝色目标 → verify → capture/认证上传 → render 回灰与隐藏 → verify。图片回填由完整成功结果驱动。
- 灰基线/蓝候选必须通过非空、灰色及蓝色差分检查，只有有效候选原子提交为正式 PNG。文件按 run/step/attempt 隔离，输出目录拒绝路径逃逸。
- 共享产品在前序工序仍有引用时保留；最后一次使用后隐藏。空工序记录 skipped，既不生成空白图也不阻塞整体完成。
- 截图后隐藏失败不会被已上传 artifact 掩盖；未知结果不自动重试；取消等待当前签名计划结束后收敛为 cancelled；失败重试恢复正确的派发状态。
- 未修改数据库结构、原有图树/缓存修复、发布配置或正式 Catalog。新增操作要求更新 Connector 二进制并重新搭建环境，旧环境明确报升级错误。

### 业务契约摘要

- inputs：已批准环境版本、device_id、任务/工序身份；执行端只接收签名计划里的绑定场景与显式目标集合。
- outputs：逐步状态、受认证的 ArtifactRef、图片散列及终态。
- business_effect：为所选线体按逆序生成当前工序蓝色高亮图，并有条件推进拆解可见性。
- invariants：不跨绑定文档；不模糊匹配；无效图不提交/隐藏；共享实例不得提前消失；整步失败不得伪报成功。
- stable errors：见 `E:/Projects/ai00_v3/.worktrees/orchestration-merge-backend-20260905/docs/contracts/vismockup.scene.render@1.md`。
- permissions/resource scope：沿用 simulation.use 与环境/Connector 资源选择器及 Craft 图片权限。
- transaction/idempotency：模型状态与上传不是数据库全局原子事务；按有依赖关系的签名步骤执行，最终投影要求完整成功，run/step/attempt 防止文件覆盖，未知执行结果走原有对账流程。
- side effects：当前模型颜色、可见性和初始相机、本地图片、认证上传与现有 Craft 回填。
- audit/sensitive data：沿用 Connector 签名结果、任务状态与 ArtifactRef，不记录凭据；内部 BOP/模型身份仍按既有权限保护。
- consumers/dependencies：数模页面、跨面板图片展示、Simulation/Craft Provider、Windows COM、当前活动模型。
- tables/migrations：沿用 capture_runs/capture_steps/artifact_refs；skipped 已在原有表约束中，不需要迁移。
- compatibility：旧操作仍在，新增 render 操作显式宣告与校验 contract hash；不把旧环境/旧运行端伪装成支持新版闭环。

## 5. Verification evidence

已执行：

- Python：逆序演示、原有捕获流程、环境 Manifest/compose、Connector 结果投影和 process plan 共 **65 passed**。
- C#：Capture、Scene、AdapterManifest、AdapterDispatcher、ServerContract、文档生命周期相关回归共 **75 passed**；其中新测试用真实 PNG 编解码与模拟 COM，覆盖灰蓝差分、隐藏、空白图、越界目标、输出路径和缩放。
- JavaScript：截图工作流/范围、原生视图、可见性及 Connector onboarding 共 **60 passed**。
- `AI00_WEB_BUILD_PROFILE=test-governance` 的 Vite 构建成功，产物在前端 `dist-test-governance`。保留项目经典 script 的 non-module 构建警告，未发布 production 产物。
- 首次 Node/esbuild 沙箱子进程启动被 EPERM 拦截，获准沙箱外重跑成功；.NET 也在获准沙箱外完成测试。
- 新功能测试先验证失败，再实现；不把外部参考测试、历史截图或模拟 COM 等同于真实 VisMockup 演示。

code_revision 如第 1 节；snapshot_gid、平台 test_run_gid、正式 result_hash 未生成，均为 unverified。

## 6. Governance status

- machine_passed：unverified（相关代码测试通过不等于正式治理快照/发布门禁通过）。
- human_approved：unverified（用户授权开发不等于正式 Catalog/发布审批）。
- runtime_verified：unverified（未对真实线体执行截图）。
- advisory：true。

## 7. Findings and unresolved risks

- 本轮完成源码、测试和测试构建；没有安装新 Connector 到正在运行的 App，没有生产发布。
- 真实演示还需在更新后的测试 App/Connector 中，选择具体 BOP 线体和对应模型，重新搭建环境；先验 3 工序，再验全线体。不得复用旧环境绕过新操作要求。
- CaptureImage 原生尺寸由 VisMockup 决定，输出按现有 1920x1080 profile 等比例适配；不是桌面截图，不裁掉模型内容，也不生成虚构零件。
- 材质覆盖和遮挡依赖真实模型；遇到颜色/场景验证失败会停止，而非宣称完成。完整恢复运行前任意材质/相机，以及交互式单步暂停不在本轮已完成范围。
- 显示范围是该 BOP 线体解析出的产品绑定，不擅自显示未证明属于线体的整车其他零件。尚未提供真实线体、模型和完整映射验收证据。

提交前检查：代码和契约测试已覆盖；正式发布、真实模型验收与对应签名审批仍待执行。本报告不能用来替代这些步骤。
