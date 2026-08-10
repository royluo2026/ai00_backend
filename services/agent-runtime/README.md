# AI00 Agent Runtime

独立部署在云端或客户私有环境中的 Pi Agent Core 服务。Web、飞书私聊和飞书群聊只是入口；模型循环、能力发现、工具调用与会话权限都在这里统一处理。

## 已实现边界

- 使用 `@earendil-works/pi-agent-core`，不依赖已弃用的旧 scope。
- 用户令牌只用于 `/auth/me` 与创建 Run 时的一次委托兑换；能力目录、确认和执行只发送服务凭据与 Run-scoped Delegation。
- 会话始终绑定 `owner_user_gid`；读取和更新 SQL 都包含 owner 条件，团队成员不能互相读取。
- 会话正文以 AES-256-GCM 加密后存入现有 MySQL；外部飞书会话 ID 只保存 SHA-256。
- Run、参与者快照、工具选择、审批和完整/投影工具结果均持久化；委托密钥和审批请求使用 AES-256-GCM 加密。
- 当前只把已认证发起人加入参与者快照；在可信群成员解析接口上线前，不接受客户端自报群成员或 approver。
- 工具集固定到一个 Catalog Release 且有数量上限；写能力遇到确认挑战时暂停 Run，由 owner/approver 决策后通过一次性 approval reference 重放。
- 同一 Run 内请求串行化，避免并发提示覆盖历史；应用启动只检查表，不执行 DDL。

## 本地启动

复制 `.env.example` 并配置环境变量，然后：

```bash
npm install
npm run build
npm start
```

当前 HTTP 接口包括会话管理、`POST /v1/runs`、Run 查询/暂停/恢复/取消、Run 消息与 SSE，以及审批列表和决策。除健康检查外都要求 `X-AI00-Token`。UI context 只作为不可信结构化元数据保存，不拼接到系统提示或用户提示。

部署必须给 Runtime 使用仅限 `workmanship_agent_*` 表的 `AI00_AGENT_DB_URL`，并在 Backend 与 Runtime 的 secret manager 中注入同一个 `AGENT_RUNTIME_SERVICE_TOKEN`。数据库结构由部署 migration 账户执行，Runtime 账户不得拥有 DDL 权限。
