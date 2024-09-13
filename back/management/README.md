### Little Worlds `management` module

This is our core logic module, it handels everything

## Migrations

As we are using the beauty of Docker containers, any migrations need to be done from with the appropriate backend container.

You can access the contianer either through the Docker desktop app or through the cli:
`docker exec -it <container-id> sh`

The container id can be found using `docker ps`.
Usually containers will be named as such: `localhost:32000/backend:registry`

When making any changes that impact the database model itself, you will need to make new migrations.
`python3 manage.py makemigrations` will auto create migration files. Most of the time you won't need to edit these files but do check them after they are created.

To apply existing migrations to a database:
`python3 manage.py migrate`
