## Admin Panel V2 Intro

We have a new admin pannel, that still work in progres.
But It's far enough along to be used for matching now and is designed to be used for our new confirmation based matching stategy.

## Contents

- Admin Panel Overview
- User Details Panel Overview
- The Chat Pane
- The Emails Pane
- The Matching Pane
- The Notes section

## The Admin Pannel

Visit `little-world.com/admin/login/?<your secret access key>` & login in.
The visit `little-world.com/admin_panel_v2/`.

### The List View

... Picture with arrows

### User Details View

... Picture with errors

### Regular Tasks

These things should be done regularly every 1-2 days:

#### 1. Check the Users To Match Lists (#1) `little-world.com/admin_panel_v2/list=...`

This is a list filtered for Volunteers that are looking for a match ( & have user-from completed + email verified ). The list is ordered by registration date ascending, so the oldest users that are looking for a match are at the top!
Also users flagged with `unmatchable`, `inactive` are not displayed!

For each one of these you should:

1. Check that the filled profile makes sense and the choice of volunteer / language learner makes sense. If it doesn't write a direct message to the user, an tag them as `in-review`.

> Always add a text-notice why you set a user to in-review in the 'notes' section

2. If step (1) was Ok go to the 'matching' tab and request a score cacluation.
The progress will be interactively displayed!

3. When this is done, you will receive a list of matching scores of `matchable=True` Learners ordered by highest score.
These results are orcourse also filtered for active, searching learners that have filled the user-form and verified their email.
You can view a user by clicking 'view' or you can add a user to your side-bar selection.

4. Check at least the top 5 matches, check there profiles manually
When a good match is found you can send out a matching proposal to the learner.
For that click on 'create matching proposal' then select the user you want to match from the selection side-bar.

5. If this is a valid matching you will see a pop-up 'matching proposal was created'.
The learner now has *7 days time* to accept or deny the matching. On the learners profile details card you can check that the matching confirmation email was send.

> Users that are waiting on a proposal confirmation are set to `searching=False` so they will no longer be listed in matchable users. Users that currently have an 'open-prematching" can be foound in the `list=...`

#### 2. Check the Message Reply required lists (#2)

This list contains all users that have send a message to the admin that was not 'read' yet. For all users in the list check the 'support-chat' in the 'chats' section.
You can either reply to the messsage, or click the message and select 'mark as read'


#### 3. Check the users in pre-marching lists

There aren't any specific TODO's for this list but this can be used to keep an eye on the existing matching proposals.

Proposals are automaticly closed when they expire after 7 days. The list is ordered by the age of the proposal in ascending order so you see the oldest proposals at the top.

But proposals shouldn't get old! If a proposal has been open for several days it might also be a nice idea to send a message to the learner and ask whats up, or maybe tell the volunteer that we are waiting on a active learner to reply.

#### 4. Check the 'users in review' list

#### 5 Check the proposals expired list
