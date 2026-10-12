import assert from "node:assert/strict";
import { test } from "node:test";

import { CoreApi, CoreError, itemPath } from "../shared/api.js";
import {
  HOST_MESSAGES, OPENABLE_PANELS, hostRequest, hosted, send, validAppearance,
} from "../shared/bridge.js";
import { ICON_NAMES, icon } from "../shared/icons.js";
import {
  canSend, isSendKey, newRequestId, normaliseMessages, sameMessages, speaker, viewRows,
} from "../chat/chat-model.js";

const raw = [
  { message_id: "m1", role: "user", content: "Hi", created_at: "2026-10-06T10:14:00Z", provenance: "owner" },
  { message_id: "m2", role: "assistant", content: "Hello!", created_at: "2026-10-06T10:14:02Z", provenance: "model" },
  { message_id: "m3", role: "status", content: "Claude finished the review.", created_at: "2026-10-06T10:20:00Z" },
  { message_id: 7, role: "assistant", content: "bad id" },
];

test("messages are normalised and attributed to owner, SORA or Core", () => {
  const messages = normaliseMessages(raw);
  assert.deepEqual(messages.map((m) => [m.id, m.who]), [["m1", "user"], ["m2", "sora"], ["m3", "core"]]);
  assert.equal(speaker({ role: "alert" }), "core");
  assert.deepEqual(normaliseMessages(null), []);
});

test("a pending turn shows until Core records the owner's message", () => {
  const messages = normaliseMessages(raw.slice(0, 2));
  const pending = { requestId: "r1", text: "Plan a trip", knownCount: 2, state: "thinking", at: null };
  let rows = viewRows(messages, pending);
  assert.deepEqual(rows.slice(-2).map((r) => [r.who, Boolean(r.pending), Boolean(r.thinking)]),
    [["user", true, false], ["sora", false, true]]);
  const recorded = [...messages, { id: "m9", who: "user", text: "Plan a trip" }];
  rows = viewRows(recorded, pending);
  assert.equal(rows.filter((r) => r.pending).length, 0);
  // An identical older message does not hide the new pending one.
  const older = [{ id: "m0", who: "user", text: "Plan a trip" }, ...messages];
  assert.equal(viewRows(older, { ...pending, knownCount: 3 }).filter((r) => r.pending).length, 1);
});

test("sameMessages detects edits and additions", () => {
  const a = normaliseMessages(raw);
  assert.ok(sameMessages(a, normaliseMessages(raw)));
  assert.ok(!sameMessages(a, a.slice(1)));
  assert.ok(!sameMessages(a, a.map((m, i) => (i === 0 ? { ...m, text: "changed" } : m))));
});

test("Enter sends, Shift+Enter and IME composition do not", () => {
  assert.ok(isSendKey({ key: "Enter", shiftKey: false, isComposing: false }));
  assert.ok(!isSendKey({ key: "Enter", shiftKey: true, isComposing: false }));
  assert.ok(!isSendKey({ key: "Enter", shiftKey: false, isComposing: true }));
  assert.ok(!isSendKey({ key: "Enter", shiftKey: false, isComposing: false, keyCode: 229 }));
});

test("sending needs Core, an idle turn and a real draft", () => {
  assert.ok(canSend("hi", { connected: true, busy: false }));
  assert.ok(!canSend("   ", { connected: true, busy: false }));
  assert.ok(!canSend("hi", { connected: false, busy: false }));
  assert.ok(!canSend("hi", { connected: true, busy: true }));
  assert.ok(!canSend("x".repeat(16_001), { connected: true, busy: false }));
});

test("request IDs match Core's pattern", () => {
  const id = newRequestId();
  assert.match(id, /^[A-Za-z0-9_-]{1,128}$/);
  assert.notEqual(id, newRequestId());
  assert.match(newRequestId(null), /^panel-/);
});

test("CoreApi calls same-origin /api/v1 only, without any token", async () => {
  const calls = [];
  const api = new CoreApi({
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return { ok: true, status: 200, json: async () => ({ response: "ok" }) };
    },
  });
  await api.dialogue("hello", "r1");
  assert.equal(calls[0].url, "/api/v1/dialogue");
  assert.equal(calls[0].init.method, "POST");
  assert.equal(JSON.parse(calls[0].init.body).request_id, "r1");
  assert.ok(!("Authorization" in calls[0].init.headers));
  await assert.rejects(api.request("https://example.com/x"), TypeError);
  await assert.rejects(api.request("/admin"), TypeError);
});

test("CoreApi separates 'Core unreachable' from 'Core refused'", async () => {
  const down = new CoreApi({ fetchImpl: async () => { throw new TypeError("Failed to fetch"); } });
  const error = await down.messages().catch((e) => e);
  assert.ok(error instanceof CoreError && error.unavailable);
  const refused = new CoreApi({ fetchImpl: async () => ({ ok: false, status: 409,
    json: async () => ({ error: { message: "Use a new request ID", code: "DIALOGUE_REQUEST_CONFLICT" } }) }) });
  const conflict = await refused.dialogue("x", "r1").catch((e) => e);
  assert.equal(conflict.code, "DIALOGUE_REQUEST_CONFLICT");
  assert.equal(conflict.message, "Use a new request ID");
  assert.ok(!conflict.unavailable);
  const proxyDown = new CoreApi({ fetchImpl: async () => ({ ok: false, status: 503, json: async () => ({}) }) });
  assert.ok((await proxyDown.status().catch((e) => e)).unavailable);
});

test("bridge only sends known messages and panels", () => {
  assert.equal(hosted, false);
  assert.deepEqual(send("window.hide"), { type: "window.hide" });
  assert.deepEqual(send("panel.open", { panel: "voice" }), { type: "panel.open", panel: "voice" });
  assert.throws(() => send("shell.exec"), TypeError);
  assert.throws(() => send("panel.open", { panel: "C:/Windows" }), TypeError);
  assert.ok(HOST_MESSAGES.includes("window.drag") && OPENABLE_PANELS.includes("settings"));
});

test("IDs go into Core paths unchanged, and only exact IDs do", async () => {
  assert.equal(itemPath("memory-1:2"), "memory-1:2");
  for (const bad of ["", "../x", "a..b", "a/b", "a b", "-x", 5, null]) assert.throws(() => itemPath(bad), TypeError);
  const calls = [];
  const api = new CoreApi({ fetchImpl: async (url, init) => {
    calls.push([url, init.method, init.body && JSON.parse(init.body)]);
    return { ok: true, status: 200, json: async () => ({}) };
  } });
  await api.memory("memory-a:b");
  await api.forgetMemory("memory-a", { request_id: "r" });
  await api.openReference("content-1");
  await api.memories({ q: "teal & blue", state: "all", project: "global", scope: "dialogue", cursor: "abc_1" });
  assert.deepEqual(calls.map((call) => call.slice(0, 2)), [
    ["/api/v1/memories/memory-a:b", "GET"], ["/api/v1/memories/memory-a/forget", "POST"],
    ["/api/v1/content/navigate", "POST"],
    ["/api/v1/memories?limit=50&state=all&project=global&q=teal%20%26%20blue&scope=dialogue&cursor=abc_1", "GET"],
  ]);
  assert.deepEqual(calls[2][2], { utterance: "open this referenced content", verb: "open",
    explicit_reference_id: "content-1" });
  // A bad ID is a rejected promise, never a request.
  await assert.rejects(api.task("../status"), TypeError);
  assert.equal(calls.length, 4);
});

test("the bridge carries busy reports, appearance saves and memory highlights, checked", async () => {
  const values = { theme: "Dark", textScale: 110, shortcut: "CtrlAltSpace", chatCompact: false,
    chatPinned: true, showTechnicalDetail: false, reducedMotion: true };
  assert.deepEqual(send("panel.busy", { busy: true }), { type: "panel.busy", busy: true });
  assert.throws(() => send("panel.busy", { busy: "yes" }), TypeError);
  assert.ok(validAppearance(values));
  for (const bad of [{ ...values, theme: "Light" }, { ...values, textScale: 200 }, { ...values, extra: 1 },
    { ...values, chatPinned: 1 }, null]) assert.equal(validAppearance(bad), false);
  assert.throws(() => send("prefs.save", { requestId: "r1", values, baseline: { ...values, shortcut: "F1" } }), TypeError);
  assert.throws(() => send("placement.reset", {}), TypeError);
  // Outside SoraShell a host request is refused honestly rather than left hanging.
  const result = await hostRequest("prefs.save", { values, baseline: values });
  assert.equal(result.ok, false);
  assert.match(result.error, /SORA's app/);
  const id = "0f8fad5b-d9cb-469f-a165-70867728950e";
  const anchor = { x: 10, y: 20, width: 300, height: 120 };
  assert.deepEqual(send("memory.presented", { requestId: id, status: "selected", anchor }),
    { type: "memory.presented", requestId: id, status: "selected", anchor });
  assert.ok(send("memory.presented", { requestId: id, status: "unavailable" }));
  assert.throws(() => send("memory.presented", { requestId: id, status: "selected" }), TypeError);
  assert.throws(() => send("memory.presented", { requestId: id, status: "unavailable", anchor }), TypeError);
  assert.throws(() => send("memory.presented", { requestId: "r1", status: "unavailable" }), TypeError);
  assert.ok(HOST_MESSAGES.includes("memory.highlight-cleared"));
});

test("icons are known, static SVG", () => {
  for (const name of ICON_NAMES) assert.match(icon(name), /^<svg class="icon"/);
  assert.match(icon("close", "Close"), /aria-label="Close"/);
  assert.throws(() => icon("nope"), TypeError);
});
