import assert from "node:assert/strict";
import { test } from "node:test";

import { blocks, spans, splitEvidence } from "../chat/chat-model.js";

test("Core's evidence footers become chips; SORA's words stay in the body", () => {
  const reply = "Spotify is paused.\n\nAutomatic window image: windows.PrintWindow, "
    + "2026-10-07T10:00:00; perception-1\n\nRead evidence:\n- window: Spotify\n- file: notes.txt";
  const { body, evidence } = splitEvidence(reply);
  assert.equal(body, "Spotify is paused.");
  assert.deepEqual(evidence.map((e) => [e.kind, e.label]),
    [["looked", "Looked at the window"], ["read", "Read 2 sources"]]);
  assert.deepEqual(evidence[1].items, ["window: Spotify", "file: notes.txt"]);
  assert.match(evidence[0].items[0], /^windows\.PrintWindow/);
});

test("the desktop overview and a closer look each get a chip", () => {
  const reply = "Your build failed.\n\nAutomatic desktop image: every monitor, scaled, "
    + "2026-10-08T10:00:00; overview-1\n\nCloser window image: windows.PrintWindow, "
    + "2026-10-08T10:00:01; perception-2";
  const { body, evidence } = splitEvidence(reply);
  assert.equal(body, "Your build failed.");
  assert.deepEqual(evidence.map((e) => [e.kind, e.label]),
    [["looked", "Looked at the desktop"], ["looked", "Looked closer at a window"]]);
  const failed = splitEvidence("I can't.\n\nCloser window image unavailable: stale reference");
  assert.deepEqual(failed.evidence.map((e) => e.label), ["Couldn't look closer"]);
});

test("a reply that only looks like evidence is never hidden", () => {
  assert.deepEqual(splitEvidence("Automatic window image: what is that?"),
    { body: "Automatic window image: what is that?", evidence: [] });
  const failed = splitEvidence("I can't see it.\n\nAutomatic window image unavailable: no window");
  assert.deepEqual(failed.evidence.map((e) => e.kind), ["looked-failed"]);
  assert.equal(splitEvidence("Plain reply.").evidence.length, 0);
});

test("inline formatting is limited to bold and code", () => {
  assert.deepEqual(spans("Use **Save** then `Reload`."), [
    { text: "Use " }, { text: "Save", bold: true }, { text: " then " },
    { text: "Reload", code: true }, { text: "." },
  ]);
  assert.deepEqual(spans("<b>not html</b>"), [{ text: "<b>not html</b>" }]);
});

test("paragraphs, lists, headings and code blocks", () => {
  const result = blocks("## Plan\nFirst line\nsecond line\n\n- one\n- **two**\n1. a\n2. b\n\n```\nx = 1\n```\nAfter");
  assert.deepEqual(result.map((b) => b.type), ["p", "p", "list", "list", "code", "p"]);
  assert.deepEqual(result[0].spans, [{ text: "Plan", bold: true }]);
  assert.equal(result[1].spans[0].text, "First line\nsecond line");
  assert.equal(result[2].ordered, false);
  assert.equal(result[2].items[1][0].bold, true);
  assert.equal(result[3].ordered, true);
  assert.equal(result[4].text, "x = 1");
  assert.deepEqual(blocks(""), []);
});

import {
  agentName, readEvents, replyFor, taskChip, turnOwnerMessage, voiceBadge,
} from "../chat/chat-model.js";

test("the event feed yields changed tasks and per-request memories", () => {
  const page = { next_sequence: 9, more_available: false, resync_required: false, events: [
    { event_type: "task.created", task_id: "task-1" },
    { event_type: "run.running", task_id: "task-1" },
    { event_type: "message.finalized", task_id: null },
    { event_type: "run.completed", task_id: "../bad" },
    { event_type: "memory.retrieved", payload: { dialogue_request_id: "panel-1",
      memories: [{ memory_id: "memory-a", entity_version: 1 }, { memory_id: "bad id" }] } },
  ] };
  const read = readEvents(page);
  assert.deepEqual(read.tasks, ["task-1"]);
  assert.deepEqual(read.memories, [{ requestId: "panel-1", memoryIds: ["memory-a"] }]);
  assert.equal(read.next, 9);
  assert.deepEqual(readEvents(null).tasks, []);
});

test("task chips use SORA's names for agents and Core's status", () => {
  assert.deepEqual(taskChip({ task_id: "t", status: "running", effective_backend: "codex" }),
    { id: "t", label: "Asked Cody · Working", tone: "active" });
  assert.equal(taskChip({ task_id: "t", status: "completed", requested_backend: "antigravity" }).tone, "ok");
  assert.equal(taskChip({ task_id: "t", status: "failed", requested_backend: "claude" }).label, "Asked Claude · Failed");
  assert.equal(agentName("custom_2"), "Agent 2");
});

test("replies are linked to the owner message and request they answer", () => {
  const messages = [
    { id: "u1", who: "user", text: "hi" }, { id: "s1", who: "sora", text: "hello" },
    { id: "c1", who: "core", text: "Cody finished." },
    { id: "u2", who: "user", text: "ask Cody" }, { id: "s2", who: "sora", text: "on it" },
  ];
  assert.equal(turnOwnerMessage(messages, 1), "u1");
  assert.equal(turnOwnerMessage(messages, 4), "u2");
  assert.equal(turnOwnerMessage(messages, 0), null);
  assert.deepEqual(replyFor(messages, 2, "ask Cody"), { userId: "u2", replyId: "s2" });
  assert.equal(replyFor(messages, 4, "ask Cody"), null);
});

test("the microphone shows Core's voice state", () => {
  assert.equal(voiceBadge(null).tone, "");
  assert.equal(voiceBadge({ state: "ready", running: true }).tone, "ready");
  // Always-on listening: an open microphone is expected, and the button switches it off.
  const listening = voiceBadge({ state: "speaking", running: true, microphone_open: true, listening: true });
  assert.equal(listening.tone, "listening");
  assert.match(listening.title, /click to stop listening/);
  assert.match(voiceBadge({ state: "listening", running: true, listening: true, hearing: true }).title,
    /^Hearing you/);
  assert.equal(voiceBadge({ state: "recording", running: true, microphone_open: true }).tone, "live");
  assert.equal(voiceBadge({ state: "ready", running: true, microphone_open: true }).tone, "live");
  assert.equal(voiceBadge({ state: "loading", running: true }).tone, "loading");
  assert.match(voiceBadge({ state: "error", message: "No microphone" }).title, /No microphone/);
  assert.equal(voiceBadge({ state: "stopped", running: false }).tone, "");
});

import { PressToTalk } from "../chat/chat-model.js";

test("hold to talk sends begin then end, or stop when the press is lost", async () => {
  const sent = [];
  let finishBegin;
  const talk = new PressToTalk((action) => {
    sent.push(action);
    return action === "begin" ? new Promise((resolve) => { finishBegin = resolve; }) : Promise.resolve();
  });
  const pressing = talk.press();
  const releasing = talk.letGo();          // released before "begin" finished
  assert.deepEqual(sent, ["begin"]);
  finishBegin();
  await pressing;
  await releasing;
  assert.deepEqual(sent, ["begin", "end"]);
  await talk.letGo();                      // a second release does nothing
  assert.deepEqual(sent, ["begin", "end"]);

  const lost = [];
  const other = new PressToTalk(async (action) => { lost.push(action); });
  await other.press();
  await other.letGo({ discard: true });
  assert.deepEqual(lost, ["begin", "stop"]);

  const failing = new PressToTalk(async (action) => { if (action === "begin") throw new Error("busy"); });
  await assert.rejects(failing.press(), /busy/);
  assert.equal(failing.held, false);
});
