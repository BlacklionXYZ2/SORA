// Memory state with no DOM: Core's canonical memory pages and exact records, the owner's
// correction and forget drafts, and SORA's "show this memory" highlight. Only fields Core
// supplies are shown, a read that was overtaken never overwrites newer state, and a change whose
// outcome is unknown is frozen and never sent again by itself (MemoryForm.cs, MemoryEdits.cs).

import { CoreError, ITEM_ID } from "../shared/api.js";

export const STATES = Object.freeze([
  { value: "active", label: "Active" },
  { value: "expired", label: "Expired" },
  { value: "superseded", label: "Replaced by a correction" },
  { value: "all", label: "Any state" },
]);
export const PROJECTS = Object.freeze([
  { value: "all", label: "This project and global" },
  { value: "project", label: "This project only" },
  { value: "global", label: "Global only" },
]);
export const DEFAULT_QUERY = Object.freeze({ q: "", state: "active", project: "all", scope: "" });
export const PAGE_LIMIT = 50;
/** Cursor history kept for Previous (Core's cursors, unchanged). */
export const MAX_PAGES = 256;
/** Core keeps at most this many characters (code points) of memory text. */
export const MAX_CONTENT = 16384;
export const READ_MS = 15000;
export const EDIT_MS = 30000;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const CURSOR = /^[A-Za-z0-9_-]{1,1024}$/;
const CONTROL = /[\u0000-\u001f\u007f-\u009f]/;
const OFFSET_TIME = /(?:Z|[+-]\d{2}:\d{2})$/;
const VISIBLE_STATES = ["active", "expired", "superseded"];
const EVIDENCE_KINDS = ["repository", "file", "document", "image", "telemetry", "artifact"];
const NAVIGATION = ["opened", "opened_with_limitations", "clarification_required", "not_found",
  "unsupported", "failed"];

/**
 * Refusals that prove nothing was written, so the draft is released for review. Everything else
 * (no answer, a timeout, a 5xx, a reply that does not match) leaves the request frozen. The two
 * PANEL_ codes come from SoraShell's proxy, which refuses before anything reaches Core.
 */
export const DEFINITE_REJECTIONS = Object.freeze(new Set([
  "MEMORY_VERSION_CONFLICT", "MEMORY_STATE_CONFLICT", "CORE_INSTANCE_CHANGED", "RUNTIME_CHANGED",
  "RUNTIME_SHUTTING_DOWN", "INVALID_MEMORY_MUTATION", "NOT_FOUND", "FORBIDDEN",
  "PANEL_ROUTE_REFUSED", "PANEL_BODY_TOO_LARGE",
]));

/**
 * What Forget does, as Core's code does it (routes.py deletes the saved moment on a first forget;
 * memory_mutations.py soft-deletes the record and keeps other versions).
 */
export const FORGET_MEANING = "SORA stops using this exact memory and it leaves this list. If SORA "
  + "saved the moment behind it (pictures, your recording and what was said), that is deleted too. "
  + "Other versions and corrections stay. Conversation history, audit records, backups and agent "
  + "transcripts are not erased. There is no Undo.";

export const EMPTY_PAGE = "No memories match. Search looks for the exact words you type, not their "
  + "meaning, and forgotten memories are not shown.";

/** Core's data was not what this page can safely show. */
export class MemoryDataError extends Error {
  constructor(message) { super(message); this.name = "MemoryDataError"; }
}

/** Core answered as a different instance than the one this page was reading from. */
export class CoreChangedError extends MemoryDataError {
  constructor(instance) {
    super("SORA's Core restarted, so this answer belongs to a different Core.");
    this.name = "CoreChangedError";
    this.instance = instance;
  }
}

/** A check before an effect failed, so nothing was sent. */
class NothingSent extends Error {}

export function message(error) {
  // In SoraShell a 409 RUNTIME_CHANGED means Core restarted and the host has not caught up yet.
  if (error?.code === "RUNTIME_CHANGED") return "SORA's Core has just restarted. Try again in a moment.";
  return error instanceof Error ? error.message : String(error?.message ?? error);
}

// ---------- validation ----------

export function wellFormed(text) {
  return typeof text.isWellFormed === "function" ? text.isWellFormed() : !/\p{Cs}/u.test(text);
}

/** An exact memory or reference ID that Core and SoraShell's proxy both accept. */
export function validId(id) {
  return typeof id === "string" && ITEM_ID.test(id) && !id.includes("..");
}

/** "" when the filters are ones Core accepts (memory_browser.py `_filters`), else why not. */
export function queryError(query) {
  const { q, state, project, scope } = query ?? {};
  if (typeof q !== "string" || typeof scope !== "string" || q.length > 256 || scope.length > 128
      || CONTROL.test(q + scope) || !wellFormed(q + scope)
      || !STATES.some((item) => item.value === state)
      || !PROJECTS.some((item) => item.value === project)) {
    return "Use up to 256 characters of search words and up to 128 for the scope, with no line "
      + "breaks or control characters.";
  }
  return "";
}

export function sameQuery(a, b) {
  return Boolean(a && b) && a.q === b.q && a.state === b.state && a.project === b.project
    && a.scope === b.scope;
}

/** "" when the text can be saved as a correction, else why not. */
export function contentError(text) {
  if (typeof text !== "string" || !text.replace(/[\s\u001c-\u001f\u0085]/g, "").length) {
    return "Write the corrected memory first.";
  }
  if (text.includes("\0")) return "The text contains a NUL character, which Core does not accept.";
  if (!wellFormed(text)) return "The text contains a broken character. Retype the last few characters.";
  const count = codePoints(text);
  if (count > MAX_CONTENT) {
    return `This is ${count.toLocaleString("en-GB")} characters; a memory holds at most 16,384.`;
  }
  return "";
}

export function codePoints(text) { return [...text].length; }

// ---------- Core's pages and records (MemoryPresentation.cs) ----------

function bad(text) { return new MemoryDataError(text); }

function text(data, name, max, nonempty = true) {
  const value = data?.[name];
  if (typeof value !== "string" || value.length > max || (nonempty && value.length === 0)) {
    throw bad(`Core sent an unusable memory field (${name}).`);
  }
  return value;
}

function id(data, name) {
  const value = text(data, name, 128);
  if (!ITEM_ID.test(value)) throw bad(`Core sent an unusable identifier (${name}).`);
  return value;
}

function optionalId(data, name) {
  return data?.[name] === null || data?.[name] === undefined ? null : id(data, name);
}

function number(data, name, min = 0) {
  const value = data?.[name];
  if (!Number.isSafeInteger(value) || value < min) throw bad(`Core sent an unusable number (${name}).`);
  return value;
}

function flag(data, name) {
  if (typeof data?.[name] !== "boolean") throw bad(`Core sent an unusable flag (${name}).`);
  return data[name];
}

function time(data, name) {
  const value = text(data, name, 80);
  if (!OFFSET_TIME.test(value) || Number.isNaN(Date.parse(value))) {
    throw bad(`Core sent a time without a time zone (${name}).`);
  }
  return value;
}

function header(data, epoch) {
  if (!data || typeof data !== "object" || Array.isArray(data) || data.schema_version !== "1.0") {
    throw bad("Core sent a memory view this page does not understand.");
  }
  const instance = text(data, "instance_id", 36);
  if (!UUID.test(instance)) throw bad("Core did not say which Core instance answered.");
  if (epoch && instance !== epoch) throw new CoreChangedError(instance);
  return {
    epoch: instance, owner: id(data, "owner_id"), project: optionalId(data, "project_id"),
    revision: number(data, "projection_revision"), observed: time(data, "observed_at"),
    note: text(data, "evidence_note", 32768),
  };
}

function item(row, owner, project) {
  if (!row || typeof row !== "object" || id(row, "owner_id") !== owner) {
    throw bad("Core sent a memory that belongs to someone else.");
  }
  const itemProject = optionalId(row, "project_id");
  if (itemProject !== null && itemProject !== project) throw bad("Core sent a memory from another project.");
  const state = text(row, "state", 16);
  if (!VISIBLE_STATES.includes(state)) throw bad("Core sent a memory in a state this page cannot show.");
  return {
    id: id(row, "memory_id"), owner, project: itemProject, version: number(row, "entity_version", 1),
    state, scope: text(row, "scope", 256, false), sensitivity: text(row, "sensitivity", 256, false),
    retention: text(row, "retention", 256, false), provenance: text(row, "provenance", 1024, false),
    metadataTruncated: flag(row, "metadata_truncated"), preview: text(row, "content_preview", 1024),
    contentTruncated: flag(row, "content_truncated"),
    validUntil: row.valid_until === null || row.valid_until === undefined ? null : time(row, "valid_until"),
  };
}

/**
 * One page of Core's list, checked against the filters it was asked for. Anything inconsistent
 * (other filters, duplicate IDs, a count below what was sent) is refused rather than shown.
 */
export function parsePage(data, query, epoch = null) {
  const problem = queryError(query);
  if (problem) throw bad(problem);
  const h = header(data, epoch);
  const echoed = { q: text(data, "query", 512, false), state: text(data, "state_filter", 16),
    project: text(data, "project_filter", 16), scope: text(data, "scope_filter", 256, false) };
  if (!sameQuery(query, echoed) || number(data, "limit", 1) !== PAGE_LIMIT) {
    throw bad("Core answered for different filters than the ones asked for.");
  }
  if (!Array.isArray(data.memories) || data.memories.length > PAGE_LIMIT) {
    throw bad("Core sent more memories than were asked for.");
  }
  const seen = new Set();
  const items = data.memories.map((row) => {
    const memory = item(row, h.owner, h.project);
    if (seen.has(memory.id) || (query.state !== "all" && memory.state !== query.state)
        || (query.project === "global" && memory.project !== null)
        || (query.project === "project" && (h.project === null || memory.project !== h.project))
        || (query.scope.length > 0 && memory.scope !== query.scope)) {
      throw bad("Core's page does not match its own filters or repeats a memory.");
    }
    seen.add(memory.id);
    return memory;
  });
  const total = number(data, "total");
  if (total < items.length) throw bad("Core's count is lower than the memories it sent.");
  const nextCursor = data.next_cursor === null || data.next_cursor === undefined
    ? null : text(data, "next_cursor", 1024);
  if (nextCursor !== null && !CURSOR.test(nextCursor)) throw bad("Core sent an unusable page cursor.");
  if (nextCursor !== null && items.length === 0) throw bad("Core sent an empty page with more to follow.");
  return { ...h, query: { ...query }, items, total, nextCursor };
}

/** One exact memory. The ID must be the one asked for; no other memory is substituted. */
export function parseDetail(data, wanted, epoch = null) {
  if (!validId(wanted)) throw bad("That is not an exact memory ID.");
  const h = header(data, epoch);
  const row = data.memory;
  const memory = item(row, h.owner, h.project);
  if (memory.id !== wanted) throw bad("Core answered with a different memory; nothing else is shown.");
  if (!Array.isArray(row.evidence) || row.evidence.length > 64) throw bad("Core sent too much evidence.");
  const seen = new Set();
  const evidence = row.evidence.map((link) => {
    const reference = id(link, "reference_id");
    const kind = text(link, "kind", 16);
    if (seen.has(reference) || reference.startsWith("capture-") || !EVIDENCE_KINDS.includes(kind)) {
      throw bad("Core sent evidence this page must not show.");
    }
    seen.add(reference);
    return { id: reference, label: text(link, "label", 1024), kind };
  });
  return { ...h, item: memory, content: text(row, "content", 32768),
    successor: optionalId(row, "superseded_by"), evidence, withheld: flag(row, "evidence_withheld") };
}

// ---------- words for the page ----------

export function stateLabel(state) {
  if (state === "active") return { label: "Active", tone: "ok" };
  if (state === "expired") return { label: "Expired", tone: "off" };
  if (state === "superseded") return { label: "Replaced", tone: "bad" };
  return { label: String(state), tone: "off" };
}

/** A readable local time for one of Core's timestamps (the exact value stays available). */
export function when(iso, { withDate = true } = {}) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return String(iso ?? "");
  return date.toLocaleString("en-GB", withDate
    ? { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }
    : { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

/** The inspector's facts: only what Core's record has. */
export function inspectionFacts(detail) {
  const m = detail.item;
  const facts = [
    { label: "Scope", value: m.scope || "None recorded" },
    { label: "Project", value: m.project ? `This project (${m.project})` : "Global (every project)" },
    { label: "Sensitivity", value: m.sensitivity || "None recorded" },
    { label: "Keep for", value: m.retention || "None recorded" },
    { label: "Where it came from", value: m.provenance || "None recorded" },
    { label: "Valid until", value: m.validUntil ? when(m.validUntil) : "No expiry recorded",
      title: m.validUntil ?? undefined },
  ];
  return facts;
}

/** The list's freshness line: what was read, when, and whether it may be out of date. */
export function pageStatus(state) {
  const page = state.page;
  if (!page) return state.reading ? "Reading memories…" : "Not read yet.";
  const shown = page.items.length;
  const parts = [`Page ${state.pageIndex + 1}`, `${shown} shown of ${page.total} matching`,
    `read at ${when(page.observed, { withDate: false })}`];
  if (state.reading) parts.push("reading…");
  else if (!state.pageCurrent) parts.push("may be out of date");
  return parts.join(" · ");
}

/** Core's answer to "open this evidence", in the classic's words (RetainedRequests.cs). */
export function navigationOutcome(reply, target) {
  if (!reply || typeof reply !== "object" || Array.isArray(reply)) {
    throw bad("Core's answer about opening the evidence was not readable, so the outcome is unknown.");
  }
  const status = typeof reply.status === "string" ? reply.status : "";
  const reason = typeof reply.reason === "string" ? reply.reason : "";
  const reference = typeof reply.reference_id === "string" ? reply.reference_id : "";
  if (!NAVIGATION.includes(status) || !reason.trim() || (reference && reference !== target)
      || (status.startsWith("opened") && reference !== target)) {
    throw bad("Core's answer about opening the evidence was incomplete, so the outcome is unknown.");
  }
  const limitations = Array.isArray(reply.limitations)
    ? reply.limitations.filter((value) => typeof value === "string" && value) : [];
  return {
    ok: status.startsWith("opened"),
    text: `${target} · ${status.replace(/_/g, " ")}: ${reason}`
      + (limitations.length ? ` · ${limitations.join(" · ")}` : ""),
  };
}

/** True when GET /api/v1/content/references still lists the reference (its path is never read). */
export function referenceListed(references, referenceId) {
  return Array.isArray(references?.references)
    && references.references.some((row) => row && row.reference_id === referenceId);
}

// ---------- corrections and forgetting (MemoryEdits.cs) ----------

export function intentError(intent) {
  const i = intent ?? {};
  const okText = i.action !== "correct" || !contentError(i.content);
  if (!UUID.test(String(i.epoch)) || !UUID.test(String(i.requestId)) || !validId(i.id) || !validId(i.owner)
      || (i.project !== null && !validId(i.project)) || !Number.isSafeInteger(i.version) || i.version < 1
      || !["correct", "forget"].includes(i.action) || (i.action === "forget" && i.content !== null)
      || !okText) {
    return "This change is not one Core accepts: an exact memory, its version and the same Core.";
  }
  return "";
}

/** The exact body Core expects; a retry sends this same body with the same request_id. */
export function intentBody(intent) {
  const problem = intentError(intent);
  if (problem) throw new TypeError(problem);
  const body = { instance_id: intent.epoch, request_id: intent.requestId, expected_version: intent.version };
  if (intent.content !== null) body.content = intent.content;
  return body;
}

export async function sha256Hex(textValue) {
  const digest = await globalThis.crypto.subtle.digest("SHA-256", new TextEncoder().encode(textValue));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

/**
 * Core's receipt, accepted only when every field matches the change that was sent, including
 * the SHA-256 of the corrected text. Anything else leaves the outcome unconfirmed.
 */
export function parseAck(data, intent, epoch) {
  const fail = () => bad("Core's reply does not match the change that was sent, so the outcome is unconfirmed.");
  if (intentError(intent) || !data || typeof data !== "object") throw fail();
  const str = (key) => { if (typeof data[key] !== "string") throw fail(); return data[key]; };
  const opt = (key) => { if (data[key] === null) return null; return str(key); };
  const int = (key) => { if (!Number.isSafeInteger(data[key])) throw fail(); return data[key]; };
  if (str("schema_version") !== "1.0" || !UUID.test(String(epoch)) || str("instance_id") !== epoch
      || !UUID.test(str("committed_instance_id")) || !UUID.test(str("request_id"))
      || str("request_id").toLowerCase() !== intent.requestId.toLowerCase()
      || str("owner_id") !== intent.owner || opt("project_id") !== intent.project
      || str("memory_id") !== intent.id || str("action") !== intent.action
      || int("expected_version") !== intent.version || int("entity_version") !== intent.version + 1
      || opt("content_sha256") !== (intent.contentSha256 ?? null)) {
    throw fail();
  }
  const successor = opt("successor_id");
  if (intent.action === "correct") {
    if (successor === null || successor === intent.id || !validId(successor) || data.successor_version !== 1) {
      throw bad("Core's reply names no usable new version, so the outcome is unconfirmed.");
    }
  } else if (successor !== null || data.successor_version !== null) {
    throw bad("Core's reply to Forget names a new version, so the outcome is unconfirmed.");
  }
  const revision = int("projection_revision");
  const eventId = str("event_id");
  const at = str("committed_at");
  if (revision < 1 || !ITEM_ID.test(eventId) || at.length > 80 || !OFFSET_TIME.test(at)
      || Number.isNaN(Date.parse(at))) {
    throw bad("Core's reply has no usable commit time or revision, so the outcome is unconfirmed.");
  }
  const note = str("retention_note");
  if (note.length < 1 || note.length > 32768 || typeof data.replayed !== "boolean") throw fail();
  return { epoch, committedEpoch: data.committed_instance_id, id: intent.id, successor,
    version: intent.version + 1, revision, eventId, at, historical: data.replayed, note,
    action: intent.action };
}

/** The owner's draft, pinned to one exact version on one Core. Lives only while the page does. */
export class EditDraft {
  constructor(original, action = "correct") {
    if (!["correct", "forget"].includes(action)) throw new TypeError("Unknown memory change.");
    this.original = original;
    this.action = action;
    this.text = action === "correct" ? original.content : null;
    this.pending = null;
    this.confirmed = null;
  }

  /** A request was sent and its outcome is not yet known. */
  get needsResolution() { return this.pending !== null && this.confirmed === null; }

  edit(textValue) {
    if (this.pending) throw new Error("This request is frozen until its outcome is known.");
    if (this.action !== "correct") throw new Error("Only a correction has text to edit.");
    this.text = String(textValue);
  }

  /** The request to send. An unresolved request is returned unchanged (same request_id). */
  begin(epoch, newId) {
    if (this.confirmed) throw new Error("This change is done. Inspect the memory before another change.");
    if (this.original.epoch !== epoch) {
      throw new Error("SORA's Core restarted since this draft began. Review the latest version, or check the old request first.");
    }
    if (this.pending) return this.pending;
    if (this.action === "correct" && this.original.item.state !== "active") {
      throw new Error("Only an active memory can be corrected.");
    }
    if (this.action === "correct") {
      const problem = contentError(this.text);
      if (problem) throw new Error(problem);
    }
    const intent = { epoch: this.original.epoch, requestId: String(newId()).toLowerCase(),
      id: this.original.item.id, owner: this.original.owner, project: this.original.item.project,
      version: this.original.item.version, action: this.action,
      content: this.action === "correct" ? this.text : null };
    const problem = intentError(intent);
    if (problem) throw new Error(problem);
    this.pending = intent;
    return intent;
  }

  /** Core refused, so nothing was written: the draft can be edited again. */
  reject() { if (!this.confirmed) this.pending = null; }

  confirm(ack) {
    if (!this.pending || ack.id !== this.pending.id) throw new Error("No matching change was sent.");
    this.confirmed = ack;
  }

  /** Re-pin to the latest version the owner reviewed; their text is kept. */
  review(latest) {
    if (this.pending || latest.item.id !== this.original.item.id || latest.owner !== this.original.owner
        || latest.item.project !== this.original.item.project) {
      throw new Error("Review must be of the same memory, and cannot replace a request whose outcome is unknown.");
    }
    this.original = latest;
  }
}

function conflictWords(code, conflict, action) {
  const version = Number.isSafeInteger(conflict?.current_version) ? conflict.current_version : null;
  const current = typeof conflict?.current_state === "string" ? conflict.current_state : "";
  const now = version !== null || current
    ? ` Core now has ${[version !== null ? `version ${version}` : "", current ? stateLabel(current).label.toLowerCase() : ""]
      .filter(Boolean).join(", ")}.` : "";
  switch (code) {
    case "MEMORY_VERSION_CONFLICT":
      return `This memory changed in Core since you opened it.${now} Review the latest version before trying again.`;
    case "MEMORY_STATE_CONFLICT":
      return `This memory is no longer active, so it cannot be corrected.${now}`;
    case "CORE_INSTANCE_CHANGED": case "RUNTIME_CHANGED":
      return "SORA's Core restarted, so nothing was changed. Review the memory again before retrying.";
    case "RUNTIME_SHUTTING_DOWN": return "SORA's Core is shutting down, so nothing was changed.";
    case "NOT_FOUND": return "Core no longer has this memory, so nothing was changed.";
    case "INVALID_MEMORY_MUTATION": return "Core refused the request as invalid, so nothing was changed.";
    case "FORBIDDEN": return "Core refused this change, so nothing was changed.";
    default: return `The change was not sent${action === "forget" ? "" : "; your draft is kept"}.`;
  }
}

/** A definite refusal: what happened, with Core's current version and state when it gave them. */
export function rejectionOutcome(error, conflict, action) {
  const keep = action === "correct" ? " Your draft is kept." : "";
  return { tone: "bad", text: conflictWords(error?.code, conflict, action) + keep,
    note: `${error?.code ?? "ERROR"}: ${message(error)}` };
}

/** The outcome is unknown: nothing is sent again by itself. */
export function uncertainOutcome(error, intent) {
  return { tone: "warn",
    text: `SORA could not confirm whether Core ${intent.action === "forget" ? "forgot this memory" : "saved your correction"}. `
      + "Nothing will be sent again by itself. Check receipt asks Core what happened; Retry sends the "
      + "exact same request again, which Core will not apply twice.",
    note: `Request ${intent.requestId}. ${message(error)}` };
}

export function editOutcome(ack) {
  const done = ack.historical ? "Core's receipt confirms" : "Core confirmed";
  const what = ack.action === "correct"
    ? `${done} the correction of ${ack.id} (now version ${ack.version}). Your words are a new memory, ${ack.successor}; the old one is kept as replaced.`
    : `${done} that ${ack.id} is forgotten (version ${ack.version}). Other versions are unchanged.`;
  return { tone: "ok", text: `${what} Refresh before relying on the list.`,
    note: `Revision ${ack.revision} · ${when(ack.at)} · ${ack.note}`, successor: ack.successor };
}

// ---------- reads with an upper bound ----------

/** The answer, or a timeout error after `ms`. A late answer is ignored by the caller's fence. */
export function bounded(promise, ms, timers = globalThis) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = timers.setTimeout(() => reject(new CoreError("SORA's Core did not answer in time.",
      { status: 0, code: "TIMEOUT" })), Math.max(1, ms));
  });
  return Promise.race([promise, timeout]).finally(() => timers.clearTimeout(timer));
}

/**
 * Keeps Core's error body for 409 replies, which carry current_version and current_state that
 * CoreError does not keep. Wrap the page's fetch with it and read one with take(path).
 */
export class ErrorDetails {
  constructor(fetchImpl) {
    this.last = new Map();
    this.fetch = async (url, init) => {
      const response = await fetchImpl(url, init);
      if (response?.status === 409 && typeof response.clone === "function") {
        const data = await response.clone().json().catch(() => null);
        this.last.set(String(url), data?.error && typeof data.error === "object" ? data.error : null);
      }
      return response;
    };
  }

  take(path) {
    const value = this.last.get(path) ?? null;
    this.last.delete(path);
    return value;
  }
}

// ---------- the panel's state machine ----------

function initialState() {
  return {
    epoch: null, connected: false, identityChecked: false, canUseCore: true, mode: "overview",
    typed: { ...DEFAULT_QUERY }, applied: null,
    page: null, pageCurrent: false, pageIndex: 0, cursors: [null], reading: false,
    listNote: null,
    selected: null, detail: null, detailCurrent: false, inspecting: false,
    outcome: null,
    draft: null, confirm: null, review: null, discarded: null,
    navigating: false, opening: null, mutating: false, presenting: false,
    highlight: null,
  };
}

/**
 * Everything the Memory page knows and may do. The view renders `state` after every change and
 * forwards the owner's actions here; tests drive it with a fake CoreApi.
 */
export class MemoryBrowser {
  constructor({ api, errors = null, newId = () => globalThis.crypto.randomUUID(), sha256 = sha256Hex,
    now = () => Date.now(), timers = globalThis } = {}) {
    this.api = api;
    this.errors = errors;
    this.newId = newId;
    this.sha256 = sha256;
    this.now = now;
    this.timers = timers;
    this.state = initialState();
    this.seq = { page: 0, detail: 0, user: 0, identity: 0 };
    this.forgetTarget = null;
    this.activePresentation = null;
    this.onChange = () => {};
    this.onHighlightCleared = () => {};
  }

  // ----- derived -----

  /** Work Quit must wait for: an open evidence, a change, a confirmation, a presentation. */
  get busy() {
    const s = this.state;
    return s.navigating || s.mutating || s.presenting || s.confirm !== null;
  }

  /** A draft that is unsent or whose outcome is unknown. */
  get dirty() { return this.state.draft !== null; }

  /** Changes and Open need a Core the host allows and this page has identified. */
  get canChange() { const s = this.state; return s.canUseCore && s.connected && s.epoch !== null; }

  availability() {
    const s = this.state;
    const draft = s.draft;
    const browsing = !this.busy && !draft;
    const detailReady = browsing && s.detailCurrent && s.detail !== null && !s.inspecting;
    return {
      browse: browsing,
      previous: browsing && s.pageCurrent && s.pageIndex > 0,
      next: browsing && s.pageCurrent && Boolean(s.page?.nextCursor) && s.pageIndex < MAX_PAGES - 1,
      open: detailReady && this.canChange,
      correct: detailReady && this.canChange && s.detail.item.state === "active",
      forget: detailReady && this.canChange,
      save: Boolean(draft) && !this.busy && this.canChange && draft.action === "correct" && !draft.pending
        && draft.original.item.state === "active" && draft.original.epoch === s.epoch
        && !contentError(draft.text),
      review: Boolean(draft) && !this.busy && !draft.pending,
      receipt: Boolean(draft?.needsResolution) && !this.busy,
      retry: Boolean(draft?.needsResolution) && !this.busy && this.canChange
        && draft.original.epoch === s.epoch,
      discard: Boolean(draft) && !this.busy,
    };
  }

  emit() {
    const s = this.state;
    const h = s.highlight;
    // A highlight only stands for the exact current record it was shown on.
    if (h && (!s.detailCurrent || s.selected !== h.id || s.detail?.item.id !== h.id
        || s.detail.item.version !== h.version || s.detail.epoch !== h.epoch)) this.clearHighlight();
    this.onChange(s);
  }

  say(textValue, tone = "") { this.state.outcome = { tone, text: textValue }; this.emit(); return false; }

  // ----- Core identity -----

  /** Learn which Core is serving. A different one clears what was read from the old one. */
  observe(epoch, connected) {
    const s = this.state;
    if (s.epoch !== null && epoch !== null && epoch !== s.epoch) {
      this.seq.page += 1;
      this.seq.detail += 1;
      Object.assign(s, { page: null, pageCurrent: false, pageIndex: 0, cursors: [null], reading: false,
        selected: null, detail: null, detailCurrent: false, inspecting: false });
      this.clearHighlight();
      s.listNote = { tone: "warn", text: "SORA's Core restarted. Refresh to read this Core's memories." };
    } else if (!connected && s.connected) {
      s.pageCurrent = false;
      s.detailCurrent = false;
    }
    if (epoch !== null) s.epoch = epoch;
    s.connected = connected;
  }

  async checkIdentity() {
    const seq = ++this.seq.identity;
    try {
      const data = await bounded(this.api.identity(), READ_MS, this.timers);
      if (seq !== this.seq.identity) return;
      const instance = data?.instance_id;
      if (typeof instance !== "string" || !UUID.test(instance)) throw bad("Core did not report its identity.");
      this.observe(instance, true);
    } catch {
      if (seq !== this.seq.identity) return;
      this.observe(null, false);
    }
    this.state.identityChecked = true;
    this.emit();
  }

  /** The page's regular check. Reconnected with nothing read yet (Core was down at start): read now. */
  async poll() {
    const wasConnected = this.state.connected;
    await this.checkIdentity();
    const s = this.state;
    if (!wasConnected && s.connected && !s.page && !s.reading) await this.readPage({ user: false });
    this.expireHighlight();
  }

  /** A response came from another Core: confirm through identity, which clears the old reads. */
  async coreChanged() { await this.checkIdentity(); }

  adopt(epoch) { if (this.state.epoch === null) this.observe(epoch, true); else this.state.connected = true; }

  setCanUseCore(value) {
    if (typeof value !== "boolean") return;
    this.state.canUseCore = value;
    this.emit();
  }

  // ----- the list -----

  setMode(mode) {
    if (mode !== "overview" && mode !== "search") return false;
    if (mode === "overview") return this.overview();
    this.state.mode = "search";
    this.emit();
    return true;
  }

  /** Overview: the default filters (active, this project and global), read again. */
  async overview() {
    const s = this.state;
    if (!this.availability().browse) return false;
    s.mode = "overview";
    s.typed = { ...DEFAULT_QUERY };
    return this.readPage();
  }

  setFilter(name, value) {
    const s = this.state;
    if (!(name in DEFAULT_QUERY) || s.draft || this.busy) return false;
    if (s.typed[name] === value) return true;
    s.typed = { ...s.typed, [name]: String(value) };
    this.seq.user += 1;
    this.clearHighlight();
    if (s.page) {
      s.pageCurrent = false;
      s.listNote = { tone: "warn",
        text: "Filters changed. Press Search to read matching memories; the list below is from before." };
    }
    const problem = queryError(s.typed);
    if (problem) s.listNote = { tone: "bad", text: problem };
    this.emit();
    return true;
  }

  async refresh() { return this.readPage(); }

  async next() {
    const s = this.state;
    if (!this.availability().next) return false;
    return this.readPage({ query: s.applied, cursor: s.page.nextCursor, index: s.pageIndex + 1 });
  }

  async previous() {
    const s = this.state;
    if (!this.availability().previous) return false;
    return this.readPage({ query: s.applied, cursor: s.cursors[s.pageIndex - 1], index: s.pageIndex - 1 });
  }

  /** Read one page. A newer read, or a different Core, makes an older answer irrelevant. */
  async readPage({ query = this.state.typed, cursor = null, index = 0, user = true } = {}) {
    const s = this.state;
    if (s.draft || this.busy) return false;
    const wanted = { ...query };
    const problem = queryError(wanted);
    if (problem) { s.listNote = { tone: "bad", text: problem }; this.emit(); return false; }
    if ((cursor !== null && !CURSOR.test(cursor)) || index < 0 || index >= MAX_PAGES) return false;
    if (user) { this.seq.user += 1; this.clearHighlight(); }
    const seq = ++this.seq.page;
    const selectedAtStart = s.selected;
    s.reading = true;
    this.emit();
    let reinspect = null;
    let autoSelect = null;
    try {
      const data = await bounded(this.api.memories({ ...wanted, cursor }), READ_MS, this.timers);
      if (seq !== this.seq.page) return false;
      const page = parsePage(data, wanted, s.epoch);
      this.adopt(page.epoch);
      s.page = page;
      s.pageCurrent = true;
      s.applied = wanted;
      s.pageIndex = index;
      s.cursors = index === 0 ? [null] : [...s.cursors.slice(0, index), cursor];
      s.listNote = page.items.length ? null : { tone: "", text: EMPTY_PAGE };
      if (index === MAX_PAGES - 1 && page.nextCursor) {
        s.listNote = { tone: "warn", text: "This is the last page SORA keeps track of. Refresh to start again from the newest." };
      }
      const listed = page.items.some((row) => row.id === s.selected);
      if (s.selected !== null && s.selected === selectedAtStart && !listed) {
        // The classic rule: a selection that is not on the new page is let go.
        s.selected = null;
        s.detail = null;
        s.detailCurrent = false;
        this.seq.detail += 1;
        s.inspecting = false;
      } else if (listed && !s.detailCurrent && !s.inspecting) {
        reinspect = s.selected;
      }
      // Nothing chosen: show the first row, as a fresh selection would.
      if (s.selected === null && page.items.length) autoSelect = page.items[0].id;
      return true;
    } catch (error) {
      if (seq !== this.seq.page) return false;
      if (error instanceof CoreChangedError) { s.reading = false; await this.coreChanged(); return false; }
      s.pageCurrent = false;
      s.listNote = { tone: "bad", text: `Memories could not be read${s.page ? "; the list below is from before" : ""}. ${message(error)}` };
      if (error?.code === "RUNTIME_CHANGED") void this.checkIdentity();
      return false;
    } finally {
      if (seq === this.seq.page) s.reading = false;
      this.emit();
      if (reinspect && s.selected === reinspect && !s.draft && !this.busy) void this.inspect(reinspect);
      if (autoSelect && s.selected === null && !s.draft && !this.busy) void this.select(autoSelect);
    }
  }

  // ----- one exact memory -----

  /** Select and read one exact memory (a row, an ID the owner typed, or Chat's request). */
  async select(memoryId) {
    const s = this.state;
    if (s.draft) return this.say("Finish or discard your draft before opening another memory.", "warn");
    if (this.busy) return this.say("Wait for the current action to finish before opening another memory.", "warn");
    if (!validId(memoryId)) return this.say("That is not an exact memory ID. IDs look like memory-1a2b3c…", "bad");
    this.seq.user += 1;
    this.clearHighlight();
    if (s.selected !== memoryId) { s.selected = memoryId; s.detail = null; }
    s.detailCurrent = false;
    s.outcome = null;
    return this.inspect(memoryId);
  }

  async inspectExact(raw) { return this.select(String(raw ?? "").trim()); }

  async inspect(memoryId) {
    const s = this.state;
    const seq = ++this.seq.detail;
    s.inspecting = true;
    s.detailCurrent = false;
    this.emit();
    try {
      const data = await bounded(this.api.memory(memoryId), READ_MS, this.timers);
      if (seq !== this.seq.detail || s.selected !== memoryId) return false;
      const detail = parseDetail(data, memoryId, s.epoch);
      this.adopt(detail.epoch);
      s.detail = detail;
      s.detailCurrent = true;
      return true;
    } catch (error) {
      if (seq !== this.seq.detail || s.selected !== memoryId) return false;
      if (error instanceof CoreChangedError) { s.inspecting = false; await this.coreChanged(); return false; }
      s.detailCurrent = false;
      s.outcome = { tone: "bad", text: "That memory is not available, and nothing else was selected.",
        note: message(error) };
      if (error?.code === "RUNTIME_CHANGED") void this.checkIdentity();
      return false;
    } finally {
      if (seq === this.seq.detail) s.inspecting = false;
      this.emit();
    }
  }

  // ----- evidence -----

  /**
   * Open one registered evidence reference: re-read the memory, check the reference is still
   * linked and still registered, then ask Core to open it. Never retried by itself.
   */
  async openEvidence(referenceId) {
    const s = this.state;
    const detail = s.detail;
    if (!this.availability().open || !detail?.evidence.some((link) => link.id === referenceId)) return false;
    const memoryId = detail.item.id;
    s.navigating = true;
    s.opening = referenceId;
    s.outcome = { tone: "", text: "Opening the evidence…" };
    const seq = ++this.seq.detail;
    let sent = false;
    let abandoned = false;
    this.emit();
    try {
      const result = await bounded((async () => {
        const fresh = parseDetail(await this.api.memory(memoryId), memoryId, s.epoch);
        if (seq !== this.seq.detail || s.selected !== memoryId) throw new NothingSent("The selection changed, so nothing was opened.");
        s.detail = fresh;
        s.detailCurrent = true;
        if (!fresh.evidence.some((link) => link.id === referenceId)) {
          throw new NothingSent("This evidence is no longer linked to this memory, so nothing was opened.");
        }
        if (!referenceListed(await this.api.contentReferences(), referenceId)) {
          throw new NothingSent("This evidence is no longer registered with SORA, so nothing was opened.");
        }
        if (!this.canChange) throw new NothingSent("SORA's Core stopped taking actions, so nothing was opened.");
        // Past the time limit the owner was told nothing opened: never send after that.
        if (abandoned) throw new NothingSent("Opening took too long, so nothing was opened.");
        sent = true;
        return navigationOutcome(await this.api.openReference(referenceId), referenceId);
      })(), EDIT_MS, this.timers);
      s.outcome = { tone: result.ok ? "ok" : "warn", text: result.text };
      return result.ok;
    } catch (error) {
      abandoned = true;
      s.outcome = !sent
        ? { tone: "warn", text: error instanceof NothingSent ? message(error) : "Nothing was opened.",
          note: error instanceof NothingSent ? undefined : message(error) }
        : { tone: "bad", text: "SORA could not confirm that the evidence opened, and will not try again by itself.",
          note: message(error) };
      if (error instanceof CoreChangedError) void this.coreChanged();
      return false;
    } finally {
      s.navigating = false;
      s.opening = null;
      this.emit();
    }
  }

  // ----- correcting and forgetting -----

  startCorrection() {
    const s = this.state;
    if (!this.availability().correct) return false;
    s.draft = new EditDraft(s.detail, "correct");
    s.discarded = null;
    s.outcome = { tone: "", text: "Your draft stays here if you close the window. Saving makes a new "
      + "memory with your words and keeps the old one as replaced. Evidence linked to the old text is "
      + "not copied to the new one." };
    this.emit();
    return true;
  }

  editDraft(textValue) {
    const draft = this.state.draft;
    if (!draft || draft.pending || draft.action !== "correct" || this.busy) return false;
    draft.edit(textValue);
    this.emit();
    return true;
  }

  askForget() {
    const s = this.state;
    if (!this.availability().forget) return false;
    this.forgetTarget = s.detail;
    s.confirm = "forget";
    this.emit();
    return true;
  }

  cancelConfirm() {
    const s = this.state;
    if (s.confirm === null) return false;
    s.confirm = null;
    s.review = null;
    this.forgetTarget = null;
    this.emit();
    return true;
  }

  async confirmForget() {
    const s = this.state;
    if (s.confirm !== "forget") return false;
    const value = this.forgetTarget;
    s.confirm = null;
    this.forgetTarget = null;
    if (!s.detailCurrent || !value || s.detail !== value || value.epoch !== s.epoch || !this.canChange || s.draft) {
      return this.say("The memory or SORA's Core changed while you were deciding, so nothing was sent. Inspect it again.", "warn");
    }
    s.draft = new EditDraft(value, "forget");
    s.discarded = null;
    return this.submit();
  }

  /** Save the correction, or (for an unresolved request) retry the exact same request. */
  async submit() {
    const s = this.state;
    const draft = s.draft;
    if (!draft || this.busy || !this.canChange) return false;
    const fresh = draft.pending === null;
    let intent;
    try {
      intent = draft.begin(s.epoch, this.newId);
    } catch (error) {
      if (draft.action === "forget" && !draft.pending) s.draft = null;
      return this.say(message(error), "bad");
    }
    s.mutating = true;
    this.emit();
    if (intent.contentSha256 === undefined) {
      try {
        intent.contentSha256 = intent.content === null ? null : await this.sha256(intent.content);
      } catch (error) {
        if (fresh) { draft.reject(); if (draft.action === "forget") s.draft = null; }
        s.mutating = false;
        return this.say(`Nothing was sent: SORA could not prepare the request. ${message(error)}`, "bad");
      }
    }
    let body;
    try {
      body = intentBody(intent);
    } catch (error) {
      if (fresh) { draft.reject(); if (draft.action === "forget") s.draft = null; }
      s.mutating = false;
      return this.say(`Nothing was sent. ${message(error)}`, "bad");
    }
    const path = `/api/v1/memories/${intent.id}/${intent.action}`;
    try {
      const call = intent.action === "correct"
        ? this.api.correctMemory(intent.id, body) : this.api.forgetMemory(intent.id, body);
      const data = await bounded(call, EDIT_MS, this.timers);
      this.finish(draft, parseAck(data, intent, s.epoch));
      return true;
    } catch (error) {
      if (error instanceof CoreError && DEFINITE_REJECTIONS.has(error.code)) {
        draft.reject();
        const conflict = error.status === 409 ? (error.detail ?? this.errors?.take(path) ?? null) : null;
        s.outcome = rejectionOutcome(error, conflict, intent.action);
        // A refused Forget leaves nothing to keep (the classic kept an odd text draft here).
        if (intent.action === "forget") s.draft = null;
        if (error.code === "RUNTIME_CHANGED" || error.code === "CORE_INSTANCE_CHANGED") void this.checkIdentity();
      } else {
        s.outcome = uncertainOutcome(error, intent);
      }
      return false;
    } finally {
      s.mutating = false;
      this.emit();
    }
  }

  finish(draft, ack) {
    const s = this.state;
    draft.confirm(ack);
    s.draft = null;
    s.pageCurrent = false;
    s.detailCurrent = false;
    s.outcome = editOutcome(ack);
  }

  /** Ask Core for the stored receipt of the frozen request. Reads only; never repeats it. */
  async checkReceipt() {
    const s = this.state;
    const draft = s.draft;
    if (!this.availability().receipt) return false;
    const intent = draft.pending;
    s.mutating = true;
    this.emit();
    try {
      await this.checkIdentity();
      const data = await bounded(this.api.memoryReceipt(intent.requestId), READ_MS, this.timers);
      this.finish(draft, parseAck(data, intent, s.epoch));
      return true;
    } catch (error) {
      s.outcome = { tone: "warn", text: "Core has no matching receipt for this request. It stays frozen: "
        + "no receipt does not prove nothing was saved.", note: `Request ${intent.requestId}. ${message(error)}` };
      return false;
    } finally {
      s.mutating = false;
      this.emit();
    }
  }

  /** Read the same memory again and offer its latest version as the draft's new target. */
  async reviewLatest() {
    const s = this.state;
    const draft = s.draft;
    if (!this.availability().review) return false;
    s.mutating = true;
    this.emit();
    try {
      const memoryId = draft.original.item.id;
      const latest = parseDetail(await bounded(this.api.memory(memoryId), READ_MS, this.timers), memoryId, s.epoch);
      s.review = latest;
      s.confirm = "review";
      return true;
    } catch (error) {
      s.outcome = { tone: "bad", text: "The latest version could not be read. Your draft and its target are unchanged.",
        note: message(error) };
      if (error instanceof CoreChangedError) void this.coreChanged();
      return false;
    } finally {
      s.mutating = false;
      this.emit();
    }
  }

  acceptReview() {
    const s = this.state;
    if (s.confirm !== "review" || !s.review || !s.draft) return false;
    const latest = s.review;
    s.confirm = null;
    s.review = null;
    if (!s.connected || latest.epoch !== s.epoch) {
      return this.say("SORA's Core changed during the review, so the draft still targets the old version.", "warn");
    }
    try {
      s.draft.review(latest);
    } catch (error) {
      return this.say(message(error), "bad");
    }
    if (s.selected === latest.item.id) { this.seq.detail += 1; s.detail = latest; s.detailCurrent = true; s.inspecting = false; }
    return this.say(`The draft now targets version ${latest.item.version}. Your text is kept.`
      + (latest.item.state === "active" ? "" : " This memory is no longer active, so it cannot be corrected."),
    latest.item.state === "active" ? "" : "warn");
  }

  askDiscard() {
    const s = this.state;
    if (!this.availability().discard) return false;
    s.confirm = "discard";
    this.emit();
    return true;
  }

  confirmDiscard() {
    const s = this.state;
    if (s.confirm !== "discard" || !s.draft) return false;
    const unresolved = s.draft.needsResolution ? s.draft.pending.requestId : null;
    s.confirm = null;
    s.draft = null;
    s.outcome = { tone: unresolved ? "warn" : "", text: "Draft discarded. This does not undo anything already sent.",
      note: unresolved ? `The outcome of request ${unresolved} is still unknown.` : undefined };
    this.emit();
    return true;
  }

  // ----- SORA's "show this memory" (host.present-memory) -----

  /**
   * Show the exact memory version the host asks for, if nothing stands in the way. Resolves to
   * {requestId, status} ("selected", "already-visible" or "unavailable"), or null when the request
   * cannot be answered at all. The view measures the highlighted card and then calls
   * endPresentation(requestId) before it replies.
   */
  async present(request, { visible = true } = {}) {
    const s = this.state;
    const requestId = typeof request?.requestId === "string" ? request.requestId.toLowerCase() : "";
    if (!UUID.test(requestId)) return null;
    const unavailable = (textValue) => {
      if (textValue) s.outcome = { tone: "warn", text: textValue };
      this.emit();
      return { requestId, status: "unavailable" };
    };
    const { id: memoryId, version } = request;
    const expires = Date.parse(String(request.expiresAt ?? ""));
    if (!validId(memoryId) || !Number.isSafeInteger(version) || version < 1 || !Number.isFinite(expires)) {
      return unavailable("SORA asked to show a memory, but the request was not usable. Nothing was selected.");
    }
    if (expires <= this.now()) return unavailable();
    if (s.presenting) return unavailable();
    if (s.draft || this.busy) {
      return unavailable("SORA asked to show a memory while you were busy here, so nothing was changed.");
    }
    const already = visible && s.selected === memoryId && s.detailCurrent && !s.inspecting
      && s.detail?.item.id === memoryId && s.detail.item.version === version;
    this.clearHighlight();
    s.presenting = true;
    this.activePresentation = requestId;
    this.emit();
    const userSeq = this.seq.user;
    try {
      const data = await bounded(this.api.memory(memoryId), expires - this.now(), this.timers);
      const value = parseDetail(data, memoryId, s.epoch);
      if (this.seq.user !== userSeq || s.draft || expires <= this.now()) return unavailable();
      if (value.item.version !== version) {
        return unavailable(`SORA asked to show version ${version} of a memory, but Core now has version `
          + `${value.item.version}. Nothing was selected.`);
      }
      this.adopt(value.epoch);
      this.seq.detail += 1;
      Object.assign(s, { selected: memoryId, detail: value, detailCurrent: true, inspecting: false });
      s.highlight = { requestId, id: memoryId, version, epoch: value.epoch, expiresAt: expires, confirmed: false };
      s.outcome = { tone: "accent", text: "SORA asked to show you this memory." };
      return { requestId, status: already ? "already-visible" : "selected" };
    } catch (error) {
      if (error instanceof CoreChangedError) void this.coreChanged();
      return unavailable(`SORA asked to show a memory that is not available, so nothing else was selected. ${message(error)}`);
    } finally {
      this.emit();
    }
  }

  /** The view could not place the highlight on screen: take it back. */
  dropHighlight(requestId) {
    if (this.state.highlight?.requestId !== requestId) return false;
    this.clearHighlight();
    this.state.outcome = null;
    this.emit();
    return true;
  }

  endPresentation(requestId) {
    if (this.activePresentation !== requestId) return false;
    this.activePresentation = null;
    this.state.presenting = false;
    this.emit();
    return true;
  }

  /** The host's word on whether Core accepted what the page reported (classic SetPresentationOutcome). */
  presentationOutcome(outcome) {
    const s = this.state;
    const requestId = typeof outcome?.requestId === "string" ? outcome.requestId.toLowerCase() : "";
    if (!s.highlight || s.highlight.requestId !== requestId || typeof outcome.confirmed !== "boolean") return false;
    if (outcome.confirmed) {
      s.highlight.confirmed = true;
      s.outcome = { tone: "accent", text: "SORA highlighted this memory." };
    } else {
      this.clearHighlight();
      s.pageCurrent = false;
      s.detailCurrent = false;
      s.outcome = { tone: "warn", text: "SORA's request to show this memory was not confirmed, so the "
        + "highlight was removed. Nothing else was selected; inspect the memory again before changing it." };
    }
    this.emit();
    return true;
  }

  expireHighlight() {
    const h = this.state.highlight;
    if (!h || this.now() < h.expiresAt) return false;
    this.clearHighlight();
    this.emit();
    return true;
  }

  /** The owner scrolled the inspector away from where the highlight was reported. */
  userScrolled() {
    if (!this.state.highlight) return false;
    this.clearHighlight();
    this.emit();
    return true;
  }

  clearHighlight() {
    if (!this.state.highlight) return false;
    this.state.highlight = null;
    this.onHighlightCleared();
    return true;
  }

  // ----- start -----

  async start({ wanted = null } = {}) {
    await this.checkIdentity();
    if (!this.state.page && !this.state.reading) await this.readPage({ user: false });
    if (wanted) await this.select(wanted);
    else if (this.state.inspecting) await this.settled();
  }

  /** Resolves once no exact read is in flight (start-up and tests). */
  async settled() {
    while (this.state.inspecting || this.state.reading) await new Promise((done) => this.timers.setTimeout(done, 5));
  }
}
