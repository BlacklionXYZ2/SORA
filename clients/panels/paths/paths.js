import { CoreApi } from "../shared/api.js";
import { hosted, onHostMessage, send as sendToHost } from "../shared/bridge.js";
import { icon } from "../shared/icons.js";
import { setUpWindow } from "../shared/window.js";
import {
  EVENT_COLUMNS, LEASE_COLUMNS, MAX_EVENTS, PathsSession, eventRows, leaseRows, nextSort, sortRows,
} from "./paths-model.js";

const api = new CoreApi();
const els = {
  refresh: document.getElementById("refresh"),
  recheck: document.getElementById("recheck"),
  readLabel: document.getElementById("read-label"),
  confirmSlot: document.getElementById("confirm-slot"),
  banner: document.getElementById("banner"),
  notice: document.getElementById("notice"),
  reservationsBody: document.getElementById("reservations-body"),
  reservationsCount: document.getElementById("reservations-count"),
  reservationsStale: document.getElementById("reservations-stale"),
  evidenceBody: document.getElementById("evidence-body"),
  evidenceCount: document.getElementById("evidence-count"),
  evidenceStale: document.getElementById("evidence-stale"),
};
const view = { leaseSort: null, eventSort: null };
let drawn = {};
let reportedBusy = false;
let toastTimer = 0;

setUpWindow();
els.refresh.innerHTML = `${icon("retry")}<span>Refresh</span>`;

// ---------- small DOM helpers ----------

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "html") node.innerHTML = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (key in node && key !== "list") node[key] = value;
    else node.setAttribute(key, value === true ? "" : value);
  }
  node.append(...children.filter((child) => child !== null && child !== undefined && child !== false));
  return node;
}

function toast(text) {
  document.querySelector(".toast")?.remove();
  const note = el("div", { class: "toast", role: "status" }, text);
  document.body.append(note);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => note.remove(), 4500);
}

const session = new PathsSession(api, { onChange: render });

// Registered before any await: the host sends host.core as soon as the page is ready.
onHostMessage((data) => {
  if (data.type === "host.core") session.hostCore(data.canUseCore);
  // host.select has nothing to select here.
});

// Escape inside the confirmation cancels it rather than hiding the window (window.js listens later).
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && session.confirming) {
    event.preventDefault();
    session.cancelRecheck();
    els.recheck.focus();
  }
}, true);

// ---------- top: actions, read time, confirmation, banner ----------

function renderTop() {
  const blocked = session.recheckBlocked();
  els.refresh.disabled = session.working;
  els.recheck.disabled = Boolean(blocked) || session.confirming;
  els.recheck.title = blocked
    || "Ask SORA's Core to check, from the evidence it already has, which writers have stopped";
  els.readLabel.textContent = session.readLabel();
  els.readLabel.classList.toggle("stale", session.stale && !session.working);

  if (!session.confirming) {
    els.confirmSlot.replaceChildren();
  } else if (!els.confirmSlot.firstChild) {
    const keep = el("button", { class: "btn", type: "button",
      onclick: () => { session.cancelRecheck(); els.recheck.focus(); } }, "Not now");
    els.confirmSlot.replaceChildren(el("div", { class: "confirm", role: "group", "aria-label": "Confirm the recheck" },
      el("span", {}, "Recheck stopped writers using the evidence SORA's Core already has? If it can't "
        + "confirm a writer stopped, that project stays reserved. This doesn't force anything open or "
        + "cancel any task."),
      keep,
      el("button", { class: "btn primary", type: "button", onclick: recheck }, "Recheck")));
    keep.focus();
  }

  const lines = session.messages();
  els.banner.hidden = lines.length === 0;
  els.banner.classList.toggle("info", lines.length > 0 && lines.every((line) => line.tone === "info"));
  els.banner.replaceChildren();
  if (lines.length) {
    els.banner.insertAdjacentHTML("afterbegin", icon("alert"));
    els.banner.append(el("div", { class: "banner-lines" }, ...lines.map((line) => el("p", {}, line.text))));
  }
}

// ---------- tables ----------

function pill(words) {
  return el("span", { class: `state ${words.tone}`, title: words.meaning || false }, words.label);
}

// Core's exact value, kept visible under the plain words.
function token(words) {
  return words.known ? el("span", { class: "token mono", title: "Core's own value" }, words.token) : null;
}

const missing = () => el("span", { class: "missing" }, "Not reported");
const mono = (value) => (value ? el("span", { class: "mono" }, value) : missing());

function openTask(link) {
  sendToHost("panel.open", link);
  if (!hosted) toast("Activity opens in SORA's app.");
}

const LEASE_CELLS = {
  folder: (row) => [row.folder ? el("span", { class: "path" }, row.folder) : missing()],
  state: (row) => [pill(row.state), token(row.state)],
  task: (row) => [row.link
    ? el("button", { class: "link mono", type: "button", title: "Open this task in Activity",
      onclick: () => openTask(row.link) }, row.taskId)
    : mono(row.taskId)],
  run: (row) => [mono(row.runId)],
  reservedAt: (row) => [el("span", { title: row.reservedAt.exact || false }, row.reservedAt.text)],
};

const EVENT_CELLS = {
  time: (row) => [el("span", { title: row.time.exact || false }, row.time.text)],
  path: (row) => [row.path ? el("span", { class: "path" }, row.path) : missing()],
  operation: (row) => [el("span", { title: row.operation.meaning || false }, row.operation.label), token(row.operation)],
  state: (row) => [pill(row.state), token(row.state)],
  source: (row) => [el("span", { title: row.source.meaning || false }, row.source.label), token(row.source)],
  run: (row) => [mono(row.runId)],
};

function table({ name, caption, columns, cells, rows, sort, onSort }) {
  const head = el("tr", {}, ...columns.map((column) => {
    const active = sort?.key === column.key;
    return el("th", { scope: "col", "aria-sort": active ? (sort.dir === "asc" ? "ascending" : "descending") : false },
      el("button", { class: "sort", type: "button", "data-key": column.key,
        title: `Sort by ${column.label.toLowerCase()}`, onclick: () => onSort(column.key) },
      column.label,
      active ? el("span", { class: "arrow", "aria-hidden": "true" }, sort.dir === "asc" ? "▲" : "▼") : null));
  }));
  const body = rows.map((row) => el("tr", {}, ...columns.map((column) =>
    el("td", { "data-label": column.label }, el("div", { class: "cell" }, ...cells[column.key](row))))));
  return el("table", { class: `data fixed stack ${name}` },
    el("caption", { class: "visually-hidden" }, caption),
    el("colgroup", {}, ...columns.map((column) => el("col", { class: `col-${column.key}` }))),
    el("thead", {}, head),
    el("tbody", {}, ...body));
}

function placeholder() {
  return el("p", { class: "empty-table" }, session.phase === "reading" || session.phase === "rechecking"
    ? "Reading…" : "Not read yet.");
}

function resort(which, key) {
  view[which] = nextSort(view[which], key);
  render();
  document.querySelector(`.${which === "leaseSort" ? "leases" : "events"} th button[data-key="${key}"]`)?.focus();
}

function renderTables() {
  const readState = session.everRead ? "read" : session.phase;
  if (drawn.leases === session.leases && drawn.events === session.events && drawn.readState === readState
      && drawn.leaseSort === view.leaseSort && drawn.eventSort === view.eventSort) return;
  drawn = { leases: session.leases, events: session.events, readState,
    leaseSort: view.leaseSort, eventSort: view.eventSort };

  const leases = sortRows(leaseRows(session.leases), LEASE_COLUMNS, view.leaseSort);
  els.reservationsCount.hidden = !session.everRead;
  els.reservationsCount.textContent = `${leases.length} reserved`;
  els.reservationsBody.replaceChildren(!session.everRead ? placeholder()
    : !leases.length ? el("p", { class: "empty-table" }, "No projects are reserved for writing right now.")
      : table({ name: "leases", caption: "Project writer reservations", columns: LEASE_COLUMNS,
        cells: LEASE_CELLS, rows: leases, sort: view.leaseSort, onSort: (key) => resort("leaseSort", key) }));

  const events = sortRows(eventRows(session.events), EVENT_COLUMNS, view.eventSort);
  els.evidenceCount.hidden = !session.everRead;
  els.evidenceCount.textContent = events.length >= MAX_EVENTS ? `Newest ${MAX_EVENTS} shown`
    : `${events.length} record${events.length === 1 ? "" : "s"}`;
  els.evidenceBody.replaceChildren(!session.everRead ? placeholder()
    : !events.length ? el("p", { class: "empty-table" }, "No path evidence has been recorded yet.")
      : table({ name: "events", caption: "Project path evidence", columns: EVENT_COLUMNS,
        cells: EVENT_CELLS, rows: events, sort: view.eventSort, onSort: (key) => resort("eventSort", key) }));
}

// ---------- everything ----------

function render() {
  renderTop();
  els.notice.hidden = !session.notice;
  els.notice.replaceChildren(el("b", {}, "Core's note: "), session.notice);
  renderTables();
  els.reservationsStale.hidden = els.evidenceStale.hidden = !session.stale;
  // Quit waits for a recheck in flight (a read changes nothing, so it does not hold Quit).
  if (session.busy !== reportedBusy) {
    reportedBusy = session.busy;
    sendToHost("panel.busy", { busy: reportedBusy });
  }
}

async function recheck() {
  const summary = await session.confirmRecheck();
  if (summary) toast(summary);
}

els.refresh.addEventListener("click", () => session.refresh());
els.recheck.addEventListener("click", () => session.askRecheck());

// Read once on opening, as the classic window did; after that only Refresh reads. No polling.
render();
await session.refresh();
