import assert from "node:assert/strict";
import { test } from "node:test";

import { CoreApi, CoreError } from "../shared/api.js";
import { send } from "../shared/bridge.js";
import {
  CORE_BLOCKED, EVENT_COLUMNS, LEASE_COLUMNS, MAX_EVENTS, PathsSession, eventRows, leaseRows,
  leaseStatusWords, nextSort, normaliseProjection, operationWords, readFailure, recheckFailure,
  sortRows, sourceWords, statusWords, taskLink, timeLabel,
} from "../paths/paths-model.js";

const NOTICE = "Declared roots and Core/provider evidence only; opaque agent reads are not fully "
  + "observed. Uncertain writers retain their roots until kernel-job reconciliation proves stop.";

const lease = (runId, acquiredAt, extra = {}) => ({
  run_id: runId, task_id: `task-${runId}`, canonical_root: "c:\\projects\\demo",
  display_root: "C:\\Projects\\demo", job_name: `Local\\SORAWriter_${runId}`, status: "reserved",
  acquired_at: acquiredAt, owner_pid: 4242, ...extra,
});
const event = (id, operation, status, source, extra = {}) => ({
  event_id: id, run_id: "run-1", path: "C:\\Projects\\demo\\src\\main.py", operation, status, source,
  occurred_at: "2026-10-12T08:54:01.814037+00:00", ...extra,
});
const projection = (leases = [lease("run-1", "2026-10-12T08:51:01+00:00")], events = [
  event("e2", "write.release", "uncertain", "core_observed"),
  event("e1", "write.reserve", "reserved", "declared_root"),
]) => ({ leases, events, notice: NOTICE });

/** A fake Core behind CoreApi: records every call and answers from `routes`. */
function fakeCore(routes) {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, method: init.method, body: init.body });
    const answer = await routes(`${init.method} ${url}`, calls.length);
    if (answer instanceof Error) throw answer;
    const { status = 200, json } = answer;
    return { ok: status >= 200 && status < 300, status, json: async () => json };
  };
  return { api: new CoreApi({ fetchImpl }), calls };
}

const identity = (instance = "core-a") => ({ json: { version: 1, instance_id: instance } });
const posts = (calls) => calls.filter((call) => call.method === "POST");

test("Core's values read as plain words, and the exact value stays alongside", () => {
  assert.deepEqual(operationWords("file.changed"),
    { label: "File changed", token: "file.changed", tone: "off", known: true,
      meaning: "The file's size or modified time differed after the run." });
  assert.equal(operationWords("write.release").label, "Release check");
  assert.equal(statusWords("uncertain").label, "Not sure it stopped");
  assert.equal(statusWords("conflict").tone, "bad");
  assert.equal(sourceWords("provider_reported").label, "Agent's own account");
  assert.equal(sourceWords("filesystem_diff").label, "File comparison");
  assert.equal(leaseStatusWords("uncertain").tone, "bad");
  assert.equal(leaseStatusWords("reserved").tone, "active");
  // Reported or observed evidence is never dressed up as verified success.
  for (const status of ["reported", "observed", "reserved"]) assert.notEqual(statusWords(status).tone, "ok");
  // Something Core adds later is shown as Core wrote it, not guessed at.
  assert.deepEqual(operationWords("file.renamed"),
    { label: "file.renamed", token: "file.renamed", tone: "off", meaning: "", known: false });
  assert.equal(statusWords("").label, "Not reported");
  assert.equal(statusWords("toString").known, false);
});

test("only the fields shown are read, and a reply that is not path evidence is refused", () => {
  const raw = projection([lease("run-1", "2026-10-12T08:51:01+00:00", { owner_pid: undefined, job_name: undefined, status: 7 })],
    [event("e1", "read", "reported", "provider_reported", { path: null }), null, "x"]);
  const shown = normaliseProjection(raw);
  assert.deepEqual(shown.leases, [{ run_id: "run-1", task_id: "task-run-1", display_root: "C:\\Projects\\demo",
    status: "", acquired_at: "2026-10-12T08:51:01+00:00" }]);
  assert.equal(shown.events.length, 1);
  assert.equal(shown.events[0].path, "");
  assert.equal(shown.notice, NOTICE);
  const many = Array.from({ length: 300 }, (_, i) => event(`e${i}`, "read", "reported", "provider_reported"));
  assert.equal(normaliseProjection(projection([], many)).events.length, MAX_EVENTS);
  for (const bad of [null, "nope", {}, { leases: [], events: {} }, { leases: "x", events: [] }]) {
    assert.equal(normaliseProjection(bad), null);
  }
});

test("reservations are newest first and open Activity only on an exact task ID", () => {
  const rows = leaseRows([lease("old", "2026-10-11T08:00:00+00:00"), lease("new", "2026-10-12T08:00:00+00:00"),
    lease("bad", "", { task_id: "../etc" })]);
  assert.deepEqual(rows.map((row) => row.runId), ["new", "old", "bad"]);
  assert.deepEqual(rows[0].link, { panel: "activity", select: "task-new" });
  assert.equal(rows[2].link, null);
  assert.equal(rows[2].reservedAt.text, "Not reported");
  assert.equal(taskLink(""), null);
  assert.equal(taskLink(42), null);
  assert.deepEqual(send("panel.open", rows[0].link), { type: "panel.open", panel: "activity", select: "task-new" });
});

test("evidence keeps Core's newest-first order with each value in words and as Core wrote it", () => {
  const rows = eventRows(projection().events);
  assert.deepEqual(rows.map((row) => row.key), ["e2", "e1"]);
  assert.deepEqual([rows[0].operation.token, rows[0].state.token, rows[0].source.token],
    ["write.release", "uncertain", "core_observed"]);
  assert.equal(rows[0].source.label, "SORA's own record");
});

test("times are shown locally, keep Core's exact value, and are never invented", () => {
  const shown = timeLabel("2026-10-12T08:54:01.814037+00:00");
  assert.equal(shown.exact, "2026-10-12T08:54:01.814037+00:00");
  assert.match(shown.text, /Oct/);
  assert.deepEqual(timeLabel(""), { text: "Not reported", exact: "" });
  assert.deepEqual(timeLabel(undefined), { text: "Not reported", exact: "" });
  assert.deepEqual(timeLabel("soon"), { text: "soon", exact: "soon" });
});

test("a column sorts ascending, flips on a second click, and keeps ties in order", () => {
  let sort = nextSort(null, "path");
  assert.deepEqual(sort, { key: "path", dir: "asc" });
  sort = nextSort(sort, "path");
  assert.deepEqual(sort, { key: "path", dir: "desc" });
  assert.deepEqual(nextSort(sort, "time"), { key: "time", dir: "asc" });
  const rows = eventRows([
    event("a", "read", "reported", "provider_reported", { path: "b.txt", occurred_at: "2026-10-12T09:00:00+00:00" }),
    event("b", "read", "reported", "provider_reported", { path: "a.txt", occurred_at: "2026-10-12T08:00:00+00:00" }),
    event("c", "read", "reported", "provider_reported", { path: "a.txt", occurred_at: "2026-10-12T10:00:00+00:00" }),
  ]);
  assert.deepEqual(sortRows(rows, EVENT_COLUMNS, { key: "path", dir: "asc" }).map((r) => r.key), ["b", "c", "a"]);
  assert.deepEqual(sortRows(rows, EVENT_COLUMNS, { key: "time", dir: "desc" }).map((r) => r.key), ["c", "a", "b"]);
  assert.equal(sortRows(rows, EVENT_COLUMNS, null), rows);
  assert.equal(sortRows(rows, LEASE_COLUMNS, { key: "nope", dir: "asc" }), rows);
});

test("CoreApi reads paths with GET and rechecks with an empty POST", async () => {
  const { api, calls } = fakeCore(() => ({ json: projection() }));
  await api.paths();
  await api.reconcilePaths();
  assert.deepEqual(calls.map((call) => [call.method, call.url, call.body]),
    [["GET", "/api/v1/paths", undefined], ["POST", "/api/v1/paths/reconcile", "{}"]]);
});

test("opening reads Core's evidence and notice once, with reads only", async () => {
  const { api, calls } = fakeCore((route) => (route.includes("identity") ? identity() : { json: projection() }));
  const session = new PathsSession(api, { now: () => new Date("2026-10-12T09:00:00Z") });
  assert.equal(session.readLabel(), "Not read yet.");
  assert.equal(await session.refresh(), true);
  assert.equal(posts(calls).length, 0);
  assert.deepEqual(calls.map((call) => call.url), ["/api/v1/runtime/identity", "/api/v1/paths", "/api/v1/runtime/identity"]);
  assert.equal(session.notice, NOTICE);
  assert.equal(session.leases.length, 1);
  assert.equal(session.events.length, 2);
  assert.equal(session.instanceId, "core-a");
  assert.match(session.readLabel(), /^Read at /);
  assert.deepEqual(session.messages(), []);
});

test("a failed read keeps the last rows and says they may be out of date", async () => {
  let fail = false;
  const { api } = fakeCore((route) => {
    if (route.includes("identity")) return identity();
    return fail ? new TypeError("Failed to fetch") : { json: projection() };
  });
  const session = new PathsSession(api);
  await session.refresh();
  fail = true;
  assert.equal(await session.refresh(), false);
  assert.equal(session.leases.length, 1, "rows are cleared only by a good read");
  assert.equal(session.stale, true);
  assert.match(session.readLabel(), /May be out of date/);
  assert.equal(session.problem.kind, "read");
  assert.equal(session.messages()[0].text, "Couldn't read path evidence: SORA's Core is not reachable.");
  fail = false;
  await session.refresh();
  assert.equal(session.stale, false);
  assert.equal(session.problem, null);
});

test("a malformed reply is a failed read, not an empty table", async () => {
  const { api } = fakeCore((route) => (route.includes("identity") ? identity() : { json: { ok: true } }));
  const session = new PathsSession(api);
  await session.refresh();
  assert.equal(session.everRead, false);
  assert.match(session.problem.text, /did not look like path evidence/);
});

test("a recheck is sent only from the confirmation, exactly once, and never retried", async () => {
  let answer = { json: projection() };
  const { api, calls } = fakeCore((route) => (route.includes("identity") ? identity()
    : route.startsWith("POST") ? answer : { json: projection() }));
  const session = new PathsSession(api);
  await session.refresh();
  assert.equal(await session.confirmRecheck(), "", "no confirmation, nothing sent");
  assert.equal(posts(calls).length, 0);
  assert.equal(session.askRecheck(), true);
  assert.equal(session.confirming, true);
  assert.equal(posts(calls).length, 0, "asking only shows the confirmation");
  assert.equal(session.cancelRecheck(), true);
  assert.equal(await session.confirmRecheck(), "");
  assert.equal(posts(calls).length, 0, "a cancelled confirmation sends nothing");

  session.askRecheck();
  answer = { status: 500, json: { error: { code: "INTERNAL_ERROR", message: "Internal server error" } } };
  assert.equal(await session.confirmRecheck(), "");
  assert.equal(await session.confirmRecheck(), "", "the confirmation is used up");
  assert.equal(posts(calls).length, 1);
  assert.deepEqual([posts(calls)[0].url, posts(calls)[0].body], ["/api/v1/paths/reconcile", "{}"]);
  await session.refresh();
  assert.equal(posts(calls).length, 1, "Refresh after a failed recheck only reads");
});

test("the recheck reply replaces both tables, and unchanged reservations are not an error", async () => {
  const after = projection([lease("run-1", "2026-10-12T08:51:01+00:00", { status: "uncertain" })],
    [event("e3", "write.release", "uncertain", "core_observed"), ...projection().events]);
  const { api } = fakeCore((route) => (route.includes("identity") ? identity()
    : route.startsWith("POST") ? { json: after } : { json: projection() }));
  const session = new PathsSession(api);
  await session.refresh();
  session.askRecheck();
  const summary = await session.confirmRecheck();
  assert.match(summary, /No reservation was released/);
  assert.equal(session.problem, null);
  assert.equal(session.events.length, 3);
  assert.equal(session.leases[0].status, "uncertain");

  const released = fakeCore((route) => (route.includes("identity") ? identity()
    : route.startsWith("POST") ? { json: projection([], []) } : { json: projection() }));
  const second = new PathsSession(released.api);
  await second.refresh();
  second.askRecheck();
  assert.equal(await second.confirmRecheck(), "Recheck finished. 1 project is no longer reserved.");
  assert.equal(second.leases.length, 0);
});

test("a recheck failure is worded apart from a read failure: refused or not confirmed", () => {
  const changed = recheckFailure(new CoreError("Core instance changed; resync before retrying",
    { status: 409, code: "RUNTIME_CHANGED" }));
  assert.equal(changed.refused, true);
  assert.match(changed.text, /^The recheck was refused: .*Nothing was rechecked\.$/);
  const shuttingDown = recheckFailure(new CoreError("Core is shutting down; no new effects are admitted",
    { status: 503, code: "RUNTIME_SHUTTING_DOWN" }));
  assert.equal(shuttingDown.refused, true, "a refusal is not an unknown outcome, even as a 503");
  for (const error of [new CoreError("SORA's Core is not reachable."),
    new CoreError("Internal server error", { status: 500, code: "INTERNAL_ERROR" }),
    new CoreError("Core is starting", { status: 503, code: "CORE_UNAVAILABLE" })]) {
    const failure = recheckFailure(error);
    assert.equal(failure.refused, false);
    assert.match(failure.text, /^The recheck wasn't confirmed: /);
    assert.match(failure.text, /won't retry by itself/);
  }
  assert.match(readFailure(new CoreError("Core returned 500.", { status: 500 })), /^Couldn't read path evidence: /);
  assert.doesNotMatch(readFailure(new CoreError("x")), /recheck/i);
  assert.match(readFailure(new CoreError("x", { status: 409, code: "RUNTIME_CHANGED" })), /restarted/);
});

test("a refused recheck leaves the rows current; an unconfirmed one marks them out of date", async () => {
  let answer;
  const { api } = fakeCore((route) => (route.includes("identity") ? identity()
    : route.startsWith("POST") ? answer : { json: projection() }));
  const session = new PathsSession(api);
  await session.refresh();
  answer = { status: 409, json: { error: { code: "RUNTIME_CHANGED", message: "Core instance changed" } } };
  session.askRecheck();
  await session.confirmRecheck();
  assert.equal(session.stale, false);
  assert.equal(session.problem.refused, true);
  answer = new TypeError("Failed to fetch");
  session.askRecheck();
  await session.confirmRecheck();
  assert.equal(session.stale, true);
  assert.equal(session.problem.kind, "recheck");
  assert.match(session.messages()[0].text, /^The recheck wasn't confirmed/);
});

test("an answer that spans a Core restart is set aside, for a read and for a recheck", async () => {
  let instance = 0;
  const { api } = fakeCore((route) => (route.includes("identity") ? identity(`core-${instance++}`)
    : { json: projection([], []) }));
  const session = new PathsSession(api);
  await session.refresh();
  assert.equal(session.everRead, false, "the read was not shown as current");
  assert.match(session.problem.text, /changed while reading/);

  const steady = fakeCore((route) => (route.includes("identity") ? identity() : { json: projection() }));
  const shown = new PathsSession(steady.api);
  await shown.refresh();
  shown.api = api;   // Core restarts between the confirmation and the reply
  shown.askRecheck();
  assert.equal(await shown.confirmRecheck(), "");
  assert.equal(shown.leases.length, 1, "the earlier rows stay");
  assert.equal(shown.stale, true);
  assert.match(shown.problem.text, /wasn't confirmed: SORA's Core changed while it ran/);
});

test("while the host can't use Core, Recheck is disabled with a reason and reads still go", async () => {
  const { api, calls } = fakeCore((route) => (route.includes("identity") ? identity() : { json: projection() }));
  const session = new PathsSession(api);
  await session.refresh();
  session.askRecheck();
  session.hostCore(false);
  assert.equal(session.confirming, false, "a confirmation does not outlive Core");
  assert.equal(session.recheckBlocked(), CORE_BLOCKED);
  assert.equal(session.askRecheck(), false);
  assert.equal(session.stale, true);
  assert.match(session.messages()[0].text, /out of date/);
  assert.equal(await session.refresh(), true, "reads may continue");
  assert.equal(posts(calls).length, 0);
  session.hostCore(true);
  assert.match(session.messages()[0].text, /^Core reconnected/);
  assert.equal(session.stale, true, "nothing is re-read by itself");
  session.hostCore("yes");
  assert.equal(session.canUseCore, true);

  const fresh = new PathsSession(api);
  fresh.hostCore(false);
  fresh.hostCore(true);
  assert.equal(fresh.messages()[0].text, "Core connected. Choose Refresh to read path evidence.");
  assert.equal(fresh.stale, false);
});

test("Quit waits only for a recheck in flight, and nothing overlaps it", async () => {
  let release;
  const { api, calls } = fakeCore((route) => {
    if (route.includes("identity")) return identity();
    if (route.startsWith("POST")) return new Promise((resolve) => { release = () => resolve({ json: projection() }); });
    return { json: projection() };
  });
  const seen = [];
  const session = new PathsSession(api, { onChange: (s) => seen.push(s.busy) });
  await session.refresh();
  assert.equal(seen.includes(true), false, "a read does not hold Quit");
  session.askRecheck();
  const running = session.confirmRecheck();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(session.busy, true);
  assert.equal(session.readLabel(), "Rechecking stopped writers…");
  assert.equal(await session.refresh(), false, "Refresh waits for the recheck");
  assert.equal(session.askRecheck(), false);
  release();
  await running;
  assert.equal(session.busy, false);
  assert.equal(posts(calls).length, 1);
  assert.equal(calls.filter((call) => call.url === "/api/v1/paths").length, 1);
});
