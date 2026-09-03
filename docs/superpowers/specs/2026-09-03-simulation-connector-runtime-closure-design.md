# 数模仿真与 AI00 Connector 运行闭环设计

## 目标

在不修改通用 Capability 治理框架的前提下，打通网页版 AI00 数模仿真的首期真实链路：读取已发布工艺执行结构，读取绑定用户当前 VisMockup BOM，解析工具、设备和工装的数模映射，构建仿真环境，按工艺倒序调用 VisMockup 内部截图，并把确认后的图片 Artifact 幂等挂载到工艺域截图区。

## 范围与所有权

本次属于数模仿真域的兼容性实现修复，并包含为该链路服务的 Connector 运行时修复。

- `simulation` 拥有环境编排、物化、倒序截图状态机、运行投影和错误语义。
- `craft` 继续拥有工艺执行结构与工序截图挂载；只提供已存在 Capability 的 typed port adapter，不复制业务规则。
- `knowledge` 继续拥有资源代码到数模版本的映射；只提供已存在 Capability 的 typed port adapter。
- `device`/AI00 Connector 拥有设备健康、Plan 租约、Artifact 传输和本地执行回执。
- 通用 Registry、Catalog 生成器、治理扫描器、审批、Release Gate 及无关 Capability 不在本次修改范围。
- 飞书和其他未来 Connector Adapter 不实现。

## 复用与原子能力结论

复用以下既有能力，不新增同义能力：

- `craft.bop.execution_structure.get@1`
- `craft.process_screenshot.attach@1`
- `knowledge.resource_model_mapping.resolve@1`
- Connector health、Plan queue/lease/complete 与 Artifact API
- `simulation.environment.compose@1`
- `simulation.environment.materialize@1`
- `simulation.capture_run.*@1`

当前打开的 VisMockup BOM 是异步本地事实，不能在服务端同步伪造读取。若既有 Connector Plan 能稳定承载 `vismockup.document.snapshot@1`，则通过数模域工作流复用它并固化 Snapshot；只有 Registry 复用检查证明缺少独立、可授权、可重试、可审计的业务效果时，才新增一个数模域“请求并固化当前文档快照”Capability。最终由 Capability 治理审核任务决定其 stable 生命周期，AI 不代替审批。

## 运行数据流

1. 管理员安装并配对 AI00 Connector；服务持续发送包含绑定用户、SessionHost、系统唤醒状态、VisMockup 实际版本和操作清单的专用心跳。
2. 网页通过 AI00 Gateway 选择该用户唯一设备，请求并等待当前 VisMockup 文档快照；浏览器不访问 localhost。
3. Simulation 通过 Craft、Knowledge、Connector typed ports 获取精确版本数据，解决所有产品及资源绑定后持久化不可变 Environment Manifest。
4. Materialization Plan 中的数模 Artifact 由 Service 使用租约授权 URL 下载，校验大小和 SHA-256，再把可信本地路径注入仅供 SessionHost 使用的执行副本；签名原始 Plan 不被修改。
5. SessionHost 在绑定用户的 STA 中串行调用 `VFFrame.Application`，加载资源数模、应用场景并验证可见节点。
6. Capture Plan 按工艺 sequence 倒序执行。VisMockup 内部生成 PNG；Service 上传并取得 ArtifactRef，回执中不得包含本地路径。
7. 服务端验签回执，将 step 结果投影到对应 Capture Run，并逐项幂等调用 Craft 截图挂载。全部完成后运行才进入 `completed`。

## Connector 运行约束

- Windows Service 与 SessionHost 使用受限 ACL 的 named pipe：只允许指定服务 SID 与绑定用户 SID，不能使用导致跨账户不可达的 `CurrentUserOnly`。
- MSI 必须安装完整 framework-dependent publish 输出，创建绑定用户登录启动项，并设置 ProgramData 凭据、Journal、Artifact 和 Capture 目录 ACL。
- 安装/配对流程负责调用 activate、用 DPAPI 落盘设备凭据，并安全配置可轮换的 Plan 验签 key；示例配置键名必须与程序读取的 `Connector` section 一致。
- 心跳独立于长 Plan 执行，最长间隔小于控制面 freshness 窗口。
- 长 Plan 必须续租或按工序拆成可在租约内完成的小 Plan。首期采用“一道工序一个 capture Plan”，避免新增复杂续租协议；每个 step 的 `timeout_seconds` 必须真正生效。
- Journal 在上传成功但回执未知时先查询/对账，不重复截图；`outcome_unknown` 未经确认不得自动重放。
- 截图目录使用绑定用户与 Service 均可访问的受限目录，成功上传和回执持久化后再清理。

## VisMockup 适配约束

- Adapter 广告实际产品版本，Plan 的兼容区间必须覆盖 VisMockup 14.x，不能继续使用 `>=1,<2`。
- `ApplyCaptureProfile` 必须实现或明确拒绝不支持的尺寸/背景；首期固定 `png/1920x1080/current`，不声称支持 JPEG、透明背景或任意尺寸。
- 文档快照输出统一为协议 snake_case，并提供产品引用字段，能够与 Craft execution structure 的 `product_ref` 精确匹配。
- 资源模型 attach 后保留 manifest node key 到实际 node key 的绑定；场景验证必须读取实际可见性，不能以 Selected 状态替代 Visible 状态。
- 锁屏允许执行；注销、SessionHost 缺失、许可证不可用或活动文档变化时返回稳定错误，不静默启动或切换文档。

## 错误、幂等与恢复

- Environment compose 在任何产品/资源未找到或歧义时不写 Manifest。
- Capture Run、Plan、step attempt、Artifact upload 和 Craft attachment 各自使用稳定幂等键。
- Plan 回执和 Simulation 投影允许重复提交同一结果，哈希不同则返回冲突。
- 租约过期、网络中断、Service/SessionHost 重启和锁屏分别有自动化或实机恢复用例。
- 本地绝对路径、设备 token、Plan secret、Cookie 和访问 URL 不进入业务回执、审计文本或浏览器。

## Web 交互

- 新治理流程仅调用 AI00 Gateway；旧 Electron `127.0.0.1:7654` Bridge 可保留为兼容入口，但不得参与新流程的成功判定。
- 单用户场景默认选择唯一健康 Connector，仍显示设备身份、VisMockup 版本和预检问题。
- 页面状态来自权威 Capture Run，不依据本地按钮状态推断成功。

## 验证

自动化验证至少覆盖：

- typed port 真实绑定及拒绝路径；
- Adapter/Plan 版本和 contract hash 一致；
- 专用心跳在执行期间持续发送；
- Artifact 下载完整性、上传对账及本地路径不泄漏；
- 每工序 Plan 的倒序、超时、幂等和 outcome-unknown；
- 回执投影与 Craft 截图 exactly-once 挂载；
- MSI 完整文件、启动项、ACL 和配置契约；
- Web 新流程不访问 localhost；
- Release .NET build/test、Simulation/Device/Craft/Knowledge Python 测试、领域边界与 Capability 严格验收。

实机验收使用安装 VisMockup 14 的单用户管理员工作站，覆盖正常桌面、锁屏、断网恢复、Service 重启和 SessionHost 重启。验收链为：

`cad_sim.js → AI00 Gateway → Connector Service → named pipe → SessionHost/COM → VisMockup 内部 CaptureImage → Artifact → Craft 截图区回读`。

## 治理状态规则

- `machine_passed` 仅来自当前 revision 的真实检查结果。
- `human_approved` 仅由可信 `super_admin` 针对精确 business-definition hash 决定。
- `runtime_verified` 仅在上述实机链路产生绑定当前版本、hash、commit 和 test run 的证据后为真。
- 所有 AI 结论均为 advisory。
