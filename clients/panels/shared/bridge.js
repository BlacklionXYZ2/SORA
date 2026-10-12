// Typed messages between a panel page and SoraShell. The host validates every message and
// drops anything it does not recognise (PanelBridge.cs); keep the two lists in step.

export const HOST_MESSAGES = Object.freeze([
  "window.close", "window.hide", "window.minimize", "window.maximize", "window.drag",
  "window.resize", "panel.open", "panel.ready", "file.pick", "panel.dirty",
]);
export const RESIZE_EDGES = Object.freeze(["n", "s", "e", "w", "ne", "nw", "se", "sw"]);
/** What a file picker may choose: model files, programs, folders, any file, or an attachment. */
export const PICK_KINDS = Object.freeze(["gguf", "exe", "dir", "file", "attachment"]);
export const OPENABLE_PANELS = Object.freeze([
  "chat", "settings", "voice", "memory", "activity", "agents", "paths", "appearance",
]);

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
  if (type === "file.pick" && (!PICK_KINDS.includes(detail.kind)
      || !/^[A-Za-z0-9_-]{1,64}$/.test(String(detail.requestId))
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

let pickCounter = 0;

/**
 * Ask the host for a native file or folder dialog. Resolves to the chosen path, or null when the
 * owner cancels. Outside SoraShell (browser preview) it asks for a typed path instead.
 */
export function pickFile(kind, { prompt = globalThis.prompt, start } = {}) {
  if (!webview) {
    const typed = prompt?.("Path (the native picker opens in SORA's app):", "");
    return Promise.resolve(typed ? typed.trim() : null);
  }
  const requestId = `pick-${Date.now().toString(36)}-${(pickCounter += 1)}`;
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
