importScripts(
  "https://www.gstatic.com/firebasejs/11.5.0/firebase-app-compat.js",
);
importScripts(
  "https://www.gstatic.com/firebasejs/11.5.0/firebase-messaging-compat.js",
);

// Check if Firebase app is already initialized to prevent duplicate-app error
if (!firebase.apps.length) {
  firebase.initializeApp({
    apiKey: "{{ apiKey }}",
    authDomain: "{{ authDomain }}",
    projectId: "{{ projectId }}",
    storageBucket: "{{ storageBucket }}",
    messagingSenderId: "{{ messagingSenderId }}",
    appId: "{{ appId }}",
    measurementId: "{{ measurementId }}",
  });
}

// Must be registered before firebase.messaging(), the SDK's own notificationclick
// handler calls stopImmediatePropagation() and would swallow this one.
self.addEventListener("notificationclick", (event) => {
  event.stopImmediatePropagation();
  event.notification.close();

  // FCM wraps the original message payload when it auto-displays a notification
  const data =
    event.notification.data?.FCM_MSG?.data ?? event.notification.data ?? {};
  const path =
    typeof data.path === "string" && data.path.startsWith("/")
      ? data.path
      : "/";
  const url = self.location.origin + path;

  // Focus an already open tab and hand the path to the running app, which routes
  // to it without a page load. client.navigate() would reload the whole app.
  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((clientList) => {
        const client = clientList.find((c) =>
          c.url.startsWith(self.location.origin),
        );
        if (!client) {
          return self.clients.openWindow(url);
        }
        return client.focus().then((focused) => {
          focused.postMessage({ type: "NAVIGATE", path });
        });
      }),
  );
});

const messaging = firebase.messaging();

self.addEventListener("install", (event) => {
  self.skipWaiting(); // Force the service worker to take control immediately
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    clients.claim(), // Ensure the service worker takes control of all open clients
  );
});
