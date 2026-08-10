import { McpServer } from "@modelcontextprotocol/server";
import {
  CapabilityClient,
  CapabilityInvocationError,
  CapabilityResult,
  CapabilitySpec,
  CapabilityTransportError,
} from "./capability-client.js";
import { jsonSchemaToZod } from "./schema.js";

function failureResult(spec: CapabilitySpec, error: unknown): CapabilityResult {
  if (error instanceof CapabilityInvocationError) return error.toResult();
  if (error instanceof CapabilityTransportError) return error.toResult(spec);
  const message = error instanceof Error ? error.message : "Capability invocation failed";
  return new CapabilityTransportError(message, "mcp-unknown-request", "mcp_gateway_error", false).toResult(spec);
}

export async function createAi00Mcp(client: CapabilityClient, token: string): Promise<McpServer> {
  const server = new McpServer({ name: "ai00-capabilities", version: "0.1.0" });
  const specs = await client.list(token);
  for (const spec of specs) {
    // Defense in depth: the backend filters this catalog too. MCP currently has
    // no confirmation UI, so only autonomous cloud reads become tools.
    if (spec.execution !== "cloud" || spec.risk !== "read" || spec.confirmation !== "none") continue;
    server.registerTool(
      spec.id,
      { description: spec.description, inputSchema: jsonSchemaToZod(spec.input_schema) },
      async (args) => {
        try {
          const result = await client.invoke(token, spec, args as Record<string, unknown>);
          return {
            content: [{ type: "text", text: JSON.stringify(result) }],
            structuredContent: result as unknown as Record<string, unknown>,
          };
        } catch (error) {
          const result = failureResult(spec, error);
          return {
            content: [{ type: "text", text: JSON.stringify(result) }],
            structuredContent: result as unknown as Record<string, unknown>,
            isError: true,
          };
        }
      },
    );
  }
  return server;
}