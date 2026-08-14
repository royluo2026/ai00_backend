export type CapabilityStatus = "completed" | "accepted" | "rejected" | "failed" | "outcome_unknown";
export type OperationStatus = "accepted" | "claimed" | "preparing" | "running" | "post_processing" | "completed" | "failed" | "cancelled" | "outcome_unknown";

export type ArtifactRef = {
  artifact_id: string;
  media_type: string;
  sha256: string;
  byte_size: number;
  version: number;
};

export type OperationRef = {
  operation_id: string;
  status: OperationStatus;
  version: number;
};

export type EvidenceRef = {
  kind: string;
  reference: string;
  digest: string | null;
  summary: string;
};

export type CapabilityError = {
  code: string;
  message: string;
  retryable: boolean;
  details: Readonly<Record<string, unknown>>;
};

export type CapabilityResult<T = unknown> = {
  ok: boolean;
  status: CapabilityStatus;
  capability_id: string;
  major_version: number;
  data: T | null;
  operation_ref: OperationRef | null;
  artifact_refs: readonly ArtifactRef[];
  error: CapabilityError | null;
  evidence: readonly EvidenceRef[];
  warnings: readonly string[];
  correlation: { request_id: string; trace_id: string | null };
  /** @deprecated Transitional bridge alias; new plugins must use `ok`. */
  success?: boolean;
};

export function isCapabilityResultV2(value: unknown): value is CapabilityResult {
  if (!value || typeof value !== "object") return false;
  const result = value as Partial<CapabilityResult>;
  return typeof result.ok === "boolean"
    && typeof result.status === "string"
    && typeof result.capability_id === "string"
    && Number.isInteger(result.major_version)
    && Array.isArray(result.artifact_refs)
    && Array.isArray(result.evidence)
    && !!result.correlation;
}

type RandomCrypto = {
  randomUUID?: () => string;
  getRandomValues?: <T extends ArrayBufferView>(array: T) => T;
};

export function createRequestId(cryptoSource: RandomCrypto = globalThis.crypto): string {
  if (typeof cryptoSource?.randomUUID === "function") return cryptoSource.randomUUID();
  if (typeof cryptoSource?.getRandomValues !== "function") throw new Error("Secure random generation is unavailable");
  const bytes = cryptoSource.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0"));
  return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
}

type InitMessage = {
  type: "ai00.plugin.init";
  protocol: 1;
  instanceId: string;
  channelToken: string;
  grantedCapabilities: string[];
  catalogRelease?: string;
  capabilityVersions?: Readonly<Record<string, number>>;
};

type ResponseMessage = {
  type: "ai00.plugin.response";
  requestId: string;
  channelToken: string;
  result: CapabilityResult;
};

export class Ai00PluginClient {
  private init?: InitMessage;
  private readyResolve!: (capabilities: readonly string[]) => void;
  private readyPromise = new Promise<readonly string[]>((resolve) => { this.readyResolve = resolve; });
  private pending = new Map<string, { resolve: (value: CapabilityResult) => void; reject: (reason: Error) => void; timer: number }>();

  constructor() {
    window.addEventListener("message", (event) => {
      if (event.source !== window.parent || !event.data || typeof event.data !== "object") return;
      if (event.data.type === "ai00.plugin.init" && event.data.protocol === 1 && !this.init) {
        this.init = event.data as InitMessage;
        this.readyResolve(Object.freeze([...this.init.grantedCapabilities]));
        window.parent.postMessage({ type: "ai00.plugin.ready", instanceId: this.init.instanceId, channelToken: this.init.channelToken }, "*");
        return;
      }
      const message = event.data as ResponseMessage;
      if (message.type !== "ai00.plugin.response" || !this.init || message.channelToken !== this.init.channelToken) return;
      const pending = this.pending.get(message.requestId);
      if (!pending) return;
      window.clearTimeout(pending.timer);
      this.pending.delete(message.requestId);
      pending.resolve(message.result);
    });
  }

  ready(): Promise<readonly string[]> {
    return this.readyPromise;
  }

  storageGet<T = unknown>(key: string): Promise<CapabilityResult<{ key: string; value: T; version: number; updated_at: string }>> {
    return this.invoke("plugin.storage.get", { key });
  }

  storageList(prefix = "", limit = 100): Promise<CapabilityResult<{ items: Array<{ key: string; version: number; updated_at: string }>; limit: number }>> {
    return this.invoke("plugin.storage.list", { prefix, limit });
  }

  storagePut(key: string, value: unknown, expectedVersion?: number): Promise<CapabilityResult<{ key: string; version: number }>> {
    const payload: Record<string, unknown> = { key, value };
    if (expectedVersion !== undefined) payload.expected_version = expectedVersion;
    return this.invoke("plugin.storage.put", payload);
  }

  storageDelete(key: string, expectedVersion?: number): Promise<CapabilityResult<{ key: string; deleted: boolean }>> {
    const payload: Record<string, unknown> = { key };
    if (expectedVersion !== undefined) payload.expected_version = expectedVersion;
    return this.invoke("plugin.storage.delete", payload);
  }

  grantedCapabilities(): readonly string[] {
    return Object.freeze([...(this.init?.grantedCapabilities ?? [])]);
  }

  catalogRelease(): string | undefined {
    return this.init?.catalogRelease;
  }

  capabilityMajor(capabilityId: string): number | undefined {
    return this.init?.capabilityVersions?.[capabilityId];
  }

  async invoke<T = unknown>(capabilityId: string, payload: Record<string, unknown>, timeoutMs = 30_000): Promise<CapabilityResult<T>> {
    if (!this.init) throw new Error("AI00 host handshake is not complete");
    if (!this.init.grantedCapabilities.includes(capabilityId)) throw new Error(`Capability not granted: ${capabilityId}`);
    const requestId = createRequestId();
    const promise = new Promise<CapabilityResult>((resolve, reject) => {
      const timer = window.setTimeout(() => {
        this.pending.delete(requestId);
        reject(new Error(`Capability request timed out: ${capabilityId}`));
      }, Math.max(1_000, Math.min(timeoutMs, 120_000)));
      this.pending.set(requestId, { resolve, reject, timer });
    });
    window.parent.postMessage({ type: "ai00.plugin.invoke", protocol: 1, instanceId: this.init.instanceId, channelToken: this.init.channelToken, requestId, capabilityId, payload }, "*");
    return promise as Promise<CapabilityResult<T>>;
  }
}
