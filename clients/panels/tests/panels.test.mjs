import assert from "node:assert/strict";
import { test } from "node:test";

import { CoreApi, CoreError } from "../shared/api.js";
import { HOST_MESSAGES, OPENABLE_PANELS, hosted, send } from "../shared/bridge.js";
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

test("icons are known, static SVG", () => {
  for (const name of ICON_NAMES) assert.match(icon(name), /^<svg class="icon"/);
  assert.match(icon("close", "Close"), /aria-label="Close"/);
  assert.throws(() => icon("nope"), TypeError);
});
