### Little Worlds `management` module

This is our core logic module, it handles everything

## Migrations

As we are using the beauty of Docker containers, any migrations need to be done from with the appropriate backend container.

The container id can be found using `docker ps`.
Usually containers will be named as such: `localhost:32000/backend:registry`

You can access the contianer either through the Docker desktop app or through the cli:
`docker exec -it <container-id> sh`

When making any changes that impact the database model itself, you will need to make new migrations.
`python3 manage.py makemigrations` will auto create migration files. Most of the time you won't need to edit these files but do check them after they are created.

To apply existing migrations to a database:
`python3 manage.py migrate`

## Locally trigger websocket actions

For a number of features in our app we utilise websockets.
In order to test these websockets locally and there associated features, you can do so by entering into the python shell in the running docker container.

Make sure you have the local server running, then run:
`docker exec -it <container-id> sh`
This will enter you into the docker container. Then:
`python3 manage.py shell`
Now you're in the shell where you can trigger websocket calls.
Some examples of triggering calls are below.

```
from management.models.user import User
from chat.consumers.messages import PostCallSurvey
user = User.objects.get(email=...)
PostCallSurvey(post_call_survey={"live_session_id": "Random-UUID"}).send(user.hash)
```

or

```
   from management.models.user import User
from chat.consumers.messages import NewActiveCallRoom

NewActiveCallRoom(
    call_room={
        "uuid": "e8c87fc9-ee8f-4529-bda0-8a86b3ba7d58",
        "created_at": "2025-01-31T10:56:16.250840+01:00",
        "activeUsers": [
            "0f12ec83-fbd5-4e69-8452-f7af3116e570-374bdfe6-515b-48d9-bf0a-89a179e1b7a7"
        ],
        "partner": {
            "first_name": "Tim",
            "interests": [],
            "availability": {
                "fr": [],
                "mo": [],
                "sa": [],
                "su": [],
                "th": [],
                "tu": [],
                "we": [],
            },
            "notify_channel": "email",
            "phone_mobile": "",
            "image_type": "image",
            "lang_skill": [],
            "avatar_config": {},
            "image": "https://litttle-world-staging-bucket.s3.eu-central-1.amazonaws.com/static/profile_pics/0f12ec83-fbd5-4e69.67a4c211-3818-4878-b020-82b67317361b-fcb087e3-d991-41be-8f76-6c0.png",
            "description": "\nHello there 👋\n\n",
            "additional_interests": "",
            "language_skill_description": "",
            "user_type": "learner",
            "id": "0f12ec83-fbd5-4e69-8452-f7af3116e570-374bdfe6-515b-48d9-bf0a-89a179e1b7a7",
        },
    }
).send(user.hash)
```
