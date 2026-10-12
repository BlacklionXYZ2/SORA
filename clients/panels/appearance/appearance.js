import { hostRequest, hosted, onHostMessage, send as sendToHost } from "../shared/bridge.js";
import { icon } from "../shared/icons.js";
import { setUpWindow } from "../shared/window.js";
import {
  FIELDS, GROUPS, PREVIEW_TEXT, TEXT_SCALE, afterSave, changeSummary, changedKeys, discard, edit,
  elsewhereChanges, emptyState, fileStatus, isConflictError, isDirty, keepMine, legacyLines,
  parseTextScale, readPreferences, receive, sameValues, saveBlocked, saveDetail, shortcutStatus,
  valueLabel, SHORTCUT_LABELS, THEME_LABELS,
} from "./appearance-model.js";

const els = {
  notices: document.getElementById("notices"),
  stateNote: document.getElementById("state-note"),
  fields: document.getElementById("fields"),
  avatar: document.getElementById("avatar"),
  placement: document.getElementById("placement"),
  file: document.getElementById("file"),
  savebar: document.getElementById("savebar"),
  savebarText: document.getElementById("savebar-text"),
  save: document.getElementById("save"),
  discard: document.getElementById("discard"),
};
const state = {
  model: emptyState(),
  busy: "",        // "save" | "reload" | "recover" | "reset" while the host works
  confirm: "",     // "reload" | "reset" | "recover" while an inline confirmation is open
  error: "",       // the last action that did not work, in the host's words
  malformed: false, // the host sent preferences this page could not read
  waited: false,   // the host has not sent preferences after a few seconds
};
let toastTimer = 0;
let reportedDirty = false;
let reportedBusy = false;
let shownValues = null; // the values the field controls were last built from
let shownReadOnly = null;

// The host sends host.preferences right after panel.ready; listen before anything else.
onHostMessage((message) => {
  if (message.type !== "host.preferences") return;
  const prefs = readPreferences(message);
  if (!prefs) {
    state.malformed = true;
    renderNotices();
    return;
  }
  state.malformed = false;
  state.model = receive(state.model, prefs);
  renderAll();
});

setUpWindow();

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

// ---------- quit protection ----------

function report() {
  const dirty = isDirty(state.model);
  if (dirty !== reportedDirty) {
    reportedDirty = dirty;
    sendToHost("panel.dirty", { dirty });
  }
  const busy = Boolean(state.busy);
  if (busy !== reportedBusy) {
    reportedBusy = busy;
    sendToHost("panel.busy", { busy });
  }
}

// ---------- notices ----------

function banner(kind, text, ...actions) {
  return el("div", { class: `banner${kind === "error" ? " error" : ""}`, role: "status",
    html: icon("alert") },
  el("span", {}, text), actions.length ? el("div", { class: "banner-actions" }, ...actions) : null);
}

function renderNotices() {
  const { prefs } = state.model;
  const notes = [];
  if (state.malformed) {
    notes.push(banner("warn", "SORA's app sent appearance preferences this page could not read. "
      + "Nothing was changed."));
  }
  if (hosted && !prefs && state.waited) {
    notes.push(banner("warn", "SORA's app has not sent your appearance preferences yet. "
      + "Close this window and open Appearance again if this stays."));
  }
  if (prefs?.readOnly) {
    notes.push(banner("warn", "SORA could not read your appearance preferences file, so it is using "
      + "safe defaults for now and saving is off. The file has not been changed.",
    el("button", { class: "btn", type: "button", disabled: Boolean(state.busy),
      onclick: () => openConfirm("recover") }, "Recover…")));
  }
  if (state.model.changedElsewhere) {
    const changes = elsewhereChanges(state.model)
      .map((change) => `${change.label} (now ${change.now})`).join(", ");
    notes.push(banner("warn", `Appearance was changed somewhere else while you were editing: ${changes}. `
      + "Your edits are kept, but they are not saved.",
    el("button", { class: "btn", type: "button", disabled: Boolean(state.busy), onclick: keepEdits },
      "Keep my edits"),
    el("button", { class: "btn", type: "button", disabled: Boolean(state.busy), onclick: useSaved },
      "Use the saved values")));
  }
  if (state.error) {
    notes.push(banner("error", state.error,
      el("button", { class: "icon-btn", type: "button", title: "Dismiss", html: icon("close", "Dismiss"),
        onclick: () => { state.error = ""; renderNotices(); } })));
  }
  els.notices.replaceChildren(...notes);
}

// ---------- fields ----------

function fieldId(key) { return `f-${key}`; }

function choiceLabel(field, value) {
  return field.key === "theme" ? THEME_LABELS[value] : SHORTCUT_LABELS[value];
}

function scaleControl(field, value) {
  const id = fieldId(field.key);
  const slider = el("input", {
    type: "range", id, min: TEXT_SCALE.min, max: TEXT_SCALE.max, step: TEXT_SCALE.step, value,
    "aria-describedby": `${id}-help`, "aria-valuetext": `${value} percent`,
  });
  const number = el("input", {
    class: "input", type: "number", min: TEXT_SCALE.min, max: TEXT_SCALE.max, step: TEXT_SCALE.step,
    value, inputMode: "numeric", "aria-label": "Panel text size in percent",
  });
  slider.addEventListener("input", () => {
    number.value = slider.value;
    slider.setAttribute("aria-valuetext", `${slider.value} percent`);
    update(field.key, Number(slider.value));
  });
  // Typed values are clamped to 85–175 once the owner leaves the box, as the classic box did.
  number.addEventListener("change", () => {
    const typed = parseTextScale(number.value);
    const next = typed ?? state.model.draft.textScale;
    number.value = String(next);
    slider.value = String(next);
    slider.setAttribute("aria-valuetext", `${next} percent`);
    update(field.key, next);
  });
  return el("div", { class: "scale" }, slider, number, el("span", { class: "unit", "aria-hidden": "true" }, "%"));
}

function control(field, value) {
  const id = fieldId(field.key);
  if (field.kind === "toggle") {
    return el("label", { class: "toggle", title: field.label },
      el("input", { type: "checkbox", id, checked: value === true, "aria-describedby": `${id}-help`,
        onchange: (event) => update(field.key, event.target.checked) }),
      el("span"));
  }
  if (field.kind === "scale") return scaleControl(field, value);
  const select = el("select", { class: "input", id, "aria-describedby": `${id}-help`,
    onchange: (event) => update(field.key, event.target.value) },
  ...field.choices.map((choice) => el("option", { value: choice, selected: choice === value },
    choiceLabel(field, choice))));
  if (field.key !== "shortcut") return select;
  return el("div", { class: "control-stack" }, select, el("div", { class: "control-note", id: "shortcut-status" }));
}

function fieldRow(field) {
  const id = fieldId(field.key);
  const values = state.model.draft;
  return el("div", { class: "field", "data-key": field.key },
    el("div", {},
      el("div", { class: "field-head" },
        hosted ? el("label", { class: "field-label", for: id }, field.label)
          : el("span", { class: "field-label" }, field.label),
        el("span", { class: "badge muted", title: "Where this applies" }, field.scope)),
      el("div", { class: "field-help", id: `${id}-help` }, field.help)),
    el("div", { class: "field-control" },
      values ? control(field, values[field.key]) : el("span", { class: "field-preview" }, "Set in SORA's app")));
}

/** Rebuild the controls only when the values or the read-only state really changed. */
function renderFields() {
  const { prefs, draft } = state.model;
  const readOnly = Boolean(prefs?.readOnly);
  els.fields.hidden = hosted && !draft;
  if (!els.fields.hidden && (shownValues === null || !sameValues(shownValues, draft)
      || shownReadOnly !== readOnly || !els.fields.childElementCount)) {
    els.fields.replaceChildren(...GROUPS.map((group) => el("section", { class: "group" },
      el("h3", { class: "group-title" }, group.title),
      el("div", { class: "fields" }, ...FIELDS.filter((field) => field.group === group.id).map(fieldRow)))));
    shownValues = draft ? { ...draft } : null;
    shownReadOnly = readOnly;
  }
  // No editing without the host, while it works, or while the file is unreadable (save is off).
  els.fields.disabled = !hosted || !draft || Boolean(state.busy) || readOnly;
  markEdited();
  renderShortcutStatus();
}

function markEdited() {
  const edited = new Set(changedKeys(state.model.draft, state.model.baseline));
  for (const row of els.fields.querySelectorAll(".field")) {
    row.classList.toggle("edited", edited.has(row.dataset.key));
  }
}

function renderShortcutStatus() {
  const box = document.getElementById("shortcut-status");
  const { prefs, draft } = state.model;
  if (!box || !prefs) return;
  const status = shortcutStatus(prefs.shortcutStatus);
  const pending = draft && draft.shortcut !== prefs.values.shortcut;
  box.replaceChildren(el("span", { class: `state ${status.tone}` }, status.text),
    ...(pending ? [el("div", {}, `${valueLabel("shortcut", draft.shortcut)} is registered when you save.`)] : []));
}

function update(key, raw) {
  try {
    state.model = edit(state.model, key, raw);
  } catch (error) {
    toast(error.message);
    return;
  }
  shownValues = state.model.draft ? { ...state.model.draft } : null;
  markEdited();
  renderShortcutStatus();
  renderSavebar();
}

// ---------- the other sections ----------

function confirmStrip(kind, text, confirmLabel, onConfirm, { danger = false } = {}) {
  const keep = el("button", { class: "btn", type: "button", onclick: closeConfirm }, "Cancel");
  const strip = el("div", { class: "confirm", role: "group", "aria-label": text, "data-confirm": kind },
    el("span", {}, text),
    el("button", { class: `btn${danger ? " danger" : " primary"}`, type: "button", disabled: Boolean(state.busy),
      onclick: onConfirm }, confirmLabel),
    keep);
  return strip;
}

function renderAvatar() {
  els.avatar.replaceChildren(
    el("span", { class: "avatar-icon", html: icon("appearance") }),
    el("span", {}, "Her avatar (how she looks) is a SORA setting, chosen in Settings → Appearance."),
    el("button", { class: "btn", type: "button", onclick: openSettings }, "Open Settings"));
}

function renderPlacement() {
  const { prefs } = state.model;
  if (!hosted || !prefs) { els.placement.replaceChildren(); return; }
  const blocked = prefs.readOnly ? "Recover the preferences file first." : "";
  els.placement.replaceChildren(
    el("h2", { id: "placement-title" }, "Window positions"),
    el("div", { class: "card" },
      el("p", {}, "Forget where SORA's windows were placed and bring open windows back to their starting "
        + "size on this screen. Other preferences, your unsaved edits here and Core settings are not changed."),
      state.confirm === "reset" && !prefs.readOnly
        ? confirmStrip("reset", "Clear the saved window positions and bring open windows into view?",
          "Reset placement", resetPlacement)
        : el("div", { class: "actions" },
          el("button", { class: "btn", type: "button", disabled: Boolean(state.busy) || prefs.readOnly,
            title: blocked || undefined, onclick: () => openConfirm("reset") }, "Reset panel placement…"),
          blocked ? el("span", { class: "notice" }, blocked) : null)));
}

function renderFile() {
  const { prefs } = state.model;
  if (!hosted || !prefs) { els.file.replaceChildren(); return; }
  const status = fileStatus(prefs);
  const legacy = legacyLines(prefs.legacy);
  let actions;
  if (state.confirm === "reload") {
    actions = confirmStrip("reload", "Discard your unsaved appearance edits and load the saved values?",
      "Discard and reload", reload, { danger: true });
  } else if (state.confirm === "recover" && prefs.readOnly) {
    actions = confirmStrip("recover", "Keep a dated, byte-identical backup of the unreadable file, then "
      + "replace only SORA's window preferences with the defaults? Core settings are not changed."
      + (isDirty(state.model) ? " Your unsaved edits here are discarded." : ""),
    "Back up and use defaults", recover, { danger: true });
  } else {
    actions = el("div", { class: "actions" },
      el("button", { class: "btn", type: "button", disabled: Boolean(state.busy), onclick: askReload,
        title: "Read the preferences file again" }, "Reload saved values…"),
      prefs.readOnly ? el("button", { class: "btn danger", type: "button", disabled: Boolean(state.busy),
        onclick: () => openConfirm("recover") }, "Recover…") : null);
  }
  els.file.replaceChildren(
    el("h2", { id: "file-title" }, "Preferences file"),
    el("div", { class: "card" },
      el("div", { class: "file-head" },
        el("span", { class: `state ${status.tone}` }, status.label),
        status.headline ? el("strong", {}, status.headline) : null),
      status.detail ? el("div", { class: "notice" }, status.detail) : null,
      prefs.filePath ? el("div", { class: "file-path", title: "Where SORA's app keeps these" }, prefs.filePath)
        : el("div", { class: "notice" }, "SORA's app did not report where the file is."),
      legacy.length ? el("ul", { class: "legacy notice" }, ...legacy.map((line) => el("li", {}, line))) : null,
      actions));
}

function renderStateNote() {
  if (!hosted) {
    els.stateNote.replaceChildren(el("div", { class: "card state-card", html: icon("appearance") },
      el("p", {}, PREVIEW_TEXT, " Below is what each preference does.")));
    return;
  }
  if (state.model.prefs) { els.stateNote.replaceChildren(); return; }
  els.stateNote.replaceChildren(el("div", { class: "loading" },
    state.waited ? "Waiting for SORA's app…" : "Loading your appearance preferences…"));
}

function renderSavebar() {
  report();
  const { model } = state;
  const dirty = isDirty(model);
  els.savebar.hidden = !dirty && state.busy !== "save";
  if (els.savebar.hidden) return;
  els.discard.hidden = !dirty || state.busy === "save";
  const blocked = saveBlocked(model, { busy: Boolean(state.busy) });
  els.save.disabled = Boolean(blocked);
  els.discard.disabled = Boolean(state.busy);
  if (state.busy === "save") els.savebarText.textContent = "Saving…";
  else if (model.prefs?.readOnly) els.savebarText.textContent = blocked;
  else els.savebarText.textContent = changeSummary(model);
}

function renderAll() {
  renderStateNote();
  renderNotices();
  renderFields();
  renderPlacement();
  renderFile();
  renderSavebar();
}

// ---------- actions ----------

function openConfirm(kind) {
  state.confirm = kind;
  renderPlacement();
  renderFile();
  const strip = document.querySelector(`[data-confirm="${kind}"]`);
  strip?.scrollIntoView({ block: "nearest" });
  strip?.querySelector("button:last-child")?.focus();
}

function closeConfirm() {
  const kind = state.confirm;
  state.confirm = "";
  renderPlacement();
  renderFile();
  if (kind === "reset") els.placement.querySelector("button")?.focus();
  else els.file.querySelector(".actions button")?.focus();
}

async function ask(kind, type, detail = {}) {
  state.busy = kind;
  state.confirm = "";
  state.error = "";
  renderAll();
  try {
    return await hostRequest(type, detail);
  } catch (error) {
    return { ok: false, error: String(error?.message ?? error) };
  } finally {
    state.busy = "";
  }
}

async function save() {
  if (saveBlocked(state.model, { busy: Boolean(state.busy) })) return;
  let detail;
  try {
    detail = saveDetail(state.model);
  } catch (error) {
    state.error = error.message;
    renderNotices();
    return;
  }
  const shortcutChanged = detail.values.shortcut !== detail.baseline.shortcut;
  const result = await ask("save", "prefs.save", detail);
  if (result.ok) {
    state.model = afterSave(state.model, detail);
    // The host re-registers the shortcut before it answers, so this is the new registration.
    toast(shortcutChanged ? `Saved. ${shortcutStatus(state.model.prefs?.shortcutStatus).text}` : "Saved.");
  } else if (isConflictError(result.error) && state.model.prefs
      && !sameValues(state.model.prefs.values, state.model.baseline)) {
    state.model = { ...state.model, changedElsewhere: true };
  } else {
    state.error = `Not saved: ${result.error || "SORA's app did not say why."} Your edits are kept.`;
  }
  renderAll();
}

function askReload() {
  if (isDirty(state.model)) openConfirm("reload");
  else reload();
}

async function reload() {
  const result = await ask("reload", "prefs.reload");
  if (result.ok) {
    state.model = discard(state.model);
    toast(state.model.prefs?.readOnly ? "The file still could not be read." : "Loaded the saved values.");
  } else {
    state.error = `Not reloaded: ${result.error || "SORA's app did not say why."}`;
  }
  renderAll();
}

async function recover() {
  const result = await ask("recover", "prefs.recover");
  if (result.ok) {
    state.model = discard(state.model);
    toast("The unreadable file was backed up and the defaults were saved.");
  } else {
    state.error = `Not recovered: ${result.error || "SORA's app did not say why."}`;
  }
  renderAll();
}

async function resetPlacement() {
  const result = await ask("reset", "placement.reset");
  if (result.ok) toast("Window positions were reset.");
  else state.error = `Window positions were not reset: ${result.error || "SORA's app did not say why."}`;
  renderAll();
}

function keepEdits() {
  state.model = keepMine(state.model);
  state.error = "";
  renderAll();
  toast("Your edits now apply on top of the latest saved values. Check them, then save.");
}

function useSaved() {
  state.model = discard(state.model);
  state.error = "";
  renderAll();
}

function openSettings() {
  sendToHost("panel.open", { panel: "settings", select: "Appearance" });
  if (!hosted) toast("Settings opens in SORA's app.");
}

els.save.addEventListener("click", save);
els.discard.addEventListener("click", () => {
  state.model = discard(state.model);
  state.confirm = state.confirm === "reload" ? "" : state.confirm;
  renderAll();
});
// Escape in an inline confirmation cancels it instead of hiding the window (window.js hides on Escape).
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && state.confirm) {
    event.preventDefault();
    closeConfirm();
  }
}, true);
document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
    event.preventDefault();
    if (!els.save.disabled && !els.savebar.hidden) save();
  }
});

renderAvatar();
renderAll();
if (hosted) {
  setTimeout(() => {
    if (state.model.prefs) return;
    state.waited = true;
    renderAll();
  }, 5000);
}
