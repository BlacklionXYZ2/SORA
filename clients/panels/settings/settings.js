import { CoreApi, CoreError } from "../shared/api.js";
import { hosted, pickFile, send as sendToHost } from "../shared/bridge.js";
import { icon } from "../shared/icons.js";
import { setUpWindow } from "../shared/window.js";
import {
  PICK_KIND, VISION_DETAIL_KEY, VISION_DISCLAIMER, VISION_ORDER, afterVisionArgumentEdit,
  brainSummary, brainTiles, categoryGroups, chooseVisionLevel, coerce, effectOf, fieldByKey,
  fileName, folderName, isPathType, launchText, rebaseDraft, saveRequest, setDraft, shownValue,
  sourceLabel, visibleCategories, visionDetail,
} from "./settings-model.js";

const api = new CoreApi();
const els = {
  rail: document.getElementById("rail"),
  content: document.getElementById("content"),
  banner: document.getElementById("banner"),
  savebar: document.getElementById("savebar"),
  savebarText: document.getElementById("savebar-text"),
  save: document.getElementById("save"),
  discard: document.getElementById("discard"),
};
const state = {
  projection: null,
  draft: {},
  invalid: {},          // key -> message, for inputs that do not parse yet
  category: "Models",
  busy: "",             // "saving" | "reloading" while a request runs
  error: "",
  notice: "",
};
let toastTimer = 0;

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

function message(error) {
  return error instanceof CoreError ? error.message : String(error?.message ?? error);
}

// ---------- rail ----------

function openAppearanceWindow() {
  sendToHost("panel.open", { panel: "appearance" });
  if (!hosted) toast("Appearance opens in SORA's app.");
}

function renderRail() {
  const categories = visibleCategories(state.projection);
  // Core's Appearance category (her avatar) links to the older window from its pane instead.
  const appearanceListed = categories.some((category) => category.id === "Appearance");
  if (!categories.some((category) => category.id === state.category) && categories.length) {
    state.category = categories[0].id;
  }
  els.rail.replaceChildren(
    ...categories.map((category) => el("button", {
      class: "rail-item", type: "button",
      "aria-current": category.id === state.category ? "page" : false,
      html: icon(category.icon) + `<span>${category.id}</span>`,
      onclick: () => { state.category = category.id; renderRail(); renderPane(); },
    })),
    el("span", { class: "rail-spacer" }),
    ...(appearanceListed ? [] : [el("button", {
      class: "rail-item", type: "button", title: "Window style and panel placement",
      html: icon("appearance") + "<span>Appearance</span>", onclick: openAppearanceWindow,
    })]),
  );
}

// ---------- banner and save bar ----------

function renderBanner() {
  const p = state.projection;
  const lines = [];
  if (state.error) lines.push(state.error);
  if (state.notice) lines.push(state.notice);
  if (p?.settings_warning) lines.push(p.settings_warning);
  if (p?.restart_required) lines.push("Some saved changes apply the next time SORA starts. Quit SORA from the tray and start it again.");
  if (p?.disk_changed) lines.push("The settings file was changed outside SORA.");
  els.banner.hidden = lines.length === 0;
  els.banner.replaceChildren();
  if (!lines.length) return;
  els.banner.insertAdjacentHTML("afterbegin", icon("alert"));
  els.banner.append(el("span", { style: "flex:1" }, lines.join(" ")));
  if (p?.disk_changed) {
    els.banner.append(el("button", { class: "btn", type: "button", onclick: refreshFromDisk },
      "Load from file"));
  }
}

let reportedDirty = false;

function renderSavebar() {
  const p = state.projection;
  const effect = p ? effectOf(p, state.draft) : { count: 0 };
  const invalid = Object.keys(state.invalid).length;
  // Tell SoraShell, so Quit can warn before unsaved edits are lost.
  const dirty = effect.count + invalid > 0;
  if (dirty !== reportedDirty) {
    reportedDirty = dirty;
    sendToHost("panel.dirty", { dirty });
  }
  const reloadReady = p && !effect.count && p.model_reload_required && p.can_reload;
  els.savebar.hidden = !effect.count && !invalid && !reloadReady && !state.busy;
  if (els.savebar.hidden) return;
  els.discard.hidden = !effect.count && !invalid;
  if (state.busy === "reloading") {
    els.savebarText.textContent = "Loading the model… SORA answers again when it is ready.";
    els.save.textContent = "Loading…";
    els.save.disabled = true;
    return;
  }
  if (state.busy === "saving") {
    els.savebarText.textContent = "Saving…";
    els.save.disabled = true;
    return;
  }
  if (reloadReady) {
    els.savebarText.textContent = "Saved model changes take effect after the model reloads.";
    els.save.textContent = "Reload model";
    els.save.disabled = false;
    return;
  }
  const parts = [`${effect.count} unsaved change${effect.count === 1 ? "" : "s"}`];
  if (invalid) parts.push(`${invalid} to fix`);
  if (effect.restart) parts.push("some apply after restarting SORA");
  els.savebarText.textContent = parts.join(" · ");
  const andReload = effect.reload && !effect.restart && p.can_reload;
  els.save.textContent = andReload ? "Save and reload model" : "Save";
  els.save.disabled = invalid > 0;
}

// ---------- field controls ----------

function edited(key) { return Object.hasOwn(state.draft, key) || Object.hasOwn(state.invalid, key); }

function update(field, raw, row) {
  try {
    const value = coerce(field, raw);
    delete state.invalid[field.key];
    state.draft = setDraft(state.projection, state.draft, field.key, value);
    state.draft = afterVisionArgumentEdit(state.projection, state.draft, field.key);
  } catch (error) {
    state.invalid[field.key] = error.message;
  }
  if (row) {
    row.classList.toggle("edited", edited(field.key));
    const errorLine = row.querySelector(".field-error");
    errorLine.textContent = state.invalid[field.key] ?? "";
    errorLine.hidden = !state.invalid[field.key];
  }
  renderSavebar();
}

function textValue(value) { return value === null || value === undefined ? "" : String(value); }

function control(field, row) {
  const value = shownValue(state.projection, state.draft, field.key);
  const id = `f-${field.key.replace(/[^A-Za-z0-9]/g, "-")}`;
  switch (field.type) {
    case "bool": {
      const input = el("input", { type: "checkbox", id, checked: Boolean(value),
        onchange: (event) => update(field, event.target.checked, row) });
      return el("label", { class: "toggle", title: field.label }, input, el("span"));
    }
    case "enum":
      return el("select", { class: "input", id, onchange: (event) => update(field, event.target.value, row) },
        ...field.choices.map((choice) => el("option", { value: choice, selected: choice === value }, choice)));
    case "agent-model-purposes":
      return purposeEditor(field, value ?? [], row);
    default: {
      const long = field.type === "string" && (field.key.endsWith(".purpose") || textValue(value).length > 60);
      const input = long
        ? el("textarea", { class: "input", id, rows: 2, value: textValue(value) })
        : el("input", {
          class: "input", id, value: textValue(value), spellcheck: false,
          type: field.type === "int" || field.type === "float" ? "number" : "text",
          step: field.type === "float" ? "any" : undefined,
          min: field.min, max: field.max,
          placeholder: field.type === "gpu" ? "auto, all or a number" : isPathType(field.type) ? "Not set" : "",
        });
      if (field.type === "gpu") {
        input.setAttribute("list", "gpu-choices");
      }
      input.addEventListener("input", () => update(field, input.value, row));
      if (!isPathType(field.type)) return input;
      const browse = el("button", { class: "btn", type: "button", title: "Browse",
        html: icon("folder") + "<span>Browse</span>",
        onclick: async () => {
          // Open the dialog where the current file is, not in the owner's Documents.
          const path = await pickFile(PICK_KIND[field.type],
            { start: folderName(input.value) || undefined });
          if (!path) return;
          input.value = path;
          update(field, path, row);
          if (field.key === "llama.model_path") await findProjector(path);
        } });
      return el("div", { class: "field-control" }, input, browse);
    }
  }
}

function purposeEditor(field, rows, row) {
  let current = rows.map((item) => ({ id: item.id ?? "", purpose: item.purpose ?? "" }));
  const box = el("div", { class: "purposes" });
  const commit = () => update(field, current, row);
  const draw = () => {
    box.replaceChildren(
      ...current.map((item, index) => el("div", { class: "purpose-row" },
        el("input", { class: "input", value: item.id, placeholder: "Model ID",
          oninput: (event) => { current[index].id = event.target.value; commit(); } }),
        el("input", { class: "input", value: item.purpose, placeholder: "What it is good for",
          oninput: (event) => { current[index].purpose = event.target.value; commit(); } }),
        el("button", { class: "icon-btn", type: "button", title: "Remove", html: icon("trash", "Remove"),
          onclick: () => { current = current.filter((_, at) => at !== index); commit(); draw(); } }),
      )),
      el("button", { class: "btn", type: "button", html: icon("plus") + "<span>Add model</span>",
        onclick: () => { current.push({ id: "", purpose: "" }); draw(); } }),
    );
  };
  draw();
  return box;
}

function fieldRow(field, { showHelp = true } = {}) {
  const row = el("div", { class: `field${edited(field.key) ? " edited" : ""}`, "data-key": field.key });
  const tier = field.tier === "next_boot" ? "Applies after restarting SORA"
    : field.tier === "model_reload" ? "Applies when the model reloads" : "";
  row.append(
    el("div", {},
      el("label", { class: "field-label", for: `f-${field.key.replace(/[^A-Za-z0-9]/g, "-")}` }, field.label),
      field.help && showHelp ? el("div", { class: "field-help" }, field.help) : null,
      tier && field.pending ? el("div", { class: "field-tier" }, `Saved, not active yet · ${tier}`) : null),
    el("div", { class: "field-control" }, control(field, row)),
    el("div", { class: "field-error", hidden: !state.invalid[field.key] }, state.invalid[field.key] ?? ""),
  );
  return row;
}

// The names SORA uses for her colleagues (HOW_TO_USE.md), with the product name beside them.
const AGENT_NAMES = { Codex: "Cody (Codex)", Antigravity: "Aggie (Antigravity)" };

function agentName(group) {
  const name = group.replace("Agents · ", "");
  return AGENT_NAMES[name] ?? name;
}

function groupBlock(group) {
  // Help shared by every field in a group is said once, under the group's title.
  const helps = new Set(group.fields.map((field) => field.help || ""));
  const shared = helps.size === 1 && group.fields.length > 1 ? [...helps][0] : "";
  const rows = group.fields.map((field) => fieldRow(field, { showHelp: !shared }));
  if (group.name.startsWith("Agents · ")) {
    // Agent colleagues fold away so the page leads with SORA's own settings.
    const enabled = group.fields.find((field) => field.key.endsWith(".enabled"));
    const on = enabled ? shownValue(state.projection, state.draft, enabled.key) : undefined;
    const open = group.fields.some((field) => edited(field.key));
    return el("details", { class: "group agent", open },
      el("summary", { html: icon("chevron") + `<span>${agentName(group.name)}</span>`
        + (on === undefined ? "" : `<span class="badge ${on ? "" : "warn"}">${on ? "On" : "Off"}</span>`) }),
      shared ? el("div", { class: "field-help group-help" }, shared) : null,
      el("div", { class: "fields" }, ...rows));
  }
  return el("section", { class: "group" },
    el("h3", { class: "group-title" }, group.name),
    shared ? el("div", { class: "field-help group-help" }, shared) : null,
    el("div", { class: "fields" }, ...rows));
}

// ---------- Models: summary card and information tiles ----------

function brainCard() {
  const brain = brainSummary(state.projection);
  const badge = el("span", { class: `badge ${brain.state.tone === "ok" ? "" : brain.state.tone}` },
    brain.state.label);
  const notes = [];
  if (brain.managed && brain.state.note) notes.push(el("div", { class: "brain-note" }, brain.state.note));
  if (brain.nextModel) notes.push(el("div", { class: "brain-note next" },
    `Saved for the next reload: ${fileName(brain.nextModel)}`));
  if (brain.error) notes.push(el("div", { class: "brain-note error" }, brain.error));
  if (!brain.managed) notes.push(el("div", { class: "brain-note" },
    "SORA is not running her own local model. To use one, set Model source to managed-llama "
    + "in General, then restart SORA."));
  const actions = el("div", { class: "brain-actions" },
    el("button", { class: "btn primary", type: "button", disabled: !!state.busy,
      html: icon("models") + "<span>Change model</span>", onclick: changeModel }));
  return el("div", { class: "card highlight brain" },
    el("div", { class: "brain-art", html: icon("models") }),
    el("div", { class: "brain-main" },
      el("div", { class: "brain-title" }, el("strong", {}, brain.title), badge),
      brain.path ? el("div", { class: "brain-path" }, brain.path) : null,
      brain.projector ? el("div", { class: "brain-note" }, `Sees the screen with ${brain.projector}`) : null,
      ...notes),
    actions);
}

function infoTiles() {
  const brain = brainSummary(state.projection);
  const tiles = brain.managed ? brainTiles(state.projection) : [];
  tiles.unshift({ label: "Model source", value: sourceLabel(brain.source), note: "" });
  if (state.projection.runtime_support && state.projection.runtime_support !== "Not checked") {
    tiles.push({ label: "Runtime check", value: state.projection.runtime_support, note: "" });
  }
  return el("div", { class: "tile-grid" }, ...tiles.map((tile) => el("div", { class: "tile" },
    el("div", { style: "min-width:0" },
      el("div", { class: "tile-label" }, tile.label),
      el("div", { class: "tile-value", title: tile.value }, tile.value),
      tile.note ? el("div", { class: "tile-note" }, tile.note) : null))));
}

function launchLine() {
  const text = launchText(state.projection);
  if (!text) return null;
  return el("div", {},
    el("h2", {}, "llama.cpp arguments"),
    el("div", { class: "launch" },
      el("code", { title: text }, text),
      el("button", { class: "icon-btn", type: "button", title: "Copy", html: icon("copy", "Copy"),
        onclick: async () => {
          try { await navigator.clipboard.writeText(text); toast("Copied."); }
          catch { toast("Copy is not available here."); }
        } })),
    el("div", { class: "field-help" }, "What SORA started the running model with. Read-only."));
}

// ---------- Vision: detail slider ----------

const VISION_NAMES = { low: "Low", medium: "Medium", high: "High", custom: "Custom" };

function visionCard() {
  const field = fieldByKey(state.projection, VISION_DETAIL_KEY);
  if (!field) return null;
  const { level, values, index } = visionDetail(state.projection, state.draft);
  const custom = index < 0;
  const badge = el("span", { class: `badge${custom ? " warn" : ""}` }, VISION_NAMES[level] ?? level);
  const slider = el("input", {
    type: "range", class: `vision-slider${custom ? " custom" : ""}`, id: "f-llama-vision_detail",
    min: 0, max: VISION_ORDER.length - 1, step: 1, value: custom ? 1 : index,
    "aria-label": "Vision detail", "aria-valuetext": VISION_NAMES[level] ?? level,
    disabled: !!state.busy,
    oninput: (event) => { badge.textContent = VISION_NAMES[VISION_ORDER[Number(event.target.value)]]; },
    onchange: (event) => {
      state.draft = chooseVisionLevel(state.projection, state.draft, VISION_ORDER[Number(event.target.value)]);
      renderPane();
      renderSavebar();
    },
  });
  const number = (value) => Number(value).toLocaleString("en-GB");
  const edited = Object.hasOwn(state.draft, VISION_DETAIL_KEY);
  return el("div", { class: `card vision${edited ? " edited" : ""}` },
    el("div", { class: "vision-head" },
      el("label", { class: "field-label", for: "f-llama-vision_detail" }, "Vision detail"), badge),
    slider,
    el("div", { class: "vision-scale", "aria-hidden": "true" },
      ...VISION_ORDER.map((name) => el("span", {}, VISION_NAMES[name]))),
    el("div", { class: "field-help" },
      `Each image may use up to ${number(values["llama.image_max_tokens"])} tokens; `
      + `context ${number(values["llama.context_size"])} tokens.`),
    custom ? el("div", { class: "field-help" },
      "Custom: llama.cpp's image arguments were changed by hand (Models and Performance). "
      + "Move the slider to use a level again.") : null,
    el("div", { class: "vision-disclaimer", html: icon("alert") + `<span>${VISION_DISCLAIMER}</span>` }),
    field.pending ? el("div", { class: "field-tier" },
      "Saved, not active yet · Applies when the model reloads") : null,
    edited ? el("div", { class: "field-help" }, "Saving reloads the model.") : null);
}

// ---------- pane ----------

function renderPane() {
  const p = state.projection;
  if (!p) {
    els.content.replaceChildren(el("div", { class: "loading" },
      state.error ? "Settings are unavailable until SORA's Core is reachable." : "Loading settings…"));
    return;
  }
  const category = visibleCategories(p).find((item) => item.id === state.category);
  const { groups, advanced } = categoryGroups(p, state.category);
  const parts = [el("h1", {}, state.category), el("p", { class: "lead" }, category?.blurb ?? "")];
  if (state.category === "Models") {
    parts.push(brainCard(), el("h2", {}, "Model information"), infoTiles());
  }
  if (state.category === "Vision") parts.push(visionCard());
  const windowStyle = state.category === "Appearance" && el("div", {},
    el("h2", {}, "Windows"),
    el("button", { class: "btn", type: "button", onclick: openAppearanceWindow },
      "Window style, Chat shortcut and placement…"),
    el("div", { class: "field-help" }, "These are still in the older Appearance window."));
  const agentGroups = groups.filter((group) => group.name.startsWith("Agents · "));
  parts.push(...groups.filter((group) => !agentGroups.includes(group) && group.name !== "Vision detail")
    .map(groupBlock));
  if (agentGroups.length) {
    parts.push(el("h2", {}, "Agent colleagues"),
      el("p", { class: "lead" }, "The hosted agents SORA can hand work to, and how she describes them."),
      ...agentGroups.map(groupBlock));
  }
  if (advanced.length) {
    parts.push(el("details", { class: "advanced" },
      el("summary", { html: icon("chevron") + "<span>Advanced configuration</span>" }),
      el("div", { class: "fields" }, ...advanced.map(fieldRow))));
  }
  if (state.category === "Models") parts.push(launchLine());
  if (windowStyle) parts.push(windowStyle);
  if (!groups.length && !advanced.length) {
    parts.push(el("div", { class: "empty-pane" }, "Nothing to set here yet."));
  }
  const scroll = els.content.scrollTop;
  els.content.replaceChildren(...parts.filter(Boolean));
  els.content.scrollTop = scroll;
}

function renderAll() { renderRail(); renderBanner(); renderPane(); renderSavebar(); }

// ---------- actions ----------

async function load({ keepDraft = true } = {}) {
  try {
    state.projection = await api.settings();
    if (!Array.isArray(state.projection?.fields)) throw new Error("Settings need a newer SORA Core.");
    state.draft = keepDraft ? rebaseDraft(state.projection, state.draft) : {};
    state.error = "";
  } catch (error) {
    state.error = message(error);
  }
  renderAll();
}

async function findProjector(modelPath) {
  try {
    const { projectors } = await api.projectors(modelPath);
    const field = fieldByKey(state.projection, "llama.mmproj_path");
    if (!field) return;
    if (Array.isArray(projectors) && projectors.length === 1) {
      state.draft = setDraft(state.projection, state.draft, field.key, projectors[0]);
      toast(`Vision projector found: ${fileName(projectors[0])}`);
    } else if (Array.isArray(projectors) && projectors.length > 1) {
      state.draft = setDraft(state.projection, state.draft, field.key, projectors[0]);
      toast(`${projectors.length} vision projectors found; using ${fileName(projectors[0])}. Change it under Brain if needed.`);
    } else {
      toast("No vision projector beside this model, so SORA cannot see the screen with it.");
    }
  } catch (error) {
    toast(message(error));
  }
}

async function changeModel() {
  const field = fieldByKey(state.projection, "llama.model_path");
  if (!field) return;
  const current = shownValue(state.projection, state.draft, field.key) || field.active_value || "";
  const path = await pickFile("gguf", { start: folderName(current) || undefined });
  if (!path) return;
  state.draft = setDraft(state.projection, state.draft, field.key, path);
  await findProjector(path);
  renderAll();
}

async function waitForReload() {
  for (let attempt = 0; attempt < 600; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    try {
      state.projection = await api.settings();
      if (state.projection.model_state !== "reloading") break;
    } catch { /* Core may be busy; keep waiting */ }
  }
}

async function reload() {
  state.busy = "reloading";
  renderAll();
  try {
    state.projection = await api.reloadModel(state.projection.settings_revision);
    await waitForReload();
    const brain = brainSummary(state.projection);
    toast(brain.error ? "The model did not load. See the error on the card."
      : `${brain.title} is loaded.`);
  } catch (error) {
    state.error = message(error);
  } finally {
    state.busy = "";
    renderAll();
  }
}

async function save() {
  const p = state.projection;
  if (!p || state.busy || Object.keys(state.invalid).length) return;
  const effect = effectOf(p, state.draft);
  if (!effect.count) {
    if (p.model_reload_required && p.can_reload) await reload();
    return;
  }
  state.busy = "saving";
  state.notice = "";
  renderSavebar();
  try {
    state.projection = await api.saveSettings(saveRequest(p, state.draft));
    state.draft = rebaseDraft(state.projection, state.draft);
    state.error = "";
    state.busy = "";
    toast("Saved.");
    if (effect.reload && !effect.restart && state.projection.can_reload
        && state.projection.model_reload_required) {
      await reload();
      return;
    }
  } catch (error) {
    state.busy = "";
    if (error instanceof CoreError && error.code === "SETTINGS_CONFLICT") {
      await load({ keepDraft: true });
      state.notice = "Settings changed elsewhere while you were editing. Your edits are kept; check them and save again.";
    } else {
      state.error = message(error);
    }
  }
  renderAll();
}

async function refreshFromDisk() {
  try {
    state.projection = await api.refreshSettings();
    state.draft = rebaseDraft(state.projection, state.draft);
    state.error = "";
    toast("Loaded the settings file.");
  } catch (error) {
    state.error = message(error);
  }
  renderAll();
}

els.save.addEventListener("click", save);
els.discard.addEventListener("click", () => {
  state.draft = {};
  state.invalid = {};
  renderAll();
});
document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
    event.preventDefault();
    if (!els.save.disabled && !els.savebar.hidden) save();
  }
});
// Edits made elsewhere (the tray, another window) show up when the window is focused again.
window.addEventListener("focus", () => { if (!state.busy) load({ keepDraft: true }); });

document.body.append(el("datalist", { id: "gpu-choices" },
  el("option", { value: "auto" }), el("option", { value: "all" })));

const wanted = new URLSearchParams(location.search).get("category");
if (wanted) state.category = wanted;
renderAll();
await load({ keepDraft: false });
