import { CoreApi } from "../shared/api.js";
import { hosted, onHostMessage, send as sendToHost } from "../shared/bridge.js";
import { icon } from "../shared/icons.js";
import { setUpWindow } from "../shared/window.js";
import { HELP, VoiceSession } from "./voice-model.js";

const POLL_MS = 2500;
const HIDDEN_POLL_MS = 10000; // a hidden window keeps the status fresh, more gently
const api = new CoreApi();
const els = {
  banner: document.getElementById("banner"),
  status: document.getElementById("status"),
  hold: document.getElementById("hold"),
  holdIcon: document.getElementById("hold-icon"),
  holdLabel: document.getElementById("hold-label"),
  holdHint: document.getElementById("hold-hint"),
  start: document.getElementById("start"),
  stopOutput: document.getElementById("stop-output"),
  stop: document.getElementById("stop"),
  closeAudio: document.getElementById("close-audio"),
  settings: document.getElementById("settings"),
  outcome: document.getElementById("outcome"),
  devices: document.getElementById("devices"),
  devicesStale: document.getElementById("devices-stale"),
  help: document.getElementById("help"),
};
// What is on screen now, so a poll that changes nothing does not rebuild (or re-announce) it.
const shown = { status: "", devices: "", outcome: null, banner: "" };
let reportedBusy = false;
let toastTimer = 0;
let pollTimer = 0;
let pollRun = 0;

const session = new VoiceSession(api, { onChange: () => render() });

setUpWindow();
// Host messages first, before any await: window.js has already sent panel.ready.
onHostMessage((data) => {
  if (data.type === "host.core" && typeof data.canUseCore === "boolean") {
    session.setCanUseCore(data.canUseCore);
    if (data.canUseCore) poll();
  }
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

// ---------- rendering ----------

function render() {
  const view = session.view();
  renderBanner(view.banner);
  renderStatus(view);
  renderControls(view.controls);
  renderOutcome(view.outcome);
  renderDevices(view.devices);
  // Tell SoraShell, so Quit waits while the microphone is held or a voice request is in flight.
  if (view.busy !== reportedBusy) {
    reportedBusy = view.busy;
    sendToHost("panel.busy", { busy: view.busy });
  }
}

function renderBanner(text) {
  if (text === shown.banner) return;
  shown.banner = text;
  els.banner.hidden = !text;
  els.banner.replaceChildren();
  if (!text) return;
  els.banner.insertAdjacentHTML("afterbegin", icon("alert"));
  els.banner.append(el("span", {}, text));
}

function renderStatus({ microphone, status, dialogue }) {
  const signature = JSON.stringify([microphone, status, dialogue]);
  if (signature === shown.status) return;
  shown.status = signature;
  const parts = [el("div", { class: `line mic ${microphone.tone}` },
    el("span", { class: "mic-dot", "aria-hidden": "true" }),
    el("span", { class: "mic-text" }, microphone.text))];
  if (status.kind === "status") {
    parts.push(el("div", { class: "line state-line" },
      el("span", { class: `state ${status.tone}` }, status.label),
      status.message && el("span", { class: "visually-hidden" }, ": "),
      status.message && el("span", { class: "message" }, status.message)));
    const flags = [
      status.listening && el("span", { class: "chip flag listening" }, "Always-on listening is on"),
      status.hearing && el("span", { class: "chip flag hearing" }, "Hearing you now"),
    ].filter(Boolean);
    if (flags.length) parts.push(el("div", { class: "flags" }, ...flags));
  } else if (status.kind === "disabled") {
    parts.push(el("div", { class: "line state-line" },
      el("span", { class: "state off" }, "Off"),
      el("span", { class: "message" }, status.text)));
    if (status.message) parts.push(el("p", { class: "notice worker-note" }, `The voice worker says: ${status.message}`));
  } else {
    parts.push(el("div", { class: "line reason", html: icon("alert") }, el("span", {}, status.text)));
  }
  parts.push(el("div", { class: `line model${dialogue.stale ? " stale" : ""}`, html: icon("models") },
    el("span", {}, dialogue.text)));
  els.status.replaceChildren(...parts);
}

function renderControls(controls) {
  els.start.disabled = !controls.start;
  els.start.classList.toggle("primary", controls.start); // the one to press now, when it can be
  els.stopOutput.disabled = !controls.stopOutput;
  els.stop.disabled = !controls.stop;
  els.closeAudio.disabled = !controls.close;
  // Only properties change here: the hold button is never rebuilt, so a press keeps its capture.
  els.hold.disabled = !controls.hold;
  els.hold.dataset.hold = controls.holdState;
  if (els.holdLabel.textContent !== controls.holdLabel) els.holdLabel.textContent = controls.holdLabel;
  if (els.holdHint.textContent !== controls.holdHint) els.holdHint.textContent = controls.holdHint;
}

function renderOutcome(outcome) {
  if (outcome === shown.outcome) return;
  shown.outcome = outcome;
  els.outcome.hidden = !outcome;
  if (!outcome) return;
  els.outcome.className = `outcome selectable ${outcome.tone}`;
  els.outcome.replaceChildren(
    el("span", { class: "outcome-icon", html: icon(outcome.tone === "ok" ? "task" : outcome.tone === "bad" ? "alert" : "mic") }),
    el("span", {}, outcome.text));
}

function renderDevices(inventory) {
  els.devicesStale.hidden = !inventory.stale;
  els.devices.classList.toggle("stale", inventory.stale);
  const signature = JSON.stringify([inventory.rows, inventory.empty]);
  if (signature === shown.devices) return;
  shown.devices = signature;
  if (!inventory.rows.length) {
    els.devices.replaceChildren(el("p", { class: "empty-note" }, inventory.empty));
    return;
  }
  const table = el("table", { class: "data" },
    el("thead", {}, el("tr", {},
      el("th", {}, "Device key"),
      el("th", { class: "num" }, "Input"),
      el("th", { class: "num" }, "Output"),
      el("th", { class: "num" }, "Adapter"),
      el("th", { class: "copy-cell" }, el("span", { class: "visually-hidden" }, "Copy")))),
    el("tbody", {}, ...inventory.rows.map((row) => {
      const key = el("span", { class: "mono key" }, row.key);
      return el("tr", { class: row.ambiguous ? "ambiguous" : "" },
        el("td", {}, key, row.ambiguous && el("span", { class: "badge warn",
          title: "This key names more than one device, so the voice worker will not pick it." }, "Ambiguous")),
        el("td", { class: "num", title: "Input channels" }, String(row.inputs)),
        el("td", { class: "num", title: "Output channels" }, String(row.outputs)),
        el("td", { class: "num", title: row.index === null ? "Not reported" : "Adapter index" },
          row.index === null ? "—" : String(row.index)),
        el("td", { class: "copy-cell" }, el("button", {
          class: "icon-btn copy", type: "button", title: "Copy this key", "aria-label": `Copy the key ${row.key}`,
          html: icon("copy"), onclick: () => copyKey(row.key, key),
        })));
    })));
  els.devices.replaceChildren(table, inventory.ambiguous && el("p", { class: "notice ambiguous-note" },
    "A key marked Ambiguous names more than one device, so the voice worker refuses it rather than guess. Choose a device whose key appears once."));
}

async function copyKey(key, node) {
  try {
    if (!navigator.clipboard?.writeText) throw new Error("No clipboard");
    await navigator.clipboard.writeText(key);
    toast("Key copied. Paste it into Settings → Audio.");
  } catch {
    const range = document.createRange();
    range.selectNodeContents(node);
    const selection = getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    toast("Copying was blocked here, so the key is selected. Press Ctrl+C to copy it.");
  }
}

// ---------- polling ----------

async function poll() {
  const run = ++pollRun;
  clearTimeout(pollTimer);
  await Promise.all([session.readVoice(), session.readCompanion()]);
  if (run !== pollRun) return; // a newer poll owns the timer
  pollTimer = setTimeout(poll, document.visibilityState === "hidden" ? HIDDEN_POLL_MS : POLL_MS);
}

// ---------- hold to talk ----------

const discard = (reason) => session.releaseHold({ discard: true, reason });

els.hold.addEventListener("pointerdown", (event) => {
  if (event.button !== 0 || session.hold.pending || !session.controls().hold) return;
  try { els.hold.setPointerCapture(event.pointerId); } catch { /* synthetic pointer: no capture */ }
  session.pressHold();
});
els.hold.addEventListener("pointerup", (event) => { if (event.button === 0) session.releaseHold(); });
// Capture lost with the left button still down (another window took it) throws the recording away.
els.hold.addEventListener("lostpointercapture", (event) => {
  if (!session.hold.held) return;
  if (event.buttons & 1) discard("the button lost the pointer");
  else session.releaseHold();
});
els.hold.addEventListener("pointercancel", () => discard("the pointer was cancelled"));
els.hold.addEventListener("contextmenu", (event) => event.preventDefault());
// Space: no click, no page scroll, and auto-repeat is ignored. Key-up is never suppressed.
els.hold.addEventListener("keydown", (event) => {
  if (event.code !== "Space" && event.key !== " ") return;
  event.preventDefault();
  if (!event.repeat) session.pressHold();
});
els.hold.addEventListener("keyup", (event) => {
  if (event.code !== "Space" && event.key !== " ") return;
  event.preventDefault();
  session.releaseHold();
});
els.hold.addEventListener("blur", () => {
  discard(document.hasFocus() ? "the Hold to talk button lost focus" : "the window lost focus");
});
window.addEventListener("blur", () => discard("the window lost focus"));
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") discard("the window was hidden");
  else poll();
});
window.addEventListener("pagehide", () => discard("the window was closing"));
// Escape hides the window (window.js); a held recording is thrown away first, and says so.
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && session.hold.held) discard("you pressed Escape, which hides this window");
}, true);

// ---------- other controls ----------

els.start.addEventListener("click", () => session.perform("start"));
els.stopOutput.addEventListener("click", () => session.perform("stop_output"));
els.stop.addEventListener("click", () => session.perform("stop"));
els.closeAudio.addEventListener("click", () => session.perform("close"));
els.settings.addEventListener("click", () => {
  sendToHost("panel.open", { panel: "settings", select: "Audio" });
  if (!hosted) toast("Settings opens in SORA's app.");
});

// ---------- start ----------

els.holdIcon.innerHTML = icon("mic");
els.settings.insertAdjacentHTML("afterbegin", icon("advanced"));
els.start.insertAdjacentHTML("afterbegin", icon("bolt"));
els.stopOutput.insertAdjacentHTML("afterbegin", icon("audio"));
els.stop.insertAdjacentHTML("afterbegin", icon("stop"));
els.closeAudio.insertAdjacentHTML("afterbegin", icon("close"));
els.help.replaceChildren(...HELP.map((line) => el("li", {}, line)));
render();
await poll();
