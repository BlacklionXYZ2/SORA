import { CoreApi, CoreError } from "../shared/api.js";
import { onHostMessage } from "../shared/bridge.js";
import { icon } from "../shared/icons.js";
import { agentNamesKnown, learnAgentNames } from "../shared/tasks.js";
import { setUpWindow } from "../shared/window.js";
import {
  agentName, canControl, evidenceSections, normaliseTasks, taskFacts, taskStatus, taskTitle,
} from "./activity-model.js";

const POLL_MS = 4000;
const api = new CoreApi();
const els = {
  tasks: document.getElementById("tasks"),
  detail: document.getElementById("detail"),
  refresh: document.getElementById("refresh"),
};
const state = {
  tasks: [], selected: null, evidence: null, error: "", confirm: "", busy: false,
  instruction: "",
};
let toastTimer = 0;
let pollTimer = 0;

setUpWindow();
els.refresh.innerHTML = icon("retry", "Refresh");

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "html") node.innerHTML = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (key in node) node[key] = value;
    else node.setAttribute(key, value === true ? "" : value);
  }
  node.append(...children.filter((child) => child !== null && child !== undefined && child !== false));
  return node;
}

function toast(text) {
  document.querySelector(".toast")?.remove();
  const note = el("div", { class: "toast", role: "status" }, text);
  document.body.append(note);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => note.remove(), 4500);
}

function message(error) {
  return error instanceof CoreError ? error.message : String(error?.message ?? error);
}

function when(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const today = new Date().toDateString() === date.toDateString();
  return today ? date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })
    : date.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

// ---------- list ----------

function renderList() {
  if (!state.tasks.length) {
    els.tasks.replaceChildren(el("li", { class: "empty-detail" },
      state.error || "No agent work yet. Ask SORA to have Cody, Hermes, Aggie or Claude do something."));
    return;
  }
  els.tasks.replaceChildren(...state.tasks.map((task) => {
    const status = taskStatus(task.status);
    return el("li", {}, el("button", {
      class: "task-item", type: "button", "aria-current": task.task_id === state.selected ? "true" : false,
      onclick: () => select(task.task_id),
    },
    el("span", { class: "row" },
      el("span", { class: "who" }, agentName(task.effective_backend || task.requested_backend)),
      el("span", { class: `state ${status.tone}` }, status.label),
      el("span", { class: "when" }, when(task.created_at))),
    el("span", { class: "what" }, taskTitle(task))));
  }));
}

// ---------- detail ----------

function renderDetail() {
  const evidence = state.evidence;
  if (!state.selected) {
    els.detail.replaceChildren(el("div", { class: "empty-detail" }, "Choose a task to see what was asked and what came back."));
    return;
  }
  if (!evidence) {
    els.detail.replaceChildren(el("div", { class: "empty-detail" }, state.error || "Loading…"));
    return;
  }
  const task = evidence.task;
  const status = taskStatus(task.status);
  const parts = [
    el("h1", {}, taskTitle(task), " ", el("span", { class: `state ${status.tone}` }, status.label)),
    el("div", { class: "facts" }, ...taskFacts(task).map((fact) => el("span", {}, el("b", {}, fact.label + " "), fact.value))),
  ];
  if (canControl(task.status)) parts.push(controls(task));
  for (const section of evidenceSections(evidence)) {
    parts.push(el("section", { class: `section ${section.kind}` },
      el("h2", {}, section.title),
      section.items ? el("ul", {}, ...section.items.map((item) => el("li", {}, item)))
        : el("p", {}, section.text)));
  }
  const scroll = els.detail.scrollTop;
  els.detail.replaceChildren(...parts);
  els.detail.scrollTop = scroll;
}

function controls(task) {
  const box = el("div", { class: "controls" });
  const input = el("textarea", { class: "input", rows: 2, maxLength: 8000, value: state.instruction,
    placeholder: `Tell ${agentName(task.effective_backend || task.requested_backend)} something about this task…`,
    oninput: (event) => { state.instruction = event.target.value; send.disabled = !state.instruction.trim() || state.busy; } });
  const send = el("button", { class: "btn primary", type: "button", disabled: !state.instruction.trim() || state.busy,
    onclick: () => steer(task.task_id) }, "Send instruction");
  const cancel = el("button", { class: "btn danger", type: "button", disabled: state.busy,
    onclick: () => { state.confirm = task.task_id; renderDetail(); } }, "Cancel task");
  box.append(input);
  if (state.confirm === task.task_id) {
    box.append(el("div", { class: "confirm" },
      el("span", {}, "Stop this task completely? The agent stops working on it."),
      el("button", { class: "btn", type: "button", onclick: () => { state.confirm = ""; renderDetail(); } }, "Keep it"),
      el("button", { class: "btn danger", type: "button", onclick: () => cancelTask(task.task_id) }, "Cancel task")));
  } else {
    box.append(el("div", { class: "buttons" }, cancel, send));
  }
  return box;
}

// ---------- data ----------

async function loadList() {
  try {
    state.tasks = normaliseTasks(await api.tasks(50));
    state.error = "";
  } catch (error) {
    state.error = message(error);
  }
  renderList();
}

async function loadDetail() {
  if (!state.selected) return;
  const id = state.selected;
  try {
    const evidence = await api.taskEvidence(id);
    if (state.selected !== id) return;
    state.evidence = evidence;
    state.error = "";
  } catch (error) {
    if (state.selected !== id) return;
    state.evidence = null;
    state.error = `That task is not available: ${message(error)}`;
  }
  renderDetail();
}

async function select(id) {
  if (state.selected !== id) {
    state.selected = id;
    state.evidence = null;
    state.instruction = "";
    state.confirm = "";
  }
  renderList();
  renderDetail();
  await loadDetail();
}

async function steer(id) {
  const instruction = state.instruction.trim();
  if (!instruction) return;
  state.busy = true;
  renderDetail();
  try {
    await api.steerTask(id, instruction);
    state.instruction = "";
    toast("Instruction sent.");
  } catch (error) {
    toast(`Not sent: ${message(error)}`);
  } finally {
    state.busy = false;
    await loadDetail();
  }
}

async function cancelTask(id) {
  state.busy = true;
  state.confirm = "";
  renderDetail();
  try {
    await api.cancelTask(id);
    toast("Cancel requested.");
  } catch (error) {
    toast(`Not cancelled: ${message(error)}`);
  } finally {
    state.busy = false;
    await Promise.all([loadList(), loadDetail()]);
  }
}

async function poll() {
  clearTimeout(pollTimer);
  await learnNames();
  await loadList();
  const current = state.tasks.find((task) => task.task_id === state.selected);
  // Re-read evidence while a task is still running, or when its state changed.
  if (state.selected && (!state.evidence || current?.status !== state.evidence.task?.status
      || canControl(current?.status))) {
    await loadDetail();
  }
  pollTimer = setTimeout(poll, POLL_MS);
}

els.refresh.addEventListener("click", () => poll());
onHostMessage((data) => {
  if (data.type === "host.select" && typeof data.id === "string") select(data.id);
});

const wanted = new URLSearchParams(location.search).get("task");
renderList();
renderDetail();
async function learnNames() {
  if (agentNamesKnown()) return;
  try { learnAgentNames(await api.agents()); } catch { /* Core starting: retry on the next poll */ }
}
await learnNames();
await loadList();
if (wanted) await select(wanted);
else if (state.tasks.length) await select(state.tasks[0].task_id);
pollTimer = setTimeout(poll, POLL_MS);
