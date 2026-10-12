import { CoreApi, CoreError } from "../shared/api.js";
import { hosted, pickFile, send as sendToHost } from "../shared/bridge.js";
import { agentNamesKnown, learnAgentNames } from "../shared/tasks.js";
import { icon } from "../shared/icons.js";
import { setUpWindow } from "../shared/window.js";
import {
  blocks, canSend, formatTime, isSendKey, newRequestId, normaliseMessages, readEvents, replyFor,
  PressToTalk, sameMessages, splitEvidence, taskChip, turnOwnerMessage, viewRows, voiceBadge,
} from "./chat-model.js";

const POLL_MS = 2500;
const api = new CoreApi();
const els = {
  transcript: document.getElementById("transcript"),
  composer: document.getElementById("composer"),
  draft: document.getElementById("draft"),
  send: document.getElementById("send"),
  voice: document.getElementById("voice"),
  offline: document.getElementById("offline"),
  jump: document.getElementById("jump"),
  attach: document.getElementById("attach"),
  attachments: document.getElementById("attachments"),
};
const MAX_ATTACHMENTS = 3;
const state = { messages: [], pending: null, connected: false, loaded: false, attempted: false,
  error: "", attachments: [],
  sequence: 0,            // event feed position
  tasks: new Map(),       // task_id -> Core's task record
  used: new Map(),        // dialogue request id -> Set of memory ids
  links: loadLinks(),     // dialogue request id -> { userId, replyId }
};

// Which reply answered which request sent from this window. Kept in this browser profile only,
// so memory chips stay attached after the window reloads.
function loadLinks() {
  try {
    return new Map(JSON.parse(localStorage.getItem("sora.chat.links") ?? "[]"));
  } catch {
    return new Map();
  }
}

function saveLinks() {
  try {
    localStorage.setItem("sora.chat.links", JSON.stringify([...state.links].slice(-200)));
  } catch { /* storage unavailable: chips still show for this session */ }
}
let pollTimer = 0;
let toastTimer = 0;

setUpWindow();
els.voice.innerHTML = icon("mic", "Voice");
els.attach.innerHTML = icon("attach", "Attach a file");
renderSendButton();

// ---------- rendering ----------

function nearBottom() {
  const t = els.transcript;
  return t.scrollHeight - t.scrollTop - t.clientHeight < 48;
}

function scrollToEnd() {
  els.transcript.scrollTop = els.transcript.scrollHeight;
  els.jump.hidden = true;
}

function messageItem(row, index, rows) {
  const item = document.createElement("li");
  item.className = `message ${row.who}${row.pending ? " pending" : ""}`;
  item.dataset.id = row.id;
  const body = document.createElement("div");
  if (row.who !== "core") {
    const avatar = document.createElement("span");
    avatar.className = row.who === "sora" ? "avatar sora" : "avatar";
    avatar.textContent = row.who === "sora" ? "S" : "U";
    avatar.setAttribute("aria-hidden", "true");
    item.append(avatar);
    const meta = document.createElement("div");
    meta.className = "meta";
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = row.who === "sora" ? "SORA" : "You";
    const time = document.createElement("span");
    time.className = "time";
    time.textContent = row.pending ? "sending…" : formatTime(row.at);
    meta.append(name, time);
    body.append(meta);
  }
  if (row.thinking) {
    const dots = document.createElement("span");
    dots.className = "thinking";
    dots.setAttribute("aria-label", "SORA is thinking");
    dots.append(document.createElement("i"), document.createElement("i"), document.createElement("i"));
    body.append(dots);
  } else if (row.who === "sora") {
    const { body: said, evidence } = splitEvidence(row.text);
    body.append(richText(said));
    const activity = turnActivity(row, index, rows);
    if (evidence.length || activity.length) body.append(evidenceChips(evidence, activity));
  } else {
    const text = document.createElement("div");
    text.className = "text";
    text.textContent = row.text;
    body.append(text);
  }
  item.append(body);
  return item;
}

// SORA's words with a small, safe subset of formatting. Text nodes only: nothing in a message
// is ever interpreted as HTML.
function richText(text) {
  const box = document.createElement("div");
  box.className = "text rich";
  const inline = (parent, parts) => {
    for (const part of parts) {
      const node = document.createElement(part.code ? "code" : part.bold ? "strong" : "span");
      node.textContent = part.text;
      parent.append(node);
    }
  };
  for (const block of blocks(text)) {
    if (block.type === "code") {
      const pre = document.createElement("pre");
      pre.textContent = block.text;
      box.append(pre);
    } else if (block.type === "list") {
      const list = document.createElement(block.ordered ? "ol" : "ul");
      for (const item of block.items) {
        const li = document.createElement("li");
        inline(li, item);
        list.append(li);
      }
      box.append(list);
    } else {
      const p = document.createElement("p");
      inline(p, block.spans);
      box.append(p);
    }
  }
  return box;
}

const EVIDENCE_ICON = { read: "file", looked: "eye", "looked-failed": "alert", context: "eye" };

// Tasks this turn started (by the owner message that created them) and memories it used (by
// the request this window sent). Both come from Core's records, never from the reply's text.
function turnActivity(row, index, rows) {
  const chips = [];
  const owner = turnOwnerMessage(rows, index);
  for (const task of state.tasks.values()) {
    if (owner && task.creator_message_id === owner) {
      const chip = taskChip(task);
      chips.push({ kind: `task ${chip.tone}`, label: chip.label, icon: "task",
        open: () => { sendToHost("panel.open", { panel: "activity", select: task.task_id });
          if (!hosted) toast("Activity opens in SORA's app."); } });
    }
  }
  for (const [requestId, link] of state.links) {
    const ids = state.used.get(requestId);
    if (link.replyId === row.id && ids?.size) {
      chips.push({ kind: "memory", label: `Used ${ids.size} memor${ids.size === 1 ? "y" : "ies"}`,
        icon: "memory", items: [...ids], memory: true });
    }
  }
  return chips;
}

async function memoryLines(ids, list) {
  list.replaceChildren(...ids.map((id) => {
    const li = document.createElement("li");
    li.textContent = "Loading…";
    return li;
  }));
  await Promise.all(ids.map(async (id, at) => {
    const li = list.children[at];
    try {
      const memory = await api.memory(id);
      li.textContent = String(memory?.preview ?? memory?.content ?? memory?.memory?.content ?? id);
      // Opens Memory on this exact record.
      const show = document.createElement("button");
      show.type = "button";
      show.className = "link";
      show.textContent = "Show";
      show.title = "Show this memory in Memory";
      show.addEventListener("click", () => {
        sendToHost("panel.open", { panel: "memory", select: id });
        if (!hosted) toast("Memory opens in SORA's app.");
      });
      li.append(" ", show);
    } catch {
      li.textContent = "No longer available (corrected or forgotten).";
    }
  }));
  const open = document.createElement("li");
  const link = document.createElement("button");
  link.type = "button";
  link.className = "link";
  link.textContent = "Open Memory";
  link.addEventListener("click", () => {
    sendToHost("panel.open", { panel: "memory" });
    if (!hosted) toast("Memory opens in SORA's app.");
  });
  open.append(link);
  list.append(open);
}

// Core's own records of what happened, as chips that open to show the detail.
function evidenceChips(evidence, activity = []) {
  const row = document.createElement("div");
  row.className = "evidence";
  for (const item of activity) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip evidence-chip " + item.kind;
    chip.innerHTML = icon(item.icon) + "<span></span>" + icon(item.memory ? "chevron" : "panel");
    chip.querySelector("span").textContent = item.label;
    row.append(chip);
    if (!item.memory) {
      chip.title = "Open Activity";
      chip.addEventListener("click", item.open);
      continue;
    }
    chip.setAttribute("aria-expanded", "false");
    const detail = document.createElement("ul");
    detail.className = "evidence-detail selectable";
    detail.hidden = true;
    let loaded = false;
    chip.addEventListener("click", () => {
      detail.hidden = !detail.hidden;
      chip.setAttribute("aria-expanded", String(!detail.hidden));
      if (!loaded) { loaded = true; memoryLines(item.items, detail); }
      if (!detail.hidden) detail.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
    row.append(detail);
  }
  for (const item of evidence) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip evidence-chip " + item.kind;
    chip.setAttribute("aria-expanded", "false");
    chip.innerHTML = icon(EVIDENCE_ICON[item.kind] ?? "file") + "<span></span>" + icon("chevron");
    chip.querySelector("span").textContent = item.label;
    const detail = document.createElement("ul");
    detail.className = "evidence-detail selectable";
    detail.hidden = true;
    for (const line of item.items) {
      const li = document.createElement("li");
      li.textContent = line;
      detail.append(li);
    }
    chip.addEventListener("click", () => {
      detail.hidden = !detail.hidden;
      chip.setAttribute("aria-expanded", String(!detail.hidden));
      if (!detail.hidden) detail.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
    row.append(chip, detail);
  }
  return row;
}

function fileLabel(path) {
  const parts = path.split(/[\\/]/);
  return parts[parts.length - 1] || path;
}

function renderAttachments() {
  els.attachments.hidden = state.attachments.length === 0;
  els.attachments.replaceChildren(...state.attachments.map((path, index) => {
    const chip = document.createElement("span");
    chip.className = "chip attachment";
    chip.title = path;
    chip.innerHTML = icon("file") + "<span></span>";
    chip.querySelector("span").textContent = fileLabel(path);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "remove";
    remove.title = "Remove";
    remove.innerHTML = icon("close", "Remove");
    remove.addEventListener("click", () => {
      state.attachments.splice(index, 1);
      renderAttachments();
    });
    chip.append(remove);
    return chip;
  }));
  els.attach.disabled = state.attachments.length >= MAX_ATTACHMENTS;
}

function renderTranscript({ forceScroll = false } = {}) {
  const stick = forceScroll || nearBottom();
  const rows = viewRows(state.messages, state.pending);
  els.transcript.replaceChildren(...rows.map((row, index) => messageItem(row, index, rows)));
  if (!rows.length && state.loaded) {
    const empty = document.createElement("li");
    empty.className = "empty";
    empty.textContent = "Say hello. SORA's replies and anything her agents report will appear here.";
    els.transcript.append(empty);
  }
  if (stick) scrollToEnd();
  else if (rows.length) els.jump.hidden = false;
}

function renderSendButton() {
  const busy = Boolean(state.pending);
  els.send.innerHTML = icon(busy ? "stop" : "send", busy ? "Stop" : "Send");
  els.send.title = busy ? "Stop SORA's reply" : "Send";
  els.send.classList.toggle("stop", busy);
  els.send.classList.toggle("send", !busy);
  els.send.disabled = busy ? false
    : !canSend(els.draft.value, { connected: state.connected, busy });
}

function renderConnection() {
  els.offline.hidden = state.connected || !state.attempted;
  if (!state.connected) {
    els.offline.replaceChildren();
    els.offline.insertAdjacentHTML("afterbegin", icon("alert"));
    els.offline.append(document.createTextNode(
      state.error || "SORA's Core is not reachable. Your draft is kept; retrying…"));
  }
  renderSendButton();
}

function toast(text) {
  document.querySelector(".toast")?.remove();
  const note = document.createElement("div");
  note.className = "toast";
  note.setAttribute("role", "status");
  note.textContent = text;
  document.body.append(note);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => note.remove(), 4000);
}

// ---------- data ----------

async function refresh() {
  try {
    const messages = normaliseMessages(await api.messages(100));
    const firstLoad = !state.loaded;
    const changed = firstLoad || !sameMessages(messages, state.messages);
    state.messages = messages;
    state.loaded = true;
    state.connected = true;
    state.error = "";
    const activity = (await syncEvents()) || (await learnNames());
    renderVoice(await api.voice().catch(() => null));
    if (changed || activity) renderTranscript({ forceScroll: firstLoad });
  } catch (error) {
    state.connected = false;
    state.error = error instanceof CoreError && !error.unavailable ? error.message : "";
  }
  state.attempted = true;
  renderConnection();
}

// Follow Core's event feed for task and memory activity. Returns true when chips changed.
async function syncEvents() {
  let changed = false;
  const touched = new Set();
  try {
    for (let page = 0; page < 10; page += 1) {
      const read = readEvents(await api.events(state.sequence));
      if (read.resync) { state.tasks.clear(); state.used.clear(); changed = true; }
      for (const id of read.tasks) touched.add(id);
      for (const { requestId, memoryIds } of read.memories) {
        const set = state.used.get(requestId) ?? new Set();
        for (const id of memoryIds) set.add(id);
        state.used.set(requestId, set);
        changed = true;
      }
      if (read.next !== null) state.sequence = read.next;
      if (!read.more) break;
    }
  } catch {
    return changed; // The feed is optional: chat keeps working without chips.
  }
  // Only the most recent tasks matter for chips; fetch each changed one's current record.
  const ids = [...touched].slice(-20);
  await Promise.all(ids.map(async (id) => {
    try {
      state.tasks.set(id, await api.task(id));
      changed = true;
    } catch { /* not ours or gone */ }
  }));
  while (state.tasks.size > 200) state.tasks.delete(state.tasks.keys().next().value);
  return changed;
}

// ---------- voice: the mic button starts voice, then hold it to talk ----------

let voiceTone = "";
const talk = new PressToTalk(async (action) => {
  const status = await api.voiceAction(action);
  renderVoice(status);
  return status;
});

function renderVoice(status) {
  const badge = voiceBadge(status);
  voiceTone = badge.tone;
  els.voice.dataset.voice = talk.held ? "live" : badge.tone;
  els.voice.title = talk.held ? "Listening · let go to send"
    : badge.tone === "ready" ? "Hold to talk (mouse or Space) · right-click for the Voice window"
    : badge.tone === "loading" ? badge.title
    : badge.tone === "error" ? `${badge.title} · click to try again, right-click for the Voice window`
    : badge.tone === "live" || badge.tone === "listening" ? badge.title
    : "Click to start voice · right-click for the Voice window";
}

async function startVoice() {
  els.voice.dataset.voice = "loading";
  toast("Starting voice… the first start loads the speech models.");
  try {
    renderVoice(await api.voiceAction("start"));
  } catch (error) {
    renderVoice(null);
    toast(error instanceof CoreError ? error.message : "Voice could not start.");
  }
}

async function holdToTalk() {
  if (voiceTone !== "ready" || talk.held) return;
  els.voice.dataset.voice = "live";
  els.voice.title = "Listening · let go to send";
  try {
    await talk.press();
  } catch (error) {
    renderVoice(null);
    toast(error instanceof CoreError ? error.message : "The microphone did not open.");
  }
}

async function letGo(discard = false) {
  if (!talk.held) return;
  try {
    await talk.letGo({ discard });
    if (!discard) toast("Sent. SORA answers out loud.");
  } catch (error) {
    toast(error instanceof CoreError ? error.message : "Release was not confirmed.");
  }
  renderVoice(await api.voice().catch(() => null));
}

function schedulePoll() {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(async () => { await refresh(); schedulePoll(); }, POLL_MS);
}

async function submit() {
  const text = els.draft.value;
  if (state.pending || !canSend(text, { connected: state.connected, busy: false })) return;
  const requestId = newRequestId();
  const files = [...state.attachments];
  state.pending = { requestId, text: text.trim(), knownCount: state.messages.length,
    state: "thinking", at: new Date().toISOString() };
  els.draft.value = "";
  state.attachments = [];
  renderAttachments();
  autoGrow();
  renderTranscript({ forceScroll: true });
  renderSendButton();
  try {
    await api.dialogue(state.pending.text, requestId, undefined, files);
  } catch (error) {
    const stopped = error instanceof CoreError && error.code === "DIALOGUE_CANCELLED";
    if (!stopped) toast(error instanceof CoreError ? error.message : "The message was not sent.");
    await refresh();
    const recorded = state.messages.slice(state.pending.knownCount)
      .some((m) => m.who === "user" && m.text === state.pending.text);
    // Never lose what the owner typed: restore it if Core did not record it.
    if (!recorded && !els.draft.value) {
      els.draft.value = state.pending.text;
      state.attachments = files;
      renderAttachments();
    }
  } finally {
    const sent = state.pending;
    state.pending = null;
    await refresh();
    const link = replyFor(state.messages, sent.knownCount, sent.text);
    if (link) {
      state.links.set(sent.requestId, link);
      saveLinks();
    }
    renderTranscript({ forceScroll: true });
    autoGrow();
    renderSendButton();
  }
}

async function stop() {
  const pending = state.pending;
  if (!pending) return;
  try {
    await api.cancelDialogue(pending.requestId);
    toast("Stopped.");
  } catch (error) {
    toast(error instanceof CoreError ? error.message : "Could not stop the reply.");
  }
}

// ---------- input ----------

function autoGrow() {
  els.draft.style.height = "auto";
  els.draft.style.height = `${Math.min(els.draft.scrollHeight, 160)}px`;
}

els.draft.addEventListener("input", () => { autoGrow(); renderSendButton(); });
els.draft.addEventListener("keydown", (event) => {
  if (isSendKey(event)) {
    event.preventDefault();
    if (!state.pending) submit();
  }
});
els.composer.addEventListener("submit", (event) => {
  event.preventDefault();
  if (state.pending) stop(); else submit();
});
els.voice.addEventListener("pointerdown", (event) => {
  if (event.button !== 0) return;
  if (voiceTone === "ready") {
    els.voice.setPointerCapture(event.pointerId);
    holdToTalk();
  }
});
els.voice.addEventListener("pointerup", () => letGo());
els.voice.addEventListener("lostpointercapture", () => { if (talk.held) letGo(); });
els.voice.addEventListener("pointercancel", () => letGo(true));
els.voice.addEventListener("click", async () => {
  if (voiceTone === "" || voiceTone === "error") startVoice();
  else if (voiceTone === "listening") {
    // One click turns always-on listening off: the microphone closes with the voice worker.
    try { renderVoice(await api.voiceAction("close")); toast("Stopped listening. Microphone closed."); }
    catch (error) { toast(error instanceof CoreError ? error.message : "Could not stop listening."); }
  }
});
els.voice.addEventListener("keydown", (event) => {
  if (event.key === " " && !event.repeat) { event.preventDefault(); holdToTalk(); }
});
els.voice.addEventListener("keyup", (event) => {
  if (event.key === " ") { event.preventDefault(); letGo(); }
});
els.voice.addEventListener("contextmenu", (event) => {
  event.preventDefault();
  sendToHost("panel.open", { panel: "voice" });
  if (!hosted) toast("The Voice window opens in SORA's app.");
});
// Losing the window while holding the mic discards the recording, like the Voice window.
window.addEventListener("blur", () => letGo(true));
els.attach.addEventListener("click", async () => {
  if (state.attachments.length >= MAX_ATTACHMENTS) return;
  const path = await pickFile("attachment");
  if (path && !state.attachments.includes(path)) {
    state.attachments.push(path);
    renderAttachments();
  }
  els.draft.focus();
});
els.transcript.addEventListener("scroll", () => { if (nearBottom()) els.jump.hidden = true; });
els.jump.addEventListener("click", scrollToEnd);
window.addEventListener("focus", () => els.draft.focus());

// Agent names (custom agents' nicknames) come from Core's catalogue. Core may still be starting
// when this window opens, so keep asking on each poll until it answers.
async function learnNames() {
  if (agentNamesKnown()) return false;
  try {
    learnAgentNames(await api.agents());
    return agentNamesKnown();
  } catch {
    return false;
  }
}
learnNames().then((learned) => { if (learned) renderTranscript(); });
await refresh();
renderTranscript({ forceScroll: true });
els.draft.focus();
schedulePoll();
