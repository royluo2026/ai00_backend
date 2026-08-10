import { randomUUID } from "node:crypto";
import type { AgentToolDescriptor, ToolSelection } from "./tool-selector.js";
import { ToolSelector } from "./tool-selector.js";

export interface DelegationBootstrap {
  runId: string; catalogRelease: string; selection: ToolSelection;
  delegationId: string; delegationToken: string; expiresAt: string;
}
export class DelegationClient {
  constructor(private readonly backendUrl: string, private readonly serviceCredential: string,
              private readonly selector = new ToolSelector()) {}
  private headers(userToken: string): Record<string, string> {
    return { "Content-Type": "application/json", "X-AI00-Token": userToken, "X-AI00-Service-Credential": this.serviceCredential };
  }
  async preview(userToken: string): Promise<{ release_id: string; descriptors: AgentToolDescriptor[] }> {
    const response = await fetch(`${this.backendUrl}/api/v2/agent-capabilities/catalog-preview`, { headers: this.headers(userToken) });
    const value = await response.json() as { release_id: string; descriptors: AgentToolDescriptor[]; detail?: unknown };
    if (!response.ok) throw new Error(`catalog_preview_failed:${JSON.stringify(value.detail)}`);
    return value;
  }
  async bootstrap(userToken: string, input: {
    goal: string; resourceScopes: string[]; dataScopes?: string[]; runId?: string;
  }): Promise<DelegationBootstrap> {
    const preview = await this.preview(userToken);
    const selection = this.selector.select(input.goal, preview.release_id, preview.descriptors);
    if (!selection.tools.length) throw new Error("no_agent_tools_selected");
    const runId = input.runId ?? `run_${randomUUID().replaceAll("-", "")}`;
    const response = await fetch(`${this.backendUrl}/api/v2/agent-capabilities/delegations`, {
      method: "POST", headers: this.headers(userToken), body: JSON.stringify({
        run_id: runId, catalog_release: preview.release_id,
        capability_scopes: selection.tools.map(item => item.id),
        resource_scopes: input.resourceScopes,
        data_scopes: input.dataScopes ?? [...new Set(selection.tools.map(item => item.data_classification || "internal"))],
      }),
    });
    const value = await response.json() as any;
    if (!response.ok) throw new Error(`delegation_exchange_failed:${JSON.stringify(value.detail)}`);
    return {
      runId, catalogRelease: preview.release_id, selection,
      delegationId: value.delegation_id, delegationToken: value.delegation_token, expiresAt: value.expires_at,
    };
  }
}
