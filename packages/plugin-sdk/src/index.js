export function isCapabilityResultV2(value) {
  return !!value && typeof value === "object"
    && typeof value.ok === "boolean"
    && typeof value.status === "string"
    && typeof value.capability_id === "string"
    && Number.isInteger(value.major_version)
    && Array.isArray(value.artifact_refs)
    && Array.isArray(value.evidence)
    && !!value.correlation;
}

export function createRequestId(cryptoSource = globalThis.crypto) {
  if (typeof cryptoSource?.randomUUID === "function") return cryptoSource.randomUUID();
  if (typeof cryptoSource?.getRandomValues !== "function") throw new Error("Secure random generation is unavailable");
  const bytes = cryptoSource.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0"));
  return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
}

export class Ai00PluginClient {
  #init; #pending = new Map(); #readyResolve;
  #ready = new Promise((resolve) => { this.#readyResolve = resolve; });
  constructor() {
    window.addEventListener("message", (event) => {
      if (event.source !== window.parent || !event.data || typeof event.data !== "object") return;
      if (event.data.type === "ai00.plugin.init" && event.data.protocol === 1 && !this.#init) {
        this.#init = event.data;
        this.#readyResolve(Object.freeze([...this.#init.grantedCapabilities]));
        window.parent.postMessage({ type: "ai00.plugin.ready", instanceId: this.#init.instanceId, channelToken: this.#init.channelToken }, "*"); return;
      }
      const message = event.data;
      if (message.type !== "ai00.plugin.response" || !this.#init || message.channelToken !== this.#init.channelToken) return;
      const pending = this.#pending.get(message.requestId);
      if (!pending) return;
      clearTimeout(pending.timer); this.#pending.delete(message.requestId); pending.resolve(message.result);
    });
  }
  ready() { return this.#ready; }
  storageGet(key) { return this.invoke("plugin.storage.get", { key }); }
  storageList(prefix = "", limit = 100) { return this.invoke("plugin.storage.list", { prefix, limit }); }
  storagePut(key, value, expectedVersion) {
    const payload = { key, value };
    if (expectedVersion !== undefined) payload.expected_version = expectedVersion;
    return this.invoke("plugin.storage.put", payload);
  }
  storageDelete(key, expectedVersion) {
    const payload = { key };
    if (expectedVersion !== undefined) payload.expected_version = expectedVersion;
    return this.invoke("plugin.storage.delete", payload);
  }
  grantedCapabilities() { return Object.freeze([...(this.#init?.grantedCapabilities ?? [])]); }
  catalogRelease() { return this.#init?.catalogRelease; }
  capabilityMajor(capabilityId) { return this.#init?.capabilityVersions?.[capabilityId]; }
  async invoke(capabilityId, payload, timeoutMs = 30_000) {
    if (!this.#init) throw new Error("AI00 host handshake is not complete");
    if (!this.#init.grantedCapabilities.includes(capabilityId)) throw new Error(`Capability not granted: ${capabilityId}`);
    const requestId = createRequestId();
    const promise = new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.#pending.delete(requestId); reject(new Error(`Capability request timed out: ${capabilityId}`)); }, Math.max(1_000, Math.min(timeoutMs, 120_000)));
      this.#pending.set(requestId, { resolve, reject, timer });
    });
    window.parent.postMessage({ type: "ai00.plugin.invoke", protocol: 1, instanceId: this.#init.instanceId, channelToken: this.#init.channelToken, requestId, capabilityId, payload }, "*");
    return promise;
  }
}
