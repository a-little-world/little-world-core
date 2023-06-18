## Big Frontend Refactor

This document describes the rough outline and aim for refactoring all our little world frontends.

### What to port?

We want to move all: `little-world-frontend`, `little-world-user-form-v2` into one Next.js app.

We still need to bundle the cookie-banner using Webpack, since we need to serve this also from WordPress or external pages.

We should consider if we want the `little-world-admin-panel` to be part of the Next.js app or if it should be kept separate (I think it should maybe be kept separate).

### Refactor base userData

Sean and I have already discussed which structure this needs to be implemented first:

```js
const {
        user: {
          id,
          isSearching,
          profile,
          settings: {
            displayLang,
            fontSize,
          }
        },
        notifications: {
          items: [],
          totalItems: 100,
          itemsPerPage: 5,
          currentPage: 1,
        },
        state: usrState,
        matches: {
          support: [{
            status: MATCH_STATUS_SUPPORT
          }],
          confirmed: [
            {
              id: '1223',
              partner: {
                id: 'sdasd',
                image: '',
                name: '',
              },

            }
          ],
          proposed: [{
            id,
            partner: {
             // ...redacted partner fields
            },
          }],
          partiallyConfirmed: []
        },
        community_events,
        admin_infos: adminInfos,
}
```

### Refactor video call joining process

There is a still open issue with our video call process: https://github.com/a-little-world/little-world-frontend/issues/31

This issue causes Firefox to ask for permission twice since it handles the permissions slightly differently on Firefox.

This bug will likely also cause issues with the Capacitor native port.

Also, we want to add direct video call room join routes.

For instance, `/video_room/<room-uuid>/` links should automatically connect to a specific match's video room (if the user is logged in).

### Routing

There are two options here:

- Completely move to Next.js router (this is probably desirable for performance and consistency)
- Mix between React-router and Next.js router: this is possible and has been done before but might be suboptimal as it probably requires less refactoring

Sketch for the routing structure:

```
uf: user_form
mf: main_frontend

uf:
    form/:slug
    um/login
    um/register
    um/reset_password
    um/change_password
    um/verify_mail

mf:
    app/
    app/call
    app/partners
    app/chat
    app/notifications
    app/profile
    app/help
    app/settings

Amounts to Next.js pages:
index.jsx -> index page with automatic authentication check and redirects
form.jsx -> user form
um.jsx -> user management (or rather user 'self' management)
app.jsx -> main dashboard (old main_frontend)
```

### Refactor root WebSocket integration

Currently, we are using the chat WebSocket to transmit some of the callbacks like:

- New match made (triggers reload)
- Incoming call (triggers the incoming call pop-up with a 'join-now' button)

This should be updated; we would rather want a separate WebSocket for handling the root callbacks.

This should be directly connected to our Redux implementation.

For example, if we have a 'notifications' Redux store, we want a function that is called, e.g., `updateNotifications -> calls GET notifications page=X ...` and then we get a specific Redux dispatch function `updateNotifications`.

Now there should be an update tag for that API, e.g., `{action: 'updateNofifications', payload: data-object }`. The `data-object` should be equivalent to the data that would be returned by the `updateNotifications` callback.

This will allow us in the backend, when a new notification needs to be triggered for a user, the backend can simply transmit an `updateNotifications` event over the WebSocket channel. The frontend then automatically calls the `updateNotifications` Redux dispatch, updating the frontend displayed notifications, and on native, this might be used to trigger some system notification using: `@capacitor/push-notifications`...

I've already worked on an example implementation for this here: ...

### Refactor how frontends are served from backend

Currently, the backend just has access to the WebSocket bundles and can dynamically choose when to render which frontend. This will change to:

```
user (loggedin ) -> requests page
--> backend --> loads user data
--> POST user_data to Next.js app
--> Next.js server-side renders page
--> backend serves page to user
```

The process is slightly different on mobile: there, only the data is requested from the backend but not the rendered page (the app is already fully statically bundled when on mobile).

### Update deployment configs

Deployment configs need to be adjusted to deploy and serve the Next.js app (this should also scale horizontally).

A load test here should also be conducted!

### Capacitor integration

There will be some additional code written for native platforms, and we should generally use the Capacitor check `Capacitor.isNative()`.

### The Video calls

The native WebView on iOS doesn't support WebRTC, but luckily someone just built a native library for that: https://github.com/agodin3z/twilio-video-ios-capacitor

On Android, the video calls should work from within the WebView.

## Iterative development plan

1. Update the user_data structure by duplicating the main_frontend.

   Serve the updated main frontend under app_v2/* refactor all the code as outlined above.

   Serve it alongside the old frontend `/app`. Test all the functions within the new app_v2 frontend. If everything works, the old frontend can be overwritten!

2. Separately develop an initial Next.js app, integrating for now the new user-form v2 and a simple experiment on video calls.

   Test video calls on Android and iOS native!

   Only when this step has successfully passed, continue.

3. Update the Next.js draft to include routing and get all components from the `main_frontend` and `user_form_v2` to correctly render and interact with the backend.

4. Add the 'render through Next.js' approach to the backend implementation. Serve it alongside the old Webpack strategy and test the new integration for all pages until it's stable!

5. Test and implement the new WebSocket integration refactor (as described above).

6. Conduct full tests native and web apps. If successful, remove the old Webpack strategies and remove all the old frontends.

DONE!

...

7. Refactor chat implementation (get rid of the old out-of-date frontend, some updated backend APIs also required).