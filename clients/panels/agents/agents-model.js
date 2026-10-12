// Agents state with no DOM: Core's agent catalogue (normalised; nothing is invented), the task
// draft and the exact submission it pins, and one agent's model-purpose draft. Listing a model
// is not proof that it runs, and Core's receipt for a task is not proof that the work happened.

import { CoreError } from "../shared/api.js";
import { TASK_ID, agentName, learnAgentNames, taskStatus } from "../shared/tasks.js";

export { agentName, learnAgentNames, taskStatus };

export const TASK_MAX = 8000;
export const KEY_MAX = 128;
export const MODEL_ID_MAX = 256;
export const PURPOSE_MAX = 500;
export const PURPOSE_ROWS_MAX = 64;
export const DIRECTORY_MAX = 4096;
/** Core's ReasoningEffort and WorkspaceMode literals (src/sora/contracts/models.py). */
export const EFFORTS = Object.freeze(["none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"]);
export const WORKSPACE_MODES = Object.freeze(["direct", "isolated", "read-only"]);
/** The agent choice that lets SORA route the task from the configured defaults. */
export const AUTOMATIC = "";
/** The agent Core sends an automatic task to when it names a project or mode (service.py). */
export const PROJECT_AGENT = "codex-app-server";

// Client deadlines. The panel proxy has none, so the page brings its own. A metadata refresh may
// legitimately take about 25 s per agent program on Core's side.
export const READ_TIMEOUT_MS = 15000;
export const TASK_TIMEOUT_MS = 15000;
export const REFRESH_TIMEOUT_MS = 35000;

const ITEM = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/;
// Core's ModelId forbids whitespace and control characters; .NET's IsControl also covers C1.
const BAD_ID_CHARACTER = /[\s\x00-\x1f\x7f-\x9f]/;
const CONTROL = /[\x00-\x1f\x7f-\x9f]/;

// ---------- catalogue ----------

const STATES = {
  not_checked: { label: "Not checked yet", tone: "off" },
  listed: { label: "Models listed", tone: "ok" },
  unavailable: { label: "Discovery failed", tone: "bad" },
  not_supported: { label: "No model list", tone: "off" },
};

/** Plain words and a tone for a catalogue entry's state. Unknown states are shown as Core sent them. */
export function agentState(state) {
  const value = String(state ?? "");
  return STATES[value] ?? { label: value ? value.replace(/_/g, " ") : "Not reported", tone: "off" };
}

/** The seven capabilities the classic window listed, as the adapter reports them. */
export const CAPABILITIES = Object.freeze([
  ["filesystem", "Works with files"],
  ["worktree_support", "Isolated worktrees"],
  ["sessions", "Sessions"],
  ["resume", "Resume"],
  ["steer", "Takes instructions mid-task"],
  ["cancel", "Can be cancelled"],
  ["tool_restrictions", "Tool restrictions"],
]);

const MODEL_STATES = {
  provider_listed: "Listed by the provider",
  configured_not_checked: "On your shortlist, not checked",
};

const PURPOSE_SOURCES = {
  owner_shortlist: "your model purposes",
  owner_default: "your default model purpose",
  provider_metadata: "the provider's description",
};

const text = (value) => (typeof value === "string" ? value : "");
const optional = (value) => (typeof value === "string" && value.trim() ? value : null);

/** A problem with an exact model ID, or "" when Core would accept it. */
export function modelIdProblem(id) {
  if (typeof id !== "string" || id.length === 0) return "Enter the exact model ID.";
  if (id.length > MODEL_ID_MAX) return `Model IDs are at most ${MODEL_ID_MAX} characters.`;
  if (BAD_ID_CHARACTER.test(id)) return "Model IDs have no spaces or control characters.";
  return "";
}

function normaliseModel(raw) {
  if (!raw || typeof raw !== "object" || modelIdProblem(raw.id)) return null;
  const efforts = Array.isArray(raw.efforts)
    ? [...new Set(raw.efforts.filter((effort) => EFFORTS.includes(effort)))] : [];
  return {
    id: raw.id,
    displayName: optional(raw.display_name) ?? raw.id,
    description: text(raw.description),
    efforts,
    embeddedEffort: optional(raw.embedded_effort),
    defaultEffort: EFFORTS.includes(raw.default_effort) ? raw.default_effort : null,
    hidden: raw.hidden === true,
    state: text(raw.state),
    stateLabel: MODEL_STATES[raw.state] ?? (optional(raw.state) ? raw.state.replace(/_/g, " ") : "Not checked"),
    purpose: text(raw.purpose),
    purposeSource: text(raw.purpose_source),
    shortlisted: raw.shortlisted === true,
  };
}

function normaliseAgent(raw) {
  const id = typeof raw?.provider === "string" ? raw.provider.trim() : "";
  if (!id || !ITEM.test(id)) return null;
  const models = [];
  const seen = new Set();
  for (const item of Array.isArray(raw.models) ? raw.models : []) {
    const model = normaliseModel(item);
    if (model && !seen.has(model.id)) { seen.add(model.id); models.push(model); }
  }
  const caps = raw.capabilities && typeof raw.capabilities === "object" ? raw.capabilities : {};
  const capabilities = CAPABILITIES.map(([key, label]) => ({
    key, label, supported: typeof caps[key] === "boolean" ? caps[key] : null,
  }));
  const choices = Array.isArray(raw.model_choices) ? raw.model_choices : [];
  return {
    id,
    name: optional(raw.display_name)?.trim() ?? agentName(id),
    harnessName: optional(raw.harness_name),
    purpose: text(raw.purpose),
    ownerRoster: Array.isArray(raw.owner_roster) ? raw.owner_roster.filter((item) => typeof item === "string" && item) : [],
    state: text(raw.state),
    checkedAt: optional(raw.checked_at),
    error: optional(raw.error),
    capabilities,
    configuredModel: optional(raw.configured_model),
    configuredEffort: optional(raw.configured_effort),
    // The classic window counts a missing flag as on; anything that is not a boolean is off.
    enabled: raw.enabled === undefined ? true : raw.enabled === true,
    preferredModel: text(raw.preferred_model),
    preferredEffort: text(raw.preferred_effort),
    modelPurpose: text(raw.model_purpose),
    projectRoot: text(raw.project_root),
    workspaceMode: optional(raw.workspace_mode),
    baseRef: optional(raw.base_ref),
    projectBoundary: optional(raw.project_boundary),
    effectiveDefaultModel: optional(raw.effective_default_model),
    effectiveDefaultEffort: optional(raw.effective_default_effort),
    modelChoices: choices
      .filter((row) => row && typeof row.id === "string")
      .map((row) => ({ id: row.id, purpose: text(row.purpose) })),
    models,
  };
}

/**
 * Core's catalogue has no exported schema, so every field is checked. Agents without an exact ID
 * and models without a valid model ID are left out; nothing missing is filled in.
 */
export function normaliseCatalogue(raw) {
  const agents = [];
  const seen = new Set();
  for (const entry of Array.isArray(raw?.providers) ? raw.providers : []) {
    const agent = entry && typeof entry === "object" ? normaliseAgent(entry) : null;
    if (agent && !seen.has(agent.id)) { seen.add(agent.id); agents.push(agent); }
  }
  return { agents, notice: optional(raw?.notice), hermesNotice: optional(raw?.hermes_notice) };
}

export function findAgent(catalogue, id) {
  return catalogue?.agents?.find((agent) => agent.id === id) ?? null;
}

export function findModel(agent, id) {
  return agent?.models?.find((model) => model.id === id) ?? null;
}

/** Whether automatic routing has anything to route to (any agent enabled). */
export function anyEnabled(catalogue) {
  return Boolean(catalogue?.agents?.some((agent) => agent.enabled));
}

// ---------- selection: agent, model, effort ----------

/**
 * The selection is {agent, model, effort}. agent "" is automatic routing and null means "choose
 * one"; model "" is the saved or configured default and null means "choose one"; effort "" is the
 * default. Picking an agent resets its model and effort.
 */
export function chooseAgent(id) {
  return { agent: id, model: "", effort: "" };
}

/** Picking a model preselects its default effort when the provider lists one. */
export function chooseModel(agent, modelId) {
  const model = findModel(agent, modelId);
  const effort = model?.defaultEffort && model.efforts.includes(model.defaultEffort) ? model.defaultEffort : "";
  return { model: modelId, effort };
}

export function effortChoices(agent, modelId) {
  return modelId ? findModel(agent, modelId)?.efforts ?? [] : [];
}

/**
 * After the catalogue is read again, keep the previous choices by ID. A choice that is no longer
 * listed is cleared (null), with a note, so nothing silently changes what will be sent.
 */
export function reconcileSelection(catalogue, previous) {
  const { agent: agentId = AUTOMATIC, model: modelId = "", effort = "" } = previous ?? {};
  if (agentId === AUTOMATIC) return { agent: AUTOMATIC, model: "", effort: "", notice: "" };
  if (agentId === null) return { agent: null, model: "", effort: "", notice: "" };
  const agent = findAgent(catalogue, agentId);
  if (!agent) {
    return { agent: null, model: "", effort: "",
      notice: "The agent you chose is no longer listed. Choose an agent before starting." };
  }
  if (modelId === null) return { agent: agentId, model: null, effort: "", notice: "" };
  if (modelId === "") return { agent: agentId, model: "", effort: "", notice: "" };
  const model = findModel(agent, modelId);
  if (!model) {
    return { agent: agentId, model: null, effort: "",
      notice: "The model you chose is no longer listed. Choose a model before starting." };
  }
  const kept = effort && model.efforts.includes(effort) ? effort : chooseModel(agent, modelId).effort;
  return { agent: agentId, model: modelId, effort: kept, notice: "" };
}

/** Labels for the "nothing chosen" options, naming Core's effective default when it reports one. */
export function defaultModelLabel(agent) {
  return agent?.effectiveDefaultModel ? `Default (${agent.effectiveDefaultModel})` : "Default (saved preference or the agent's own)";
}

export function defaultEffortLabel(agent, modelId) {
  if (modelId) {
    const model = findModel(agent, modelId);
    return model?.embeddedEffort ? `Model's own tier (${model.embeddedEffort})` : "Model's own default";
  }
  return agent?.effectiveDefaultEffort ? `Default (${agent.effectiveDefaultEffort})` : "Default";
}

export function modelLabel(model) {
  return model.displayName && model.displayName !== model.id ? `${model.displayName} · ${model.id}` : model.id;
}

export function agentOptionLabel(agent) {
  return `${agent.name} · ${agentState(agent.state).label}${agent.enabled ? "" : " · off"}`;
}

/** What one model's row says about it, all from Core's catalogue. */
export function modelNotes(model) {
  const notes = [model.stateLabel];
  if (model.hidden) notes.push("Hidden by the provider");
  if (model.embeddedEffort) notes.push(`Tier in its name: ${model.embeddedEffort}`);
  if (model.efforts.length) {
    notes.push(`Efforts: ${model.efforts.join(", ")}${model.defaultEffort ? ` (default ${model.defaultEffort})` : ""}`);
  }
  return notes;
}

export function purposeLine(model) {
  const purpose = model.purpose || model.description;
  if (!purpose) return "";
  const source = PURPOSE_SOURCES[model.purposeSource];
  return source ? `${purpose} (from ${source})` : purpose;
}

// ---------- the task ----------

export function emptyForm() {
  return { agent: AUTOMATIC, model: "", effort: "", directory: "", mode: "", intent: "" };
}

/** True when Core would send an automatic task with this project or mode to Cody. */
export function routesToProjectAgent(form) {
  return form.agent === AUTOMATIC && Boolean(form.directory.trim() || form.mode);
}

/**
 * The exact request for POST /api/v1/tasks, as the classic AgentSelection.TaskBody built it:
 * intent and key always; agent, model, effort, project and mode only when chosen.
 */
export function taskBody(form, key) {
  const intent = String(form.intent ?? "").trim();
  if (!intent) throw new TypeError("Describe the task first.");
  if (intent.length > TASK_MAX) throw new TypeError(`A task is at most ${TASK_MAX.toLocaleString("en-GB")} characters.`);
  if (typeof key !== "string" || !key || key.length > KEY_MAX || CONTROL.test(key)) {
    throw new TypeError("The request key is not valid.");
  }
  const agent = form.agent;
  if (agent === null) throw new TypeError("Choose an agent.");
  if (form.model === null) throw new TypeError("Choose a model.");
  if ((form.model || form.effort) && !agent) {
    throw new TypeError("A model or effort needs a specific agent, not automatic routing.");
  }
  const body = { intent, idempotency_key: key };
  if (agent) {
    if (!ITEM.test(agent)) throw new TypeError("Choose a listed agent.");
    body.explicit_provider = agent;
  }
  if (form.model) {
    const problem = modelIdProblem(form.model);
    if (problem) throw new TypeError(problem);
    body.explicit_model = form.model;
  }
  if (form.effort) {
    if (!EFFORTS.includes(form.effort)) throw new TypeError("Choose a listed effort.");
    body.explicit_effort = form.effort;
  }
  const directory = String(form.directory ?? "").trim();
  if (directory) {
    if (directory.length > DIRECTORY_MAX || CONTROL.test(directory)) throw new TypeError("That project folder is not a usable path.");
    body.working_directory = directory;
  }
  if (form.mode) {
    if (!WORKSPACE_MODES.includes(form.mode)) throw new TypeError("Choose a listed mode.");
    body.workspace_mode = form.mode;
  }
  return body;
}

/** Whether Start can be pressed, its label, and (when it cannot) why, in plain words. */
export function startState({ form, catalogue, catalogueCurrent, canUseCore, submission, loading }) {
  if (submission.sending) return { enabled: false, label: "Starting…", reason: "" };
  if (submission.confirmed) {
    return { enabled: false, label: "Start task", reason: "Core accepted this task. Choose New task to start another." };
  }
  const retry = submission.unconfirmed;
  const label = retry ? "Retry exact submission" : "Start task";
  const no = (reason) => ({ enabled: false, label, reason });
  if (!canUseCore) return no("SORA's Core is not available right now, so nothing can be sent.");
  if (retry) return { enabled: true, label, reason: "" };
  if (loading) return no("Reading the agent list…");
  if (!catalogue || !catalogueCurrent) return no("Read the agent list first; it may be out of date.");
  if (form.agent === null) return no("Choose an agent.");
  if (form.agent === AUTOMATIC) {
    if (!anyEnabled(catalogue)) return no("No agent is turned on in Settings, so a task cannot start.");
  } else {
    const agent = findAgent(catalogue, form.agent);
    if (!agent) return no("Choose an agent.");
    if (!agent.enabled) return no(`${agent.name} is turned off in Settings.`);
  }
  if (form.model === null) return no("Choose a model.");
  const intent = String(form.intent ?? "").trim();
  if (!intent) return no("Describe the task.");
  if (intent.length > TASK_MAX) return no(`The task is too long (at most ${TASK_MAX.toLocaleString("en-GB")} characters).`);
  const directory = String(form.directory ?? "").trim();
  if (directory.length > DIRECTORY_MAX || CONTROL.test(directory)) return no("That project folder is not a usable path.");
  return { enabled: true, label, reason: "" };
}

/**
 * The confirmation summary for exactly the request that will be sent. When Core will route an
 * automatic task to Cody (a project or mode is set), the summary says so instead of "Automatic".
 */
export function confirmation(body, catalogue, { retry = false } = {}) {
  const lines = [];
  const warnings = [];
  const agent = body.explicit_provider ? findAgent(catalogue, body.explicit_provider) : null;
  if (body.explicit_provider) {
    lines.push({ label: "Agent", value: agent ? agent.name : agentName(body.explicit_provider) });
  } else if (body.working_directory || body.workspace_mode) {
    const cody = findAgent(catalogue, PROJECT_AGENT);
    const name = cody?.name ?? agentName(PROJECT_AGENT);
    lines.push({ label: "Agent", value: `${name}: Core sends automatic tasks with a project folder or mode to ${name}` });
    if (!cody) warnings.push(`${name} is not in the agent list, so Core may refuse this task.`);
    else if (!cody.enabled) warnings.push(`${name} is turned off in Settings, so Core may refuse this task.`);
  } else {
    lines.push({ label: "Agent", value: "Automatic: SORA chooses from your configured defaults" });
  }
  lines.push({ label: "Model", value: body.explicit_model ?? (agent ? defaultModelLabel(agent) : "Default") });
  lines.push({ label: "Effort", value: body.explicit_effort ?? "Default" });
  lines.push({ label: "Project", value: body.working_directory ?? "The agent's saved project, if any" });
  lines.push({ label: "Mode", value: body.workspace_mode ?? "Saved, or decided from the task" });
  const question = retry
    ? "Send the same request again with the same key? If you are not sure whether it started, check Activity first."
    : "Start this task?";
  return { lines, warnings, question };
}

// ---------- the submission an attempt pins ----------

function randomKey() {
  const uuid = globalThis.crypto?.randomUUID?.()
    ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
  return `agents-${uuid}`;
}

function sameJson(a, b) { return JSON.stringify(a) === JSON.stringify(b); }

/** A valid task ID in Core's answer, or "" (an answer without one is not a confirmation). */
export function receiptTaskId(receipt) {
  const id = receipt && typeof receipt === "object" ? receipt.task_id : null;
  return typeof id === "string" && TASK_ID.test(id) && !id.includes("..") ? id : "";
}

/**
 * One delegation attempt. The first Start pins the exact request body (with a stable
 * idempotency key) and the Core instance it went to. Only a 400 INVALID_INPUT unpins it, because
 * Core refused it before admission. Any other failure (a 500, 503, timeout or lost connection)
 * may have started the task, so the only way forward is the same body with the same key, or an
 * explicit discard after checking Activity. Nothing is ever resent automatically.
 */
export class TaskSubmission {
  constructor({ newKey = randomKey } = {}) {
    this.newKey = newKey;
    this.reset();
  }

  reset() {
    this.key = this.newKey();
    this.body = null;
    this.instanceId = null;
    this.phase = "draft";
    this.receipt = null;
    this.outcome = "";
  }

  get attempted() { return this.body !== null; }
  get sending() { return this.phase === "sending"; }
  get unconfirmed() { return this.phase === "unconfirmed"; }
  get confirmed() { return this.phase === "acknowledged"; }

  /** First attempt: pin this body under the attempt's key. */
  begin(body, instanceId = null) {
    if (this.attempted) throw new Error("This attempt is already pinned. Retry it exactly, or discard it.");
    const pinned = { ...body, idempotency_key: this.key };
    this.body = Object.freeze(pinned);
    this.instanceId = typeof instanceId === "string" && instanceId ? instanceId : null;
    this.phase = "sending";
    this.outcome = "";
    return this.body;
  }

  /** Retry: exactly the pinned body, and only against the Core instance it was first sent to. */
  retry(instanceId = null) {
    if (!this.unconfirmed) throw new Error("There is no unconfirmed task to retry.");
    if (this.instanceId && typeof instanceId === "string" && instanceId && instanceId !== this.instanceId) {
      throw new Error("SORA's Core has restarted since this attempt, so it is not resent to a different Core. "
        + "Check Activity; if the task is not there, discard this attempt and start again.");
    }
    this.phase = "sending";
    return this.body;
  }

  /** Core answered 201. Without a valid task ID the outcome stays unknown. */
  acknowledge(receipt) {
    if (!this.sending) return false;
    if (!receiptTaskId(receipt)) {
      this.phase = "unconfirmed";
      this.outcome = "Core answered without a valid task ID, so SORA cannot confirm the task.";
      return false;
    }
    this.phase = "acknowledged";
    this.receipt = receipt;
    this.outcome = "";
    return true;
  }

  /** "rejected" (400 INVALID_INPUT: editable again, new key) or "uncertain" (still pinned). */
  fail(error) {
    if (!this.sending) return "ignored";
    if (error instanceof CoreError && error.status === 400 && error.code === "INVALID_INPUT") {
      this.reset();
      this.outcome = error.message;
      return "rejected";
    }
    this.phase = "unconfirmed";
    this.outcome = error?.message ? String(error.message) : "No answer from Core.";
    return "uncertain";
  }

  /** The owner chose to drop an unconfirmed attempt (after checking Activity). */
  discard() {
    if (this.sending) throw new Error("Wait for Core to answer first.");
    this.reset();
  }
}

/** Facts from Core's 201 answer, with "Not reported" where Core sent nothing. */
export function receiptFacts(receipt) {
  const value = (key, fallback) => (optional(receipt?.[key]) ?? fallback);
  const backend = optional(receipt?.selected_backend);
  return [
    { label: "Task", value: receiptTaskId(receipt) || "Not reported", mono: true },
    { label: "State", value: optional(receipt?.status) ? taskStatus(receipt.status).label : "Not reported" },
    { label: "Agent", value: backend ? agentName(backend) : "Not reported" },
    { label: "Model", value: value("requested_model", "Not reported (provider default)") },
    { label: "Effort", value: value("requested_effort", "Not reported (configured)") },
    { label: "Project", value: value("working_directory", "Not reported") },
    { label: "Mode", value: value("workspace_mode", "Not reported") },
  ];
}

// ---------- model purposes (agents.<agent>.model_choices in Settings) ----------

const PURPOSE_AGENTS = {
  "codex-app-server": "codex", codex: "codex",
  "hermes-acp": "hermes", hermes: "hermes",
  "claude-code": "claude", claude: "claude",
  antigravity: "antigravity",
};

/** The settings key holding an agent's model purposes, or null when Core has none for it. */
export function purposeSettingsKey(agentId) {
  const name = Object.hasOwn(PURPOSE_AGENTS, String(agentId)) ? PURPOSE_AGENTS[agentId] : null;
  return name ? `agents.${name}.model_choices` : null;
}

/** Saved rows as Core stores them. A malformed or duplicated list is refused, not repaired. */
export function savedPurposeRows(value) {
  if (!Array.isArray(value)) throw new Error("Core's saved model purposes are not a list.");
  const rows = [];
  const seen = new Set();
  for (const row of value) {
    if (!row || typeof row !== "object" || typeof row.id !== "string") {
      throw new Error("Core's saved model purposes are not in the expected form.");
    }
    if (seen.has(row.id)) throw new Error("Core's saved model purposes list one model twice.");
    seen.add(row.id);
    rows.push({ id: row.id, purpose: text(row.purpose) });
  }
  return rows;
}

/**
 * What the editor starts from: the saved rows, plus the settings version and revision a save must
 * name. A Core without unified settings (no fields or version) cannot save purposes.
 */
export function purposeBase(projection, key) {
  if (!key) throw new Error("Model purposes can be set for Cody, Hermes, Aggie and Claude only.");
  if (!Array.isArray(projection?.fields) || !Number.isInteger(projection?.settings_version)
      || !Number.isInteger(projection?.settings_revision)) {
    throw new Error("Model purposes need a newer SORA Core; this one has no editable settings.");
  }
  const field = projection.fields.find((item) => item?.key === key);
  if (!field) throw new Error("This Core does not offer model purposes for this agent.");
  if (field.editable === false) throw new Error("Core reports these model purposes as read-only.");
  return {
    key,
    version: projection.settings_version,
    revision: projection.settings_revision,
    saved: savedPurposeRows(field.value),
  };
}

/**
 * Check the rows being edited. Text is trimmed; a row with neither ID nor purpose is ignored.
 * Each row gets "" or a problem; clean holds the rows Core would get.
 */
export function checkPurposeRows(rows) {
  const clean = [];
  const errors = [];
  const seen = new Set();
  let count = 0;
  for (const row of rows) {
    const id = String(row?.id ?? "").trim();
    const purpose = String(row?.purpose ?? "").trim();
    if (!id && !purpose) { errors.push(""); continue; }
    count += 1;
    let problem = modelIdProblem(id);
    if (!problem && purpose.length > PURPOSE_MAX) problem = `A purpose is at most ${PURPOSE_MAX} characters.`;
    if (!problem && seen.has(id)) problem = "This model ID is already in the list.";
    errors.push(problem);
    if (!problem) { seen.add(id); clean.push({ id, purpose }); }
  }
  const tooMany = count > PURPOSE_ROWS_MAX;
  return {
    clean, errors, count, tooMany,
    valid: !tooMany && errors.every((error) => !error),
  };
}

/** True when the rows differ from what is saved (a row with a problem counts as a change). */
export function purposesChanged(saved, rows) {
  const check = checkPurposeRows(rows);
  return !check.valid || !sameJson(saved ?? [], check.clean);
}

/** The exact settings edit: this agent's purpose rows only, with the revision the editor read. */
export function purposeSaveRequest(base, rows) {
  const check = checkPurposeRows(rows);
  if (!check.valid) throw new TypeError("Fix the highlighted rows first.");
  return { version: base.version, expected_revision: base.revision, changes: { [base.key]: check.clean } };
}

/**
 * After SETTINGS_CONFLICT, take Core's new revision and keep the owner's rows. Says whether this
 * agent's saved purposes themselves changed elsewhere (as opposed to some other setting).
 */
export function rebasePurposes(base, projection) {
  const next = purposeBase(projection, base.key);
  return { base: next, changedHere: !sameJson(next.saved, base.saved) };
}

/** Listed model IDs not yet in the draft, offered as suggestions (as the classic dialog did). */
export function purposeSuggestions(agent, rows) {
  const used = new Set(rows.map((row) => String(row.id ?? "").trim()));
  return (agent?.models ?? []).map((model) => model.id).filter((id) => !used.has(id));
}

// ---------- quit protection ----------

/**
 * Unsaved work SoraShell should warn about on Quit: a typed task that Core has not accepted
 * (including an attempt waiting to be retried) and purpose edits that are not saved.
 */
export function isDirty({ intent, submission, purposes }) {
  const task = Boolean(String(intent ?? "").trim()) && !submission.confirmed;
  const edits = Boolean(purposes && purposesChanged(purposes.base.saved, purposes.rows));
  return task || edits;
}

// ---------- calls to Core with a deadline ----------

/**
 * Run a Core call with a deadline. On timeout the call is aborted and a CoreError (status 0) is
 * thrown; the page must treat a timed-out task start as "outcome unknown", never as failure.
 */
export async function withDeadline(ms, run) {
  const seconds = Math.max(1, Math.round(ms / 1000));
  const late = () => new CoreError(`No answer from Core within ${seconds} second${seconds === 1 ? "" : "s"}.`,
    { status: 0, code: "TIMEOUT" });
  const controller = new AbortController();
  let timer = 0;
  const expired = new Promise((_, reject) => {
    timer = setTimeout(() => {
      controller.abort();
      reject(late());
    }, ms);
  });
  try {
    return await Promise.race([run(controller.signal), expired]);
  } catch (error) {
    if (error?.name === "AbortError") {
      throw late();
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

/** The Core calls this page makes, each with its own deadline. */
export class AgentsCore {
  constructor(api, { readMs = READ_TIMEOUT_MS, taskMs = TASK_TIMEOUT_MS, refreshMs = REFRESH_TIMEOUT_MS } = {}) {
    this.api = api;
    this.ms = { read: readMs, task: taskMs, refresh: refreshMs };
  }

  /** The cached catalogue: no discovery, no inference. */
  catalogue() {
    return withDeadline(this.ms.read, (signal) => this.api.request("/api/v1/agents/catalogue", { signal }));
  }

  /** Explicit metadata discovery. Core runs it once at a time and finishes it even if we stop waiting. */
  refresh() { return withDeadline(this.ms.refresh, (signal) => this.api.refreshAgents(signal)); }

  identity() {
    return withDeadline(this.ms.read, (signal) => this.api.request("/api/v1/runtime/identity", { signal }));
  }

  settings() {
    return withDeadline(this.ms.read, (signal) => this.api.request("/api/v1/projections/settings", { signal }));
  }

  savePurposes(edit) {
    return withDeadline(this.ms.read, (signal) => this.api.request("/api/v1/settings",
      { method: "POST", body: edit, signal }));
  }

  /** POST /api/v1/tasks with the pinned body (it carries its own idempotency_key). */
  delegate(body) {
    return withDeadline(this.ms.task, (signal) => this.api.request("/api/v1/tasks",
      { method: "POST", body, signal }));
  }
}

/** Errors that mean the list on screen may belong to a Core that is no longer there. */
export function staleCatalogueError(error) {
  return error instanceof CoreError && (error.unavailable || error.code === "RUNTIME_CHANGED");
}
