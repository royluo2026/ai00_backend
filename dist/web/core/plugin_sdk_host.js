// Generated from @ai00/plugin-sdk/src/host.ts; SHA256 24a5648e69a0d8aa5feccf832ac42c055f8762ac5ad77f5bab59be98d85b0371
var AI00PluginHost = (() => {
  var __defProp = Object.defineProperty;
  var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
  var __getOwnPropNames = Object.getOwnPropertyNames;
  var __hasOwnProp = Object.prototype.hasOwnProperty;
  var __export = (target, all) => {
    for (var name in all)
      __defProp(target, name, { get: all[name], enumerable: true });
  };
  var __copyProps = (to, from, except, desc) => {
    if (from && typeof from === "object" || typeof from === "function") {
      for (let key of __getOwnPropNames(from))
        if (!__hasOwnProp.call(to, key) && key !== except)
          __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
    }
    return to;
  };
  var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

  // ../orchestration-merge-backend-20260905/packages/plugin-sdk/src/host.ts
  var host_exports = {};
  __export(host_exports, {
    mountAi00Plugin: () => mountAi00Plugin
  });
  function mountAi00Plugin(options) {
    const iframe = document.createElement("iframe");
    iframe.sandbox.add("allow-scripts");
    iframe.referrerPolicy = "no-referrer";
    iframe.src = options.url;
    const instanceId = crypto.randomUUID();
    const channelToken = crypto.randomUUID() + crypto.randomUUID();
    const granted = new Set(options.grantedCapabilities);
    let ready = false;
    const rejected = (capabilityId, requestId, code, message) => ({
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
      correlation: { request_id: requestId, trace_id: null }
    });
    const compatibleResult = (result) => ({
      ...result,
      success: result.ok
    });
    const send = (message) => iframe.contentWindow?.postMessage(message, "*");
    const onMessage = async (event) => {
      if (event.source !== iframe.contentWindow || !event.data || typeof event.data !== "object")
        return;
      const message = event.data;
      if (message.instanceId !== instanceId || message.channelToken !== channelToken)
        return;
      if (message.type === "ai00.plugin.ready") {
        ready = true;
        return;
      }
      if (message.type !== "ai00.plugin.invoke" || message.protocol !== 1 || typeof message.requestId !== "string")
        return;
      if (!granted.has(message.capabilityId)) {
        send({ type: "ai00.plugin.response", requestId: message.requestId, channelToken, result: compatibleResult(rejected(message.capabilityId, message.requestId, "capability_not_granted", "Capability was not approved for this mount session")) });
        return;
      }
      try {
        const result = await options.invoke(message.capabilityId, message.payload ?? {});
        send({ type: "ai00.plugin.response", requestId: message.requestId, channelToken, result: compatibleResult(result) });
      } catch (error) {
        send({ type: "ai00.plugin.response", requestId: message.requestId, channelToken, result: compatibleResult(rejected(message.capabilityId, message.requestId, "host_bridge_failed", error instanceof Error ? error.message : "Capability host bridge failed")) });
      }
    };
    window.addEventListener("message", onMessage);
    iframe.addEventListener("load", () => send({
      type: "ai00.plugin.init",
      protocol: 1,
      instanceId,
      channelToken,
      catalogRelease: options.catalogRelease,
      capabilityVersions: options.capabilityVersions ?? {},
      grantedCapabilities: [...granted]
    }));
    options.container.replaceChildren(iframe);
    return () => {
      ready = false;
      window.removeEventListener("message", onMessage);
      iframe.remove();
    };
  }
  return __toCommonJS(host_exports);
})();
