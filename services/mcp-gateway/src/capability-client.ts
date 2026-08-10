import { randomUUID } from "node:crypto";

export interface CapabilitySpec {
  id: string; version: number; owner: string; use_when: string; do_not_use_when: string;
  subject_concepts: string[]; effects: string[]; deprecated: boolean; replaced_by: string | null;
  description: string; execution: "cloud" | "local"; risk: "read" | "write" | "destructive";
  confirmation: "none" | "user" | "admin"; idempotent: boolean; plugin_callable: boolean;
  permissions: string[]; input_schema: Record<string, unknown>; output_schema: Record<string, unknown>;
  device_capability: string | null; tags: string[];
}

export interface EvidenceRef {
  kind: string; reference: string; digest: string | null; summary: string; metadata: Record<string, unknown>;
}
export interface CapabilityError {
  code: string; message: string; retryable: boolean; details: Record<string, unknown>;
}
export interface CapabilityResult<T = unknown> {
  ok: boolean; capability_id: string; version: number; data: T | null; error: CapabilityError | null;
  evidence: EvidenceRef[]; audit: Record<string, unknown>;
}
interface Envelope<T> { success: boolean; data?: T; detail?: unknown }

type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function fallbackCode(status: number): string {
  if (status === 400) return "invalid_request";
  if (status === 401) return "authentication_required";
  if (status === 403) return "permission_denied";
  if (status === 404) return "capability_not_found";
  if (status === 409) return "conflict";
  if (status === 412) return "precondition_failed";
  if (status === 429) return "rate_limit_exceeded";
  return status >= 500 ? "internal_error" : "capability_invocation_failed";
}

function fallbackMessage(status: number): string {
  if (status === 401) return "Authentication is required";
  if (status === 403) return "Capability permission denied";
  if (status === 404) return "Capability was not found";
  if (status === 409) return "Capability invocation conflict";
  if (status === 429) return "Capability invocation rate limit exceeded";
  if (status >= 500) return "Capability execution failed";
  return "Capability invocation failed";
}

export function normalizeCapabilityError(detail: unknown, status: number): CapabilityError {
  const raw = isRecord(detail) ? detail : {};
  const code = typeof raw.code === "string" && raw.code ? raw.code : fallbackCode(status);
  const message = typeof raw.message === "string" && raw.message ? raw.message : fallbackMessage(status);
  const retryable = typeof raw.retryable === "boolean" ? raw.retryable : status === 429 || status >= 500;
  const details = isRecord(raw.details) ? raw.details : {};
  return { code, message, retryable, details };
}

export class CapabilityInvocationError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: unknown,
    public readonly capabilityId: string,
    public readonly version: number,
    public readonly requestId: string,
  ) {
    const normalized = normalizeCapabilityError(detail, status);
    super(normalized.message);
    this.name = "CapabilityInvocationError";
  }

  toResult<T = unknown>(): CapabilityResult<T> {
    return {
      ok: false,
      capability_id: this.capabilityId,
      version: this.version,
      data: null,
      error: normalizeCapabilityError(this.detail, this.status),
      evidence: [],
      audit: {
        source: "mcp",
        request_id: this.requestId,
        http_status: this.status,
      },
    };
  }
}

export class CapabilityTransportError extends Error {
  constructor(
    message: string,
    public readonly requestId: string,
    public readonly code = "transport_unavailable",
    public readonly retryable = true,
  ) {
    super(message);
    this.name = "CapabilityTransportError";
  }

  toResult<T = unknown>(spec: CapabilitySpec): CapabilityResult<T> {
    return {
      ok: false,
      capability_id: spec.id,
      version: spec.version,
      data: null,
      error: { code: this.code, message: this.message, retryable: this.retryable, details: {} },
      evidence: [],
      audit: { source: "mcp", request_id: this.requestId },
    };
  }
}

async function readEnvelope(response: Response): Promise<Envelope<unknown>> {
  try {
    return await response.json() as Envelope<unknown>;
  } catch {
    return { success: false, detail: `HTTP ${response.status}` };
  }
}

export class CapabilityClient {
  constructor(private readonly backendUrl: string) {}

  private headers(token: string, requestId?: string): Record<string, string> {
    return {
      "Content-Type": "application/json",
      "X-AI00-Token": token,
      "X-AI00-Source": "mcp",
      ...(requestId ? { "X-Request-ID": requestId } : {}),
    };
  }

  async list(token: string): Promise<CapabilitySpec[]> {
    const response = await fetch(`${this.backendUrl}/api/v1/capabilities?execution=cloud&consumer=mcp`, { headers: this.headers(token) });
    const body = await readEnvelope(response) as Envelope<CapabilitySpec[]>;
    if (!response.ok) throw new Error(`Capability discovery failed (${response.status})`);
    return body.data || [];
  }

  async invoke<T = unknown>(
    token: string,
    spec: CapabilitySpec,
    payload: Record<string, unknown>,
    requestId: string = randomUUID(),
  ): Promise<CapabilityResult<T>> {
    let response: Response;
    try {
      response = await fetch(`${this.backendUrl}/api/v1/capabilities/${encodeURIComponent(spec.id)}:invoke`, {
        method: "POST",
        headers: this.headers(token, requestId),
        body: JSON.stringify({ version: spec.version, payload }),
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Capability backend is unavailable";
      throw new CapabilityTransportError(message, requestId);
    }

    const envelope = await readEnvelope(response) as Envelope<CapabilityResult<T>>;
    const responseRequestId = response.headers?.get("X-Request-ID") || requestId;
    if (!response.ok) {
      throw new CapabilityInvocationError(response.status, envelope.detail, spec.id, spec.version, responseRequestId);
    }
    if (!envelope.data || typeof envelope.data !== "object") {
      throw new CapabilityTransportError("Capability response did not contain a CapabilityResult", responseRequestId, "capability_protocol_error", false);
    }
    const result = envelope.data;
    result.audit = {
      ...(isRecord(result.audit) ? result.audit : {}),
      source: "mcp",
      request_id: result.audit?.request_id || responseRequestId,
    };
    return result;
  }
}