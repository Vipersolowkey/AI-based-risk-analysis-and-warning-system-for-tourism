// Minimal service worker for Web Push severe-weather alerts.
// No caching/offline support — this app is not a full PWA, just needs a
// service worker registration to receive push events.

self.addEventListener("push", (event) => {
  let payload = { title: "Cảnh báo thời tiết", body: "Có cập nhật mới." };
  try {
    if (event.data) payload = event.data.json();
  } catch {
    // ignore malformed payload, use default
  }

  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: "window" }).then((clientList) => {
      for (const client of clientList) {
        if ("focus" in client) return client.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow("/");
    })
  );
});
