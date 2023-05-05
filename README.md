## Little World Backend V2

The backend for the little world web-application and its services.

> For stack info check [`django-clean-state`](https://github.com/tbscode/django-clean-slate)

### Development, Documentation & Apis

The default staging server is deployed at [`s1.littleworld-test.com`](https://s1.littleworld-test.com)
For viewing documentation and apis you can loging with a test user:

by visiting:

[`https://s1.littleworld-test.com/api/user/login?token=devUserAutoLoginTokenXYZ&u=devuser@mail.com&l=email&n=/docs`](https://s1.littleworld-test.com/api/user/login?token=devUserAutoLoginTokenXYZ&u=devuser@mail.com&l=email&n=/docs)

Or you can login manually at [`https://s1.littleworld-test.com/login`](https://s1.littleworld-test.com/login)
with the default staging user `pw: Test321!`, `email: default.devuser@mail.com`.

When you logged in you can view the **Documentation** at [`https://s1.littleworld-test.com/docs`](https://s1.littleworld-test.com/docs)

###### Authors

@tbscode, tim@timschupp.de

### tasks reformulated

Roadmap to finished beta [https://app.clickup.com/t/861mpnjqu]

- email: add unsubscribe button ( for all mails that are optional )
- email: implement autosend lists ( as descibed in email docs )
  - /emails/next_steps [https://app.clickup.com/t/861mq18xk]
  - /emails/email_unverified
  - /emails/unfinished_user_form_1
  - /emails/unfinished_user_form_2
  - /emails/confirm_match_1
  - /emails/confirm_match_2
  - /emails/still_in_contact [https://app.clickup.com/t/863gj9at8]
  - /emails/match_resolved
  - design and implement a stale user activation email
- docs: deploy new documentation, make it acessible a little more complete
- question-cards: add basic question cards
  - gather question cards from oliver (?)
- translations: redeploy and integrate suggestions
  - integrate all backend suggestions
- user-form-old: integrate beta fixes:
  - beta anmerkung ramen verbessern [https://app.clickup.com/t/325whhj]
  - add gaps between lines [https://app.clickup.com/t/34aga3u]
- new-user-form:
  - make sure it works on safari and internet explorer [https://app.clickup.com/t/34g5czm]
- main-frontend: general fixes and beta polishing
  - kaffeklatsch -> gruppen gespracht
  - change password api
  - email subscribtion settings
  - send messages only on shift + enter / button press
  - interests: psycology -> psychology
  - Kontaktseite: zuer -> zur
  - camera and mike permission reiteratte on present bugs ( firefox mobile still shows camera used after leaving for me @tbscode ) [https://app.clickup.com/t/861m9u5nd] & another task for email
  - delete account button [https://app.clickup.com/t/861m9u6v3]
  - post video call screen [https://app.clickup.com/t/861mpnjt0]
  - fix and finish unmatch modal
- admin pannel:

  - seperate text descriptions from other search values [https://app.clickup.com/t/32q36wv]
  - allow admins to mark messages as read [https://app.clickup.com/t/861m4a8cc]
  - allow copying user hash [https://app.clickup.com/t/861m6ea37]
  - investigate some messages not correctly marked as read admin pannel [https://app.clickup.com/t/861m7upkq]

- think waht to give to mike
- checkout the KPI again
- list problems with clickup ( make a shared document )
