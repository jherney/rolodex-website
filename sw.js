// Rolodex Service Worker — Offline-First PWA
const CACHE_NAME = 'rolodex-v14';
const ASSETS = [
  '/',
  '/vintage/styles.css',
  '/vintage/app.js',
  '/manifest.json'
];

// Install: cache core assets
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(ASSETS))
  );
  self.skipWaiting();
});

// Activate: clean old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch: network-first for API, cache-first for static
self.addEventListener('fetch', event => {
  // Only GETs can be cached; let writes (POST/PUT/DELETE) go straight to the network
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);

  // API calls are never cached or served from cache: they are per-account data, and a cached
  // copy could show one account's cards to the next person who signs in on this browser
  if (url.pathname.startsWith('/api/') || url.pathname === '/get_contacts' || url.pathname === '/save_contacts') {
    return;
  }

  // Static assets: network-first for app.js, cache-first for others
  const isAppJS = url.pathname === '/app.js';
  if (isAppJS) {
    event.respondWith(
      fetch(event.request)
        .then(resp => {
          const clone = resp.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          return resp;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }
  
  event.respondWith(
    caches.match(event.request)
      .then(cached => cached || fetch(event.request).then(resp => {
        const clone = resp.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        return resp;
      }))
  );
});
