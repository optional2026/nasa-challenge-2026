// ASTRA service worker — caches ONLY the application shell (index.html, built JS/CSS, icon, manifest) so the
// previously loaded app can open when the network is unavailable. API calls (/api/*) and the real-time channel
// (/ws) are NEVER cached: health data always comes from the server (the onboard server is the authoritative
// database; browser storage is not a replacement for it). Each server origin (onboard / Earth) has its own cache.
const CACHE = "astra-shell-v1";
const SHELL = ["/", "/manifest.webmanifest", "/icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/ws")) return; // never cache data
  if (req.mode === "navigate") {
    // network first: always the current app when the server is reachable; cached shell otherwise
    event.respondWith(fetch(req).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put("/", copy));
      return res;
    }).catch(() => caches.match("/").then((r) => r || Response.error())));
    return;
  }
  if (url.pathname.startsWith("/assets/") || SHELL.includes(url.pathname)) {
    // content-hashed build assets: cache first
    event.respondWith(caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); }
      return res;
    })));
  }
});
