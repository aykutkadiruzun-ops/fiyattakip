const CACHE_VERSION = 'v2';

self.addEventListener('install', event => {
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_VERSION).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('push', function(event) {
  const data = event.data ? event.data.json() : {};
  const title = data.title || 'Rafta';
  const options = {
    body: data.body || 'Fiyat değişikliği var!',
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    data: { url: data.url || 'https://rafta.net' }
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', function(event) {
  event.notification.close();
  const url = event.notification.data?.url || 'https://rafta.net';
  event.waitUntil(clients.openWindow(url));
});
