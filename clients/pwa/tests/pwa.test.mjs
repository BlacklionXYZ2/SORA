import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { SoraApiClient, SoraApiError } from "../../../src/sora/pwa/api-client.js";
import { ProjectionStore, SyncCoordinator } from "../../../src/sora/pwa/sync.js";

const root = fileURLToPath(new URL("../../../", import.meta.url));

test("conversation Stop sends the same request nonce and preserves typed cancellation errors", async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    if (url.endsWith('/dialogue')) return new Response(JSON.stringify({
      error: { message: 'Stopped', code: 'DIALOGUE_CANCELLED' },
    }), { status: 409 });
    return new Response(JSON.stringify({ state: 'cancelled' }), { status: 200 });
  };
  try {
    const client = new SoraApiClient({ baseUrl: 'http://127.0.0.1:8765' });
    client.setToken('local-test-only');
    await assert.rejects(client.dialogue('Hello', 'turn-exact'), error =>
      error instanceof SoraApiError && error.code === 'DIALOGUE_CANCELLED');
    await client.cancelDialogue('turn-exact');
    assert.equal(JSON.parse(calls[0].options.body).request_id, 'turn-exact');
    assert.equal(JSON.parse(calls[1].options.body).request_id, 'turn-exact');
    assert.equal(calls[1].url, 'http://127.0.0.1:8765/api/v1/dialogue/cancel');
  } finally { globalThis.fetch = originalFetch; }
});

test("API credentials stay in memory and every authenticated fetch is network-only", async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return new Response(JSON.stringify({ status: "online" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  try {
    const client = new SoraApiClient({ baseUrl: "http://127.0.0.1:8765", deviceId: "test-device" });
    await assert.rejects(client.status(), (error) => error instanceof SoraApiError && error.code === "TOKEN_REQUIRED");
    client.setToken("header-only-secret");
    await client.status();
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, "http://127.0.0.1:8765/api/v1/status");
    assert.equal(calls[0].options.headers.Authorization, "Bearer header-only-secret");
    assert.equal(calls[0].options.cache, "no-store");
    assert.equal(calls[0].options.credentials, "omit");
    assert.equal(calls[0].url.includes("header-only-secret"), false);
    client.clearToken();
    assert.equal(client.authenticated, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("paired devices exchange a long-lived device credential for a memory-only scoped session", async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return new Response(JSON.stringify({ session_token: "short-session" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  try {
    const client = new SoraApiClient({
      baseUrl: "https://127.0.0.1:8766",
      deviceId: "phone-browser-0001",
    });
    await client.createRemoteSession("phone-browser-0001.device-secret", ["conversation:read"]);
    assert.equal(calls[0].options.headers.Authorization, "SoraDevice phone-browser-0001.device-secret");
    assert.equal(calls[0].options.cache, "no-store");
    assert.equal(calls[0].url.includes("device-secret"), false);

    client.setAuthorization("SoraSession", "short-session");
    await client.messages();
    assert.equal(calls[1].options.headers.Authorization, "SoraSession short-session");
    assert.equal(calls[1].options.cache, "no-store");
    assert.equal(calls[1].url.includes("short-session"), false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("a disconnected client converges to the same authoritative projections", async () => {
  let canonical = {
    messages: [{ message_id: "m1", role: "assistant", content: "one" }],
    tasks: { tasks: [{ task_id: "t1", status: "running" }] },
    companion: { companion: { activity: "working" } },
    capabilities: { available_verbs: ["send"] },
    status: { status: "online" },
  };
  let latestSequence = 1;
  const makeApi = () => ({
    messages: async () => canonical.messages,
    tasks: async () => canonical.tasks,
    companion: async () => canonical.companion,
    capabilities: async () => canonical.capabilities,
    status: async () => canonical.status,
    events: async (cursor, limit) => ({
      events: Array.from({ length: Math.min(limit, latestSequence - cursor) }, (_, index) => ({
        sequence: cursor + index + 1,
        type: "state.changed",
      })),
      next_sequence: Math.min(latestSequence, cursor + limit),
      latest_sequence: latestSequence,
      more_available: cursor + limit < latestSequence,
      resync_required: cursor > latestSequence,
    }),
  });
  const storeA = new ProjectionStore();
  const storeB = new ProjectionStore();
  const syncA = new SyncCoordinator(makeApi(), storeA, { pageLimit: 1 });
  const syncB = new SyncCoordinator(makeApi(), storeB, { pageLimit: 1 });
  await syncA.pollOnce();
  await syncB.pollOnce();

  canonical = {
    ...canonical,
    messages: [...canonical.messages, { message_id: "m2", role: "user", content: "offline change" }],
    tasks: { tasks: [{ task_id: "t1", status: "completed" }, { task_id: "t2", status: "running" }] },
    companion: { companion: { activity: "ready" } },
  };
  latestSequence = 4;
  await syncA.pollOnce();
  storeB.disconnected(new Error("offline"));
  await syncB.pollOnce();

  assert.deepEqual(storeB.state.messages, storeA.state.messages);
  assert.deepEqual(storeB.state.tasks, storeA.state.tasks);
  assert.deepEqual(storeB.state.companion, storeA.state.companion);
  assert.equal(storeB.state.lastSequence, 4);
  assert.equal(storeB.state.connected, true);
});

test("service worker caches only its fixed shell and explicitly bypasses API data", async () => {
  const source = await readFile(`${root}src/sora/pwa/service-worker.js`, "utf8");
  const shellLiteral = source.slice(source.indexOf("Object.freeze(["), source.indexOf("]);", source.indexOf("Object.freeze([")));
  assert.equal(shellLiteral.includes("/api/"), false);
  assert.match(source, /url\.pathname\.startsWith\("\/api\/"\)/);
  assert.match(source, /fetch\(request, \{ cache: "no-store" \}\)/);
  assert.doesNotMatch(source, /caches\.match\([^)]*api/i);
  assert.doesNotMatch(source, /cache\.put/);
});

test("manifest and generated PNGs meet installable app-shell requirements", async () => {
  const manifest = JSON.parse(await readFile(`${root}src/sora/pwa/manifest.webmanifest`, "utf8"));
  assert.equal(manifest.start_url, "/app");
  assert.equal(manifest.display, "standalone");
  assert.deepEqual(manifest.icons.map((icon) => icon.sizes), ["192x192", "512x512"]);
  for (const size of [192, 512]) {
    const png = await readFile(`${root}src/sora/pwa/icons/sora-${size}.png`);
    assert.equal(png.subarray(1, 4).toString("ascii"), "PNG");
    assert.equal(png.readUInt32BE(16), size);
    assert.equal(png.readUInt32BE(20), size);
  }
});

test("conversation, microphone, task control, and optional traces are present", async () => {
  const html = await readFile(`${root}src/sora/pwa/index.html`, "utf8");
  const app = await readFile(`${root}src/sora/pwa/app.js`, "utf8");
  for (const control of ["message-input", "mic-button", "task-list", "trace-panel"]) {
    assert.match(html, new RegExp(`id="${control}"`));
  }
  assert.match(app, /api\.dialogue\(content, requestId\)/);
  assert.match(app, /api\.cancelDialogue\(requestId\)/);
  assert.match(html, /id="stop-response"/);
  assert.match(app, /api\.steer\(taskId, instruction\.trim\(\)\)/);
  assert.match(app, /api\.cancel\(taskId\)/);
  assert.match(app, /SpeechRecognition/);
  assert.match(html, /may not be local/);
});

test("remote pairing UI and vault never persist the owner or short-lived session token", async () => {
  const html = await readFile(`${root}src/sora/pwa/index.html`, "utf8");
  const app = await readFile(`${root}src/sora/pwa/app.js`, "utf8");
  const vault = await readFile(`${root}src/sora/pwa/device-vault.js`, "utf8");
  assert.match(html, /id="pairing-form"/);
  assert.match(html, /id="create-pairing-button"/);
  assert.match(html, /id="paired-device-list"/);
  assert.match(app, /setAuthorization\("SoraSession", session\.session_token\)/);
  assert.match(vault, /indexedDB\.open/);
  assert.match(vault, /deviceCredential/);
  assert.doesNotMatch(vault, /session[_A-Z]?token/i);
  assert.doesNotMatch(vault, /owner.*token/i);
  assert.doesNotMatch(vault, /localStorage|sessionStorage/);
});
