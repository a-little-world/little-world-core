First you set a static email host ein `envs/dev.env`: `DJ_EMAIL_STATIC_URL=https://little-world-formv2-bucket.s3.eu-central-1.amazonaws.com`

Then process is as follows:

- We change something in the backend templates ( `front/apps/admin_panel_frontend/src/emails/` )
- Then click the `[DEVELOPMENT] sync templates` button on `/matching/emails/` ( this updates the django templates )

Now the emails could be send locally if we set `DJ_SG_SENDGRID_API_KEY=`
But this shoudn't be required for now we can just test the emails on multiple clients at the same time using `testi.at`:

- Just run `/_scripts/pre_render_emails.sh` 

This creates a folder `rendered_test_emails` containing a `.zip` file for each email that we can directly upload to testi.at
This is then rendered a-cross clients and displayes us issues with the emails.