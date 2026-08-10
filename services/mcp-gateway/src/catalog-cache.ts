import { createHash } from "node:crypto";

export interface McpCapabilityDescriptor {
  id: string; major_version: number; description: string;
  exposure: { mcp: boolean }; execution_mode?: string; side_effect_level?: string;
  confirmation_policy?: string; input_schema?: Record<string, unknown>;
  agent_output_schema?: Record<string, unknown> | null;
}
export interface BoundCatalog { releaseId: string; tools: readonly McpCapabilityDescriptor[] }

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`).join(",")}}`;
  return JSON.stringify(value);
}
export class CatalogCache {
  private readonly releases = new Map<string, { digest: string; catalog: BoundCatalog }>();
  bind(releaseId: string, descriptors: McpCapabilityDescriptor[]): BoundCatalog {
    const tools = descriptors.filter(item => item.exposure?.mcp === true
      && (item.execution_mode === undefined || item.execution_mode === "cloud_sync")
      && (item.side_effect_level === undefined || item.side_effect_level === "read")
      && (item.confirmation_policy === undefined || item.confirmation_policy === "none"))
      .sort((a, b) => a.id.localeCompare(b.id) || a.major_version - b.major_version);
    const names = tools.map(item => item.id);
    if (new Set(names).size !== names.length) throw new Error("duplicate_mcp_tool_name");
    const digest = createHash("sha256").update(canonical(tools)).digest("hex");
    const existing = this.releases.get(releaseId);
    if (existing && existing.digest !== digest) throw new Error("catalog_release_drift");
    if (existing) return existing.catalog;
    const catalog = Object.freeze({ releaseId, tools: Object.freeze(tools.map(item => Object.freeze(structuredClone(item)))) });
    this.releases.set(releaseId, { digest, catalog });
    return catalog;
  }
}
