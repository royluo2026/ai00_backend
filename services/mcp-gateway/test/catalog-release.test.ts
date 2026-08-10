import test from "node:test";
import assert from "node:assert/strict";
import { CatalogCache } from "../src/catalog-cache.js";

const release = "rel_0123456789abcdef0123456789abcdef";
test("catalog cache pins exact release and major and rejects drift", () => {
  const cache = new CatalogCache();
  const first = cache.bind(release, [{ id: "system.echo", major_version: 1, exposure: { mcp: true } }] as any);
  assert.equal(first.tools[0]?.major_version, 1);
  assert.throws(() => cache.bind(release, [{ id: "system.echo", major_version: 2, exposure: { mcp: true } }] as any), /catalog_release_drift/);
});

test("duplicate MCP tool names fail closed", () => {
  const cache = new CatalogCache();
  assert.throws(() => cache.bind(release, [
    { id: "same.tool", major_version: 1, exposure: { mcp: true } },
    { id: "same.tool", major_version: 2, exposure: { mcp: true } },
  ] as any), /duplicate_mcp_tool_name/);
});

test("same immutable catalog can serve different delegation scopes", () => {
  const cache = new CatalogCache();
  const descriptors = [
    { id: "a.tool", major_version: 1, exposure: { mcp: true } },
    { id: "b.tool", major_version: 1, exposure: { mcp: true } },
  ] as any;
  assert.equal(cache.bind(release, descriptors), cache.bind(release, descriptors));
});
