import { CoreApi } from "../shared/api.js";
import { onHostMessage, send as sendToHost } from "../shared/bridge.js";
import { icon } from "../shared/icons.js";
import { setUpWindow } from "../shared/window.js";
import {
  DEFAULT_QUERY, ErrorDetails, FORGET_MEANING, MAX_CONTENT, MemoryBrowser, PROJECTS, STATES,
  codePoints, contentError, inspectionFacts, pageStatus, sameQuery, stateLabel, when,
} from "./memory-model.js";

const IDENTITY_MS = 5000;
const errors = new ErrorDetails(globalThis.fetch.bind(globalThis));
const memory = new MemoryBrowser({ api: new CoreApi({ fetchImpl: errors.fetch }), errors });
const s = memory.state;
const $ = (id) => document.getElementById(id);
const els = {
  body: $("body"), modeOverview: $("mode-overview"), modeSearch: $("mode-search"), modeGraph: $("mode-graph"),
  filters: $("filters"), q: $("q"), state: $("state"), project: $("project"), scope: $("scope"),
  search: $("search"), exact: $("exact"), inspectId: $("inspect-id"), listTitle: $("list-title"),
  refresh: $("refresh"), list: $("list"), listNote: $("list-note"), previous: $("previous"),
  next: $("next"), pageStatus: $("page-status"), about: $("about"), aboutNote: $("about-note"),
  inspector: $("inspector"), main: $("inspector-main"), draft: $("draft"),
};
let toastTimer = 0;
let identityTimer = 0;
let expiryTimer = 0;
let expiryFor = null;
let reportedDirty = false;
let reportedBusy = false;
let shownConfirm = null;
let shownOutcome = null;
let highlightTop = null;   // where the highlighted card was when its place was reported
let editor = null;

setUpWindow();

// Host messages first: the host sends host.select and presentations as soon as panel.ready arrives.
memory.onChange = () => render();
memory.onHighlightCleared = () => { highlightTop = null; sendToHost("memory.highlight-cleared"); };
onHostMessage((data) => {
  if (data.type === "host.select" && typeof data.id === "string") void memory.select(data.id);
  else if (data.type === "host.core") memory.setCanUseCore(data.canUseCore);
  else if (data.type === "host.present-memory") void present(data);
  else if (data.type === "host.presentation-outcome") memory.presentationOutcome(data);
});

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

/** Keeps keyboard focus on the same control when a region is rebuilt. */
function focusedKey(container) {
  const active = document.activeElement;
  return active && container.contains(active) ? active.dataset?.key ?? null : null;
}

function restoreFocus(container, key) {
  if (!key) return;
  const node = container.querySelector(`[data-key="${CSS.escape(key)}"]`);
  if (node && !node.disabled && document.activeElement !== node) node.focus({ preventScroll: true });
}

function focusOn(container, key) {
  const node = container.querySelector(`[data-key="${CSS.escape(key)}"]`);
  if (node && !node.disabled) node.focus({ preventScroll: true });
}

const narrow = () => globalThis.matchMedia?.("(max-width: 860px)").matches ?? false;
/** The element that scrolls the inspector: its own pane, or the whole body when stacked. */
const scroller = () => (narrow() ? els.body : els.inspector);

/** Scrolls the inspector just enough to show a node (never while SORA's highlight is showing). */
function reveal(node) {
  if (!node || s.highlight) return;
  const box = scroller().getBoundingClientRect();
  const r = node.getBoundingClientRect();
  if (r.bottom > box.bottom) scroller().scrollTop += Math.min(r.bottom - box.bottom + 12, r.top - box.top - 12);
  else if (r.top < box.top) scroller().scrollTop -= box.top - r.top + 12;
}

// ---------- static parts ----------

els.modeOverview.innerHTML = icon("memory") + "<span>Overview</span>";
els.modeSearch.innerHTML = icon("search") + "<span>Search</span>";
els.modeGraph.innerHTML = icon("models") + "<span>Graph</span><span class=\"soon\">not yet</span>";
els.search.innerHTML = icon("search") + "<span>Search</span>";
els.refresh.innerHTML = icon("retry", "Read again");
els.state.replaceChildren(...STATES.map((item) => el("option", { value: item.value }, item.label)));
els.project.replaceChildren(...PROJECTS.map((item) => el("option", { value: item.value }, item.label)));

// ---------- the list side ----------

function renderModes(a) {
  els.modeOverview.setAttribute("aria-selected", String(s.mode === "overview"));
  els.modeSearch.setAttribute("aria-selected", String(s.mode === "search"));
  els.modeGraph.setAttribute("aria-selected", "false");
  els.modeOverview.disabled = !a.browse;
  els.modeOverview.title = a.browse ? "SORA's active memories" : "Finish what you are doing first";
  els.filters.hidden = s.mode !== "search";
  for (const name of ["q", "state", "project", "scope"]) {
    const input = els[name];
    input.disabled = !a.browse;
    if (input.value !== s.typed[name]) input.value = s.typed[name];
  }
  els.exact.disabled = !a.browse;
  els.search.disabled = !a.browse;
  els.inspectId.disabled = !a.browse || !els.exact.value.trim();
  const applied = s.applied ?? DEFAULT_QUERY;
  els.listTitle.textContent = sameQuery(applied, DEFAULT_QUERY) ? "Active memories" : "Matching memories";
}

function rowMeta(m) {
  const status = stateLabel(m.state);
  return el("span", { class: "meta" },
    el("span", { class: `state ${status.tone}` }, status.label),
    el("span", {}, `Version ${m.version}`),
    m.scope ? el("span", { class: "tag" }, m.scope) : null,
    m.project === null ? el("span", { class: "tag" }, "Global") : null,
    m.validUntil ? el("span", { title: m.validUntil },
      `${m.state === "expired" ? "Expired" : "Valid until"} ${when(m.validUntil)}`) : null);
}

function renderList(a) {
  const page = s.page;
  const scroll = els.list.scrollTop;
  const key = focusedKey(els.list);
  if (!page || !page.items.length) {
    const words = s.reading ? "Reading memories…" : page ? "" : s.listNote ? "" : "No memories read yet.";
    els.list.replaceChildren(...(words ? [el("li", { class: "empty-detail" }, words)] : []));
  } else {
    els.list.replaceChildren(...page.items.map((m) => el("li", {}, el("button", {
      class: "memory-item", type: "button", "data-key": m.id, disabled: !a.browse,
      "aria-current": m.id === s.selected ? "true" : false,
      onclick: () => memory.select(m.id),
    },
    el("span", { class: "preview" }, m.preview + (m.contentTruncated ? "…" : "")),
    rowMeta(m)))));
  }
  els.list.classList.toggle("stale", Boolean(page) && !s.pageCurrent);
  els.list.setAttribute("aria-busy", String(s.reading));
  els.list.scrollTop = scroll;
  restoreFocus(els.list, key);
  els.listNote.hidden = !s.listNote?.text;
  els.listNote.className = `list-note ${s.listNote?.tone ?? ""}`;
  els.listNote.textContent = s.listNote?.text ?? "";
}

function renderPager(a) {
  els.previous.disabled = !a.previous;
  els.next.disabled = !a.next;
  els.refresh.disabled = !a.browse;
  els.pageStatus.textContent = pageStatus(s);
  els.about.hidden = !s.page;
  els.aboutNote.textContent = s.page?.note ?? "";
}

function revealSelectedRow() {
  if (!s.selected) return;
  const row = els.list.querySelector(`[data-key="${CSS.escape(s.selected)}"]`);
  if (!row) return;
  const box = els.list.getBoundingClientRect();
  const r = row.getBoundingClientRect();
  if (r.top < box.top) els.list.scrollTop -= box.top - r.top + 4;
  else if (r.bottom > box.bottom) els.list.scrollTop += r.bottom - box.bottom + 4;
}

// ---------- the inspector ----------

function banner(text) {
  return el("div", { class: "banner", role: "status", html: icon("alert") }, el("span", {}, text));
}

function placeholder() {
  return el("div", { class: "placeholder" },
    el("div", { class: "placeholder-art", html: icon("memory") }),
    el("p", {}, "Choose a memory to see everything SORA keeps about it."),
    el("p", { class: "notice" }, "Correcting saves your words as a new memory and keeps the old one as "
      + "replaced. Forgetting removes only that one memory."));
}

function actionNote(detail, a) {
  if (s.draft) return "Finish or discard the draft below before changing anything else.";
  if (!s.canUseCore || !memory.canChange) return "";
  if (!s.detailCurrent && !s.inspecting) return "Inspect it again before changing it.";
  if (!a.correct && a.forget && detail.item.state !== "active") {
    return "Only an active memory can be corrected. It can still be forgotten.";
  }
  return "";
}

function actions(detail, a) {
  const m = detail.item;
  if (s.confirm === "forget") {
    return el("div", { class: "confirm", role: "group", "aria-label": "Forget this memory?" },
      el("span", {}, el("strong", {}, `Forget ${m.id} (version ${m.version})? `), FORGET_MEANING),
      el("button", { class: "btn", type: "button", "data-key": "forget-cancel",
        onclick: () => memory.cancelConfirm() }, "Keep it"),
      el("button", { class: "btn danger", type: "button", "data-key": "forget-confirm",
        onclick: () => memory.confirmForget() }, "Forget"));
  }
  const note = actionNote(detail, a);
  return el("div", { class: "actions" },
    el("div", { class: "buttons" },
      el("button", { class: "btn", type: "button", "data-key": "correct", disabled: !a.correct,
        title: "Write a corrected version of this exact memory", onclick: () => memory.startCorrection() },
      "Correct…"),
      el("button", { class: "btn danger", type: "button", "data-key": "forget", disabled: !a.forget,
        title: "Forget only this exact memory", onclick: () => memory.askForget() }, "Forget…"),
      el("button", { class: "btn quiet", type: "button", "data-key": "reinspect", disabled: !a.browse,
        title: "Read this exact memory again", onclick: () => memory.select(m.id) }, "Inspect again")),
    note ? el("p", { class: "action-note" }, note) : null);
}

function evidence(detail, a) {
  const links = detail.evidence;
  return el("section", { class: "evidence" },
    el("h2", {}, "Evidence", links.length ? el("span", { class: "count" }, String(links.length)) : null),
    links.length
      ? el("ul", {}, ...links.map((link) => el("li", {},
        el("span", { class: "evidence-text" },
          el("span", { class: "evidence-label" }, link.label),
          el("span", { class: "evidence-meta" }, `${link.kind} · `, el("span", { class: "mono" }, link.id))),
        el("button", { class: "btn small", type: "button", "data-key": `open:${link.id}`, disabled: !a.open,
          title: "Ask SORA's Core to open this on the computer it runs on",
          onclick: () => memory.openEvidence(link.id) }, s.opening === link.id ? "Opening…" : "Open"))))
      : el("p", { class: "muted" }, "No registered evidence is linked to this memory."),
    detail.withheld ? el("p", { class: "notice" }, "Some evidence is not shown: private captures, "
      + "unregistered or out-of-scope items, or more than the limit.") : null);
}

function memoryCard(detail, a) {
  const m = detail.item;
  const status = stateLabel(m.state);
  const presented = s.highlight?.id === m.id;
  return el("article", {
    class: `card memory-card${presented ? " highlight presented" : ""}${s.detailCurrent || s.inspecting ? "" : " stale"}`,
    id: "memory-card",
    "aria-label": presented ? `Memory ${m.id}, version ${m.version}, highlighted by SORA` : `Memory ${m.id}`,
  },
  presented ? el("div", { class: "presented-chip", html: `${icon("eye")}<span>SORA is pointing at this memory</span>` }) : null,
  el("div", { class: "card-head" },
    el("span", { class: `state ${status.tone}` }, status.label),
    el("span", { class: "version" }, `Version ${m.version}`),
    s.inspecting ? el("span", { class: "loading" }, "Reading…") : null),
  el("div", { class: "memory-id" }, el("span", { class: "label" }, "ID"), el("span", { class: "mono" }, m.id)),
  !s.detailCurrent && !s.inspecting
    ? el("p", { class: "stale-note" }, "This may be out of date. Inspect it again before relying on it or changing it.")
    : null,
  el("blockquote", { class: "content" }, detail.content),
  el("dl", { class: "facts" }, ...inspectionFacts(detail).flatMap((fact) => [
    el("dt", {}, fact.label), el("dd", { title: fact.title }, fact.value)])),
  m.metadataTruncated ? el("p", { class: "notice" }, "Some long details were shortened in this view.") : null,
  detail.successor ? el("div", { class: "successor" },
    el("span", {}, "Replaced by ", el("span", { class: "mono" }, detail.successor)),
    el("button", { class: "btn small", type: "button", "data-key": "successor", disabled: !a.browse,
      onclick: () => memory.select(detail.successor) }, "Inspect it")) : null,
  evidence(detail, a),
  actions(detail, a),
  s.outcome?.text && !s.draft ? outcomeBox(s.outcome, a) : null,
  el("p", { class: "read-at" }, `Read at ${when(detail.observed)} · revision ${detail.revision} · not live`),
  el("p", { class: "notice" }, "Core does not share when a memory was made, how important it is or "
    + "what it connects to, so none of that is shown."),
  el("details", { class: "about" }, el("summary", {}, "What this record shows"),
    el("p", { class: "notice" }, detail.note)));
}

function outcomeBox(outcome, a) {
  return el("div", { class: `outcome ${outcome.tone || ""}`, role: "status" },
    el("p", {}, outcome.text),
    outcome.note ? el("p", { class: "notice" }, outcome.note) : null,
    outcome.successor ? el("button", { class: "btn small", type: "button", "data-key": "new-version",
      disabled: !a.browse, onclick: () => memory.select(outcome.successor) }, "Inspect the new version") : null);
}

function renderInspector(a) {
  const parts = [];
  if (!s.canUseCore) {
    parts.push(banner("SORA's Core is not taking changes right now (it may be starting, stopping or "
      + "disconnected). You can still read memories; Correct, Forget and Open wait until it is back."));
  } else if (!s.connected && s.identityChecked) {
    parts.push(banner(s.epoch ? "SORA's Core is not answering. What you see was read earlier and may be out of date."
      : "SORA's Core is not answering yet."));
  }
  const card = s.selected !== null && s.detail?.item.id === s.selected;
  if (s.selected === null) {
    if (!s.draft) parts.push(placeholder());
  } else if (card) {
    parts.push(memoryCard(s.detail, a));
  } else {
    parts.push(el("article", { class: "card memory-card pending", id: "memory-card" },
      el("div", { class: "memory-id" }, el("span", { class: "label" }, "ID"), el("span", { class: "mono" }, s.selected)),
      el("p", { class: "loading" }, s.inspecting ? "Reading this exact memory…" : "This memory could not be shown.")));
  }
  // The outcome sits next to the buttons that caused it: in the draft, in the card, or below.
  if (s.outcome?.text && !card && !s.draft) parts.push(outcomeBox(s.outcome, a));
  const key = focusedKey(els.main);
  const scroll = scroller().scrollTop;
  els.main.replaceChildren(...parts);
  scroller().scrollTop = scroll;
  restoreFocus(els.main, key);
}

// ---------- the draft (kept in place so typing is never interrupted) ----------

function buildEditor(draft) {
  const correct = draft.action === "correct";
  const parts = {
    draft,
    pin: el("p", { class: "pin" }),
    frozen: el("p", { class: "frozen", role: "status" }),
    textarea: correct ? el("textarea", { class: "input", rows: 8, spellcheck: true,
      "aria-label": "Corrected memory text", "data-key": "draft-text",
      oninput: (event) => memory.editDraft(event.target.value) }) : null,
    problem: el("span", { class: "error-text" }),
    counter: el("span", { class: "counter" }),
    outcome: el("div", { class: "draft-outcome" }),
    buttons: el("div", { class: "buttons" }),
    confirm: el("div", { class: "draft-confirm" }),
  };
  if (parts.textarea) parts.textarea.value = draft.text;
  const root = el("section", { class: "card draft", "aria-label": correct ? "Correction draft" : "Forget request" },
    el("h2", {}, correct ? "Correct this memory" : "Forgetting this memory"),
    parts.pin, parts.frozen, parts.textarea,
    correct ? el("div", { class: "draft-foot" }, parts.problem, parts.counter) : null,
    parts.outcome, parts.buttons, parts.confirm);
  els.draft.replaceChildren(root);
  parts.root = root;
  if (parts.textarea) parts.textarea.focus({ preventScroll: true });
  reveal(root);
  return parts;
}

function draftButtons(draft, a) {
  const button = (key, label, enabled, onclick, kind = "") => el("button", {
    class: `btn ${kind}`.trim(), type: "button", "data-key": key, disabled: !enabled, onclick }, label);
  if (draft.needsResolution) {
    return [
      button("discard", "Discard draft", a.discard, () => memory.askDiscard()),
      button("receipt", "Check receipt", a.receipt, () => memory.checkReceipt()),
      button("retry", "Retry same request", a.retry, () => memory.submit(), "primary"),
    ];
  }
  return [
    button("discard", "Discard draft", a.discard, () => memory.askDiscard()),
    button("review", "Review latest", a.review, () => memory.reviewLatest()),
    button("save", s.mutating ? "Saving…" : "Save correction", a.save, () => memory.submit(), "primary"),
  ];
}

function draftConfirm(draft) {
  if (s.confirm === "discard") {
    return el("div", { class: "confirm", role: "group", "aria-label": "Discard this draft?" },
      el("span", {}, "Discard this draft? This does not undo anything already sent.",
        draft.needsResolution ? ` The outcome of request ${draft.pending.requestId} is still unknown.` : ""),
      el("button", { class: "btn", type: "button", "data-key": "discard-cancel",
        onclick: () => memory.cancelConfirm() }, "Keep draft"),
      el("button", { class: "btn danger", type: "button", "data-key": "discard-confirm",
        onclick: () => memory.confirmDiscard() }, "Discard"));
  }
  if (s.confirm === "review" && s.review) {
    const latest = s.review;
    const status = stateLabel(latest.item.state);
    return el("div", { class: "review", role: "group", "aria-label": "Review the latest version" },
      el("p", {}, `Core has version ${latest.item.version} (${status.label.toLowerCase()}), read at `
        + `${when(latest.observed)}. Its text:`),
      el("blockquote", { class: "content" }, latest.content),
      el("p", {}, `Use version ${latest.item.version} as the draft's target? Your text is kept.`),
      el("div", { class: "buttons" },
        el("button", { class: "btn", type: "button", "data-key": "review-cancel",
          onclick: () => memory.cancelConfirm() }, "Keep the current target"),
        el("button", { class: "btn primary", type: "button", "data-key": "review-accept",
          onclick: () => memory.acceptReview() }, `Use version ${latest.item.version}`)));
  }
  return null;
}

function renderDraft(a) {
  const draft = s.draft;
  if (!draft) {
    if (editor) { editor = null; els.draft.replaceChildren(); }
    return;
  }
  if (!editor || editor.draft !== draft) editor = buildEditor(draft);
  const o = draft.original.item;
  editor.pin.textContent = `${draft.action === "correct" ? "Pinned to" : "Request for"} ${o.id} · version ${o.version} · `
    + (draft.original.epoch === s.epoch ? "same Core"
      : "SORA's Core has restarted since; review the latest version before saving");
  editor.frozen.hidden = !draft.needsResolution;
  editor.frozen.textContent = draft.needsResolution
    ? `Request ${draft.pending.requestId} was sent, but its outcome is not known. It is frozen: check `
      + "its receipt, or retry exactly the same request." : "";
  if (editor.textarea) {
    editor.textarea.readOnly = Boolean(draft.pending) || memory.busy;
    if (editor.textarea.value !== draft.text) editor.textarea.value = draft.text;
    const count = codePoints(draft.text);
    editor.counter.textContent = `${count.toLocaleString("en-GB")} / ${MAX_CONTENT.toLocaleString("en-GB")}`;
    editor.counter.classList.toggle("over", count > MAX_CONTENT);
    editor.problem.textContent = draft.pending ? "" : contentError(draft.text);
  }
  const key = focusedKey(editor.root);
  editor.outcome.replaceChildren(...(s.outcome?.text ? [outcomeBox(s.outcome, a)] : []));
  editor.buttons.replaceChildren(...draftButtons(draft, a));
  const confirm = draftConfirm(draft);
  editor.confirm.replaceChildren(...(confirm ? [confirm] : []));
  restoreFocus(editor.root, key);
}

// ---------- host and timers ----------

function syncHost() {
  const dirty = memory.dirty;
  const busy = memory.busy;
  if (dirty !== reportedDirty) { reportedDirty = dirty; sendToHost("panel.dirty", { dirty }); }
  if (busy !== reportedBusy) { reportedBusy = busy; sendToHost("panel.busy", { busy }); }
}

function armExpiry() {
  const h = s.highlight;
  if (!h) { clearTimeout(expiryTimer); expiryFor = null; return; }
  if (expiryFor === h) return;
  expiryFor = h;
  clearTimeout(expiryTimer);
  expiryTimer = setTimeout(() => {
    expiryFor = null;
    if (!memory.expireHighlight()) armExpiry();
  }, Math.max(0, h.expiresAt - Date.now()) + 25);
}

/** Puts the safe button under the keyboard when a confirmation opens, and shows a new outcome. */
function focusConfirm() {
  if (s.outcome !== shownOutcome) {
    shownOutcome = s.outcome;
    if (s.outcome) reveal(document.querySelector(".outcome"));
  }
  if (s.confirm === shownConfirm) return;
  shownConfirm = s.confirm;
  const safe = { forget: "forget-cancel", discard: "discard-cancel", review: "review-cancel" }[s.confirm];
  if (!safe) return;
  focusOn(document.body, safe);
  reveal(document.querySelector(s.confirm === "review" ? ".review" : ".confirm"));
}

function render() {
  const a = memory.availability();
  renderModes(a);
  renderList(a);
  renderPager(a);
  renderInspector(a);
  renderDraft(a);
  focusConfirm();
  syncHost();
  armExpiry();
}

// ---------- SORA's "show this memory" ----------

/** Waits for layout and paint, with a fallback for when frames are throttled. */
function settle() {
  return new Promise((resolve) => {
    let done = false;
    const finish = () => { if (!done) { done = true; resolve(); } };
    requestAnimationFrame(() => requestAnimationFrame(finish));
    setTimeout(finish, 120);
  });
}

function bringCardIntoView(card) {
  const box = scroller().getBoundingClientRect();
  const r = card.getBoundingClientRect();
  // Top of the card near the top of its pane, so most of it is on screen where SORA points.
  if (r.top < box.top || r.top > box.top + box.height / 3) scroller().scrollTop += r.top - box.top - 8;
}

/** The visible part of the highlighted card, in CSS pixels of this page, or null. */
function cardAnchor() {
  const card = $("memory-card");
  if (!card) return null;
  const r = card.getBoundingClientRect();
  const box = scroller().getBoundingClientRect();
  const left = Math.max(r.left, box.left, 0);
  const top = Math.max(r.top, box.top, 0);
  const right = Math.min(r.right, box.right, globalThis.innerWidth);
  const bottom = Math.min(r.bottom, box.bottom, globalThis.innerHeight);
  if (right - left < 1 || bottom - top < 1) return null;
  const round = (value) => Math.round(value * 100) / 100;
  return { x: round(left), y: round(top), width: round(right - left), height: round(bottom - top) };
}

async function present(request) {
  const result = await memory.present(request, { visible: document.visibilityState === "visible" });
  if (!result) return;
  let anchor = null;
  if (result.status !== "unavailable") {
    revealSelectedRow();
    const card = $("memory-card");
    if (card) bringCardIntoView(card);
    await settle();
    anchor = s.highlight?.requestId === result.requestId ? cardAnchor() : null;
    if (anchor) highlightTop = $("memory-card").getBoundingClientRect().top;
    else memory.dropHighlight(result.requestId);
  }
  // Not busy any more before replying, so the host's own check sees an idle page.
  memory.endPresentation(result.requestId);
  sendToHost("memory.presented", anchor
    ? { requestId: result.requestId, status: result.status, anchor }
    : { requestId: result.requestId, status: "unavailable" });
}

/** Scrolling the inspector moves the card away from the place reported to SORA. */
function checkScroll() {
  if (!s.highlight || highlightTop === null) return;
  const card = $("memory-card");
  if (!card || Math.abs(card.getBoundingClientRect().top - highlightTop) > 2) memory.userScrolled();
}

// ---------- owner actions ----------

els.modeOverview.addEventListener("click", () => memory.overview());
els.modeSearch.addEventListener("click", () => {
  memory.setMode("search");
  els.q.focus();
});
els.modeGraph.addEventListener("click", () => toast("Graph is not available yet. Core does not share "
  + "connections between memories, so SORA does not draw any."));
els.filters.addEventListener("submit", (event) => {
  event.preventDefault();
  void memory.refresh();
});
els.q.addEventListener("input", () => memory.setFilter("q", els.q.value));
els.scope.addEventListener("input", () => memory.setFilter("scope", els.scope.value));
els.state.addEventListener("change", () => memory.setFilter("state", els.state.value));
els.project.addEventListener("change", () => memory.setFilter("project", els.project.value));
els.exact.addEventListener("input", () => { els.inspectId.disabled = !memory.availability().browse || !els.exact.value.trim(); });
els.exact.addEventListener("keydown", (event) => {
  if (event.key === "Enter") { event.preventDefault(); void memory.inspectExact(els.exact.value); }
});
els.inspectId.addEventListener("click", () => memory.inspectExact(els.exact.value));
els.refresh.addEventListener("click", () => memory.refresh());
els.previous.addEventListener("click", () => memory.previous());
els.next.addEventListener("click", () => memory.next());
els.list.addEventListener("keydown", (event) => {
  if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
  const rows = [...els.list.querySelectorAll("button.memory-item:not(:disabled)")];
  if (!rows.length) return;
  event.preventDefault();
  const at = rows.indexOf(document.activeElement);
  const step = event.key === "ArrowDown" ? 1 : -1;
  const index = event.key === "Home" ? 0 : event.key === "End" ? rows.length - 1
    : Math.min(rows.length - 1, Math.max(0, at + step));
  rows[index].focus();
  void memory.select(rows[index].dataset.key);
});
els.inspector.addEventListener("scroll", checkScroll, { passive: true });
els.body.addEventListener("scroll", checkScroll, { passive: true });
// Escape closes a confirmation, or asks before discarding a draft, instead of hiding the window.
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape" || event.defaultPrevented) return;
  if (s.confirm) { event.preventDefault(); memory.cancelConfirm(); return; }
  if (s.draft && editor?.textarea && event.target === editor.textarea) {
    event.preventDefault();
    memory.askDiscard();
  }
}, true);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && !s.page && !s.reading) void memory.readPage({ user: false });
});

async function pollIdentity() {
  clearTimeout(identityTimer);
  await memory.poll();
  identityTimer = setTimeout(pollIdentity, IDENTITY_MS);
}

// ---------- start ----------

const wanted = new URLSearchParams(location.search).get("memory");
render();
await memory.start({ wanted });
identityTimer = setTimeout(pollIdentity, IDENTITY_MS);
