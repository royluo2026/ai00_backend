export interface CapabilitySpec {
  id: string;
  version: number;
  owner: string;
  use_when: string;
  do_not_use_when: string;
  subject_concepts: string[];
  effects: string[];
  deprecated: boolean;
  replaced_by: string | null;
  description: string;
  execution: "cloud" | "local";
  risk: "read" | "write" | "destructive";
  confirmation: "none" | "user" | "admin";
  idempotent: boolean;
  plugin_callable: boolean;
  permissions: string[];
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  device_capability: string | null;
  tags: string[];
}

export interface EvidenceRef {
  kind: string;
  reference: string;
  digest: string | null;
  summary: string;
  metadata: Record<string, unknown>;
}

export interface CapabilityError {
  code: string;
  message: string;
  retryable: boolean;
  details: Record<string, unknown>;
}

export interface CapabilityResult<T = unknown> {
  ok: boolean;
  capability_id: string;
  version: number;
  data: T;
  error: CapabilityError | null;
  evidence: EvidenceRef[];
  audit: Record<string, unknown>;
}

interface Envelope<T> { success: boolean; data: T; detail?: unknown }

export class CapabilityInvocationError extends Error {
  constructor(public readonly status: number, public readonly detail: unknown) {
    super(typeof detail === "object" ? JSON.stringify(detail) : String(detail || `HTTP ${status}`));
    this.name = "CapabilityInvocationError";
  }
}

export class CapabilityClient {
  constructor(private readonly backendUrl: string) {}

  private headers(token: string): Record<string, string> {
    return { "Content-Type": "application/json", "X-AI00-Token": token, "X-AI00-Source": "agent-runtime" };
  }

  async currentUser(token: string): Promise<{ gid: string; [key: string]: unknown }> {
    const response = await fetch(`${this.backendUrl}/auth/me`, { headers: this.headers(token) });
    if (!response.ok) throw new Error(`Authentication failed (${response.status})`);
    return await response.json() as { gid: string; [key: string]: unknown };
  }

  async list(token: string): Promise<CapabilitySpec[]> {
    const response = await fetch(`${this.backendUrl}/api/v1/capabilities?consumer=agent`, { headers: this.headers(token) });
    if (!response.ok) throw new Error(`Capability discovery failed (${response.status})`);
    const body = await response.json() as Envelope<CapabilitySpec[]>;
    return body.data;
  }

  async invoke<T = unknown>(token: string, capability: CapabilitySpec, payload: Record<string, unknown>, signal?: AbortSignal): Promise<CapabilityResult<T>> {
    const response = await fetch(`${this.backendUrl}/api/v1/capabilities/${encodeURIComponent(capability.id)}:invoke`, {
      method: "POST", headers: this.headers(token), signal,
      body: JSON.stringify({ version: capability.version, payload }),
    });
    const body = await response.json() as Envelope<CapabilityResult<T>>;
    if (!response.ok) throw new CapabilityInvocationError(response.status, body.detail);
    return body.data;
  }
}
