import { createHash } from "node:crypto";
import type { McpCapabilityDescriptor } from "./catalog-cache.js";

export interface DelegationSession {
  delegationId: string; delegationToken: string; catalogRelease: string;
  expiresAt: string; descriptors: McpCapabilityDescriptor[];
  capabilityScopes?: string[];
}
export class DelegationClient {
  constructor(private readonly backendUrl: string, private readonly serviceCredential: string) {}
  async exchange(externalToken: string): Promise<DelegationSession> {
    const response = await fetch(`${this.backendUrl}/api/v2/mcp-capabilities/delegations`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-AI00-Token": externalToken,
        "X-AI00-Service-Credential": this.serviceCredential }, body: "{}",
    });
    const value = await response.json() as any;
    if (!response.ok) throw new Error(`mcp_delegation_exchange_failed:${response.status}`);
    return { delegationId: value.delegation_id, delegationToken: value.delegation_token,
      catalogRelease: value.catalog_release, expiresAt: value.expires_at,
      capabilityScopes: value.capability_scopes || [], descriptors: value.descriptors || [] };
  }
}
export class DelegationSessionCache {
  private readonly sessions = new Map<string, DelegationSession>();
  private readonly inFlight = new Map<string, Promise<DelegationSession>>();
  constructor(private readonly maximumSessions = 1_000) {
    if (!Number.isInteger(maximumSessions) || maximumSessions < 1) throw new Error("invalid_session_cache_limit");
  }
  async getOrExchange(externalToken: string, exchange: () => Promise<DelegationSession>): Promise<DelegationSession> {
    const key = createHash("sha256").update(externalToken).digest("hex");
    const now = Date.now();
    for (const [cacheKey, value] of this.sessions) {
      if (new Date(value.expiresAt).getTime() <= now + 5_000) this.sessions.delete(cacheKey);
    }
    const current = this.sessions.get(key);
    if (current) return current;
    const pending = this.inFlight.get(key);
    if (pending) return await pending;
    const work = exchange().then(value => {
      while (this.sessions.size >= this.maximumSessions) this.sessions.delete(this.sessions.keys().next().value!);
      this.sessions.set(key, structuredClone(value));
      return this.sessions.get(key)!;
    }).finally(() => this.inFlight.delete(key));
    this.inFlight.set(key, work);
    return await work;
  }
  snapshot(): Array<[string, DelegationSession]> { return structuredClone([...this.sessions.entries()]); }
}
