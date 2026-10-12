import { agentName, taskStatus } from "../shared/tasks.js";

// Chat state with no DOM: what to show, given Core's messages and the turn in flight.
// Core's message list is authoritative; a pending turn is only shown until Core records it.

export function newRequestId(random = globalThis.crypto) {
  // Core accepts [A-Za-z0-9_-]{1,128}.
  const raw = random?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `panel-${raw}`.replace(/[^A-Za-z0-9_-]/g, "").slice(0, 128);
}

/** Who wrote a Core message: the owner, SORA, or Core itself (status and alert lines). */
export function speaker(message) {
  if (message?.role === "user") return "user";
  if (message?.role === "status" || message?.role === "alert") return "core";
  return "sora";
}

export function normaliseMessages(raw) {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((m) => m && typeof m.message_id === "string" && typeof m.content === "string")
    .map((m) => ({
      id: m.message_id,
      who: speaker(m),
      text: m.content,
      at: typeof m.created_at === "string" ? m.created_at : null,
      provenance: typeof m.provenance === "string" ? m.provenance : "",
    }));
}

/**
 * Rows to render: Core's messages, then the pending owner message and a "thinking" row while
 * a turn is in flight. The pending owner message disappears as soon as Core lists it.
 */
export function viewRows(messages, pending) {
  const rows = [...messages];
  if (pending) {
    const recorded = messages.some((m, index) => m.who === "user" && m.text === pending.text
      && index >= pending.knownCount);
    if (!recorded) rows.push({ id: `pending-${pending.requestId}`, who: "user", text: pending.text,
      at: pending.at, pending: true });
    if (pending.state === "thinking") {
      rows.push({ id: `thinking-${pending.requestId}`, who: "sora", text: "", thinking: true });
    }
  }
  return rows;
}

/** Same messages in the same order? Used to avoid re-rendering on every poll. */
export function sameMessages(a, b) {
  return a.length === b.length && a.every((m, i) => m.id === b[i].id && m.text === b[i].text);
}

export function formatTime(iso, locale = undefined) {
  if (!iso) return "";
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "";
  return when.toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" });
}

/** Enter sends; Shift+Enter is a new line; Enter while an IME is composing does neither. */
export function isSendKey(event) {
  return event.key === "Enter" && !event.shiftKey && !event.isComposing && event.keyCode !== 229;
}

export function canSend(draft, { connected, busy }) {
  return connected && !busy && draft.trim().length > 0 && draft.length <= 16_000;
}

// ---------- What SORA did: Core's evidence footers become chips ----------

const EVIDENCE = [
  { prefix: "Automatic desktop image unavailable:", kind: "looked-failed", label: "Couldn't see the desktop" },
  { prefix: "Automatic desktop image:", kind: "looked", label: "Looked at the desktop" },
  { prefix: "Closer window image unavailable:", kind: "looked-failed", label: "Couldn't look closer" },
  { prefix: "Closer window image:", kind: "looked", label: "Looked closer at a window" },
  // Replies saved before 2026-10-08 carry the older window-only footers.
  { prefix: "Automatic window image unavailable:", kind: "looked-failed", label: "Couldn't see the window" },
  { prefix: "Automatic window image:", kind: "looked", label: "Looked at the window" },
  { prefix: "Background window context:", kind: "context", label: "Used what she saw earlier" },
];

/**
 * Split a reply into what SORA said and Core's own records of what happened (appended by Core,
 * never written by the model). Unknown text always stays in the body.
 */
export function splitEvidence(text) {
  let body = String(text ?? "");
  const evidence = [];
  const read = body.indexOf("\n\nRead evidence:\n");
  if (read !== -1) {
    const items = body.slice(read + "\n\nRead evidence:\n".length).split("\n")
      .map((line) => line.replace(/^- /, "").trim()).filter(Boolean);
    body = body.slice(0, read);
    evidence.push({ kind: "read", label: `Read ${items.length} source${items.length === 1 ? "" : "s"}`,
      items });
  }
  const paragraphs = body.split("\n\n");
  while (paragraphs.length > 1) {
    const last = paragraphs[paragraphs.length - 1].trim();
    const match = EVIDENCE.find((entry) => last.startsWith(entry.prefix));
    if (!match) break;
    paragraphs.pop();
    evidence.unshift({ kind: match.kind, label: match.label,
      items: [last.slice(match.prefix.length).trim()] });
  }
  return { body: paragraphs.join("\n\n").trimEnd(), evidence };
}

// ---------- Inert formatting: a small, safe subset of Markdown ----------

/** Inline spans: **bold** and `code`. Everything else is plain text. */
export function spans(text) {
  const out = [];
  const pattern = /(\*\*[^*\n]+\*\*|`[^`\n]+`)/g;
  let last = 0;
  for (const match of String(text).matchAll(pattern)) {
    if (match.index > last) out.push({ text: text.slice(last, match.index) });
    const token = match[0];
    out.push(token.startsWith("**") ? { text: token.slice(2, -2), bold: true }
      : { text: token.slice(1, -1), code: true });
    last = match.index + token.length;
  }
  if (last < text.length) out.push({ text: text.slice(last) });
  return out;
}

/**
 * Blocks to render: paragraphs, bullet or numbered lists, headings (shown as bold lines) and
 * fenced code. Rendered with text nodes only, so no HTML from a message ever runs.
 */
export function blocks(text) {
  const lines = String(text ?? "").replace(/\r\n/g, "\n").split("\n");
  const result = [];
  let paragraph = [];
  let list = null;
  const flush = () => {
    if (paragraph.length) result.push({ type: "p", spans: spans(paragraph.join("\n")) });
    paragraph = [];
    if (list) result.push(list);
    list = null;
  };
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (/^```/.test(line.trim())) {
      flush();
      const code = [];
      for (index += 1; index < lines.length && !/^```/.test(lines[index].trim()); index += 1) {
        code.push(lines[index]);
      }
      result.push({ type: "code", text: code.join("\n") });
      continue;
    }
    const bullet = /^\s*(?:[-*•]|(\d+)[.)])\s+(.*)$/.exec(line);
    if (bullet) {
      if (paragraph.length) { result.push({ type: "p", spans: spans(paragraph.join("\n")) }); paragraph = []; }
      const ordered = bullet[1] !== undefined;
      if (!list || list.ordered !== ordered) {
        if (list) result.push(list);
        list = { type: "list", ordered, items: [] };
      }
      list.items.push(spans(bullet[2]));
      continue;
    }
    const heading = /^#{1,6}\s+(.*)$/.exec(line);
    if (heading) { flush(); result.push({ type: "p", spans: [{ text: heading[1], bold: true }] }); continue; }
    if (!line.trim()) { flush(); continue; }
    if (list) { result.push(list); list = null; }
    paragraph.push(line);
  }
  flush();
  return result;
}

// ---------- Voice state on the microphone button ----------

/** What the microphone button shows, from Core's local voice status. */
export function voiceBadge(status) {
  if (!status || typeof status !== "object") return { tone: "", title: "Voice" };
  const state = String(status.state ?? "");
  // Always-on listening: the microphone is open by design; the button switches it off.
  if (status.running && status.listening && state !== "error") {
    return { tone: "listening", title: status.hearing ? "Hearing you… · click to stop listening"
      : `${status.message || "Listening"} · click to stop listening` };
  }
  if (status.microphone_open) return { tone: "live", title: "Voice · microphone open" };
  if (state === "error") return { tone: "error", title: `Voice problem: ${status.message || "see the Voice window"}` };
  if (state === "loading") return { tone: "loading", title: "Voice is starting…" };
  if (status.running) return { tone: "ready", title: "Voice ready · hold to talk in the Voice window" };
  return { tone: "", title: "Voice is off · click to open the Voice window" };
}

// ---------- Turn activity: tasks SORA started and memories she used ----------

const TASK_EVENTS = new Set([
  "task.planned", "task.created", "task.started", "task.retried", "task.steered", "run.created",
  "run.launching", "run.running", "run.completed", "run.failed", "run.cancelled", "run.interrupted",
]);
const ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/;

/** Read one page of Core's event feed: which tasks changed, and which memories each turn used. */
export function readEvents(page) {
  const tasks = new Set();
  const memories = [];
  for (const event of Array.isArray(page?.events) ? page.events : []) {
    if (!event || typeof event.event_type !== "string") continue;
    if (TASK_EVENTS.has(event.event_type) && ID.test(String(event.task_id ?? ""))) {
      tasks.add(event.task_id);
    }
    const data = event.payload;
    if (event.event_type === "memory.retrieved" && data && ID.test(String(data.dialogue_request_id ?? ""))
        && Array.isArray(data.memories)) {
      const ids = data.memories.map((m) => m?.memory_id).filter((id) => ID.test(String(id ?? "")));
      if (ids.length) memories.push({ requestId: data.dialogue_request_id, memoryIds: ids });
    }
  }
  return {
    tasks: [...tasks], memories,
    next: Number.isInteger(page?.next_sequence) ? page.next_sequence : null,
    more: Boolean(page?.more_available), resync: Boolean(page?.resync_required),
  };
}

export { agentName } from "../shared/tasks.js";

/** A task chip: who is doing it and its state, from Core's task record only. */
export function taskChip(task) {
  const status = taskStatus(task?.status);
  return {
    id: task.task_id,
    label: `Asked ${agentName(task.effective_backend || task.requested_backend)} · ${status.label}`,
    tone: status.tone,
  };
}

/** The owner message a SORA reply answers: the nearest earlier message from the owner. */
export function turnOwnerMessage(messages, index) {
  for (let at = index - 1; at >= 0; at -= 1) {
    if (messages[at].who === "user") return messages[at].id;
    if (messages[at].who === "sora") return null;
  }
  return null;
}

/** After a turn sent from this window finishes, the reply that belongs to its request. */
export function replyFor(messages, knownCount, text) {
  for (let at = knownCount; at < messages.length; at += 1) {
    if (messages[at].who === "user" && messages[at].text === text) {
      const reply = messages.slice(at + 1).find((m) => m.who === "sora");
      return reply ? { userId: messages[at].id, replyId: reply.id } : null;
    }
  }
  return null;
}

/**
 * Hold-to-talk against Core's local voice worker: press sends "begin", release sends "end", and
 * a lost press (focus or pointer lost) sends "stop", which discards the recording. A release that
 * happens while "begin" is still in flight is sent as soon as "begin" settles.
 */
export class PressToTalk {
  constructor(act) {
    this.act = act;
    this.held = false;
    this.beginning = null;
    this.release = "end";
  }

  async press() {
    if (this.held) return;
    this.held = true;
    this.release = "end";
    this.beginning = this.act("begin");
    try {
      await this.beginning;
    } catch (error) {
      this.held = false;
      throw error;
    } finally {
      this.beginning = null;
    }
  }

  async letGo({ discard = false } = {}) {
    if (!this.held) return;
    if (discard) this.release = "stop";
    if (this.beginning) {
      try { await this.beginning; } catch { return; }
    }
    if (!this.held) return;
    this.held = false;
    await this.act(this.release);
  }
}
