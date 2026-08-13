# Capability V2 Gitea RC 运维手册（多库强化隔离配置）

本文用于在专用、隔离的 OceanBase test/rc 租户与受保护 Windows runner 上执行 Capability V2 的完整 RC 验收。它不会创建生产租户，也不会接受静态或模拟证据。

> **适用范围更新（2026-08-13）：** 本手册及当前
> `.gitea/workflows/capability-v2-release.yml` 只适用于十一数据库、二十二账号的
> `per_domain_databases` 强化隔离配置。公司测试/生产环境采用
> `single_database_domain_tables`，应执行
> `docs/runbooks/capability-v2-single-database.md` 中的 Schema、DBeaver 和五组授权流程。
> 当前仓库尚未提供与本手册同等强度、绑定单库 profile 的 Gitea RC 工作流，因此不得用
> 本手册的多库 RC 报告宣称公司单库配置已经生产就绪。两种配置共享 Capability、Provider、
> Catalog 和消费者验收，但数据库证据不可互相替代。

## 必要前置条件

- OceanBase 4.3.5 或更高版本、MYSQL 模式、严格 SQL 模式，且 DBA 已创建名称明确包含 `test` 或 `rc` 的专用租户。
- 管理员连接必须通过 `AI00_RC_ADMIN_DB_URL` 显式传入；不得使用 `sys`、生产租户或生产主机。
- `AI00_ACCEPTANCE_OCEANBASE_SSL_CA` 必须指向可读的 TLS CA 文件。
- Gitea runner 必须同时具有 `self-hosted`、`test-server`、`capability-v2-rc` 三个受保护标签，不得换成通用 runner。
- Backend、Agent Runtime 与 MCP Gateway 使用三个独立 HTTPS 地址；Local Runtime 只主动出站，不配置入站健康端口。
- 探针计划由受保护文件 `AI00_RC_PROBE_CONFIG` 提供。文件须覆盖 5 个组件以及 11 个 Domain 的 manifest-owned smoke capability；载荷不得提交到仓库。
- PowerShell 进程中必须存在用户/设备/服务凭据，但不要把凭据写进命令行、日志或 artifact。

受保护的 probe config 是 JSON，`schema_version` 固定为 1。`gateway_headers_env` 和每个 step 的 `headers_env` 将 HTTP header 映射到环境变量名，文件中不得出现真实凭据。`components` 必须精确包含 `backend_gateway`、`plugin`、`agent`、`mcp`、`local_runtime`；check 名称分别固定为：

- Backend：`health`、`catalog`、`unauthenticated_denial`、`permitted_invoke`、`audit`
- Plugin：`catalog`、`permitted`、`denied`、`approval`
- Agent：`health`、`tools`、`permitted`、`denied`、`approval`
- MCP：`initialize`、`tools`、`permitted`、`denied`
- Local Runtime：`heartbeat`、`lease`

每个 step 还需提供 `target`、`method`、`path`、`body`、`expect` 和可选 `timeout_seconds`。Plugin path 必须位于 `/api/v1/plugin-marketplace/` 下，Local Runtime path 必须位于 `/api/v1/device-runtime/` 下。`expect` 只能表达真实的 `health`、`catalog`、`success`、`approval` 或 `denied` 结果；denied 必须收到 401/403/404。

`providers` 必须精确包含 official manifest 的 11 个 `domain_id`。每项包含 `capability_id`、`major_version`、`payload` 和可选 timeout；脚本会校验 capability 的 `owner_domain` 确属该 Domain，并只通过 Backend `/api/v1/capabilities/{id}:invoke` 调用。该文件通常含 RC seed ID 或业务载荷，必须由环境所有者生成并存放在 runner 受保护路径，不能提交到 Git 或上传为 artifact。

缺少管理员 URL、TLS CA、受保护 runner 标签或真实服务凭据时，结论只能是“环境阻塞”。禁止用 `sys`、生产环境、模拟 evidence、常量 `passed` 或通用 runner 绕过。

在 WSL 内启动依赖进程时，只对该进程树提高文件句柄限制：

```bash
ulimit -n 65535
```

不要永久修改宿主机全局限制。

## Gitea 环境与 secrets

创建受保护环境 `capability-v2-release-candidate`，限制只有 RC 管理员可 dispatch。至少配置：

- `CAPABILITY_V2_RC_ADMIN_DB_URL`
- `CAPABILITY_V2_OCEANBASE_URL`
- `CAPABILITY_V2_OCEANBASE_SSL_CA`
- `CAPABILITY_V2_OIS_HEALTH_URL`
- `CAPABILITY_V2_JWT_DISCOVERY_URL`、`CAPABILITY_V2_JWT_ISSUER`
- `CAPABILITY_V2_OAUTH_DISCOVERY_URL`、`CAPABILITY_V2_OAUTH_ISSUER`
- `CAPABILITY_V2_RC_BACKEND_URL`
- `CAPABILITY_V2_RC_AGENT_URL`
- `CAPABILITY_V2_RC_MCP_URL`
- `CAPABILITY_V2_RC_PROBE_CONFIG`
- `CAPABILITY_V2_RC_USER_TOKEN`
- `CAPABILITY_V2_RC_DEVICE_ID`、`CAPABILITY_V2_RC_DEVICE_TOKEN`

Agent/MCP/Backend 启动所需的 service secret、会话加密密钥与模型凭据也应保存在该环境中。不要配置 22 个 Domain URL secret；bootstrap 会生成它们，并由数据库 setup CLI 校验后写入 job environment。

## 本机 bootstrap 与迁移

先确认变量存在，只输出布尔值，不输出内容：

```powershell
@(
  "AI00_RC_ADMIN_DB_URL",
  "AI00_ACCEPTANCE_OCEANBASE_SSL_CA"
) | ForEach-Object {
  if (-not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($_))) {
    "$_=configured"
  } else {
    "$_=missing"
  }
}
```

然后创建 11 个数据库、22 个最小权限 principal，并执行 11 条 Domain migration 流：

```powershell
python backend/scripts/bootstrap_capability_v2_rc_databases.py `
  --admin-url-env AI00_RC_ADMIN_DB_URL `
  --environment-id capability-v2-local-rc `
  --output-env .runtime/capability-v2-rc.env

python backend/scripts/run_capability_v2_rc_database_setup.py `
  --env-file .runtime/capability-v2-rc.env
```

重试已有环境时必须复用并重新验证全部 22 个登录与精确 grants：

```powershell
python backend/scripts/bootstrap_capability_v2_rc_databases.py `
  --admin-url-env AI00_RC_ADMIN_DB_URL `
  --environment-id capability-v2-local-rc `
  --output-env .runtime/capability-v2-rc.env `
  --reuse-env .runtime/capability-v2-rc.env
```

## 启动四个运行面

将 `.runtime/capability-v2-rc.env` 导入当前进程时，应复用 `run_capability_v2_rc_database_setup.py --export-job-env` 的解析逻辑；不要自行 `Get-Content` 后打印记录。Backend 参考仓库启动文档，以 `python -m uvicorn backend.main:app` 启动。Agent 与 MCP 先构建再分别运行 `npm start`，使用不同端口和各自 service secret。Local Runtime 使用 `dotnet run --project local-runtime/src/Ai00.LocalRuntime.Service`，通过 `LocalRuntime__GatewayUrl`、`LocalRuntime__DeviceId`、`LocalRuntime__DeviceToken` 配置主动出站 heartbeat/lease。

启动后分别验证 Backend `/health`、Agent `/health`、MCP `/health`；不要为 Local Runtime 增加入站端口。

## 当前运行证据与严格验收

```powershell
$env:AI00_ACCEPTANCE_ENVIRONMENT_ID = "capability-v2-local-rc"
$env:AI00_ACCEPTANCE_RUN_ID = "local:$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds()):1"

python backend/scripts/run_capability_v2_rc_runtime.py `
  --backend-url "$env:AI00_RC_BACKEND_URL" `
  --agent-url "$env:AI00_RC_AGENT_URL" `
  --mcp-url "$env:AI00_RC_MCP_URL" `
  --provider-output artifacts/provider-crud.json `
  --runtime-output artifacts/runtime-evidence.json

python backend/scripts/verify_domain_database_isolation.py `
  --provider-evidence artifacts/provider-crud.json `
  --output artifacts/database-isolation.json

python backend/scripts/assemble_capability_v2_rc_evidence.py `
  --runtime-evidence artifacts/runtime-evidence.json `
  --database-evidence artifacts/database-isolation.json `
  --output artifacts/capability-v2-rc-evidence.json

$env:AI00_ACCEPTANCE_RC_EVIDENCE = "artifacts/capability-v2-rc-evidence.json"
python backend/scripts/run_capability_v2_acceptance.py `
  --mode release-candidate --strict `
  --report artifacts/capability-v2-release-candidate.json
python backend/scripts/check_capability_v2_completion.py `
  --mode strict `
  --report artifacts/capability-v2-release-candidate.json
```

合格结果应为：1848/1848 mandatory outcomes、5/5 component probes、11/11 Provider smoke、11 个 runtime DDL denied、110 个跨域 credential pair 的读写均 denied，最终 `status: passed` 且 `validation_scope: runtime_e2e`。

## Dispatch 与 artifact 审核

在 Gitea Actions 中手工运行 `Capability V2 Release Candidate`，输入不可变、明确含 `test` 或 `rc` 的 `environment_id`。工作流只允许上传以下五个文件：

- `provider-crud.json`
- `runtime-evidence.json`
- `database-isolation.json`
- `capability-v2-rc-evidence.json`
- `capability-v2-release-candidate.json`

下载后确认绑定的 commit、run ID、environment ID 一致，并检查 JSON key 不含 `password`、`token`、`secret`、`credential`、`database_url`、`dsn`、`authorization`、`admin_url` 或 `private_key`。`.runtime/*.env` 永远不得上传或提交。

## 清理责任

RC 环境所有者负责保留或销毁 test/rc 租户、撤销 22 个 Domain principal、轮换用户/设备/service secrets，并安全删除 runner 上的 `.runtime` 和 `artifacts` 临时文件。数据库删除或 principal 撤销属于破坏性操作，必须由环境所有者核对租户与数据库清单后执行；本仓库脚本不会自动删除它们。
