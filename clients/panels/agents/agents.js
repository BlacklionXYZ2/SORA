import { CoreApi, CoreError } from "../shared/api.js";
import { hosted, onHostMessage, pickFile, send as sendToHost } from "../shared/bridge.js";
import { icon } from "../shared/icons.js";
import { setUpWindow } from "../shared/window.js";
import {
  AUTOMATIC, AgentsCore, EFFORTS, PROJECT_AGENT, PURPOSE_MAX, PURPOSE_ROWS_MAX, TASK_MAX,
  TaskSubmission, WORKSPACE_MODES, agentName, agentOptionLabel, agentState, anyEnabled,
  checkPurposeRows, chooseAgent, chooseModel, confirmation, defaultEffortLabel, defaultModelLabel,
  effortChoices, emptyForm, findAgent, findModel, isDirty, learnAgentNames, modelLabel, modelNotes,
  normaliseCatalogue, purposeBase, purposeLine, purposeSaveRequest, purposeSettingsKey,
  purposeSuggestions, purposesChanged, rebasePurposes, receiptFacts, receiptTaskId,
  reconcileSelection, routesToProjectAgent, staleCatalogueError, startState, taskBody,
} from "./agents-model.js";

const MODELS_SHOWN = 30;
const api = new CoreApi();
const core = new AgentsCore(api);
const els = {
  agents: document.getElementById("agents"),
  foot: document.getElementById("list-foot"),
  detail: document.getElementById("detail"),
  reload: document.getElementById("reload"),
};
const state = {
  catalogue: null,
  catalogueCurrent: false,   // read since Core was last (re)usable; Start needs it
  loading: "",               // "read" | "refresh" while a catalogue call runs
  loadError: "",
  readAt: null,
  selectionNotice: "",
  view: AUTOMATIC,           // the agent shown in the detail pane
  form: emptyForm(),
  submission: new TaskSubmission(),
  starting: false,           // the pre-send check and POST are in flight
  confirm: null,             // {body, retry} while the inline confirmation is open
  discardConfirm: false,
  outcome: null,             // {tone, title, text} after a start that was not accepted
  canUseCore: true,          // host.core; a browser preview never sends it
  purposes: null,            // {agentId, name, key, base, rows, saving, notice, error}
  purposesLoading: "",
  purposesError: null,       // {agentId, text}
  showAllModels: false,
};
let toastTimer = 0;
let loadSeq = 0;
let started = false;
let live = {};               // nodes updated while typing, without a re-render
let shownInList = null;

setUpWindow();
els.reload.innerHTML = icon("retry", "Read the agent list again");

// Registered before the first await: the host sends host.core as soon as the page is ready.
onHostMessage((data) => {
  if (data.type !== "host.core" || typeof data.canUseCore !== "boolean") return;
  const was = state.canUseCore;
  state.canUseCore = data.canUseCore;
  // While the host blocks Core (managed start or stop, or disconnected) the list may go stale.
  if (!data.canUseCore) state.catalogueCurrent = false;
  renderAll();
  if (data.canUseCore && !was && started) loadCatalogue(false);
});

// ---------- small DOM helpers ----------

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "html") node.innerHTML = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (key in node && key !== "list") node[key] = value;
    else node.setAttribute(key, value === true ? "" : value);
  }
  node.append(...children.flat().filter((child) => child !== null && child !== undefined && child !== false));
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
  const text = error instanceof CoreError ? error.message : String(error?.message ?? error);
  // Core's words are shown as they are, ending as a sentence so ours can follow.
  return /[.!?…)]$/.test(text.trim()) ? text.trim() : `${text.trim()}.`;
}

function when(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

/** Re-render without losing the owner's place in a text box. */
function keepFocus(container, build) {
  const active = document.activeElement;
  const key = active && container.contains(active) ? active.dataset?.focus : "";
  let start = null;
  let end = null;
  try { start = active.selectionStart; end = active.selectionEnd; } catch { /* not a text box */ }
  const scroll = container.scrollTop;
  build();
  container.scrollTop = scroll;
  if (!key) return;
  const next = container.querySelector(`[data-focus="${key}"]`);
  if (!next || next.disabled) return;
  next.focus({ preventScroll: true });
  try { if (start !== null && start !== undefined) next.setSelectionRange(start, end); } catch { /* select */ }
}

/** Focus a control after the next render, scrolling only the detail pane to show it. */
function focusLater(key) {
  requestAnimationFrame(() => {
    const node = els.detail.querySelector(`[data-focus="${key}"]`);
    if (!node) return;
    node.focus({ preventScroll: true });
    const box = els.detail.getBoundingClientRect();
    const at = node.getBoundingClientRect();
    if (at.bottom > box.bottom - 12) els.detail.scrollTop += at.bottom - box.bottom + 24;
    else if (at.top < box.top + 12) els.detail.scrollTop -= box.top - at.top + 24;
  });
}

function openPanel(panel, select) {
  sendToHost("panel.open", select ? { panel, select } : { panel });
  if (!hosted) toast(`${panel === "activity" ? "Activity" : "Settings"} opens in SORA's app.`);
}

function frozen() {
  return state.submission.attempted || state.starting || Boolean(state.confirm);
}

function canLoad() {
  return !state.loading && !state.starting && !state.submission.sending && !state.submission.unconfirmed;
}

function purposesDirty() {
  return Boolean(state.purposes && purposesChanged(state.purposes.base.saved, state.purposes.rows));
}

// ---------- quit protection ----------

let reportedBusy = false;
let reportedDirty = false;

function report() {
  const busy = state.starting || state.submission.sending || Boolean(state.purposes?.saving);
  if (busy !== reportedBusy) {
    reportedBusy = busy;
    sendToHost("panel.busy", { busy });
  }
  const dirty = isDirty({ intent: state.form.intent, submission: state.submission, purposes: state.purposes });
  if (dirty !== reportedDirty) {
    reportedDirty = dirty;
    sendToHost("panel.dirty", { dirty });
  }
}

// ---------- list ----------

function mark(agent) {
  if (!agent) return el("span", { class: "mark auto", html: icon("bolt") });
  const letter = (agent.name.match(/[A-Za-z0-9]/)?.[0] ?? "?").toUpperCase();
  return el("span", { class: `mark${agent.enabled ? "" : " off"}`, "aria-hidden": "true" }, letter);
}

function listItem(agent) {
  const id = agent ? agent.id : AUTOMATIC;
  const status = agent ? agentState(agent.state) : null;
  const unsaved = agent && state.purposes?.agentId === agent.id && purposesDirty();
  const sub = agent
    ? agent.models.length ? `${agent.models.length} model${agent.models.length === 1 ? "" : "s"} · ${agent.purpose}` : agent.purpose
    : "SORA picks the agent from your configured defaults.";
  return el("li", {}, el("button", {
    class: "agent-item", type: "button", "aria-current": state.view === id ? "true" : false,
    onclick: () => selectAgent(id),
  },
  mark(agent),
  el("span", { class: "agent-main" },
    el("span", { class: "row" },
      el("span", { class: "who" }, agent ? agent.name : "Automatic"),
      status ? el("span", { class: `state ${status.tone}` }, status.label) : null,
      agent && !agent.enabled ? el("span", { class: "badge warn" }, "Off") : null,
      unsaved ? el("span", { class: "badge muted", title: "Model purposes not saved yet" }, "Unsaved") : null),
    el("span", { class: "what" }, sub))));
}

/** Scroll the list (a strip in narrow windows) just enough to show the chosen agent. */
function revealCurrent() {
  const item = els.agents.querySelector('[aria-current="true"]');
  if (!item) return;
  const box = els.agents.getBoundingClientRect();
  const at = item.getBoundingClientRect();
  if (at.left < box.left) els.agents.scrollLeft -= box.left - at.left + 8;
  else if (at.right > box.right) els.agents.scrollLeft += at.right - box.right + 8;
  if (at.top < box.top) els.agents.scrollTop -= box.top - at.top + 8;
  else if (at.bottom > box.bottom) els.agents.scrollTop += at.bottom - box.bottom + 8;
}

function renderList() {
  const agents = state.catalogue?.agents ?? [];
  const items = [listItem(null), ...agents.map(listItem)];
  if (state.catalogue && !agents.length) {
    items.push(el("li", { class: "empty-detail" }, "Core lists no agents. Turn one on in Settings."));
  }
  const { scrollLeft, scrollTop } = els.agents;
  els.agents.replaceChildren(...items);
  els.agents.scrollLeft = scrollLeft;
  els.agents.scrollTop = scrollTop;
  if (shownInList !== state.view) {
    shownInList = state.view;
    revealCurrent();
  }
  els.reload.disabled = !canLoad();

  const refreshing = state.loading === "refresh";
  const refreshBlocked = !canLoad() || !state.canUseCore;
  // Core's Hermes notice matters only when Hermes is one of the agents a refresh will ask.
  const hermes = state.catalogue?.agents.some((agent) => agent.id.startsWith("hermes"));
  const readAt = state.readAt
    ? `Read at ${state.readAt.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}${state.catalogueCurrent ? "" : " (may be out of date)"}`
    : "";
  els.foot.replaceChildren(...[
    el("div", { class: "foot-row" },
      el("button", {
        class: "btn", type: "button", disabled: refreshBlocked, onclick: () => loadCatalogue(true),
        title: !state.canUseCore ? "SORA's Core is not available right now."
          : state.submission.unconfirmed ? "Retry or discard the unconfirmed task first." : "",
        html: icon("retry") + `<span>${refreshing ? "Refreshing…" : "Refresh models"}</span>`,
      }),
      readAt ? el("span", { class: "notice" }, readAt) : null),
    refreshing ? el("span", { class: "state active" }, "Asking each agent's program for its models") : null,
    el("p", { class: "notice" },
      "Refresh asks each agent's program for its model list. No model runs, and SORA's own model does not change.",
      hermes && state.catalogue.hermesNotice ? ` ${state.catalogue.hermesNotice}` : ""),
  ].filter(Boolean));
}

// ---------- detail: banner and header ----------

function banner() {
  const lines = [];
  let action = null;
  if (!state.canUseCore) {
    lines.push("SORA's Core is not available right now (it may be starting or stopping). Your draft is kept, and nothing will be sent.");
  }
  if (state.loadError) lines.push(state.loadError);
  // (A retry of a pinned attempt does not need a fresh list, and reading waits until it is settled.)
  if (state.catalogue && !state.catalogueCurrent && state.canUseCore && !state.loading
      && !state.submission.unconfirmed && !state.submission.sending) {
    lines.push("The agent list may be out of date. Read it again before starting a task.");
    if (canLoad()) action = el("button", { class: "btn", type: "button", onclick: () => loadCatalogue(false) }, "Read list");
  }
  if (state.selectionNotice) lines.push(state.selectionNotice);
  if (!lines.length) return null;
  return el("div", { class: "banner", role: "status", html: icon("alert") },
    el("span", { class: "banner-text" }, lines.join(" ")), action);
}

function header(agent) {
  if (!agent) {
    return el("div", { class: "detail-head" }, mark(null),
      el("div", { class: "head-main" },
        el("h1", {}, "Automatic routing"),
        el("p", { class: "lead" }, "SORA chooses the agent from your configured defaults and each agent's usage description.")));
  }
  const status = agentState(agent.state);
  return el("div", { class: "detail-head" }, mark(agent),
    el("div", { class: "head-main" },
      el("h1", {}, agent.name, " ", el("span", { class: `state ${status.tone}` }, status.label),
        agent.enabled ? null : el("span", { class: "badge warn" }, "Off in Settings")),
      agent.purpose ? el("p", { class: "lead" }, agent.purpose) : null));
}

// ---------- detail: the task card ----------

function codyName() {
  return findAgent(state.catalogue, PROJECT_AGENT)?.name ?? agentName(PROJECT_AGENT);
}

function field(label, id, control, note) {
  return el("div", { class: "field-block" }, el("label", { for: id }, label), control, note ?? null);
}

function agentSelect(disabled) {
  const form = state.form;
  const agents = state.catalogue?.agents ?? [];
  const known = form.agent === null || form.agent === AUTOMATIC || agents.some((agent) => agent.id === form.agent);
  return el("select", { class: "input", id: "task-agent", "data-focus": "agent", disabled,
    onchange: (event) => setAgent(event.target.value === "__none" ? null : event.target.value) },
  el("option", { value: AUTOMATIC, selected: form.agent === AUTOMATIC }, "Automatic"),
  form.agent === null ? el("option", { value: "__none", selected: true, disabled: true }, "Choose an agent") : null,
  ...agents.map((agent) => el("option", { value: agent.id, selected: form.agent === agent.id }, agentOptionLabel(agent))),
  known ? null : el("option", { value: form.agent, selected: true }, `${agentName(form.agent)} (no longer listed)`));
}

function modelSelect(agent, disabled) {
  const form = state.form;
  const models = agent?.models ?? [];
  const known = !form.model || models.some((model) => model.id === form.model);
  return el("select", { class: "input", id: "task-model", "data-focus": "model",
    disabled: disabled || !form.agent,
    onchange: (event) => setModel(event.target.value === "__none" ? null : event.target.value) },
  el("option", { value: "", selected: form.model === "" }, form.agent ? defaultModelLabel(agent) : "Default"),
  form.model === null ? el("option", { value: "__none", selected: true, disabled: true }, "Choose a model") : null,
  ...models.map((model) => el("option", { value: model.id, selected: form.model === model.id }, modelLabel(model))),
  known ? null : el("option", { value: form.model, selected: true }, `${form.model} (no longer listed)`));
}

function effortSelect(agent, disabled) {
  const form = state.form;
  const efforts = effortChoices(agent, form.model);
  const known = !form.effort || efforts.includes(form.effort);
  return el("select", { class: "input", id: "task-effort", "data-focus": "effort",
    disabled: disabled || (!efforts.length && known),
    onchange: (event) => { state.form.effort = event.target.value; renderDetail(); } },
  el("option", { value: "", selected: form.effort === "" }, defaultEffortLabel(agent, form.model)),
  ...efforts.map((effort) => el("option", { value: effort, selected: form.effort === effort }, effort)),
  known || !EFFORTS.includes(form.effort) ? null : el("option", { value: form.effort, selected: true }, form.effort));
}

function modeSelect(disabled) {
  const cody = codyName();
  const labels = {
    direct: "Direct: works in the folder",
    isolated: `Isolated: separate worktree (${cody} only)`,
    "read-only": "Read-only",
  };
  return el("select", { class: "input", id: "task-mode", "data-focus": "mode", disabled,
    onchange: (event) => { state.form.mode = event.target.value; renderDetail(); } },
  el("option", { value: "", selected: state.form.mode === "" }, "Saved, or from the task"),
  ...WORKSPACE_MODES.map((mode) => el("option", { value: mode, selected: state.form.mode === mode }, labels[mode])));
}

function modelInfo(agent) {
  const form = state.form;
  if (!form.agent) return null;
  const model = findModel(agent, form.model);
  if (!model) {
    if (form.model === "") {
      return el("p", { class: "notice" }, "Core uses the saved preferred model if there is one, otherwise the agent's own default. ",
        "Preferences are in Settings.");
    }
    return null;
  }
  const purpose = purposeLine(model);
  return el("div", { class: "model-info" },
    purpose ? el("p", {}, purpose) : null,
    el("p", { class: "notice" }, `${model.id} · ${modelNotes(model).join(" · ")}. A listed model is not proof that it runs.`));
}

function taskCard() {
  const submission = state.submission;
  const form = state.form;
  const locked = frozen();
  const agent = form.agent ? findAgent(state.catalogue, form.agent) : null;

  const directory = el("input", { class: "input", id: "task-project", "data-focus": "directory", type: "text",
    value: form.directory, spellcheck: false, disabled: locked, maxLength: 4096,
    placeholder: "Blank: the agent's saved project",
    oninput: (event) => { state.form.directory = event.target.value; updateLive(); } });
  const browse = el("button", { class: "btn", type: "button", disabled: locked, title: "Choose a project folder",
    html: icon("folder") + "<span>Browse</span>", onclick: browseProject });

  const intent = el("textarea", { class: "input", id: "task-intent", "data-focus": "intent", rows: 5,
    maxLength: TASK_MAX, value: form.intent, disabled: locked,
    placeholder: "Describe the work for the agent. This is separate from Chat.",
    oninput: (event) => { state.form.intent = event.target.value; updateLive(); },
    onkeydown: (event) => {
      if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) { event.preventDefault(); askStart(); }
    } });

  live.counter = el("span", { class: "counter" });
  live.hint = el("span", { class: "hint" });
  live.start = el("button", { class: "btn primary", type: "button", "data-focus": "start",
    html: icon("send"), onclick: askStart }, el("span", {}, ""));

  // Shown while typing a folder too, so it is a live node rather than part of a re-render.
  live.route = el("p", { class: "notice route-note" },
    `With a project folder or mode set, Core sends an automatic task to ${codyName()}.`);

  const parts = [
    el("div", { class: "card-head" },
      el("h2", { html: icon("task") }, el("span", {}, "Delegate a task")),
      el("span", { class: "notice" }, "SORA sends exactly what you choose here.")),
    el("div", { class: "task-grid" },
      field("Agent", "task-agent", agentSelect(locked)),
      field("Model", "task-model", modelSelect(agent, locked)),
      field("Effort", "task-effort", effortSelect(agent, locked))),
    modelInfo(agent),
    el("div", { class: "task-grid wide" },
      field("Project folder", "task-project", el("div", { class: "project-row" }, directory, browse)),
      field("Mode", "task-mode", modeSelect(locked))),
    live.route,
    field("Task", "task-intent", intent),
  ];

  if (state.outcome) parts.push(outcomeBox());
  if (submission.confirmed) parts.push(receiptBox(submission.receipt));

  // An open confirmation replaces the buttons, so the only choices are its own.
  if (state.confirm) {
    parts.push(confirmStrip());
  } else if (state.discardConfirm) {
    parts.push(discardStrip());
  } else {
    const buttons = [];
    if (submission.unconfirmed && !state.starting) {
      buttons.push(el("button", { class: "btn", type: "button", onclick: () => openPanel("activity") }, "Open Activity"),
        el("button", { class: "btn danger", type: "button",
          onclick: () => { state.discardConfirm = true; renderDetail(); focusLater("discard-no"); } },
        "Discard attempt…"));
    }
    if (submission.confirmed) {
      buttons.push(el("button", { class: "btn", type: "button", "data-focus": "new-task", onclick: newTask }, "New task"));
    } else {
      buttons.push(live.start);
    }
    parts.push(el("div", { class: "task-actions" }, live.counter, live.hint, el("span", { class: "spacer" }), ...buttons));
  }

  updateLive();
  return el("section", { class: `card task${locked ? " locked" : ""}`, "aria-label": "Delegate a task" }, ...parts);
}

/** Counter, Start button and hint, updated while typing (no re-render, so the caret stays put). */
function updateLive() {
  if (!live.start) return;
  const length = state.form.intent.trim().length;
  live.counter.textContent = `${length.toLocaleString("en-GB")} / ${TASK_MAX.toLocaleString("en-GB")}`;
  const start = startState({
    form: state.form, catalogue: state.catalogue, catalogueCurrent: state.catalogueCurrent,
    canUseCore: state.canUseCore, submission: state.submission, loading: Boolean(state.loading),
  });
  const starting = state.starting;
  live.start.disabled = starting || !start.enabled;
  live.start.lastChild.textContent = starting ? "Starting…" : start.label;
  live.hint.textContent = starting ? "Sending to Core…" : start.reason;
  live.route.hidden = !routesToProjectAgent(state.form);
  report();
}

function factList(lines) {
  return el("dl", { class: "summary" }, ...lines.flatMap((line) => [
    el("dt", {}, line.label), el("dd", { class: line.mono ? "mono" : "" }, line.value)]));
}

function confirmStrip() {
  const { body, retry } = state.confirm;
  const summary = confirmation(body, state.catalogue, { retry });
  return el("div", { class: "confirm task-confirm", role: "group", "aria-label": "Confirm the task" },
    el("span", { class: "confirm-question" }, summary.question),
    factList(summary.lines),
    ...summary.warnings.map((warning) => el("p", { class: "confirm-warning" }, warning)),
    el("div", { class: "confirm-buttons" },
      el("button", { class: "btn", type: "button", "data-focus": "confirm-no",
        onclick: () => { state.confirm = null; renderDetail(); focusLater("start"); } }, "Not yet"),
      el("button", { class: "btn primary", type: "button", onclick: confirmStart },
        retry ? "Retry with the same key" : "Start task")));
}

function discardStrip() {
  return el("div", { class: "confirm", role: "group", "aria-label": "Discard the unconfirmed task" },
    el("span", {}, "Discard this unconfirmed task? If Core did start it, starting again makes a second task. Check Activity first."),
    el("div", { class: "confirm-buttons" },
      el("button", { class: "btn", type: "button", "data-focus": "discard-no",
        onclick: () => { state.discardConfirm = false; renderDetail(); } }, "Keep it"),
      el("button", { class: "btn danger", type: "button", onclick: discardAttempt }, "Discard")));
}

function outcomeBox() {
  const { tone, title, text } = state.outcome;
  return el("div", { class: `outcome ${tone}`, role: "status" },
    el("strong", {}, title), el("p", {}, text));
}

function receiptBox(receipt) {
  const taskId = receiptTaskId(receipt);
  const said = typeof receipt?.acknowledgement === "string" ? receipt.acknowledgement.trim() : "";
  return el("div", { class: "receipt" },
    el("div", { class: "receipt-head" },
      el("strong", {}, "Core accepted the task"),
      el("span", { class: "badge muted" }, "Not proof it ran")),
    el("p", { class: "notice" }, "This is Core's receipt only. Activity shows what the agent does and what it reports."),
    factList(receiptFacts(receipt)),
    said ? el("div", { class: "said" }, el("span", { class: "notice" }, "Core's acknowledgement"), el("p", {}, said)) : null,
    el("div", { class: "confirm-buttons" },
      el("button", { class: "btn primary", type: "button", disabled: !taskId, html: icon("panel"),
        onclick: () => openPanel("activity", taskId) }, el("span", {}, "Open in Activity"))));
}

// ---------- detail: agent facts ----------

/** A titled section: an icon and heading, then its content on raised glass (as in the concept). */
function section(iconName, title, extra, ...children) {
  return el("section", { class: "section" },
    el("h2", { class: "section-head", html: icon(iconName) }, el("span", {}, title), extra ?? null),
    el("div", { class: "section-body" }, ...children));
}

function modelsSection(agent) {
  const status = agentState(agent.state);
  let note;
  if (agent.state === "listed") {
    note = `Listed by ${agent.name}'s program${agent.checkedAt ? ` (checked ${when(agent.checkedAt)})` : ""}. A listed model is not proof that it runs.`;
  } else if (agent.state === "not_checked") {
    note = "Not checked yet. Refresh models asks the agent's program for its list."
      + (agent.models.length ? " Until then, only your shortlisted models are shown." : "");
  } else {
    note = status.label + (agent.checkedAt ? ` (checked ${when(agent.checkedAt)})` : "") + ".";
  }
  const models = state.showAllModels ? agent.models : agent.models.slice(0, MODELS_SHOWN);
  return section("models", "Models",
    agent.models.length ? el("span", { class: "badge muted" }, String(agent.models.length)) : null,
    el("p", { class: "notice" }, note),
    agent.error ? el("p", { class: agent.state === "unavailable" ? "error-text" : "notice" }, agent.error) : null,
    agent.models.length ? el("ul", { class: "models" }, ...models.map((model) => el("li", { class: "model-row" },
      el("div", { class: "model-head" },
        el("strong", {}, model.displayName),
        model.displayName !== model.id ? el("span", { class: "mono" }, model.id) : null),
      el("div", { class: "model-notes" }, ...modelNotes(model).map((note) => el("span", { class: "chip small" }, note))),
      purposeLine(model) ? el("p", {}, purposeLine(model)) : null)))
      : agent.state === "listed" ? el("p", { class: "notice" }, "The program listed no models.") : null,
    agent.models.length > MODELS_SHOWN && !state.showAllModels
      ? el("button", { class: "btn", type: "button", onclick: () => { state.showAllModels = true; renderDetail(); } },
        `Show all ${agent.models.length}`) : null);
}

function purposesSection(agent) {
  const key = purposeSettingsKey(agent.id);
  const head = ["file", "Model purposes", null];
  if (!key) {
    return section(...head,
      el("p", { class: "notice" }, "Model purposes can be set for Cody, Hermes, Aggie and Claude. This agent has none."));
  }
  const editing = state.purposes?.agentId === agent.id ? state.purposes : null;
  if (editing) return section(...head, purposeEditor(agent, editing));
  const otherDirty = state.purposes && state.purposes.agentId !== agent.id && purposesDirty();
  const loading = state.purposesLoading === agent.id;
  const error = state.purposesError?.agentId === agent.id ? state.purposesError.text : "";
  return section(...head,
    el("p", { class: "notice" }, "What each model is good for. SORA reads these when she picks a model. As Core last reported:"),
    agent.modelChoices.length
      ? el("ul", { class: "purpose-list" }, ...agent.modelChoices.map((row) => el("li", {},
        el("span", { class: "mono" }, row.id), row.purpose ? el("span", {}, row.purpose) : el("span", { class: "notice" }, "No purpose written"))))
      : el("p", { class: "empty-line" }, "None saved."),
    error ? el("p", { class: "error-text" }, error) : null,
    el("div", { class: "section-actions" },
      el("button", { class: "btn", type: "button", disabled: loading || otherDirty,
        title: otherDirty ? `Save or cancel the purposes you are editing for ${state.purposes.name} first.` : "",
        html: icon("file"), onclick: () => openPurposes(agent) },
      el("span", {}, loading ? "Reading Settings…" : "Edit model purposes"))));
}

function purposeEditor(agent, editing) {
  const check = checkPurposeRows(editing.rows);
  const rowErrors = [];
  const listId = `purpose-ids-${agent.id.replace(/[^A-Za-z0-9]/g, "-")}`;
  const rows = editing.rows.map((row, index) => {
    const error = el("div", { class: "row-error", hidden: !check.errors[index] }, check.errors[index] ?? "");
    rowErrors.push(error);
    return el("li", { class: "purpose-row" },
      el("input", { class: "input mono", type: "text", value: row.id, spellcheck: false, maxLength: 256,
        "data-focus": `purpose-id-${index}`, placeholder: "Exact model ID", "aria-label": `Model ID ${index + 1}`,
        list: listId, disabled: editing.saving,
        oninput: (event) => { editing.rows[index].id = event.target.value; updatePurposeLive(); } }),
      el("textarea", { class: "input", rows: 1, value: row.purpose, maxLength: PURPOSE_MAX,
        "data-focus": `purpose-text-${index}`, placeholder: "What it is good for", "aria-label": `Purpose ${index + 1}`,
        disabled: editing.saving,
        oninput: (event) => { editing.rows[index].purpose = event.target.value; updatePurposeLive(); } }),
      el("button", { class: "icon-btn", type: "button", title: "Remove from the draft", disabled: editing.saving,
        html: icon("trash", "Remove from the draft"),
        onclick: () => { editing.rows.splice(index, 1); renderAll(); } }),
      error);
  });
  const status = el("span", { class: "hint" });
  const save = el("button", { class: "btn primary", type: "button", onclick: savePurposes }, editing.saving ? "Saving…" : "Save purposes");
  const add = el("button", { class: "btn", type: "button", html: icon("plus") + "<span>Add a model</span>",
    disabled: editing.saving,
    onclick: () => {
      editing.rows.push({ id: "", purpose: "" });
      renderAll();
      focusLater(`purpose-id-${editing.rows.length - 1}`);
    } });
  live.purpose = { rowErrors, status, save, add, editing };
  const box = el("div", { class: "purposes-editor", role: "group", "aria-label": `Model purposes for ${agent.name}` },
    el("p", { class: "notice" },
      "Describe what each model is good for. An ID here does not prove access, runs no model and does not change "
      + "the preferred model. Other listed models stay available. Saving changes only this agent's model purposes."),
    editing.notice ? el("p", { class: "outcome warn" }, editing.notice) : null,
    editing.error ? el("p", { class: "error-text" }, editing.error) : null,
    el("ol", { class: "purpose-rows" }, ...rows),
    el("datalist", { id: listId }, ...purposeSuggestions(agent, editing.rows).map((id) => el("option", { value: id }))),
    el("div", { class: "task-actions" }, add, status, el("span", { class: "spacer" }),
      el("button", { class: "btn", type: "button", disabled: editing.saving, onclick: cancelPurposes }, "Cancel"),
      save));
  updatePurposeLive();
  return box;
}

function updatePurposeLive() {
  const ui = live.purpose;
  if (!ui || state.purposes !== ui.editing) { report(); return; }
  const editing = ui.editing;
  const check = checkPurposeRows(editing.rows);
  check.errors.forEach((error, index) => {
    const line = ui.rowErrors[index];
    if (!line) return;
    line.textContent = error;
    line.hidden = !error;
  });
  const changed = purposesChanged(editing.base.saved, editing.rows);
  ui.status.textContent = check.tooMany
    ? `At most ${PURPOSE_ROWS_MAX} model purposes per agent; this draft has ${check.count}.`
    : !check.valid ? "Fix the highlighted rows to save."
    : !state.canUseCore ? "SORA's Core is not available right now, so nothing can be saved."
    : changed ? `${check.count}/${PURPOSE_ROWS_MAX} in this draft. Not saved yet.` : "No changes yet.";
  ui.save.disabled = editing.saving || !check.valid || !changed || !state.canUseCore;
  ui.add.disabled = editing.saving || editing.rows.length >= PURPOSE_ROWS_MAX;
  // The list badge for unsaved purposes follows the draft.
  renderList();
  report();
}

function factsSection(agent) {
  const effort = agent.preferredEffort && agent.preferredEffort !== "configured" ? agent.preferredEffort : "Configured default";
  const lines = [
    { label: "Takes tasks", value: agent.enabled ? "Yes" : "No: turned off in Settings" },
    { label: "Model when none is chosen", value: agent.effectiveDefaultModel ?? "The agent's own default" },
    { label: "Effort when none is chosen", value: agent.effectiveDefaultEffort ?? "The agent's own default" },
    { label: "Saved preferred model", value: agent.preferredModel || "None" },
    { label: "Saved preferred effort", value: effort },
    { label: "Default model purpose", value: agent.modelPurpose || "None" },
    { label: "Configured in its program", value: [agent.configuredModel ?? "Provider default model", agent.configuredEffort ?? "provider default effort"].join(" · ") },
    { label: "Saved project", value: agent.projectRoot || "None" },
    { label: "Project mode", value: agent.workspaceMode ?? "Not reported" },
    { label: "Saved base ref", value: agent.baseRef ?? "Not reported" },
    { label: "Project boundary", value: agent.projectBoundary ?? "Not reported" },
    { label: "Task time limit", value: "Set in Core's configuration; there is no per-task override here." },
  ];
  return section("tools", "For new tasks", null,
    el("p", { class: "notice" }, "Saved in Settings, as Core reports them."),
    factList(lines),
    el("div", { class: "section-actions" },
      el("button", { class: "btn", type: "button", html: icon("general"),
        onclick: () => openPanel("settings", "Models") }, el("span", {}, "Change in Settings"))));
}

function capabilitiesSection(agent) {
  return section("bolt", "What it can do", null,
    el("p", { class: "notice" }, "As the agent's adapter reports it."),
    el("div", { class: "chips" }, ...agent.capabilities.map((cap) => el("span", {
      class: `chip${cap.supported === true ? "" : " off"}`,
      html: icon(cap.supported === true ? "task" : cap.supported === false ? "close" : "alert"),
    }, el("span", {}, cap.supported === null ? `${cap.label}: not reported` : cap.label),
    el("span", { class: "visually-hidden" }, cap.supported === true ? " (supported)" : cap.supported === false ? " (not supported)" : "")))));
}

function technicalSection(agent) {
  const lines = [
    { label: "Agent ID", value: agent.id, mono: true },
    agent.harnessName ? { label: "Program", value: agent.harnessName } : null,
    { label: "Last checked", value: agent.checkedAt ? when(agent.checkedAt) || agent.checkedAt : "Not yet" },
  ].filter(Boolean);
  return section("advanced", "Details", null,
    factList(lines),
    agent.ownerRoster.length ? el("div", { class: "roster" },
      el("p", { class: "notice" }, "Your roster for this agent (what you want available; not a check of access):"),
      el("ul", {}, ...agent.ownerRoster.map((item) => el("li", {}, item)))) : null);
}

function automaticSection() {
  const agents = state.catalogue?.agents ?? [];
  const on = agents.filter((agent) => agent.enabled).map((agent) => agent.name);
  const off = agents.filter((agent) => !agent.enabled).map((agent) => agent.name);
  return section("bolt", "How automatic routing works", null,
    el("p", {}, "SORA reads each agent's usage description and your saved preferences, then picks one. "
      + `A task with a project folder or mode goes to ${codyName()}.`),
    state.catalogue ? el("p", { class: "notice" },
      on.length ? `Turned on: ${on.join(", ")}.` : "No agent is turned on in Settings, so a task cannot start.",
      off.length ? ` Turned off: ${off.join(", ")}.` : "") : null,
    el("div", { class: "section-actions" },
      el("button", { class: "btn", type: "button", html: icon("general"),
        onclick: () => openPanel("settings", "Models") }, el("span", {}, "Agent settings"))));
}

function renderDetail() {
  live = {};
  const agent = state.view === AUTOMATIC ? null : findAgent(state.catalogue, state.view);
  const parts = [banner(), header(agent)];
  if (!state.catalogue) {
    parts.push(el("p", { class: "loading" }, state.loading ? "Reading the agent list…" : "The agent list has not been read yet."));
  }
  parts.push(taskCard());
  if (agent) {
    parts.push(modelsSection(agent), purposesSection(agent), factsSection(agent),
      capabilitiesSection(agent), technicalSection(agent));
  } else {
    parts.push(automaticSection());
  }
  if (state.catalogue?.notice) parts.push(el("p", { class: "notice core-notice" }, state.catalogue.notice));
  keepFocus(els.detail, () => els.detail.replaceChildren(...parts.filter(Boolean)));
  report();
}

function renderAll() {
  renderList();
  renderDetail();
}

// ---------- actions: choosing ----------

/** Show another agent's page, from the top. */
function showAgent(id) {
  if (state.view === id) return false;
  state.view = id;
  state.showAllModels = false;
  return true;
}

function selectAgent(id) {
  const moved = showAgent(id);
  // While a task is pinned, browsing other agents does not change what it will send.
  if (!frozen() && state.form.agent !== id) {
    Object.assign(state.form, chooseAgent(id));
    state.selectionNotice = "";
  }
  renderAll();
  if (moved) els.detail.scrollTop = 0;
}

function setAgent(id) {
  if (frozen()) return;
  Object.assign(state.form, chooseAgent(id));
  state.selectionNotice = "";
  if (id !== null) showAgent(id);
  renderAll();
}

function setModel(id) {
  if (frozen()) return;
  const agent = findAgent(state.catalogue, state.form.agent);
  Object.assign(state.form, id === null ? { model: null, effort: "" } : chooseModel(agent, id));
  state.selectionNotice = "";
  renderDetail();
}

async function browseProject() {
  const current = state.form.directory.trim();
  const path = await pickFile("dir", { start: current && current.length <= 260 ? current : undefined });
  if (!path || frozen()) return;
  state.form.directory = path;
  renderDetail();
}

// ---------- actions: the catalogue ----------

async function loadCatalogue(probe) {
  if (!canLoad() || (probe && !state.canUseCore)) return;
  const seq = ++loadSeq;
  state.loading = probe ? "refresh" : "read";
  renderAll();
  try {
    const raw = probe ? await core.refresh() : await core.catalogue();
    if (seq !== loadSeq) return;
    learnAgentNames(raw);
    state.catalogue = normaliseCatalogue(raw);
    // A read while the host blocks Core may come from a Core in transition; read again later.
    state.catalogueCurrent = state.canUseCore;
    state.loadError = "";
    state.readAt = new Date();
    if (!frozen()) {
      const next = reconcileSelection(state.catalogue, state.form);
      state.form.agent = next.agent;
      state.form.model = next.model;
      state.form.effort = next.effort;
      state.selectionNotice = next.notice;
    }
    if (state.view !== AUTOMATIC && !findAgent(state.catalogue, state.view)) state.view = AUTOMATIC;
    if (state.purposes && !findAgent(state.catalogue, state.purposes.agentId) && !purposesDirty()) state.purposes = null;
    if (probe) toast("Model lists refreshed. No task was started and no model was run.");
  } catch (error) {
    if (seq !== loadSeq) return;
    if (probe && error instanceof CoreError && error.code === "TIMEOUT") {
      state.loadError = "Core is still asking the agents' programs for their models; it finishes in the background. Read the list again in a minute.";
    } else {
      state.loadError = `The agent list could not be ${probe ? "refreshed" : "read"}: ${message(error)}`
        + (state.catalogue ? " Showing what was read before." : "");
    }
    if (staleCatalogueError(error) && !(probe && error.code === "TIMEOUT")) state.catalogueCurrent = false;
  } finally {
    if (seq === loadSeq) {
      state.loading = "";
      renderAll();
    }
  }
}

// ---------- actions: the task ----------

function askStart() {
  if (state.starting || state.confirm || state.submission.sending || state.submission.confirmed) return;
  state.discardConfirm = false;
  if (state.submission.unconfirmed) {
    if (!state.canUseCore) return;
    state.confirm = { body: state.submission.body, retry: true };
  } else {
    const start = startState({ form: state.form, catalogue: state.catalogue, catalogueCurrent: state.catalogueCurrent,
      canUseCore: state.canUseCore, submission: state.submission, loading: Boolean(state.loading) });
    if (!start.enabled) return;
    try {
      state.confirm = { body: taskBody(state.form, state.submission.key), retry: false };
    } catch (error) {
      state.outcome = { tone: "bad", title: "Not started", text: error.message };
      renderDetail();
      return;
    }
    state.outcome = null;
  }
  renderAll();
  focusLater("confirm-no");
}

async function confirmStart() {
  const pending = state.confirm;
  if (!pending || state.starting) return;
  state.confirm = null;
  if (!state.canUseCore) {
    state.outcome = { tone: "warn", title: "Nothing was sent", text: "SORA's Core is not available right now. Try again when it is back." };
    renderAll();
    return;
  }
  state.starting = true;
  state.outcome = null;
  renderAll();
  try {
    // Check which Core is answering first, so an unconfirmed attempt is never resent to another.
    let identity;
    try {
      identity = await core.identity();
    } catch (error) {
      if (staleCatalogueError(error)) state.catalogueCurrent = false;
      state.outcome = { tone: "warn", title: "Nothing was sent",
        text: `SORA could not check Core before sending: ${message(error)} Try again when Core is back.` };
      return;
    }
    const instance = typeof identity?.instance_id === "string" ? identity.instance_id : null;
    let body;
    try {
      body = pending.retry ? state.submission.retry(instance) : state.submission.begin(pending.body, instance);
    } catch (error) {
      state.outcome = { tone: "warn", title: "Not sent again", text: error.message };
      return;
    }
    renderAll();
    try {
      const receipt = await core.delegate(body);
      if (state.submission.acknowledge(receipt)) {
        state.selectionNotice = "";
        toast("Core accepted the task. Activity shows what happens next.");
      } else {
        state.outcome = uncertain(state.submission.outcome);
      }
    } catch (error) {
      if (staleCatalogueError(error)) state.catalogueCurrent = false;
      if (state.submission.fail(error) === "rejected") {
        state.outcome = { tone: "bad", title: "Core turned the request down before starting it",
          text: `Nothing was started. Correct the task and start again. (${message(error)})` };
      } else {
        state.outcome = uncertain(message(error));
      }
    }
  } finally {
    state.starting = false;
    renderAll();
  }
}

function uncertain(reason) {
  return { tone: "warn", title: "Not confirmed",
    text: `${reason} The task may or may not have started, so check Activity first. `
      + "Retry sends exactly the same request with the same key, so Core can recognise it if it did start. "
      + "If Activity shows no such task, you can discard this attempt instead." };
}

function discardAttempt() {
  if (!state.submission.unconfirmed) return;
  state.submission.discard();
  state.discardConfirm = false;
  state.outcome = null;
  afterUnfreeze();
  toast("Attempt discarded. Your task is still here; nothing new was sent.");
  renderAll();
}

function newTask() {
  if (state.starting || state.submission.sending || state.submission.unconfirmed) return;
  state.submission.reset();
  state.form.intent = "";
  state.outcome = null;
  afterUnfreeze();
  toast("New task. Nothing has been sent yet.");
  renderAll();
  focusLater("intent");
}

/** Once the form is editable again, recheck its choices against the list read meanwhile. */
function afterUnfreeze() {
  if (!state.catalogue) return;
  const next = reconcileSelection(state.catalogue, state.form);
  state.form.agent = next.agent;
  state.form.model = next.model;
  state.form.effort = next.effort;
  state.selectionNotice = next.notice;
  if (next.agent !== null) state.view = next.agent;
}

// ---------- actions: model purposes ----------

async function openPurposes(agent) {
  const key = purposeSettingsKey(agent.id);
  if (!key || state.purposesLoading) return;
  if (state.purposes && state.purposes.agentId !== agent.id && purposesDirty()) return;
  state.purposesLoading = agent.id;
  state.purposesError = null;
  renderDetail();
  try {
    const base = purposeBase(await core.settings(), key);
    state.purposes = { agentId: agent.id, name: agent.name, key, base,
      rows: base.saved.length ? base.saved.map((row) => ({ ...row })) : [{ id: "", purpose: "" }],
      saving: false, notice: "", error: "" };
  } catch (error) {
    state.purposesError = { agentId: agent.id, text: `Model purposes could not be opened: ${message(error)}` };
  } finally {
    state.purposesLoading = "";
    renderAll();
  }
  if (state.purposes?.agentId === agent.id) focusLater("purpose-id-0");
}

function cancelPurposes() {
  if (!state.purposes || state.purposes.saving) return;
  state.purposes = null;
  renderAll();
}

async function savePurposes() {
  const editing = state.purposes;
  if (!editing || editing.saving || !state.canUseCore) return;
  let edit;
  try {
    edit = purposeSaveRequest(editing.base, editing.rows);
  } catch (error) {
    editing.error = error.message;
    renderDetail();
    return;
  }
  editing.saving = true;
  editing.error = "";
  editing.notice = "";
  renderAll();
  try {
    await core.savePurposes(edit);
    state.purposes = null;
    toast("Model purposes saved. No model was run, and the preferred model is unchanged.");
    // The list shows the new purposes once it is read again (not while a task waits for a retry).
    if (canLoad()) await loadCatalogue(false);
  } catch (error) {
    if (error instanceof CoreError && error.code === "SETTINGS_CONFLICT") {
      await afterConflict(editing, error);
    } else {
      editing.error = `Not saved; your rows are kept. ${message(error)}`;
    }
    editing.saving = false;
  } finally {
    renderAll();
  }
}

/** Never retried automatically: take Core's new revision, keep the rows, and say what changed. */
async function afterConflict(editing, error) {
  const previous = editing.base.revision;
  try {
    const { base, changedHere } = rebasePurposes(editing.base, await core.settings());
    editing.base = base;
    if (!purposesChanged(base.saved, editing.rows)) {
      if (state.purposes === editing) state.purposes = null;
      toast("These model purposes are already saved.");
      if (canLoad()) loadCatalogue(false);
      return;
    }
    editing.notice = base.revision === previous
      ? `${message(error)} Your rows are kept; try again in a moment.`
      : changedHere
        ? "These model purposes were changed somewhere else (perhaps in Settings) while you were editing. "
          + "Your rows are kept: compare them and save again, or cancel to keep the saved ones."
        : "Other settings were saved while you were editing. Your rows are kept; check them and save again.";
  } catch (readError) {
    editing.error = `Not saved: settings changed elsewhere, and reading them again failed: ${message(readError)}`;
  }
}

// ---------- keyboard ----------

// Capture phase, so an open confirmation or editor gets Escape before window.js hides the window.
window.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (state.confirm && !state.starting) {
    event.preventDefault();
    state.confirm = null;
    renderAll();
    focusLater("start");
  } else if (state.discardConfirm) {
    event.preventDefault();
    state.discardConfirm = false;
    renderDetail();
  } else if (state.purposes && !state.purposes.saving && event.target?.closest?.(".purposes-editor")) {
    event.preventDefault();
    cancelPurposes();
  }
}, true);

els.reload.addEventListener("click", () => loadCatalogue(false));

renderAll();
await loadCatalogue(false);
started = true;
