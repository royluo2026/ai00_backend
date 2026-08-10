import { createServer } from "node:http";
import { hostHeaderValidation, NodeStreamableHTTPServerTransport } from "@modelcontextprotocol/node";
import { CapabilityClient } from "./capability-client.js";
import { CatalogCache } from "./catalog-cache.js";
import { DelegationClient, DelegationSessionCache } from "./delegation.js";
import { createAi00Mcp } from "./mcp.js";

function required(name: string): string {
  const value = process.env[name]?.trim(); if (!value) throw new Error(`${name} is required`); return value;
}
const port = Number(process.env.PORT || "8091");
const backendUrl = (process.env.AI00_BACKEND_URL || "http://127.0.0.1:8080").replace(/\/$/, "");
const serviceCredential = required("MCP_GATEWAY_SERVICE_TOKEN");
if (serviceCredential.length < 32) throw new Error("MCP_GATEWAY_SERVICE_TOKEN must contain at least 32 characters");
const allowedHosts = (process.env.AI00_MCP_ALLOWED_HOSTS || "localhost,127.0.0.1").split(",").map(v => v.trim()).filter(Boolean);
const validateHost = hostHeaderValidation(allowedHosts);
const client = new CapabilityClient(backendUrl, serviceCredential);
const delegations = new DelegationClient(backendUrl, serviceCredential);
const sessions = new DelegationSessionCache();
const catalogs = new CatalogCache();

function bearer(header: string | undefined): string {
  const match = header?.match(/^Bearer\s+(.+)$/i); if (!match) throw new Error("authentication_required"); return match[1]!;
}

createServer(async (req, res) => {
  try {
    const url = new URL(req.url || "/", "http://mcp.local");
    if (url.pathname === "/health") { res.writeHead(200, { "Content-Type": "application/json" }); return res.end(JSON.stringify({ ok: true, service: "mcp-gateway" })); }
    if (url.pathname !== "/mcp") { res.writeHead(404); return res.end(); }
    if (!validateHost(req, res)) return;
    const externalToken = bearer(req.headers.authorization);
    const session = await sessions.getOrExchange(externalToken, () => delegations.exchange(externalToken));
    const catalog = catalogs.bind(session.catalogRelease, session.descriptors);
    const mcp = createAi00Mcp(client, session, catalog);
    const transport = new NodeStreamableHTTPServerTransport({ sessionIdGenerator: undefined, enableJsonResponse: true });
    await mcp.connect(transport);
    res.on("close", () => { void transport.close(); });
    await transport.handleRequest(req, res);
  } catch (error) {
    if (res.headersSent) return;
    const unauthorized = error instanceof Error && error.message === "authentication_required";
    res.writeHead(unauthorized ? 401 : 500, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: unauthorized ? "authentication_required" : "internal_error" }));
  }
}).listen(port, "0.0.0.0", () => console.error(`mcp-gateway listening on :${port}`));
