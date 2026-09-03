# AI00 Connector（Windows）

这不是桌面 UI，也不替代 Web。只有需要控制 VisMockup 或运行本地插件的工作站安装它。

## 进程边界

- `Ai00.Connector.Service`：Windows Service，主动向 AI00 heartbeat/lease，不开放本地 HTTP 端口。
- `Ai00.Connector.SessionHost`：运行在唯一绑定用户 Session 的独立进程，通过固定 named pipe 接收白名单计划。
- `Ai00.Connector.Contracts`：版本化计划、Adapter、租约和回执契约；程序集版本不代表协议或 Adapter 版本。
- `Ai00.Connector.Adapters.VisMockup`：内置 VisMockup COM Adapter，所有调用串行进入 STA 队列。

第一阶段仅启用签名清单明确广告的 VisMockup 操作；后续软件通过相同的 `IConnectorAdapter` 边界接入。外部 MCP Adapter 默认拒绝执行，只有管理员允许且签名、契约哈希和操作白名单全部匹配时才能加载。

## 安全约束

- 设备主动出站，不要求客户开放 7654 或任何入站端口。
- 云端命令是显式 capability，不存在远程 `getattr`/任意方法调用。
- `command_id` 幂等、payload SHA-256、短租约、过期时间和设备 token 都会校验。
- `open_file` 只接受管理员配置根目录内存在的 `.jt`/`.plmxml`。
- Service 与 Session Host 分离，COM 始终在 STA 用户会话执行。
- 生产安装必须用 DPAPI/证书库保存设备 token；示例 JSON 不能存真实密钥。

## 构建

需要 Windows 与 .NET 8 SDK：

```powershell
dotnet build .\Ai00.LocalRuntime.sln -c Release -m:1
dotnet test .\Ai00.LocalRuntime.sln -c Release --no-build -m:1
```

仓库级验收必须在 Windows 与 .NET 8 SDK 上完成 Release 全解决方案构建和测试。发布 MSI 前仍必须在 Windows CI 重跑，并在安装 VisMockup 的试点机执行 COM 行为对照测试。

## 升级

`UpdateManifestVerifier` 已定义 RSA-PSS 签名与 SHA-256 文件验证，状态枚举覆盖 download → verify → drain → switch → health-check → rollback。下载器、A/B slot 切换和 Authenticode 验证尚未接入，当前版本不得声称支持无人值守自动升级。
