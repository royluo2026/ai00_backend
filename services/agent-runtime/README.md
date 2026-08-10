# AI00 Agent Runtime

独立部署在云端或客户私有环境中的 Pi Agent Core 服务。Web、飞书私聊和飞书群聊只是入口；模型循环、能力发现、工具调用与会话权限都在这里统一处理。

## 已实现边界

- 使用 `@earendil-works/pi-agent-core`，不依赖已弃用的旧 scope。
- 每次请求用 `X-AI00-Token` 向主后端 `/auth/me` 验证身份，不信任客户端传入的用户 ID。
- 会话始终绑定 `owner_user_gid`；读取和更新 SQL 都包含 owner 条件，团队成员不能互相读取。
- 会话正文以 AES-256-GCM 加密后存入现有 MySQL；外部飞书会话 ID 只保存 SHA-256。
- Agent 只自动加载 `cloud + read + confirmation=none` 的 Capability。写入、破坏性和本地能力不会被模型绕过确认直接执行。
- 同一会话内请求串行化，避免并发提示覆盖历史。

## 本地启动

复制 `.env.example` 并配置环境变量，然后：

```bash
npm install
npm run build
npm start
```

当前 HTTP 接口：`GET /health`、`GET /v1/tools`、`GET/POST /v1/sessions`、`GET/DELETE /v1/sessions/:gid`、`POST /v1/sessions/:gid/messages` 和 SSE `POST /v1/sessions/:gid/messages/stream`。除健康检查外都要求 `X-AI00-Token`。主后端设置 `AI00_AGENT_RUNTIME_MODE=pi` 与 `AI00_AGENT_RUNTIME_URL` 后，现有 `/api/ai/*` Web 调用会经兼容代理切换到本服务；改回 `legacy` 即可回滚。

当前响应是一次性 JSON。下一阶段 Web 接入时应在这个服务增加 SSE 事件流，并把需要确认的 tool call 作为显式事件交给 Web 确认界面；不应在 Agent 内自动获取确认 token。
