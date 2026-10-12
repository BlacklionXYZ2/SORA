import assert from "node:assert/strict";
import { test } from "node:test";

import { send } from "../shared/bridge.js";
import { canControl, taskStatus } from "../shared/tasks.js";
import { evidenceSections, normaliseTasks, taskFacts, taskTitle } from "../activity/activity-model.js";

const task = {
  task_id: "task-1", status: "completed", effective_backend: "codex", requested_model: "gpt-5",
  companion_brief: "Fix the failing parser test in tests/test_parse.py and explain the cause.",
  working_directory: "C:/Projects/demo", created_at: "2026-10-07T10:00:00Z",
};

test("tasks are listed by SORA's names with Core's status in plain words", () => {
  assert.deepEqual(normaliseTasks({ tasks: [task, { task_id: "../x" }, null] }).map((t) => t.task_id), ["task-1"]);
  assert.equal(taskTitle(task), task.companion_brief);
  assert.equal(taskTitle({ task_id: "task-2" }), "task-2");
  assert.ok(taskTitle({ companion_brief: "x".repeat(200) }).endsWith("…"));
  assert.deepEqual(taskStatus("waiting_for_input"), { label: "Needs your input", tone: "bad" });
  assert.equal(canControl("working"), true);
  assert.equal(canControl("completed"), false);
  assert.deepEqual(taskFacts(task).map((f) => f.label).slice(0, 3), ["Agent", "Model", "Project"]);
  assert.equal(taskFacts(task)[0].value, "Cody");
});

test("evidence reads request, brief, the agent's report, then coverage", () => {
  const sections = evidenceSections({
    task, owner_request: "ask Cody to fix the parser test",
    result: { summary: "Fixed the off-by-one.", conclusion: "Tests pass.",
      files_changed: ["src/parse.py"], commands_run: ["pytest -q"], warnings: [] },
    evidence_note: "Task completion is a validated provider report.",
  });
  assert.deepEqual(sections.map((s) => s.kind),
    ["request", "brief", "result", "list", "list", "coverage"]);
  assert.match(sections[1].title, /not your words/);
  assert.match(sections[2].title, /reported by the agent/);
  assert.equal(sections[2].text, "Fixed the off-by-one.\n\nTests pass.");
  assert.deepEqual(sections[3], { kind: "list", title: "Files changed", items: ["src/parse.py"] });
  const failed = evidenceSections({ task: { ...task, status: "failed" },
    result: { summary: "", error: { code: "timeout", message: "No reply" } } });
  assert.ok(failed.some((s) => s.kind === "failure" && s.text === "timeout: No reply"));
  const running = evidenceSections({ task: { ...task, status: "working" }, result: null });
  assert.match(running.find((s) => s.kind === "pending").text, /Still working/);
});

test("a panel can be opened on an exact task, and nothing else", () => {
  assert.deepEqual(send("panel.open", { panel: "activity", select: "task-1" }),
    { type: "panel.open", panel: "activity", select: "task-1" });
  assert.throws(() => send("panel.open", { panel: "activity", select: "../etc" }), /Invalid selection/);
});

import { agentName, learnAgentNames } from "../shared/tasks.js";

test("agent names come from Core's catalogue, with SORA's names as the fallback", () => {
  assert.equal(agentName("codex-app-server"), "Cody");
  assert.equal(agentName("antigravity"), "Aggie");
  learnAgentNames({ providers: [{ provider: "custom-1", display_name: "Pip" }, { provider: 3 }] });
  assert.equal(agentName("custom-1"), "Pip");
  assert.equal(agentName("custom-2"), "Agent 2");
});

test("a repeated summary is shown once, and machine codes read as words", () => {
  const sections = evidenceSections({ task,
    result: { summary: "I checked the three items.", conclusion: "I checked the three items.\n\n- Done.",
      task_updates: ["changelog_missing", "Ran 3 checks"] } });
  assert.equal(sections.find((s) => s.kind === "result").text, "I checked the three items.\n\n- Done.");
  assert.deepEqual(sections.find((s) => s.title === "Progress notes").items,
    ["Changelog missing", "Ran 3 checks"]);
});
