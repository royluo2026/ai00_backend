import { createHash, randomUUID } from "node:crypto";
import type { Pool } from "mysql2/promise";
import { open, seal } from "./crypto.js";

export type ApprovalStatus = "pending" | "approved" | "rejected" | "expired";
export interface ApprovalRequest {
  approvalRequestId: string; runId: string; capabilityId: string; majorVersion: number;
  requestId: string; payloadHash: string; requestCiphertext: string;
  challenge: Record<string, unknown>; status: ApprovalStatus;
  decidedBy: string | null; createdAt: string; decidedAt: string | null; version: number;
}
export interface ApprovalRepository {
  insert(value: ApprovalRequest): Promise<void>;
  load(id: string): Promise<ApprovalRequest | null>;
  listByRun(runId: string): Promise<ApprovalRequest[]>;
  decide(id: string, expectedVersion: number, status: "approved" | "rejected", decidedBy: string, decidedAt: string): Promise<boolean>;
}
const digest = (payload: Record<string, unknown>) => createHash("sha256").update(JSON.stringify(sortValue(payload))).digest("hex");
function sortValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortValue);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => [k, sortValue(v)]));
  return value;
}
export class ApprovalDispatcher {
  constructor(private readonly repository: ApprovalRepository, private readonly encryptionKey: Buffer) {}
  async request(input: { runId: string; capabilityId: string; majorVersion: number; requestId: string; payload: Record<string, unknown>; challenge: Record<string, unknown> }): Promise<ApprovalRequest> {
    const value: ApprovalRequest = {
      approvalRequestId: `arq_${randomUUID().replaceAll("-", "")}`, runId: input.runId,
      capabilityId: input.capabilityId, majorVersion: input.majorVersion, requestId: input.requestId,
      payloadHash: digest(input.payload), requestCiphertext: seal({ payload: input.payload }, this.encryptionKey),
      challenge: structuredClone(input.challenge), status: "pending", decidedBy: null,
      createdAt: new Date().toISOString(), decidedAt: null, version: 1,
    };
    await this.repository.insert(value); return structuredClone(value);
  }
  async list(runId: string): Promise<ApprovalRequest[]> { return await this.repository.listByRun(runId); }
  async get(id: string): Promise<ApprovalRequest> {
    const value = await this.repository.load(id);
    if (!value) throw new Error("approval_not_found");
    return value;
  }
  payload(request: ApprovalRequest): Record<string, unknown> {
    return open<{ payload: Record<string, unknown> }>(request.requestCiphertext, this.encryptionKey).payload;
  }
  async decide(id: string, actor: string, decision: "approved" | "rejected", suppliedPayload?: Record<string, unknown>): Promise<ApprovalRequest> {
    const current = await this.get(id);
    if (current.status !== "pending") throw new Error("approval_already_decided");
    if (suppliedPayload && current.payloadHash !== digest(suppliedPayload)) throw new Error("payload_mismatch");
    if (!await this.repository.decide(id, current.version, decision, actor, new Date().toISOString())) throw new Error("approval_version_conflict");
    return (await this.repository.load(id))!;
  }
}
export class InMemoryApprovalRepository implements ApprovalRepository {
  private rows = new Map<string, ApprovalRequest>();
  async insert(value: ApprovalRequest): Promise<void> { this.rows.set(value.approvalRequestId, structuredClone(value)); }
  async load(id: string): Promise<ApprovalRequest | null> { return structuredClone(this.rows.get(id) ?? null); }
  async listByRun(runId: string): Promise<ApprovalRequest[]> { return structuredClone([...this.rows.values()].filter(item => item.runId === runId)); }
  async decide(id: string, expectedVersion: number, status: "approved" | "rejected", decidedBy: string, decidedAt: string): Promise<boolean> {
    const current = this.rows.get(id); if (!current || current.version !== expectedVersion || current.status !== "pending") return false;
    this.rows.set(id, { ...current, status, decidedBy, decidedAt, version: current.version + 1 }); return true;
  }
}
export class SqlApprovalRepository implements ApprovalRepository {
  constructor(private readonly pool: Pool) {}
  async insert(value: ApprovalRequest): Promise<void> {
    await this.pool.execute(
      `INSERT INTO workmanship_agent_run_approvals
       (approval_request_id,run_id,capability_id,major_version,request_id,payload_hash,challenge_json,request_ciphertext,status,decided_by,created_at,decided_at,version)
       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)`,
      [value.approvalRequestId, value.runId, value.capabilityId, value.majorVersion, value.requestId,
        value.payloadHash, JSON.stringify(value.challenge), value.requestCiphertext, value.status,
        value.decidedBy, value.createdAt, value.decidedAt, value.version],
    );
  }
  async load(id: string): Promise<ApprovalRequest | null> {
    const [rows] = await this.pool.query<any[]>("SELECT * FROM workmanship_agent_run_approvals WHERE approval_request_id=? LIMIT 1", [id]);
    return rows[0] ? fromRow(rows[0]) : null;
  }
  async listByRun(runId: string): Promise<ApprovalRequest[]> {
    const [rows] = await this.pool.query<any[]>("SELECT * FROM workmanship_agent_run_approvals WHERE run_id=? ORDER BY created_at", [runId]);
    return rows.map(fromRow);
  }
  async decide(id: string, expectedVersion: number, status: "approved" | "rejected", decidedBy: string, decidedAt: string): Promise<boolean> {
    const [result] = await this.pool.execute<any>(
      "UPDATE workmanship_agent_run_approvals SET status=?,decided_by=?,decided_at=?,version=version+1 WHERE approval_request_id=? AND version=? AND status='pending'",
      [status, decidedBy, decidedAt, id, expectedVersion],
    );
    return result.affectedRows === 1;
  }
}
function fromRow(row: any): ApprovalRequest {
  return {
    approvalRequestId: row.approval_request_id, runId: row.run_id, capabilityId: row.capability_id,
    majorVersion: Number(row.major_version), requestId: row.request_id, payloadHash: row.payload_hash,
    requestCiphertext: row.request_ciphertext,
    challenge: jsonValue(row.challenge_json),
    status: row.status, decidedBy: row.decided_by, createdAt: new Date(row.created_at).toISOString(),
    decidedAt: row.decided_at ? new Date(row.decided_at).toISOString() : null, version: Number(row.version),
  };
}
function jsonValue(value: unknown): Record<string, unknown> {
  if (Buffer.isBuffer(value)) value = value.toString("utf8");
  return (typeof value === "string" ? JSON.parse(value) : value) as Record<string, unknown>;
}
