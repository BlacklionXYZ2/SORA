// Shared window behaviour: title-bar buttons, dragging and the host's backdrop report.
import { RESIZE_EDGES, hosted, onHostMessage, send } from "./bridge.js";
import { icon } from "./icons.js";

export function setUpWindow(root = document) {
  const titlebar = root.querySelector(".titlebar");
  const controls = root.querySelector(".window-controls");
  if (controls) {
    controls.innerHTML = `
      <button type="button" data-action="window.minimize" title="Minimise">${icon("minimize", "Minimise")}</button>
      <button type="button" data-action="window.maximize" title="Maximise">${icon("maximize", "Maximise")}</button>
      <button type="button" class="close" data-action="window.hide" title="Close">${icon("close", "Close")}</button>`;
    controls.addEventListener("click", (event) => {
      const action = event.target.closest("button")?.dataset.action;
      if (action) send(action);
    });
  }
  if (titlebar) {
    // The host turns this into a native caption drag (snap and Aero Shake keep working).
    titlebar.addEventListener("pointerdown", (event) => {
      if (event.button === 0 && !event.target.closest("button")) send("window.drag");
    });
    titlebar.addEventListener("dblclick", (event) => {
      if (!event.target.closest("button")) send("window.maximize");
    });
  }
  if (hosted) {
    // Thin invisible grips along the edges; the host turns them into native resizing.
    for (const edge of RESIZE_EDGES) {
      const grip = document.createElement("div");
      grip.className = `resize-grip ${edge}`;
      grip.addEventListener("pointerdown", (event) => {
        if (event.button === 0) send("window.resize", { edge });
      });
      document.body.append(grip);
    }
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !event.defaultPrevented) send("window.hide");
  });
  onHostMessage((message) => {
    if (message.type === "host.backdrop") {
      const root = document.documentElement;
      root.dataset.backdrop = String(message.kind || "none");
      // Match Windows' own rounded corners so the glass and the window edge line up.
      const radius = Number(message.cornerRadius);
      if (Number.isFinite(radius) && radius >= 0 && radius <= 40) {
        root.style.setProperty("--radius-window", `${radius}px`);
      }
    }
  });
  if (!hosted) document.body.classList.add("preview-desktop");
  send("panel.ready");
}
