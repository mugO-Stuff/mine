const CACHE_NAME = 'agendadia-v1';
const STATIC_ASSETS = [
  '/',
  '/static/css/style.css',
  '/static/js/script.js',
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
