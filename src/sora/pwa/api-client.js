export class SoraApiError extends Error {
  constructor(message, status = 0, code = "NETWORK_ERROR") {
    super(message);
    this.name = "SoraApiError";
    this.status = status;
    this.code = code;
  }
}

export class SoraApiClient {
  #token = "";
  #authorizationScheme = "Bearer";

  constructor({ baseUrl = globalThis.location?.origin ?? "http://127.0.0.1:8765", deviceId } = {}) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.deviceId = deviceId || `pwa-${globalThis.crypto?.randomUUID?.() ?? "local"}`;
  }

  setToken(token) {
    this.#authorizationScheme = "Bearer";
    this.#token = String(token || "").trim();
  }

  setAuthorization(scheme, token) {
    if (!["Bearer", "SoraSession"].includes(scheme)) throw new TypeError("Unsupported authorization scheme.");
    this.#authorizationScheme = scheme;
    this.#token = String(token || "").trim();
  }

  setDeviceId(deviceId) {
    this.deviceId = String(deviceId || "").trim();
  }

  clearToken() {
    this.#token = "";
  }

  get authenticated() {
    return this.#token.length > 0;
  }

  async request(path, { method = "GET", body } = {}) {
    if (!this.#token) throw new SoraApiError("Enter the local Core token to connect.", 401, "TOKEN_REQUIRED");
    const headers = {
      Accept: "application/json",
      Authorization: `${this.#authorizationScheme} ${this.#token}`,
      "X-SORA-Device-ID": this.deviceId,
    };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    let response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        cache: "no-store",
        credentials: "omit",
        referrerPolicy: "no-referrer",
      });
    } catch (error) {
      throw new SoraApiError(error instanceof Error ? error.message : "Core is unreachable.");
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = data?.error;
      throw new SoraApiError(detail?.message || `Core returned ${response.status}.`, response.status, detail?.code);
    }
    return data;
  }

  status() { return this.request("/api/v1/status"); }
  messages() { return this.request("/api/v1/messages?limit=100"); }
  tasks() { return this.request("/api/v1/tasks?limit=100&offset=0"); }
  companion() { return this.request("/api/v1/projections/companion"); }
  capabilities() { return this.request("/api/v1/projections/capabilities"); }
  dialogue(content, requestId) {
    return this.request("/api/v1/dialogue", { method: "POST", body: { content, request_id: requestId } });
  }
  cancelDialogue(requestId) {
    return this.request("/api/v1/dialogue/cancel", { method: "POST", body: { request_id: requestId } });
  }
  steer(taskId, instruction) {
    return this.request(`/api/v1/tasks/${encodeURIComponent(taskId)}/steer`, {
      method: "POST",
      body: { instruction },
    });
  }
  cancel(taskId) {
    return this.request(`/api/v1/tasks/${encodeURIComponent(taskId)}/cancel`, {
      method: "POST",
      body: {},
    });
  }
  events(sinceSequence, limit = 100) {
    return this.request(`/api/v1/events?since_sequence=${encodeURIComponent(sinceSequence)}&limit=${encodeURIComponent(limit)}`);
  }

  async publicRequest(path, { body, authorization = "" } = {}) {
    let response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-SORA-Device-ID": this.deviceId,
          ...(authorization ? { Authorization: authorization } : {}),
        },
        body: JSON.stringify(body || {}),
        cache: "no-store",
        credentials: "omit",
        referrerPolicy: "no-referrer",
      });
    } catch (error) {
      throw new SoraApiError(error instanceof Error ? error.message : "Core is unreachable.");
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = data?.error;
      throw new SoraApiError(detail?.message || `Core returned ${response.status}.`, response.status, detail?.code);
    }
    return data;
  }

  claimPairing(pairingCode, label) {
    return this.publicRequest("/api/v1/pairing/claim", {
      body: { pairing_code: pairingCode, device_id: this.deviceId, label },
    });
  }

  createRemoteSession(deviceCredential, scopes) {
    return this.publicRequest("/api/v1/pairing/session", {
      authorization: `SoraDevice ${deviceCredential}`,
      body: { device_id: this.deviceId, ...(scopes ? { scopes } : {}) },
    });
  }

  createPairingInvitation(label = "SORA browser") {
    return this.request("/api/v1/pairing/invitations", {
      method: "POST",
      body: { label, expires_in_seconds: 300 },
    });
  }

  pairedDevices() { return this.request("/api/v1/pairing/devices"); }
  revokeDevice(deviceId) {
    return this.request(`/api/v1/pairing/devices/${encodeURIComponent(deviceId)}/revoke`, {
      method: "POST",
      body: {},
    });
  }
}
