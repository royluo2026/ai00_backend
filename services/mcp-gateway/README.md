# AI00 MCP Gateway

把 Capability Kernel 映射为远程 MCP Streamable HTTP 服务，端点为 `/mcp`。实现使用 MCP TypeScript SDK v2；每个请求创建无状态 transport，便于横向扩容。

鉴权使用 `Authorization: Bearer <AI00 JWT>`，JWT 继续由主后端验证并决定能力权限。当前只发布 `cloud + read + confirmation=none` 能力：外部客户端不能借 MCP 绕过 AI00 的写操作确认。

```bash
npm install
npm run build
npm start
```

公网部署必须将 `AI00_MCP_ALLOWED_HOSTS` 配为真实域名，并由网关终止 TLS。后续开放写能力时，应先完成独立 OAuth resource server、scope 到 Capability permission 的映射，以及 MCP elicitation 到一次性确认 token 的闭环。
## CapabilityResult 与错误契约

MCP Tool 与后端 Capability 一一对应。成功调用的 `structuredContent` 和文本内容都保留完整 `CapabilityResult`：`ok`、`capability_id`、`version`、`data`、`error`、`evidence`、`audit`。

失败调用也不会降成只有一段文本：后端的 HTTP `code/message/retryable/details` 会转换为 `ok=false` 的 `CapabilityResult`，并保留 `capability_id`、`version`、空 evidence、`source=mcp`、`request_id` 和 HTTP 状态审计信息。网络不可达或响应协议异常则使用 `transport_unavailable` 或 `capability_protocol_error`，不伪造业务成功。

网关为每次调用发送 `X-AI00-Source: mcp` 和稳定 `X-Request-ID`。后端 `consumer=mcp` 目录也会再次过滤，只返回 `cloud + read + confirmation=none` 的非 deprecated 能力；写能力和需要确认的能力必须等 MCP OAuth scope 与 elicitation 确认闭环完成后另行开放。
