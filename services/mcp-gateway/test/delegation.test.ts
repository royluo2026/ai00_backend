import test from "node:test";
import assert from "node:assert/strict";
import { CapabilityClient } from "../src/capability-client.js";
import { DelegationClient, DelegationSessionCache } from "../src/delegation.js";

test("mcp backend calls use service credential and delegation rather than user bearer", async () => {
  const original = globalThis.fetch;
  let seen: Headers | undefined;
  globalThis.fetch = (async (_input: string | URL | Request, init?: RequestInit) => {
    seen = new Headers(init?.headers);
    return { ok: true, status: 200, json: async () => ({ ok: true, status: "completed", capability_id: "system.echo", major_version: 1, data: {}, evidence: [], artifact_refs: [], warnings: [], correlation: {} }) } as Response;
  }) as typeof fetch;
  try {
    const client = new CapabilityClient("http://base", "mcp-service-secret-with-at-least-32-bytes");
    await client.invoke("delegation-secret", { id: "system.echo", major_version: 1 } as any,
      "rel_0123456789abcdef0123456789abcdef", {}, "req_1");
    assert.equal(seen?.get("authorization"), null);
    assert.equal(seen?.get("x-ai00-token"), null);
    assert.equal(seen?.get("x-ai00-delegation"), "delegation-secret");
    assert.equal(seen?.get("x-ai00-service-credential"), "mcp-service-secret-with-at-least-32-bytes");
  } finally { globalThis.fetch = original; }
});

test("external bearer is exchanged once and cache persists only its hash", async () => {
  let exchanges = 0;
  const exchange = async () => {
    exchanges += 1;
    return { delegationId: "dlg_1", delegationToken: "delegation-secret", catalogRelease: "rel_0123456789abcdef0123456789abcdef",
      expiresAt: new Date(Date.now() + 60_000).toISOString(), descriptors: [] };
  };
  const cache = new DelegationSessionCache();
  const first = await cache.getOrExchange("long-lived-user-bearer", exchange);
  const second = await cache.getOrExchange("long-lived-user-bearer", exchange);
  assert.equal(first, second);
  assert.equal(exchanges, 1);
  assert.equal(JSON.stringify(cache.snapshot()).includes("long-lived-user-bearer"), false);
});

test("concurrent requests share one delegation exchange", async () => {
  let exchanges = 0;
  const cache = new DelegationSessionCache();
  const exchange = async () => {
    exchanges += 1;
    await Promise.resolve();
    return { delegationId: "dlg_1", delegationToken: "secret", catalogRelease: "rel_0123456789abcdef0123456789abcdef",
      expiresAt: new Date(Date.now() + 60_000).toISOString(), descriptors: [] };
  };
  await Promise.all([cache.getOrExchange("same-token", exchange), cache.getOrExchange("same-token", exchange)]);
  assert.equal(exchanges, 1);
});

test("delegation exchange is the only request that carries the external token", async () => {
  const original = globalThis.fetch;
  let seen: Headers | undefined;
  globalThis.fetch = (async (_input: string | URL | Request, init?: RequestInit) => {
    seen = new Headers(init?.headers);
    return { ok: true, status: 200, json: async () => ({ delegation_id: "dlg_1", delegation_token: "secret", catalog_release: "rel_0123456789abcdef0123456789abcdef", expires_at: new Date(Date.now() + 60_000).toISOString(), descriptors: [] }) } as Response;
  }) as typeof fetch;
  try {
    await new DelegationClient("http://base", "service-secret-with-at-least-32-bytes").exchange("external-token");
    assert.equal(seen?.get("x-ai00-token"), "external-token");
    assert.equal(seen?.get("x-ai00-service-credential"), "service-secret-with-at-least-32-bytes");
  } finally { globalThis.fetch = original; }
});
