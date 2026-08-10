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
  status?: "completed" | "accepted" | "rejected" | "failed" | "outcome_unknown";
  capability_id: string;
  version: number;
  major_version?: number;
  data: T;
  operation_ref?: Record<string, unknown> | null;
  artifact_refs?: Record<string, unknown>[];
  error: CapabilityError | null;
  evidence: EvidenceRef[];
  audit: Record<string, unknown>;
}

export class CapabilityInvocationError extends Error {
  constructor(public readonly status: number, public readonly detail: unknown) {
    super(typeof detail === "object" ? JSON.stringify(detail) : String(detail || `HTTP ${status}`));
    this.name = "CapabilityInvocationError";
  }
}

export class CapabilityClient {
  constructor(private readonly backendUrl: string, private readonly serviceCredential?: string) {}

  private userHeaders(token: string): Record<string, string> {
    return { "Content-Type": "application/json", "X-AI00-Token": token };
  }

  private delegatedHeaders(delegationToken: string): Record<string, string> {
    if (!this.serviceCredential) throw new Error("agent runtime service credential is required");
    return {
      "Content-Type": "application/json",
      "X-AI00-Service-Credential": this.serviceCredential,
      "X-AI00-Delegation": delegationToken,
    };
  }

  async listDelegated(delegationToken: string, catalogRelease: string): Promise<any> {
    const response = await fetch(
      `${this.backendUrl}/api/v2/agent-capabilities/catalog?release=${encodeURIComponent(catalogRelease)}`,
      { headers: this.delegatedHeaders(delegationToken) },
    );
    const value = await response.json();
    if (!response.ok) throw new CapabilityInvocationError(response.status, value);
    return value;
  }

  async invokeDelegated<T = unknown>(delegationToken: string, capabilityId: string, majorVersion: number,
      catalogRelease: string, payload: Record<string, unknown>, requestId: string,
      approvalReference?: string, signal?: AbortSignal): Promise<T> {
    const response = await fetch(`${this.backendUrl}/api/v2/agent-capabilities/${encodeURIComponent(capabilityId)}:invoke`, {
      method: "POST", headers: { ...this.delegatedHeaders(delegationToken), "X-Request-ID": requestId }, signal,
      body: JSON.stringify({ major_version: majorVersion, catalog_release: catalogRelease, payload, approval_reference: approvalReference }),
    });
    const value = await response.json() as T;
    if (!response.ok) throw new CapabilityInvocationError(response.status, value);
    return value;
  }

  async confirmDelegated(delegationToken: string, capabilityId: string, majorVersion: number,
      catalogRelease: string, payload: Record<string, unknown>, requestId: string): Promise<{ approval_reference: string }> {
    const response = await fetch(`${this.backendUrl}/api/v2/agent-capabilities/${encodeURIComponent(capabilityId)}:confirm`, {
      method: "POST", headers: { ...this.delegatedHeaders(delegationToken), "X-Request-ID": requestId },
      body: JSON.stringify({ major_version: majorVersion, catalog_release: catalogRelease, payload }),
    });
    const value = await response.json() as { approval_reference: string };
    if (!response.ok) throw new CapabilityInvocationError(response.status, value);
    return value;
  }

  async currentUser(token: string): Promise<{ gid: string; [key: string]: unknown }> {
    const response = await fetch(`${this.backendUrl}/auth/me`, { headers: this.userHeaders(token) });
    if (!response.ok) throw new Error(`Authentication failed (${response.status})`);
    return await response.json() as { gid: string; [key: string]: unknown };
  }

}
