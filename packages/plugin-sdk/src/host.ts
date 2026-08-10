import type { CapabilityResult } from "./index.js";

export type HostInvoke = (capabilityId: string, payload: Record<string, unknown>) => Promise<CapabilityResult>;

export function mountAi00Plugin(options: {
  container: HTMLElement;
  url: string;
  grantedCapabilities: readonly string[];
  capabilityVersions?: Readonly<Record<string, number>>;
  catalogRelease?: string;
  mountSessionId?: string;
  invoke: HostInvoke;
}): () => void {
  const iframe = document.createElement("iframe");
  iframe.sandbox.add("allow-scripts");
  iframe.referrerPolicy = "no-referrer";
  iframe.src = options.url;
  const instanceId = crypto.randomUUID();
  const channelToken = crypto.randomUUID() + crypto.randomUUID();
  const granted = new Set(options.grantedCapabilities);
  let ready = false;

  const rejected = (capabilityId: string, requestId: string, code: string, message: string): CapabilityResult => ({
    ok: false,
    status: "rejected",
    capability_id: capabilityId,
    major_version: options.capabilityVersions?.[capabilityId] ?? 1,
    data: null,
    operation_ref: null,
    artifact_refs: [],
    error: { code, message, retryable: false, details: {} },
    evidence: [],
    warnings: [],
    correlation: { request_id: requestId, trace_id: null },
  });

  const send = (message: object) => iframe.contentWindow?.postMessage(message, "*");
  const onMessage = async (event: MessageEvent) => {
    if (event.source !== iframe.contentWindow || !event.data || typeof event.data !== "object") return;
    const message = event.data;
    if (message.instanceId !== instanceId || message.channelToken !== channelToken) return;
    if (message.type === "ai00.plugin.ready") { ready = true; return; }
    if (message.type !== "ai00.plugin.invoke" || message.protocol !== 1 || typeof message.requestId !== "string") return;
    if (!granted.has(message.capabilityId)) {
      send({ type: "ai00.plugin.response", requestId: message.requestId, channelToken, result: rejected(message.capabilityId, message.requestId, "capability_not_granted", "Capability was not approved for this mount session") });
      return;
    }
    try {
      const result = await options.invoke(message.capabilityId, message.payload ?? {});
      send({ type: "ai00.plugin.response", requestId: message.requestId, channelToken, result });
    } catch (error) {
      send({ type: "ai00.plugin.response", requestId: message.requestId, channelToken, result: rejected(message.capabilityId, message.requestId, "host_bridge_failed", error instanceof Error ? error.message : "Capability host bridge failed") });
    }
  };
  window.addEventListener("message", onMessage);
  iframe.addEventListener("load", () => send({
    type: "ai00.plugin.init", protocol: 1, instanceId, channelToken,
    catalogRelease: options.catalogRelease,
    capabilityVersions: options.capabilityVersions ?? {}, grantedCapabilities: [...granted],
  }));
  options.container.replaceChildren(iframe);
  return () => { ready = false; window.removeEventListener("message", onMessage); iframe.remove(); };
}
