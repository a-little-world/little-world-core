### Guide on setting up and running a local database

1. Optain a entrypted backup `localdb.sql.gz.encrypted` ( was encrypted via `openssl enc -aes-256-cbc -salt -pbkdf2 -in localdb.sql.gz -out localdb.sql.gz.encrypted` )

2. Decrypt the backup

ThisTheBestPasswordJus!stFor5ean

```bash
openssl enc -aes-256-cbc -d -pbkdf2 -in localdb.sql.gz.encrypted -out localdb.sql.gz
```

3. Make sure the `_scripts/local_db.sh` references the correct backup.

Start it ONCE ONLY with this command: `IMPORT_BACKUP=true ./_scripts/local_db.sh`

This can take up to 20! as it will decompress and import the whole database!

4. Setup `envs/dev.env`

Add the following ( remove them if you want to use the local mysql db again )

```bash
DJ_DATABASE_ENGINE="postgresql_psycopg2"
DJ_DATABASE_NAME="dbname"
DJ_DATABASE_USERNAME="postgres"
DJ_DATABASE_PASSWORD="dbpass"
DJ_DATABASE_HOST="host.docker.internal"
DJ_DATABASE_PORT="5432"
DJ_DATABASE_DISABLE_SSL="true"
```

5. Now everytime you run `./_scripts/local_dh.sh` is whould just re-start the already imported database and you should be good to coninue