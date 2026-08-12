# AI00 Local Runtime（Windows）

这不是桌面 UI，也不替代 Web。只有需要控制 VisMockup 或运行本地插件的工作站安装它。

## 进程边界

- `Ai00.LocalRuntime.Service`：Windows Service，主动向云端 heartbeat/lease，不开放本地 HTTP 端口。
- `Ai00.LocalRuntime.SessionHost`：运行在交互式用户 Session 的独立进程，通过固定 named pipe 接收白名单命令并执行 COM。
- `Ai00.LocalRuntime.Contracts`：命令、租约和回执契约。

当前 .NET Adapter 只广告并实现 `vismockup.status`、`launch`、`open_file`、`visibility`、`capture`。结构树和 CATIA 高亮仍保留在 Python Bridge，等完成 COM 行为对照测试后再加入广告列表；云端即使注册了这些能力，也不会向未广告的设备排队。

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
dotnet build .\Ai00.LocalRuntime.sln -c Release
dotnet test .\Ai00.LocalRuntime.sln -c Release --no-build
```

仓库级验收必须在 Windows 与 .NET 8 SDK 上完成 Release 全解决方案构建和测试。发布 MSI 前仍必须在 Windows CI 重跑，并在安装 VisMockup 的试点机执行 COM 行为对照测试。

## 升级

`UpdateManifestVerifier` 已定义 RSA-PSS 签名与 SHA-256 文件验证，状态枚举覆盖 download → verify → drain → switch → health-check → rollback。下载器、A/B slot 切换和 Authenticode 验证尚未接入，当前版本不得声称支持无人值守自动升级。
