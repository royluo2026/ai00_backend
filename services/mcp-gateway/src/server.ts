import { createServer } from "node:http";
import { hostHeaderValidation, NodeStreamableHTTPServerTransport } from "@modelcontextprotocol/node";
import { CapabilityClient } from "./capability-client.js";
import { createAi00Mcp } from "./mcp.js";

const port = Number(process.env.PORT || "8091");
const backendUrl = (process.env.AI00_BACKEND_URL || "http://127.0.0.1:8080").replace(/\/$/, "");
const allowedHosts = (process.env.AI00_MCP_ALLOWED_HOSTS || "localhost,127.0.0.1").split(",").map(v => v.trim()).filter(Boolean);
const validateHost = hostHeaderValidation(allowedHosts);
const client = new CapabilityClient(backendUrl);

function bearer(header: string | undefined): string {
  const match = header?.match(/^Bearer\s+(.+)$/i);
  if (!match) throw new Error("Bearer token required");
  return match[1]!;
}

createServer(async (req, res) => {
  try {
    const url = new URL(req.url || "/", "http://mcp.local");
    if (url.pathname === "/health") {
      res.writeHead(200, { "Content-Type": "application/json" });
      return res.end(JSON.stringify({ ok: true, service: "mcp-gateway" }));
    }
    if (url.pathname !== "/mcp") { res.writeHead(404); return res.end(); }
    if (!validateHost(req, res)) return;
    const token = bearer(req.headers.authorization);
    const mcp = await createAi00Mcp(client, token);
    const transport = new NodeStreamableHTTPServerTransport({ sessionIdGenerator: undefined, enableJsonResponse: true });
    await mcp.connect(transport);
    res.on("close", () => { void transport.close(); });
    await transport.handleRequest(req, res);
  } catch (error) {
    if (res.headersSent) return;
    const message = error instanceof Error ? error.message : "internal_error";
    res.writeHead(message.includes("Bearer") ? 401 : 500, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: message }));
  }
}).listen(port, "0.0.0.0", () => console.error(`mcp-gateway listening on :${port}`));
