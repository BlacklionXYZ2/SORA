import assert from "node:assert/strict";
import { test } from "node:test";

import { CoreApi } from "../shared/api.js";
import { send } from "../shared/bridge.js";
import {
  CoreChangedError, DEFAULT_QUERY, EditDraft, ErrorDetails, FORGET_MEANING, MAX_PAGES, MemoryBrowser,
  contentError, inspectionFacts, navigationOutcome, pageStatus, parseAck, parseDetail, parsePage,
  queryError, referenceListed, sha256Hex,
} from "../memory/memory-model.js";

const EPOCH = "4e61839a-2ded-42e3-bb38-dc44f9d9aab2";
const OTHER = "0b0c3d1e-7f4a-4c55-9a1b-2c3d4e5f6a7b";
const NOTE = "Canonical owner-local records. Literal content search, not semantic ranking.";

function summary(id, extra = {}) {
  return { schema_version: "1.0", memory_id: id, owner_id: "owner-local", project_id: "project-sora",
    entity_version: 1, state: "active", scope: "dialogue", sensitivity: "private", retention: "durable",
    provenance: "owner-stated", metadata_truncated: false, content_preview: `Words of ${id}`,
    content_truncated: false, valid_until: null, ...extra };
}

function pageOf(ids, { query = DEFAULT_QUERY, next = null, total = ids.length, instance = EPOCH } = {}) {
  return { schema_version: "1.0", instance_id: instance, owner_id: "owner-local", project_id: "project-sora",
    projection_revision: 73, observed_at: "2026-10-12T09:06:16.656101Z", evidence_note: NOTE,
    state_filter: query.state, project_filter: query.project, scope_filter: query.scope, query: query.q,
    limit: 50, memories: ids.map((id) => summary(id)), total, next_cursor: next };
}

function detailOf(id, extra = {}, { instance = EPOCH, evidence = [] } = {}) {
  return { schema_version: "1.0", instance_id: instance, owner_id: "owner-local", project_id: "project-sora",
    projection_revision: 73, observed_at: "2026-10-12T09:06:22.096965Z", evidence_note: NOTE,
    memory: { ...summary(id), content: `Full words of ${id}`, superseded_by: null, evidence,
      evidence_withheld: false, ...extra } };
}

function reply(status, data) {
  return { ok: status >= 200 && status < 300, status, json: async () => data, clone: () => reply(status, data) };
}

/** A fake Core behind the real CoreApi: routes are "METHOD /path" → (request) => reply | Promise. */
function fakeCore(routes = {}) {
  const calls = [];
  const fetchImpl = async (url, init = {}) => {
    const method = init.method ?? "GET";
    const call = { url, method, body: init.body === undefined ? undefined : JSON.parse(init.body) };
    calls.push(call);
    const handler = routes[`${method} ${url}`] ?? routes[`${method} ${url.split("?")[0]}`];
    if (!handler) return reply(404, { error: { code: "NOT_FOUND", message: "Memory/receipt not found" } });
    return handler(call);
  };
  const errors = new ErrorDetails(fetchImpl);
  return { api: new CoreApi({ fetchImpl: errors.fetch }), errors, calls, routes };
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

const identity = () => reply(200, { version: 1, instance_id: EPOCH, owner_id: "owner-local", project_id: "project-sora" });
const FIRST = "/api/v1/memories?limit=50&state=active&project=all&q=&scope=";

function browser(routes, options = {}) {
  const core = fakeCore({ "GET /api/v1/runtime/identity": identity, ...routes });
  let n = 0;
  const memory = new MemoryBrowser({ api: core.api, errors: core.errors,
    newId: () => `00000000-0000-4000-8000-${String(++n).padStart(12, "0")}`, ...options });
  const cleared = [];
  memory.onHighlightCleared = () => cleared.push(true);
  return { memory, core, cleared, s: memory.state };
}

async function ackFor(body, action, { replayed = false } = {}) {
  return { schema_version: "1.0", instance_id: EPOCH, committed_instance_id: EPOCH, request_id: body.request_id,
    owner_id: "owner-local", project_id: "project-sora", memory_id: "memory-teal", action,
    expected_version: body.expected_version, entity_version: body.expected_version + 1,
    successor_id: action === "correct" ? "memory-9f1c" : null, successor_version: action === "correct" ? 1 : null,
    content_sha256: action === "correct" ? await sha256Hex(body.content) : null, projection_revision: 74,
    event_id: "event-1", committed_at: "2026-10-12T09:10:00.000001Z", replayed,
    retention_note: "Only this exact canonical record is affected." };
}

// ---------- validation and Core's data ----------

test("filters are checked before Core is asked, the way Core checks them", () => {
  assert.equal(queryError(DEFAULT_QUERY), "");
  assert.equal(queryError({ ...DEFAULT_QUERY, q: "a..b teal", state: "all", project: "global", scope: "qa-bulk" }), "");
  for (const bad of [{ q: "x".repeat(257) }, { scope: "s".repeat(129) }, { q: "line\nbreak" }, { scope: "\u0085" },
    { q: "\ud800" }, { state: "deleted" }, { project: "other" }, { q: 5 }]) {
    assert.match(queryError({ ...DEFAULT_QUERY, ...bad }), /256 characters/, JSON.stringify(bad));
  }
});

test("a page is shown only when it matches the filters it was asked for", () => {
  const page = parsePage(pageOf(["memory-b", "memory-a"], { next: "abc_-1", total: 63 }), DEFAULT_QUERY, EPOCH);
  assert.deepEqual(page.items.map((m) => m.id), ["memory-b", "memory-a"]);
  assert.equal(page.nextCursor, "abc_-1");
  assert.equal(page.total, 63);
  const broken = [
    (p) => { p.query = "teal"; },                                   // other filters echoed
    (p) => { p.limit = 20; },
    (p) => { p.memories.push(summary("memory-b")); },              // a repeated memory
    (p) => { p.memories[0].state = "expired"; },                   // not the state asked for
    (p) => { p.total = 1; },                                       // count below what was sent
    (p) => { p.next_cursor = "not/a/cursor"; },
    (p) => { p.memories[0].owner_id = "someone-else"; },
    (p) => { p.memories[0].project_id = "project-other"; },
    (p) => { p.observed_at = "2026-10-12T09:06:16"; },             // no time zone
    (p) => { p.schema_version = "2.0"; },
  ];
  for (const change of broken) {
    const data = pageOf(["memory-b", "memory-a"]);
    change(data);
    assert.throws(() => parsePage(data, DEFAULT_QUERY, EPOCH), /Core/, change.toString());
  }
  const empty = pageOf([], { next: "more" });
  assert.throws(() => parsePage(empty, DEFAULT_QUERY, EPOCH), /empty page/);
  assert.throws(() => parsePage(pageOf(["memory-a"], { instance: OTHER }), DEFAULT_QUERY, EPOCH), CoreChangedError);
  const global = { ...DEFAULT_QUERY, project: "global" };
  assert.throws(() => parsePage(pageOf(["memory-a"], { query: global }), global, EPOCH), /filters/);
});

test("an exact memory is never substituted, and private or unknown evidence is refused", () => {
  const link = { schema_version: "1.0", reference_id: "content-trip-notes", label: "Weekend trip notes", kind: "file" };
  const detail = parseDetail(detailOf("memory-trip", {}, { evidence: [link] }), "memory-trip", EPOCH);
  assert.equal(detail.content, "Full words of memory-trip");
  assert.deepEqual(detail.evidence, [{ id: "content-trip-notes", label: "Weekend trip notes", kind: "file" }]);
  assert.throws(() => parseDetail(detailOf("memory-other"), "memory-trip", EPOCH), /different memory/);
  assert.throws(() => parseDetail(detailOf("memory-trip", {}, { evidence: [{ ...link, reference_id: "capture-1" }] }),
    "memory-trip", EPOCH), /must not show/);
  assert.throws(() => parseDetail(detailOf("memory-trip", {}, { evidence: [{ ...link, kind: "secret" }] }),
    "memory-trip", EPOCH), /must not show/);
  assert.throws(() => parseDetail(detailOf("memory-trip", {}, { evidence: [link, link] }), "memory-trip", EPOCH),
    /must not show/);
  assert.throws(() => parseDetail(detailOf("memory-trip", { content: "" }), "memory-trip", EPOCH), /content/);
  assert.throws(() => parseDetail(detailOf("memory-trip"), "../memory", EPOCH), /exact memory ID/);
  assert.throws(() => parseDetail(detailOf("memory-trip", {}, { instance: OTHER }), "memory-trip", EPOCH),
    CoreChangedError);
});

test("the inspector shows only what Core's record has: no dates, importance or connections", () => {
  const detail = parseDetail(detailOf("memory-repo", { project_id: null, scope: "", valid_until: "2026-11-10T09:02:23Z" }),
    "memory-repo", EPOCH);
  const facts = inspectionFacts(detail);
  assert.deepEqual(facts.map((f) => f.label),
    ["Scope", "Project", "Sensitivity", "Keep for", "Where it came from", "Valid until"]);
  assert.equal(facts[0].value, "None recorded");
  assert.equal(facts[1].value, "Global (every project)");
  assert.match(facts[5].value, /2026/);
  assert.equal(facts[5].title, "2026-11-10T09:02:23Z");
  const words = facts.map((f) => `${f.label} ${f.value}`).join(" ").toLowerCase();
  for (const invented of ["created", "importance", "relevance", "connection", "title"]) {
    assert.ok(!words.includes(invented), invented);
  }
  const plain = parseDetail(detailOf("memory-teal"), "memory-teal", EPOCH);
  assert.equal(inspectionFacts(plain)[1].value, "This project (project-sora)");
  assert.equal(inspectionFacts(plain)[5].value, "No expiry recorded");
});

test("correction text is counted in characters, as Core counts it, and must be meaningful", () => {
  assert.equal(contentError("Oscar's favourite colour is teal."), "");
  assert.equal(contentError("😀".repeat(16384)), "");             // 32,768 UTF-16 units, 16,384 characters
  assert.match(contentError("😀".repeat(16385)), /16,385 characters/);
  assert.match(contentError(" \n\t "), /Write the corrected memory/);
  assert.match(contentError("a\0b"), /NUL/);
  assert.match(contentError("broken \ud83d"), /broken character/);
});

test("Core's answer about opening evidence reads as the classic panel wrote it", () => {
  assert.deepEqual(navigationOutcome({ status: "opened_with_limitations", reason: "Opened in Notepad",
    reference_id: "content-trip-notes", limitations: ["read only", "no focus"] }, "content-trip-notes"),
  { ok: true, text: "content-trip-notes · opened with limitations: Opened in Notepad · read only · no focus" });
  assert.equal(navigationOutcome({ status: "unsupported", reason: "No handler", reference_id: null },
    "content-trip-notes").ok, false);
  assert.throws(() => navigationOutcome({ status: "opened", reason: "ok", reference_id: "content-other" },
    "content-trip-notes"), /outcome is unknown/);
  assert.throws(() => navigationOutcome({ status: "opened", reason: " " }, "content-trip-notes"), /unknown/);
  assert.equal(referenceListed({ references: [{ reference_id: "content-trip-notes", path: "C:/secret" }] },
    "content-trip-notes"), true);
  assert.equal(referenceListed({ references: [] }, "content-trip-notes"), false);
});

// ---------- drafts and receipts ----------

function teal(state = "active", version = 1, instance = EPOCH) {
  return parseDetail(detailOf("memory-teal", { state, entity_version: version }, { instance }), "memory-teal", instance);
}

test("a draft keeps one request ID across retries and never reuses it for a new edit", () => {
  let n = 0;
  const newId = () => `00000000-0000-4000-8000-00000000000${++n}`;
  const draft = new EditDraft(teal());
  draft.edit("Oscar's favourite colour is dark teal.");
  const first = draft.begin(EPOCH, newId);
  assert.equal(first.requestId, "00000000-0000-4000-8000-000000000001");
  assert.equal(draft.begin(EPOCH, newId), first, "an unresolved request is retried as it was");
  assert.throws(() => draft.edit("changed"), /frozen/);
  assert.throws(() => draft.review(teal()), /cannot replace/);
  draft.reject();
  assert.notEqual(draft.begin(EPOCH, newId).requestId, first.requestId, "a new edit gets a new ID");
  assert.throws(() => new EditDraft(teal()).begin(OTHER, newId), /restarted/);
  assert.throws(() => new EditDraft(teal("expired")).begin(EPOCH, newId), /active/);
  const blank = new EditDraft(teal());
  blank.edit("   ");
  assert.throws(() => blank.begin(EPOCH, newId), /Write the corrected memory/);
  assert.equal(new EditDraft(teal(), "forget").begin(EPOCH, newId).content, null);
});

test("a receipt is accepted only when every field matches the change that was sent", async () => {
  const draft = new EditDraft(teal());
  draft.edit("Oscar's favourite colour is dark teal.");
  const intent = draft.begin(EPOCH, () => "11111111-2222-4333-8444-555555555555");
  intent.contentSha256 = await sha256Hex(intent.content);
  const body = { request_id: intent.requestId, expected_version: 1, content: intent.content };
  const good = await ackFor(body, "correct");
  const ack = parseAck(good, intent, EPOCH);
  assert.equal(ack.successor, "memory-9f1c");
  assert.equal(ack.version, 2);
  assert.equal(ack.historical, false);
  const broken = [
    { content_sha256: await sha256Hex("Oscar's favourite colour is teal.") },
    { instance_id: OTHER },
    { request_id: "11111111-2222-4333-8444-000000000000" },
    { entity_version: 3 },
    { memory_id: "memory-other" },
    { action: "forget" },
    { project_id: null },
    { successor_id: "memory-teal" },
    { successor_version: 2 },
    { committed_at: "2026-10-12T09:10:00" },
    { projection_revision: 0 },
    { retention_note: "" },
  ];
  for (const change of broken) {
    assert.throws(() => parseAck({ ...good, ...change }, intent, EPOCH), /unconfirmed/, JSON.stringify(change));
  }
  const forget = new EditDraft(teal(), "forget").begin(EPOCH, () => "11111111-2222-4333-8444-555555555556");
  forget.contentSha256 = null;
  const forgetAck = await ackFor({ request_id: forget.requestId, expected_version: 1 }, "forget");
  assert.equal(parseAck(forgetAck, forget, EPOCH).successor, null);
  assert.throws(() => parseAck({ ...forgetAck, successor_id: "memory-x", successor_version: 1 }, forget, EPOCH),
    /new version/);
});

// ---------- the panel's behaviour ----------

test("an older, slower page never overwrites a newer one", async () => {
  const slow = deferred();
  const { memory, s } = browser({
    [`GET ${FIRST}`]: () => slow.promise,
    "GET /api/v1/memories?limit=50&state=all&project=all&q=&scope=": () =>
      reply(200, pageOf(["memory-new"], { query: { ...DEFAULT_QUERY, state: "all" } })),
  });
  await memory.checkIdentity();
  const older = memory.readPage();
  memory.setFilter("state", "all");
  assert.equal(await memory.readPage(), true);
  slow.resolve(reply(200, pageOf(["memory-old"])));
  assert.equal(await older, false);
  assert.deepEqual(s.page.items.map((m) => m.id), ["memory-new"]);
  assert.equal(s.applied.state, "all");
  assert.equal(s.reading, false);
});

test("selecting reads that exact memory; an overtaken read is dropped", async () => {
  const slow = deferred();
  const { memory, s } = browser({
    "GET /api/v1/memories/memory-a": () => slow.promise,
    "GET /api/v1/memories/memory-b": () => reply(200, detailOf("memory-b")),
  });
  await memory.checkIdentity();
  const first = memory.select("memory-a");
  assert.equal(s.inspecting, true);
  await memory.select("memory-b");
  slow.resolve(reply(200, detailOf("memory-a")));
  assert.equal(await first, false);
  assert.equal(s.selected, "memory-b");
  assert.equal(s.detail.item.id, "memory-b");
  assert.equal(s.detailCurrent, true);
  assert.equal(await memory.select("memory..a"), false, "an ID the proxy refuses is not sent");
  assert.match(s.outcome.text, /not an exact memory ID/);
});

test("paging passes Core's cursors unchanged and keeps a bounded history", async () => {
  const { memory, s, core } = browser({
    [`GET ${FIRST}`]: () => reply(200, pageOf(["memory-2", "memory-1"], { next: "c1", total: 3 })),
    [`GET ${FIRST}&cursor=c1`]: () => reply(200, pageOf(["memory-0"], { total: 3 })),
  });
  await memory.checkIdentity();
  await memory.readPage();
  assert.equal(memory.availability().next, true);
  await memory.next();
  assert.equal(s.pageIndex, 1);
  assert.deepEqual(s.cursors, [null, "c1"]);
  assert.equal(memory.availability().next, false);
  await memory.previous();
  assert.equal(s.pageIndex, 0);
  assert.deepEqual(core.calls.filter((c) => c.url.startsWith("/api/v1/memories?")).map((c) => c.url),
    [FIRST, `${FIRST}&cursor=c1`, FIRST]);
  s.pageIndex = MAX_PAGES - 1;
  assert.equal(memory.availability().next, false, "no page beyond the history bound");
  memory.setFilter("q", "teal");
  assert.equal(memory.availability().previous, false, "changed filters make the page stale");
  assert.match(pageStatus(s), /may be out of date/);
});

test("a restarted Core clears what was read but keeps typed filters and the draft", async () => {
  let instance = EPOCH;
  const { memory, s } = browser({
    "GET /api/v1/runtime/identity": () => reply(200, { instance_id: instance }),
    [`GET ${FIRST}`]: () => reply(200, pageOf(["memory-teal"])),
    "GET /api/v1/memories/memory-teal": () => reply(200, detailOf("memory-teal", {}, { instance })),
  });
  await memory.start();
  assert.equal(s.selected, "memory-teal");
  memory.startCorrection();
  memory.setFilter("q", "teal");
  assert.equal(s.typed.q, "", "filters are locked while a draft exists");
  memory.cancelConfirm();
  instance = OTHER;
  await memory.checkIdentity();
  assert.equal(s.page, null);
  assert.equal(s.selected, null);
  assert.equal(s.epoch, OTHER);
  assert.match(s.listNote.text, /restarted/);
  assert.ok(s.draft, "the draft survives, pinned to the old Core");
  assert.equal(memory.availability().save, false);
  assert.equal(memory.availability().review, true);
});

test("saving a correction sends exactly instance, request, version and text, then confirms Core's receipt", async () => {
  const { memory, s, core } = browser({
    [`GET ${FIRST}`]: () => reply(200, pageOf(["memory-teal"])),
    "GET /api/v1/memories/memory-teal": () => reply(200, detailOf("memory-teal")),
    "POST /api/v1/memories/memory-teal/correct": async ({ body }) => reply(200, await ackFor(body, "correct")),
  });
  await memory.start();
  assert.equal(memory.dirty, false);
  assert.equal(memory.startCorrection(), true);
  assert.equal(memory.dirty, true);
  memory.editDraft("Oscar's favourite colour is dark teal.");
  assert.equal(await memory.submit(), true);
  const post = core.calls.find((c) => c.method === "POST");
  assert.deepEqual(post.body, { instance_id: EPOCH, request_id: "00000000-0000-4000-8000-000000000001",
    expected_version: 1, content: "Oscar's favourite colour is dark teal." });
  assert.equal(s.draft, null);
  assert.equal(memory.dirty, false);
  assert.equal(s.detailCurrent, false, "the shown record is no longer current");
  assert.match(s.outcome.text, /Core confirmed the correction of memory-teal \(now version 2\)/);
  assert.equal(s.outcome.successor, "memory-9f1c");
});

test("a version conflict releases the draft and shows Core's current version and state", async () => {
  const { memory, s } = browser({
    [`GET ${FIRST}`]: () => reply(200, pageOf(["memory-teal"])),
    "GET /api/v1/memories/memory-teal": () => reply(200, detailOf("memory-teal")),
    "POST /api/v1/memories/memory-teal/correct": () => reply(409, { error: {
      message: "Memory changed or request conflicts; inspect before editing", code: "MEMORY_VERSION_CONFLICT",
      status: 409, current_version: 3, current_state: "superseded" } }),
  });
  await memory.start();
  memory.startCorrection();
  memory.editDraft("New words");
  assert.equal(await memory.submit(), false);
  assert.match(s.outcome.text, /changed in Core.*version 3, replaced/);
  assert.match(s.outcome.note, /MEMORY_VERSION_CONFLICT/);
  assert.equal(s.draft.pending, null, "nothing was written, so the draft can be reviewed and edited");
  assert.equal(s.draft.text, "New words");
  assert.equal(memory.availability().review, true);
});

test("an unconfirmed save is frozen: nothing is re-sent until the owner asks, and Retry reuses the request", async () => {
  let posts = 0;
  let receipt = null;
  const { memory, s, core } = browser({
    [`GET ${FIRST}`]: () => reply(200, pageOf(["memory-teal"])),
    "GET /api/v1/memories/memory-teal": () => reply(200, detailOf("memory-teal")),
    "POST /api/v1/memories/memory-teal/correct": async ({ body }) => {
      posts += 1;
      receipt = await ackFor(body, "correct", { replayed: true });
      return reply(503, { error: { code: "MEMORY_UNAVAILABLE", message: "Canonical Memory mutation unavailable" } });
    },
  });
  await memory.start();
  memory.startCorrection();
  memory.editDraft("Teal, but darker");
  assert.equal(await memory.submit(), false);
  assert.equal(posts, 1);
  assert.equal(s.draft.needsResolution, true);
  assert.equal(memory.dirty, true);
  assert.match(s.outcome.text, /could not confirm.*Nothing will be sent again by itself/);
  assert.equal(memory.editDraft("other words"), false, "the frozen text cannot change");
  assert.deepEqual([memory.availability().save, memory.availability().review], [false, false]);
  await new Promise((done) => setTimeout(done, 20));
  assert.equal(posts, 1, "no automatic retry");
  await memory.submit();   // the owner presses Retry same request
  const bodies = core.calls.filter((c) => c.method === "POST").map((c) => c.body);
  assert.equal(bodies.length, 2);
  assert.deepEqual(bodies[0], bodies[1], "a retry is the exact same request");
  core.routes[`GET /api/v1/memory-mutations/${bodies[0].request_id}`] = () => reply(200, receipt);
  assert.equal(await memory.checkReceipt(), true);
  assert.equal(s.draft, null);
  assert.match(s.outcome.text, /Core's receipt confirms the correction/);
});

test("no answer, a timeout or a missing receipt leaves the request frozen", async () => {
  const { memory, s } = browser({
    [`GET ${FIRST}`]: () => reply(200, pageOf(["memory-teal"])),
    "GET /api/v1/memories/memory-teal": () => reply(200, detailOf("memory-teal")),
    "POST /api/v1/memories/memory-teal/forget": () => { throw new TypeError("Failed to fetch"); },
  });
  await memory.start();
  memory.askForget();
  await memory.confirmForget();
  assert.equal(s.draft.action, "forget");
  assert.equal(s.draft.needsResolution, true);
  assert.match(s.outcome.text, /could not confirm whether Core forgot/);
  assert.equal(await memory.checkReceipt(), false, "404: no receipt");
  assert.equal(s.draft.needsResolution, true);
  assert.match(s.outcome.text, /no receipt does not prove nothing was saved/);

  const never = new Promise(() => {});
  const quick = { setTimeout: (fn) => { queueMicrotask(fn); return 1; }, clearTimeout() {} };
  const slow = browser({ "POST /api/v1/memories/memory-teal/correct": () => never }, { timers: quick });
  slow.memory.observe(EPOCH, true);
  slow.s.selected = "memory-teal";
  slow.s.detail = teal();
  slow.s.detailCurrent = true;
  slow.memory.startCorrection();
  slow.memory.editDraft("words");
  assert.equal(await slow.memory.submit(), false);
  assert.equal(slow.s.draft.needsResolution, true, "a timeout is not a failure");
  assert.match(slow.s.outcome.note, /did not answer in time/);
});

test("Forget asks first, checks the record did not change, and a refusal leaves nothing behind", async () => {
  const { memory, s, core } = browser({
    [`GET ${FIRST}`]: () => reply(200, pageOf(["memory-teal"])),
    "GET /api/v1/memories/memory-teal": () => reply(200, detailOf("memory-teal")),
    "POST /api/v1/memories/memory-teal/forget": () => reply(409, { error: { code: "MEMORY_VERSION_CONFLICT",
      message: "Memory changed", status: 409, current_version: 2, current_state: "active" } }),
  });
  await memory.start();
  assert.equal(memory.askForget(), true);
  assert.equal(memory.busy, true, "an open confirmation holds Quit");
  assert.match(FORGET_MEANING, /pictures, your recording.*deleted too/);
  assert.match(FORGET_MEANING, /no Undo/i);
  memory.cancelConfirm();
  assert.equal(core.calls.filter((c) => c.method === "POST").length, 0);
  memory.askForget();
  s.detail = teal("active", 1);   // the record was read again while the owner decided
  await memory.confirmForget();
  assert.equal(core.calls.filter((c) => c.method === "POST").length, 0, "nothing sent");
  assert.match(s.outcome.text, /changed while you were deciding/);
  s.detailCurrent = true;
  memory.askForget();
  await memory.confirmForget();
  const post = core.calls.find((c) => c.method === "POST");
  assert.deepEqual(Object.keys(post.body).sort(), ["expected_version", "instance_id", "request_id"]);
  assert.equal(s.draft, null, "a refused Forget keeps no draft");
  assert.match(s.outcome.text, /version 2, active/);
});

test("Open evidence re-reads the memory and the registered list before asking Core, never after a refusal", async () => {
  const link = { schema_version: "1.0", reference_id: "content-trip-notes", label: "Weekend trip notes", kind: "file" };
  let linked = [link];
  let registered = true;
  const { memory, s, core } = browser({
    [`GET ${FIRST}`]: () => reply(200, pageOf(["memory-trip"])),
    "GET /api/v1/memories/memory-trip": () => reply(200, detailOf("memory-trip", {}, { evidence: linked })),
    "GET /api/v1/content/references": () => reply(200, { references: registered
      ? [{ reference_id: "content-trip-notes", kind: "file", label: "Weekend trip notes", path: "/home/x/trip.txt" }] : [] }),
    "POST /api/v1/content/navigate": () => reply(200, { schema_version: "1.0", status: "opened", reason: "Opened with the default app",
      resolution: "explicit", reference_id: "content-trip-notes", handler_id: null, process_id: 42, limitations: [] }),
  });
  await memory.start();
  assert.equal(await memory.openEvidence("content-trip-notes"), true);
  assert.deepEqual(core.calls.slice(-3).map((c) => `${c.method} ${c.url}`), [
    "GET /api/v1/memories/memory-trip", "GET /api/v1/content/references", "POST /api/v1/content/navigate"]);
  assert.deepEqual(core.calls.at(-1).body, { utterance: "open this referenced content", verb: "open",
    explicit_reference_id: "content-trip-notes" });
  assert.equal(s.outcome.text, "content-trip-notes · opened: Opened with the default app");
  assert.ok(!JSON.stringify(s).includes("/home/x/trip.txt"), "a reference's local path is never kept");
  registered = false;
  await memory.openEvidence("content-trip-notes");
  assert.match(s.outcome.text, /no longer registered.*nothing was opened/);
  linked = [];
  registered = true;
  s.detail = parseDetail(detailOf("memory-trip", {}, { evidence: [link] }), "memory-trip", EPOCH);
  await memory.openEvidence("content-trip-notes");
  assert.match(s.outcome.text, /no longer linked/);
  assert.equal(core.calls.filter((c) => c.method === "POST").length, 1, "only the first open was sent");
});

test("when the host blocks Core, reading continues but Correct, Forget and Open wait", async () => {
  const { memory } = browser({
    [`GET ${FIRST}`]: () => reply(200, pageOf(["memory-teal"])),
    "GET /api/v1/memories/memory-teal": () => reply(200, detailOf("memory-teal")),
  });
  await memory.start();
  assert.deepEqual([memory.availability().correct, memory.availability().forget, memory.availability().open],
    [true, true, true]);
  memory.setCanUseCore(false);
  assert.deepEqual([memory.availability().correct, memory.availability().forget, memory.availability().open],
    [false, false, false]);
  assert.equal(memory.availability().browse, true);
  assert.equal(await memory.select("memory-teal"), true, "reads still work");
  assert.equal(memory.startCorrection(), false);
});

// ---------- SORA's presentation ----------

const REQUEST = "6a1f8a10-3b2c-4d5e-8f90-1a2b3c4d5e6f";
const present = (memory, extra = {}) => memory.present({ type: "host.present-memory", requestId: REQUEST,
  id: "memory-teal", version: 1, expiresAt: new Date(Date.now() + 15000).toISOString(), ...extra });

test("SORA's request selects and highlights only the exact version asked for", async () => {
  const { memory, s, cleared } = browser({
    [`GET ${FIRST}`]: () => reply(200, pageOf(["memory-a", "memory-teal"])),
    "GET /api/v1/memories/memory-a": () => reply(200, detailOf("memory-a")),
    "GET /api/v1/memories/memory-teal": () => reply(200, detailOf("memory-teal")),
  });
  await memory.start();
  assert.equal(s.selected, "memory-a");
  const result = await present(memory);
  assert.deepEqual(result, { requestId: REQUEST, status: "selected" });
  assert.equal(s.selected, "memory-teal");
  assert.equal(s.highlight.id, "memory-teal");
  assert.equal(memory.busy, true, "busy until the page has measured and replied");
  assert.equal(memory.endPresentation(REQUEST), true);
  assert.equal(memory.busy, false);
  memory.presentationOutcome({ requestId: REQUEST, confirmed: true });
  assert.equal(s.outcome.text, "SORA highlighted this memory.");
  await memory.select("memory-a");
  assert.equal(s.highlight, null, "choosing something else clears the highlight");
  assert.equal(cleared.length, 1);
  // The reply the page sends is one the bridge accepts.
  assert.deepEqual(send("memory.presented", { ...result, anchor: { x: 560, y: 60, width: 400, height: 600 } }).status,
    "selected");
  assert.throws(() => send("memory.presented", { requestId: REQUEST, status: "selected" }), TypeError);
  assert.throws(() => send("memory.presented", { requestId: REQUEST, status: "unavailable",
    anchor: { x: 0, y: 0, width: 1, height: 1 } }), TypeError);
});

test("a presentation of what is already on screen says so, and only one runs at a time", async () => {
  const { memory } = browser({
    [`GET ${FIRST}`]: () => reply(200, pageOf(["memory-teal"])),
    "GET /api/v1/memories/memory-teal": () => reply(200, detailOf("memory-teal")),
  });
  await memory.start();
  const second = REQUEST.replace("6a", "7a");
  assert.equal((await present(memory)).status, "already-visible");
  assert.equal((await present(memory, { requestId: second })).status, "unavailable", "one at a time");
  assert.equal(memory.endPresentation(second), false, "a refused request cannot end the running one");
  assert.equal(memory.busy, true);
  memory.endPresentation(REQUEST);
  memory.clearHighlight();
  const hidden = await memory.present({ requestId: second, id: "memory-teal", version: 1,
    expiresAt: new Date(Date.now() + 15000).toISOString() }, { visible: false });
  assert.equal(hidden.status, "selected", "a hidden window was not already showing it");
});

test("when SORA opens Memory on a record, the list still loads and that record stays selected", async () => {
  const gate = deferred();
  const { memory, s, cleared } = browser({
    "GET /api/v1/runtime/identity": async () => { await gate.promise; return identity(); },
    [`GET ${FIRST}`]: () => reply(200, pageOf(["memory-a"])),
    "GET /api/v1/memories/memory-teal": () => reply(200, detailOf("memory-teal")),
  });
  const starting = memory.start();
  // The host's request lands while the page is still starting.
  assert.equal((await present(memory)).status, "selected");
  gate.resolve();
  await starting;
  assert.equal(s.page, null, "the first read waits while SORA's request runs");
  memory.endPresentation(REQUEST);
  await new Promise((done) => setTimeout(done, 0));
  assert.deepEqual(s.page.items.map((m) => m.id), ["memory-a"]);
  assert.equal(s.selected, "memory-teal", "not on this page, but SORA is showing it");
  assert.equal(s.highlight.id, "memory-teal");
  assert.equal(cleared.length, 0);
});

test("when Core was down at the start, the page reads as soon as it answers", async () => {
  let up = false;
  const { memory, s } = browser({
    "GET /api/v1/runtime/identity": () => (up ? identity() : reply(503, { error: { code: "CORE_UNAVAILABLE", message: "Core is starting" } })),
    [`GET ${FIRST}`]: () => (up ? reply(200, pageOf(["memory-teal"])) : reply(503, { error: { code: "CORE_UNAVAILABLE", message: "Core is starting" } })),
    "GET /api/v1/memories/memory-teal": () => reply(200, detailOf("memory-teal")),
  });
  await memory.start();
  assert.equal(s.connected, false);
  assert.equal(s.page, null);
  assert.match(s.listNote.text, /could not be read.*Core is starting/);
  up = true;
  await memory.poll();
  assert.equal(s.connected, true);
  assert.deepEqual(s.page.items.map((m) => m.id), ["memory-teal"]);
});

test("another version, a missing memory, a draft or an expired request is unavailable and changes nothing", async () => {
  const { memory, s } = browser({
    [`GET ${FIRST}`]: () => reply(200, pageOf(["memory-a"])),
    "GET /api/v1/memories/memory-a": () => reply(200, detailOf("memory-a")),
    "GET /api/v1/memories/memory-teal": () => reply(200, detailOf("memory-teal", { entity_version: 2 })),
  });
  await memory.start();
  const outcome = async (extra) => {
    const result = await present(memory, extra);
    memory.endPresentation(REQUEST);
    return result?.status;
  };
  assert.equal(await outcome({}), "unavailable");
  assert.equal(s.selected, "memory-a", "nothing else is selected");
  assert.match(s.outcome.text, /version 1.*Core now has version 2/);
  assert.equal(await outcome({ id: "memory-gone" }), "unavailable");
  assert.equal(await outcome({ expiresAt: new Date(Date.now() - 1).toISOString() }), "unavailable");
  assert.equal(await present(memory, { requestId: "not-a-uuid" }), null, "no reply is possible");
  memory.startCorrection();
  assert.equal(await outcome({ version: 2 }), "unavailable");
  assert.equal(s.selected, "memory-a");
  assert.equal(s.highlight, null);
});

test("the highlight clears when it expires, on a filter change, on scroll and when Core does not confirm it", async () => {
  let now = Date.now();
  const { memory, s, cleared } = browser({
    [`GET ${FIRST}`]: () => reply(200, pageOf(["memory-teal"])),
    "GET /api/v1/memories/memory-teal": () => reply(200, detailOf("memory-teal")),
  }, { now: () => now });
  await memory.start();
  const show = async () => { await present(memory); memory.endPresentation(REQUEST); assert.ok(s.highlight); };
  await show();
  now += 16000;
  assert.equal(memory.expireHighlight(), true);
  now = Date.now();
  await show();
  memory.setFilter("q", "teal");
  assert.equal(s.highlight, null);
  memory.setFilter("q", "");
  await show();
  assert.equal(memory.userScrolled(), true);
  await show();
  memory.presentationOutcome({ requestId: "00000000-0000-4000-8000-000000000999", confirmed: false });
  assert.ok(s.highlight, "another request's outcome is ignored");
  memory.presentationOutcome({ requestId: REQUEST, confirmed: false });
  assert.equal(s.highlight, null);
  assert.equal(s.detailCurrent, false, "read again before relying on it");
  assert.match(s.outcome.text, /not confirmed.*Nothing else was selected/);
  assert.equal(cleared.length, 4);
});
