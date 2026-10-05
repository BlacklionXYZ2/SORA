const CACHE_NAME = "sora-app-shell-v3";
const APP_SHELL = Object.freeze([
  "/app",
  "/app.css",
  "/app.js",
  "/api-client.js",
  "/sync.js",
  "/device-vault.js",
  "/manifest.webmanifest",
  "/icons/sora-192.png",
  "/icons/sora-512.png",
]);
const APP_SHELL_PATHS = new Set(APP_SHELL);

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) => Promise.all(names.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Authenticated data is always network-only. There is deliberately no cached
  // fallback for API, health, or readiness responses.
  if (url.pathname.startsWith("/api/") || url.pathname === "/healthz" || url.pathname === "/readyz") {
    event.respondWith(fetch(request, { cache: "no-store" }));
    return;
  }

  if (request.method !== "GET") return;
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => (response.ok ? response : Promise.reject(new Error("navigation failed"))))
        .catch(() => caches.match("/app")),
    );
    return;
  }

  if (APP_SHELL_PATHS.has(url.pathname)) {
    event.respondWith(caches.match(request).then((cached) => cached || fetch(request)));
  }
});
