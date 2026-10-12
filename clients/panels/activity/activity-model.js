// Activity state with no DOM: Core's task list and one task's evidence, in plain sections.
// The agent's result is a provider report, so it is labelled as one; nothing is inferred.

import { TASK_ID, agentName, canControl, taskStatus } from "../shared/tasks.js";

export { agentName, canControl, taskStatus };

/** A one-line title for a task: SORA's brief if there is one, otherwise the task ID. */
export function taskTitle(task) {
  const brief = String(task?.companion_brief ?? "").replace(/\s+/g, " ").trim();
  if (!brief) return String(task?.task_id ?? "Task");
  return brief.length > 90 ? `${brief.slice(0, 89)}…` : brief;
}

export function normaliseTasks(page) {
  const tasks = Array.isArray(page?.tasks) ? page.tasks : [];
  return tasks.filter((task) => task && TASK_ID.test(String(task.task_id ?? "")));
}

const LISTS = [
  ["files_changed", "Files changed"],
  ["commands_run", "Commands run"],
  ["actions_taken", "What it did"],
  ["files_read", "Files read"],
  ["warnings", "Warnings"],
  ["uncertainties", "Uncertainties"],
  ["task_updates", "Progress notes"],
  ["artifacts", "Artifacts"],
];

/**
 * Sections for the detail pane, in reading order: the owner's own request first, then SORA's
 * brief, then the agent's report, then Core's coverage note.
 */
export function evidenceSections(evidence) {
  const sections = [];
  const task = evidence?.task ?? {};
  if (evidence?.owner_request) {
    sections.push({ kind: "request", title: "Your request", text: String(evidence.owner_request) });
  }
  if (task.companion_brief) {
    sections.push({ kind: "brief", title: "SORA's brief to the agent (not your words)",
      text: String(task.companion_brief) });
  }
  const result = evidence?.result;
  if (result && typeof result === "object") {
    // Agents often repeat their summary inside the conclusion; show that text once.
    const summary = String(result.summary ?? "").trim();
    const conclusion = String(result.conclusion ?? "").trim();
    const text = !summary ? conclusion
      : !conclusion || conclusion.includes(summary) ? conclusion || summary
      : summary.includes(conclusion) ? summary : `${summary}\n\n${conclusion}`;
    sections.push({ kind: "result", title: "Result (reported by the agent)", text: text || "No summary." });
    if (result.error && typeof result.error === "object") {
      sections.push({ kind: "failure", title: "Failure",
        text: `${result.error.code ?? "error"}: ${result.error.message ?? ""}`.trim() });
    }
    for (const [key, title] of LISTS) {
      const items = Array.isArray(result[key]) ? result[key] : [];
      if (items.length) {
        sections.push({ kind: "list", title, items: items.map(readable) });
      }
    }
    if (result.changelog_path) {
      sections.push({ kind: "note", title: "Changelog (reported)", text: String(result.changelog_path) });
    }
  } else {
    sections.push({ kind: "pending", title: "Result",
      text: canControl(task.status) ? "Still working. This updates by itself."
        : "No result was stored for this task." });
  }
  if (evidence?.evidence_note) {
    sections.push({ kind: "coverage", title: "What this proves", text: String(evidence.evidence_note) });
  }
  return sections;
}

// Machine codes such as "changelog_missing" read as words ("Changelog missing").
function readable(item) {
  if (typeof item !== "string") return JSON.stringify(item);
  if (/^[a-z]+(?:_[a-z]+)+$/.test(item)) {
    const words = item.replace(/_/g, " ");
    return words[0].toUpperCase() + words.slice(1);
  }
  return item;
}

/** Facts shown under the title: agent, model, project. Only values the task record has. */
export function taskFacts(task) {
  const facts = [];
  const add = (label, value) => { if (value) facts.push({ label, value: String(value) }); };
  add("Agent", agentName(task?.effective_backend || task?.requested_backend));
  add("Model", task?.requested_model);
  add("Effort", task?.requested_effort);
  add("Project", task?.working_directory);
  add("Mode", task?.workspace_mode);
  if (task?.created_at) add("Started", new Date(task.created_at).toLocaleString("en-GB"));
  return facts;
}
