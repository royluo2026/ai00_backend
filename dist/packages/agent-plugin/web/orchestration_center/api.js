(function (root, factory) {
  const exports = factory();
  if (typeof module === 'object' && module.exports) module.exports = exports;
  if (root) root.OrchestrationApi = exports;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  class CapabilityUnavailableError extends Error {}
  class RevisionConflictError extends Error {}
  class CapabilityInvocationError extends Error {
    constructor(message, code) {
      super(message);
      this.code = code || 'capability_failed';
    }
  }

  function createOrchestrationApi(fetcher, capabilityManifest = {}) {
    if (typeof fetcher !== 'function') throw new TypeError('fetcher is required');

    async function invokeMutation(key, payload, idempotencyKey, confirmationToken) {
      const capability = capabilityManifest[key];
      if (!capability?.id || !capability?.version) {
        throw new CapabilityUnavailableError(`Capability ${key} is not approved by Gate 0`);
      }
      if (!idempotencyKey) throw new TypeError('idempotencyKey is required');
      const response = await fetcher(capability.id, {
          version: capability.version,
          expected_resource_version: payload?.expected_resource_version == null
            ? null
            : String(payload.expected_resource_version),
          payload,
          idempotency_key: idempotencyKey,
        });
      const gatewayResult = response?.data;
      const error = gatewayResult?.error || response?.detail || response?.error;
      const code = error?.code;
      if (code === 'version_conflict' || code === 'ORCH_REVISION_CONFLICT') {
        throw new RevisionConflictError('Authoritative panorama revision changed');
      }
      if (response?.success === false || gatewayResult?.ok === false || error) {
        throw new CapabilityInvocationError(error?.message || code || 'Capability invocation failed', code);
      }
      if (gatewayResult?.status === 'accepted' && gatewayResult.operation_ref) return gatewayResult.operation_ref;
      return gatewayResult?.ok === true ? gatewayResult.data : (gatewayResult ?? response);
    }

    async function invokeRead(key, payload) {
      const capability = capabilityManifest[key];
      if (!capability?.id || !capability?.version) {
        throw new CapabilityUnavailableError(`Capability ${key} is not approved by Gate 0`);
      }
      const response = await fetcher(capability.id, { version: capability.version, payload });
      const gatewayResult = response?.data;
      const error = gatewayResult?.error || response?.detail || response?.error;
      if (response?.success === false || gatewayResult?.ok === false || error) {
        throw new CapabilityInvocationError(error?.message || error?.code || 'Capability invocation failed', error?.code);
      }
      return gatewayResult?.ok === true ? gatewayResult.data : gatewayResult;
    }

    // Reads are intentionally not exposed as direct REST fallbacks. Governed
    // read models must be supplied by an approved Capability/Provider adapter;
    // exposing guessed orchestration routes here would make the demo look
    // connected while bypassing Gate 0 and the universal Gateway envelope.
    return { invokeMutation, invokeRead };
  }

  return {
    createOrchestrationApi,
    CapabilityInvocationError,
    CapabilityUnavailableError,
    RevisionConflictError,
  };
});
