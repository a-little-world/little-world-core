{% load temp_utils %}
{% get_base_url as BASE_URL %}

importScripts(
  "https://www.gstatic.com/firebasejs/11.5.0/firebase-app-compat.js"
);
importScripts(
  "https://www.gstatic.com/firebasejs/11.5.0/firebase-messaging-compat.js"
);

firebase.initializeApp({
  apiKey: "{{ apiKey }}",
  authDomain: "{{ authDomain }}",
  projectId: "{{ projectId }}",
  storageBucket: "{{ storageBucket }}",
  messagingSenderId: "{{ messagingSenderId }}",
  appId: "{{ appId }}",
  measurementId: "{{ measurementId }}",
});

const messaging = firebase.messaging();

async function onBackgroundMessage(payload) {
  const notificationTitle = payload.data.title;
  const notificationOptions = {
    body: payload.data.body,
  };

  await self.registration.showNotification(
    notificationTitle,
    notificationOptions
  );
}

messaging.onBackgroundMessage((payload) => {
  const notificationTitle = payload.data.title;
  const notificationOptions = {
    body: payload.data.body,
  };

  return self.registration.showNotification(
    notificationTitle,
    notificationOptions
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  // This looks to see if the tab current is already open and focuses if it is
  event.waitUntil(
    event.target.clients
      .matchAll({
        type: "window",
        includeUncontrolled: true,
      })
      .then((clientList) => {
        for (const client of clientList) {
          if (
            client.url.startsWith("{{ BASE_URL }}") &&
            "focus" in client
          )
            return client.focus();
        }
        if (clients.openWindow) return clients.openWindow("/");
      })
  );
});

self.addEventListener("install", (event) => {
  self.skipWaiting(); // Force the service worker to take control immediately
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    clients.claim() // Ensure the service worker takes control of all open clients
  );
});
