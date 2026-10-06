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
