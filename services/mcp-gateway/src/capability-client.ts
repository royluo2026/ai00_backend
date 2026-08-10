import type { McpCapabilityDescriptor } from "./catalog-cache.js";

export class CapabilityInvocationError extends Error {
  constructor(public readonly status: number, public readonly detail: unknown) {
    super(`capability_invocation_failed:${status}`); this.name = "CapabilityInvocationError";
  }
}
export class CapabilityTransportError extends Error {
  constructor(message = "capability_transport_unavailable") { super(message); this.name = "CapabilityTransportError"; }
}
export class CapabilityClient {
  constructor(private readonly backendUrl: string, private readonly serviceCredential: string) {}
  private headers(delegationToken: string, requestId: string): Record<string, string> {
    return { "Content-Type": "application/json", "X-AI00-Service-Credential": this.serviceCredential,
      "X-AI00-Delegation": delegationToken, "X-Request-ID": requestId };
  }
  async invoke<T = unknown>(delegationToken: string, spec: McpCapabilityDescriptor,
      catalogRelease: string, payload: Record<string, unknown>, requestId: string): Promise<T> {
    let response: Response;
    try {
      response = await fetch(`${this.backendUrl}/api/v2/mcp-capabilities/${encodeURIComponent(spec.id)}:invoke`, {
        method: "POST", headers: this.headers(delegationToken, requestId),
        body: JSON.stringify({ major_version: spec.major_version, catalog_release: catalogRelease, payload }),
      });
    } catch { throw new CapabilityTransportError(); }
    let value: unknown;
    try { value = await response.json(); } catch { throw new CapabilityTransportError("capability_protocol_error"); }
    if (!response.ok) throw new CapabilityInvocationError(response.status, value);
    if (!value || typeof value !== "object") throw new CapabilityTransportError("capability_protocol_error");
    return value as T;
  }
}
