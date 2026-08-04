export type CapabilityResult<T = unknown> = {
  success: boolean;
  data?: T;
  error?: { code: string; message: string };
};

type InitMessage = {
  type: "ai00.plugin.init";
  protocol: 1;
  instanceId: string;
  channelToken: string;
  grantedCapabilities: string[];
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

  async invoke<T = unknown>(capabilityId: string, payload: Record<string, unknown>, timeoutMs = 30_000): Promise<CapabilityResult<T>> {
    if (!this.init) throw new Error("AI00 host handshake is not complete");
    if (!this.init.grantedCapabilities.includes(capabilityId)) throw new Error(`Capability not granted: ${capabilityId}`);
    const requestId = crypto.randomUUID();
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
