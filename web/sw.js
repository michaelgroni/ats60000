/**
 * Service Worker der PWA: statisches Caching fuer Offline-Start.
 * Netzwerkverbindung (Web Bluetooth) ist von Natur aus online-only.
 */

const CACHE = "ats-mini-remote-v1";
const ASSETS = [
  "./",
  "index.html",
  "style.css",
  "app.js",
  "protocol.js",
  "ble.js",
  "manifest.webmanifest",
  "icon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE)
    .then((cache) => cache.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) =>
    Promise.all(keys.filter((k) => k !== CACHE)
      .map((k) => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") {
    return;
  }
  event.respondWith(
    caches.match(event.request).then((cached) =>
      cached || fetch(event.request)),
  );
});
