// 見どころなう 通知の受け取り役（サービスワーカー）
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let d = { title: "見どころなう", body: "見どころです", url: "./" };
  try { d = Object.assign(d, event.data.json()); } catch (_) {}
  event.waitUntil(self.registration.showNotification(d.title, {
    body: d.body,
    icon: "icon-192.png",
    badge: "icon-192.png",
    data: { url: d.url },
    tag: d.title,        // 同じ試合の通知はまとめる
    renotify: true,
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "./";
  event.waitUntil(self.clients.openWindow(url));
});
