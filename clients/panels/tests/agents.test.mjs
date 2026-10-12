import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { CoreApi, CoreError } from "../shared/api.js";
import { send } from "../shared/bridge.js";
import {
  AUTOMATIC, AgentsCore, PURPOSE_ROWS_MAX, TASK_MAX, TaskSubmission, agentState, checkPurposeRows,
  chooseAgent, chooseModel, confirmation, defaultEffortLabel, defaultModelLabel, effortChoices,
  emptyForm, isDirty, modelIdProblem, modelNotes, normaliseCatalogue, purposeBase, purposeLine,
  purposeSaveRequest, purposeSettingsKey, purposeSuggestions, purposesChanged, rebasePurposes,
  receiptFacts, receiptTaskId, reconcileSelection, routesToProjectAgent, savedPurposeRows,
  staleCatalogueError, startState, taskBody, withDeadline,
} from "../agents/agents-model.js";

// A catalogue in the shape agent_catalogue.py produces after a refresh.
const raw = {
  schema_version: 1,
  notice: "Provider-listed models are not verified entitlements. No inference was run.",
  hermes_notice: "Hermes discovery creates an empty ACP session, with no prompt or MCP startup.",
  providers: [
    {
      provider: "codex-app-server", display_name: "Cody", harness_name: "codex-app-server",
      purpose: "Coding and repository changes.", owner_roster: ["Full provider-listed ChatGPT catalogue"],
      state: "listed", checked_at: "2026-10-12T09:00:00+00:00", error: null,
      capabilities: { filesystem: true, worktree_support: true, sessions: true, resume: true, steer: true,
        cancel: true, tool_restrictions: false },
      configured_model: null, configured_effort: "medium", enabled: true, preferred_model: "gpt-5.5",
      preferred_effort: "high", model_purpose: "", project_root: "C:/Projects/demo", workspace_mode: "direct",
      base_ref: "HEAD", project_boundary: "native Codex sandbox; live boundary acceptance pending",
      effective_default_model: "gpt-5.5", effective_default_effort: "high",
      model_choices: [{ id: "gpt-5.5", purpose: "Hard refactors" }],
      models: [
        { id: "gpt-5.5", display_name: "GPT-5.5", description: "Flagship", efforts: ["low", "medium", "high", "turbo"],
          embedded_effort: null, default_effort: "medium", hidden: false, state: "provider_listed",
          execution_verified: false, purpose: "Hard refactors", shortlisted: true, purpose_source: "owner_shortlist" },
        { id: "gpt-5.5-mini", display_name: "GPT-5.5 mini", description: "Quick edits", efforts: [],
          embedded_effort: null, default_effort: null, hidden: true, state: "provider_listed",
          execution_verified: false, purpose: "Quick edits", shortlisted: false, purpose_source: "provider_metadata" },
        { id: "has space", display_name: "Bad" },
        { id: "gpt-5.5", display_name: "Duplicate" },
      ],
    },
    {
      provider: "hermes-acp", display_name: "Hermes", state: "unavailable", checked_at: "2026-10-12T09:00:01+00:00",
      error: "Model discovery failed (TimeoutError); no model was substituted.", enabled: false, models: [],
      capabilities: { filesystem: false }, preferred_effort: "configured",
    },
    { provider: "antigravity", display_name: "Aggie", state: "not_checked", models: [],
      enabled: "yes" },
    { provider: "../escape", display_name: "Nope" },
    { provider: "codex-app-server", display_name: "Second Cody" },
    null,
  ],
};
const catalogue = () => normaliseCatalogue(structuredClone(raw));

test("the catalogue keeps only what Core reported, with SORA's names and nothing filled in", () => {
  const c = catalogue();
  assert.deepEqual(c.agents.map((a) => a.id), ["codex-app-server", "hermes-acp", "antigravity"]);
  assert.equal(c.notice, raw.notice);
  assert.equal(c.hermesNotice, raw.hermes_notice);
  const cody = c.agents[0];
  assert.equal(cody.name, "Cody");
  assert.deepEqual(cody.models.map((m) => m.id), ["gpt-5.5", "gpt-5.5-mini"]);
  assert.deepEqual(cody.models[0].efforts, ["low", "medium", "high"]);
  assert.equal(cody.models[1].hidden, true);
  assert.equal(cody.configuredModel, null);
  const hermes = c.agents[1];
  assert.equal(hermes.enabled, false);
  assert.equal(hermes.capabilities.find((cap) => cap.key === "filesystem").supported, false);
  assert.equal(hermes.capabilities.find((cap) => cap.key === "steer").supported, null, "missing is not reported");
  assert.equal(hermes.workspaceMode, null);
  // A flag that is not a boolean counts as off; a missing one as on (as the classic window did).
  assert.equal(c.agents[2].enabled, false);
  assert.equal(normaliseCatalogue({ providers: [{ provider: "claude-code" }] }).agents[0].enabled, true);
  assert.deepEqual(normaliseCatalogue(null), { agents: [], notice: null, hermesNotice: null });
});

test("states and model notes read as plain words, and listing is never called verification", () => {
  assert.deepEqual(agentState("listed"), { label: "Models listed", tone: "ok" });
  assert.deepEqual(agentState("unavailable"), { label: "Discovery failed", tone: "bad" });
  assert.equal(agentState("new_state").label, "new state");
  assert.equal(agentState(undefined).label, "Not reported");
  const [listed, hidden] = catalogue().agents[0].models;
  assert.deepEqual(modelNotes(listed), ["Listed by the provider", "Efforts: low, medium, high (default medium)"]);
  assert.ok(modelNotes(hidden).includes("Hidden by the provider"));
  assert.equal(purposeLine(listed), "Hard refactors (from your model purposes)");
  assert.equal(purposeLine(hidden), "Quick edits (from the provider's description)");
  for (const note of modelNotes(listed)) assert.doesNotMatch(note, /verified|available to you/i);
});

test("picking a model preselects its default effort only when the provider lists it", () => {
  const cody = catalogue().agents[0];
  assert.deepEqual(chooseAgent("codex-app-server"), { agent: "codex-app-server", model: "", effort: "" });
  assert.deepEqual(chooseModel(cody, "gpt-5.5"), { model: "gpt-5.5", effort: "medium" });
  assert.deepEqual(chooseModel(cody, "gpt-5.5-mini"), { model: "gpt-5.5-mini", effort: "" });
  assert.deepEqual(effortChoices(cody, ""), [], "no efforts without an explicit model");
  assert.equal(defaultModelLabel(cody), "Default (gpt-5.5)");
  assert.equal(defaultEffortLabel(cody, ""), "Default (high)");
  assert.equal(defaultEffortLabel(cody, "gpt-5.5"), "Model's own default");
});

test("reading the list again keeps choices by ID and clears (with a note) any that disappeared", () => {
  const c = catalogue();
  assert.deepEqual(reconcileSelection(c, { agent: "codex-app-server", model: "gpt-5.5", effort: "low" }),
    { agent: "codex-app-server", model: "gpt-5.5", effort: "low", notice: "" });
  assert.deepEqual(reconcileSelection(c, { agent: "codex-app-server", model: "gpt-5.5", effort: "max" }),
    { agent: "codex-app-server", model: "gpt-5.5", effort: "medium", notice: "" });
  const goneAgent = reconcileSelection(c, { agent: "custom-1", model: "x", effort: "" });
  assert.equal(goneAgent.agent, null);
  assert.match(goneAgent.notice, /no longer listed/);
  const goneModel = reconcileSelection(c, { agent: "codex-app-server", model: "o9", effort: "high" });
  assert.deepEqual([goneModel.agent, goneModel.model, goneModel.effort], ["codex-app-server", null, ""]);
  assert.match(goneModel.notice, /Choose a model/);
  assert.equal(reconcileSelection(c, { agent: AUTOMATIC }).agent, AUTOMATIC);
});

test("the task request carries exactly the chosen fields, as the classic window built it", () => {
  const form = { ...emptyForm(), intent: "  Fix the parser test  " };
  assert.deepEqual(taskBody(form, "k1"), { intent: "Fix the parser test", idempotency_key: "k1" });
  const full = { agent: "codex-app-server", model: "gpt-5.5", effort: "high", directory: " C:/Projects/demo ",
    mode: "isolated", intent: "Fix it" };
  assert.deepEqual(taskBody(full, "k2"), { intent: "Fix it", idempotency_key: "k2",
    explicit_provider: "codex-app-server", explicit_model: "gpt-5.5", explicit_effort: "high",
    working_directory: "C:/Projects/demo", workspace_mode: "isolated" });
  assert.throws(() => taskBody({ ...form, model: "gpt-5.5" }, "k"), /specific agent/);
  assert.throws(() => taskBody({ ...form, intent: "   " }, "k"), /Describe/);
  assert.throws(() => taskBody({ ...form, intent: "x".repeat(TASK_MAX + 1) }, "k"), /at most/);
  assert.throws(() => taskBody({ ...full, effort: "turbo" }, "k"), /effort/);
  assert.throws(() => taskBody({ ...full, mode: "anywhere" }, "k"), /mode/);
  assert.throws(() => taskBody({ ...full, model: "two words" }, "k"), /spaces/);
  assert.throws(() => taskBody(form, "x".repeat(129)), /key/);
  assert.throws(() => taskBody({ ...form, agent: null }, "k"), /Choose an agent/);
  assert.equal(routesToProjectAgent({ ...form, directory: "C:/p" }), true);
  assert.equal(routesToProjectAgent({ ...full }), false);
});

test("Start says why it cannot run, and a pinned retry does not need a fresh list", () => {
  const c = catalogue();
  const base = { form: { ...emptyForm(), intent: "Do it" }, catalogue: c, catalogueCurrent: true,
    canUseCore: true, submission: new TaskSubmission(), loading: false };
  assert.deepEqual(startState(base), { enabled: true, label: "Start task", reason: "" });
  assert.match(startState({ ...base, canUseCore: false }).reason, /not available/);
  assert.match(startState({ ...base, catalogueCurrent: false }).reason, /out of date/);
  assert.match(startState({ ...base, form: { ...base.form, intent: " " } }).reason, /Describe/);
  assert.match(startState({ ...base, form: { ...base.form, agent: "hermes-acp" } }).reason, /Hermes is turned off/);
  assert.match(startState({ ...base, form: { ...base.form, model: null, agent: "codex-app-server" } }).reason, /Choose a model/);
  const allOff = normaliseCatalogue({ providers: [{ provider: "codex-app-server", enabled: false }] });
  assert.match(startState({ ...base, catalogue: allOff }).reason, /No agent is turned on/);

  const submission = new TaskSubmission({ newKey: () => "key-1" });
  submission.begin(taskBody(base.form, submission.key), "core-a");
  submission.fail(new CoreError("Core returned 500.", { status: 500, code: "INTERNAL_ERROR" }));
  const retry = startState({ ...base, submission, catalogueCurrent: false });
  assert.deepEqual(retry, { enabled: true, label: "Retry exact submission", reason: "" });
  assert.equal(startState({ ...base, submission, canUseCore: false }).enabled, false);
});

test("the confirmation names exactly what is sent, and says when Core routes automatic work to Cody", () => {
  const c = catalogue();
  const auto = confirmation({ intent: "x", idempotency_key: "k", working_directory: "C:/p" }, c);
  assert.match(auto.lines[0].value, /^Cody: Core sends automatic tasks with a project folder or mode to Cody/);
  assert.deepEqual(auto.warnings, []);
  assert.equal(auto.question, "Start this task?");
  const noCody = confirmation({ intent: "x", idempotency_key: "k", workspace_mode: "read-only" },
    normaliseCatalogue({ providers: [{ provider: "deterministic-mock", display_name: "deterministic-mock" }] }));
  assert.match(noCody.warnings[0], /not in the agent list/);
  const plain = confirmation({ intent: "x", idempotency_key: "k" }, c, { retry: true });
  assert.match(plain.lines[0].value, /^Automatic/);
  assert.match(plain.question, /same key/);
  const exact = confirmation({ intent: "x", idempotency_key: "k", explicit_provider: "codex-app-server",
    explicit_model: "gpt-5.5", explicit_effort: "high" }, c);
  assert.deepEqual(exact.lines.slice(0, 3).map((l) => l.value), ["Cody", "gpt-5.5", "high"]);
});

test("an attempt pins its exact body and key; only 400 INVALID_INPUT makes it editable again", () => {
  let n = 0;
  const submission = new TaskSubmission({ newKey: () => `key-${(n += 1)}` });
  const body = taskBody({ ...emptyForm(), intent: "Do it" }, submission.key);
  const pinned = submission.begin(body, "core-a");
  assert.equal(pinned.idempotency_key, "key-1");
  assert.ok(Object.isFrozen(pinned));
  assert.throws(() => submission.begin(body), /already pinned/);

  // Anything else may have started the task: the same body and key, or an explicit discard.
  for (const error of [
    new CoreError("Core returned 500.", { status: 500, code: "INTERNAL_ERROR" }),
    new CoreError("Core is starting", { status: 503, code: "CORE_UNAVAILABLE" }),
    new CoreError("SORA's Core is not reachable."),
    new CoreError("No answer from Core within 15 seconds.", { status: 0, code: "TIMEOUT" }),
    new CoreError("Which project?", { status: 409, code: "TASK_SELECTION_CONFLICT" }),
    new CoreError("Invalid task request", { status: 422, code: "INVALID_INPUT" }),
  ]) {
    assert.equal(submission.fail(error), "uncertain");
    assert.equal(submission.unconfirmed, true);
    assert.equal(submission.retry("core-a"), pinned, "a retry sends the identical body");
  }
  assert.equal(submission.fail(new CoreError("Invalid provider/model/effort selection", { status: 400, code: "INVALID_INPUT" })), "rejected");
  assert.equal(submission.attempted, false);
  assert.equal(submission.key, "key-2", "a rejected request gets a new key");
  assert.equal(submission.fail(new Error("late")), "ignored");
});

test("a retry is refused against a different Core, and a bad receipt is not a confirmation", () => {
  const submission = new TaskSubmission({ newKey: () => "key-1" });
  submission.begin({ intent: "Do it" }, "core-a");
  submission.fail(new CoreError("lost"));
  assert.throws(() => submission.retry("core-b"), /restarted/);
  assert.equal(submission.unconfirmed, true);
  submission.retry("core-a");
  assert.equal(submission.acknowledge({ task_id: "../../etc" }), false);
  assert.equal(submission.unconfirmed, true);
  assert.match(submission.outcome, /valid task ID/);
  submission.retry(null);
  assert.equal(submission.acknowledge({ task_id: "task-1", status: "queued" }), true);
  assert.equal(submission.confirmed, true);
  assert.throws(() => submission.retry("core-a"), /no unconfirmed/);
  assert.equal(receiptTaskId({ task_id: "task-1" }), "task-1");
  assert.equal(receiptTaskId({ task_id: "a..b" }), "");
});

test("an unconfirmed attempt can be discarded only by the owner, never while it is being sent", () => {
  let n = 0;
  const submission = new TaskSubmission({ newKey: () => `key-${(n += 1)}` });
  submission.begin({ intent: "Do it" });
  assert.throws(() => submission.discard(), /Wait/);
  submission.fail(new CoreError("lost"));
  submission.discard();
  assert.deepEqual([submission.attempted, submission.phase, submission.key], [false, "draft", "key-2"]);
});

test("Core's receipt is shown with 'Not reported' where Core sent nothing", () => {
  const facts = receiptFacts({ task_id: "task-1", status: "queued", selected_backend: "codex-app-server",
    requested_model: null, acknowledgement: "On it." });
  const value = (label) => facts.find((fact) => fact.label === label).value;
  assert.equal(value("Task"), "task-1");
  assert.equal(value("State"), "Queued");
  assert.equal(value("Agent"), "Cody");
  assert.equal(value("Model"), "Not reported (provider default)");
  assert.equal(value("Project"), "Not reported");
  assert.equal(receiptFacts({}).find((fact) => fact.label === "Agent").value, "Not reported");
});

test("Activity opens on the acknowledged task, and busy and dirty are plain booleans", () => {
  assert.deepEqual(send("panel.open", { panel: "activity", select: receiptTaskId({ task_id: "task-9" }) }),
    { type: "panel.open", panel: "activity", select: "task-9" });
  assert.deepEqual(send("panel.open", { panel: "settings", select: "Models" }),
    { type: "panel.open", panel: "settings", select: "Models" });
  assert.deepEqual(send("panel.busy", { busy: true }), { type: "panel.busy", busy: true });
  assert.throws(() => send("panel.busy", { busy: "yes" }), TypeError);
});

// ---------- model purposes ----------

const fixture = JSON.parse(readFileSync(new URL("./fixtures/settings-projection.json", import.meta.url)));
const projection = () => structuredClone(fixture);

test("each built-in agent maps to its own model-purpose setting; others have none", () => {
  assert.equal(purposeSettingsKey("codex-app-server"), "agents.codex.model_choices");
  assert.equal(purposeSettingsKey("hermes-acp"), "agents.hermes.model_choices");
  assert.equal(purposeSettingsKey("claude-code"), "agents.claude.model_choices");
  assert.equal(purposeSettingsKey("antigravity"), "agents.antigravity.model_choices");
  assert.equal(purposeSettingsKey("custom-1"), null);
  assert.equal(purposeSettingsKey("deterministic-mock"), null);
  assert.equal(purposeSettingsKey("constructor"), null);
  for (const agent of ["codex", "hermes", "claude", "antigravity"]) {
    assert.ok(projection().fields.some((f) => f.key === `agents.${agent}.model_choices`), agent);
  }
});

test("the purpose editor starts from Core's saved rows and revision, and refuses an old Core", () => {
  const p = projection();
  p.settings_revision = 7;
  p.fields.find((f) => f.key === "agents.codex.model_choices").value = [{ id: "gpt-5.5", purpose: "Refactors" }];
  assert.deepEqual(purposeBase(p, "agents.codex.model_choices"),
    { key: "agents.codex.model_choices", version: 10, revision: 7, saved: [{ id: "gpt-5.5", purpose: "Refactors" }] });
  assert.throws(() => purposeBase({ owner_id: "x" }, "agents.codex.model_choices"), /newer SORA Core/);
  assert.throws(() => purposeBase(p, null), /Cody, Hermes, Aggie and Claude/);
  const readOnly = projection();
  readOnly.fields.find((f) => f.key === "agents.hermes.model_choices").editable = false;
  assert.throws(() => purposeBase(readOnly, "agents.hermes.model_choices"), /read-only/);
  assert.throws(() => savedPurposeRows([{ id: "a" }, { id: "a" }]), /twice/);
  assert.throws(() => savedPurposeRows("a"), /not a list/);
});

test("purpose rows follow Core's rules: exact IDs, 500-character purposes, unique, at most 64", () => {
  const check = checkPurposeRows([
    { id: " gpt-5.5 ", purpose: " Refactors " },
    { id: "", purpose: "" },
    { id: "two words", purpose: "" },
    { id: "gpt-5.5", purpose: "again" },
    { id: "o9", purpose: "x".repeat(501) },
    { id: "", purpose: "orphan purpose" },
  ]);
  assert.deepEqual(check.clean, [{ id: "gpt-5.5", purpose: "Refactors" }]);
  assert.deepEqual(check.errors.map(Boolean), [false, false, true, true, true, true]);
  assert.equal(check.valid, false);
  assert.match(check.errors[3], /already/);
  const many = Array.from({ length: PURPOSE_ROWS_MAX + 1 }, (_, i) => ({ id: `m${i}`, purpose: "" }));
  assert.equal(checkPurposeRows(many).tooMany, true);
  assert.equal(checkPurposeRows(many.slice(1)).valid, true);
  assert.equal(modelIdProblem("x".repeat(257)), "Model IDs are at most 256 characters.");
  assert.match(modelIdProblem("tab\there"), /spaces/);
  assert.match(modelIdProblem("nbsp\u00a0here"), /spaces/);
  assert.equal(modelIdProblem("vendor/model:latest"), "");
});

test("saving sends only this agent's rows with the revision read; a conflict keeps the rows", () => {
  const p = projection();
  const base = purposeBase(p, "agents.claude.model_choices");
  const rows = [{ id: "claude-opus", purpose: "Long reviews" }, { id: "", purpose: "" }];
  assert.equal(purposesChanged(base.saved, rows), true);
  assert.deepEqual(purposeSaveRequest(base, rows), {
    version: 10, expected_revision: 0,
    changes: { "agents.claude.model_choices": [{ id: "claude-opus", purpose: "Long reviews" }] },
  });
  assert.throws(() => purposeSaveRequest(base, [{ id: "bad id", purpose: "" }]), /Fix/);
  // Someone else saved a different setting: new revision, this agent's rows unchanged.
  const other = projection();
  other.settings_revision = 1;
  assert.deepEqual(rebasePurposes(base, other).changedHere, false);
  assert.equal(rebasePurposes(base, other).base.revision, 1);
  // Someone else saved these very rows.
  const same = projection();
  same.settings_revision = 2;
  same.fields.find((f) => f.key === "agents.claude.model_choices").value = [{ id: "claude-opus", purpose: "Long reviews" }];
  const rebased = rebasePurposes(base, same);
  assert.equal(rebased.changedHere, true);
  assert.equal(purposesChanged(rebased.base.saved, rows), false, "nothing left to save");
});

test("suggestions are the listed model IDs not already in the draft", () => {
  const cody = catalogue().agents[0];
  assert.deepEqual(purposeSuggestions(cody, [{ id: "gpt-5.5 ", purpose: "" }]), ["gpt-5.5-mini"]);
});

test("unsaved work is a typed task Core has not accepted, or purpose edits", () => {
  const submission = new TaskSubmission();
  assert.equal(isDirty({ intent: "  ", submission, purposes: null }), false);
  assert.equal(isDirty({ intent: "Fix it", submission, purposes: null }), true);
  submission.begin({ intent: "Fix it" });
  submission.fail(new CoreError("lost"));
  assert.equal(isDirty({ intent: "Fix it", submission, purposes: null }), true, "an unconfirmed attempt still counts");
  submission.retry();
  submission.acknowledge({ task_id: "task-1" });
  assert.equal(isDirty({ intent: "Fix it", submission, purposes: null }), false);
  const base = { key: "agents.codex.model_choices", version: 10, revision: 0, saved: [{ id: "a", purpose: "" }] };
  assert.equal(isDirty({ intent: "", submission, purposes: { base, rows: [{ id: "a", purpose: "" }] } }), false);
  assert.equal(isDirty({ intent: "", submission, purposes: { base, rows: [{ id: "a", purpose: "x" }] } }), true);
});

// ---------- calls to Core ----------

function fakeFetch(responses) {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, method: init.method, body: init.body ? JSON.parse(init.body) : undefined, signal: init.signal });
    const next = responses.shift();
    if (next instanceof Error) throw next;
    if (next === "hang") {
      return new Promise((_, reject) => init.signal.addEventListener("abort",
        () => reject(Object.assign(new Error("aborted"), { name: "AbortError" }))));
    }
    return { ok: next.status < 300, status: next.status, json: async () => next.json };
  };
  return { calls, fetchImpl };
}

test("the page reads the cached list, refreshes only on request, and posts the pinned body", async () => {
  const { calls, fetchImpl } = fakeFetch([
    { status: 200, json: raw }, { status: 200, json: raw },
    { status: 201, json: { task_id: "task-1", status: "queued" } },
    { status: 200, json: { settings_version: 10, settings_revision: 1 } },
  ]);
  const core = new AgentsCore(new CoreApi({ fetchImpl }));
  await core.catalogue();
  await core.refresh();
  const body = Object.freeze({ intent: "Do it", idempotency_key: "key-1", explicit_provider: "deterministic-mock" });
  assert.deepEqual(await core.delegate(body), { task_id: "task-1", status: "queued" });
  await core.savePurposes({ version: 10, expected_revision: 0, changes: { "agents.codex.model_choices": [] } });
  assert.deepEqual(calls.map((c) => `${c.method} ${c.url}`), [
    "GET /api/v1/agents/catalogue", "POST /api/v1/agents/catalogue/refresh", "POST /api/v1/tasks", "POST /api/v1/settings"]);
  assert.deepEqual(calls[1].body, {});
  assert.deepEqual(calls[2].body, body);
  assert.ok(calls.every((c) => c.signal), "every call can be abandoned at its deadline");
});

test("a call that outlives its deadline is aborted and reported as no answer (status 0)", async () => {
  const { calls, fetchImpl } = fakeFetch(["hang"]);
  const core = new AgentsCore(new CoreApi({ fetchImpl }), { taskMs: 20 });
  await assert.rejects(core.delegate({ intent: "x", idempotency_key: "k" }), (error) => {
    assert.ok(error instanceof CoreError);
    assert.equal(error.code, "TIMEOUT");
    assert.equal(error.unavailable, true);
    return true;
  });
  assert.equal(calls[0].signal.aborted, true);
  // Even a call that ignores its abort signal stops being waited for.
  await assert.rejects(withDeadline(20, () => new Promise(() => {})), /No answer from Core within 1 second\./);
});

test("Core errors keep their code, and only unreachable or restarted Cores make the list stale", async () => {
  const { fetchImpl } = fakeFetch([
    { status: 409, json: { error: { code: "SETTINGS_CONFLICT", message: "Settings changed before this edit. Refresh and try again." } } },
  ]);
  const core = new AgentsCore(new CoreApi({ fetchImpl }));
  await assert.rejects(core.savePurposes({}), (error) => error.code === "SETTINGS_CONFLICT" && error.status === 409);
  assert.equal(staleCatalogueError(new CoreError("x", { status: 503, code: "CORE_UNAVAILABLE" })), true);
  assert.equal(staleCatalogueError(new CoreError("x", { status: 409, code: "RUNTIME_CHANGED" })), true);
  assert.equal(staleCatalogueError(new CoreError("x", { status: 500, code: "INTERNAL_ERROR" })), false);
});
