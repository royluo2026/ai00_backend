import { randomUUID } from "node:crypto";
import { McpServer } from "@modelcontextprotocol/server";
import { CapabilityClient } from "./capability-client.js";
import type { BoundCatalog } from "./catalog-cache.js";
import type { DelegationSession } from "./delegation.js";
import { projectResult } from "./projection.js";
import { jsonSchemaToZod } from "./schema.js";

function failure(spec: any, requestId: string, error: unknown): Record<string, unknown> {
  const code = (error instanceof Error ? error.message.split(":")[0] : "mcp_gateway_error") || "mcp_gateway_error";
  return { ok: false, status: "failed", capability_id: spec.id, major_version: spec.major_version,
    data: null, operation_ref: null, artifact_refs: [],
    error: { code, message: "Capability invocation failed", retryable: code.includes("transport") },
    evidence: [], warnings: [], correlation: { request_id: requestId, trace_id: requestId } };
}

export function createAi00Mcp(client: CapabilityClient, session: DelegationSession,
                              catalog: BoundCatalog): McpServer {
  if (session.catalogRelease !== catalog.releaseId) throw new Error("delegation_catalog_mismatch");
  const server = new McpServer({ name: "ai00-capabilities", version: "0.2.0" });
  const scopes = new Set(session.capabilityScopes ?? catalog.tools.map(item => item.id));
  for (const spec of catalog.tools.filter(item => scopes.has(item.id))) {
    server.registerTool(
      spec.id,
      { description: spec.description, inputSchema: jsonSchemaToZod(spec.input_schema || { type: "object", properties: {} }) },
      async (args) => {
        const requestId = `mcp_${randomUUID().replaceAll("-", "")}`;
        try {
          const full = await client.invoke<any>(session.delegationToken, spec, catalog.releaseId,
            args as Record<string, unknown>, requestId);
          const result = projectResult(full, spec.agent_output_schema);
          return { content: [{ type: "text", text: JSON.stringify(result) }], structuredContent: result };
        } catch (error) {
          const result = failure(spec, requestId, error);
          return { content: [{ type: "text", text: JSON.stringify(result) }], structuredContent: result, isError: true };
        }
      },
    );
  }
  return server;
}
