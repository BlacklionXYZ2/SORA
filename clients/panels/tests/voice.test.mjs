import assert from "node:assert/strict";
import { test } from "node:test";

import { CoreApi } from "../shared/api.js";
import { send } from "../shared/bridge.js";
import {
  HoldToTalk, VoiceActionError, VoiceSession, actionOutcome, can, canHold, deviceInventory, deviceText,
  dialogueLine, errorText, holdOutcome, microphoneLine, parseCompanion, parseVoice,
} from "../voice/voice-model.js";

const voice = (overrides = {}) => ({
  state: "ready", message: "Hold to talk. Microphone is closed.", running: true, enabled: true,
  microphone_open: false, hearing: false, listening: false,
  devices: [{ key: "Windows WASAPI:Microphone (USB)", index: 3, input_channels: 1, output_channels: 0 }],
  ...overrides,
});

/** A fake Core behind CoreApi: records every call; each route can be replaced per test. */
function fakeCore(initial = {}) {
  const core = {
    status: voice(), instance: "core-1", reply: null, companion: { companion: {
      state: "idle", dialogue_ready: true, model_state: "ready", dialogue_model: "Offline test model" } },
    calls: [], routes: {}, ...initial,
  };
  const respond = (status, data) => ({ ok: status < 400, status, json: async () => data });
  const fetchImpl = async (url, init = {}) => {
    const method = init.method ?? "GET";
    const body = init.body === undefined ? undefined : JSON.parse(init.body);
    core.calls.push({ method, url, body });
    const route = core.routes[`${method} ${url}`];
    if (route) return route(body);
    if (url === "/api/v1/runtime/identity") return respond(200, { version: 1, instance_id: core.instance });
    if (url === "/api/v1/voice/local") return respond(200, method === "POST" ? core.reply ?? core.status : core.status);
    if (url === "/api/v1/projections/companion") return respond(200, core.companion);
    return respond(404, { error: { code: "NOT_FOUND", message: "Not found" } });
  };
  return { core, api: new CoreApi({ fetchImpl }), respond };
}

const posts = (core) => core.calls.filter((call) => call.method === "POST");

async function readySession(initial) {
  const { core, api, respond } = fakeCore(initial);
  const session = new VoiceSession(api);
  await session.readVoice();
  await session.readCompanion();
  return { core, api, session, respond };
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((ok, fail) => { resolve = ok; reject = fail; });
  return { promise, resolve, reject };
}

// ---------- strict status ----------

test("Core's voice status is read only when every field is within the classic window's bounds", () => {
  const parsed = parseVoice(voice());
  assert.equal(parsed.state, "ready");
  assert.equal(parsed.microphoneOpen, false);
  assert.deepEqual(parsed.devices, [{ key: "Windows WASAPI:Microphone (USB)", inputs: 1, outputs: 0, index: 3 }]);
  const bad = [
    voice({ state: "invented" }), voice({ message: "x".repeat(1001) }), voice({ running: "yes" }),
    voice({ devices: "none" }), voice({ devices: Array.from({ length: 129 }, (_, i) => ({ key: `k${i}`, input_channels: 1, output_channels: 0 })) }),
    voice({ devices: [{ key: "", input_channels: 1, output_channels: 0 }] }),
    voice({ devices: [{ key: "x".repeat(513), input_channels: 1, output_channels: 0 }] }),
    voice({ devices: [{ key: "mic\u0007bell", input_channels: 1, output_channels: 0 }] }),
    voice({ devices: [{ key: "mic", input_channels: -1, output_channels: 0 }] }),
    voice({ devices: [{ key: "mic", input_channels: 1, output_channels: 257 }] }),
    voice({ devices: [{ key: "mic", input_channels: 1.5, output_channels: 0 }] }),
    voice({ devices: [{ key: "mic", input_channels: 1, output_channels: 0, index: 4097 }] }),
    voice({ devices: [{ key: "mic", input_channels: 1, output_channels: 0, index: "2" }] }),
    voice({ devices: [{ key: "mic", input_channels: 1, output_channels: 0, index: null }] }),
    voice({ devices: [null] }), null, [], "ready",
  ];
  for (const data of bad) assert.throws(() => parseVoice(data), { name: "VoiceDataError" });
  assert.equal(parseVoice(voice({ message: "x".repeat(1000), devices: [] })).message.length, 1000);
});

test("a missing Settings switch needs the preflight's value, and an old Core's microphone is unknown, never closed", () => {
  const { enabled, ...withoutSwitch } = voice();
  assert.equal(enabled, true);
  assert.throws(() => parseVoice(withoutSwitch), /turned on in Settings/);
  assert.equal(parseVoice(withoutSwitch, false).enabled, false);
  const { microphone_open: _, ...oldCore } = voice();
  const parsed = parseVoice(oldCore);
  assert.equal(parsed.microphoneOpen, null);
  assert.match(microphoneLine(parsed, true).text, /UNKNOWN/);
  assert.equal(parseVoice(voice({ microphone_open: "open" })).microphoneOpen, null);
  assert.match(microphoneLine({ ...parsed, enabled: false }, true).text, /UNKNOWN/);
});

test("controls follow the classic enablement table, and Hold is off while always-on listening is on", () => {
  const at = (state, extra = {}) => parseVoice(voice({ state, ...extra }));
  assert.equal(can(at("stopped", { running: false }), "start"), true);
  assert.equal(can(at("error"), "start"), true);
  assert.equal(can(at("ready"), "start"), false);
  for (const state of ["ready", "recording", "transcribing", "thinking", "speaking"]) assert.equal(can(at(state), "begin"), true);
  for (const state of ["stopped", "loading", "listening", "error"]) assert.equal(can(at(state), "begin"), false);
  assert.equal(can(at("ready", { running: false }), "begin"), false);
  assert.equal(can(at("speaking"), "stop_output"), true);
  assert.equal(can(at("ready", { enabled: false }), "stop"), false);
  assert.equal(can(at("ready", { enabled: false }), "close"), true);
  assert.equal(can(null, "close"), true);
  assert.equal(can(at("ready"), "arbitrary"), false);
  assert.equal(canHold(at("speaking", { listening: true, microphone_open: true })), false);
  assert.equal(canHold(at("speaking")), true);
});

// ---------- status lines ----------

test("the microphone line has the classic five readings, with listening told apart from recording", () => {
  const status = (extra) => parseVoice(voice(extra));
  assert.equal(microphoneLine(status({ state: "recording", microphone_open: true }), true).text, "Microphone on · recording");
  assert.equal(microphoneLine(status({ state: "listening", microphone_open: true, listening: true }), true).text,
    "Microphone on · listening for her name");
  assert.equal(microphoneLine(status({ state: "speaking", microphone_open: true, listening: true }), true).tone, "listening");
  assert.equal(microphoneLine(status({}), true).text, "Microphone closed · as the voice worker reports");
  assert.equal(microphoneLine(status({ microphone_open: null }), true).text, "Microphone status UNKNOWN");
  assert.equal(microphoneLine(null, false).text, "Microphone status UNKNOWN");
  assert.equal(microphoneLine(status({ microphone_open: true }), false).text, "Microphone UNKNOWN · last reported open");
  assert.equal(microphoneLine(status({}), false).text, "Microphone status UNKNOWN");
});

test("the state line reads Core's state and message, or says voice is off in Settings", async () => {
  const { session } = await readySession();
  assert.deepEqual(session.statusLine().text, "Ready: Hold to talk. Microphone is closed.");
  const off = await readySession({ status: voice({ enabled: false, state: "stopped", running: false,
    message: "Voice stopped after settings/access changed.", microphone_open: null }) });
  const line = off.session.statusLine();
  assert.equal(line.kind, "disabled");
  assert.equal(line.text, "Voice is turned off in Settings.");
  assert.equal(line.message, "Voice stopped after settings/access changed.");
  assert.equal(new VoiceSession(fakeCore().api).statusLine().text, "Voice status has not been read yet.");
});

test("the dialogue model line uses only what Core reports, and says when it is not reported", () => {
  const companion = (fields) => parseCompanion({ companion: { state: "idle", dialogue_ready: true, model_state: "ready", ...fields } });
  assert.equal(dialogueLine(companion({ dialogue_model: "gemma-4.gguf" }), true).text, "Dialogue model: Ready to talk · gemma-4.gguf");
  assert.equal(dialogueLine(companion({}), true).text, "Dialogue model: Ready to talk · not reported by Core");
  assert.equal(dialogueLine(companion({ state: "thinking" }), true).label, "Thinking…");
  assert.equal(dialogueLine(companion({ state: "talking" }), true).label, "Speaking…");
  assert.equal(dialogueLine(companion({ dialogue_ready: false, model_state: "reloading" }), true).label, "Model reloading…");
  assert.equal(dialogueLine(companion({ dialogue_ready: false, model_state: "failed" }), true).label, "Model unavailable (see Settings)");
  const stale = dialogueLine(companion({ dialogue_model: "gemma-4.gguf" }), false);
  assert.equal(stale.text, "Dialogue model: Reconnecting… · gemma-4.gguf (last reported)");
  assert.equal(dialogueLine(null, null).text, "Dialogue model: not read yet");
  assert.match(dialogueLine(null, false).text, /not reported, because Core did not answer/);
  assert.throws(() => parseCompanion({}), { name: "VoiceDataError" });
  // Never the client-invented "Configured dialogue model" fallback.
  assert.doesNotMatch(dialogueLine(null, true).text, /Configured/);
});

test("devices are listed as last reported; a repeated key is flagged, never merged or chosen", () => {
  const status = parseVoice(voice({ devices: [
    { key: "MME:Speakers", index: 1, input_channels: 0, output_channels: 2 },
    { key: "MME:Speakers", index: 2, input_channels: 0, output_channels: 2 },
    { key: "WASAPI:Mic", input_channels: 1, output_channels: 0 },
  ] }));
  const inventory = deviceInventory(status, true);
  assert.equal(inventory.rows.length, 3);
  assert.deepEqual(inventory.rows.map((row) => row.ambiguous), [true, true, false]);
  assert.equal(inventory.ambiguous, true);
  assert.equal(inventory.stale, false);
  assert.equal(deviceText(inventory.rows[0]), "MME:Speakers · input 0 / output 2 · adapter index 1 · AMBIGUOUS KEY (not silently selected)");
  assert.equal(deviceText(inventory.rows[2]), "WASAPI:Mic · input 1 / output 0");
  assert.equal(deviceInventory(status, false).stale, true);
  assert.match(deviceInventory(null, false).empty, /Core has not reported one/);
  assert.match(deviceInventory(parseVoice(voice({ devices: [] })), true).empty, /Start voice to have the voice worker list/);
});

// ---------- hold to talk ----------

test("a release before Core confirms begin sends exactly one end, after begin", async () => {
  const sent = [];
  const begin = deferred();
  const hold = new HoldToTalk((action) => { sent.push(action); return action === "begin" ? begin.promise : Promise.resolve(); });
  const pressing = hold.press();
  assert.equal(hold.holding, true);
  const first = hold.letGo();
  const second = hold.letGo();
  assert.equal(hold.releasing, true);
  assert.equal(hold.pending, true);
  assert.deepEqual(sent, ["begin"]);
  begin.resolve();
  await Promise.all([pressing, first, second]);
  assert.deepEqual(sent, ["begin", "end"]);
  assert.equal(hold.pending, false);
  await hold.letGo();
  assert.deepEqual(sent, ["begin", "end"]);
});

test("losing focus before begin is confirmed discards the recording instead of sending it", async () => {
  const sent = [];
  const begin = deferred();
  const hold = new HoldToTalk((action) => { sent.push(action); return action === "begin" ? begin.promise : Promise.resolve(); });
  const pressing = hold.press();
  const losing = hold.letGo({ discard: true });
  begin.resolve();
  await Promise.all([pressing, losing]);
  assert.deepEqual(sent, ["begin", "stop"]);
});

test("an unconfirmed begin after the owner let go gets one safety stop, and begin is never replayed", async () => {
  const sent = [];
  const begin = deferred();
  const hold = new HoldToTalk((action) => { sent.push(action); return action === "begin" ? begin.promise : Promise.resolve(); });
  const pressing = hold.press();
  const releasing = hold.letGo();
  begin.reject(new VoiceActionError("No answer", { sent: true }));
  await assert.rejects(pressing, /No answer/);
  await releasing;
  assert.deepEqual(sent, ["begin", "stop"]);
  assert.equal(hold.safetyStop, "confirmed");
  assert.equal(hold.held, false);

  // A begin refused before it was sent changed nothing, so it needs no stop.
  const refused = [];
  const gate = deferred();
  const other = new HoldToTalk((action) => { refused.push(action); return gate.promise; });
  const press = other.press();
  const letGo = other.letGo();
  gate.reject(new VoiceActionError("Voice is turned off in Settings.", { sent: false }));
  await assert.rejects(press);
  await letGo;
  assert.deepEqual(refused, ["begin"]);
});

test("a begin that throws at once does not leave the hold latched or invent a release", async () => {
  const sent = [];
  const hold = new HoldToTalk((action) => { sent.push(action); throw new Error("Nothing sent"); });
  await assert.rejects(hold.press(), /Nothing sent/);
  assert.equal(hold.held, false);
  assert.equal(hold.pending, false);
  await hold.letGo();
  assert.deepEqual(sent, ["begin"]);
});

// ---------- actions against Core ----------

test("each action re-reads Core, then posts exactly {action} to the one voice route", async () => {
  for (const [action, state, running] of [["start", "stopped", false], ["stop_output", "speaking", true],
    ["stop", "thinking", true], ["close", "stopped", false]]) {
    const { core, session } = await readySession({ status: voice({ state, running }) });
    core.calls.length = 0;
    await session.perform(action);
    assert.deepEqual(core.calls.map((call) => `${call.method} ${call.url}`), [
      "GET /api/v1/voice/local", "GET /api/v1/runtime/identity", "POST /api/v1/voice/local", "GET /api/v1/runtime/identity",
    ], action);
    assert.deepEqual(posts(core)[0].body, { action });
    assert.equal(session.outcome.tone, "ok");
  }
  const { core, session } = await readySession();
  await assert.rejects(session.runAction("arbitrary"), TypeError);
  await assert.rejects(session.runAction("../sessions"), TypeError);
  assert.equal(core.calls.filter((call) => call.url !== "/api/v1/projections/companion").length, 1);
});

test("a state or Settings change seen in the preflight sends nothing, and close is still allowed", async () => {
  const { core, session } = await readySession();
  core.status = voice({ enabled: false });
  await session.perform("stop");
  assert.equal(posts(core).length, 0);
  assert.equal(session.outcome.text, "Stop voice response was not sent. Voice is turned off in Settings.");
  await session.perform("close");
  assert.deepEqual(posts(core).map((call) => call.body.action), ["close"]);

  // Close is the safety action: an unreadable or refused status does not block it.
  const { core: broken, session: other, respond } = await readySession();
  broken.routes["GET /api/v1/voice/local"] = () => respond(200, { state: "invented" });
  await other.perform("start");
  assert.equal(posts(broken).length, 0);
  assert.match(other.outcome.text, /^Start voice was not sent\. Core sent a voice status this page could not trust/);
  broken.routes["GET /api/v1/voice/local"] = () => respond(403, { error: { code: "FORBIDDEN", message: "Local audio is owner-local only" } });
  broken.reply = voice({ state: "stopped", running: false, message: "Local audio closed. The microphone is closed." });
  await other.perform("close");
  assert.deepEqual(posts(broken).map((call) => call.body.action), ["close"]);
  assert.equal(other.voice.state, "stopped");
});

test("an action in flight makes the status unconfirmed and blocks other actions, and a failure is never retried", async () => {
  const { core, session, respond } = await readySession();
  const reply = deferred();
  core.routes["POST /api/v1/voice/local"] = () => reply.promise;
  const starting = session.perform("stop_output");
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(session.busy, true);
  assert.equal(session.current, false);
  assert.match(microphoneLine(session.voice, session.current).text, /UNKNOWN/);
  assert.match(session.statusLine().text, /Waiting for Core to confirm/);
  const controls = session.controls();
  assert.deepEqual([controls.start, controls.hold, controls.stopOutput, controls.stop, controls.close],
    [false, false, false, false, false]);
  assert.equal(session.view().busy, true);
  await assert.rejects(session.runAction("stop"), { name: "VoiceActionError", sent: false });
  reply.resolve(respond(409, { error: { code: "LOCAL_VOICE_UNAVAILABLE", message: "" } }));
  await starting;
  assert.equal(posts(core).length, 1);
  assert.equal(session.outcome.text,
    "Stop speaking was not confirmed, and SORA will not retry it automatically. The voice worker did not answer in time.");
  assert.equal(session.busy, false);
  await session.readVoice();
  assert.equal(session.current, true);
  assert.equal(posts(core).length, 1);
});

test("a reply from a Core that changed after the request was sent is not shown as success", async () => {
  const { core, session } = await readySession({ status: voice({ state: "stopped", running: false }) });
  core.routes["POST /api/v1/voice/local"] = () => {
    core.instance = "core-2";
    return { ok: true, status: 200, json: async () => voice({ state: "loading" }) };
  };
  await session.perform("start");
  assert.equal(session.outcome.text,
    "Start voice was not confirmed, and SORA will not retry it automatically. Core changed after the request was sent.");
  assert.equal(session.current, false);
});

test("a hold is pinned to the Core it began on: a restarted Core gets nothing", async () => {
  const { core, session } = await readySession();
  await session.pressHold();
  assert.equal(session.hold.held, true);
  assert.equal(session.holdInstance, "core-1");
  core.instance = "core-2";
  await session.releaseHold();
  assert.deepEqual(posts(core).map((call) => call.body.action), ["begin"]);
  assert.match(session.outcome.text, /^Your release was not sent, so the microphone status may be unknown\./);
  assert.match(session.outcome.text, /restarted after you pressed Hold to talk/);
});

test("hold to talk through Core: begin, then end with a sent outcome, or stop with the discard reason", async () => {
  const { core, session } = await readySession();
  core.reply = voice({ state: "recording", microphone_open: true, message: "Recording only while held; release to send speech." });
  await session.pressHold();
  assert.equal(session.controls().holdLabel, "Release to send");
  assert.equal(session.view().microphone.text, "Microphone on · recording");
  assert.equal(session.view().busy, true);
  core.reply = voice({ state: "transcribing", message: "Transcribing locally. Microphone is closed." });
  await session.releaseHold();
  assert.deepEqual(posts(core).map((call) => call.body.action), ["begin", "end"]);
  assert.equal(session.outcome.text, "Recording sent. The status above shows what she is doing with it.");
  assert.equal(session.view().busy, false);

  core.reply = voice({ state: "recording", microphone_open: true });
  await session.pressHold();
  core.reply = voice();
  await session.releaseHold({ discard: true, reason: "the window lost focus" });
  assert.deepEqual(posts(core).map((call) => call.body.action), ["begin", "end", "begin", "stop"]);
  assert.equal(session.outcome.text, "Recording discarded because the window lost focus. Nothing was sent.");
});

test("Stop voice response while holding only discards the hold, and Close discards it first", async () => {
  const { core, session } = await readySession();
  core.reply = voice({ state: "recording", microphone_open: true });
  await session.pressHold();
  core.reply = voice();
  await session.perform("stop");
  assert.deepEqual(posts(core).map((call) => call.body.action), ["begin", "stop"]);
  assert.match(session.outcome.text, /you pressed Stop voice response/);
  core.reply = voice({ state: "recording", microphone_open: true });
  await session.pressHold();
  core.reply = voice({ state: "stopped", running: false });
  await session.perform("close");
  assert.deepEqual(posts(core).map((call) => call.body.action), ["begin", "stop", "begin", "stop", "close"]);
  assert.match(session.outcome.text, /^Core confirmed Close audio worker\./);
});

test("the hold button stays enabled while held, whatever the status says meanwhile", async () => {
  const { core, session } = await readySession();
  core.reply = voice({ state: "recording", microphone_open: true });
  await session.pressHold();
  core.status = voice({ state: "loading", running: true });
  await session.readVoice();
  session.setCanUseCore(false);
  assert.equal(session.controls().hold, true);
  assert.equal(session.controls().holdState, "held");
  session.setCanUseCore(true);
  core.reply = voice({ state: "loading", running: true });
  await session.releaseHold();
  assert.deepEqual(posts(core).map((call) => call.body.action), ["begin", "end"]);
  assert.equal(session.controls().hold, false);
  assert.equal(session.controls().holdHint, "Wait until voice is ready.");
});

test("a definite refusal from Core is reported as refused, and a refused begin needs no safety stop", async () => {
  const { core, session, respond } = await readySession();
  const forbidden = () => respond(403, { error: { code: "FORBIDDEN", message: "Local audio is owner-local only" } });
  core.routes["POST /api/v1/voice/local"] = forbidden;
  await session.perform("close");
  assert.equal(session.outcome.text, "Core refused Close audio worker. Local audio is owner-local only");
  assert.equal(session.statusLine().text, "The last voice action was refused by Core. Local audio is owner-local only");
  await session.readVoice();
  const gate = deferred();
  core.routes["POST /api/v1/voice/local"] = () => gate.promise;
  const pressing = session.pressHold();
  await new Promise((resolve) => setImmediate(resolve));
  const releasing = session.releaseHold();
  assert.equal(session.controls().holdLabel, "Releasing…");
  gate.resolve(forbidden());
  await Promise.all([pressing, releasing]);
  assert.deepEqual(posts(core).map((call) => call.body.action), ["close", "begin"]);
  assert.equal(session.outcome.text, "The recording did not start: Core refused it. Local audio is owner-local only");
});

test("a begin Core does not confirm leaves an honest outcome that points to Close audio worker", async () => {
  const { core, session, respond } = await readySession();
  core.routes["POST /api/v1/voice/local"] = () => respond(409, { error: { code: "LOCAL_VOICE_UNAVAILABLE",
    message: "Listening is always on: just speak, and say her name to start." } });
  await session.pressHold();
  assert.equal(session.hold.held, false);
  assert.match(session.outcome.text, /^The recording was not confirmed\. If the microphone status stays unknown, use Close audio worker\./);
  assert.match(session.outcome.text, /Listening is always on/);
});

// ---------- reads ----------

test("a slow read that started before an action never overwrites the action's newer reply", async () => {
  const { core, session, respond } = await readySession({ status: voice({ state: "stopped", running: false }) });
  const slow = deferred();
  core.routes["GET /api/v1/voice/local"] = () => slow.promise;
  const reading = session.readVoice();
  delete core.routes["GET /api/v1/voice/local"];
  core.reply = voice({ state: "loading", message: "Loading local speech runtime; microphone closed." });
  await session.perform("start");
  slow.resolve(respond(200, voice({ state: "stopped", running: false })));
  await reading;
  assert.equal(session.voice.state, "loading");
  assert.match(session.outcome.text, /loading the speech models/);
});

test("a failed read keeps the last report, marked stale, and never claims the microphone closed", async () => {
  const { core, session, respond } = await readySession({ status: voice({ state: "recording", microphone_open: true }) });
  core.routes["GET /api/v1/voice/local"] = () => { throw new TypeError("Failed to fetch"); };
  await session.readVoice();
  const view = session.view();
  assert.equal(view.microphone.text, "Microphone UNKNOWN · last reported open");
  assert.match(view.status.text, /could not be read, so what you see is the last report/);
  assert.equal(view.devices.stale, true);
  assert.equal(view.devices.rows.length, 1);
  assert.match(view.banner, /not reachable/);
  core.routes["GET /api/v1/voice/local"] = () => respond(200, { ...voice(), state: "dancing" });
  await session.readVoice();
  assert.match(session.statusLine().text, /could not trust \(its state is not one SORA knows\), so it is not shown/);
  assert.equal(session.voice.state, "recording"); // the invalid status is not rendered
  core.routes["GET /api/v1/voice/local"] = () => respond(409, { error: { code: "RUNTIME_CHANGED", message: "Core changed" } });
  await session.readVoice();
  assert.equal(session.voice, null);
  assert.equal(session.statusLine().text, "SORA's Core changed, so the voice status must be read again.");
});

test("while the host pauses Core for panels, every action is off and refused without sending", async () => {
  const { core, session } = await readySession();
  session.setCanUseCore(false);
  const controls = session.controls();
  assert.deepEqual([controls.start, controls.hold, controls.stopOutput, controls.stop, controls.close],
    [false, false, false, false, false]);
  assert.match(session.view().banner, /starting or stopping Core/);
  assert.match(session.view().microphone.text, /UNKNOWN/);
  await session.perform("close");
  assert.equal(posts(core).length, 0);
  assert.equal(session.outcome.text, "Close audio worker was not sent. SORA has paused panel access to Core.");
});

test("always-on listening switches Hold off with a reason, and offers Stop and Close instead", async () => {
  const { session } = await readySession({ status: voice({ state: "listening", listening: true, microphone_open: true,
    message: "Listening. Say \"Sora\" to talk to her." }) });
  const controls = session.controls();
  assert.equal(controls.hold, false);
  assert.equal(controls.holdState, "listening");
  assert.equal(controls.holdLabel, "Listening");
  assert.equal(controls.holdHint, "Always-on listening is on: just say her name.");
  assert.equal(controls.stop, true);
  assert.equal(controls.close, true);
  assert.equal(session.statusLine().listening, true);
});

test("the companion read is fenced too, and a failure keeps the last model as last reported", async () => {
  const { core, session, respond } = await readySession();
  const slow = deferred();
  core.routes["GET /api/v1/projections/companion"] = () => slow.promise;
  const old = session.readCompanion();
  core.routes["GET /api/v1/projections/companion"] = () => { throw new TypeError("Failed to fetch"); };
  await session.readCompanion();
  slow.resolve(respond(200, { companion: { state: "idle", dialogue_ready: true, dialogue_model: "old.gguf" } }));
  await old;
  assert.equal(session.view().dialogue.text, "Dialogue model: Reconnecting… · Offline test model (last reported)");
});

// ---------- copy and host messages ----------

test("outcome wording keeps 'not sent' and 'not confirmed' apart", () => {
  assert.equal(actionOutcome("close", new VoiceActionError("SORA's Core is not reachable.", { sent: false })).text,
    "Close audio worker was not sent. SORA's Core is not reachable.");
  assert.match(actionOutcome("start", new VoiceActionError("x", { sent: true })).text, /not confirmed, and SORA will not retry/);
  assert.match(holdOutcome("begin-failed", { error: new VoiceActionError("x", { sent: false }) }).text, /did not start, and nothing was sent/);
  assert.match(holdOutcome("begin-failed", { error: new VoiceActionError("x", { sent: true }), safetyStop: "failed" }).text,
    /a stop was sent, but it was not confirmed either/);
  assert.equal(errorText(Object.assign(new Error("boom"))), "boom");
});

test("the page tells the host when Quit must wait, and opens Settings on Audio", () => {
  assert.deepEqual(send("panel.busy", { busy: true }), { type: "panel.busy", busy: true });
  assert.throws(() => send("panel.busy", { busy: "yes" }), TypeError);
  assert.deepEqual(send("panel.open", { panel: "settings", select: "Audio" }),
    { type: "panel.open", panel: "settings", select: "Audio" });
});
