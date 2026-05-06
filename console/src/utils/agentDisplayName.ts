import type { TFunction } from "i18next";
import type { AgentSummary } from "../api/types/agents";

export const DEFAULT_AGENT_ID = "default";

/** UI label for an agent; `default` id uses i18n, others use API `name` (fallback: id). */
export function getAgentDisplayName(
  agent: Pick<AgentSummary, "id" | "name">,
  t: TFunction,
): string {
  // 优先使用用户自定义的 name
  if (agent.name) {
    return agent.name;
  }
  // 如果没有 name，且 id 是 default，则返回国际化默认名称
  if (agent.id === DEFAULT_AGENT_ID) {
    return t("agent.defaultDisplayName");
  }
  // 最后回退到 id
  return agent.id;
}
