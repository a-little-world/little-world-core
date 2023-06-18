### Big Frontend Refactor

This document describes the routh outline and aim for refactoring all our little world frontends.

### What to port?

we want to move all: `little-world-frontend`, `little-world-user-form-v2` into one nextjs app.

We still need to bundle cookie-banner using webpack since we need to serve this also from wordpress or external pages.

We should consider if we want the `little-world-admin-panel` to be part of the nextjs app or if it should be kept seperate ( I think it should maybe be kept seperate ).

### Refactor base userData

@sean and I have already discussed which stucture this need to be implemented first:

```
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
```

### Refactor video call joining process

There is a still open issue with out video call process: https://github.com/a-little-world/little-world-frontend/issues/31

This issue causes firefox to ask for permission twice since it handles the permissions slighly diffrent on firefox.

This bug will likely also cause issue with the capacitor native port.

Also we want to add video call room join directly routes.

I.e.: `/video_room/<room-uuid>/` links should automaticly connect to a specific matches video room (if the user is logged in).


### Routing

There are two options here:

- completly move to nextjs-router ( is prob desirable for performance and consistency )
- mix between react-router and nextjs-router, this is possible and has been done before prob requres less refactoring but might be suboptimal

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
    
Amounts to nextjs pages:
index.jsx -> index page with automatic authentication check and redirects
form.jsx -> user form
um.jsx -> user management ( or rather user 'self' management )
app.jsx -> main dashboard ( old main_frontend )
```

### Refactor root websocket integration

Currently we are using the chat websocket to transmit some of the callbacks like:

- new match made ( triggers reload )
- incoming call ( triggers the incoming call pop-up with a 'join-now' button )

This should be updated, we rather want a seperate websocket for handling the root callbacks.

This should be directly connected to our redux implementation.

E.g.: If we have a 'notifications' redux store, we want a function that is calleed e.g.: `updateNotifications -> calls GET notifications page=X ...` and then we get a specific redux dispatch function `updateNofitications`.

Now there should be an update tag for that api e.g.: `{action: 'updateNofifications', payload: data-object }` the `data-object` should basicly be equivalent to the data that would be returned by `updateNotifications` callback.

This will allow us in the backend if a new notification needs to be triggered for a user, the backend can just transmit a `updateNotifications` event over the websocket canner, then frontend then automaticly calls the `updateNotifications` redux dispatch, updating the frontend displayed notifications and on native this might be used to trigger some system notification using: `@capacitor/push-notifications`...

I've already worked on an example implementation for this here: ...

### Refactor how frontends are severd from backend

Currently the backend just has access to the websocket bundles and can dynamicly coose when to render which frontend, this will change to:

```
user (loggedin ) -> requests page
--> backend --> loads user data
--> POST user_data to nextjs app
--> Nextjs serverside renderes page
--> backend serves page to user
```

The process is slighly different on mobile there only the data is requested from the backend but not the rendered page ( the app is already fully staicly bundles when on mobile ).

### update deployment configs

Deployment configs need to be adjusted to deploy and serve the nextjs app ( this should also scale horizonally )

A load test here should also be conducted!

### Capacitor integration

Ther will be some additional code written for native plattforms, we should generall use the capacitor check `Capacitor.isNative()`.

### The Video calls

The native webview on ios doesn't support web-rtc but luckly someone just build a native libary for that: https://github.com/agodin3z/twilio-video-ios-capacitor

On android the video calls should work from within the webview.


## Itterative development plan

1. update the user_data stucture by duplicating the main_frontend

Serve the update main frontend under app_v2/* refactor all the code as outlined above.

Serve it alongside the old frontend `/app` test all the function within the new app_v2 frontend if everything works the old frontend can be overwritten!

2. Seperately develop a inital nextjs app integrating for now the new user-form v2 and a simple experiement on video calls.

Test video calls on android and ios native! 

Only when this step sucessfully passed continue.

3. Update the nextjs draft to include routing and get all components form the `main_frontend` and `user_form_v2` to correctly render and interact with the backend.

4. Add the 'render though nextjs' apprach to the backend implementation. ! Alongside the old webpack stategry' test the new integration for all pages and serve it alongside the old approach untill it's stable!

5. Test and implement the new websocket integration refactor ( as desribed above )

6. Full tests native and web apps if sucessfull remove the old webpack stategies and remove all the old frontends

DONE!

...

7. Refactor chat implementation ( get rid of the old out-of-data frontend, some updated so backend apis also required )