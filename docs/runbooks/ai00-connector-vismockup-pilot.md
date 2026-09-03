# AI00 Connector / VisMockup 真实环境验收

本手册只生成运行时证据，不自行把 capability 标记为 `runtime_verified`。受控证据服务和发布流程负责区分 `machine_passed`、`human_approved` 与 `runtime_verified`。

## 前置条件

- 指定 Windows 工作站已由管理员安装组织签名的 AI00 Connector MSI，并绑定唯一 AI00 用户与 Windows SID。
- VisMockup 已打开目标 Teamcenter BOM，机器允许锁屏但任务期间不得休眠。
- AI00 使用非生产工艺版本、不可变环境 manifest 和 HTTPS 服务地址。
- pilot case 符合 `local-runtime/tests/pilot/pilot-case.schema.json`，`expected_operation_ids` 必须按工艺顺序倒序填写。

## 执行矩阵

依次执行：桌面解锁、锁屏、显示器关闭、RDP 断开；每种状态再覆盖网络短断、Connector Service 重启、SessionHost 重启、VisMockup 异常退出。每次只使用一个交互用户会话。

```powershell
pwsh -File local-runtime/tests/pilot/run-vismockup-pilot.ps1 -CasePath .\pilot.json -AccessToken $env:AI00_PILOT_TOKEN
```

## 必须核对的原始证据

- Connector、Adapter、VisMockup 版本和代码 revision；
- 已连接的现有 VisMockup 进程、document ID、Teamcenter source identity、baseline snapshot hash；
- 工具/设备/工装解析到的不可变模型版本与实际 attach node；
- 截图 operation ID 倒序、expected/actual scene hash 一致；
- PNG signature、尺寸、字节数和 SHA-256；
- 上传后的 ArtifactRef，以及工艺域截图区按 operation ID 的回读结果；
- 故障注入后的 lease、journal、重试 attempt、exact-once 挂接结果。

任一 document ID、版本或 baseline hash 在执行中变化，立即停止，不允许自动换 BOM 或推断节点。锁屏成功只能证明 VisMockup 内部 `CaptureImage` 路径可用，不能外推为休眠状态可用。
