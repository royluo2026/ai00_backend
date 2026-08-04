export type HostInvoke = (capabilityId: string, payload: Record<string, unknown>) => Promise<unknown>;

export function mountAi00Plugin(options: {
  container: HTMLElement;
  url: string;
  grantedCapabilities: readonly string[];
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

  const send = (message: object) => iframe.contentWindow?.postMessage(message, "*");
  const onMessage = async (event: MessageEvent) => {
    if (event.source !== iframe.contentWindow || !event.data || typeof event.data !== "object") return;
    const message = event.data;
    if (message.instanceId !== instanceId || message.channelToken !== channelToken) return;
    if (message.type === "ai00.plugin.ready") { ready = true; return; }
    if (message.type !== "ai00.plugin.invoke" || message.protocol !== 1 || typeof message.requestId !== "string") return;
    if (!granted.has(message.capabilityId)) {
      send({ type: "ai00.plugin.response", requestId: message.requestId, channelToken, result: { success: false, error: { code: "capability_not_granted", message: "Capability was not approved for this installation" } } });
      return;
    }
    try {
      const data = await options.invoke(message.capabilityId, message.payload ?? {});
      send({ type: "ai00.plugin.response", requestId: message.requestId, channelToken, result: { success: true, data } });
    } catch (error) {
      send({ type: "ai00.plugin.response", requestId: message.requestId, channelToken, result: { success: false, error: { code: "capability_failed", message: error instanceof Error ? error.message : "Capability failed" } } });
    }
  };
  window.addEventListener("message", onMessage);
  iframe.addEventListener("load", () => send({ type: "ai00.plugin.init", protocol: 1, instanceId, channelToken, grantedCapabilities: [...granted] }));
  options.container.replaceChildren(iframe);
  return () => { ready = false; window.removeEventListener("message", onMessage); iframe.remove(); };
}
