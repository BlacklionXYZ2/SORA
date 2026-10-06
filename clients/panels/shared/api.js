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
  dialogue(content, requestId, signal) {
    return this.request("/api/v1/dialogue",
      { method: "POST", body: { content, request_id: requestId }, signal });
  }
  cancelDialogue(requestId) {
    return this.request("/api/v1/dialogue/cancel", { method: "POST", body: { request_id: requestId } });
  }
}
