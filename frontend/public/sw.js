// Service worker de la prueba de push (Fase 4). En iOS, cada push debe mostrar una notificación.
self.addEventListener('push', (event) => {
  let data = { title: 'CompaBook', body: '' }
  try {
    data = event.data.json()
  } catch {
    // Sin carga útil: se muestra el aviso genérico.
  }
  event.waitUntil(
    self.registration.showNotification(data.title, { body: data.body, icon: '/icon-192.png' }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windows) => {
      if (windows.length > 0) return windows[0].focus()
      return self.clients.openWindow('/')
    }),
  )
})
