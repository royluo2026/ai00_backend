import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { CapabilityClient } from "./capability-client.js";
import { loadConfig } from "./config.js";
import { PiRuntime } from "./pi-runtime.js";
import { SessionStore, type ChannelType } from "./session-store.js";

function json(res: ServerResponse, status: number, value: unknown): void {
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" });
  res.end(JSON.stringify(value));
}
async function body(req: IncomingMessage): Promise<any> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(Buffer.from(chunk));
  if (chunks.reduce((n, c) => n + c.length, 0) > 1_000_000) throw new Error("Request body too large");
  return JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
}
function token(req: IncomingMessage): string {
  const value = req.headers["x-ai00-token"];
  if (typeof value !== "string" || !value) throw new Error("X-AI00-Token is required");
  return value;
}
function messageText(message: any): string {
  if (typeof message?.content === "string") return message.content;
  if (Array.isArray(message?.content)) return message.content.filter((part: any) => part?.type === "text").map((part: any) => part.text).join("");
  return "";
}function promptText(input: any): string {
  const context = input.context && typeof input.context === "object" ? `\n\n[当前界面上下文]\n${JSON.stringify(input.context)}` : "";
  return input.text.trim() + context;
}

const config = loadConfig();
const client = new CapabilityClient(config.backendUrl);
const sessions = new SessionStore(config.databaseUrl, config.sessionEncryptionKey);
const runtime = new PiRuntime(client, sessions, config.modelProvider, config.modelId);
await sessions.initialize();

createServer(async (req, res) => {
  try {
    const url = new URL(req.url || "/", "http://runtime.local");
    if (req.method === "GET" && url.pathname === "/health") return json(res, 200, { ok: true, service: "agent-runtime" });
    const authToken = token(req);
    const user = await client.currentUser(authToken);
    if (req.method === "GET" && url.pathname === "/v1/tools") return json(res, 200, { data: await client.list(authToken) });
    if (req.method === "GET" && url.pathname === "/v1/sessions") return json(res, 200, { data: await sessions.list(user.gid) });
    if (req.method === "POST" && url.pathname === "/v1/sessions") {
      const input = await body(req); const channelType = (input.channelType || "web") as ChannelType;
      if (!["web", "feishu_private", "feishu_group"].includes(channelType)) return json(res, 400, { error: "invalid_channel_type" });
      return json(res, 201, { data: await sessions.create(user.gid, channelType, input.externalChannelId) });
    }
    const sessionMatch = url.pathname.match(/^\/v1\/sessions\/([^/]+)$/);
    if (sessionMatch && req.method === "GET") {
      const state = await sessions.load(user.gid, decodeURIComponent(sessionMatch[1]!));
      const turns = state.messages.filter((message: any) => message?.role === "user" || message?.role === "assistant").map((message: any) => ({ role: message.role, content: messageText(message) }));
      return json(res, 200, { data: { turns } });
    }
    if (sessionMatch && req.method === "DELETE") {
      await sessions.delete(user.gid, decodeURIComponent(sessionMatch[1]!));
      return json(res, 200, { success: true });
    }
    const streamMatch = url.pathname.match(/^\/v1\/sessions\/([^/]+)\/messages\/stream$/);
    if (req.method === "POST" && streamMatch) {
      const input = await body(req);
      if (typeof input.text !== "string" || !input.text.trim()) return json(res, 400, { error: "text_required" });
      const controller = new AbortController();
      res.on("close", () => { if (!res.writableEnded) controller.abort(); });
      res.writeHead(200, { "Content-Type": "text/event-stream; charset=utf-8", "Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Connection": "keep-alive" });
      try {
        await runtime.prompt(user.gid, authToken, decodeURIComponent(streamMatch[1]!), promptText(input), event => res.write(`data: ${JSON.stringify(event)}\n\n`), controller.signal);
      } catch { /* Runtime already emitted a sanitized SSE error. */ }
      return res.end();
    }
    const messageMatch = url.pathname.match(/^\/v1\/sessions\/([^/]+)\/messages$/);
    if (req.method === "POST" && messageMatch) {
      const input = await body(req);
      if (typeof input.text !== "string" || !input.text.trim()) return json(res, 400, { error: "text_required" });
      return json(res, 200, { data: await runtime.prompt(user.gid, authToken, decodeURIComponent(messageMatch[1]!), promptText(input)) });
    }
    return json(res, 404, { error: "not_found" });
  } catch (error) {
    const message = error instanceof Error ? error.message : "internal_error";
    const status = /required|Authentication failed/.test(message) ? 401 : /not found/.test(message) ? 404 : 500;
    return json(res, status, { error: message });
  }
}).listen(config.port, "0.0.0.0", () => console.log(`agent-runtime listening on :${config.port}`));
