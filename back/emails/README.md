## Little World Emails

These are all our current emails, click the link in the preview to view them

We have our own django app that manages emails, we use django templating to generate email html's and render them. Currently we use sendgrid to send the emails but the backend really doesn't matter.

### Adding a new email

To add a new email, edit the file `back/emails/mails.py` and add a new email to the `templates` list. Here, you will be asked to add a `@dataclasses` for the email's `params`. This should include all parameters that can be changed in an email (e.g., for `MatchMailParams`, that is `first_name`, `match_first_name`, `profile_link_url`).

Next, you need to add `texts` and `defaults`. `Default` is what is rendered when you want to view the email in the admin panel, while `text` contains the email's content. Make sure to have a unique `name` for every email and specify the `template` to be used. Our templates are pretty general, so if you don't want any specific components in the email, you're probably good with the `emails/welcome.html` template.

Once you've implemented your email, you can log in locally as an admin user and view them at `/emails/{email_name}`.

| Name                            | Preview                          | Receivers        | Condition                                                                                                     | Is Optional | New | Misc                                                     |
| ------------------------------- | -------------------------------- | ---------------- | ------------------------------------------------------------------------------------------------------------- | ----------- | --- | -------------------------------------------------------- |
| welcome email                   | [`/emails/welcome`](/emails/)    | All users        | After registration                                                                                            | No          | Old | Contains initial email confirmation                      |
| match made email                | `/emails/match`                  |                  | After match was confirmed by volunteer                                                                        | No          | Old |                                                          |
| password reset email            | `/emails/password_reset`         |                  | When a user wants to reset their password                                                                     | No          | Old |                                                          |
| new messages email              | `/emails/new_messages`           |                  | If the user has new unread messages (checked every hour)                                                      | Yes         | Old |                                                          |
| email unverified                | `/emails/email_unverified`       | Everybody        | User registered AND not confirmed email AND sign-up more than one day ago                                     | No          | New | Send only once per user max                              |
| unfinished user-form reminder 1 | `/emails/unfinished_user_form_1` | Everybody        | User registered AND verified email BUT still not finished user form AND two days passed since user registered | No          | New |                                                          |
| unfinished user-from reminder 2 | `/emails/unfinished_user_form_2` | Everybody        | User registered AND verified email BUT still not finished user form AND 10 days passed since user registered  | No          | New |                                                          |
| confirm match email 1           | `/emails/unfinished_user_form_1` | Volunteers       | When match suggestion found (instead of current match email)                                                  | No          | New | Changes in general matching state management needed      |
| confirm match email 2           | `/emails/unfinished_user_form_2` | Volunteers       | When match suggestion found AND 5 days passed without accepting                                               | No          | New |                                                          |
| still in contact mail           | `/emails/still_in_contact`       | Inactive matches | An INACTIVE match is a match that has not interacted within the last two weeks                                | Yes         | New | Not for self_unmatched matches, send only once per match |
| match resolved mail             | `/emails/match_resolved`         |                  |                                                                                                               | No          | New |                                                          |
