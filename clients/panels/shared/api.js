// Core API for panels. Pages call their own origin (/api/v1/...); the host (SoraShell's
// WebView2 request filter, or scripts/panels-dev-server.py in a browser) forwards the call to
// Core and adds the owner token. The token never reaches page code.

export class CoreError extends Error {
  constructor(message, { status = 0, code = "CORE_UNAVAILABLE" } = {}) {
    super(message);
    this.name = "CoreError";
    this.status = status;
    this.code = code;
  }

  /** True when Core could not be reached at all, rather than refusing the request. */
  get unavailable() {
    return this.status === 0 || this.status === 502 || this.status === 503 || this.status === 504;
  }
}

/** An exact Core identifier (task, memory, reference). Core does not percent-decode paths. */
export const ITEM_ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/;

/** The ID as a path segment: checked, then inserted unchanged (":" must stay ":"). */
export function itemPath(id) {
  if (typeof id !== "string" || !ITEM_ID.test(id) || id.includes("..")) {
    throw new TypeError("Use an exact Core identifier.");
  }
  return id;
}

export class CoreApi {
  constructor({ fetchImpl = globalThis.fetch?.bind(globalThis), base = "" } = {}) {
    this.fetch = fetchImpl;
    this.base = base;
  }

  async request(path, { method = "GET", body, signal } = {}) {
    if (!path.startsWith("/api/v1/")) throw new TypeError("Panels may only call /api/v1/ routes.");
    let response;
    try {
      response = await this.fetch(this.base + path, {
        method,
        headers: body === undefined ? { Accept: "application/json" }
          : { Accept: "application/json", "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
        cache: "no-store",
        signal,
      });
    } catch (error) {
      if (error?.name === "AbortError") throw error;
      throw new CoreError("SORA's Core is not reachable.");
    }
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = data?.error ?? {};
      throw new CoreError(detail.message || `Core returned ${response.status}.`,
        { status: response.status, code: detail.code || "CORE_ERROR" });
    }
    return data;
  }

  messages(limit = 100) { return this.request(`/api/v1/messages?limit=${limit}`); }
  status() { return this.request("/api/v1/status"); }
  dialogue(content, requestId, signal, filePaths = []) {
    const body = { content, request_id: requestId };
    if (filePaths.length) body.file_paths = filePaths;
    return this.request("/api/v1/dialogue", { method: "POST", body, signal });
  }
  cancelDialogue(requestId) {
    return this.request("/api/v1/dialogue/cancel", { method: "POST", body: { request_id: requestId } });
  }

  // Event feed and the records it points at (tasks, memories).
  events(since, limit = 100) {
    return this.request(`/api/v1/events?since_sequence=${since}&limit=${limit}`);
  }
  voice() { return this.request("/api/v1/voice/local"); }
  voiceAction(action) {
    return this.request("/api/v1/voice/local", { method: "POST", body: { action } });
  }
  async task(taskId) { return this.request(`/api/v1/tasks/${itemPath(taskId)}`); }
  agents() { return this.request("/api/v1/agents/catalogue"); }
  tasks(limit = 50) { return this.request(`/api/v1/tasks?limit=${limit}`); }
  async taskEvidence(taskId) {
    return this.request(`/api/v1/tasks/${itemPath(taskId)}/evidence`);
  }
  async cancelTask(taskId) {
    return this.request(`/api/v1/tasks/${itemPath(taskId)}/cancel`, { method: "POST", body: {} });
  }
  async steerTask(taskId, instruction) {
    return this.request(`/api/v1/tasks/${itemPath(taskId)}/steer`,
      { method: "POST", body: { instruction } });
  }
  async memory(memoryId) { return this.request(`/api/v1/memories/${itemPath(memoryId)}`); }

  // Agents: the cached catalogue is free to read; refreshing asks each agent for its models.
  refreshAgents(signal) {
    return this.request("/api/v1/agents/catalogue/refresh", { method: "POST", body: {}, signal });
  }
  /** Start a delegated task. The body carries its own idempotency_key, reused on an exact retry. */
  delegate(body) { return this.request("/api/v1/tasks", { method: "POST", body }); }

  // Project paths: who holds a writer reservation, and the recent write evidence.
  paths() { return this.request("/api/v1/paths"); }
  reconcilePaths() { return this.request("/api/v1/paths/reconcile", { method: "POST", body: {} }); }

  // Memory. Filters are checked by the page's model before they get here.
  memories({ q = "", state = "active", project = "all", scope = "", cursor = null } = {}) {
    const query = `limit=50&state=${state}&project=${project}&q=${encodeURIComponent(q)}`
      + `&scope=${encodeURIComponent(scope)}${cursor ? `&cursor=${cursor}` : ""}`;
    return this.request(`/api/v1/memories?${query}`);
  }
  async correctMemory(memoryId, body) {
    return this.request(`/api/v1/memories/${itemPath(memoryId)}/correct`, { method: "POST", body });
  }
  async forgetMemory(memoryId, body) {
    return this.request(`/api/v1/memories/${itemPath(memoryId)}/forget`, { method: "POST", body });
  }
  async memoryReceipt(requestId) { return this.request(`/api/v1/memory-mutations/${itemPath(requestId)}`); }
  contentReferences() { return this.request("/api/v1/content/references"); }
  async openReference(referenceId) {
    return this.request("/api/v1/content/navigate", { method: "POST", body: {
      utterance: "open this referenced content", verb: "open", explicit_reference_id: itemPath(referenceId) } });
  }

  identity() { return this.request("/api/v1/runtime/identity"); }
  /** What the companion is running (dialogue model, voice), as Core reports it. */
  companion() { return this.request("/api/v1/projections/companion"); }

  // Settings (owner-local; Core checks the revision so a stale page cannot overwrite).
  settings() { return this.request("/api/v1/projections/settings"); }
  saveSettings(edit) { return this.request("/api/v1/settings", { method: "POST", body: edit }); }
  reloadModel(revision) {
    return this.request("/api/v1/model/reload", { method: "POST", body: { expected_revision: revision } });
  }
  refreshSettings() { return this.request("/api/v1/settings/refresh", { method: "POST", body: {} }); }
  projectors(modelPath) {
    return this.request("/api/v1/models/projectors", { method: "POST", body: { model_path: modelPath } });
  }
}
