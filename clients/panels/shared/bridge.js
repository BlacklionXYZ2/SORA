// Typed messages between a panel page and SoraShell. The host validates every message and
// drops anything it does not recognise (PanelBridge.cs); keep the two lists in step.

export const HOST_MESSAGES = Object.freeze([
  "window.close", "window.hide", "window.minimize", "window.maximize", "window.drag",
  "window.resize", "panel.open", "panel.ready",
]);
export const RESIZE_EDGES = Object.freeze(["n", "s", "e", "w", "ne", "nw", "se", "sw"]);
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
  if (type === "window.resize" && !RESIZE_EDGES.includes(detail.edge)) {
    throw new TypeError(`Unknown edge: ${detail.edge}`);
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
