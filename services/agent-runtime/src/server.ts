import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { CapabilityClient } from "./capability-client.js";
import { loadConfig } from "./config.js";
import { PiRuntime } from "./pi-runtime.js";
import { SessionStore, type ChannelType } from "./session-store.js";
import mysql from "mysql2/promise";
import { DelegationClient } from "./delegation-client.js";
import { RunStore, SqlRunRepository } from "./run-store.js";
import { ApprovalDispatcher, SqlApprovalRepository } from "./approval-dispatcher.js";
import { projectCapabilityResult } from "./projection.js";

function json(res: ServerResponse, status: number, value: unknown): void {
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" });
  res.end(JSON.stringify(value));
}
async function body(req: IncomingMessage): Promise<any> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of req) {
    const value = Buffer.from(chunk); size += value.length;
    if (size > 1_000_000) throw new Error("request_body_too_large");
    chunks.push(value);
  }
  try { return JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}"); }
  catch { throw new Error("invalid_json_body"); }
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
}function promptText(input: any): string { return input.text.trim(); }
function publicApproval(value: any): any {
  const { requestCiphertext: _ciphertext, payloadHash: _payloadHash, ...safe } = value;
  return safe;
}
function publicRun(value: any): any {
  const { delegationCiphertext: _delegationCiphertext, ...safe } = value;
  return safe;
}

const config = loadConfig();
const client = new CapabilityClient(config.backendUrl, config.serviceCredential);
const sessions = new SessionStore(config.databaseUrl, config.sessionEncryptionKey);
const runPool = mysql.createPool({ uri: config.databaseUrl, connectionLimit: 10, enableKeepAlive: true, timezone: "Z" });
const runs = new RunStore(new SqlRunRepository(runPool), config.sessionEncryptionKey);
const approvals = new ApprovalDispatcher(new SqlApprovalRepository(runPool), config.sessionEncryptionKey);
const delegations = new DelegationClient(config.backendUrl, config.serviceCredential);
const runtime = new PiRuntime(client, sessions, runs, approvals, config.modelProvider, config.modelId);
await sessions.initialize();

createServer(async (req, res) => {
  try {
    const url = new URL(req.url || "/", "http://runtime.local");
    if (req.method === "GET" && url.pathname === "/health") return json(res, 200, { ok: true, service: "agent-runtime" });
    const authToken = token(req);
    const user = await client.currentUser(authToken);
    if (req.method === "GET" && url.pathname === "/v1/tools") return json(res, 200, { data: await delegations.preview(authToken) });
    if (req.method === "POST" && url.pathname === "/v1/runs") {
      const input = await body(req);
      if (typeof input.goal !== "string" || !input.goal.trim() || typeof input.sessionId !== "string") return json(res, 400, { error: "goal_and_session_required" });
      await sessions.load(user.gid, input.sessionId);
      const tenantId = String(user.team_id || "default");
      const resourceScopes = Array.isArray(input.resourceScopes) && input.resourceScopes.length ? input.resourceScopes : [`tenant:${tenantId}`];
      const bootstrap = await delegations.bootstrap(authToken, { goal: input.goal, resourceScopes });
      const run = await runs.create({
        runId: bootstrap.runId, sessionId: input.sessionId, tenantId, requestedBy: user.gid,
        channelType: (input.channelType || "web") as ChannelType, goal: input.goal.trim(),
        uiContext: input.context && typeof input.context === "object" ? input.context : {},
        catalogRelease: bootstrap.catalogRelease, delegationId: bootstrap.delegationId,
        delegationToken: bootstrap.delegationToken, participants: [],
        selectedTools: bootstrap.selection.tools.map(item => item.id),
      });
      return json(res, 201, { data: publicRun(run) });
    }
    const runMatch = url.pathname.match(/^\/v1\/runs\/([^/]+)$/);
    if (runMatch && req.method === "GET") {
      const run = await runs.loadForParticipant(decodeURIComponent(runMatch[1]!), user.gid);
      return json(res, 200, { data: publicRun(run) });
    }
    const runAction = url.pathname.match(/^\/v1\/runs\/([^/]+)\/(pause|resume|cancel)$/);
    if (runAction && req.method === "POST") {
      const run = await runs.loadForParticipant(decodeURIComponent(runAction[1]!), user.gid);
      if (!run.participants.some(item => item.principalId === user.gid && item.role === "owner")) return json(res, 403, { error: "run_owner_required" });
      const target = runAction[2] === "pause" ? "paused" : runAction[2] === "resume" ? "running" : "cancelled";
      return json(res, 200, { data: publicRun(await runs.transition(run.runId, run.version, target)) });
    }
    const approvalList = url.pathname.match(/^\/v1\/runs\/([^/]+)\/approvals$/);
    if (approvalList && req.method === "GET") {
      const run = await runs.loadForParticipant(decodeURIComponent(approvalList[1]!), user.gid);
      return json(res, 200, { data: (await approvals.list(run.runId)).map(publicApproval) });
    }
    const approvalDecision = url.pathname.match(/^\/v1\/runs\/([^/]+)\/approvals\/([^/]+)\/decision$/);
    if (approvalDecision && req.method === "POST") {
      let run = await runs.loadForParticipant(decodeURIComponent(approvalDecision[1]!), user.gid);
      const participant = run.participants.find(item => item.principalId === user.gid);
      if (!participant || !["owner", "approver"].includes(participant.role)) return json(res, 403, { error: "approver_role_required" });
      const input = await body(req);
      if (!['approved', 'rejected'].includes(input.decision)) return json(res, 400, { error: "invalid_approval_decision" });
      const approvalId = decodeURIComponent(approvalDecision[2]!);
      const pending = await approvals.get(approvalId);
      if (pending.runId !== run.runId) return json(res, 404, { error: "approval_not_found" });
      const decided = await approvals.decide(approvalId, user.gid, input.decision);
      if (input.decision === "rejected") {
        if (run.status === "awaiting_approval") run = await runs.transition(run.runId, run.version, "cancelled");
        return json(res, 200, { data: { approval: publicApproval(decided), run: { runId: run.runId, status: run.status } } });
      }
      const payload = approvals.payload(decided);
      const delegationToken = runs.delegationToken(run);
      let confirmationIssued = false;
      try {
        const confirmation = await client.confirmDelegated(
          delegationToken, decided.capabilityId, decided.majorVersion, run.catalogRelease, payload, decided.requestId,
        );
        confirmationIssued = true;
        const full = await client.invokeDelegated<any>(
          delegationToken, decided.capabilityId, decided.majorVersion, run.catalogRelease, payload,
          decided.requestId, confirmation.approval_reference,
        );
        const catalog = await client.listDelegated(delegationToken, run.catalogRelease);
        const descriptor = (catalog.descriptors || []).find((item: any) =>
          item.id === decided.capabilityId && item.major_version === decided.majorVersion);
        const projected = projectCapabilityResult(full, 16_384, descriptor?.agent_output_schema);
        await runs.recordToolResult({ runId: run.runId, callId: `approval:${decided.approvalRequestId}`,
          capabilityId: decided.capabilityId, majorVersion: decided.majorVersion,
          fullResult: full, projectedResult: projected });
        run = await runs.load(run.runId);
        if (run.status === "awaiting_approval") run = await runs.transition(run.runId, run.version, full?.ok ? "running" : "failed");
        return json(res, 200, { data: { approval: publicApproval(decided), result: projected, run: { runId: run.runId, status: run.status } } });
      } catch (error) {
        run = await runs.load(run.runId);
        if (run.status === "awaiting_approval") await runs.transition(
          run.runId, run.version, confirmationIssued ? "outcome_unknown" : "failed");
        throw error;
      }
    }
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
      const sessionId = decodeURIComponent(sessionMatch[1]!);
      await sessions.load(user.gid, sessionId);
      if (await runs.hasActiveForSession(sessionId)) return json(res, 409, { error: "session_has_active_runs" });
      await sessions.delete(user.gid, sessionId);
      return json(res, 200, { success: true });
    }
    const streamMatch = url.pathname.match(/^\/v1\/runs\/([^/]+)\/messages\/stream$/);
    if (req.method === "POST" && streamMatch) {
      const input = await body(req);
      if (typeof input.text !== "string" || !input.text.trim()) return json(res, 400, { error: "text_required" });
      const controller = new AbortController();
      res.on("close", () => { if (!res.writableEnded) controller.abort(); });
      res.writeHead(200, { "Content-Type": "text/event-stream; charset=utf-8", "Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Connection": "keep-alive" });
      try {
        await runtime.promptRun(user.gid, decodeURIComponent(streamMatch[1]!), promptText(input), event => res.write(`data: ${JSON.stringify(event)}\n\n`), controller.signal);
      } catch { /* Runtime already emitted a sanitized SSE error. */ }
      return res.end();
    }
    const messageMatch = url.pathname.match(/^\/v1\/runs\/([^/]+)\/messages$/);
    if (req.method === "POST" && messageMatch) {
      const input = await body(req);
      if (typeof input.text !== "string" || !input.text.trim()) return json(res, 400, { error: "text_required" });
      return json(res, 200, { data: await runtime.promptRun(user.gid, decodeURIComponent(messageMatch[1]!), promptText(input)) });
    }
    return json(res, 404, { error: "not_found" });
  } catch (error) {
    const message = error instanceof Error ? error.message : "internal_error";
    const status = /required|Authentication failed/.test(message) ? 401
      : /not_found|not found/.test(message) ? 404
      : /version_conflict|invalid_transition|already_decided|awaiting_approval|terminal/.test(message) ? 409
      : /invalid_|too_large|mismatch|denied/.test(message) ? 400 : 500;
    return json(res, status, { error: status === 500 ? "internal_error" : message });
  }
}).listen(config.port, "0.0.0.0", () => console.log(`agent-runtime listening on :${config.port}`));
