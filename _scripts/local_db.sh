#!/bin/bash
# 'IMPORT_BACKUP=true ./_scripts/local_db.sh'

# Set variables
DB_NAME="dbname"
DB_USER="postgres"
DB_PASSWORD="dbpass"
BACKUP_FILE="2024-06-21_23-18-20.sql.gz"

# docker run -it -e PGPASSWORD="$DB_PASS" --rm mypostgres psql -h $DB_HOST -d $DB_NAME -U $DB_USER 

IMPORT_BACKUP=${IMPORT_BACKUP:-false}

# Pull the latest PostgreSQL Docker image
docker pull postgres

# lOCAL
if [ "$IMPORT_BACKUP" = true ]; then
  # Check if the backup file exists
  if [ ! -f $BACKUP_FILE ]; then
    echo "The backup file '$BACKUP_FILE' does not exist."
    exit 1
  fi
  docker rm -f mypostgres || true
fi


# Run the PostgreSQL Docker container
if [ ! "$IMPORT_BACKUP" = true ]; then
  docker start mypostgres || true
else
  docker run -d --name mypostgres \
    -e POSTGRES_DB=$DB_NAME \
    -e POSTGRES_USER=$DB_USER \
    -e POSTGRES_PASSWORD=$DB_PASSWORD \
    -p 5432:5432 \
    -v /home/tim-schupp/.little-world/local_db:/var/lib/postgresql/data \
    postgres
fi

echo "Waiting for the PostgreSQL service to start..."
sleep 2
# Create the database
docker exec -it mypostgres psql -U $DB_USER -c "CREATE DATABASE $DB_NAME" || true

if [ "$IMPORT_BACKUP" = true ]; then
  # Import the backup file
  gunzip -c $BACKUP_FILE | docker exec -i mypostgres psql -U $DB_USER $DB_NAME
fi

docker exec -it mypostgres psql -U $DB_USER -c "\l" # List databases to verify connection