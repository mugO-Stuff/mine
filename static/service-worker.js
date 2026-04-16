const CACHE_NAME = 'agendadia-v4';
const STATIC_ASSETS = [
  '/',
  '/manifest.webmanifest',
  '/favicon.ico',
  '/static/css/style.css',
  '/static/js/script.js',
  '/static/icons/icon-16x16.png',
  '/static/icons/icon-32x32.png',
  '/static/icons/icon-180x180.png',
  '/static/icons/icon-192x192.png',
  '/static/icons/icon-512x512.png'
  // Adicione outros arquivos estáticos importantes aqui
];

// Instalação: cacheia arquivos estáticos
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
});

// Ativação: limpa caches antigos
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))
      )
    )
  );
});

// Busca: responde com cache ou rede
self.addEventListener('fetch', event => {
  const { request } = event;
  // Só cacheia GET e arquivos estáticos
  if (request.method !== 'GET') return;

  const requestPath = new URL(request.url).pathname;

  if (requestPath === '/static/css/style.css') {
    // Network first para CSS: evita ficar preso em estilo antigo após deploy.
    event.respondWith(
      fetch(request)
        .then(response => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
          return response;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  if (request.url.includes('/static/')) {
    // Cache first para arquivos estáticos
    event.respondWith(
      caches.match(request).then(
        cached =>
          cached ||
          fetch(request).then(response => {
            const clone = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
            return response;
          })
      )
    );
  } else {
    // Network first para páginas dinâmicas
    event.respondWith(
      fetch(request)
        .then(response => {
          return response;
        })
        .catch(() => caches.match(request))
    );
  }
});

// Permite que a página principal solicite uma notificação via postMessage
// Útil para notificar mesmo quando a aba não está em foco (mobile/PWA)
self.addEventListener('message', event => {
  if (!event.data || event.data.type !== 'SHOW_NOTIFICATION') return;

  const title = event.data.title || 'AgendaDia';
  const options = {
    body: event.data.body || '',
    icon: '/static/icons/icon-192x192.png',
    badge: '/static/icons/icon-32x32.png',
    tag: 'chat-message',
    renotify: true,
    data: { url: '/chat' }
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('push', event => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = {};
  }

  const title = data.title || 'AgendaDia';
  const options = {
    body: data.body || 'Você tem um novo lembrete.',
    icon: data.icon || '/static/icons/icon-192x192.png',
    badge: data.badge || '/static/icons/icon-32x32.png',
    data: {
      url: data.url || '/'
    }
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(windowClients => {
      for (const client of windowClients) {
        if (client.url.includes(targetUrl) && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
      return null;
    })
  );
});
