/**
 * DigitalOZO service worker.
 *
 * Strategie:
 * - /_next/static/*  → cache-first (immutable bundles, hash v URL)
 * - HTML navigace    → network-first s fallback na offline.html
 * - /api/*           → NIKDY cache (multi-tenant, security)
 * - icony, manifest  → cache-first
 *
 * Verze cache: bump CACHE_VERSION při změně SW pro nucený refresh.
 */

const CACHE_VERSION = "v1";
const STATIC_CACHE = `bozoapp-static-${CACHE_VERSION}`;
const PAGES_CACHE = `bozoapp-pages-${CACHE_VERSION}`;

const PRECACHE_URLS = [
  "/offline.html",
  "/manifest.json",
  "/icon-192.png",
  "/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => !k.endsWith(CACHE_VERSION))
          .map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // Jen same-origin
  if (url.origin !== self.location.origin) return;
  // Jen GET
  if (req.method !== "GET") return;

  // /api/* nikdy necachuj — multi-tenant data, auth tokeny
  if (url.pathname.startsWith("/api/")) return;

  // Statické bundles — cache-first (immutable díky hash v URL)
  if (url.pathname.startsWith("/_next/static/")) {
    event.respondWith(
      caches.match(req).then((cached) => {
        if (cached) return cached;
        return fetch(req).then((resp) => {
          if (resp.ok) {
            const clone = resp.clone();
            caches.open(STATIC_CACHE).then((c) => c.put(req, clone));
          }
          return resp;
        });
      })
    );
    return;
  }

  // Navigace (HTML) — network-first, fallback offline.html
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req)
        .then((resp) => {
          if (resp.ok) {
            const clone = resp.clone();
            caches.open(PAGES_CACHE).then((c) => c.put(req, clone));
          }
          return resp;
        })
        .catch(() =>
          caches.match(req).then((cached) =>
            cached || caches.match("/offline.html")
          )
        )
    );
    return;
  }

  // Ikony, manifest, ostatní statické v /public — cache-first
  if (
    url.pathname === "/manifest.json" ||
    url.pathname.startsWith("/icon-") ||
    url.pathname.endsWith(".png") ||
    url.pathname.endsWith(".svg") ||
    url.pathname.endsWith(".ico")
  ) {
    event.respondWith(
      caches.match(req).then((cached) => cached || fetch(req).then((resp) => {
        if (resp.ok) {
          const clone = resp.clone();
          caches.open(STATIC_CACHE).then((c) => c.put(req, clone));
        }
        return resp;
      }))
    );
    return;
  }

  // Ostatní — passthrough (žádné cache)
});

// Skill: client → SW message pro skipWaiting (nucený update bez refresh)
self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});
