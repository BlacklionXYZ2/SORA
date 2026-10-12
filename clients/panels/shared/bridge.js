// Typed messages between a panel page and SoraShell. The host validates every message and
// drops anything it does not recognise (PanelBridge.cs); keep the two lists in step.

export const HOST_MESSAGES = Object.freeze([
  "window.close", "window.hide", "window.minimize", "window.maximize", "window.drag",
  "window.resize", "panel.open", "panel.ready", "file.pick", "panel.dirty", "panel.busy",
  "prefs.save", "prefs.reload", "prefs.recover", "placement.reset",
  "memory.presented", "memory.highlight-cleared",
]);
export const RESIZE_EDGES = Object.freeze(["n", "s", "e", "w", "ne", "nw", "se", "sw"]);
/** What a file picker may choose: model files, programs, folders, any file, or an attachment. */
export const PICK_KINDS = Object.freeze(["gguf", "exe", "dir", "file", "attachment"]);
export const OPENABLE_PANELS = Object.freeze([
  "chat", "settings", "voice", "memory", "activity", "agents", "paths", "appearance",
]);
/** UI preference values the Appearance page may save (host-local, never Core). */
export const THEMES = Object.freeze(["Dark", "System"]);
export const SHORTCUTS = Object.freeze(["None", "CtrlAltSpace", "CtrlAltS"]);
const APPEARANCE_FIELDS = ["theme", "textScale", "shortcut", "chatCompact", "chatPinned",
  "showTechnicalDetail", "reducedMotion"];
const REQUEST_ID = /^[A-Za-z0-9_-]{1,64}$/;
const HOST_REQUESTS = ["prefs.save", "prefs.reload", "prefs.recover", "placement.reset"];

/** Exactly the seven appearance fields, each a value the host accepts. */
export function validAppearance(values) {
  if (!values || typeof values !== "object" || Array.isArray(values)) return false;
  const keys = Object.keys(values);
  return keys.length === APPEARANCE_FIELDS.length && APPEARANCE_FIELDS.every((key) => keys.includes(key))
    && THEMES.includes(values.theme) && SHORTCUTS.includes(values.shortcut)
    && Number.isInteger(values.textScale) && values.textScale >= 85 && values.textScale <= 175
    && ["chatCompact", "chatPinned", "showTechnicalDetail", "reducedMotion"]
      .every((key) => typeof values[key] === "boolean");
}

function validRect(rect) {
  return rect && typeof rect === "object" && ["x", "y", "width", "height"]
    .every((key) => Number.isFinite(rect[key]) && Math.abs(rect[key]) <= 100000)
    && rect.width > 0 && rect.height > 0;
}

const webview = globalThis.chrome?.webview;

/** True inside SoraShell; false in a browser preview. */
export const hosted = Boolean(webview);

export function send(type, detail = {}) {
  if (!HOST_MESSAGES.includes(type)) throw new TypeError(`Unknown host message: ${type}`);
  if (type === "panel.open" && !OPENABLE_PANELS.includes(detail.panel)) {
    throw new TypeError(`Unknown panel: ${detail.panel}`);
  }
  // Optional exact item to select in the opened panel (a task ID for Activity).
  if (type === "panel.open" && detail.select !== undefined
      && !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(String(detail.select))) {
    throw new TypeError(`Invalid selection: ${detail.select}`);
  }
  if (type === "window.resize" && !RESIZE_EDGES.includes(detail.edge)) {
    throw new TypeError(`Unknown edge: ${detail.edge}`);
  }
  if (type === "panel.dirty" && typeof detail.dirty !== "boolean") {
    throw new TypeError("panel.dirty needs dirty: true or false");
  }
  if (type === "panel.busy" && typeof detail.busy !== "boolean") {
    throw new TypeError("panel.busy needs busy: true or false");
  }
  if (HOST_REQUESTS.includes(type)
      && (typeof detail.requestId !== "string" || !REQUEST_ID.test(detail.requestId))) {
    throw new TypeError(`Invalid request ID for ${type}`);
  }
  if (type === "prefs.save" && (!validAppearance(detail.values) || !validAppearance(detail.baseline))) {
    throw new TypeError("prefs.save needs the seven appearance values and their baseline");
  }
  if (type === "memory.presented" && (
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(String(detail.requestId))
    || !["selected", "already-visible", "unavailable"].includes(detail.status)
    || (detail.status === "unavailable" ? detail.anchor != null : !validRect(detail.anchor)))) {
    throw new TypeError("memory.presented needs the request, a status and (when shown) where");
  }
  if (type === "file.pick" && (!PICK_KINDS.includes(detail.kind)
      || typeof detail.requestId !== "string" || !REQUEST_ID.test(detail.requestId)
      || (detail.start !== undefined && (typeof detail.start !== "string" || detail.start.length > 260)))) {
    throw new TypeError(`Invalid file request: ${detail.kind}`);
  }
  const message = { type, ...detail };
  if (webview) webview.postMessage(message);
  return message;
}

/** Messages from the host, such as {type: "host.backdrop", kind: "system", cornerRadius: 8}. */
export function onHostMessage(listener) {
  if (!webview) return () => {};
  const handler = (event) => {
    const data = event.data;
    if (data && typeof data === "object" && typeof data.type === "string") listener(data);
  };
  webview.addEventListener("message", handler);
  return () => webview.removeEventListener("message", handler);
}

let requestCounter = 0;
const nextRequestId = (prefix) => `${prefix}-${Date.now().toString(36)}-${(requestCounter += 1)}`;

/**
 * Ask the host to do something only it can (save UI preferences, reset window placement).
 * Resolves to {ok, error}. Outside SoraShell it resolves to a refusal that says so.
 */
export function hostRequest(type, detail = {}) {
  if (!HOST_REQUESTS.includes(type)) throw new TypeError(`Unknown host request: ${type}`);
  if (!webview) {
    send(type, { ...detail, requestId: "preview" });
    return Promise.resolve({ ok: false, error: "This works in SORA's app, not in a browser preview." });
  }
  const requestId = nextRequestId("req");
  return new Promise((resolve) => {
    const stop = onHostMessage((message) => {
      if (message.type === "host.result" && message.requestId === requestId) {
        stop();
        resolve({ ok: message.ok === true, error: typeof message.error === "string" ? message.error : "" });
      }
    });
    send(type, { ...detail, requestId });
  });
}

/**
 * Ask the host for a native file or folder dialog. Resolves to the chosen path, or null when the
 * owner cancels. Outside SoraShell (browser preview) it asks for a typed path instead.
 */
export function pickFile(kind, { prompt = globalThis.prompt, start } = {}) {
  if (!webview) {
    const typed = prompt?.("Path (the native picker opens in SORA's app):", "");
    return Promise.resolve(typed ? typed.trim() : null);
  }
  const requestId = nextRequestId("pick");
  return new Promise((resolve) => {
    const stop = onHostMessage((message) => {
      if (message.type === "host.file" && message.requestId === requestId) {
        stop();
        resolve(typeof message.path === "string" && message.path ? message.path : null);
      }
    });
    send("file.pick", start ? { kind, requestId, start } : { kind, requestId });
  });
}
