import { Agent, type AgentMessage, type AgentTool } from "@earendil-works/pi-agent-core";
import { builtinModels } from "@earendil-works/pi-ai/providers/all";
import type { TSchema } from "@earendil-works/pi-ai";
import { CapabilityClient, type CapabilitySpec } from "./capability-client.js";
import { SessionStore } from "./session-store.js";

export type RuntimeEvent =
  | { type: "token"; content: string }
  | { type: "tool_start"; name: string }
  | { type: "tool_end"; name: string; ok: boolean }
  | { type: "done"; session_id: string }
  | { type: "error"; message: string };

function toolName(id: string): string { return id.replaceAll(".", "__").replaceAll("-", "_"); }
export function autonomousCapabilities(specs: CapabilitySpec[]): CapabilitySpec[] {
  return specs.filter(spec => spec.execution === "cloud" && spec.risk === "read" && spec.confirmation === "none");
}
function asTool(spec: CapabilitySpec, client: CapabilityClient, token: string): AgentTool<TSchema> {
  return {
    name: toolName(spec.id), label: spec.id, description: spec.description, parameters: spec.input_schema as TSchema,
    execute: async (_callId, params, signal) => {
      const result = await client.invoke(token, spec, params as Record<string, unknown>, signal);
      return { content: [{ type: "text", text: JSON.stringify(result) }], details: { capabilityId: spec.id, version: spec.version } };
    },
  };
}
function assistantText(messages: readonly unknown[]): string {
  const last = [...messages].reverse().find((message: any) => message?.role === "assistant") as any;
  if (!last) return "";
  if (typeof last.content === "string") return last.content;
  if (Array.isArray(last.content)) return last.content.filter((part: any) => part?.type === "text").map((part: any) => part.text).join("");
  return "";
}

export class PiRuntime {
  private readonly models = builtinModels();
  private readonly locks = new Map<string, Promise<unknown>>();
  constructor(private readonly client: CapabilityClient, private readonly sessions: SessionStore, private readonly modelProvider: string, private readonly modelId: string) {}

  async prompt(ownerUserGid: string, token: string, sessionGid: string, text: string, onEvent?: (event: RuntimeEvent) => void, signal?: AbortSignal): Promise<{ text: string }> {
    const prior = this.locks.get(sessionGid) || Promise.resolve();
    const work = prior.then(() => this.run(ownerUserGid, token, sessionGid, text, onEvent, signal));
    const tracked = work.finally(() => { if (this.locks.get(sessionGid) === tracked) this.locks.delete(sessionGid); });
    this.locks.set(sessionGid, tracked);
    return await work;
  }

  private async run(ownerUserGid: string, token: string, sessionGid: string, text: string, onEvent?: (event: RuntimeEvent) => void, signal?: AbortSignal): Promise<{ text: string }> {
    const [state, specs] = await Promise.all([this.sessions.load(ownerUserGid, sessionGid), this.client.list(token)]);
    const model = this.models.getModel(this.modelProvider, this.modelId);
    if (!model) throw new Error(`Unknown Pi model: ${this.modelProvider}/${this.modelId}`);
    const agent = new Agent({
      initialState: {
        systemPrompt: "你是 AI00 工程共创助手。尊重权限边界；引用知识来源；写操作必须等待显式用户确认。",
        model, thinkingLevel: "medium", messages: state.messages as AgentMessage[],
        tools: autonomousCapabilities(specs).map(spec => asTool(spec, this.client, token)),
      },
      streamFn: this.models.streamSimple.bind(this.models), sessionId: sessionGid, toolExecution: "parallel",
    });
    agent.subscribe(event => {
      if (event.type === "message_update" && event.assistantMessageEvent.type === "text_delta") onEvent?.({ type: "token", content: event.assistantMessageEvent.delta });
      else if (event.type === "tool_execution_start") onEvent?.({ type: "tool_start", name: event.toolName });
      else if (event.type === "tool_execution_end") onEvent?.({ type: "tool_end", name: event.toolName, ok: !event.isError });
    });
    const abort = () => agent.abort();
    signal?.addEventListener("abort", abort, { once: true });
    try {
      await agent.prompt(text);
      const result = { text: assistantText(agent.state.messages) };
      onEvent?.({ type: "done", session_id: sessionGid });
      return result;
    } catch (error) {
      onEvent?.({ type: "error", message: error instanceof Error ? error.message : "Agent failed" });
      throw error;
    } finally {
      signal?.removeEventListener("abort", abort);
      await this.sessions.save(ownerUserGid, sessionGid, { messages: [...agent.state.messages] });
    }
  }
}
