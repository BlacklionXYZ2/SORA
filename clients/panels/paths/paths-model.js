// Project paths state with no DOM: which project folders are reserved for an agent's writing, and
// the recent write evidence, exactly as Core reports them (GET /api/v1/paths). Core's tokens are
// put into plain words but always kept alongside, and nothing is inferred beyond them. A recheck
// (POST /api/v1/paths/reconcile) is sent only after an inline confirmation, never retried by
// itself, and a reply that spans a Core restart is set aside rather than shown as current.

import { CoreError, ITEM_ID } from "../shared/api.js";

/** Core returns at most this many evidence records, newest first. */
export const MAX_EVENTS = 250;

const text = (value) => (typeof value === "string" ? value : "");

// ---------- words for Core's tokens (docs/runbooks/SORA_AGENT_MODELS.md, project_paths.py) ----------

const OPERATIONS = {
  "write.reserve": ["Reservation request", "SORA tried to reserve this folder for a run's writing."],
  "write.release": ["Release check", "SORA checked whether the run's writer had stopped."],
  read: ["Read", "The agent said it read this."],
  write: ["Write", "The agent said it wrote this."],
  "diff.incomplete": ["File check incomplete",
    "SORA's before-and-after file check could not cover the whole folder, so changes may be missing."],
  "file.created": ["File created", "The file was not there before the run and was there after."],
  "file.discovered": ["File found afterwards",
    "The file was there after the run; the check before was incomplete, so it may not be new."],
  "file.removed": ["File removed", "The file was there before the run and not after."],
  "file.unobserved": ["File not seen afterwards",
    "The file was there before the run; the check after was incomplete, so it may still exist."],
  "file.changed": ["File changed", "The file's size or modified time differed after the run."],
};

const STATUSES = {
  reserved: ["Reserved", "off", "The folder was reserved for this run's writing."],
  conflict: ["Refused (overlap)", "bad",
    "Not reserved: the folder overlaps a project already reserved for another run."],
  stopped: ["Writer stopped", "ok",
    "SORA found the writer had stopped (or never started) and released the project."],
  uncertain: ["Not sure it stopped", "bad",
    "SORA could not confirm the writer stopped, so the project stays reserved."],
  reported: ["Agent reported", "off", "The agent reported this. SORA did not check it."],
  observed: ["Seen by SORA", "off", "SORA recorded this itself, within the limits of its check."],
};

// A held reservation reads differently from an event in the history.
const LEASE_STATUSES = {
  reserved: ["Reserved", "active",
    "Reserved for this run's writing. SORA won't reserve this folder, or one inside or around it, for another run."],
  uncertain: ["Not sure it stopped", "bad",
    "SORA could not confirm the writer stopped, so the project stays reserved until it can."],
};

const SOURCES = {
  declared_root: ["Chosen project folder", "The project folder chosen for the task (its declared scope)."],
  core_observed: ["SORA's own record",
    "Recorded by SORA's Core itself when it reserved, refused or released a project for a run."],
  provider_reported: ["Agent's own account", "What the agent said it did. SORA did not check it."],
  filesystem_diff: ["File comparison",
    "SORA compared file sizes and modified times before and after. It does not show who made a change."],
};

// Each entry is [label, meaning] or [label, tone, meaning].
function words(table, token, fallbackTone = "off") {
  const entry = Object.hasOwn(table, token) ? table[token] : null;
  if (!entry) {
    // An unfamiliar value is shown as Core wrote it, not guessed at.
    return { label: token || "Not reported", token, tone: fallbackTone, meaning: "", known: false };
  }
  const [label, tone, meaning] = entry.length === 3 ? entry : [entry[0], fallbackTone, entry[1]];
  return { label, token, tone, meaning, known: true };
}

/** What happened, in plain words, with Core's own token kept. */
export function operationWords(operation) { return words(OPERATIONS, text(operation)); }
/** An evidence record's state, in plain words, with a tone for its pill. */
export function statusWords(status) { return words(STATUSES, text(status)); }
/** A reservation's state, in plain words. */
export function leaseStatusWords(status) { return words(LEASE_STATUSES, text(status), "bad"); }
/** How SORA knows (the source label describes coverage, not verified success). */
export function sourceWords(source) { return words(SOURCES, text(source)); }

// ---------- time ----------

const TIME_FORMAT = { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" };

/** A local, readable time, with Core's exact value kept for the tooltip. Never invented. */
export function timeLabel(iso) {
  const exact = text(iso);
  if (!exact) return { text: "Not reported", exact: "" };
  const date = new Date(exact);
  if (Number.isNaN(date.getTime())) return { text: exact, exact };
  return { text: date.toLocaleString("en-GB", TIME_FORMAT), exact };
}

// ---------- Core's projection ----------

/**
 * Only the fields this page shows, as strings. Returns null when the reply is not path evidence,
 * so a malformed answer is a failed read (the old rows stay) rather than an empty table.
 */
export function normaliseProjection(data) {
  if (!data || typeof data !== "object" || !Array.isArray(data.leases) || !Array.isArray(data.events)) {
    return null;
  }
  const leases = data.leases.filter((item) => item && typeof item === "object").map((item) => ({
    run_id: text(item.run_id), task_id: text(item.task_id), display_root: text(item.display_root),
    status: text(item.status), acquired_at: text(item.acquired_at),
  }));
  const events = data.events.filter((item) => item && typeof item === "object").slice(0, MAX_EVENTS)
    .map((item) => ({
      event_id: text(item.event_id), run_id: text(item.run_id), path: text(item.path),
      operation: text(item.operation), status: text(item.status), source: text(item.source),
      occurred_at: text(item.occurred_at),
    }));
  return { leases, events, notice: text(data.notice) };
}

/** The exact task to open in Activity for a reservation, or null when the ID is not one. */
export function taskLink(taskId) {
  return typeof taskId === "string" && ITEM_ID.test(taskId) ? { panel: "activity", select: taskId } : null;
}

const instant = (iso) => {
  const time = Date.parse(iso);
  return Number.isNaN(time) ? -Infinity : time;
};

/** Reservation rows, newest first (Core's list has no order of its own). */
export function leaseRows(leases) {
  return [...(Array.isArray(leases) ? leases : [])]
    .map((lease, index) => ({ lease, index }))
    .sort((a, b) => instant(b.lease.acquired_at) - instant(a.lease.acquired_at) || a.index - b.index)
    .map(({ lease, index }) => ({
      key: lease.run_id || `lease-${index}`,
      folder: lease.display_root,
      state: leaseStatusWords(lease.status),
      taskId: lease.task_id,
      link: taskLink(lease.task_id),
      runId: lease.run_id,
      reservedAt: timeLabel(lease.acquired_at),
    }));
}

/** Evidence rows in Core's order (newest first). */
export function eventRows(events) {
  return (Array.isArray(events) ? events : []).slice(0, MAX_EVENTS).map((event, index) => ({
    key: event.event_id || `event-${index}`,
    time: timeLabel(event.occurred_at),
    path: event.path,
    operation: operationWords(event.operation),
    state: statusWords(event.status),
    source: sourceWords(event.source),
    runId: event.run_id,
  }));
}

// ---------- columns and sorting ----------

export const LEASE_COLUMNS = Object.freeze([
  { key: "folder", label: "Project folder", value: (row) => row.folder },
  { key: "state", label: "State", value: (row) => row.state.label },
  { key: "task", label: "Task", value: (row) => row.taskId },
  { key: "run", label: "Run", value: (row) => row.runId },
  { key: "reservedAt", label: "Reserved at", value: (row) => instant(row.reservedAt.exact) },
]);

export const EVENT_COLUMNS = Object.freeze([
  { key: "time", label: "Time", value: (row) => instant(row.time.exact) },
  { key: "path", label: "Path", value: (row) => row.path },
  { key: "operation", label: "What happened", value: (row) => row.operation.label },
  { key: "state", label: "State", value: (row) => row.state.label },
  { key: "source", label: "How SORA knows", value: (row) => row.source.label },
  { key: "run", label: "Run", value: (row) => row.runId },
]);

/** Next sort for a header click: a new column sorts ascending, the same one flips. */
export function nextSort(current, key) {
  if (current?.key === key) return { key, dir: current.dir === "asc" ? "desc" : "asc" };
  return { key, dir: "asc" };
}

/** Rows sorted by one column (stable); without a sort, the rows keep their order. */
export function sortRows(rows, columns, sort) {
  const column = sort && columns.find((item) => item.key === sort.key);
  if (!column) return rows;
  const sign = sort.dir === "desc" ? -1 : 1;
  return rows.map((row, index) => ({ row, index })).sort((a, b) => {
    const left = column.value(a.row);
    const right = column.value(b.row);
    const order = typeof left === "number" && typeof right === "number"
      ? (left === right ? 0 : left < right ? -1 : 1)
      : String(left).localeCompare(String(right), "en-GB", { numeric: true, sensitivity: "base" });
    return order * sign || a.index - b.index;
  }).map(({ row }) => row);
}

// ---------- failures, worded separately for a read and a recheck ----------

/** Core's fence for a request that spans a Core restart. */
export class CoreChanged extends Error {
  constructor() { super("SORA's Core changed while this was running."); this.name = "CoreChanged"; }
}

/** Core answered, but not with path evidence. */
export class NotPathEvidence extends Error {
  constructor() { super("Core's reply did not look like path evidence."); this.name = "NotPathEvidence"; }
}

const detail = (error) => (error instanceof CoreError || error instanceof Error
  ? error.message : String(error ?? "Unknown error"));
const sentence = (value) => (/[.!?…]$/.test(value) ? value : `${value}.`);

/** Why a read failed. The rows already on screen stay. */
export function readFailure(error) {
  if (error instanceof CoreChanged) {
    return "SORA's Core changed while reading, so that answer was set aside. Choose Refresh to read again.";
  }
  if (error instanceof CoreError && error.code === "RUNTIME_CHANGED") {
    return "SORA's Core restarted and the app has not caught up yet. Choose Refresh again in a moment.";
  }
  return `Couldn't read path evidence: ${sentence(detail(error))}`;
}

// Refusals Core or the host gives before the recheck starts, so nothing was rechecked.
const REFUSED_BEFORE_START = new Set(["RUNTIME_CHANGED", "RUNTIME_SHUTTING_DOWN", "UNAUTHORIZED",
  "FORBIDDEN", "PANEL_ROUTE_REFUSED", "PANEL_BODY_TOO_LARGE", "NOT_FOUND", "METHOD_NOT_ALLOWED"]);

/**
 * Why a recheck failed, and whether Core certainly did nothing (refused) or the outcome is unknown.
 * Either way SORA never sends it again by itself.
 */
export function recheckFailure(error) {
  if (error instanceof CoreError && REFUSED_BEFORE_START.has(error.code)) {
    const why = error.code === "RUNTIME_CHANGED"
      ? "SORA's Core restarted and the app has not caught up yet"
      : error.code === "RUNTIME_SHUTTING_DOWN" ? "SORA's Core is shutting down and accepts no changes"
        : detail(error).replace(/[.!?…]$/, "");
    return { refused: true, text: `The recheck was refused: ${why}. Nothing was rechecked.` };
  }
  const why = error instanceof CoreChanged ? "SORA's Core changed while it ran"
    : error instanceof NotPathEvidence ? "Core answered, but not with path evidence"
      : detail(error).replace(/[.!?…]$/, "");
  return {
    refused: false,
    text: `The recheck wasn't confirmed: ${why}. Core may have settled some reservations before this `
      + "failed. SORA won't retry by itself; choose Refresh to see where things stand.",
  };
}

/** A short, honest summary after a recheck, comparing Core's reservations before and after. */
export function recheckSummary(beforeRunIds, afterLeases, { hadRead }) {
  if (!hadRead) return "Recheck finished. Showing Core's current reservations.";
  const after = new Set(afterLeases.map((lease) => lease.run_id));
  const released = [...beforeRunIds].filter((runId) => !after.has(runId)).length;
  if (released) {
    return `Recheck finished. ${released} project${released === 1 ? " is" : "s are"} no longer reserved.`;
  }
  if (!beforeRunIds.size) return "Recheck finished. No project was reserved.";
  return "Recheck finished. No reservation was released: a project stays reserved until SORA can "
    + "confirm its writer stopped.";
}

// ---------- the panel's session ----------

export const CORE_BLOCKED = "SORA's app isn't connected to Core right now, or is starting or stopping "
  + "it, so a recheck can't be sent.";

/**
 * Reads, the confirmed recheck and what the page should say about them. The view renders from
 * this and calls refresh(), askRecheck(), cancelRecheck(), confirmRecheck() and hostCore().
 */
export class PathsSession {
  constructor(api, { onChange = () => {}, now = () => new Date() } = {}) {
    this.api = api;
    this.onChange = onChange;
    this.now = now;
    this.leases = [];
    this.events = [];
    this.notice = "";
    this.readAt = null;        // when this page last read good evidence (the page's own clock)
    this.instanceId = null;    // the Core instance that answered it, when known
    this.phase = "idle";       // "idle" | "reading" | "rechecking"
    this.confirming = false;   // the inline recheck confirmation is showing
    this.canUseCore = true;    // host.core; a browser preview never sends it
    this.stale = false;        // the rows on screen may be out of date
    this.problem = null;       // { kind: "read" | "recheck", text, refused? }
    this.info = "";            // a neutral note, such as "Core reconnected…"
    this.seq = 0;              // only the newest request may change what is shown
  }

  get everRead() { return this.readAt !== null; }
  get working() { return this.phase !== "idle"; }
  /** Work Quit must wait for: only a recheck in flight (a read changes nothing). */
  get busy() { return this.phase === "rechecking"; }

  /** Why Recheck can't be pressed now, or "" when it can. */
  recheckBlocked() {
    if (!this.canUseCore) return CORE_BLOCKED;
    if (this.working) return "Wait for the current read to finish.";
    return "";
  }

  changed() { this.onChange(this); }

  /** Read Core's evidence. Does nothing while a read or recheck is in flight. */
  async refresh() {
    if (this.working) return false;
    this.confirming = false;
    const seq = ++this.seq;
    this.phase = "reading";
    this.changed();
    try {
      const { projection, instanceId } = await this.#fenced(() => this.api.paths());
      if (seq !== this.seq) return false;
      this.#accept(projection, instanceId);
      return true;
    } catch (error) {
      if (seq !== this.seq) return false;
      this.problem = { kind: "read", text: readFailure(error) };
      this.stale = this.everRead;
      return false;
    } finally {
      if (seq === this.seq) {
        this.phase = "idle";
        this.changed();
      }
    }
  }

  /** Show the inline confirmation. Nothing is sent yet. */
  askRecheck() {
    if (this.recheckBlocked()) return false;
    this.confirming = true;
    this.changed();
    return true;
  }

  cancelRecheck() {
    if (!this.confirming) return false;
    this.confirming = false;
    this.changed();
    return true;
  }

  /**
   * Send the recheck once, only from the confirmation. Resolves to a summary for a toast, or ""
   * when it was not sent or did not succeed. Never retried automatically.
   */
  async confirmRecheck() {
    if (!this.confirming) return "";
    this.confirming = false;
    if (this.recheckBlocked()) {
      this.changed();
      return "";
    }
    const seq = ++this.seq;
    const hadRead = this.everRead;
    const before = new Set(this.leases.map((lease) => lease.run_id));
    this.phase = "rechecking";
    this.problem = null;
    this.info = "";
    this.changed();
    try {
      const { projection, instanceId } = await this.#fenced(() => this.api.reconcilePaths());
      if (seq !== this.seq) return "";
      this.#accept(projection, instanceId);
      return recheckSummary(before, projection.leases, { hadRead });
    } catch (error) {
      if (seq !== this.seq) return "";
      const failure = recheckFailure(error);
      this.problem = { kind: "recheck", text: failure.text, refused: failure.refused };
      if (!failure.refused) this.stale = this.everRead;
      return "";
    } finally {
      if (seq === this.seq) {
        this.phase = "idle";
        this.changed();
      }
    }
  }

  /** The host's view of Core (host.core). Mutations wait while it is false; reads may go on. */
  hostCore(canUseCore) {
    if (typeof canUseCore !== "boolean" || canUseCore === this.canUseCore) return;
    this.canUseCore = canUseCore;
    if (!canUseCore) {
      // A confirmation given for a Core that has gone is not carried over to the next one.
      this.confirming = false;
      this.info = "";
    } else {
      this.info = this.everRead
        ? "Core reconnected. The rows below were read before, so choose Refresh before relying on them."
        : "Core connected. Choose Refresh to read path evidence.";
    }
    if (this.everRead) this.stale = true;
    this.changed();
  }

  /** Lines for the page's banner: a failure, the host's state, then a neutral note. */
  messages() {
    const lines = [];
    if (this.problem) lines.push({ tone: "warn", text: this.problem.text });
    if (!this.canUseCore) {
      lines.push({ tone: "warn", text: this.everRead
        ? `${CORE_BLOCKED} The rows below are from the last read and may be out of date.`
        : CORE_BLOCKED });
    } else if (this.info) {
      lines.push({ tone: "info", text: this.info });
    }
    return lines;
  }

  /** "Read at 09:58:01", plus a stale warning when the rows may be out of date. */
  readLabel() {
    if (this.phase === "reading") return "Reading path evidence…";
    if (this.phase === "rechecking") return "Rechecking stopped writers…";
    if (!this.everRead) return "Not read yet.";
    const at = this.readAt.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    return this.stale ? `Last read at ${at}. May be out of date.` : `Read at ${at}.`;
  }

  #accept(projection, instanceId) {
    this.leases = projection.leases;
    this.events = projection.events;
    this.notice = projection.notice;
    this.instanceId = instanceId;
    this.readAt = this.now();
    this.stale = false;
    this.problem = null;
    this.info = "";
  }

  // Core's instance before and after the call: an answer that spans a restart is not current.
  async #fenced(call) {
    const before = await this.#instance();
    const data = await call();
    const after = await this.#instance();
    if (before && after && before !== after) throw new CoreChanged();
    const projection = normaliseProjection(data);
    if (!projection) throw new NotPathEvidence();
    return { projection, instanceId: after || before || null };
  }

  async #instance() {
    try {
      const identity = await this.api.identity();
      return typeof identity?.instance_id === "string" && identity.instance_id ? identity.instance_id : null;
    } catch {
      return null;   // the paths call itself reports any real failure
    }
  }
}
