import { SoraApiClient } from "/api-client.js";
import { clearPairedDevice, loadPairedDevice, savePairedDevice } from "/device-vault.js";
import { ProjectionStore, SyncCoordinator } from "/sync.js";

const elements = Object.fromEntries(
  [
    "auth-panel", "auth-form", "token-input", "auth-error", "workspace", "connection-label",
    "disconnect-button", "install-button", "message-list", "message-input", "composer", "send-button",
    "mic-button", "stop-response", "activity-label", "provider-list", "task-list", "refresh-button", "trace-list",
    "trace-count", "toast",
    "pairing-form", "pairing-code-input", "device-label-input", "pairing-error",
    "reconnect-device-button", "pairing-admin", "create-pairing-button", "pairing-code-output",
    "paired-device-list",
  ].map((id) => [id, document.getElementById(id)]),
);

const api = new SoraApiClient();
const store = new ProjectionStore();
const sync = new SyncCoordinator(api, store);
let pollTimer = 0;
let pollDelay = 1000;
let installPrompt = null;
let speechRecognition = null;
let connectionMode = "none";
let dialogueRequestId = null;
let pairedRecord = null;
let activeRemoteScopes = new Set();

store.subscribe(render);

elements["auth-form"].addEventListener("submit", async (event) => {
  event.preventDefault();
  elements["auth-error"].textContent = "";
  api.setToken(elements["token-input"].value);
  elements["token-input"].value = "";
  try {
    await enterWorkspace("owner");
  } catch (error) {
    api.clearToken();
    elements["auth-error"].textContent = error.message || "Unable to connect.";
  }
});

elements["pairing-form"].addEventListener("submit", async (event) => {
  event.preventDefault();
  elements["pairing-error"].textContent = "";
  if (window.location.protocol !== "https:") {
    elements["pairing-error"].textContent = "Pairing is accepted only on Core's private HTTPS listener.";
    return;
  }
  const code = elements["pairing-code-input"].value.trim();
  const label = elements["device-label-input"].value.trim();
  if (!code || !label) return;
  const deviceId = `pwa-${crypto.randomUUID()}`;
  api.setDeviceId(deviceId);
  try {
    const claim = await api.claimPairing(code, label);
    await savePairedDevice(claim);
    pairedRecord = await loadPairedDevice();
    elements["pairing-code-input"].value = "";
    await resumePairedDevice();
  } catch (error) {
    elements["pairing-error"].textContent = error.message || "Pairing was rejected.";
  }
});

elements["reconnect-device-button"].addEventListener("click", async () => {
  elements["pairing-error"].textContent = "";
  try {
    await resumePairedDevice();
  } catch (error) {
    elements["pairing-error"].textContent = error.message || "The paired device could not reconnect.";
  }
});

elements["disconnect-button"].addEventListener("click", () => {
  window.clearTimeout(pollTimer);
  stopSpeechRecognition();
  api.clearToken();
  connectionMode = "none";
  activeRemoteScopes = new Set();
  store.update({ connected: false, initialized: false, messages: [], tasks: [], traces: [], lastSequence: 0 });
  elements.workspace.hidden = true;
  elements["auth-panel"].hidden = false;
  elements["disconnect-button"].hidden = true;
  elements["pairing-admin"].hidden = true;
  elements["reconnect-device-button"].hidden = !pairedRecord;
  elements["token-input"].focus();
});

elements["create-pairing-button"].addEventListener("click", async () => {
  elements["create-pairing-button"].disabled = true;
  try {
    const invitation = await api.createPairingInvitation("SORA browser");
    elements["pairing-code-output"].textContent = `${invitation.pairing_code} · expires ${new Date(invitation.expires_at).toLocaleTimeString()}`;
    await refreshPairedDevices();
  } catch (error) {
    showToast(error.message || "A pairing code could not be created.");
  } finally {
    elements["create-pairing-button"].disabled = false;
  }
});

elements["paired-device-list"].addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-device-id]");
  if (!button) return;
  button.disabled = true;
  try {
    await api.revokeDevice(button.dataset.deviceId);
    await refreshPairedDevices();
  } catch (error) {
    showToast(error.message || "The device could not be revoked.");
  } finally {
    button.disabled = false;
  }
});

elements.composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  const content = elements["message-input"].value.trim();
  if (!content || dialogueRequestId) return;
  const requestId = globalThis.crypto.randomUUID();
  dialogueRequestId = requestId;
  elements["stop-response"].hidden = connectionMode !== "owner";
  elements["stop-response"].disabled = connectionMode !== "owner";
  elements["send-button"].disabled = true;
  elements["activity-label"].textContent = "Thinking…";
  try {
    elements["message-input"].value = "";
    await api.dialogue(content, requestId);
    await sync.pollOnce();
  } catch (error) {
    if (!elements["message-input"].value) elements["message-input"].value = content;
    showToast(error.code === "DIALOGUE_CANCELLED"
      ? "Response stopped. Draft preserved; dispatched actions are not undone."
      : error.message || "Message could not be sent.");
  } finally {
    elements["send-button"].disabled = false;
    dialogueRequestId = null;
    elements["stop-response"].disabled = true;
    elements["stop-response"].hidden = true;
  }
});

elements["stop-response"].addEventListener("click", async () => {
  const requestId = dialogueRequestId;
  if (!requestId || connectionMode !== "owner") return;
  elements["stop-response"].disabled = true;
  try {
    const result = await api.cancelDialogue(requestId);
    if (dialogueRequestId === requestId && result.state === "already-finishing")
      showToast("Response is already finishing; check the transcript.");
  } catch (error) {
    if (dialogueRequestId === requestId) {
      elements["stop-response"].disabled = false;
      showToast(`Stop not confirmed: ${error.message}`);
    }
  }
});

elements["message-input"].addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    elements.composer.requestSubmit();
  }
});

elements["refresh-button"].addEventListener("click", async () => {
  try { await sync.synchronize(); } catch (error) { showToast(error.message); }
});

elements["task-list"].addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const taskId = button.dataset.taskId;
  button.disabled = true;
  try {
    if (button.dataset.action === "cancel") {
      await api.cancel(taskId);
    } else {
      const instruction = window.prompt("How should SORA steer this task?");
      if (!instruction?.trim()) return;
      await api.steer(taskId, instruction.trim());
    }
    await sync.pollOnce();
  } catch (error) {
    showToast(error.message || "Task action failed.");
  } finally {
    button.disabled = false;
  }
});

elements["mic-button"].addEventListener("click", () => {
  if (speechRecognition) {
    stopSpeechRecognition();
    return;
  }
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    showToast("Browser speech recognition is unavailable. The local P14 voice client remains available.");
    return;
  }
  const recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.lang = document.documentElement.lang || "en";
  recognition.onresult = (event) => {
    let transcript = "";
    let final = false;
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      transcript += event.results[index][0].transcript;
      final ||= event.results[index].isFinal;
    }
    elements["message-input"].value = transcript.trim();
    if (final) stopSpeechRecognition();
  };
  recognition.onerror = (event) => {
    showToast(`Microphone stopped: ${event.error || "recognition error"}.`);
    stopSpeechRecognition();
  };
  recognition.onend = () => stopSpeechRecognition(false);
  speechRecognition = recognition;
  elements["mic-button"].setAttribute("aria-pressed", "true");
  elements["mic-button"].textContent = "Stop";
  recognition.start();
});

function stopSpeechRecognition(abort = true) {
  const recognition = speechRecognition;
  speechRecognition = null;
  elements["mic-button"].setAttribute("aria-pressed", "false");
  elements["mic-button"].textContent = "Mic";
  if (abort && recognition) recognition.abort();
}

function schedulePoll(delay = pollDelay) {
  window.clearTimeout(pollTimer);
  pollTimer = window.setTimeout(async () => {
    try {
      await sync.pollOnce();
      pollDelay = 1000;
    } catch (error) {
      if (connectionMode === "remote" && error?.status === 401 && pairedRecord) {
        try {
          await resumePairedDevice(false);
          pollDelay = 1000;
        } catch {
          await clearPairedDevice().catch(() => {});
          pairedRecord = null;
          api.clearToken();
          connectionMode = "none";
          elements.workspace.hidden = true;
          elements["auth-panel"].hidden = false;
          elements["disconnect-button"].hidden = true;
          elements["reconnect-device-button"].hidden = true;
          elements["pairing-error"].textContent = "This device session expired or was revoked. Pair it again from the owner device.";
        }
      }
      pollDelay = Math.min(pollDelay * 2, 15000);
    }
    if (api.authenticated) schedulePoll();
  }, delay);
}

async function enterWorkspace(mode) {
  await sync.pollOnce();
  connectionMode = mode;
  render(store.state);
  elements["auth-panel"].hidden = true;
  elements.workspace.hidden = false;
  elements["disconnect-button"].hidden = false;
  elements["pairing-admin"].hidden = mode !== "owner";
  if (mode === "owner") {
    try {
      await refreshPairedDevices();
    } catch (error) {
      elements["pairing-admin"].hidden = error?.code === "REMOTE_DISABLED";
      if (error?.code !== "REMOTE_DISABLED") showToast(error.message);
    }
  }
  schedulePoll(0);
}

async function resumePairedDevice(openWorkspace = true) {
  pairedRecord ||= await loadPairedDevice();
  if (!pairedRecord) throw new Error("No paired-device credential is stored for this origin.");
  api.setDeviceId(pairedRecord.deviceId);
  const session = await api.createRemoteSession(
    pairedRecord.deviceCredential,
    pairedRecord.scopes,
  );
  activeRemoteScopes = new Set(session.scopes || []);
  api.setAuthorization("SoraSession", session.session_token);
  if (openWorkspace) await enterWorkspace("remote");
  else {
    connectionMode = "remote";
    await sync.pollOnce();
  }
}

async function refreshPairedDevices() {
  const result = await api.pairedDevices();
  elements["paired-device-list"].replaceChildren();
  for (const device of result.devices || []) {
    const item = document.createElement("li");
    item.className = "paired-device";
    const description = document.createElement("span");
    description.textContent = `${device.label} · ${device.revoked_at ? "revoked" : "paired"}`;
    item.append(description);
    if (!device.revoked_at) {
      const revoke = document.createElement("button");
      revoke.type = "button";
      revoke.className = "quiet cancel";
      revoke.dataset.deviceId = device.device_id;
      revoke.textContent = "Revoke";
      item.append(revoke);
    }
    elements["paired-device-list"].append(item);
  }
}

function render(state) {
  elements["connection-label"].textContent = state.connected ? "Core connected" : state.lastError || "Not connected";
  elements["activity-label"].textContent = state.connected ? companionActivity(state.companion) : "Reconnecting…";
  renderMessages(state.messages);
  renderProviders(state.status?.providers || {});
  renderTasks(state.tasks);
  renderTraces(state.traces);
}

function renderMessages(messages) {
  elements["message-list"].replaceChildren();
  if (!messages.length) {
    const empty = document.createElement("li");
    empty.className = "empty";
    empty.textContent = "Start a conversation with SORA.";
    elements["message-list"].append(empty);
    return;
  }
  for (const message of messages) {
    const item = document.createElement("li");
    item.className = `message ${message.role === "user" ? "user" : "assistant"}`;
    const role = document.createElement("span");
    role.className = "role";
    role.textContent = message.role === "user" ? "You" : "SORA";
    const content = document.createElement("span");
    content.textContent = String(message.content || "");
    item.append(role, content);
    elements["message-list"].append(item);
  }
  elements["message-list"].scrollTop = elements["message-list"].scrollHeight;
}

function renderProviders(providers) {
  elements["provider-list"].replaceChildren();
  for (const [id, provider] of Object.entries(providers)) {
    const chip = document.createElement("span");
    chip.className = `provider ${provider.available ? "" : "offline"}`;
    chip.textContent = provider.display_name || id;
    chip.title = provider.available ? "Available" : "Unavailable";
    elements["provider-list"].append(chip);
  }
}

function renderTasks(tasks) {
  elements["task-list"].replaceChildren();
  if (!tasks.length) {
    const empty = document.createElement("li");
    empty.className = "empty";
    empty.textContent = "No agent tasks yet.";
    elements["task-list"].append(empty);
    return;
  }
  for (const task of tasks) {
    const item = document.createElement("li");
    item.className = "task";
    const title = document.createElement("p");
    title.className = "task-title";
    title.textContent = String(task.intent || task.constraints?.[0] || task.task_id || "Task");
    const meta = document.createElement("p");
    meta.className = "task-meta";
    meta.textContent = task.status === "planned"
      ? "TODO · no specialist started"
      : `${task.effective_backend || task.provider || "unassigned"} · ${task.status || "unknown"}`;
    const actions = document.createElement("div");
    actions.className = "task-actions";
    if (task.active_run_id && !isTerminal(task.status) &&
        (connectionMode === "owner" || activeRemoteScopes.has("tasks:control"))) {
      actions.append(taskButton("Steer", "steer", task.task_id), taskButton("Cancel", "cancel", task.task_id, "cancel"));
    }
    item.append(title, meta, actions);
    elements["task-list"].append(item);
  }
}

function taskButton(label, action, taskId, className = "") {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `quiet ${className}`.trim();
  button.dataset.action = action;
  button.dataset.taskId = taskId;
  button.textContent = label;
  return button;
}

function renderTraces(traces) {
  elements["trace-list"].replaceChildren();
  elements["trace-count"].textContent = String(traces.length);
  for (const trace of traces.slice().reverse()) {
    const item = document.createElement("li");
    item.textContent = `#${trace.sequence} ${trace.eventType}${trace.timestamp ? ` · ${trace.timestamp}` : ""}`;
    elements["trace-list"].append(item);
  }
}

function companionActivity(companion) {
  const activity = companion?.companion?.activity;
  return activity ? String(activity).replaceAll("_", " ") : "Ready";
}

function isTerminal(status) {
  return ["completed", "failed", "cancelled"].includes(String(status || "").toLowerCase());
}

function showToast(message) {
  elements.toast.textContent = String(message || "Something went wrong.");
  elements.toast.hidden = false;
  window.setTimeout(() => { elements.toast.hidden = true; }, 4500);
}

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  installPrompt = event;
  elements["install-button"].hidden = false;
});

elements["install-button"].addEventListener("click", async () => {
  if (!installPrompt) return;
  installPrompt.prompt();
  await installPrompt.userChoice;
  installPrompt = null;
  elements["install-button"].hidden = true;
});

if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("/service-worker.js", { scope: "/" }).catch(() => {
    showToast("Offline app shell could not be enabled. API data remains network-only.");
  });
}

loadPairedDevice()
  .then((record) => {
    pairedRecord = record;
    elements["reconnect-device-button"].hidden = !record;
  })
  .catch(() => {
    elements["pairing-error"].textContent = "Paired-device storage is unavailable in this browser.";
  });
