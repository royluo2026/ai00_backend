import { randomUUID } from "node:crypto";
import type { Pool } from "mysql2/promise";
import { open, seal } from "./crypto.js";
import type { ChannelType } from "./session-store.js";

export type RunStatus = "pending" | "running" | "paused" | "awaiting_approval" | "completed" | "failed" | "cancelled" | "outcome_unknown";
export interface RunParticipant { principalId: string; principalType: "user" | "service"; role: "owner" | "participant" | "approver" }
export interface CreateRunInput {
  runId?: string;
  sessionId: string; tenantId: string; requestedBy: string; channelType: ChannelType;
  goal: string; uiContext: Record<string, unknown>; catalogRelease: string;
  delegationId: string; delegationToken: string; participants: RunParticipant[];
  selectedTools?: string[];
}
export interface AgentRun extends Omit<CreateRunInput, "runId" | "delegationToken" | "participants"> {
  runId: string; status: RunStatus; delegationCiphertext: string; participants: RunParticipant[];
  selectedTools: string[]; version: number; createdAt: string; updatedAt: string;
}
interface StoredAgentRun extends Omit<AgentRun, "goal" | "uiContext"> { inputCiphertext: string }

export interface RunRepository {
  insert(run: StoredAgentRun): Promise<void>;
  load(runId: string): Promise<StoredAgentRun | null>;
  compareAndSet(runId: string, expectedVersion: number, status: RunStatus, updatedAt: string): Promise<boolean>;
  insertToolResult(record: ToolResultRecord): Promise<void>;
  hasActiveForSession(sessionId: string): Promise<boolean>;
}
export interface ToolResultRecord {
  resultId: string; runId: string; callId: string; capabilityId: string; majorVersion: number;
  fullResult: unknown; projectedResult: unknown; createdAt: string;
}

const transitions: Record<RunStatus, readonly RunStatus[]> = {
  pending: ["running", "paused", "cancelled", "failed"],
  running: ["paused", "awaiting_approval", "completed", "failed", "cancelled"],
  paused: ["running", "cancelled", "failed"],
  awaiting_approval: ["running", "cancelled", "failed", "outcome_unknown"],
  completed: [], failed: [], cancelled: [], outcome_unknown: [],
};

export class RunStore {
  constructor(private readonly repository: RunRepository, private readonly encryptionKey: Buffer) {}

  async create(input: CreateRunInput): Promise<AgentRun> {
    const now = new Date().toISOString();
    const owner: RunParticipant = { principalId: input.requestedBy, principalType: "user", role: "owner" };
    const participants = [owner, ...input.participants].filter((item, index, all) =>
      all.findIndex(other => other.principalId === item.principalId && other.principalType === item.principalType) === index);
    const run: AgentRun = {
      runId: input.runId ?? `run_${randomUUID().replaceAll("-", "")}`, sessionId: input.sessionId,
      tenantId: input.tenantId, requestedBy: input.requestedBy, channelType: input.channelType,
      goal: input.goal, uiContext: structuredClone(input.uiContext), catalogRelease: input.catalogRelease,
      delegationId: input.delegationId, delegationCiphertext: seal({ token: input.delegationToken }, this.encryptionKey),
      participants, selectedTools: [...(input.selectedTools ?? [])], status: "pending", version: 1, createdAt: now, updatedAt: now,
    };
    const { goal, uiContext, ...metadata } = run;
    await this.repository.insert({ ...metadata, inputCiphertext: seal({ goal, uiContext }, this.encryptionKey) });
    return structuredClone(run);
  }

  async load(runId: string): Promise<AgentRun> {
    const stored = await this.repository.load(runId);
    if (!stored) throw new Error("run_not_found");
    const { inputCiphertext, ...metadata } = stored;
    const input = open<{ goal: string; uiContext: Record<string, unknown> }>(inputCiphertext, this.encryptionKey);
    return { ...metadata, goal: input.goal, uiContext: input.uiContext };
  }

  async loadForParticipant(runId: string, principalId: string): Promise<AgentRun> {
    const run = await this.load(runId);
    if (!run.participants.some(item => item.principalId === principalId)) throw new Error("participant_required");
    return run;
  }

  delegationToken(run: AgentRun): string {
    return open<{ token: string }>(run.delegationCiphertext, this.encryptionKey).token;
  }

  async transition(runId: string, expectedVersion: number, status: RunStatus): Promise<AgentRun> {
    const current = await this.load(runId);
    if (current.version !== expectedVersion) throw new Error("version_conflict");
    if (!transitions[current.status].includes(status)) throw new Error("invalid_transition");
    if (!await this.repository.compareAndSet(runId, expectedVersion, status, new Date().toISOString())) throw new Error("version_conflict");
    return await this.load(runId);
  }

  async recordToolResult(input: Omit<ToolResultRecord, "resultId" | "createdAt">): Promise<ToolResultRecord> {
    const record = { ...input, resultId: `res_${randomUUID().replaceAll("-", "")}`, createdAt: new Date().toISOString() };
    await this.repository.insertToolResult(record);
    return structuredClone(record);
  }
  async hasActiveForSession(sessionId: string): Promise<boolean> { return await this.repository.hasActiveForSession(sessionId); }
}

export class InMemoryRunRepository implements RunRepository {
  private readonly rows = new Map<string, StoredAgentRun>();
  private readonly results: ToolResultRecord[] = [];
  async insert(run: StoredAgentRun): Promise<void> {
    if (this.rows.has(run.runId)) throw new Error("run_exists");
    this.rows.set(run.runId, structuredClone(run));
  }
  async load(runId: string): Promise<StoredAgentRun | null> { return structuredClone(this.rows.get(runId) ?? null); }
  async compareAndSet(runId: string, expectedVersion: number, status: RunStatus, updatedAt: string): Promise<boolean> {
    const run = this.rows.get(runId);
    if (!run || run.version !== expectedVersion) return false;
    this.rows.set(runId, { ...run, status, version: run.version + 1, updatedAt });
    return true;
  }
  async insertToolResult(record: ToolResultRecord): Promise<void> { this.results.push(structuredClone(record)); }
  async hasActiveForSession(sessionId: string): Promise<boolean> {
    return [...this.rows.values()].some(item => item.sessionId === sessionId && !["completed", "failed", "cancelled", "outcome_unknown"].includes(item.status));
  }
  snapshot(): StoredAgentRun[] { return structuredClone([...this.rows.values()]); }
  resultSnapshot(): ToolResultRecord[] { return structuredClone(this.results); }
}

export class SqlRunRepository implements RunRepository {
  constructor(private readonly pool: Pool) {}
  async insert(run: StoredAgentRun): Promise<void> {
    const connection = await this.pool.getConnection();
    try {
      await connection.beginTransaction();
      await connection.execute(
        `INSERT INTO workmanship_agent_runs
         (run_id,session_gid,tenant_gid,requested_by_user_gid,channel_type,status,run_input_ciphertext,catalog_release,delegation_id,delegation_ciphertext,selected_tools_json,version,created_at,updated_at)
         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)`,
        [run.runId, run.sessionId, run.tenantId, run.requestedBy, run.channelType, run.status,
          run.inputCiphertext, run.catalogRelease, run.delegationId,
          run.delegationCiphertext, JSON.stringify(run.selectedTools), run.version, run.createdAt, run.updatedAt],
      );
      for (const participant of run.participants) {
        await connection.execute(
          `INSERT INTO workmanship_agent_run_participants
           (run_id,principal_gid,principal_type,participant_role,created_at) VALUES (?,?,?,?,?)`,
          [run.runId, participant.principalId, participant.principalType, participant.role, run.createdAt],
        );
      }
      await connection.commit();
    } catch (error) { await connection.rollback(); throw error; }
    finally { connection.release(); }
  }
  async load(runId: string): Promise<StoredAgentRun | null> {
    const [rows] = await this.pool.query<any[]>("SELECT * FROM workmanship_agent_runs WHERE run_id=? LIMIT 1", [runId]);
    if (!rows[0]) return null;
    const [participants] = await this.pool.query<any[]>("SELECT * FROM workmanship_agent_run_participants WHERE run_id=?", [runId]);
    const row = rows[0];
    return {
      runId: row.run_id, sessionId: row.session_gid, tenantId: row.tenant_gid,
      requestedBy: row.requested_by_user_gid, channelType: row.channel_type, status: row.status,
      inputCiphertext: row.run_input_ciphertext, catalogRelease: row.catalog_release,
      delegationId: row.delegation_id, delegationCiphertext: row.delegation_ciphertext,
      selectedTools: jsonValue(row.selected_tools_json, []), version: Number(row.version),
      participants: participants.map(item => ({ principalId: item.principal_gid, principalType: item.principal_type, role: item.participant_role })),
      createdAt: new Date(row.created_at).toISOString(), updatedAt: new Date(row.updated_at).toISOString(),
    };
  }
  async compareAndSet(runId: string, expectedVersion: number, status: RunStatus, updatedAt: string): Promise<boolean> {
    const [result] = await this.pool.execute<any>(
      "UPDATE workmanship_agent_runs SET status=?,version=version+1,updated_at=? WHERE run_id=? AND version=?",
      [status, updatedAt, runId, expectedVersion],
    );
    return result.affectedRows === 1;
  }
  async insertToolResult(record: ToolResultRecord): Promise<void> {
    await this.pool.execute(
      `INSERT INTO workmanship_agent_run_tool_results
       (result_id,run_id,call_id,capability_id,major_version,full_result_json,projected_result_json,created_at)
       VALUES (?,?,?,?,?,?,?,?)`,
      [record.resultId, record.runId, record.callId, record.capabilityId, record.majorVersion,
        JSON.stringify(record.fullResult), JSON.stringify(record.projectedResult), record.createdAt],
    );
  }
  async hasActiveForSession(sessionId: string): Promise<boolean> {
    const [rows] = await this.pool.query<any[]>(
      "SELECT 1 FROM workmanship_agent_runs WHERE session_gid=? AND status IN ('pending','running','paused','awaiting_approval') LIMIT 1",
      [sessionId],
    );
    return Boolean(rows[0]);
  }
}
function jsonValue<T>(value: unknown, fallback: T): T {
  if (value === null || value === undefined) return fallback;
  if (Buffer.isBuffer(value)) value = value.toString("utf8");
  return (typeof value === "string" ? JSON.parse(value) : value) as T;
}
