// Shared words for agent tasks, used by Chat chips and the Activity window. Values come from
// Core's TaskStatus (src/sora/contracts/models.py); nothing here invents a state.

export const TASK_ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/;

const AGENT_NAMES = { codex: "Cody", hermes: "Hermes", antigravity: "Aggie", claude: "Claude" };

// Display names from Core's agent catalogue (provider id -> display_name), when a page has read it.
const catalogueNames = new Map();

/** True once a catalogue with at least one agent has been read. */
export function agentNamesKnown() { return catalogueNames.size > 0; }

/** Remember the names Core's catalogue gives each agent (including custom agents' nicknames). */
export function learnAgentNames(catalogue) {
  for (const entry of Array.isArray(catalogue?.providers) ? catalogue.providers : []) {
    if (typeof entry?.provider === "string" && typeof entry?.display_name === "string"
        && entry.display_name.trim()) {
      catalogueNames.set(entry.provider.toLowerCase(), entry.display_name.trim());
    }
  }
}

/** The name SORA uses for an agent backend (HOW_TO_USE.md), e.g. codex-app-server -> Cody. */
export function agentName(backend) {
  const key = String(backend ?? "").toLowerCase();
  if (catalogueNames.has(key)) return catalogueNames.get(key);
  const known = Object.keys(AGENT_NAMES).find((name) => key === name || key.startsWith(`${name}-`));
  if (known) return AGENT_NAMES[known];
  return key ? key.replace(/^custom[_-]?/, "Agent ") : "an agent";
}

const STATUS_WORDS = {
  planned: "Planned", queued: "Queued", routing: "Starting", reasoning: "Thinking",
  working: "Working", running: "Working", waiting_for_permission: "Needs your OK",
  waiting_for_input: "Needs your input", cancel_requested: "Stopping", interrupted: "Interrupted",
  completed: "Done", succeeded: "Done", failed: "Failed", cancelled: "Cancelled",
};

const ACTIVE = new Set(["queued", "routing", "reasoning", "working", "waiting_for_permission",
  "waiting_for_input"]);

/** Plain words and a tone for a task status: ok, bad (needs attention) or active. */
export function taskStatus(status) {
  const value = String(status ?? "").toLowerCase();
  const done = ["completed", "succeeded"].includes(value);
  const bad = ["failed", "cancelled", "interrupted"].includes(value) || value.startsWith("waiting_for");
  return { label: STATUS_WORDS[value] ?? (value || "Unknown"), tone: done ? "ok" : bad ? "bad" : "active" };
}

/** Whether Core accepts Cancel or Send instruction for this status (TaskPresentation.CanControl). */
export function canControl(status) {
  return ACTIVE.has(String(status ?? "").toLowerCase());
}

export function isActive(status) { return canControl(status) || status === "cancel_requested"; }
