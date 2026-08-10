import { createHash, randomUUID } from "node:crypto";
import mysql, { type Pool } from "mysql2/promise";
import { open, seal } from "./crypto.js";

export type ChannelType = "web" | "feishu_private" | "feishu_group";
export interface SessionState { messages: unknown[] }
export interface SessionMeta { gid: string; channelType: ChannelType; createdAt: string; updatedAt: string }

export class SessionStore {
  private readonly pool: Pool;
  constructor(databaseUrl: string, private readonly encryptionKey: Buffer) {
    this.pool = mysql.createPool({ uri: databaseUrl, connectionLimit: 10, enableKeepAlive: true });
  }
  async initialize(): Promise<void> {
    await this.pool.execute(`CREATE TABLE IF NOT EXISTS workmanship_agent_sessions (
      gid VARCHAR(64) PRIMARY KEY, owner_user_gid VARCHAR(128) NOT NULL,
      channel_type VARCHAR(32) NOT NULL, external_channel_hash CHAR(64) NULL,
      state_ciphertext MEDIUMTEXT NOT NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      INDEX idx_agent_session_owner (owner_user_gid, updated_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`);
  }
  async create(ownerUserGid: string, channelType: ChannelType = "web", externalChannelId?: string): Promise<SessionMeta> {
    const gid = `as_${randomUUID().replaceAll("-", "")}`;
    const channelHash = externalChannelId ? createHash("sha256").update(externalChannelId).digest("hex") : null;
    await this.pool.execute(
      "INSERT INTO workmanship_agent_sessions (gid, owner_user_gid, channel_type, external_channel_hash, state_ciphertext) VALUES (?, ?, ?, ?, ?)",
      [gid, ownerUserGid, channelType, channelHash, seal({ messages: [] }, this.encryptionKey)],
    );
    return { gid, channelType, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() };
  }
  async list(ownerUserGid: string): Promise<SessionMeta[]> {
    const [rows] = await this.pool.query<any[]>(
      "SELECT gid, channel_type, created_at, updated_at FROM workmanship_agent_sessions WHERE owner_user_gid=? ORDER BY updated_at DESC LIMIT 100", [ownerUserGid],
    );
    return rows.map(row => ({ gid: row.gid, channelType: row.channel_type, createdAt: new Date(row.created_at).toISOString(), updatedAt: new Date(row.updated_at).toISOString() }));
  }
  async load(ownerUserGid: string, gid: string): Promise<SessionState> {
    const [rows] = await this.pool.query<any[]>(
      "SELECT state_ciphertext FROM workmanship_agent_sessions WHERE gid=? AND owner_user_gid=? LIMIT 1", [gid, ownerUserGid],
    );
    if (!rows[0]) throw new Error("Session not found");
    return open<SessionState>(rows[0].state_ciphertext, this.encryptionKey);
  }
  async save(ownerUserGid: string, gid: string, state: SessionState): Promise<void> {
    const [result] = await this.pool.execute<any>(
      "UPDATE workmanship_agent_sessions SET state_ciphertext=?, updated_at=NOW() WHERE gid=? AND owner_user_gid=?",
      [seal(state, this.encryptionKey), gid, ownerUserGid],
    );
    if (result.affectedRows !== 1) throw new Error("Session not found");
  }
  async delete(ownerUserGid: string, gid: string): Promise<void> {
    const [result] = await this.pool.execute<any>(
      "DELETE FROM workmanship_agent_sessions WHERE gid=? AND owner_user_gid=?", [gid, ownerUserGid],
    );
    if (result.affectedRows !== 1) throw new Error("Session not found");
  }
}
