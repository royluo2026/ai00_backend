# AI00 MCP Gateway

把 Capability V2 映射为远程 MCP Streamable HTTP 服务，端点为 `/mcp`。MCP Gateway 属于 Base Platform 协议适配层，不依赖 Agent Runtime。

## 信任与目录边界

- 外部 `Authorization: Bearer` 只用于首次向 Backend 兑换短期、可撤销的 MCP Delegation；缓存键仅保存 Bearer 的 SHA-256。
- 后续能力调用只发送 `MCP_GATEWAY_SERVICE_TOKEN + X-AI00-Delegation`，不转发用户 Bearer、consumer/source 或客户端声明的权限。
- 每个外部认证会话固定一个不可变 Catalog Release 和精确 major；相同 release 内容漂移、重复 MCP 工具名都会 fail closed。
- 当前仅发布 `cloud_sync + read + confirmation=none + exposure.mcp=true` 能力。写能力在 MCP elicitation 审批闭环完成前保持关闭。
- `structuredContent` 和文本只包含按 `agent_output_schema` allowlist 投影的 CapabilityResultV2；保留 Artifact/Operation/Evidence 引用，移除内部 details 和秘密字段。

## 部署

配置 `.env.example` 中的 Backend 地址、允许 Host 和至少 32 字符的服务密钥；Backend 必须注入相同的 `MCP_GATEWAY_SERVICE_TOKEN`。公网入口由反向代理终止 TLS，并限制请求体、连接数和速率。

```bash
npm install
npm run build
npm start
```
