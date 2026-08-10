export interface AgentToolDescriptor {
  id: string; major_version: number; description: string; exposure: { agent: boolean };
  side_effect_level?: string; data_classification?: string; input_schema?: Record<string, unknown>;
}
export interface ToolSelection { catalogRelease: string; tools: AgentToolDescriptor[] }

export class ToolSelector {
  constructor(private readonly maximumTools = 24) {
    if (!Number.isInteger(maximumTools) || maximumTools < 1 || maximumTools > 64) throw new Error("invalid_tool_limit");
  }
  select(goal: string, catalogRelease: string, descriptors: AgentToolDescriptor[]): ToolSelection {
    const terms = new Set(goal.toLowerCase().split(/[^\p{L}\p{N}_.-]+/u).filter(Boolean));
    const score = (item: AgentToolDescriptor): number => {
      const value = `${item.id} ${item.description}`.toLowerCase();
      return [...terms].reduce((total, term) => total + (value.includes(term) ? 1 : 0), 0);
    };
    const tools = descriptors.filter(item => item.exposure?.agent === true)
      .sort((left, right) => score(right) - score(left) || left.id.localeCompare(right.id))
      .slice(0, this.maximumTools).map(item => structuredClone(item));
    return { catalogRelease, tools };
  }
}
