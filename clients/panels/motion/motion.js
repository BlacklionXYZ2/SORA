import { CoreApi, CoreError } from "../shared/api.js";
import { hosted, send as sendToHost } from "../shared/bridge.js";
import { icon } from "../shared/icons.js";
import { setUpWindow } from "../shared/window.js";
import {
  ENGINE_ICONS, STATE_LABELS, SELECTABLE, activeChoice, changes, choiceLabel, choiceUsable,
  customVersions, engineEntry, measureRows, project, readPreview, sameChoice, saveRequest,
  savedChoice, selectedModel, statusNotice, withVersion,
} from "./motion-model.js";

const api = new CoreApi();
const els = Object.fromEntries(["notices", "sources", "options", "details", "preview",
  "preview-empty", "preview-label", "preview-time", "play", "measures", "savebar", "savebar-text",
  "save", "discard", "head-icon"].map((id) => [id.replace(/-(\w)/g, (_, c) => c.toUpperCase()),
  document.getElementById(id)]));
const state = {
  projection: null, catalog: null, saved: null, draft: null, status: null,
  error: "", busy: false, message: "", reloading: false,
};
let statusTimer = 0;
const previews = new Map(); // preview name → clip (or an error string)
// name: the preview shown, "" for none; null until the first render decides.
const player = { clip: null, name: null, start: performance.now(), paused: false, pausedAt: 0 };
let reportedDirty = false;

setUpWindow();
els.headIcon.innerHTML = icon("motion");
if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) player.paused = true;

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "html") node.innerHTML = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function messageOf(error) {
  return error instanceof CoreError ? error.message : String(error?.message ?? error);
}

// ---------- loading and saving ----------

async function load({ keepDraft = false } = {}) {
  try {
    const [projection, catalog] = await Promise.all([api.settings(), api.motionCatalog()]);
    state.projection = projection;
    state.catalog = catalog;
    state.saved = savedChoice(projection);
    if (!keepDraft || !state.draft) state.draft = state.saved ? { ...state.saved } : null;
    state.error = state.saved ? "" : "This Core has no motion settings yet. Update SORA and restart it.";
  } catch (error) {
    state.error = `Motion settings are unavailable: ${messageOf(error)}`;
  }
  await loadStatus();
  renderAll();
}

// What moves her now. While a model is starting, check again every second.
async function loadStatus() {
  clearTimeout(statusTimer);
  try { state.status = await api.motionStatus(); } catch { state.status = null; }
  if (statusNotice(state.status, state.catalog)?.busy) {
    statusTimer = setTimeout(async () => { await loadStatus(); renderNotices(); }, 1000);
  }
}

// Reload motion model: applies the saved choice now. Core stops the old engine, records her for
// a few seconds while the new one loads, then hands her over.
async function reloadMotion() {
  if (state.reloading || !state.projection) return;
  state.reloading = true; renderNotices(); sendToHost("panel.busy", { busy: true });
  try {
    const result = await api.reloadMotion(state.projection.settings_revision);
    state.projection = result.settings;
    state.status = result.motion;
    state.message = "";
  } catch (error) {
    state.message = `Not reloaded: ${messageOf(error)}`;
  } finally {
    state.reloading = false; sendToHost("panel.busy", { busy: false });
    await load({ keepDraft: true });
  }
}

async function save() {
  if (state.busy || !state.projection || !choiceUsable(state.catalog, state.draft)) return;
  state.busy = true; state.message = ""; renderSavebar(); sendToHost("panel.busy", { busy: true });
  try {
    await api.saveSettings(saveRequest(state.projection, state.saved, state.draft));
    state.message = "Saved. Reload motion model to use it now.";
    await load();
  } catch (error) {
    state.message = error?.status === 409
      ? "Settings changed elsewhere. Reloaded them; your choice is kept, so save again."
      : `Not saved: ${messageOf(error)}`;
    if (error?.status === 409) await load({ keepDraft: true });
  } finally {
    state.busy = false; sendToHost("panel.busy", { busy: false }); renderAll();
  }
}

function setDraft(next) {
  state.draft = next; state.message = ""; renderAll();
}

// ---------- rendering ----------

function renderAll() {
  renderNotices(); renderSources(); renderOptions(); renderDetails(); renderMeasures();
  renderSavebar(); loadPreview();
  const dirty = Object.keys(changes(state.saved, state.draft)).length > 0;
  if (dirty !== reportedDirty) { reportedDirty = dirty; sendToHost("panel.dirty", { dirty }); }
}

function banner(text, kind = "", action = null) {
  return el("div", { class: `banner ${kind}` },
    el("span", { class: "banner-icon", html: icon(kind === "error" ? "alert" : "info") }),
    el("span", { class: "banner-text" }, text), action);
}

function renderNotices() {
  const items = [];
  if (state.error) {
    items.push(banner(state.error, "error", el("button", { class: "btn", type: "button", onclick: () => load() }, "Retry")));
  }
  const active = activeChoice(state.projection);
  const pending = state.saved && active && !sameChoice(state.saved, active);
  const reload = (primary) => el("button", { class: `btn${primary ? " primary" : ""}`, type: "button",
    disabled: state.reloading || !state.projection, onclick: reloadMotion },
  state.reloading ? "Reloading…" : "Reload motion model");
  if (pending) {
    items.push(banner(`Saved: ${choiceLabel(state.catalog, state.saved)}. She is still moving with `
      + `${choiceLabel(state.catalog, active)} until you reload the motion model.`, "", reload(true)));
  }
  const notice = statusNotice(state.status, state.catalog);
  if (notice) items.push(banner(notice.text, notice.kind, !pending && !notice.busy && state.status?.state !== "unavailable" ? reload(false) : null));
  if (state.draft?.engine === "custom") {
    items.push(banner("SORA's own trained models can be chosen and saved, but can't drive her yet: "
      + "only ARDY runs live so far.", "warn"));
  }
  if (state.catalog?.note) items.push(banner(state.catalog.note));
  els.notices.replaceChildren(...items);
}

function badge(text, kind = "") { return el("span", { class: `badge ${kind}` }, text); }

function stateBadge(stateName) {
  const kind = { ready: "", experimental: "warn", missing: "down", planned: "muted" }[stateName] ?? "muted";
  return badge(STATE_LABELS[stateName] ?? stateName, kind);
}

function engineState(engine) {
  const models = engine?.models ?? [];
  if (models.some((m) => m.state === "ready")) return "ready";
  if (models.some((m) => m.state === "experimental")) return "experimental";
  return models.some((m) => m.state === "missing") ? "missing" : "planned";
}

function renderSources() {
  const engines = state.catalog?.engines ?? [];
  els.sources.replaceChildren(...engines.map((engine) => {
    const usable = engine.models.some((m) => SELECTABLE.has(m.state));
    const checked = state.draft?.engine === engine.id;
    return el("button", {
      class: "source", type: "button", role: "radio", "aria-checked": String(checked),
      disabled: !usable || !state.draft || state.busy,
      onclick: () => {
        if (engine.id === "custom") {
          const first = customVersions(state.catalog).reverse()
            .find((v) => v.sizes.some((m) => SELECTABLE.has(m.state)));
          const keep = state.draft.engine === "custom" ? state.draft.version : first?.version;
          setDraft(withVersion(state.catalog, state.draft, keep ?? state.draft.version));
        } else setDraft({ ...state.draft, engine: engine.id });
      },
    },
    el("span", { class: "source-top" }, el("span", { html: icon(ENGINE_ICONS[engine.id] ?? "models") }),
      el("span", { class: "source-name" }, engine.name), el("span", { class: "radio", "aria-hidden": "true" })),
    el("span", { class: "source-text" }, engine.summary),
    el("span", { class: "badges" }, stateBadge(engineState(engine)),
      engine.id === "custom" && badge(`${customVersions(state.catalog).length} versions`, "muted")));
  }));
}

function pill(label, note, pressed, onclick, disabled = false) {
  return el("button", { class: "pill", type: "button", "aria-pressed": String(pressed),
    disabled: disabled || state.busy, onclick }, label, note && el("small", {}, note));
}

function renderOptions() {
  const draft = state.draft;
  if (!draft || !state.catalog) { els.options.replaceChildren(); return; }
  const parts = [];
  if (draft.engine === "algorithmic") {
    parts.push(el("h2", {}, "Algorithmic system"),
      el("p", { class: "sub" }, "Nothing to choose: her built-in poses and gait. This is also what she falls back to."));
  } else if (draft.engine === "ardy") {
    const ardy = engineEntry(state.catalog, "ardy");
    parts.push(el("h2", {}, "ARDY settings"), el("p", { class: "sub" }, ardy?.licence ?? ""),
      el("div", { class: "option-title" }, "Precision"),
      el("div", { class: "pills" }, ...["fp16", "fp32"].map((precision) => {
        const model = ardy?.models.find((m) => m.version === `Core ${precision}`);
        return pill(precision, precision === "fp16" ? "less memory" : "cleaner at rest",
          draft.precision === precision, () => setDraft({ ...draft, precision }),
          !model || !SELECTABLE.has(model.state));
      })),
      el("div", { class: "option-title" }, "Diffusion steps"),
      el("div", { class: "pills" }, ...[2, 4, 6, 8, 10].map((steps) => pill(String(steps),
        steps === 4 ? "recommended" : steps === 2 ? "too few" : steps >= 6 ? "slower" : "",
        draft.steps === steps, () => setDraft({ ...draft, steps })))),
      el("div", { class: "option-note", html: icon("info") + "<span>4 steps keeps up in real time on this PC while "
        + "she replans every 0.4 s. More steps take longer than she has; 2 loses walking speed.</span>" }));
  } else {
    const versions = customVersions(state.catalog);
    const current = versions.find((v) => v.version === draft.version);
    parts.push(el("h2", {}, "Model version"),
      el("p", { class: "sub" }, "SORA's own trained versions, oldest to newest."),
      el("div", { class: "pills" }, ...versions.map((v) => {
        const usable = v.sizes.some((m) => SELECTABLE.has(m.state));
        return pill(v.version, usable ? "" : "not trained", draft.version === v.version,
          () => setDraft(withVersion(state.catalog, draft, v.version)), !usable);
      })),
      el("div", { class: "option-title" }, "Model size"),
      el("div", { class: "pills" }, ...(current?.sizes ?? []).map((m) => pill(m.size,
        m.state === "planned" ? "planned" : m.state === "missing" ? "missing" : m.parameters
          ? `${m.parameters.toLocaleString()} params` : "",
        draft.size === m.size, () => setDraft({ ...draft, size: m.size }), !SELECTABLE.has(m.state)))),
      el("div", { class: "option-note", html: icon("info") + "<span>Every version so far is experimental: none "
        + "has passed the motion core's quality gate. Larger sizes appear here once they are trained.</span>" }));
  }
  els.options.replaceChildren(...parts);
}

function renderDetails() {
  const draft = state.draft;
  const model = selectedModel(state.catalog, draft);
  const engine = engineEntry(state.catalog, draft?.engine);
  if (!draft || !engine) { els.details.replaceChildren(); return; }
  const title = draft.engine === "algorithmic" ? "Algorithmic" : draft.engine === "ardy"
    ? `ARDY · Core ${draft.precision}` : `${draft.version} · ${draft.size}`;
  const saved = state.saved && sameChoice(state.saved, draft);
  els.details.replaceChildren(
    el("div", { class: "detail-head" }, el("span", { class: "name" }, title),
      model && stateBadge(model.state), saved && badge("Saved", "muted")),
    el("p", { class: "detail-text" }, model?.summary || engine.summary),
    el("h2", { id: "details-title" }, "Model information"),
    el("dl", { class: "info" },
      el("dt", {}, "Source"), el("dd", {}, engine.name),
      el("dt", {}, "Model"), el("dd", {}, model ? `${model.version}${model.size ? `, ${model.size}` : ""}` : "Not in the catalogue"),
      model?.parameters && [el("dt", {}, "Parameters"), el("dd", {}, model.parameters.toLocaleString())],
      draft.engine === "ardy" && [el("dt", {}, "Diffusion steps"), el("dd", {}, String(draft.steps))],
      engine.licence && [el("dt", {}, "Licence"), el("dd", {}, engine.licence)],
      el("dt", {}, "Status"), el("dd", {}, el("span", { class: `status-dot ${model?.state ?? "missing"}` }),
        model ? STATE_LABELS[model.state] : "Missing"),
      el("dt", {}, "Applies"), el("dd", {}, "With Reload motion model, without restarting SORA"),
      state.catalog?.lab_path && [el("dt", {}, "motion-lab"), el("dd", {}, state.catalog.lab_path)]));
}

function renderMeasures() {
  const model = selectedModel(state.catalog, state.draft);
  const rows = measureRows(state.catalog, model);
  if (!rows.length) {
    els.measures.replaceChildren(el("div", { class: "measures-empty" },
      state.draft?.engine === "algorithmic"
        ? "The algorithmic system plays fixed poses, so there's nothing to measure here."
        : "No measurements for this model yet."));
    return;
  }
  els.measures.replaceChildren(...rows.map((row) => el("div", { class: "measure" },
    el("div", { class: "measure-head" }, el("span", {}, row.label), el("span", { class: "value" }, row.text)),
    el("div", { class: "measure-bar" }, el("span", { class: "fill", style: `width:${(row.width * 100).toFixed(1)}%` }),
      row.referenceWidth !== null && el("span", { class: "ref", style: `left:calc(${(row.referenceWidth * 100).toFixed(1)}% - 1px)`,
        title: `Real motion capture: ${row.referenceText}` })),
    el("div", { class: "measure-note" }, row.reference !== null ? `Real motion capture: ${row.referenceText}`
      : row.better === "lower" ? "Lower is better." : ""))),
  model?.measures?.note && el("div", { class: "measure-note" }, model.measures.note));
}

function renderSavebar() {
  const pending = Object.keys(changes(state.saved, state.draft)).length > 0;
  const usable = choiceUsable(state.catalog, state.draft);
  els.savebar.hidden = !pending && !state.message;
  els.savebarText.textContent = state.busy ? "Saving…" : state.message
    || (pending ? `${choiceLabel(state.catalog, state.draft)}, applied when you reload the motion model.`
      + (usable ? "" : " This model can't be selected.") : "");
  els.save.disabled = state.busy || !pending || !usable;
  els.discard.disabled = state.busy || !pending;
}

els.save.addEventListener("click", save);
els.discard.addEventListener("click", () => setDraft(state.saved ? { ...state.saved } : null));
els.play.addEventListener("click", () => {
  const now = performance.now();
  if (player.paused) { player.start += now - player.pausedAt; player.paused = false; }
  else { player.paused = true; player.pausedAt = now; }
  els.play.textContent = player.paused ? "Play" : "Pause";
});
els.play.textContent = player.paused ? "Play" : "Pause";

// ---------- preview ----------

async function loadPreview() {
  const model = selectedModel(state.catalog, state.draft);
  const name = model?.preview ?? "";
  if (name === player.name) return;
  player.name = name; player.clip = null; player.start = performance.now();
  els.previewLabel.textContent = "Motion this model generated.";
  els.play.hidden = true;
  if (!name) {
    showEmpty(state.draft?.engine === "algorithmic"
      ? "The algorithmic system is what you already see her do."
      : state.draft?.engine === "ardy" ? "No preview for this precision yet: fp16 has one."
        : "No preview for this model yet.");
    return;
  }
  if (!previews.has(name)) {
    try { previews.set(name, readPreview(await api.motionPreview(name)) ?? "The preview file is malformed."); }
    catch (error) { previews.set(name, `Preview unavailable: ${messageOf(error)}`); }
  }
  if (player.name !== name) return;
  const clip = previews.get(name);
  if (typeof clip === "string") { showEmpty(clip); return; }
  player.clip = clip; els.previewEmpty.hidden = true; els.previewLabel.textContent = clip.label;
  els.play.hidden = false;
}

function showEmpty(text) {
  els.previewEmpty.hidden = false; els.previewEmpty.textContent = text;
  const ctx = els.preview.getContext("2d");
  ctx.clearRect(0, 0, els.preview.width, els.preview.height);
  els.previewTime.textContent = "";
}

function draw(now) {
  const clip = player.clip;
  if (clip) {
    const t = ((player.paused ? player.pausedAt : now) - player.start) / 1000;
    const duration = clip.frames.length / clip.fps;
    const position = ((t % duration) + duration) % duration;
    const index = Math.min(clip.frames.length - 1, Math.floor(position * clip.fps));
    const frame = clip.frames[index];
    const root = frame[0];
    const canvas = els.preview;
    const ctx = canvas.getContext("2d");
    const { width, height } = canvas;
    ctx.clearRect(0, 0, width, height);
    const view = { scale: height * 0.42, cx: width / 2, cy: height * 0.86 };
    // Floor grid, moving with her so walking reads as travel.
    ctx.strokeStyle = "rgba(120, 170, 255, 0.16)"; ctx.lineWidth = 1;
    const step = 0.5, reach = 3;
    for (let k = -reach; k <= reach; k += step) {
      const gx = Math.round(root[0] / step) * step + k, gz = Math.round(root[2] / step) * step + k;
      line(ctx, project([gx, 0, root[2] - reach], root, view), project([gx, 0, root[2] + reach], root, view));
      line(ctx, project([root[0] - reach, 0, gz], root, view), project([root[0] + reach, 0, gz], root, view));
    }
    // Bones, with a soft glow, and joints.
    ctx.lineCap = "round"; ctx.shadowColor = "rgba(80, 160, 255, 0.8)"; ctx.shadowBlur = 10;
    ctx.strokeStyle = "#7cc4ff"; ctx.lineWidth = 3.2;
    clip.parents.forEach((parent, j) => {
      if (parent >= 0) line(ctx, project(frame[parent], root, view), project(frame[j], root, view));
    });
    ctx.shadowBlur = 0; ctx.fillStyle = "#e8eef8";
    const head = clip.names.findIndex((n) => /^head$/i.test(n));
    if (head >= 0) {
      const [hx, hy] = project(frame[head], root, view);
      ctx.beginPath(); ctx.arc(hx, hy - view.scale * 0.06, view.scale * 0.07, 0, Math.PI * 2);
      ctx.strokeStyle = "#7cc4ff"; ctx.lineWidth = 2.5; ctx.stroke();
    }
    els.previewTime.textContent = `${position.toFixed(1)} s / ${duration.toFixed(0)} s`;
  }
  requestAnimationFrame(draw);
}

function line(ctx, [x1, y1], [x2, y2]) { ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke(); }

requestAnimationFrame(draw);
window.addEventListener("focus", () => { if (!state.busy && !Object.keys(changes(state.saved, state.draft)).length) load(); });
if (!hosted) document.title = "SORA · Motion (preview)";
load();
