# Shared Agent Runtime Secret Design

## Goal

Let a `super_admin` configure one model credential for the shared XiaoRou Agent Runtime on the local test server. All application users consume the same runtime configuration; nobody can read the stored secret back.

## Classification and ownership

- Classification: compatible deployment-control addition.
- Owner: Agent Runtime / `official.agent`.
- Existing governed read surface: `agent.runtime.config.read@1` remains unchanged and returns only model metadata, `has_key`, and a masked preview.
- The secret enrollment endpoint is deployment control, not a model-visible business Capability. It is not exposed to Agent, MCP, plugin tools, or the Catalog.

## Chosen design

Reuse `POST /api/ai/admin-config` as the compatibility endpoint instead of adding another route. The endpoint is enabled only when `ALLOW_LOCAL_RUNTIME_SECRET_ADMIN=1`, requires authenticated `super_admin`, and rejects non-loopback clients.

The backend stores `{api_key, model, api_base}` as one DPAPI CurrentUser-encrypted file outside tracked source. DPAPI binds decryption to the Windows account running the backend; every web user still shares the same backend runtime and therefore the same XiaoRou credential. The response contains status and masked metadata only. The secret is never written to the business database, Catalog, logs, exceptions, audit payloads, or API responses.

Runtime configuration resolution keeps deployment environment variables first, then uses the encrypted local test secret. Saving takes effect on the next request without restarting the service. The existing connection-test endpoint verifies the resolved configuration.

## UI

AI Settings shows editable model, API base, and password-style API Key fields only to administrators when local secret enrollment is enabled. An empty API Key preserves the current secret; replacing it requires a non-empty value. Non-admin users see the existing read-only status.

## Errors and checks

- Disabled feature: `403 local_runtime_secret_admin_disabled`.
- Non-loopback request: `403 local_runtime_secret_admin_loopback_only`.
- Invalid/empty first credential: `422 invalid_runtime_config`.
- DPAPI or atomic file replacement failure: fail without changing the previous file and return a redacted error.
- Tests cover encryption round-trip, no plaintext at rest, access gates, masked responses, environment precedence, and frontend preservation/replacement behavior.

## Governance status

This design does not change a Capability business definition or approval state. Provider artifact hashes must be re-frozen after implementation, and machine tests, human approval, and runtime verification remain separately reported.
