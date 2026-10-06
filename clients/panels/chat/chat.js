import { CoreApi, CoreError } from "../shared/api.js";
import { hosted, send as sendToHost } from "../shared/bridge.js";
import { icon } from "../shared/icons.js";
import { setUpWindow } from "../shared/window.js";
import {
  canSend, formatTime, isSendKey, newRequestId, normaliseMessages, sameMessages, viewRows,
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
};
const state = { messages: [], pending: null, connected: false, loaded: false, attempted: false,
  error: "" };
let pollTimer = 0;
let toastTimer = 0;

setUpWindow();
els.voice.innerHTML = icon("mic", "Voice");
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

function messageItem(row) {
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
  } else {
    const text = document.createElement("div");
    text.className = "text";
    text.textContent = row.text;
    body.append(text);
  }
  item.append(body);
  return item;
}

function renderTranscript({ forceScroll = false } = {}) {
  const stick = forceScroll || nearBottom();
  const rows = viewRows(state.messages, state.pending);
  els.transcript.replaceChildren(...rows.map(messageItem));
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
    if (changed) renderTranscript({ forceScroll: firstLoad });
  } catch (error) {
    state.connected = false;
    state.error = error instanceof CoreError && !error.unavailable ? error.message : "";
  }
  state.attempted = true;
  renderConnection();
}

function schedulePoll() {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(async () => { await refresh(); schedulePoll(); }, POLL_MS);
}

async function submit() {
  const text = els.draft.value;
  if (state.pending || !canSend(text, { connected: state.connected, busy: false })) return;
  const requestId = newRequestId();
  state.pending = { requestId, text: text.trim(), knownCount: state.messages.length,
    state: "thinking", at: new Date().toISOString() };
  els.draft.value = "";
  autoGrow();
  renderTranscript({ forceScroll: true });
  renderSendButton();
  try {
    await api.dialogue(state.pending.text, requestId);
  } catch (error) {
    const stopped = error instanceof CoreError && error.code === "DIALOGUE_CANCELLED";
    if (!stopped) toast(error instanceof CoreError ? error.message : "The message was not sent.");
    await refresh();
    const recorded = state.messages.slice(state.pending.knownCount)
      .some((m) => m.who === "user" && m.text === state.pending.text);
    // Never lose what the owner typed: restore it if Core did not record it.
    if (!recorded && !els.draft.value) els.draft.value = state.pending.text;
  } finally {
    state.pending = null;
    await refresh();
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
els.voice.addEventListener("click", () => {
  sendToHost("panel.open", { panel: "voice" });
  if (!hosted) toast("Voice opens in SORA's app, not in a browser preview.");
});
els.transcript.addEventListener("scroll", () => { if (nearBottom()) els.jump.hidden = true; });
els.jump.addEventListener("click", scrollToEnd);
window.addEventListener("focus", () => els.draft.focus());

await refresh();
renderTranscript({ forceScroll: true });
els.draft.focus();
schedulePoll();
